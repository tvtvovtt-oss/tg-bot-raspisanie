from typing import List, Dict, Any, Optional
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.filters.callback_data import CallbackData

from premium_emoji import (
    PE_CALENDAR, PE_TIME_PASSED, PE_BELL, PE_PEOPLE, PE_SEARCH,
    PE_HOUSE, PE_ARROW_LEFT, PE_REPEAT, PE_LINK,
    PE_PERSON_CHECK, PE_CLOCK, PE_INFO, PE_CHECK
)


# ---------- Callback-данные ----------

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
    action: str  # "select", "letter"
    teacher_id: str = ""  # ID преподавателя ИЛИ буква алфавита


class MenuCallback(CallbackData, prefix="menu"):
    action: str  # "home", "today", "tomorrow", "dates", "calls", "mygroup", "teachers", "groups"


# ---------- Reply-клавиатура (только премиум-иконки, чистый текст без дефолт-эмодзи) ----------

def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Главная reply-клавиатура: текст без дефолтных эмодзи, только премиум-иконки слева."""
    kb = [
        [
            KeyboardButton(text="На сегодня", icon_custom_emoji_id=PE_CALENDAR),
            KeyboardButton(text="На завтра", icon_custom_emoji_id=PE_TIME_PASSED)
        ],
        [
            KeyboardButton(text="Выбрать дату", icon_custom_emoji_id=PE_CLOCK),
            KeyboardButton(text="Звонки", icon_custom_emoji_id=PE_BELL)
        ],
        [
            KeyboardButton(text="Моя группа", icon_custom_emoji_id=PE_PEOPLE),
            KeyboardButton(text="Найти группу", icon_custom_emoji_id=PE_SEARCH)
        ],
        [
            KeyboardButton(text="Преподаватели", icon_custom_emoji_id=PE_PERSON_CHECK)
        ]
    ]
    return ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
        input_field_placeholder="Выбирай действие кнопками"
    )


# ---------- Общие вспомогательные кнопки ----------

def get_home_button_row() -> List[InlineKeyboardButton]:
    """Строка с кнопкой «Главное меню» (только премиум-иконка)."""
    return [
        InlineKeyboardButton(
            text="Главное меню",
            icon_custom_emoji_id=PE_HOUSE,
            callback_data=MenuCallback(action="home").pack()
        )
    ]


# ---------- Inline: главное интерактивное меню ----------

def get_main_menu_inline() -> InlineKeyboardMarkup:
    """Инлайн-меню: чистый текст с премиум-иконками без дефолтных эмодзи."""
    rows = [
        [
            InlineKeyboardButton(
                text="Расписание на сегодня",
                icon_custom_emoji_id=PE_CALENDAR,
                callback_data=MenuCallback(action="today").pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="Расписание на завтра",
                icon_custom_emoji_id=PE_TIME_PASSED,
                callback_data=MenuCallback(action="tomorrow").pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="Выбрать дату",
                icon_custom_emoji_id=PE_CLOCK,
                callback_data=MenuCallback(action="dates").pack()
            ),
            InlineKeyboardButton(
                text="Звонки",
                icon_custom_emoji_id=PE_BELL,
                callback_data=MenuCallback(action="calls").pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="Моя группа",
                icon_custom_emoji_id=PE_PEOPLE,
                callback_data=MenuCallback(action="mygroup").pack()
            ),
            InlineKeyboardButton(
                text="Найти группу",
                icon_custom_emoji_id=PE_SEARCH,
                callback_data=MenuCallback(action="groups").pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="Преподаватели",
                icon_custom_emoji_id=PE_PERSON_CHECK,
                callback_data=MenuCallback(action="teachers").pack()
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------- Inline: выбор даты ----------

def get_dates_inline_keyboard(
    dates: List[Dict[str, Any]],
    target_type: str = "group",
    target_id: str = ""
) -> InlineKeyboardMarkup:
    """Inline-кнопки с доступными датами + кнопка возврата в меню."""
    buttons: List[List[InlineKeyboardButton]] = []
    row: List[InlineKeyboardButton] = []
    for d in dates:
        dt = d["date"]
        label = d.get("day_name", "") or d.get("label", dt)
        
        btn = InlineKeyboardButton(
            text=label,
            icon_custom_emoji_id=PE_CALENDAR,
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

    buttons.append(get_home_button_row())
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ---------- Inline: группы и курсы ----------

def get_course_selection_keyboard() -> InlineKeyboardMarkup:
    """Выбор курса чисто кнопками: 1–4 курс (без дефолтных эмодзи) + назад в меню."""
    buttons = [
        [
            InlineKeyboardButton(text="1 курс", icon_custom_emoji_id=PE_SEARCH, callback_data=GroupCallback(action="course", course=1).pack()),
            InlineKeyboardButton(text="2 курс", icon_custom_emoji_id=PE_SEARCH, callback_data=GroupCallback(action="course", course=2).pack())
        ],
        [
            InlineKeyboardButton(text="3 курс", icon_custom_emoji_id=PE_SEARCH, callback_data=GroupCallback(action="course", course=3).pack()),
            InlineKeyboardButton(text="4 курс", icon_custom_emoji_id=PE_SEARCH, callback_data=GroupCallback(action="course", course=4).pack())
        ],
        get_home_button_row()
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_groups_search_inline_keyboard(groups: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """Список найденных групп / групп курса с премиум-иконками."""
    buttons: List[List[InlineKeyboardButton]] = []
    for g in groups[:20]:
        name = g.get("out_name") or g.get("name")
        buttons.append([
            InlineKeyboardButton(
                text=name,
                icon_custom_emoji_id=PE_PEOPLE,
                callback_data=GroupCallback(action="select", group_id=str(g["id"])).pack()
            )
        ])
    buttons.append([
        InlineKeyboardButton(
            text="К выбору курса",
            icon_custom_emoji_id=PE_ARROW_LEFT,
            callback_data=MenuCallback(action="groups").pack()
        )
    ])
    buttons.append(get_home_button_row())
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ---------- Inline: преподаватели (алфавит и списки) ----------

def get_teachers_letters_keyboard(letters: List[str]) -> InlineKeyboardMarkup:
    """Алфавит фамилий преподавателей — выбор чисто кнопками."""
    buttons: List[List[InlineKeyboardButton]] = []
    row: List[InlineKeyboardButton] = []
    for letter in letters:
        row.append(InlineKeyboardButton(
            text=letter,
            icon_custom_emoji_id=PE_PERSON_CHECK,
            callback_data=TeacherCallback(action="letter", teacher_id=letter).pack()
        ))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append(get_home_button_row())
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_teachers_search_inline_keyboard(
    teachers: List[Dict[str, Any]],
    with_back: bool = True
) -> InlineKeyboardMarkup:
    """Список преподавателей с премиум-иконками (без дефолт-эмодзи в тексте)."""
    buttons: List[List[InlineKeyboardButton]] = []
    for t in teachers[:25]:
        fio = t.get("short_fio") or t.get("fio")
        buttons.append([
            InlineKeyboardButton(
                text=fio,
                icon_custom_emoji_id=PE_PERSON_CHECK,
                callback_data=TeacherCallback(
                    action="select",
                    teacher_id=str(t["id"])
                ).pack()
            )
        ])
    if with_back:
        buttons.append([
            InlineKeyboardButton(
                text="К алфавиту",
                icon_custom_emoji_id=PE_ARROW_LEFT,
                callback_data=MenuCallback(action="teachers").pack()
            )
        ])
    buttons.append(get_home_button_row())
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ---------- Inline: навигация под расписанием ----------

def get_schedule_nav_inline_keyboard(
    group_id: str,
    date_str: str,
    web_url: Optional[str] = None
) -> InlineKeyboardMarkup:
    """Кнопки под расписанием: обновить, дата, на завтра, меню, сайт."""
    buttons = [
        [
            InlineKeyboardButton(
                text="Обновить",
                icon_custom_emoji_id=PE_REPEAT,
                callback_data=DateCallback(
                    action="pick",
                    date=date_str,
                    target_type="group",
                    target_id=group_id
                ).pack()
            ),
            InlineKeyboardButton(
                text="Другая дата",
                icon_custom_emoji_id=PE_CLOCK,
                callback_data=DateCallback(
                    action="nav",
                    date="",
                    target_type="group",
                    target_id=group_id
                ).pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="На завтра",
                icon_custom_emoji_id=PE_TIME_PASSED,
                callback_data=MenuCallback(action="tomorrow").pack()
            ),
            InlineKeyboardButton(
                text="Главное меню",
                icon_custom_emoji_id=PE_HOUSE,
                callback_data=MenuCallback(action="home").pack()
            )
        ]
    ]

    if web_url:
        buttons.append([
            InlineKeyboardButton(
                text="Открыть на almetpt.ru",
                icon_custom_emoji_id=PE_LINK,
                url=web_url
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_teacher_schedule_nav_inline_keyboard(
    teacher_id: str,
    date_str: str,
    web_url: Optional[str] = None
) -> InlineKeyboardMarkup:
    """Навигация под расписанием преподавателя."""
    buttons = [
        [
            InlineKeyboardButton(
                text="Обновить",
                icon_custom_emoji_id=PE_REPEAT,
                callback_data=DateCallback(
                    action="pick",
                    date=date_str,
                    target_type="teacher",
                    target_id=teacher_id
                ).pack()
            ),
            InlineKeyboardButton(
                text="Другая дата",
                icon_custom_emoji_id=PE_CLOCK,
                callback_data=DateCallback(
                    action="nav",
                    date="",
                    target_type="teacher",
                    target_id=teacher_id
                ).pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="К преподавателям",
                icon_custom_emoji_id=PE_PERSON_CHECK,
                callback_data=MenuCallback(action="teachers").pack()
            ),
            InlineKeyboardButton(
                text="Главное меню",
                icon_custom_emoji_id=PE_HOUSE,
                callback_data=MenuCallback(action="home").pack()
            )
        ]
    ]

    if web_url:
        buttons.append([
            InlineKeyboardButton(
                text="Открыть на almetpt.ru",
                icon_custom_emoji_id=PE_LINK,
                url=web_url
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_calls_keyboard() -> InlineKeyboardMarkup:
    """Кнопки под расписанием звонков."""
    return InlineKeyboardMarkup(inline_keyboard=[get_home_button_row()])


def get_my_group_keyboard(notifications_enabled: bool = True) -> InlineKeyboardMarkup:
    """Кнопки под профилем группы с возможностью включения/отключения уведомлений."""
    notify_text = "Уведомления: Вкл" if notifications_enabled else "Уведомления: Выкл"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=notify_text,
                icon_custom_emoji_id=PE_BELL,
                callback_data=MenuCallback(action="toggle_notify").pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="Сменить группу",
                icon_custom_emoji_id=PE_SEARCH,
                callback_data=MenuCallback(action="groups").pack()
            )
        ],
        get_home_button_row()
    ])
