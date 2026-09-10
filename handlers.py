from datetime import datetime, timedelta
import html
from typing import Optional

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import get_user, set_user_group, set_user_teacher, toggle_user_notifications
from parser import (
    get_available_dates,
    get_groups,
    get_groups_by_course,
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
    get_dates_inline_keyboard,
    get_groups_search_inline_keyboard,
    get_course_selection_keyboard,
    get_teachers_letters_keyboard,
    get_teachers_search_inline_keyboard,
    get_schedule_nav_inline_keyboard,
    get_teacher_schedule_nav_inline_keyboard,
    get_calls_keyboard,
    get_my_group_keyboard,
    DateCallback,
    GroupCallback,
    TeacherCallback,
    MenuCallback
)
import logging
logger = logging.getLogger(__name__)

from premium_emoji import (
    te, strip_tg_emoji, PE_BOT, PE_CALENDAR, PE_BELL, PE_SEARCH, PE_PEOPLE, PE_INFO, PE_CHECK,
    PE_CLOCK, PE_HOUSE, PE_PERSON_CHECK, PE_TIME_PASSED, PE_STAR, PE_WARNING,
    PE_WRITE, PE_LINK, PE_REPEAT, PE_ARROW_LEFT, PE_CROSS
)

router = Router()


class BotStates(StatesGroup):
    waiting_for_group_search = State()
    waiting_for_teacher_search = State()


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


# ---------- Команды ----------

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Единственная нужная команда: дальше всё управление только кнопками."""
    await state.clear()
    user = await get_user(message.from_user.id)
    first_name = message.from_user.first_name or "студент"
    
    await safe_answer(
        message,
        build_welcome_text(user, first_name),
        reply_markup=get_main_keyboard()
    )
    await safe_answer(message, get_menu_text(user), reply_markup=get_main_menu_inline())


@router.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        f"{te(PE_INFO)} <b>Как пользоваться ботом:</b>\n\n"
        f"• {te(PE_CALENDAR)} <b>На сегодня / На завтра</b> — расписание твоей группы\n"
        f"• {te(PE_CLOCK)} <b>Выбрать дату</b> — расписание на любой день\n"
        f"• {te(PE_PEOPLE)} <b>Моя группа</b> — текущая группа, смена группы и уведомления\n\n"
        f"{te(PE_SEARCH)} <b>Быстрый поиск группы:</b> просто отправь в чат её номер или первые буквы (например: <code>ИС</code>, <code>253</code> или <code>АВ-261</code>)!\n\n"
        f"{te(PE_STAR)} <i>Подсказка: ты можешь нажать /start один раз и дальше переключаться кнопками меню!</i>"
    )
    await safe_answer(message, text, reply_markup=get_main_keyboard())


# ---------- Обработчики текстовых кнопок Reply-клавиатуры ----------

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
    notif_status_text = "Включены" if notifications_on else "Отключены"
    notif_icon = te(PE_BELL) if notifications_on else te(PE_CROSS)
    if user and user.get("group_name"):
        text = (
            f"{te(PE_PEOPLE)} <b>Твой профиль:</b>\n\n"
            f"{te(PE_CHECK)} Сохранённая группа: <b>{html.escape(user['group_name'])}</b>\n"
            f"{notif_icon} Уведомления о расписании: <b>{notif_status_text}</b>\n\n"
            "Чтобы сменить группу, нажми <b>«Сменить группу»</b> или просто отправь её номер в чат."
        )
    else:
        text = (
            f"{te(PE_INFO)} <b>Группа пока не выбрана!</b>\n\n"
            f"{notif_icon} Уведомления: <b>{notif_status_text}</b>\n\n"
            "Нажми <b>«Сменить группу»</b> ниже, чтобы выбрать курс кнопками."
        )
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
        try:
            await wait_msg.delete()
        except TelegramBadRequest:
            pass
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
        try:
            await wait_msg.delete()
        except TelegramBadRequest:
            pass
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
        text = get_menu_text(user)
        kb = get_main_menu_inline()
        await safe_edit_text(query.message, text, reply_markup=kb)

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
        notif_status_text = "Включены" if notifications_on else "Отключены"
        notif_icon = te(PE_BELL) if notifications_on else te(PE_CROSS)
        if user and user.get("group_name"):
            text = (
                f"{te(PE_PEOPLE)} <b>Твой профиль:</b>\n\n"
                f"{te(PE_CHECK)} Сохранённая группа: <b>{html.escape(user['group_name'])}</b>\n"
                f"{notif_icon} Уведомления о расписании: <b>{notif_status_text}</b>\n\n"
                "Чтобы сменить группу, нажми <b>«Сменить группу»</b> или просто напиши её номер в чат."
            )
        else:
            text = (
                f"{te(PE_INFO)} <b>Группа пока не выбрана!</b>\n\n"
                f"{notif_icon} Уведомления: <b>{notif_status_text}</b>\n\n"
                "Напиши в чат номер или первые буквы своей группы (например: <code>253</code> или <code>ИС</code>):"
            )
        await safe_edit_text(query.message, text, reply_markup=get_my_group_keyboard(notifications_on))

    elif action == "toggle_notify":
        new_state = await toggle_user_notifications(query.from_user.id)
        user = await get_user(query.from_user.id)
        notif_status_text = "Включены" if new_state else "Отключены"
        notif_icon = te(PE_BELL) if new_state else te(PE_CROSS)
        await safe_query_answer(query, f"Уведомления {notif_status_text.lower()}!")
        if user and user.get("group_name"):
            text = (
                f"{te(PE_PEOPLE)} <b>Твой профиль:</b>\n\n"
                f"{te(PE_CHECK)} Сохранённая группа: <b>{html.escape(user['group_name'])}</b>\n"
                f"{notif_icon} Уведомления о расписании: <b>{notif_status_text}</b>\n\n"
                "Чтобы сменить группу, нажми <b>«Сменить группу»</b> или просто напиши её номер в чат."
            )
        else:
            text = (
                f"{te(PE_INFO)} <b>Группа пока не выбрана!</b>\n\n"
                f"{notif_icon} Уведомления: <b>{notif_status_text}</b>\n\n"
                "Напиши в чат номер или первые буквы своей группы (например: <code>253</code> или <code>ИС</code>):"
            )
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
    
    if callback_data.action == "course":
        course_num = callback_data.course
        groups = await get_groups_by_course(course_num)
        if not groups:
            await safe_query_answer(query, f"Группы {course_num} курса не найдены.", show_alert=True)
            return
        kb = get_groups_search_inline_keyboard(groups, with_back_course=True)
        await safe_edit_text(
            query.message,
            f"{te(PE_INFO)} <b>Группы {course_num} курса ({len(groups)}):</b>\nВыбери свою группу кнопками:",
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
            try:
                await wait_msg.delete()
            except TelegramBadRequest:
                pass
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
        f"💡 <b>Подсказка:</b> чтобы найти группу, отправь в чат её номер или первые буквы (например: <code>ИС</code>, <code>253</code> или <code>АВ-261</code>).",
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
            try:
                await wait_msg.delete()
            except TelegramBadRequest:
                pass
        await safe_answer(message, text, reply_markup=kb)
        return

    kb = get_groups_search_inline_keyboard(groups)
    await safe_answer(
        message,
        f"{te(PE_PEOPLE)} <b>Найденные группы ({len(groups)}):</b>\nВыбери свою группу кнопками:",
        reply_markup=kb
    )
