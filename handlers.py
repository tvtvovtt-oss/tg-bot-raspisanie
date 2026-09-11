import asyncio
from datetime import datetime, timedelta
import html
import re
from typing import Optional, Dict, Any, Tuple

from aiogram import Router, F
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import (
    get_user, ensure_user, set_user_group, set_user_teacher, toggle_user_notifications,
    is_admin, is_stat_admin, is_maintenance_mode, set_maintenance_mode, get_bot_stats, get_all_user_ids,
    create_broadcast, get_broadcast, get_broadcasts, get_broadcasts_count, cancel_broadcast, get_broadcasts_summary
)
from broadcast_service import execute_broadcast
from parser import (
    get_available_dates,
    get_groups,
    get_groups_by_course,
    get_zaochn_groups,
    search_groups,
    get_staffs,
    search_teachers,
    get_teacher_letters,
    get_teachers_by_letter,
    get_group_schedule,
    get_teacher_schedule,
    format_schedule_message,
    format_teacher_schedule_message,
    get_calls_text,
    get_tomorrow_date,
    resolve_weekday_to_date,
    parse_weekday_from_text
)
from keyboards import (
    get_main_keyboard,
    get_main_menu_inline,
    get_home_button_row,
    get_dates_inline_keyboard,
    get_groups_search_inline_keyboard,
    get_course_selection_keyboard,
    get_zaochn_selection_keyboard,
    get_teachers_letters_keyboard,
    get_teachers_search_inline_keyboard,
    get_schedule_nav_inline_keyboard,
    get_teacher_schedule_nav_inline_keyboard,
    get_calls_keyboard,
    get_my_group_keyboard,
    get_admin_keyboard,
    get_admin_back_keyboard,
    get_broadcast_setup_keyboard,
    get_broadcast_time_selection_keyboard,
    get_broadcast_custom_time_back_keyboard,
    get_stat_admin_menu_keyboard,
    get_stat_admin_bot_stats_keyboard,
    get_broadcast_list_keyboard,
    get_broadcast_detail_keyboard,
    DateCallback,
    GroupCallback,
    TeacherCallback,
    MenuCallback,
    AdminCallback,
    BroadcastCallback,
    StatAdminCallback
)
import logging
logger = logging.getLogger(__name__)

from premium_emoji import (
    te, strip_tg_emoji, PE_BOT, PE_CALENDAR, PE_BELL, PE_SEARCH, PE_PEOPLE, PE_INFO, PE_CHECK,
    PE_CLOCK, PE_HOUSE, PE_PERSON_CHECK, PE_TIME_PASSED, PE_STAR, PE_WARNING,
    PE_WRITE, PE_LINK, PE_REPEAT, PE_ARROW_LEFT, PE_CROSS,
    PE_SETTINGS, PE_LOCK_CLOSED, PE_LOCK_OPEN, PE_CHART_STATS, PE_CHART_GROW, PE_MEGAPHONE, PE_BAN,
    PE_PAPERCLIP, PE_SEND_UP
)

router = Router()


class BotStates(StatesGroup):
    waiting_for_group_search = State()
    waiting_for_teacher_search = State()
    waiting_for_broadcast_text = State()
    waiting_for_broadcast_custom_time = State()
    waiting_for_broadcast_daily_time = State()


async def safe_query_answer(query: CallbackQuery, text: Optional[str] = None, show_alert: bool = False):
    """Безопасный ответ на callback-запрос без падений при повторном вызове."""
    try:
        await query.answer(text=text, show_alert=show_alert)
    except TelegramBadRequest:
        pass


async def safe_edit_text(message: Message, text: str, reply_markup=None) -> bool:
    """Безопасное редактирование сообщения с авто-фолбэком при ошибках разметки или эмодзи."""
    try:
        await message.edit_text(text, reply_markup=reply_markup)
        return True
    except TelegramBadRequest as e:
        err_msg = str(e).lower()
        if "message is not modified" in err_msg:
            return False
        
        logger.warning(f"edit_text failed ({e}), retrying without <tg-emoji> tags...")
        clean_text = strip_tg_emoji(text)
        try:
            await message.edit_text(clean_text, reply_markup=reply_markup)
            return True
        except TelegramBadRequest as e2:
            if "message is not modified" in str(e2).lower():
                return False
            logger.warning(f"edit_text retry failed ({e2}), falling back to answer...")
            try:
                await message.answer(clean_text, reply_markup=reply_markup)
                return True
            except Exception as e3:
                logger.error(f"Failed to safe_edit_text completely: {e3}")
                return False


async def safe_answer(message: Message, text: str, reply_markup=None, **kwargs) -> Optional[Message]:
    """Безопасная отправка сообщения с авто-фолбэком без <tg-emoji> при ошибках Telegram."""
    try:
        return await message.answer(text, reply_markup=reply_markup, **kwargs)
    except TelegramBadRequest as e:
        logger.warning(f"answer failed ({e}), retrying without <tg-emoji> tags...")
        clean_text = strip_tg_emoji(text)
        try:
            return await message.answer(clean_text, reply_markup=reply_markup, **kwargs)
        except Exception as e2:
            logger.error(f"Failed safe_answer completely: {e2}")
            return None


def build_welcome_text(user, first_name: str) -> str:
    base = (
        f"{te(PE_BOT)} <b>Привет, {html.escape(first_name)}!</b>\n\n"
        "Здесь актуальное расписание пар АПТ.\n\n"
    )
    if user and user.get("group_name"):
        base += (
            f"{te(PE_CHECK)} Твоя группа: <b>{html.escape(user['group_name'])}</b>\n\n"
            "Выбирай действие кнопками ниже или отправь номер другой группы в чат:"
        )
    else:
        base += (
            f"{te(PE_INFO)} <b>Группа ещё не выбрана.</b>\n"
            "Просто напиши в чат номер или первые буквы группы (например: <code>253</code> или <code>ИС</code>)."
        )
    return base


def get_menu_text(user) -> str:
    if user and user.get("group_name"):
        return (
            f"{te(PE_HOUSE)} <b>Главное меню</b> — {html.escape(user['group_name'])}:\n"
            "Выбирай действие кнопками:"
        )
    return (
        f"{te(PE_HOUSE)} <b>Главное меню</b>:\n"
        "Выбирай действие кнопками или напиши номер группы:"
    )


def render_profile_text(user: Optional[dict]) -> str:
    """Формирует понятный текст профиля пользователя с группой и преподавателем."""
    notifications_on = True if (not user or user.get("notifications") is None or user.get("notifications") == 1) else False
    notif_status_text = "Включены" if notifications_on else "Отключены"
    notif_icon = te(PE_BELL) if notifications_on else te(PE_CROSS)

    lines = [f"{te(PE_PEOPLE)} <b>Твой профиль:</b>\n"]
    has_target = False
    if user and user.get("group_name"):
        lines.append(f"{te(PE_CHECK)} Сохранённая группа: <b>{html.escape(user['group_name'])}</b>")
        has_target = True
    if user and user.get("teacher_name"):
        lines.append(f"{te(PE_PERSON_CHECK)} Сохранённый преподаватель: <b>{html.escape(user['teacher_name'])}</b>")
        has_target = True
    
    if not has_target:
        lines.append(f"{te(PE_INFO)} <i>Группа пока не выбрана!</i>")

    lines.append(f"{notif_icon} Уведомления о расписании: <b>{notif_status_text}</b>\n")
    lines.append("Чтобы сменить группу, нажми <b>«Сменить группу»</b> или просто напиши её номер в чат.")
    return "\n".join(lines)


