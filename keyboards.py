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
    PE_PERSON_CHECK, PE_CLOCK, PE_INFO, PE_CHECK,
    PE_SETTINGS, PE_LOCK_CLOSED, PE_LOCK_OPEN, PE_CHART_STATS,
    PE_MEGAPHONE, PE_CROSS
)


# ---------- Callback-данные ----------

class DateCallback(CallbackData, prefix="dt"):
    action: str  # "pick", "nav"
    date: str
    target_type: str = "group"  # "group" or "teacher"
    target_id: str = ""


class GroupCallback(CallbackData, prefix="grp"):
    action: str  # "select", "course", "zaochn_menu", "zaochn_all"
    group_id: str = ""
    course: int = 0
    form: str = "fulltime"


class TeacherCallback(CallbackData, prefix="tch"):
    action: str  # "select", "letter"
    teacher_id: str = ""  # ID преподавателя ИЛИ буква алфавита


class MenuCallback(CallbackData, prefix="menu"):
    action: str  # "home", "today", "tomorrow", "dates", "calls", "mygroup", "teachers", "groups", "admin"


class AdminCallback(CallbackData, prefix="adm"):
    action: str  # "toggle_maint", "stats", "refresh_cache", "broadcast", "confirm_bc", "cancel_bc", "close", "panel"


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
            KeyboardButton(text="Моя группа", icon_custom_emoji_id=PE_PEOPLE)
        ]
    ]
    return ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
        input_field_placeholder="Напиши номер группы или выбери действие"
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

