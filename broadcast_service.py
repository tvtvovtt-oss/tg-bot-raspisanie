import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from database import (
    get_broadcast,
    get_due_scheduled_broadcasts,
    update_broadcast_status,
    get_all_user_ids,
    get_admins
)
from premium_emoji import te, PE_MEGAPHONE, PE_CHECK, PE_BAN, PE_WARNING, PE_PEOPLE, PE_PAPERCLIP, strip_tg_emoji

logger = logging.getLogger(__name__)

# Задержка между отправками сообщений для защиты от лимитов Telegram API (25-30 msg/sec)
SEND_DELAY_SECONDS = 0.04
# Интервал проверки запланированных рассылок (в секундах)
CHECK_INTERVAL_SECONDS = 15


async def execute_broadcast(bot: Bot, broadcast_id: int):
    """
    Выполняет рассылку сообщений всем пользователям бота.
    Поддерживает закрепление сообщений (pin), подсчет статистики и отправку отчета автору.
    """
    bc = await get_broadcast(broadcast_id)
    if not bc:
        logger.error(f"Рассылка #{broadcast_id} не найдена в базе данных.")
        return

    if bc["status"] in ("in_progress", "completed", "cancelled"):
        logger.info(f"Рассылка #{broadcast_id} пропущена: статус {bc['status']}.")
        return

    # Переводим статус в in_progress
    await update_broadcast_status(broadcast_id, status="in_progress")
    logger.info(f"Запуск рассылки #{broadcast_id}...")

    user_ids = await get_all_user_ids()
    total = len(user_ids)
    msg_text = bc["message_text"]
    pin_message = bool(bc.get("pin_message", 0))
    created_by = bc.get("created_by")

    sent = 0
    blocked = 0
    failed = 0

    for uid in user_ids:
        sent_msg = None
        try:
            sent_msg = await bot.send_message(
                chat_id=uid,
                text=msg_text,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            sent += 1
        except TelegramBadRequest:
            try:
                # Фолбэк на текст без кастомных эмодзи в случае ошибки парсера Telegram
                sent_msg = await bot.send_message(
                    chat_id=uid,
                    text=strip_tg_emoji(msg_text),
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
                sent += 1
            except Exception as e2:
                logger.warning(f"Ошибка отправки сообщения пользователю {uid}: {e2}")
                failed += 1
        except TelegramForbiddenError:
            blocked += 1
        except Exception as e:
            err = str(e).lower()
            if "forbidden" in err or "blocked" in err or "chat not found" in err:
                blocked += 1
            else:
                logger.warning(f"Сбой отправки рассылки #{broadcast_id} пользователю {uid}: {e}")
                failed += 1

        # Закрепляем сообщение, если включена опция
        if pin_message and sent_msg:
            try:
                await bot.pin_chat_message(
                    chat_id=uid,
                    message_id=sent_msg.message_id,
                    disable_notification=True
                )
            except Exception as pin_err:
                logger.debug(f"Не удалось закрепить сообщение у пользователя {uid}: {pin_err}")

        await asyncio.sleep(SEND_DELAY_SECONDS)

    # Фиксируем завершение рассылки в БД
    completed_at_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    is_daily = (bc.get("repeat_type") == "daily")
    repeat_time_str = bc.get("repeat_time") or "07:00"

    if is_daily:
        # Для ежедневной рассылки переносим следующее выполнение на завтра
        try:
            rh, rm = map(int, repeat_time_str.split(":"))
        except Exception:
            rh, rm = 7, 0
        tomorrow_dt = (datetime.now() + timedelta(days=1)).replace(hour=rh, minute=rm, second=0, microsecond=0)
        next_scheduled_str = tomorrow_dt.strftime("%Y-%m-%d %H:%M:00")

        await update_broadcast_status(
            broadcast_id=broadcast_id,
            status="scheduled",
            total_targets=total,
            sent_count=sent,
            blocked_count=blocked,
            failed_count=failed,
            completed_at=completed_at_str,
            scheduled_at=next_scheduled_str
        )
        logger.info(
            f"Ежедневная рассылка #{broadcast_id} за сегодня выполнена. Следующая запланирована на {next_scheduled_str}"
        )
    else:
        await update_broadcast_status(
            broadcast_id=broadcast_id,
            status="completed",
            total_targets=total,
            sent_count=sent,
            blocked_count=blocked,
            failed_count=failed,
            completed_at=completed_at_str
        )
        logger.info(
            f"Рассылка #{broadcast_id} завершена: отправлено {sent}, заблокировано {blocked}, ошибок {failed} (всего {total})"
        )

    # Формируем и отправляем отчет создателю рассылки
    success_rate = f"{(sent / total * 100):.1f}%" if total > 0 else "0%"
    pin_status_str = "Да (закреплено)" if pin_message else "Нет"

    if is_daily:
        report_header = f"{te(PE_MEGAPHONE)} <b>Отчёт: ежедневная рассылка #{broadcast_id}</b>"
        next_line = f"{te(PE_WARNING)} <b>Следующая отправка:</b> <code>{tomorrow_dt.strftime('%d.%m.%Y в %H:%M')}</code>\n<i>Для отмены повторов перейдите в меню статистики рассылок (/statadmin).</i>\n\n"
    else:
        report_header = f"{te(PE_MEGAPHONE)} <b>Отчёт о завершении рассылки #{broadcast_id}</b>"
        next_line = ""

    report_text = (
        f"{report_header}\n\n"
        f"{te(PE_CHECK)} Доставлено: <b>{sent}</b> из <b>{total}</b> ({success_rate})\n"
        f"{te(PE_PAPERCLIP)} Закрепление в чатах: <b>{pin_status_str}</b>\n"
        f"{te(PE_BAN)} Заблокировали бота: <b>{blocked}</b>\n"
        f"{te(PE_WARNING)} Ошибок отправки: <b>{failed}</b>\n"
        f"{te(PE_PEOPLE)} Всего пользователей в базе: <b>{total}</b>\n\n"
        f"{next_line}"
        f"<i>Завершена: {completed_at_str}</i>"
    )

    recipients_for_report = set()
    if created_by:
        recipients_for_report.add(created_by)
    else:
        # Если автор не известен, отправляем всем админам
        admin_list = await get_admins()
        recipients_for_report.update(admin_list)

    for a_id in recipients_for_report:
        try:
            await bot.send_message(
                chat_id=a_id,
                text=report_text,
                parse_mode="HTML"
            )
        except Exception as rep_err:
            logger.warning(f"Не удалось отправить отчет о рассылке админу {a_id}: {rep_err}")


async def broadcast_scheduler_worker(bot: Bot):
    """
    Фоновый воркер, проверяющий запланированные рассылки по таймеру каждые 15 секунд.
    """
    logger.info("Фоновый планировщик отложенных рассылок запущен.")
    while True:
        try:
            due_broadcasts = await get_due_scheduled_broadcasts()
            for bc in due_broadcasts:
                logger.info(f"Наступило время выполнения запланированной рассылки #{bc['id']} ({bc.get('scheduled_at')}). Запуск...")
                # Запускаем рассылку в отдельном фоновом таске, чтобы не блокировать цикл
                asyncio.create_task(execute_broadcast(bot, bc["id"]))
        except asyncio.CancelledError:
            logger.info("Планировщик отложенных рассылок остановлен.")
            break
        except Exception as e:
            logger.error(f"Ошибка в фоновом планировщике рассылок: {e}", exc_info=True)

        try:
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            logger.info("Планировщик отложенных рассылок остановлен во время ожидания.")
            break
