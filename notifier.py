import asyncio
import hashlib
import json
import logging
from typing import Dict, List, Any, Optional

from aiogram import Bot

from database import (
    get_users_for_notifications,
    get_notified_fingerprints,
    mark_user_notified,
    clear_baseline_pending,
    disable_user_notifications,
    mark_user_blocked,
    is_maintenance_mode,
    is_restore_in_progress
)
from delivery import send_with_retry, BLOCKED, SENT
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
from premium_emoji import te, PE_BELL
from timeutil import today_local_str

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
    _, outcome = await send_with_retry(bot, user_id, text, reply_markup=reply_markup)
    return outcome


def _group_users_by_target(users: List[Dict[str, Any]]):
    """Группирует пользователей по группе/преподавателю, чтобы минимум обращаться к almetpt.ru."""
    groups_map: Dict[str, List[Dict[str, Any]]] = {}
    teachers_map: Dict[str, List[Dict[str, Any]]] = {}
    for u in users:
        if u.get("group_id"):
            groups_map.setdefault(str(u["group_id"]), []).append(u)
        if u.get("teacher_id"):
            teachers_map.setdefault(str(u["teacher_id"]), []).append(u)
    return groups_map, teachers_map


async def _mark_existing_as_known(users: List[Dict[str, Any]], available_dates: List[str]) -> bool:
    """
    Тихо отмечает уже опубликованное расписание как «известное», ничего не отправляя.
    Используется при первом запуске и для пользователей, которые только что выбрали
    группу/преподавателя или включили уведомления, — иначе они получили бы пачку старых оповещений.
    Возвращает False, если часть расписаний не удалось получить (отметку стоит повторить позже).
    """
    groups_map, teachers_map = _group_users_by_target(users)
    complete = True

    for group_id, group_users in groups_map.items():
        for date_str in available_dates:
            schedule = await get_group_schedule(group_id, date_str, force_refresh=True)
            if not schedule.get("success", True):
                complete = False
                continue
            if is_schedule_published(schedule):
                fingerprint = schedule_fingerprint(schedule)
                for user in group_users:
                    await mark_user_notified(user["user_id"], "group", group_id, date_str, fingerprint)

    for teacher_id, teacher_users in teachers_map.items():
        for date_str in available_dates:
            schedule = await get_teacher_schedule(teacher_id, date_str, force_refresh=True)
            if not schedule.get("success", True):
                complete = False
                continue
            if is_schedule_published(schedule):
                fingerprint = schedule_fingerprint(schedule)
                for user in teacher_users:
                    await mark_user_notified(user["user_id"], "teacher", teacher_id, date_str, fingerprint)

    return complete


def _pending_users(
    target_users: List[Dict[str, Any]],
    notified: Dict[int, Optional[str]],
    fingerprint: str
) -> List[Dict[str, Any]]:
    """Пользователи, которым ещё не отправлена именно эта версия расписания."""
    return [
        u for u in target_users
        if u["user_id"] not in notified or notified[u["user_id"]] != fingerprint
    ]


async def _notify_pending(
    bot: Bot,
    pending_users: List[Dict[str, Any]],
    target_type: str,
    target_id: str,
    target_label: str,
    date_str: str,
    fingerprint: str,
    full_text: str,
    kb
) -> None:
    for u in pending_users:
        u_id = u["user_id"]
        outcome = await _send_notification(bot, u_id, full_text, kb)
        if outcome == SENT:
            logger.info(f"Уведомление отправлено пользователю {u_id} ({target_label}, дата {date_str})")
            await mark_user_notified(u_id, target_type, target_id, date_str, fingerprint)
        elif outcome == BLOCKED:
            logger.info("Пользователь %s заблокировал бота; уведомления отключены.", u_id)
            await disable_user_notifications(u_id)
            await mark_user_blocked(u_id)


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

        if is_restore_in_progress():
            logger.info("Идёт восстановление базы данных: проверка уведомлений пропущена.")
            return

        dates_info = await get_available_dates(force_refresh=True)
        today_str = dates_info.get("today") or today_local_str()
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
            complete = await _mark_existing_as_known(users, available_dates)
            if complete:
                await clear_baseline_pending([u["user_id"] for u in users if u.get("baseline_pending")])
            _IS_FIRST_RUN = False
            logger.info(f"Notifier инициализирован: сохранено {len(users)} пользователей и {len(available_dates)} дат.")
            return

        # Новые подписчики: уже опубликованное расписание им не отправляем, только запоминаем.
        fresh_users = [u for u in users if u.get("baseline_pending")]
        if fresh_users:
            complete = await _mark_existing_as_known(fresh_users, available_dates)
            if complete:
                await clear_baseline_pending([u["user_id"] for u in fresh_users])
            fresh_ids = {u["user_id"] for u in fresh_users}
            users = [u for u in users if u["user_id"] not in fresh_ids]
            if not users:
                return

        groups_map, teachers_map = _group_users_by_target(users)

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
                notified = await get_notified_fingerprints("group", g_id, date_str)
                pending_users = _pending_users(group_users, notified, fingerprint)
                if not pending_users:
                    continue

                human_date = format_schedule_notification_date(date_str)
                header = (
                    f"{te(PE_BELL)} <b>Опубликовано или обновлено расписание на {human_date}!</b>\n\n"
                )
                body = format_schedule_message(sched, g_name, date_str)
                full_text = header + body
                kb = get_schedule_nav_inline_keyboard(g_id, date_str, sched.get("url"))

                await _notify_pending(
                    bot, pending_users, "group", g_id, f"группа {g_name}", date_str, fingerprint, full_text, kb
                )

        # 2. Process teacher schedules
        for t_id, teacher_users in teachers_map.items():
            t_name = teacher_users[0].get("teacher_name") or "Преподаватель"

            for date_str in available_dates:
                sched = await get_teacher_schedule(t_id, date_str, force_refresh=True)
                if not is_schedule_published(sched):
                    continue
                fingerprint = schedule_fingerprint(sched)

                notified = await get_notified_fingerprints("teacher", t_id, date_str)
                pending_users = _pending_users(teacher_users, notified, fingerprint)
                if not pending_users:
                    continue

                human_date = format_schedule_notification_date(date_str)
                header = (
                    f"{te(PE_BELL)} <b>Опубликовано или обновлено расписание на {human_date}!</b>\n\n"
                )
                body = format_teacher_schedule_message(sched, t_name, date_str)
                full_text = header + body
                kb = get_teacher_schedule_nav_inline_keyboard(t_id, date_str, sched.get("url"))

                await _notify_pending(
                    bot, pending_users, "teacher", t_id, f"преподаватель {t_name}", date_str, fingerprint, full_text, kb
                )

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
