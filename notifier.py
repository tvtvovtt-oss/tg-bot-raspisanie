import asyncio
import hashlib
import json
import logging
from typing import Dict, List, Any
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

from database import (
    get_users_for_notifications,
    is_user_notified,
    mark_user_notified,
    disable_user_notifications,
    is_maintenance_mode
)
from parser import (
    get_available_dates,
    get_group_schedule,
    get_teacher_schedule,
    format_schedule_message,
    format_teacher_schedule_message,
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


def schedule_fingerprint(schedule: Dict[str, Any]) -> str:
    """Hashes only user-visible schedule data so real changes trigger a new alert."""
    payload = {
        "lessons": schedule.get("lessons", []),
        "practices": schedule.get("practices", []),
        "consultations": schedule.get("consultations", []),
        "alerts": schedule.get("alerts", []),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


async def _send_notification(bot: Bot, user_id: int, text: str, reply_markup) -> str:
    """Returns sent, blocked, or failed; transient failures remain retryable."""
    current_text = text
    fallback_used = False
    for attempt in range(3):
        try:
            await bot.send_message(
                chat_id=user_id,
                text=current_text,
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
            return "sent"
        except TelegramRetryAfter as exc:
            if attempt == 2:
                logger.warning("Telegram rate limit persisted for user %s", user_id)
                return "failed"
            await asyncio.sleep(max(float(exc.retry_after), 0.1) + 0.1)
        except TelegramForbiddenError:
            return "blocked"
        except TelegramBadRequest as exc:
            if not fallback_used:
                clean_text = strip_tg_emoji(current_text)
                if clean_text != current_text:
                    current_text = clean_text
                    fallback_used = True
                    continue
            logger.warning("Не удалось отправить уведомление %s: %s", user_id, exc)
            return "failed"
        except Exception as exc:
            logger.warning("Не удалось отправить уведомление %s: %s", user_id, exc)
            return "failed"
    return "failed"


async def check_and_notify_users(bot: Bot):
    """
    Checks for newly published schedules and notifies subscribed users.
    Only checks official on-site published dates >= today.
    """
    global _IS_FIRST_RUN

    try:
        from config import ENABLE_NOTIFICATIONS
        if not ENABLE_NOTIFICATIONS:
            return

        if await is_maintenance_mode():
            logger.info("Технический перерыв включен: отправка плановых уведомлений приостановлена.")
            return

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

        # Group users by target to minimize requests to almetpt.ru.
        groups_map: Dict[str, List[Dict[str, Any]]] = {}
        teachers_map: Dict[str, List[Dict[str, Any]]] = {}
        for u in users:
            if u.get("group_id"):
                groups_map.setdefault(str(u["group_id"]), []).append(u)
            if u.get("teacher_id"):
                teachers_map.setdefault(str(u["teacher_id"]), []).append(u)

        # On first startup, pre-mark existing current dates so we don't spam notifications
        # for schedules that were already available when bot launched
        if _IS_FIRST_RUN:
            for group_id, group_users in groups_map.items():
                for date_str in available_dates:
                    schedule = await get_group_schedule(group_id, date_str, force_refresh=True)
                    if is_schedule_published(schedule):
                        fingerprint = schedule_fingerprint(schedule)
                        for user in group_users:
                            await mark_user_notified(
                                user["user_id"], "group", group_id, date_str, fingerprint
                            )
            for teacher_id, teacher_users in teachers_map.items():
                for date_str in available_dates:
                    schedule = await get_teacher_schedule(teacher_id, date_str, force_refresh=True)
                    if is_schedule_published(schedule):
                        fingerprint = schedule_fingerprint(schedule)
                        for user in teacher_users:
                            await mark_user_notified(
                                user["user_id"], "teacher", teacher_id, date_str, fingerprint
                            )
            _IS_FIRST_RUN = False
            logger.info(f"Notifier инициализирован: сохранено {len(users)} пользователей и {len(available_dates)} дат.")
            return

        # 1. Process group schedules
        for g_id, group_users in groups_map.items():
            g_name = group_users[0].get("group_name") or f"Группа {g_id}"
            
            for date_str in available_dates:
                # Fetch once per group/date, then compare its fingerprint for all users.
                sched = await get_group_schedule(g_id, date_str, force_refresh=True)
                if not is_schedule_published(sched):
                    continue
                fingerprint = schedule_fingerprint(sched)

                # Find users who have not received notification for this group and date
                pending_users = []
                for u in group_users:
                    notified = await is_user_notified(
                        u["user_id"], "group", g_id, date_str, fingerprint
                    )
                    if not notified:
                        pending_users.append(u)

                if not pending_users:
                    continue

                human_date = format_schedule_notification_date(date_str)
                header = (
                    f"{te(PE_BELL)} <b>Опубликовано или обновлено расписание на {human_date}!</b>\n\n"
                )
                body = format_schedule_message(sched, g_name, date_str)
                full_text = header + body
                web_url = sched.get("url")
                kb = get_schedule_nav_inline_keyboard(g_id, date_str, web_url)

                for u in pending_users:
                    u_id = u["user_id"]
                    outcome = await _send_notification(bot, u_id, full_text, kb)
                    if outcome == "sent":
                        logger.info(f"Уведомление о расписании отправлено пользователю {u_id} (группа {g_name}, дата {date_str})")
                        await mark_user_notified(u_id, "group", g_id, date_str, fingerprint)
                    elif outcome == "blocked":
                        logger.info("Пользователь %s заблокировал бота; уведомления отключены.", u_id)
                        await disable_user_notifications(u_id)

        # 2. Process teacher schedules
        for t_id, teacher_users in teachers_map.items():
            t_name = teacher_users[0].get("teacher_name") or "Преподаватель"

            for date_str in available_dates:
                sched = await get_teacher_schedule(t_id, date_str, force_refresh=True)
                if not is_schedule_published(sched):
                    continue
                fingerprint = schedule_fingerprint(sched)

                pending_users = []
                for u in teacher_users:
                    notified = await is_user_notified(
                        u["user_id"], "teacher", t_id, date_str, fingerprint
                    )
                    if not notified:
                        pending_users.append(u)

                if not pending_users:
                    continue

                human_date = format_schedule_notification_date(date_str)
                header = (
                    f"{te(PE_BELL)} <b>Опубликовано или обновлено расписание на {human_date}!</b>\n\n"
                )
                body = format_teacher_schedule_message(sched, t_name, date_str)
                full_text = header + body
                web_url = sched.get("url")
                kb = get_teacher_schedule_nav_inline_keyboard(t_id, date_str, web_url)

                for u in pending_users:
                    u_id = u["user_id"]
                    outcome = await _send_notification(bot, u_id, full_text, kb)
                    if outcome == "sent":
                        logger.info(f"Уведомление отправлено пользователю {u_id} (преподаватель {t_name}, дата {date_str})")
                        await mark_user_notified(u_id, "teacher", t_id, date_str, fingerprint)
                    elif outcome == "blocked":
                        logger.info("Пользователь %s заблокировал бота; уведомления отключены.", u_id)
                        await disable_user_notifications(u_id)

    except Exception as e:
        logger.error(f"Ошибка в цикле проверки расписания: {e}", exc_info=True)


async def schedule_notification_worker(bot: Bot):
    """
    Background worker loop checking for schedule updates every 3 minutes.
    """
    from config import ENABLE_NOTIFICATIONS
    if not ENABLE_NOTIFICATIONS:
        logger.info("Фоновый сервис уведомлений о расписании отключен (ENABLE_NOTIFICATIONS=false).")
        return

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
