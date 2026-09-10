import asyncio
import logging
from typing import Dict, List, Any
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from database import (
    get_users_for_notifications,
    is_user_notified,
    mark_user_notified
)
from parser import (
    get_available_dates,
    get_group_schedule,
    get_teacher_schedule,
    format_schedule_message,
    format_teacher_schedule_message,
    format_russian_date,
    format_schedule_notification_date,
    is_schedule_published
)
from keyboards import (
    get_schedule_nav_inline_keyboard,
    get_teacher_schedule_nav_inline_keyboard
)
from premium_emoji import te, PE_BELL, strip_tg_emoji

logger = logging.getLogger(__name__)

# Poll interval: 3 minutes (180 seconds)
POLL_INTERVAL_SECONDS = 180

# Tracks if this is the first execution after bot startup
_IS_FIRST_RUN = True


async def check_and_notify_users(bot: Bot):
    """
    Checks for newly published schedules and notifies subscribed users.
    Only checks official on-site published dates >= today.
    """
    global _IS_FIRST_RUN

    try:
        dates_info = await get_available_dates(force_refresh=True)
        today_str = dates_info.get("today") or datetime.now().strftime("%Y-%m-%d")
        # Only check dates that are officially published on the college site (not synthetic UI placeholders)
        available_dates = [
            d["date"] for d in dates_info.get("dates", [])
            if d.get("date", "") >= today_str and d.get("on_site", False)
        ]

        if not available_dates:
            return

        users = await get_users_for_notifications()
        if not users:
            return

        # On first startup, pre-mark existing current dates so we don't spam notifications
        # for schedules that were already available when bot launched
        if _IS_FIRST_RUN:
            for u in users:
                u_id = u["user_id"]
                if u.get("group_id"):
                    for d_str in available_dates:
                        await mark_user_notified(u_id, "group", u["group_id"], d_str)
                if u.get("teacher_id"):
                    for d_str in available_dates:
                        await mark_user_notified(u_id, "teacher", u["teacher_id"], d_str)
            _IS_FIRST_RUN = False
            logger.info(f"Notifier инициализирован: сохранено {len(users)} пользователей и {len(available_dates)} дат.")
            return

        # Group users by group_id and teacher_id to minimize requests to almetpt.ru
        groups_map: Dict[str, List[Dict[str, Any]]] = {}
        teachers_map: Dict[str, List[Dict[str, Any]]] = {}

        for u in users:
            if u.get("group_id"):
                groups_map.setdefault(str(u["group_id"]), []).append(u)
            if u.get("teacher_id"):
                teachers_map.setdefault(str(u["teacher_id"]), []).append(u)

        # 1. Process group schedules
        for g_id, group_users in groups_map.items():
            g_name = group_users[0].get("group_name") or f"Группа {g_id}"
            
            for date_str in available_dates:
                # Find users who have not received notification for this group and date
                pending_users = []
                for u in group_users:
                    notified = await is_user_notified(u["user_id"], "group", g_id, date_str)
                    if not notified:
                        pending_users.append(u)

                if not pending_users:
                    continue

                # Fetch schedule once for this group and date
                sched = await get_group_schedule(g_id, date_str, force_refresh=True)
                if not is_schedule_published(sched):
                    # If empty, 'не опубликовано' or failed, skip so we can notify when it truly publishes
                    continue

                human_date = format_schedule_notification_date(date_str)
                header = (
                    f"{te(PE_BELL)} <b>Опубликовано новое расписание на {human_date}!</b>\n\n"
                )
                body = format_schedule_message(sched, g_name, date_str)
                full_text = header + body
                web_url = sched.get("url")
                kb = get_schedule_nav_inline_keyboard(g_id, date_str, web_url)

                for u in pending_users:
                    u_id = u["user_id"]
                    try:
                        await bot.send_message(
                            chat_id=u_id,
                            text=full_text,
                            reply_markup=kb,
                            disable_web_page_preview=True
                        )
                        logger.info(f"Уведомление о расписании отправлено пользователю {u_id} (группа {g_name}, дата {date_str})")
                    except TelegramBadRequest as e:
                        try:
                            clean_text = strip_tg_emoji(full_text)
                            await bot.send_message(
                                chat_id=u_id,
                                text=clean_text,
                                reply_markup=kb,
                                disable_web_page_preview=True
                            )
                            logger.info(f"Уведомление о расписании отправлено пользователю {u_id} (без тегов эмодзи)")
                        except Exception as e2:
                            logger.warning(f"Не удалось отправить уведомление {u_id}: {e2}")
                    except TelegramForbiddenError as e:
                        logger.warning(f"Пользователь {u_id} заблокировал бота: {e}")
                    except Exception as e:
                        logger.error(f"Неожиданная ошибка при отправке пользователю {u_id}: {e}")
                    finally:
                        await mark_user_notified(u_id, "group", g_id, date_str)

        # 2. Process teacher schedules
        for t_id, teacher_users in teachers_map.items():
            t_name = teacher_users[0].get("teacher_name") or "Преподаватель"

            for date_str in available_dates:
                pending_users = []
                for u in teacher_users:
                    notified = await is_user_notified(u["user_id"], "teacher", t_id, date_str)
                    if not notified:
                        pending_users.append(u)

                if not pending_users:
                    continue

                sched = await get_teacher_schedule(t_id, date_str, force_refresh=True)
                if not is_schedule_published(sched):
                    continue

                human_date = format_schedule_notification_date(date_str)
                header = (
                    f"{te(PE_BELL)} <b>Опубликовано новое расписание на {human_date}!</b>\n\n"
                )
                body = format_teacher_schedule_message(sched, t_name, date_str)
                full_text = header + body
                web_url = sched.get("url")
                kb = get_teacher_schedule_nav_inline_keyboard(t_id, date_str, web_url)

                for u in pending_users:
                    u_id = u["user_id"]
                    try:
                        await bot.send_message(
                            chat_id=u_id,
                            text=full_text,
                            reply_markup=kb,
                            disable_web_page_preview=True
                        )
                        logger.info(f"Уведомление отправлено пользователю {u_id} (преподаватель {t_name}, дата {date_str})")
                    except TelegramBadRequest as e:
                        try:
                            clean_text = strip_tg_emoji(full_text)
                            await bot.send_message(
                                chat_id=u_id,
                                text=clean_text,
                                reply_markup=kb,
                                disable_web_page_preview=True
                            )
                            logger.info(f"Уведомление отправлено пользователю {u_id} (без тегов эмодзи)")
                        except Exception as e2:
                            logger.warning(f"Не удалось отправить уведомление {u_id}: {e2}")
                    except TelegramForbiddenError as e:
                        logger.warning(f"Пользователь {u_id} заблокировал бота: {e}")
                    except Exception as e:
                        logger.error(f"Неожиданная ошибка при отправке {u_id}: {e}")
                    finally:
                        await mark_user_notified(u_id, "teacher", t_id, date_str)

    except Exception as e:
        logger.error(f"Ошибка в цикле проверки расписания: {e}", exc_info=True)


async def schedule_notification_worker(bot: Bot):
    """
    Background worker loop checking for schedule updates every 3 minutes.
    """
    logger.info("Запущен фоновый сервис уведомлений о расписании.")
    while True:
        try:
            await check_and_notify_users(bot)
        except asyncio.CancelledError:
            logger.info("Фоновый сервис уведомлений остановлен.")
            break
        except Exception as e:
            logger.error(f"Сбой в фоновом сервисе уведомлений: {e}")

        try:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            logger.info("Фоновый сервис уведомлений остановлен во время ожидания.")
            break
