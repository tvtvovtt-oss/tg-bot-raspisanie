from typing import List, Dict, Any, Optional
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.filters.callback_data import CallbackData


class DateCallback(CallbackData, prefix="dt"):
    action: str  # "pick", "nav"
    date: str
    target_type: str = "group"  # "group" or "teacher"
    target_id: str = ""


class GroupCallback(CallbackData, prefix="grp"):
    action: str  # "select", "page"
    group_id: str
    group_name: str
    page: int = 0


class TeacherCallback(CallbackData, prefix="tch"):
    action: str  # "select", "page"
    teacher_id: str
    teacher_name: str
    page: int = 0


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Main persistent reply keyboard for fast access."""
    kb = [
        [
            KeyboardButton(text="📅 На сегодня"),
            KeyboardButton(text="📆 На завтра")
        ],
        [
            KeyboardButton(text="🗓 Выбрать дату"),
            KeyboardButton(text="🔔 Звонки")
        ],
        [
            KeyboardButton(text="👥 Моя группа"),
            KeyboardButton(text="🔍 Найти группу")
        ],
        [
            KeyboardButton(text="👨‍🏫 Преподаватели")
        ]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def get_dates_inline_keyboard(
    dates: List[Dict[str, Any]],
    target_type: str = "group",
    target_id: str = ""
) -> InlineKeyboardMarkup:
    """Inline buttons with available dates."""
    buttons = []
    row = []
    for d in dates:
        dt = d["date"]
        label = d.get("day_name", "") or d.get("label", dt)
        if d.get("is_today"):
            label = f"📍 {label} (сегодня)"
        
        btn = InlineKeyboardButton(
            text=label,
            callback_data=DateCallback(
                action="pick",
                date=dt,
                target_type=target_type,
                target_id=target_id
            ).pack()
        )
        row.append(btn)
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_groups_search_inline_keyboard(
    groups: List[Dict[str, Any]],
    query: str = "",
    page: int = 0,
    per_page: int = 8
) -> InlineKeyboardMarkup:
    """Shows search results for groups with pagination."""
    total = len(groups)
    start = page * per_page
    end = start + per_page
    page_groups = groups[start:end]

    buttons = []
    # 2 buttons per row
    row = []
    for g in page_groups:
        btn = InlineKeyboardButton(
            text=f"👥 {g['name']}",
            callback_data=GroupCallback(
                action="select",
                group_id=str(g["id"]),
                group_name=g["name"],
                page=page
            ).pack()
        )
        row.append(btn)
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Navigation row
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=GroupCallback(
                action="page",
                group_id="",
                group_name="",
                page=page - 1
            ).pack()
        ))
    if end < total:
        nav_row.append(InlineKeyboardButton(
            text="Вперёд ➡️",
            callback_data=GroupCallback(
                action="page",
                group_id="",
                group_name="",
                page=page + 1
            ).pack()
        ))
    if nav_row:
        buttons.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_teachers_search_inline_keyboard(
    teachers: List[Dict[str, Any]],
    page: int = 0,
    per_page: int = 6
) -> InlineKeyboardMarkup:
    """Shows search results for teachers with pagination."""
    total = len(teachers)
    start = page * per_page
    end = start + per_page
    page_teachers = teachers[start:end]

    buttons = []
    for t in page_teachers:
        fio = t.get("short_fio") or t.get("fio")
        btn = InlineKeyboardButton(
            text=f"👨‍🏫 {fio}",
            callback_data=TeacherCallback(
                action="select",
                teacher_id=str(t["id"]),
                teacher_name=fio,
                page=page
            ).pack()
        )
        buttons.append([btn])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=TeacherCallback(
                action="page",
                teacher_id="",
                teacher_name="",
                page=page - 1
            ).pack()
        ))
    if end < total:
        nav_row.append(InlineKeyboardButton(
            text="Вперёд ➡️",
            callback_data=TeacherCallback(
                action="page",
                teacher_id="",
                teacher_name="",
                page=page + 1
            ).pack()
        ))
    if nav_row:
        buttons.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_schedule_nav_inline_keyboard(
    group_id: str,
    date_str: str,
    web_url: Optional[str] = None
) -> InlineKeyboardMarkup:
    """Buttons below schedule: Refresh, Choose date, Link to website."""
    buttons = [
        [
            InlineKeyboardButton(
                text="🔄 Обновить",
                callback_data=DateCallback(
                    action="pick",
                    date=date_str,
                    target_type="group",
                    target_id=group_id
                ).pack()
            ),
            InlineKeyboardButton(
                text="🗓 Другая дата",
                callback_data=DateCallback(
                    action="nav",
                    date="",
                    target_type="group",
                    target_id=group_id
                ).pack()
            )
        ]
    ]

    if web_url:
        buttons.append([
            InlineKeyboardButton(
                text="🌐 Открыть на сайте almetpt.ru",
                url=web_url
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_teacher_schedule_nav_inline_keyboard(
    teacher_id: str,
    date_str: str,
    web_url: Optional[str] = None
) -> InlineKeyboardMarkup:
    """Navigation buttons for teacher schedule."""
    buttons = [
        [
            InlineKeyboardButton(
                text="🔄 Обновить",
                callback_data=DateCallback(
                    action="pick",
                    date=date_str,
                    target_type="teacher",
                    target_id=teacher_id
                ).pack()
            ),
            InlineKeyboardButton(
                text="🗓 Другая дата",
                callback_data=DateCallback(
                    action="nav",
                    date="",
                    target_type="teacher",
                    target_id=teacher_id
                ).pack()
            )
        ]
    ]

    if web_url:
        buttons.append([
            InlineKeyboardButton(
                text="🌐 Открыть на сайте almetpt.ru",
                url=web_url
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)