def get_main_menu_inline(is_admin_user: bool = False) -> InlineKeyboardMarkup:
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
                text="Моя группа",
                icon_custom_emoji_id=PE_PEOPLE,
                callback_data=MenuCallback(action="mygroup").pack()
            )
        ]
    ]
    if is_admin_user:
        rows.append([
            InlineKeyboardButton(
                text="Панель администратора",
                icon_custom_emoji_id=PE_SETTINGS,
                callback_data=MenuCallback(action="admin").pack()
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------- Inline: выбор даты ----------

WEEKDAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def format_date_button_label(dt_str: str, today_str: Optional[str] = None) -> str:
    """
    Генерирует понятный текст кнопки с днем недели и датой.
    Например:
    - 'Сегодня (10.09)'
    - 'Завтра (11.09)'
    - 'Сб, 12.09'
    - 'Пн, 14.09' (след. понедельник)
    - '07.09 (Пн)' (архивный день)
    """
    try:
        from datetime import datetime
        dt = datetime.strptime(dt_str, "%Y-%m-%d")
        t_dt = datetime.strptime(today_str, "%Y-%m-%d") if today_str else datetime.now()
        diff = (dt.date() - t_dt.date()).days
        wd = WEEKDAYS_SHORT[dt.weekday()]
        day_str = f"{dt.day:02d}.{dt.month:02d}"

        if diff == 0:
            return f"Сегодня ({day_str})"
        elif diff == 1:
            return f"Завтра ({day_str})"
        elif diff == -1:
            return f"Вчера ({day_str})"
        elif diff > 1:
            return f"{wd}, {day_str}"
        else:
            return f"{day_str} ({wd})"
    except Exception:
        return dt_str


def get_dates_inline_keyboard(
    dates: List[Dict[str, Any]],
    target_type: str = "group",
    target_id: str = "",
    today_str: Optional[str] = None
) -> InlineKeyboardMarkup:
    """Inline-кнопки с доступными датами + кнопка возврата в меню."""
    if not today_str:
        for d in dates:
            if d.get("is_today"):
                today_str = d.get("date")
                break
    if not today_str:
        from datetime import datetime
        today_str = datetime.now().strftime("%Y-%m-%d")

    buttons: List[List[InlineKeyboardButton]] = []
    row: List[InlineKeyboardButton] = []
    for d in dates:
        dt = d["date"]
        label = format_date_button_label(dt, today_str)

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
    """Выбор курса очного отделения (1–4 курс) + кнопка Заочное отделение + назад в меню."""
    buttons = [
        [
            InlineKeyboardButton(text="1 курс (очн.)", icon_custom_emoji_id=PE_SEARCH, callback_data=GroupCallback(action="course", course=1, form="fulltime").pack()),
            InlineKeyboardButton(text="2 курс (очн.)", icon_custom_emoji_id=PE_SEARCH, callback_data=GroupCallback(action="course", course=2, form="fulltime").pack())
        ],
        [
            InlineKeyboardButton(text="3 курс (очн.)", icon_custom_emoji_id=PE_SEARCH, callback_data=GroupCallback(action="course", course=3, form="fulltime").pack()),
            InlineKeyboardButton(text="4 курс (очн.)", icon_custom_emoji_id=PE_SEARCH, callback_data=GroupCallback(action="course", course=4, form="fulltime").pack())
        ],
        [
            InlineKeyboardButton(text="Заочное отделение", icon_custom_emoji_id=PE_PEOPLE, callback_data=GroupCallback(action="zaochn_menu").pack())
        ],
        get_home_button_row()
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_zaochn_selection_keyboard() -> InlineKeyboardMarkup:
    """Выбор курса заочного отделения или всех заочных групп."""
    buttons = [
        [
            InlineKeyboardButton(text="1 курс (заоч.)", icon_custom_emoji_id=PE_SEARCH, callback_data=GroupCallback(action="course", course=1, form="correspondence").pack()),
            InlineKeyboardButton(text="2 курс (заоч.)", icon_custom_emoji_id=PE_SEARCH, callback_data=GroupCallback(action="course", course=2, form="correspondence").pack())
        ],
        [
            InlineKeyboardButton(text="3 курс (заоч.)", icon_custom_emoji_id=PE_SEARCH, callback_data=GroupCallback(action="course", course=3, form="correspondence").pack()),
            InlineKeyboardButton(text="4 курс (заоч.)", icon_custom_emoji_id=PE_SEARCH, callback_data=GroupCallback(action="course", course=4, form="correspondence").pack())
        ],
        [
            InlineKeyboardButton(text="Все группы заочного (38)", icon_custom_emoji_id=PE_PEOPLE, callback_data=GroupCallback(action="zaochn_all").pack())
        ],
        [
            InlineKeyboardButton(text="К очному отделению", icon_custom_emoji_id=PE_ARROW_LEFT, callback_data=MenuCallback(action="change_group").pack())
        ],
        get_home_button_row()
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_groups_search_inline_keyboard(
    groups: List[Dict[str, Any]],
    with_back_course: bool = False,
    back_action: str = "change_group"
) -> InlineKeyboardMarkup:
    """Список найденных групп в виде сетки кнопок (по 2 в ряд) + Главное меню."""
    buttons: List[List[InlineKeyboardButton]] = []
    row: List[InlineKeyboardButton] = []
    for g in groups[:50]:
        name = g.get("out_name") or g.get("name")
        btn = InlineKeyboardButton(
            text=name,
            icon_custom_emoji_id=PE_PEOPLE,
            callback_data=GroupCallback(action="select", group_id=str(g["id"])).pack()
        )
        row.append(btn)
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    if with_back_course:
        if back_action == "zaochn_menu":
            back_btn_cb = GroupCallback(action="zaochn_menu").pack()
            back_btn_text = "К заочному отделению"
        else:
            back_btn_cb = MenuCallback(action="change_group").pack()
            back_btn_text = "К выбору курса"
        buttons.append([
            InlineKeyboardButton(
                text=back_btn_text,
                icon_custom_emoji_id=PE_ARROW_LEFT,
                callback_data=back_btn_cb
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
                callback_data=MenuCallback(action="change_group").pack()
            )
        ],
        get_home_button_row()
    ])


# ---------- Клавиатуры панели администратора ----------

def get_admin_keyboard(is_maintenance: bool) -> InlineKeyboardMarkup:
    """Клавиатура главной панели администратора."""
    maint_text = "Открыть бота (выкл. тех. перерыв)" if is_maintenance else "Закрыть бота на тех. перерыв"
    maint_icon = PE_LOCK_OPEN if is_maintenance else PE_LOCK_CLOSED
    kb = [
        [
            InlineKeyboardButton(
                text=maint_text,
                icon_custom_emoji_id=maint_icon,
                callback_data=AdminCallback(action="toggle_maint").pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="Статистика",
                icon_custom_emoji_id=PE_CHART_STATS,
                callback_data=AdminCallback(action="stats").pack()
            ),
            InlineKeyboardButton(
                text="Сбросить кэш сайта",
                icon_custom_emoji_id=PE_REPEAT,
                callback_data=AdminCallback(action="refresh_cache").pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="Рассылка пользователям",
                icon_custom_emoji_id=PE_MEGAPHONE,
                callback_data=AdminCallback(action="broadcast").pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="Закрыть панель",
                icon_custom_emoji_id=PE_CROSS,
                callback_data=AdminCallback(action="close").pack()
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def get_admin_back_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура возврата в админ-панель."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Назад в админ-панель",
                icon_custom_emoji_id=PE_ARROW_LEFT,
                callback_data=AdminCallback(action="panel").pack()
            )
        ]
    ])


def get_broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения рассылки."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Отправить всем",
                icon_custom_emoji_id=PE_CHECK,
                callback_data=AdminCallback(action="confirm_bc").pack()
            ),
            InlineKeyboardButton(
                text="Отмена",
                icon_custom_emoji_id=PE_CROSS,
                callback_data=AdminCallback(action="cancel_bc").pack()
            )
        ]
    ])
