from datetime import datetime, timedelta
import html
from typing import Optional

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import get_user, set_user_group, set_user_teacher
from parser import (
    get_available_dates,
    get_groups,
    search_groups,
    get_staffs,
    search_teachers,
    get_group_schedule,
    get_teacher_schedule,
    format_schedule_message,
    format_teacher_schedule_message,
    get_calls_text
)
from keyboards import (
    get_main_keyboard,
    get_dates_inline_keyboard,
    get_groups_search_inline_keyboard,
    get_teachers_search_inline_keyboard,
    get_schedule_nav_inline_keyboard,
    get_teacher_schedule_nav_inline_keyboard,
    DateCallback,
    GroupCallback,
    TeacherCallback
)

router = Router()


class BotStates(StatesGroup):
    waiting_for_group_search = State()
    waiting_for_teacher_search = State()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = await get_user(message.from_user.id)
    first_name = message.from_user.first_name or "студент"
    
    welcome_text = (
        f"👋 <b>Привет, {html.escape(first_name)}!</b>\n\n"
        "Я официальный бот-помощник по расписанию <b>Альметьевского политехнического техникума</b> (almetpt.ru).\n\n"
    )

    if user and user.get("group_name"):
        welcome_text += (
            f"📌 Твоя выбранная группа: <b>{html.escape(user['group_name'])}</b>\n\n"
            "Выбирай нужное действие в меню ниже 👇"
        )
    else:
        welcome_text += (
            "⚠️ <b>Группа ещё не выбрана.</b>\n"
            "Напиши номер своей группы (например, <code>АВ-261</code> или <code>БУР-261</code>), "
            "или нажми <b>«🔍 Найти группу»</b>."
        )

    await message.answer(welcome_text, reply_markup=get_main_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "📖 <b>Как пользоваться ботом:</b>\n\n"
        "• <b>📅 На сегодня</b> — расписание твоей группы на текущий день\n"
        "• <b>📆 На завтра</b> — расписание твоей группы на следующий день\n"
        "• <b>🗓 Выбрать дату</b> — расписание на любой день недели\n"
        "• <b>🔔 Звонки</b> — график и звонки пар\n"
        "• <b>👥 Моя группа</b> — посмотреть или изменить сохранённую группу\n"
        "• <b>🔍 Найти группу</b> — поиск расписания любой группы техникума\n"
        "• <b>👨‍🏫 Преподаватели</b> — поиск расписания преподавателя по фамилии\n\n"
        "💡 <i>Ты также можешь просто отправить боту название группы в любой момент, например:</i> <code>АВ-261</code>"
    )
    await message.answer(text, reply_markup=get_main_keyboard())


@router.message(F.text == "🔔 Звонки")
@router.message(Command("calls"))
async def cmd_calls(message: Message):
    await message.answer(get_calls_text(), reply_markup=get_main_keyboard())


@router.message(F.text == "👥 Моя группа")
@router.message(Command("mygroup"))
async def cmd_my_group(message: Message, state: FSMContext):
    await state.clear()
    user = await get_user(message.from_user.id)
    if user and user.get("group_name"):
        text = (
            f"👤 <b>Твой профиль:</b>\n\n"
            f"👥 Выбранная группа: <b>{html.escape(user['group_name'])}</b>\n"
            f"🆔 ID группы: <code>{user.get('group_id')}</code>\n\n"
            "Чтобы сменить группу, просто отправь её название сообщением или нажми <b>«🔍 Найти группу»</b>."
        )
    else:
        text = (
            "ℹ️ <b>Группа не сохранена!</b>\n\n"
            "Напиши название группы в чат (например: <code>АВ-261</code>) или нажми кнопку <b>«🔍 Найти группу»</b>."
        )
    await message.answer(text, reply_markup=get_main_keyboard())


@router.message(F.text == "🔍 Найти группу")
@router.message(Command("search"))
async def cmd_search_group(message: Message, state: FSMContext):
    await state.set_state(BotStates.waiting_for_group_search)
    await message.answer(
        "🔎 Введи название группы (например: <code>АВ-261</code>, <code>261</code> или <code>БУР</code>):",
        reply_markup=get_main_keyboard()
    )


@router.message(F.text == "👨‍🏫 Преподаватели")
@router.message(Command("teachers"))
async def cmd_search_teacher(message: Message, state: FSMContext):
    await state.set_state(BotStates.waiting_for_teacher_search)
    await message.answer(
        "👨‍🏫 Введи фамилию преподавателя (например: <code>Агеева</code>, <code>Багманов</code> или <code>Почикян</code>):",
        reply_markup=get_main_keyboard()
    )