# ---------- Команды ----------

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Единственная нужная команда: дальше всё управление только кнопками."""
    await state.clear()
    await ensure_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name
    )
    user = await get_user(message.from_user.id)
    first_name = message.from_user.first_name or "студент"
    is_adm = await is_admin(message.from_user.id)
    
    await safe_answer(
        message,
        build_welcome_text(user, first_name),
        reply_markup=get_main_keyboard(is_admin_user=is_adm)
    )
    await safe_answer(message, get_menu_text(user), reply_markup=get_main_menu_inline(is_admin_user=is_adm))


@router.message(Command("help"))
async def cmd_help(message: Message):
    is_adm = await is_admin(message.from_user.id)
    text = (
        f"{te(PE_INFO)} <b>Как пользоваться ботом:</b>\n\n"
        f"• {te(PE_CALENDAR)} <b>На сегодня / На завтра</b> — расписание твоей группы\n"
        f"• {te(PE_CLOCK)} <b>Выбрать дату</b> — расписание на любой день\n"
        f"• {te(PE_PEOPLE)} <b>Моя группа</b> — текущая группа, смена группы и уведомления\n\n"
        f"{te(PE_SEARCH)} <b>Быстрый поиск группы:</b> просто отправь в чат её номер или первые буквы (например: <code>ИС</code>, <code>253</code> или <code>АВ-261</code>)!\n\n"
        f"{te(PE_STAR)} <i>Подсказка: ты можешь нажать /start один раз и дальше переключаться кнопками меню!</i>"
    )
    await safe_answer(message, text, reply_markup=get_main_keyboard(is_admin_user=is_adm))


# ---------- Обработчики текстовых кнопок Reply-клавиатуры ----------

@router.message(StateFilter("*"), F.text.in_({"Панель администратора", "Админ-панель", "Админка", "⚙️ Панель администратора"}))
async def handle_reply_admin_button(message: Message, state: FSMContext):
    """Открытие админ-панели по нажатию reply-кнопки."""
    await cmd_admin(message, state)


@router.message(StateFilter("*"), F.text.in_({"Статистика", "Статистика бота", "Статистика и рассылки", "📊 Статистика", "Аналитика"}))
async def handle_reply_stats_button(message: Message, state: FSMContext):
    """Открытие панели статистики по нажатию reply-кнопки."""
    await cmd_statadmin(message, state)


@router.message(F.text.in_({"Звонки", "🔔 Звонки"}))
@router.message(Command("calls"))
async def cmd_calls(message: Message):
    await safe_answer(message, get_calls_text(), reply_markup=get_calls_keyboard())


@router.message(F.text.in_({"Моя группа", "👥 Моя группа", "Профиль", "профиль"}))
@router.message(Command("mygroup"))
async def cmd_my_group(message: Message, state: FSMContext):
    await state.clear()
    user = await get_user(message.from_user.id)
    notifications_on = True if (not user or user.get("notifications") is None or user.get("notifications") == 1) else False
    text = render_profile_text(user)
    await safe_answer(message, text, reply_markup=get_my_group_keyboard(notifications_on))


@router.message(F.text.in_({"Найти группу", "🔍 Найти группу"}))
@router.message(Command("search"))
async def cmd_search_group(message: Message, state: FSMContext):
    await state.set_state(BotStates.waiting_for_group_search)
    await safe_answer(
        message,
        f"{te(PE_SEARCH)} <b>Поиск группы:</b>\n"
        "Напиши в чат номер или первые буквы своей группы (например: <code>253</code>, <code>ИС</code> или <code>АВ-261</code>):"
    )


@router.message(F.text.in_({"Преподаватели", "👨‍🏫 Преподаватели"}))
@router.message(Command("teachers"))
async def cmd_search_teacher(message: Message, state: FSMContext):
    await state.set_state(BotStates.waiting_for_teacher_search)
    letters = await get_teacher_letters()
    if not letters:
        await safe_answer(
            message,
            f"{te(PE_WARNING, '!')} Не удалось получить список преподавателей с сайта. Попробуй позже.",
            reply_markup=get_main_keyboard()
        )
        return

    await safe_answer(
        message,
        f"{te(PE_PERSON_CHECK)} <b>Выбери первую букву фамилии преподавателя:</b>\n"
        "<i>(или введи фамилию текстом в чат, например: <code>Агеева</code>)</i>",
        reply_markup=get_teachers_letters_keyboard(letters)
    )


@router.message(F.text.in_({"На сегодня", "📅 На сегодня", "Расписание на сегодня", "🗓 На сегодня", "📆 На сегодня", "Сегодня", "сегодня"}))
@router.message(Command("today"))
async def cmd_today(message: Message):
    user = await get_user(message.from_user.id)
    if not user or not user.get("group_id"):
        await safe_answer(
            message,
            f"{te(PE_WARNING, '!')} <b>Сначала укажи свою группу!</b>\n"
            "Напиши в чат её номер или первые буквы (например: <code>253</code> или <code>ИС</code>):"
        )
        return

    dates_info = await get_available_dates()
    today_str = dates_info.get("today") or datetime.now().strftime("%Y-%m-%d")

    wait_msg = await safe_answer(message, f"{te(PE_CALENDAR)} <i>Загружаю расписание с almetpt.ru...</i>")
    sched = await get_group_schedule(user["group_id"], today_str)
    
    text = format_schedule_message(sched, user["group_name"], today_str, "Сегодня")
    web_url = sched.get("url")
    kb = get_schedule_nav_inline_keyboard(user["group_id"], today_str, web_url)
    
    if wait_msg:
        edited = await safe_edit_text(wait_msg, text, reply_markup=kb)
        if not edited:
            await safe_answer(message, text, reply_markup=kb)
    else:
        await safe_answer(message, text, reply_markup=kb)


@router.message(F.text.in_({"На завтра", "📆 На завтра", "Расписание на завтра", "📅 На завтра", "Завтра", "завтра"}))
@router.message(Command("tomorrow"))
async def cmd_tomorrow(message: Message):
    user = await get_user(message.from_user.id)
    if not user or not user.get("group_id"):
        await safe_answer(
            message,
            f"{te(PE_WARNING, '!')} <b>Сначала укажи свою группу!</b>\n"
            "Напиши в чат её номер или первые буквы (например: <code>253</code> или <code>ИС</code>):"
        )
        return

    dates_info = await get_available_dates()
    tomorrow_str = get_tomorrow_date(dates_info)

    wait_msg = await safe_answer(message, f"{te(PE_TIME_PASSED)} <i>Загружаю расписание на завтра...</i>")
    sched = await get_group_schedule(user["group_id"], tomorrow_str)
    
    text = format_schedule_message(sched, user["group_name"], tomorrow_str, "Завтра")
    web_url = sched.get("url")
    kb = get_schedule_nav_inline_keyboard(user["group_id"], tomorrow_str, web_url)
    
    if wait_msg:
        edited = await safe_edit_text(wait_msg, text, reply_markup=kb)
        if not edited:
            await safe_answer(message, text, reply_markup=kb)
    else:
        await safe_answer(message, text, reply_markup=kb)


@router.message(F.text.in_({"Выбрать дату", "🗓 Выбрать дату", "📅 Выбрать дату", "Даты", "даты", "Выбор даты"}))
@router.message(Command("dates"))
async def cmd_choose_date(message: Message):
    user = await get_user(message.from_user.id)
    group_id = user["group_id"] if user and user.get("group_id") else ""
    
    dates_info = await get_available_dates()
    dates_list = dates_info.get("dates", [])
    today_str = dates_info.get("today")
    
    if not dates_list:
        await safe_answer(message, f"{te(PE_WARNING, '!')} Не удалось получить список дат с сайта.")
        return

    kb = get_dates_inline_keyboard(dates_list, target_type="group", target_id=group_id, today_str=today_str)
    await safe_answer(message, f"{te(PE_CLOCK)} <b>Выбери дату для просмотра расписания:</b>", reply_markup=kb)


# ---------- Интерактивное Inline-меню (MenuCallback) ----------

@router.callback_query(MenuCallback.filter())
async def cb_menu_handler(query: CallbackQuery, callback_data: MenuCallback):
    """Центральный обработчик всех inline-кнопок навигации по боту."""
    await safe_query_answer(query)
    action = callback_data.action
    user = await get_user(query.from_user.id)

    if action == "home":
        # Возврат в главное меню
        is_adm = await is_admin(query.from_user.id)
        text = get_menu_text(user)
        kb = get_main_menu_inline(is_admin_user=is_adm)
        await safe_edit_text(query.message, text, reply_markup=kb)

    elif action == "admin":
        if not await is_admin(query.from_user.id):
            await safe_query_answer(query, "Доступ запрещен.", show_alert=True)
            return
        panel_text = await render_admin_panel_text()
        is_maint = await is_maintenance_mode()
        kb = get_admin_keyboard(is_maint)
        await safe_edit_text(query.message, panel_text, reply_markup=kb)

    elif action == "today":
        if not user or not user.get("group_id"):
            await safe_edit_text(
                query.message,
                f"{te(PE_WARNING, '!')} <b>Сначала укажи группу!</b>\n"
                "Напиши в чат её номер или первые буквы (например: <code>253</code> или <code>ИС</code>):",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[get_home_button_row()])
            )
            return
        dates_info = await get_available_dates()
        today_str = dates_info.get("today") or datetime.now().strftime("%Y-%m-%d")
        sched = await get_group_schedule(user["group_id"], today_str)
        text = format_schedule_message(sched, user["group_name"], today_str, "Сегодня")
        kb = get_schedule_nav_inline_keyboard(user["group_id"], today_str, sched.get("url"))
        edited = await safe_edit_text(query.message, text, reply_markup=kb)
        if not edited:
            await safe_query_answer(query, "Расписание на сегодня актуально!")

    elif action == "tomorrow":
        if not user or not user.get("group_id"):
            await safe_edit_text(
                query.message,
                f"{te(PE_WARNING, '!')} <b>Сначала укажи группу!</b>\n"
                "Напиши в чат её номер или первые буквы (например: <code>253</code> или <code>ИС</code>):",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[get_home_button_row()])
            )
            return
        dates_info = await get_available_dates()
        tomorrow_str = get_tomorrow_date(dates_info)

        sched = await get_group_schedule(user["group_id"], tomorrow_str)
        text = format_schedule_message(sched, user["group_name"], tomorrow_str, "Завтра")
        kb = get_schedule_nav_inline_keyboard(user["group_id"], tomorrow_str, sched.get("url"))
        edited = await safe_edit_text(query.message, text, reply_markup=kb)
        if not edited:
            await safe_query_answer(query, "Расписание на завтра актуально!")

    elif action == "dates":
        group_id = user["group_id"] if user and user.get("group_id") else ""
        dates_info = await get_available_dates()
        dates_list = dates_info.get("dates", [])
        today_str = dates_info.get("today")
        if not dates_list:
            await safe_query_answer(query, "Не удалось загрузить даты.", show_alert=True)
            return
        kb = get_dates_inline_keyboard(dates_list, target_type="group", target_id=group_id, today_str=today_str)
        await safe_edit_text(query.message, f"{te(PE_CLOCK)} <b>Выбери дату кнопками:</b>", reply_markup=kb)

    elif action == "calls":
        await safe_edit_text(query.message, get_calls_text(), reply_markup=get_calls_keyboard())

    elif action == "mygroup":
        notifications_on = True if (not user or user.get("notifications") is None or user.get("notifications") == 1) else False
        text = render_profile_text(user)
        await safe_edit_text(query.message, text, reply_markup=get_my_group_keyboard(notifications_on))

    elif action == "toggle_notify":
        new_state = await toggle_user_notifications(query.from_user.id)
        user = await get_user(query.from_user.id)
        notif_status_text = "включены" if new_state else "отключены"
        await safe_query_answer(query, f"Уведомления {notif_status_text}!")
        text = render_profile_text(user)
        await safe_edit_text(query.message, text, reply_markup=get_my_group_keyboard(new_state))

    elif action in ("change_group", "groups"):
        await safe_edit_text(
            query.message,
            f"{te(PE_SEARCH)} <b>Смена группы:</b>\n\n"
            "Выбери свой курс кнопками ниже или просто напиши номер/буквы группы в чат (например: <code>253</code> или <code>ИС</code>):",
            reply_markup=get_course_selection_keyboard()
        )

    elif action == "teachers":
        letters = await get_teacher_letters()
        if not letters:
            await safe_query_answer(query, "Список преподавателей временно недоступен.", show_alert=True)
            return
        await safe_edit_text(
            query.message,
            f"{te(PE_PERSON_CHECK)} <b>Выбери первую букву фамилии преподавателя:</b>",
            reply_markup=get_teachers_letters_keyboard(letters)
        )


# ---------- Обработчики выбора преподавателей (TeacherCallback) ----------

@router.callback_query(TeacherCallback.filter())
async def cb_teacher_handler(query: CallbackQuery, callback_data: TeacherCallback):
    """Оживление кнопки Преподаватели: алфавит букв + выбор преподавателя."""
    await safe_query_answer(query)
    action = callback_data.action

    if action == "letter":
        letter = callback_data.teacher_id
        teachers = await get_teachers_by_letter(letter)
        if not teachers:
            await safe_query_answer(query, f"Преподаватели на букву «{letter}» не найдены.", show_alert=True)
            return

        kb = get_teachers_search_inline_keyboard(teachers, with_back=True)
        await safe_edit_text(
            query.message,
            f"{te(PE_PERSON_CHECK)} <b>Преподаватели на букву «{letter}» ({len(teachers)}):</b>\nВыбери из списка:",
            reply_markup=kb
        )

    elif action == "select":
        t_id = callback_data.teacher_id
        all_staff = await get_staffs()
        t_info = all_staff.get(t_id, {})
        t_name = t_info.get("short_fio") or t_info.get("fio", "Преподаватель")
        
        await set_user_teacher(query.from_user.id, t_id, t_name)
        
        dates_info = await get_available_dates()
        today_str = dates_info.get("today") or datetime.now().strftime("%Y-%m-%d")

        await safe_edit_text(
            query.message,
            f"{te(PE_CLOCK)} <i>Загружаю расписание {html.escape(t_name)}...</i>"
        )

        sched = await get_teacher_schedule(t_id, today_str)
        text = format_teacher_schedule_message(sched, t_name, today_str)
        web_url = sched.get("url")
        kb = get_teacher_schedule_nav_inline_keyboard(t_id, today_str, web_url)
        
        await safe_edit_text(query.message, text, reply_markup=kb)


# ---------- Обработчики выбора групп и курсов (GroupCallback) ----------

@router.callback_query(GroupCallback.filter())
async def cb_group_handler(query: CallbackQuery, callback_data: GroupCallback):
    await safe_query_answer(query)
    
    if callback_data.action == "zaochn_menu":
        await safe_edit_text(
            query.message,
            f"{te(PE_PEOPLE)} <b>Заочное отделение:</b>\n\n"
            "Выбери курс заочного отделения или открой полный список групп:",
            reply_markup=get_zaochn_selection_keyboard()
        )
        return

    if callback_data.action == "zaochn_all":
        groups = await get_zaochn_groups()
        kb = get_groups_search_inline_keyboard(groups, with_back_course=True, back_action="zaochn_menu")
        await safe_edit_text(
            query.message,
            f"{te(PE_INFO)} <b>Все группы заочного отделения ({len(groups)}):</b>\nВыбери свою группу кнопками:",
            reply_markup=kb
        )
        return

    if callback_data.action == "course":
        course_num = callback_data.course
        form = callback_data.form or "fulltime"
        groups = await get_groups_by_course(course_num, form=form)
        if not groups:
            form_text = "очного" if form == "fulltime" else "заочного"
            await safe_query_answer(query, f"Группы {course_num} курса ({form_text}) не найдены.", show_alert=True)
            return
        back_act = "change_group" if form == "fulltime" else "zaochn_menu"
        kb = get_groups_search_inline_keyboard(groups, with_back_course=True, back_action=back_act)
        title_form = "очное отделение" if form == "fulltime" else "заочное отделение"
        await safe_edit_text(
            query.message,
            f"{te(PE_INFO)} <b>Группы {course_num} курса ({title_form}, {len(groups)}):</b>\nВыбери свою группу кнопками:",
            reply_markup=kb
        )
        return

    if callback_data.action == "select":
        g_id = callback_data.group_id
        all_groups = await get_groups()
        g_info = all_groups.get(g_id, {})
        g_name = g_info.get("name", "Группа")
        
        await set_user_group(
            user_id=query.from_user.id,
            group_id=g_id,
            group_name=g_name,
            username=query.from_user.username,
            first_name=query.from_user.first_name
        )
        
        dates_info = await get_available_dates()
        today_str = dates_info.get("today") or datetime.now().strftime("%Y-%m-%d")
        
        await safe_edit_text(
            query.message,
            f"{te(PE_CLOCK)} <i>Загружаю расписание группы {html.escape(g_name)}...</i>"
        )

        sched = await get_group_schedule(g_id, today_str)
        text = format_schedule_message(sched, g_name, today_str, "Сегодня")
        web_url = sched.get("url")
        kb = get_schedule_nav_inline_keyboard(g_id, today_str, web_url)
        
        await safe_edit_text(query.message, text, reply_markup=kb)


# ---------- Обработчики выбора дат (DateCallback) ----------

@router.callback_query(DateCallback.filter())
async def cb_date_handler(query: CallbackQuery, callback_data: DateCallback):
    action = callback_data.action
    target_type = callback_data.target_type
    target_id = callback_data.target_id
    date_str = callback_data.date

    if not target_id:
        user = await get_user(query.from_user.id)
        if user and user.get("group_id"):
            target_id = user["group_id"]
        else:
            await safe_query_answer(query, "Сначала выбери группу в меню.", show_alert=True)
            return

    if action == "nav":
        dates_info = await get_available_dates()
        dates_list = dates_info.get("dates", [])
        today_str = dates_info.get("today")
        kb = get_dates_inline_keyboard(dates_list, target_type=target_type, target_id=target_id, today_str=today_str)
        try:
            await query.message.edit_reply_markup(reply_markup=kb)
        except TelegramBadRequest:
            pass
        await safe_query_answer(query)
        return

    if action == "pick":
        if target_type == "teacher":
            all_staff = await get_staffs()
            t_info = all_staff.get(target_id, {})
            t_name = t_info.get("short_fio") or t_info.get("fio", "Преподаватель")
            
            sched = await get_teacher_schedule(target_id, date_str)
            text = format_teacher_schedule_message(sched, t_name, date_str)
            web_url = sched.get("url")
            kb = get_teacher_schedule_nav_inline_keyboard(target_id, date_str, web_url)
            edited = await safe_edit_text(query.message, text, reply_markup=kb)
            if edited:
                await safe_query_answer(query, "Расписание обновлено!")
            else:
                await safe_query_answer(query, "Расписание актуально, изменений нет.")
        else:
            all_groups = await get_groups()
            g_info = all_groups.get(target_id, {})
            g_name = g_info.get("name", "Группа")
            
            sched = await get_group_schedule(target_id, date_str)
            text = format_schedule_message(sched, g_name, date_str)
            web_url = sched.get("url")
            kb = get_schedule_nav_inline_keyboard(target_id, date_str, web_url)
            edited = await safe_edit_text(query.message, text, reply_markup=kb)
            if edited:
                await safe_query_answer(query, "Расписание обновлено!")
            else:
                await safe_query_answer(query, "Расписание актуально, изменений нет.")


# ---------- Поиск по текстовому вводу (если пользователь захочет написать) ----------

@router.message(BotStates.waiting_for_group_search)
async def process_group_search_state(message: Message, state: FSMContext):
    await state.clear()
    if not message.text:
        await safe_answer(message, f"{te(PE_WARNING, '!')} Отправь номер или первые буквы группы.", reply_markup=get_main_keyboard())
        return
    await handle_group_search_query(message, message.text.strip())


@router.message(BotStates.waiting_for_teacher_search)
async def process_teacher_search_state(message: Message, state: FSMContext):
    await state.clear()
    if not message.text:
        await safe_answer(message, f"{te(PE_WARNING, '!')} Отправь фамилию преподавателя текстом или выбери букву кнопками.", reply_markup=get_main_keyboard())
        return
    query = message.text.strip()
    teachers = await search_teachers(query)
    if not teachers:
        await safe_answer(
            message,
            f"{te(PE_CROSS, '!')} Преподаватели по запросу «<b>{html.escape(query)}</b>» не найдены.\n"
            "Попробуй выбрать букву кнопками или введи только фамилию (например: <code>Агеева</code>).",
            reply_markup=get_teachers_letters_keyboard(await get_teacher_letters())
        )
        return

    kb = get_teachers_search_inline_keyboard(teachers, with_back=True)
    await safe_answer(
        message,
        f"{te(PE_PERSON_CHECK)} <b>Найденные преподаватели ({len(teachers)}):</b>\nВыбери из списка:",
        reply_markup=kb
    )


@router.message(F.text)
async def process_any_text(message: Message, state: FSMContext):
    """Если пользователь просто прислал сообщение в чат."""
    text = message.text.strip()

    # 0. Проверяем, не запрашивает ли пользователь день недели (например: "понедельник", "на понедельник", "расписание на понедельник")
    wd = parse_weekday_from_text(text)
    if wd is not None:
        user = await get_user(message.from_user.id)
        if not user or not user.get("group_id"):
            await safe_answer(
                message,
                f"{te(PE_WARNING, '!')} <b>Сначала укажи свою группу!</b>\n"
                "Напиши в чат её номер или первые буквы (например: <code>253</code> или <code>ИС</code>):"
            )
            return

        dates_info = await get_available_dates()
        today_str = dates_info.get("today") or datetime.now().strftime("%Y-%m-%d")
        try:
            today_dt = datetime.strptime(today_str, "%Y-%m-%d")
        except Exception:
            today_dt = datetime.now()

        target_date_str, day_label = resolve_weekday_to_date(wd, today_dt)
        wait_msg = await safe_answer(
            message,
            f"{te(PE_CALENDAR)} <i>Загружаю расписание на {day_label.lower()} ({target_date_str})...</i>"
        )
        sched = await get_group_schedule(user["group_id"], target_date_str)
        text_msg = format_schedule_message(sched, user["group_name"], target_date_str, day_label)
        web_url = sched.get("url")
        kb = get_schedule_nav_inline_keyboard(user["group_id"], target_date_str, web_url)
        if wait_msg:
            edited = await safe_edit_text(wait_msg, text_msg, reply_markup=kb)
            if not edited:
                await safe_answer(message, text_msg, reply_markup=kb)
        else:
            await safe_answer(message, text_msg, reply_markup=kb)
        return

    if len(text) <= 25:
        # 1. Поиск групп по первым буквам или цифрам (например: ис, 253, ав-261, 26)
        groups = await search_groups(text)
        if groups:
            await handle_group_search_query(message, text, preloaded_groups=groups)
            return
        
        # 2. Поиск преподавателя по фамилии
        teachers = await search_teachers(text)
        if teachers:
            kb = get_teachers_search_inline_keyboard(teachers, with_back=False)
            await safe_answer(
                message,
                f"{te(PE_PERSON_CHECK)} <b>Найденные преподаватели ({len(teachers)}):</b>\nВыбери из списка:",
                reply_markup=kb
            )
            return

    # Если ничего не подошло
    await safe_answer(
        message,
        f"{te(PE_CROSS, '!')} По запросу «<b>{html.escape(text)}</b>» ничего не найдено.\n\n"
        f"{te(PE_STAR)} <b>Подсказка:</b> чтобы найти группу, отправь в чат её номер или первые буквы (например: <code>ИС</code>, <code>253</code> или <code>АВ-261</code>).",
        reply_markup=get_main_menu_inline()
    )


async def handle_group_search_query(message: Message, query: str, preloaded_groups=None):
    groups = preloaded_groups if preloaded_groups is not None else await search_groups(query)
    
    if not groups:
        await safe_answer(
            message,
            f"{te(PE_CROSS, '!')} Группы по запросу «<b>{html.escape(query)}</b>» не найдены.\n"
            "Попробуй ввести первые буквы (например: <code>ИС</code>) или цифры (например: <code>253</code>):",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[get_home_button_row()])
        )
        return

    if len(groups) == 1:
        g = groups[0]
        await set_user_group(
            user_id=message.from_user.id,
            group_id=str(g["id"]),
            group_name=g["name"],
            username=message.from_user.username,
            first_name=message.from_user.first_name
        )
        dates_info = await get_available_dates()
        today_str = dates_info.get("today") or datetime.now().strftime("%Y-%m-%d")

        wait_msg = await safe_answer(message, f"{te(PE_CHECK)} Выбрана группа <b>{html.escape(g['name'])}</b>!\nЗагружаю расписание...")
        sched = await get_group_schedule(str(g["id"]), today_str)
        text = format_schedule_message(sched, g["name"], today_str, "Сегодня")
        web_url = sched.get("url")
        kb = get_schedule_nav_inline_keyboard(str(g["id"]), today_str, web_url)
        
        if wait_msg:
            edited = await safe_edit_text(wait_msg, text, reply_markup=kb)
            if not edited:
                await safe_answer(message, text, reply_markup=kb)
        else:
            await safe_answer(message, text, reply_markup=kb)
        return

    kb = get_groups_search_inline_keyboard(groups)
    await safe_answer(
        message,
        f"{te(PE_PEOPLE)} <b>Найденные группы ({len(groups)}):</b>\nВыбери свою группу кнопками:",
        reply_markup=kb
    )


# ---------- Панель администратора (/admin) ----------

async def render_admin_panel_text() -> str:
    """Формирует текст главной панели администратора."""
    is_maint = await is_maintenance_mode()
    stats = await get_bot_stats()
    maint_status = (
        f"{te(PE_LOCK_CLOSED)} <b>ВКЛЮЧЕН</b> (доступ только админам)"
        if is_maint else
        f"{te(PE_CHECK)} <b>ВЫКЛЮЧЕН</b> (бот открыт для всех)"
    )
    return (
        f"{te(PE_SETTINGS)} <b>Панель администратора</b>\n\n"
        f"{te(PE_WARNING)} <b>Технический перерыв:</b> {maint_status}\n\n"
        f"{te(PE_PEOPLE)} <b>Пользователей в базе:</b> <code>{stats['total']}</code>\n"
        f"{te(PE_BELL)} <b>С уведомлениями:</b> <code>{stats['with_notif']}</code>\n"
        f"{te(PE_SEARCH)} <b>Выбрали группу:</b> <code>{stats['with_group']}</code>\n"
        f"{te(PE_PERSON_CHECK)} <b>Выбрали преподавателя:</b> <code>{stats['with_teacher']}</code>\n\n"
        f"{te(PE_MEGAPHONE)} <b>Рассылок проведено:</b> <code>{stats['total_broadcasts']}</code> (доставлено: <code>{stats['total_sent_broadcast_messages']}</code>)\n"
        f"{te(PE_CLOCK)} <b>Запланировано рассылок:</b> <code>{stats['scheduled_broadcasts']}</code>"
    )


@router.message(Command("admin", "adm"), StateFilter("*"))
async def cmd_admin(message: Message, state: FSMContext):
    """Команда открытия панели администратора."""
    await state.clear()
    if not await is_admin(message.from_user.id):
        await safe_answer(message, f"{te(PE_WARNING, '!')} <b>Доступ запрещен.</b> У вас нет прав администратора.")
        return
    panel_text = await render_admin_panel_text()
    is_maint = await is_maintenance_mode()
    await safe_answer(message, panel_text, reply_markup=get_admin_keyboard(is_maint))


@router.callback_query(AdminCallback.filter())
async def cb_admin_handler(query: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    """Обработчик действий внутри панели администратора."""
    if not await is_admin(query.from_user.id):
        await safe_query_answer(query, "Доступ запрещен.", show_alert=True)
        return

    action = callback_data.action

    if action == "panel":
        await state.clear()
        panel_text = await render_admin_panel_text()
        is_maint = await is_maintenance_mode()
        await safe_edit_text(query.message, panel_text, reply_markup=get_admin_keyboard(is_maint))
        await safe_query_answer(query)

    elif action == "toggle_maint":
        curr = await is_maintenance_mode()
        new_maint = not curr
        await set_maintenance_mode(new_maint)
        alert_text = (
            "Технический перерыв ВКЛЮЧЕН!\nБот закрыт для всех обычных пользователей."
            if new_maint else
            "Технический перерыв ВЫКЛЮЧЕН!\nБот снова открыт для всех пользователей."
        )
        await safe_query_answer(query, alert_text, show_alert=True)
        panel_text = await render_admin_panel_text()
        await safe_edit_text(query.message, panel_text, reply_markup=get_admin_keyboard(new_maint))

    elif action == "stats":
        text = await render_stat_admin_bot_stats_text()
        await safe_edit_text(query.message, text, reply_markup=get_stat_admin_bot_stats_keyboard())
        await safe_query_answer(query)

    elif action == "bc_stats":
        text, total_pages, broadcasts = await render_broadcast_list_text(page=0)
        kb = get_broadcast_list_keyboard(broadcasts, page=0, total_pages=total_pages)
        await safe_edit_text(query.message, text, reply_markup=kb)
        await safe_query_answer(query)

    elif action == "refresh_cache":
        try:
            await get_groups(force_refresh=True)
            await get_available_dates(force_refresh=True)
            await safe_query_answer(query, "Кэш групп и дат успешно сброшен!", show_alert=True)
        except Exception as e:
            await safe_query_answer(query, f"Ошибка обновления кэша: {e}", show_alert=True)

    elif action == "close":
        await state.clear()
        try:
            await query.message.delete()
        except Exception:
            pass

    elif action == "broadcast":
        await state.set_state(BotStates.waiting_for_broadcast_text)
        text = (
            f"{te(PE_MEGAPHONE)} <b>Создание новой рассылки</b>\n\n"
            "Отправьте текст сообщения для рассылки всем пользователям бота.\n"
            "<i>Поддерживается HTML-форматирование и премиум-эмодзи.</i>\n\n"
            "На следующем шаге вы сможете задать <b>точное время отправки</b> и выбрать, "
            "<b>закреплять ли сообщение</b> в чатах пользователей.\n\n"
            "<i>Для отмены напишите <code>отмена</code> или нажмите кнопку ниже:</i>"
        )
        await safe_edit_text(query.message, text, reply_markup=get_admin_back_keyboard())
        await safe_query_answer(query)


# ---------- Логика создания и настройки рассылки ----------

def parse_custom_scheduled_time(input_str: str) -> Tuple[Optional[datetime], Optional[str]]:
    """
    Разбирает пользовательскую строку даты/времени для запланированной рассылки.
    Поддерживает:
    - ЧЧ:ММ (напр. 18:30)
    - ДД.ММ ЧЧ:ММ (напр. 12.09 10:00)
    - ДД.ММ.ГГГГ ЧЧ:ММ (напр. 12.09.2026 10:00)
    """
    raw = input_str.strip()
    now = datetime.now()

    # 1. Формат ЧЧ:ММ
    time_match = re.match(r"^(\d{1,2})[:.-](\d{2})$", raw)
    if time_match:
        h, m = int(time_match.group(1)), int(time_match.group(2))
        if 0 <= h <= 23 and 0 <= m <= 59:
            target_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if target_dt <= now:
                # Если время сегодня уже прошло, переносим на завтра
                target_dt += timedelta(days=1)
            return target_dt, None
        return None, "Некорректное время. Часы: 0-23, минуты: 0-59."

    # 2. Формат ДД.ММ ЧЧ:ММ
    dt_match1 = re.match(r"^(\d{1,2})[.-](\d{1,2})\s+(\d{1,2})[:.-](\d{2})$", raw)
    if dt_match1:
        d, mon, h, m = int(dt_match1.group(1)), int(dt_match1.group(2)), int(dt_match1.group(3)), int(dt_match1.group(4))
        try:
            target_dt = datetime(year=now.year, month=mon, day=d, hour=h, minute=m, second=0)
            if target_dt <= now:
                target_dt = datetime(year=now.year + 1, month=mon, day=d, hour=h, minute=m, second=0)
            return target_dt, None
        except ValueError:
            return None, "Некорректная дата или время."

    # 3. Формат ДД.ММ.ГГГГ ЧЧ:ММ
    dt_match2 = re.match(r"^(\d{1,2})[.-](\d{1,2})[.-](\d{4})\s+(\d{1,2})[:.-](\d{2})$", raw)
    if dt_match2:
        d, mon, y, h, m = int(dt_match2.group(1)), int(dt_match2.group(2)), int(dt_match2.group(3)), int(dt_match2.group(4)), int(dt_match2.group(5))
        try:
            target_dt = datetime(year=y, month=mon, day=d, hour=h, minute=m, second=0)
            if target_dt <= now:
                return None, "Указанное время уже прошло. Введите дату и время в будущем."
            return target_dt, None
        except ValueError:
            return None, "Некорректная дата или время."

    return None, "Не удалось распознать формат. Используйте <code>ЧЧ:ММ</code> (напр. <code>18:30</code>) или <code>ДД.ММ ЧЧ:ММ</code> (напр. <code>12.09 10:00</code>)."


def render_broadcast_setup_text(
    broadcast_text: str,
    pin_message: bool,
    scheduled_at_str: Optional[str],
    total_users: int,
    repeat_type: str = "once",
    repeat_time: Optional[str] = None
) -> str:
    """Формирует предпросмотр и параметры создаваемой рассылки."""
    pin_label = (
        f"{te(PE_CHECK)} <b>Да</b> (сообщение закрепится в чате)"
        if pin_message else
        f"{te(PE_CROSS)} <b>Нет</b> (обычное сообщение)"
    )
    if repeat_type == "daily":
        time_label = f"{te(PE_REPEAT)} <b>Каждый день в {repeat_time or '07:00'}</b> (след. отправка: <code>{scheduled_at_str}</code>)"
    elif scheduled_at_str:
        time_label = f"{te(PE_CLOCK)} <b>Запланировано на:</b> <code>{scheduled_at_str}</code>"
    else:
        time_label = f"{te(PE_SEND_UP)} <b>Сразу после подтверждения</b>"

    return (
        f"{te(PE_MEGAPHONE)} <b>Параметры рассылки:</b>\n\n"
        f"<b>Предпросмотр сообщения:</b>\n"
        f"────────────────────\n"
        f"{broadcast_text}\n"
        f"────────────────────\n\n"
        f"{te(PE_CLOCK)} <b>Время отправки:</b> {time_label}\n"
        f"{te(PE_PAPERCLIP)} <b>Закрепление:</b> {pin_label}\n"
        f"{te(PE_PEOPLE)} <b>Получателей:</b> <code>~{total_users}</code> чел.\n\n"
        f"<i>Настройте параметры кнопками ниже и подтвердите отправку:</i>"
    )


@router.message(BotStates.waiting_for_broadcast_text)
async def handle_broadcast_text_input(message: Message, state: FSMContext):
    """Прием текста сообщения для рассылки администратором."""
    if not await is_admin(message.from_user.id):
        await state.clear()
        return

    text = message.text or message.caption or ""
    if text.strip().lower() in ("отмена", "/cancel", "отменить"):
        await state.clear()
        panel_text = await render_admin_panel_text()
        is_maint = await is_maintenance_mode()
        await safe_answer(message, f"{te(PE_CROSS)} Создание рассылки отменено.")
        await safe_answer(message, panel_text, reply_markup=get_admin_keyboard(is_maint))
        return

    formatted_text = message.html_text if hasattr(message, "html_text") else html.escape(text)
    user_ids = await get_all_user_ids()
    total_users = len(user_ids)

    # Сохраняем в FSM данные по умолчанию (время: Сразу, закрепление: Нет)
    await state.update_data(
        broadcast_text=formatted_text,
        pin_message=False,
        scheduled_at=None,
        repeat_type="once",
        repeat_time=None,
        total_users=total_users
    )

    setup_text = render_broadcast_setup_text(
        broadcast_text=formatted_text,
        pin_message=False,
        scheduled_at_str=None,
        total_users=total_users,
        repeat_type="once",
        repeat_time=None
    )
    kb = get_broadcast_setup_keyboard(
        pin_enabled=False,
        is_scheduled=False,
        scheduled_label="Сразу",
        is_daily=False
    )
    await safe_answer(message, setup_text, reply_markup=kb)


@router.callback_query(BroadcastCallback.filter())
async def cb_broadcast_handler(query: CallbackQuery, callback_data: BroadcastCallback, state: FSMContext):
    """Обработчик настройки параметров и отправки рассылки."""
    if not await is_admin(query.from_user.id):
        await safe_query_answer(query, "Доступ запрещен.", show_alert=True)
        return

    action = callback_data.action
    data = await state.get_data()
    bc_text = data.get("broadcast_text")

    if action == "cancel":
        await state.clear()
        panel_text = await render_admin_panel_text()
        is_maint = await is_maintenance_mode()
        await safe_edit_text(query.message, panel_text, reply_markup=get_admin_keyboard(is_maint))
        await safe_query_answer(query, "Создание рассылки отменено.")
        return

    if not bc_text:
        await safe_query_answer(query, "Данные рассылки устарели. Начните создание заново.", show_alert=True)
        return

    pin_message = data.get("pin_message", False)
    scheduled_at = data.get("scheduled_at")
    repeat_type = data.get("repeat_type", "once")
    repeat_time = data.get("repeat_time")
    is_daily = (repeat_type == "daily")
    total_users = data.get("total_users") or len(await get_all_user_ids())

    if action == "toggle_pin":
        pin_message = not pin_message
        await state.update_data(pin_message=pin_message)
        if is_daily:
            sch_label = f"Ежедневно в {repeat_time or '07:00'}"
        else:
            sch_label = scheduled_at if scheduled_at else "Сразу"
        setup_text = render_broadcast_setup_text(bc_text, pin_message, scheduled_at, total_users, repeat_type, repeat_time)
        kb = get_broadcast_setup_keyboard(pin_message, bool(scheduled_at), sch_label, is_daily=is_daily)
        await safe_edit_text(query.message, setup_text, reply_markup=kb)
        await safe_query_answer(query, "Закрепление ВКЛЮЧЕНО" if pin_message else "Закрепление ВЫКЛЮЧЕНО")

    elif action == "time_menu":
        text = (
            f"{te(PE_CLOCK)} <b>Выбор времени отправки рассылки</b>\n\n"
            "Выберите быстрый пресет, настройте <b>ежедневную рассылку</b> (например, каждое утро в 07:00) "
            "или введите дату и точное время вручную:\n\n"
            f"Текущее время бота: <code>{datetime.now().strftime('%d.%m.%Y %H:%M')}</code>"
        )
        await safe_edit_text(query.message, text, reply_markup=get_broadcast_time_selection_keyboard())
        await safe_query_answer(query)

    elif action == "back_setup":
        await state.set_state(BotStates.waiting_for_broadcast_text)
        if is_daily:
            sch_label = f"Ежедневно в {repeat_time or '07:00'}"
        else:
            sch_label = scheduled_at if scheduled_at else "Сразу"
        setup_text = render_broadcast_setup_text(bc_text, pin_message, scheduled_at, total_users, repeat_type, repeat_time)
        kb = get_broadcast_setup_keyboard(pin_message, bool(scheduled_at), sch_label, is_daily=is_daily)
        await safe_edit_text(query.message, setup_text, reply_markup=kb)
        await safe_query_answer(query)

    elif action == "set_time":
        val = callback_data.val
        now = datetime.now()
        new_scheduled_at = None
        new_repeat_type = "once"
        new_repeat_time = None

        if val == "now":
            new_scheduled_at = None
        elif val == "daily_7am":
            new_repeat_type = "daily"
            new_repeat_time = "07:00"
            today_7am = now.replace(hour=7, minute=0, second=0, microsecond=0)
            first_dt = today_7am if now < today_7am else (today_7am + timedelta(days=1))
            new_scheduled_at = first_dt.strftime("%Y-%m-%d %H:%M:00")
        elif val == "daily_custom":
            await state.set_state(BotStates.waiting_for_broadcast_daily_time)
            text = (
                f"{te(PE_CLOCK)} <b>Настройка ежедневной рассылки</b>\n\n"
                "Отправьте время в формате <code>ЧЧ:ММ</code>, в которое бот должен <b>каждый день</b> отправлять эту рассылку всем пользователям.\n\n"
                "<b>Примеры:</b>\n"
                "• <code>07:00</code> — каждое утро в 7:00\n"
                "• <code>14:30</code> — каждый день в 14:30\n"
                "• <code>20:00</code> — каждый вечер в 20:00\n\n"
                "<i>Для отмены нажмите кнопку ниже:</i>"
            )
            await safe_edit_text(query.message, text, reply_markup=get_broadcast_custom_time_back_keyboard())
            await safe_query_answer(query)
            return
        elif val == "15m":
            new_scheduled_at = (now + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:00")
        elif val == "1h":
            new_scheduled_at = (now + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:00")
        elif val == "3h":
            new_scheduled_at = (now + timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:00")
        elif val == "tomorrow_9am":
            tomorrow = now + timedelta(days=1)
            new_scheduled_at = tomorrow.strftime("%Y-%m-%d 09:00:00")
        elif val == "custom":
            await state.set_state(BotStates.waiting_for_broadcast_custom_time)
            text = (
                f"{te(PE_CLOCK)} <b>Ручной ввод времени рассылки</b>\n\n"
                "Отправьте сообщение с желаемым временем отправки.\n\n"
                "<b>Поддерживаемые форматы:</b>\n"
                "• <code>18:30</code> — сегодня в 18:30 (или завтра, если время прошло)\n"
                "• <code>12.09 10:00</code> — на указанный день и время\n"
                "• <code>12.09.2026 10:00</code> — точная дата и время\n\n"
                "<i>Для отмены нажмите кнопку ниже:</i>"
            )
            await safe_edit_text(query.message, text, reply_markup=get_broadcast_custom_time_back_keyboard())
            await safe_query_answer(query)
            return

        await state.update_data(
            scheduled_at=new_scheduled_at,
            repeat_type=new_repeat_type,
            repeat_time=new_repeat_time
        )
        scheduled_at = new_scheduled_at
        repeat_type = new_repeat_type
        repeat_time = new_repeat_time
        is_daily = (repeat_type == "daily")

        if is_daily:
            sch_label = f"Ежедневно в {repeat_time}"
        else:
            sch_label = scheduled_at if scheduled_at else "Сразу"

        setup_text = render_broadcast_setup_text(bc_text, pin_message, scheduled_at, total_users, repeat_type, repeat_time)
        kb = get_broadcast_setup_keyboard(pin_message, bool(scheduled_at), sch_label, is_daily=is_daily)
        await safe_edit_text(query.message, setup_text, reply_markup=kb)
        await safe_query_answer(query, f"Время установлено: {sch_label}")

    elif action == "confirm_send":
        await state.clear()
        bc_id = await create_broadcast(
            created_by=query.from_user.id,
            message_text=bc_text,
            pin_message=pin_message,
            scheduled_at=scheduled_at,
            repeat_type=repeat_type,
            repeat_time=repeat_time
        )

        pin_note = "Да (будет закреплено в чатах)" if pin_message else "Нет"
        if is_daily:
            success_msg = (
                f"{te(PE_REPEAT)} <b>Ежедневная рассылка #{bc_id} успешно запущена!</b>\n\n"
                f"{te(PE_CLOCK)} Время: <b>Каждый день в {repeat_time}</b>\n"
                f"{te(PE_CALENDAR)} Первая отправка: <code>{scheduled_at}</code>\n"
                f"{te(PE_PAPERCLIP)} Закрепление: <b>{pin_note}</b>\n"
                f"{te(PE_PEOPLE)} Получателей: <b>{total_users}</b>\n\n"
                f"<i>Бот будет отправлять рассылку каждый день точно в {repeat_time}. "
                f"Вы можете отслеживать статистику или остановить рассылку кнопками в статистике.</i>"
            )
        elif not scheduled_at:
            # Мгновенный запуск рассылки в фоне
            asyncio.create_task(execute_broadcast(query.bot, bc_id))
            pin_note_fast = "Сообщение будет закреплено в чатах пользователей." if pin_message else "Без закрепления."
            success_msg = (
                f"{te(PE_SEND_UP)} <b>Рассылка #{bc_id} запущена!</b>\n\n"
                f"{te(PE_PEOPLE)} Получателей: <b>{total_users}</b>\n"
                f"{te(PE_PAPERCLIP)} Закрепление: <b>{pin_note_fast}</b>\n\n"
                f"<i>Бот выполняет рассылку в фоновом режиме. По завершении вы получите детальный отчёт.</i>"
            )
        else:
            success_msg = (
                f"{te(PE_CHECK)} <b>Рассылка #{bc_id} успешно запланирована!</b>\n\n"
                f"{te(PE_CLOCK)} Время отправки: <code>{scheduled_at}</code>\n"
                f"{te(PE_PAPERCLIP)} Закрепление: <b>{pin_note}</b>\n"
                f"{te(PE_PEOPLE)} Примерно получателей: <b>{total_users}</b>\n\n"
                f"<i>Рассылка будет автоматически отправлена ровно в указанное время. "
                f"Вы можете отслеживать её статус или отменить в панели аналитики (/statadmin).</i>"
            )

        await safe_edit_text(query.message, success_msg, reply_markup=get_admin_back_keyboard())
        await safe_query_answer(query)


@router.message(BotStates.waiting_for_broadcast_daily_time)
async def handle_broadcast_daily_time_input(message: Message, state: FSMContext):
    """Прием времени ЧЧ:ММ для ежедневной рассылки."""
    if not await is_admin(message.from_user.id):
        await state.clear()
        return

    text = (message.text or "").strip()
    if text.lower() in ("отмена", "/cancel", "отменить"):
        await state.set_state(BotStates.waiting_for_broadcast_text)
        data = await state.get_data()
        bc_text = data.get("broadcast_text", "")
        pin_message = data.get("pin_message", False)
        scheduled_at = data.get("scheduled_at")
        repeat_type = data.get("repeat_type", "once")
        repeat_time = data.get("repeat_time")
        total_users = data.get("total_users") or len(await get_all_user_ids())
        sch_label = scheduled_at if scheduled_at else "Сразу"
        setup_text = render_broadcast_setup_text(bc_text, pin_message, scheduled_at, total_users, repeat_type, repeat_time)
        kb = get_broadcast_setup_keyboard(pin_message, bool(scheduled_at), sch_label, is_daily=(repeat_type == "daily"))
        await safe_answer(message, setup_text, reply_markup=kb)
        return

    time_match = re.match(r"^(\d{1,2})[:.-](\d{2})$", text)
    if not time_match:
        await safe_answer(
            message,
            f"{te(PE_WARNING, '!')} Не удалось распознать время.\n"
            "Пожалуйста, введите время в формате <code>ЧЧ:ММ</code> (например: <code>07:00</code> или <code>15:30</code>).\n"
            "Или напишите <code>отмена</code>."
        )
        return

    h, m = int(time_match.group(1)), int(time_match.group(2))
    if not (0 <= h <= 23 and 0 <= m <= 59):
        await safe_answer(message, f"{te(PE_WARNING, '!')} Некорректное время. Часы должны быть 0-23, минуты 0-59.")
        return

    rep_time_str = f"{h:02d}:{m:02d}"
    now = datetime.now()
    target_today = now.replace(hour=h, minute=m, second=0, microsecond=0)
    first_dt = target_today if now < target_today else (target_today + timedelta(days=1))
    scheduled_at_str = first_dt.strftime("%Y-%m-%d %H:%M:00")

    await state.update_data(scheduled_at=scheduled_at_str, repeat_type="daily", repeat_time=rep_time_str)
    await state.set_state(BotStates.waiting_for_broadcast_text)

    data = await state.get_data()
    bc_text = data.get("broadcast_text", "")
    pin_message = data.get("pin_message", False)
    total_users = data.get("total_users") or len(await get_all_user_ids())

    sch_label = f"Ежедневно в {rep_time_str}"
    setup_text = render_broadcast_setup_text(bc_text, pin_message, scheduled_at_str, total_users, repeat_type="daily", repeat_time=rep_time_str)
    kb = get_broadcast_setup_keyboard(pin_message, True, sch_label, is_daily=True)
    await safe_answer(
        message,
        f"{te(PE_CHECK)} Время установлено: <b>Каждый день в {rep_time_str}</b> (первая отправка: <code>{scheduled_at_str}</code>)\n\n" + setup_text,
        reply_markup=kb
    )


@router.message(BotStates.waiting_for_broadcast_custom_time)
async def handle_broadcast_custom_time_input(message: Message, state: FSMContext):
    """Прием ручного ввода времени для однократной запланированной рассылки."""
    if not await is_admin(message.from_user.id):
        await state.clear()
        return

    text = (message.text or "").strip()
    if text.lower() in ("отмена", "/cancel", "отменить"):
        await state.set_state(BotStates.waiting_for_broadcast_text)
        data = await state.get_data()
        bc_text = data.get("broadcast_text", "")
        pin_message = data.get("pin_message", False)
        scheduled_at = data.get("scheduled_at")
        total_users = data.get("total_users") or len(await get_all_user_ids())
        sch_label = scheduled_at if scheduled_at else "Сразу"
        setup_text = render_broadcast_setup_text(bc_text, pin_message, scheduled_at, total_users)
        kb = get_broadcast_setup_keyboard(pin_message, bool(scheduled_at), sch_label)
        await safe_answer(message, setup_text, reply_markup=kb)
        return

    target_dt, err = parse_custom_scheduled_time(text)
    if err or not target_dt:
        err_text = err or "Не удалось распознать время."
        await safe_answer(
            message,
            f"{te(PE_WARNING, '!')} {err_text}\n\n"
            "Попробуйте ещё раз, например: <code>18:30</code> или <code>12.09 10:00</code>.\n"
            "Или напишите <code>отмена</code>."
        )
        return

    scheduled_at_str = target_dt.strftime("%Y-%m-%d %H:%M:00")
    await state.update_data(scheduled_at=scheduled_at_str, repeat_type="once", repeat_time=None)
    await state.set_state(BotStates.waiting_for_broadcast_text)

    data = await state.get_data()
    bc_text = data.get("broadcast_text", "")
    pin_message = data.get("pin_message", False)
    total_users = data.get("total_users") or len(await get_all_user_ids())

    setup_text = render_broadcast_setup_text(bc_text, pin_message, scheduled_at_str, total_users)
    kb = get_broadcast_setup_keyboard(pin_message, True, scheduled_at_str)
    await safe_answer(
        message,
        f"{te(PE_CHECK)} Время отправки установлено: <code>{scheduled_at_str}</code>\n\n" + setup_text,
        reply_markup=kb
    )


# ---------- Отдельная панель статистики (/statadmin, /stats) ----------

async def render_stat_admin_menu_text() -> str:
    """Формирует текст главного экрана панели статистики."""
    stats = await get_bot_stats()
    bc_summary = await get_broadcasts_summary()
    return (
        f"{te(PE_CHART_STATS)} <b>Панель статистики и аналитики</b>\n\n"
        f"Добро пожаловать в панель просмотра показателей бота и отчётов по рассылкам.\n\n"
        f"{te(PE_PEOPLE)} <b>Всего пользователей в базе:</b> <code>{stats['total']}</code>\n"
        f"{te(PE_BELL)} <b>С включенными уведомлениями:</b> <code>{stats['with_notif']}</code>\n"
        f"{te(PE_CHART_GROW)} <b>Активных пользователей за 24 часа:</b> <code>{stats['active_today']}</code>\n\n"
        f"{te(PE_MEGAPHONE)} <b>Успешно завершено рассылок:</b> <code>{bc_summary['completed']}</code>\n"
        f"{te(PE_CLOCK)} <b>Запланировано отложенных рассылок:</b> <code>{bc_summary['scheduled']}</code>\n"
        f"{te(PE_CHECK)} <b>Суммарно доставлено сообщений:</b> <code>{bc_summary['sum_sent']}</code>\n\n"
        f"<i>Выберите нужный раздел для подробного просмотра:</i>"
    )


async def render_stat_admin_bot_stats_text() -> str:
    """Формирует детальную статистику аудитории бота."""
    stats = await get_bot_stats()
    top_groups_str = "\n".join([f"  • <b>{html.escape(g)}</b>: <code>{cnt}</code> чел." for g, cnt in stats["top_groups"]]) or "  <i>Нет данных</i>"
    pct_notif = round(stats['with_notif'] / stats['total'] * 100, 1) if stats['total'] > 0 else 0
    pct_group = round(stats['with_group'] / stats['total'] * 100, 1) if stats['total'] > 0 else 0
    pct_teacher = round(stats['with_teacher'] / stats['total'] * 100, 1) if stats['total'] > 0 else 0

    return (
        f"{te(PE_CHART_STATS)} <b>Детальная статистика аудитории бота</b>\n\n"
        f"{te(PE_PEOPLE)} Всего пользователей в базе: <b>{stats['total']}</b>\n"
        f"{te(PE_BELL)} Включили уведомления: <b>{stats['with_notif']}</b> ({pct_notif}%)\n"
        f"{te(PE_SEARCH)} Выбрали группу: <b>{stats['with_group']}</b> ({pct_group}%)\n"
        f"{te(PE_PERSON_CHECK)} Выбрали преподавателя: <b>{stats['with_teacher']}</b> ({pct_teacher}%)\n\n"
        f"{te(PE_CHART_GROW)} <b>Показатели активности:</b>\n"
        f"  • Активны за последние 24 часа: <b>{stats['active_today']}</b> чел.\n"
        f"  • Активны за последние 7 дней: <b>{stats['active_week']}</b> чел.\n\n"
        f"{te(PE_STAR)} <b>Топ-5 популярных групп:</b>\n{top_groups_str}"
    )


async def render_broadcast_list_text(page: int = 0) -> Tuple[str, int, list]:
    """Формирует текст списка рассылок с пагинацией."""
    PAGE_SIZE = 5
    total_count = await get_broadcasts_count()
    total_pages = max(1, (total_count + PAGE_SIZE - 1) // PAGE_SIZE)
    if page >= total_pages:
        page = total_pages - 1
    if page < 0:
        page = 0

    broadcasts = await get_broadcasts(limit=PAGE_SIZE, offset=page * PAGE_SIZE)
    summary = await get_broadcasts_summary()

    header = (
        f"{te(PE_MEGAPHONE)} <b>История и статистика рассылок</b>\n\n"
        f"{te(PE_CHECK)} Завершено: <b>{summary['completed']}</b> | "
        f"{te(PE_CLOCK)} Запланировано: <b>{summary['scheduled']}</b> | "
        f"{te(PE_CROSS)} Отменено: <b>{summary['cancelled']}</b>\n"
        f"{te(PE_SEND_UP)} Всего доставлено сообщений: <b>{summary['sum_sent']}</b>\n\n"
        f"Страница <b>{page + 1}</b> из <b>{total_pages}</b> (всего рассылок: {total_count}):\n"
        f"<i>Нажмите на рассылку ниже, чтобы открыть карточку с подробностями:</i>"
    )
    if not broadcasts:
        header += "\n\n<i>Рассылок пока не создавалось.</i>"

    return header, total_pages, broadcasts


def render_broadcast_detail_text(bc: Dict[str, Any]) -> str:
    """Формирует подробную карточку конкретной рассылки."""
    bc_id = bc["id"]
    status = bc.get("status", "")
    created_at = bc.get("created_at") or "Не указано"
    scheduled_at = bc.get("scheduled_at")
    completed_at = bc.get("completed_at")
    repeat_type = bc.get("repeat_type", "once")
    repeat_time = bc.get("repeat_time") or "07:00"
    is_daily = (repeat_type == "daily")

    pin = bool(bc.get("pin_message", 0))
    pin_str = f"{te(PE_CHECK)} Да (закреплено в чатах)" if pin else f"{te(PE_CROSS)} Нет"

    total = bc.get("total_targets", 0)
    sent = bc.get("sent_count", 0)
    blocked = bc.get("blocked_count", 0)
    failed = bc.get("failed_count", 0)
    pct = f"{(sent / total * 100):.1f}%" if total > 0 else "0%"

    if is_daily and status == "scheduled":
        status_line = f"{te(PE_REPEAT)} <b>Активна (ежедневно в {repeat_time})</b>"
    elif status == "completed":
        status_line = f"{te(PE_CHECK)} <b>Завершена</b> (завершена: {completed_at or '-'})"
    elif status == "scheduled":
        status_line = f"{te(PE_CLOCK)} <b>Запланирована на:</b> <code>{scheduled_at}</code>"
    elif status == "in_progress":
        status_line = f"{te(PE_REPEAT)} <b>В процессе доставки...</b>"
    elif status == "cancelled":
        status_line = f"{te(PE_CROSS)} <b>Отменена администратором</b>"
    else:
        status_line = f"{te(PE_INFO)} <b>{status}</b>"

    if is_daily:
        time_line = f"{te(PE_REPEAT)} <b>Каждый день в {repeat_time}</b> (след. отправка: <code>{scheduled_at}</code>)"
    elif scheduled_at:
        time_line = f"Запланировано на: <code>{scheduled_at}</code>"
    else:
        time_line = "Отправка: <i>Сразу</i>"

    msg_preview = bc.get("message_text") or ""
    if len(msg_preview) > 600:
        msg_preview = msg_preview[:600] + "..."

    return (
        f"{te(PE_MEGAPHONE)} <b>Детальная статистика рассылки #{bc_id}</b>\n\n"
        f"{te(PE_INFO)} <b>Статус:</b> {status_line}\n"
        f"{te(PE_CALENDAR)} <b>Создана:</b> <code>{created_at}</code>\n"
        f"{te(PE_CLOCK)} <b>Время отправки:</b> {time_line}\n"
        f"{te(PE_PAPERCLIP)} <b>Закрепление:</b> {pin_str}\n\n"
        f"{te(PE_CHART_STATS)} <b>Результаты доставки:</b>\n"
        f"  {te(PE_CHECK)} Доставлено: <b>{sent}</b> из <b>{total}</b> ({pct})\n"
        f"  {te(PE_BAN)} Заблокировали бота: <b>{blocked}</b>\n"
        f"  {te(PE_WARNING)} Ошибок отправки: <b>{failed}</b>\n\n"
        f"<b>Текст сообщения:</b>\n"
        f"────────────────────\n"
        f"{msg_preview}\n"
        f"────────────────────"
    )


@router.message(Command("statadmin"))
@router.message(Command("statadmin", "stats", "stat", "statistics"), StateFilter("*"))
async def cmd_statadmin(message: Message, state: FSMContext):
    """Открытие отдельной панели статистики бота и рассылок."""
    await state.clear()
    if not await is_stat_admin(message.from_user.id):
        await safe_answer(
            message,
            f"{te(PE_WARNING, '!')} <b>Доступ запрещен.</b> У вас нет прав для просмотра аналитики."
        )
        return

    text = await render_stat_admin_menu_text()
    is_full = await is_admin(message.from_user.id)
    await safe_answer(message, text, reply_markup=get_stat_admin_menu_keyboard(is_full_admin=is_full))


@router.callback_query(StatAdminCallback.filter())
async def cb_stat_admin_handler(query: CallbackQuery, callback_data: StatAdminCallback, state: FSMContext):
    """Обработчик действий внутри панели аналитики и статистики."""
    if not await is_stat_admin(query.from_user.id):
        await safe_query_answer(query, "Доступ запрещен.", show_alert=True)
        return

    action = callback_data.action
    is_full = await is_admin(query.from_user.id)

    if action == "menu":
        text = await render_stat_admin_menu_text()
        await safe_edit_text(query.message, text, reply_markup=get_stat_admin_menu_keyboard(is_full_admin=is_full))
        await safe_query_answer(query)

    elif action == "bot_stats":
        text = await render_stat_admin_bot_stats_text()
        await safe_edit_text(query.message, text, reply_markup=get_stat_admin_bot_stats_keyboard())
        await safe_query_answer(query)

    elif action == "broadcast_list":
        page = callback_data.page
        text, total_pages, broadcasts = await render_broadcast_list_text(page)
        kb = get_broadcast_list_keyboard(broadcasts, page, total_pages)
        await safe_edit_text(query.message, text, reply_markup=kb)
        await safe_query_answer(query)

    elif action == "broadcast_detail":
        bc_id = callback_data.bc_id
        page = callback_data.page
        bc = await get_broadcast(bc_id)
        if not bc:
            await safe_query_answer(query, "Рассылка не найдена.", show_alert=True)
            return

        text = render_broadcast_detail_text(bc)
        is_scheduled = (bc.get("status") == "scheduled")
        kb = get_broadcast_detail_keyboard(bc_id, is_scheduled, page=page)
        await safe_edit_text(query.message, text, reply_markup=kb)
        await safe_query_answer(query)

    elif action == "broadcast_cancel":
        bc_id = callback_data.bc_id
        page = callback_data.page
        cancelled = await cancel_broadcast(bc_id)
        if cancelled:
            await safe_query_answer(query, f"Запланированная рассылка #{bc_id} успешно отменена!", show_alert=True)
        else:
            await safe_query_answer(query, "Не удалось отменить рассылку (возможно, она уже выполняется или завершена).", show_alert=True)

        bc = await get_broadcast(bc_id)
        if bc:
            text = render_broadcast_detail_text(bc)
            kb = get_broadcast_detail_keyboard(bc_id, is_scheduled=False, page=page)
            await safe_edit_text(query.message, text, reply_markup=kb)

    elif action == "close":
        try:
            await query.message.delete()
        except Exception:
            pass

