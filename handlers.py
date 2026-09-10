from datetime import datetime, timedelta
import html
from typing import Optional

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import get_user, set_user_group, set_user_teacher
from parser import (
    get_available_dates,
    get_groups,
    get_groups_by_course,
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
    get_course_selection_keyboard,
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
        "Я официальный бот по расписанию <b>Альметьевского политехнического техникума</b> (almetpt.ru).\n\n"
    )

    if user and user.get("group_name"):
        welcome_text += (
            f"📌 Твоя сохранённая группа: <b>{html.escape(user['group_name'])}</b>\n\n"
            "Выбирай нужное действие в меню ниже 👇"
        )
    else:
        welcome_text += (
            "⚠️ <b>Группа ещё не выбрана.</b>\n"
            "Напиши номер своей группы в чат (например: <code>АВ-261</code> или <code>БУР-261</code>), "
            "или нажми <b>«🔍 Найти группу»</b>."
        )

    await message.answer(welcome_text, reply_markup=get_main_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "📖 <b>Как пользоваться ботом:</b>\n\n"
        "• <b>📅 На сегодня</b> — расписание твоей группы на сегодня\n"
        "• <b>📆 На завтра</b> — расписание твоей группы на следующий учебный день\n"
        "• <b>🗓 Выбрать дату</b> — расписание на любой доступный день недели\n"
        "• <b>🔔 Звонки</b> — график звонков пар и перемен техникума\n"
        "• <b>👥 Моя группа</b> — посмотреть или изменить сохранённую группу\n"
        "• <b>🔍 Найти группу</b> — поиск любой группы по названию или курсу\n"
        "• <b>👨‍🏫 Преподаватели</b> — расписание преподавателя по фамилии\n\n"
        "💡 <i>Подсказка: ты можешь просто отправить боту номер группы в любой момент, например:</i> <code>261</code> или <code>АВ-261</code>"
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
            f"👥 Сохранённая группа: <b>{html.escape(user['group_name'])}</b>\n\n"
            "Чтобы сменить группу, отправь её название в чат или нажми <b>«🔍 Найти группу»</b>."
        )
    else:
        text = (
            "ℹ️ <b>Группа пока не выбрана!</b>\n\n"
            "Напиши название своей группы (например: <code>АВ-261</code>) или нажми <b>«🔍 Найти группу»</b>."
        )
    await message.answer(text, reply_markup=get_main_keyboard())


@router.message(F.text == "🔍 Найти группу")
@router.message(Command("search"))
async def cmd_search_group(message: Message, state: FSMContext):
    await state.set_state(BotStates.waiting_for_group_search)
    kb = get_course_selection_keyboard()
    await message.answer(
        "🔎 Введи номер группы (например: <code>АВ-261</code>, <code>261</code>, <code>БУР</code>)\n"
        "или выбери курс ниже:",
        reply_markup=kb
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

    wait_msg = await message.answer("⏳ <i>Загружаю расписание с almetpt.ru...</i>")
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
    
    # Smart next day detection:
    # 1. Check if dates_info has a date after today
    tomorrow_str = ""
    dates_list = dates_info.get("dates", [])
    found_today = False
    for d in dates_list:
        if d["date"] == today_str:
            found_today = True
            continue
        if found_today:
            tomorrow_str = d["date"]
            break
            
    # 2. If not found in published list, calculate next calendar day (skip Sunday)
    if not tomorrow_str:
        try:
            curr = datetime.strptime(today_str, "%Y-%m-%d")
            next_day = curr + timedelta(days=1)
            if next_day.weekday() == 6:  # Sunday
                next_day += timedelta(days=1)
            tomorrow_str = next_day.strftime("%Y-%m-%d")
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
    """Fallback handler: if user directly enters group name in chat."""
    text = message.text.strip()
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

    kb = get_groups_search_inline_keyboard(groups)
    await message.answer(
        f"🔍 <b>Найдено групп: {len(groups)}</b>\nВыбери свою группу:",
        reply_markup=kb
    )


# --- Callback Handlers ---

@router.callback_query(GroupCallback.filter())
async def cb_group_handler(query: CallbackQuery, callback_data: GroupCallback):
    await query.answer()
    
    if callback_data.action == "course":
        course_num = callback_data.course
        groups = await get_groups_by_course(course_num)
        if not groups:
            await query.message.answer(f"Группы для {course_num} курса не найдены.")
            return
        kb = get_groups_search_inline_keyboard(groups)
        await query.message.edit_text(
            f"🎓 <b>Группы {course_num} курса ({len(groups)}):</b>\nВыбери свою группу:",
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
        
        try:
            await query.message.edit_text(f"⏳ <i>Загружаю расписание группы {html.escape(g_name)}...</i>")
        except TelegramBadRequest:
            pass

        sched = await get_group_schedule(g_id, today_str)
        text = format_schedule_message(sched, g_name, today_str, "Сегодня")
        web_url = sched.get("url")
        kb = get_schedule_nav_inline_keyboard(g_id, today_str, web_url)
        
        try:
            await query.message.edit_text(text, reply_markup=kb)
        except TelegramBadRequest:
            pass


@router.callback_query(DateCallback.filter())
async def cb_date_handler(query: CallbackQuery, callback_data: DateCallback):
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
            await query.answer("⚠️ Сначала выбери группу в меню.", show_alert=True)
            return

    if action == "nav":
        dates_info = await get_available_dates()
        dates_list = dates_info.get("dates", [])
        kb = get_dates_inline_keyboard(dates_list, target_type=target_type, target_id=target_id)
        try:
            await query.message.edit_reply_markup(reply_markup=kb)
            await query.answer()
        except TelegramBadRequest:
            await query.answer()
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
            try:
                await query.message.edit_text(text, reply_markup=kb)
                await query.answer("Расписание обновлено!")
            except TelegramBadRequest:
                await query.answer("Расписание актуально, изменений нет.")
        else:
            all_groups = await get_groups()
            g_info = all_groups.get(target_id, {})
            g_name = g_info.get("name", "Группа")
            
            sched = await get_group_schedule(target_id, date_str)
            text = format_schedule_message(sched, g_name, date_str)
            web_url = sched.get("url")
            kb = get_schedule_nav_inline_keyboard(target_id, date_str, web_url)
            try:
                await query.message.edit_text(text, reply_markup=kb)
                await query.answer("Расписание обновлено!")
            except TelegramBadRequest:
                await query.answer("Расписание актуально, изменений нет.")


@router.callback_query(TeacherCallback.filter())
async def cb_teacher_handler(query: CallbackQuery, callback_data: TeacherCallback):
    if callback_data.action == "select":
        t_id = callback_data.teacher_id
        all_staff = await get_staffs()
        t_info = all_staff.get(t_id, {})
        t_name = t_info.get("short_fio") or t_info.get("fio", "Преподаватель")
        
        await set_user_teacher(query.from_user.id, t_id, t_name)
        
        dates_info = await get_available_dates()
        today_str = dates_info.get("today") or datetime.now().strftime("%Y-%m-%d")
        
        try:
            await query.message.edit_text(f"⏳ <i>Загружаю расписание {html.escape(t_name)}...</i>")
        except TelegramBadRequest:
            pass

        sched = await get_teacher_schedule(t_id, today_str)
        text = format_teacher_schedule_message(sched, t_name, today_str)
        web_url = sched.get("url")
        kb = get_teacher_schedule_nav_inline_keyboard(t_id, today_str, web_url)
        
        try:
            await query.message.edit_text(text, reply_markup=kb)
            await query.answer()
        except TelegramBadRequest:
            await query.answer()