@router.message(F.text == "📅 На сегодня")
@router.message(Command("today"))
async def cmd_today(message: Message):
    user = await get_user(message.from_user.id)
    if not user or not user.get("group_id"):
        await message.answer(
            "⚠️ Сначала выбери свою группу! Напиши её название (например, <code>АВ-261</code>) "
            "или нажми <b>«🔍 Найти группу»</b>.",
            reply_markup=get_main_keyboard()
        )
        return

    dates_info = await get_available_dates()
    today_str = dates_info.get("today") or datetime.now().strftime("%Y-%m-%d")

    wait_msg = await message.answer("⏳ <i>Загружаю расписание с сайта almetpt.ru...</i>")
    sched = await get_group_schedule(user["group_id"], today_str)
    
    text = format_schedule_message(sched, user["group_name"], today_str, "Сегодня")
    web_url = sched.get("url")
    kb = get_schedule_nav_inline_keyboard(user["group_id"], today_str, web_url)
    
    await wait_msg.delete()
    await message.answer(text, reply_markup=kb)


@router.message(F.text == "📆 На завтра")
@router.message(Command("tomorrow"))
async def cmd_tomorrow(message: Message):
    user = await get_user(message.from_user.id)
    if not user or not user.get("group_id"):
        await message.answer(
            "⚠️ Сначала выбери свою группу! Напиши её название (например, <code>АВ-261</code>).",
            reply_markup=get_main_keyboard()
        )
        return

    dates_info = await get_available_dates()
    today_str = dates_info.get("today") or datetime.now().strftime("%Y-%m-%d")
    
    # Calculate tomorrow or next available date
    try:
        dt = datetime.strptime(today_str, "%Y-%m-%d") + timedelta(days=1)
        tomorrow_str = dt.strftime("%Y-%m-%d")
    except Exception:
        tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    wait_msg = await message.answer("⏳ <i>Загружаю расписание на завтра...</i>")
    sched = await get_group_schedule(user["group_id"], tomorrow_str)
    
    text = format_schedule_message(sched, user["group_name"], tomorrow_str, "Завтра")
    web_url = sched.get("url")
    kb = get_schedule_nav_inline_keyboard(user["group_id"], tomorrow_str, web_url)
    
    await wait_msg.delete()
    await message.answer(text, reply_markup=kb)


@router.message(F.text == "🗓 Выбрать дату")
@router.message(Command("dates"))
async def cmd_choose_date(message: Message):
    user = await get_user(message.from_user.id)
    group_id = user["group_id"] if user and user.get("group_id") else ""
    
    dates_info = await get_available_dates()
    dates_list = dates_info.get("dates", [])
    
    if not dates_list:
        await message.answer("⚠️ Не удалось получить список дат с сайта.")
        return

    kb = get_dates_inline_keyboard(dates_list, target_type="group", target_id=group_id)
    await message.answer("🗓 <b>Выбери дату для просмотра расписания:</b>", reply_markup=kb)


# --- Handle Search Queries (Group & Teacher) ---

@router.message(BotStates.waiting_for_group_search)
async def process_group_search_state(message: Message, state: FSMContext):
    await state.clear()
    await handle_group_search_query(message, message.text.strip())


@router.message(BotStates.waiting_for_teacher_search)
async def process_teacher_search_state(message: Message, state: FSMContext):
    await state.clear()
    query = message.text.strip()
    teachers = await search_teachers(query)
    if not teachers:
        await message.answer(
            f"❌ Преподаватели по запросу «<b>{html.escape(query)}</b>» не найдены.\n"
            "Попробуй ввести только фамилию (например, <code>Агеева</code>).",
            reply_markup=get_main_keyboard()
        )
        return

    kb = get_teachers_search_inline_keyboard(teachers)
    await message.answer(
        f"👨‍🏫 <b>Найденные преподаватели ({len(teachers)}):</b>\nВыбери из списка:",
        reply_markup=kb
    )


@router.message(F.text)
async def process_any_text(message: Message, state: FSMContext):
    """Fallback text handler: if user enters group name directly in chat."""
    text = message.text.strip()
    # If text is not a command and looks like a group search (short string with letters or numbers)
    if len(text) <= 25:
        groups = await search_groups(text)
        if groups:
            await handle_group_search_query(message, text, preloaded_groups=groups)
            return

    await message.answer(
        "🤔 Я не совсем понял команду.\n"
        "Воспользуйся кнопками меню ниже 👇 или отправь номер группы для поиска.",
        reply_markup=get_main_keyboard()
    )


async def handle_group_search_query(message: Message, query: str, preloaded_groups=None):
    groups = preloaded_groups if preloaded_groups is not None else await search_groups(query)
    
    if not groups:
        await message.answer(
            f"❌ Группы по запросу «<b>{html.escape(query)}</b>» не найдены.\n"
            "Пример правильного названия: <code>АВ-261</code>, <code>БУР-261</code>, <code>261</code>.",
            reply_markup=get_main_keyboard()
        )
        return

    if len(groups) == 1:
        # Exactly one group found
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

        wait_msg = await message.answer(f"✅ Выбрана группа <b>{html.escape(g['name'])}</b>!\nЗагружаю расписание...")
        sched = await get_group_schedule(str(g["id"]), today_str)
        text = format_schedule_message(sched, g["name"], today_str, "Сегодня")
        web_url = sched.get("url")
        kb = get_schedule_nav_inline_keyboard(str(g["id"]), today_str, web_url)
        
        await wait_msg.delete()
        await message.answer(text, reply_markup=kb)
        return

    # Multiple groups found
    kb = get_groups_search_inline_keyboard(groups, query=query)
    await message.answer(
        f"🔍 <b>Найдено групп: {len(groups)}</b>\nВыбери свою группу:",
        reply_markup=kb
    )


