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
    action: str  # "select", "course"
    group_id: str = ""
    course: int = 0


class TeacherCallback(CallbackData, prefix="tch"):
    action: str  # "select"
    teacher_id: str = ""


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
    groups: List[Dict[str, Any]]
) -> InlineKeyboardMarkup:
    """Shows search results for groups (max 10 buttons, 2 per row)."""
    buttons = []
    row = []
    for g in groups[:10]:
        btn = InlineKeyboardButton(
            text=f"👥 {g['name']}",
            callback_data=GroupCallback(
                action="select",
                group_id=str(g["id"])
            ).pack()
        )
        row.append(btn)
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_course_selection_keyboard() -> InlineKeyboardMarkup:
    """Keyboard to choose course: 1, 2, 3, 4 курс."""
    buttons = [
        [
            InlineKeyboardButton(text="1️⃣ 1 курс", callback_data=GroupCallback(action="course", course=1).pack()),
            InlineKeyboardButton(text="2️⃣ 2 курс", callback_data=GroupCallback(action="course", course=2).pack())
        ],
        [
            InlineKeyboardButton(text="3️⃣ 3 курс", callback_data=GroupCallback(action="course", course=3).pack()),
            InlineKeyboardButton(text="4️⃣ 4 курс", callback_data=GroupCallback(action="course", course=4).pack())
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_teachers_search_inline_keyboard(
    teachers: List[Dict[str, Any]]
) -> InlineKeyboardMarkup:
    """Shows search results for teachers."""
    buttons = []
    for t in teachers[:10]:
        fio = t.get("short_fio") or t.get("fio")
        btn = InlineKeyboardButton(
            text=f"👨‍🏫 {fio}",
            callback_data=TeacherCallback(
                action="select",
                teacher_id=str(t["id"])
            ).pack()
        )
        buttons.append([btn])

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