# --- Callback Handlers ---

@router.callback_query(GroupCallback.filter())
async def cb_group_handler(query: CallbackQuery, callback_data: GroupCallback):
    await query.answer()
    
    if callback_data.action == "select":
        g_id = callback_data.group_id
        g_name = callback_data.group_name
        
        await set_user_group(
            user_id=query.from_user.id,
            group_id=g_id,
            group_name=g_name,
            username=query.from_user.username,
            first_name=query.from_user.first_name
        )
        
        dates_info = await get_available_dates()
        today_str = dates_info.get("today") or datetime.now().strftime("%Y-%m-%d")
        
        await query.message.edit_text(f"⏳ <i>Загружаю расписание группы {html.escape(g_name)}...</i>")
        sched = await get_group_schedule(g_id, today_str)
        
        text = format_schedule_message(sched, g_name, today_str, "Сегодня")
        web_url = sched.get("url")
        kb = get_schedule_nav_inline_keyboard(g_id, today_str, web_url)
        
        await query.message.edit_text(text, reply_markup=kb)

    elif callback_data.action == "page":
        # Paginate
        groups = list((await get_groups()).values())
        kb = get_groups_search_inline_keyboard(groups, page=callback_data.page)
        await query.message.edit_reply_markup(reply_markup=kb)


@router.callback_query(DateCallback.filter())
async def cb_date_handler(query: CallbackQuery, callback_data: DateCallback):
    await query.answer()
    action = callback_data.action
    target_type = callback_data.target_type
    target_id = callback_data.target_id
    date_str = callback_data.date

    # If target_id is empty, check user's saved group
    if not target_id:
        user = await get_user(query.from_user.id)
        if user and user.get("group_id"):
            target_id = user["group_id"]
        else:
            await query.message.answer("⚠️ Сначала выбери группу в меню.")
            return

    if action == "nav":
        # User wants to choose another date
        dates_info = await get_available_dates()
        dates_list = dates_info.get("dates", [])
        kb = get_dates_inline_keyboard(dates_list, target_type=target_type, target_id=target_id)
        await query.message.edit_reply_markup(reply_markup=kb)
        return

    if action == "pick":
        # User picked a specific date
        if target_type == "teacher":
            all_staff = await get_staffs()
            t_info = all_staff.get(target_id, {})
            t_name = t_info.get("short_fio") or t_info.get("fio", "Преподаватель")
            
            await query.message.edit_text(f"⏳ <i>Загружаю расписание {html.escape(t_name)} на {date_str}...</i>")
            sched = await get_teacher_schedule(target_id, date_str)
            text = format_teacher_schedule_message(sched, t_name, date_str)
            web_url = sched.get("url")
            kb = get_teacher_schedule_nav_inline_keyboard(target_id, date_str, web_url)
            await query.message.edit_text(text, reply_markup=kb)
        else:
            all_groups = await get_groups()
            g_info = all_groups.get(target_id, {})
            g_name = g_info.get("name", "Группа")
            
            await query.message.edit_text(f"⏳ <i>Загружаю расписание группы {html.escape(g_name)} на {date_str}...</i>")
            sched = await get_group_schedule(target_id, date_str)
            text = format_schedule_message(sched, g_name, date_str)
            web_url = sched.get("url")
            kb = get_schedule_nav_inline_keyboard(target_id, date_str, web_url)
            await query.message.edit_text(text, reply_markup=kb)


@router.callback_query(TeacherCallback.filter())
async def cb_teacher_handler(query: CallbackQuery, callback_data: TeacherCallback):
    await query.answer()
    
    if callback_data.action == "select":
        t_id = callback_data.teacher_id
        t_name = callback_data.teacher_name
        
        await set_user_teacher(query.from_user.id, t_id, t_name)
        
        dates_info = await get_available_dates()
        today_str = dates_info.get("today") or datetime.now().strftime("%Y-%m-%d")
        
        await query.message.edit_text(f"⏳ <i>Загружаю расписание преподавателя {html.escape(t_name)}...</i>")
        sched = await get_teacher_schedule(t_id, today_str)
        
        text = format_teacher_schedule_message(sched, t_name, today_str)
        web_url = sched.get("url")
        kb = get_teacher_schedule_nav_inline_keyboard(t_id, today_str, web_url)
        
        await query.message.edit_text(text, reply_markup=kb)

    elif callback_data.action == "page":
        all_teachers = list((await get_staffs()).values())
        teachers = [t for t in all_teachers if t.get("is_teacher", 1)]
        kb = get_teachers_search_inline_keyboard(teachers, page=callback_data.page)
        await query.message.edit_reply_markup(reply_markup=kb)
