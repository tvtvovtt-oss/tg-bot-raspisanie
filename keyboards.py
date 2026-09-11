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
    PE_HOUSE, PE_ARROW_LEFT, PE_ARROW_RIGHT, PE_REPEAT, PE_LINK,
    PE_PERSON_CHECK, PE_CLOCK, PE_INFO, PE_CHECK,
    PE_SETTINGS, PE_LOCK_CLOSED, PE_LOCK_OPEN, PE_CHART_STATS,
    PE_MEGAPHONE, PE_CROSS, PE_PAPERCLIP, PE_SEND_UP, PE_STAR, PE_BAN, PE_WARNING,
    PE_FILE
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
    action: str  # "toggle_maint", "stats", "refresh_cache", "broadcast", "close", "panel", "bc_stats"


class BroadcastCallback(CallbackData, prefix="bc"):
    action: str  # "time_menu", "set_time", "toggle_pin", "confirm_send", "cancel", "back_setup"
    val: str = ""


class StatAdminCallback(CallbackData, prefix="sta"):
    action: str  # "menu", "bot_stats", "broadcast_list", "broadcast_detail", "broadcast_cancel", "close"
    bc_id: int = 0
    page: int = 0


# ---------- Reply-клавиатура (только премиум-иконки, чистый текст без дефолт-эмодзи) ----------

def get_main_keyboard(is_admin_user: bool = False, is_stat_admin_user: bool = False) -> ReplyKeyboardMarkup:
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
    if is_admin_user:
        kb.append([
            KeyboardButton(text="Панель администратора", icon_custom_emoji_id=PE_SETTINGS),
            KeyboardButton(text="Статистика", icon_custom_emoji_id=PE_CHART_STATS)
        ])
    elif is_stat_admin_user:
        kb.append([
            KeyboardButton(text="Статистика", icon_custom_emoji_id=PE_CHART_STATS)
        ])
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

def get_main_menu_inline(is_admin_user: bool = False, is_stat_admin_user: bool = False) -> InlineKeyboardMarkup:
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
            ),
            InlineKeyboardButton(
                text="Статистика и рассылки",
                icon_custom_emoji_id=PE_CHART_STATS,
                callback_data=StatAdminCallback(action="menu").pack()
            )
        ])
    elif is_stat_admin_user:
        rows.append([
            InlineKeyboardButton(
                text="Статистика и рассылки",
                icon_custom_emoji_id=PE_CHART_STATS,
                callback_data=StatAdminCallback(action="menu").pack()
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
                text="Статистика бота",
                icon_custom_emoji_id=PE_CHART_STATS,
                callback_data=AdminCallback(action="stats").pack()
            ),
            InlineKeyboardButton(
                text="Статистика рассылок",
                icon_custom_emoji_id=PE_MEGAPHONE,
                callback_data=AdminCallback(action="bc_stats").pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="Сбросить кэш сайта",
                icon_custom_emoji_id=PE_REPEAT,
                callback_data=AdminCallback(action="refresh_cache").pack()
            ),
            InlineKeyboardButton(
                text="Новая рассылка",
                icon_custom_emoji_id=PE_SEND_UP,
                callback_data=AdminCallback(action="broadcast").pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="Скачать бэкап базы данных",
                icon_custom_emoji_id=PE_FILE,
                callback_data=AdminCallback(action="backup").pack()
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


def get_broadcast_cancel_keyboard(is_full_admin: bool = True) -> InlineKeyboardMarkup:
    """Клавиатура отмены создания рассылки."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Отменить создание рассылки",
                icon_custom_emoji_id=PE_CROSS,
                callback_data=BroadcastCallback(action="cancel").pack()
            )
        ]
    ])


def get_broadcast_finish_keyboard(is_full_admin: bool = True) -> InlineKeyboardMarkup:
    """Клавиатура после завершения/подтверждения рассылки."""
    kb = []
    if is_full_admin:
        kb.append([
            InlineKeyboardButton(
                text="В админ-панель",
                icon_custom_emoji_id=PE_SETTINGS,
                callback_data=AdminCallback(action="panel").pack()
            )
        ])
    kb.append([
        InlineKeyboardButton(
            text="К списку рассылок",
            icon_custom_emoji_id=PE_MEGAPHONE,
            callback_data=StatAdminCallback(action="broadcast_list", page=0).pack()
        ),
        InlineKeyboardButton(
            text="В меню аналитики",
            icon_custom_emoji_id=PE_HOUSE,
            callback_data=StatAdminCallback(action="menu").pack()
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=kb)


# ---------- Клавиатуры настройки рассылки ----------

def get_broadcast_setup_keyboard(
    pin_enabled: bool,
    is_scheduled: bool,
    scheduled_label: str,
    is_daily: bool = False
) -> InlineKeyboardMarkup:
    """
    Клавиатура настройки параметров рассылки:
    - Выбор времени (Сразу / запланировано / ежедневно)
    - Закрепление (Да / Нет)
    - Подтверждение
    - Отмена
    """
    pin_text = "Закрепить сообщение: ДА" if pin_enabled else "Закрепить сообщение: НЕТ"
    pin_icon = PE_CHECK if pin_enabled else PE_CROSS

    if is_daily:
        send_text = "Запустить ежедневную рассылку"
        send_icon = PE_REPEAT
    else:
        send_text = "Запланировать рассылку" if is_scheduled else "Отправить сейчас"
        send_icon = PE_CLOCK if is_scheduled else PE_SEND_UP

    kb = [
        [
            InlineKeyboardButton(
                text=f"Время: {scheduled_label}",
                icon_custom_emoji_id=PE_CLOCK,
                callback_data=BroadcastCallback(action="time_menu").pack()
            )
        ],
        [
            InlineKeyboardButton(
                text=pin_text,
                icon_custom_emoji_id=pin_icon,
                callback_data=BroadcastCallback(action="toggle_pin").pack()
            )
        ],
        [
            InlineKeyboardButton(
                text=send_text,
                icon_custom_emoji_id=send_icon,
                callback_data=BroadcastCallback(action="confirm_send").pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="Отмена",
                icon_custom_emoji_id=PE_CROSS,
                callback_data=BroadcastCallback(action="cancel").pack()
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def get_broadcast_time_selection_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора времени отправки рассылки (пресеты, ежедневно и ручной ввод)."""
    kb = [
        [
            InlineKeyboardButton(
                text="Отправить сразу",
                icon_custom_emoji_id=PE_SEND_UP,
                callback_data=BroadcastCallback(action="set_time", val="now").pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="Каждый день в 07:00",
                icon_custom_emoji_id=PE_REPEAT,
                callback_data=BroadcastCallback(action="set_time", val="daily_7am").pack()
            ),
            InlineKeyboardButton(
                text="Каждый день в своё время",
                icon_custom_emoji_id=PE_CLOCK,
                callback_data=BroadcastCallback(action="set_time", val="daily_custom").pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="Через 15 минут",
                icon_custom_emoji_id=PE_CLOCK,
                callback_data=BroadcastCallback(action="set_time", val="15m").pack()
            ),
            InlineKeyboardButton(
                text="Через 1 час",
                icon_custom_emoji_id=PE_CLOCK,
                callback_data=BroadcastCallback(action="set_time", val="1h").pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="Через 3 часа",
                icon_custom_emoji_id=PE_CLOCK,
                callback_data=BroadcastCallback(action="set_time", val="3h").pack()
            ),
            InlineKeyboardButton(
                text="Завтра в 09:00",
                icon_custom_emoji_id=PE_CALENDAR,
                callback_data=BroadcastCallback(action="set_time", val="tomorrow_9am").pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="Ввести дату и время вручную",
                icon_custom_emoji_id=PE_SEARCH,
                callback_data=BroadcastCallback(action="set_time", val="custom").pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="Назад к параметрам",
                icon_custom_emoji_id=PE_ARROW_LEFT,
                callback_data=BroadcastCallback(action="back_setup").pack()
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def get_broadcast_custom_time_back_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура отмены ручного ввода времени."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Отмена ввода времени",
                icon_custom_emoji_id=PE_ARROW_LEFT,
                callback_data=BroadcastCallback(action="back_setup").pack()
            )
        ]
    ])


# ---------- Клавиатуры отдельной панели статистики (/statadmin) ----------

def get_stat_admin_menu_keyboard(is_full_admin: bool = False) -> InlineKeyboardMarkup:
    """Главное меню отдельной панели статистики."""
    kb = [
        [
            InlineKeyboardButton(
                text="Статистика аудитории бота",
                icon_custom_emoji_id=PE_CHART_STATS,
                callback_data=StatAdminCallback(action="bot_stats").pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="История и статистика рассылок",
                icon_custom_emoji_id=PE_MEGAPHONE,
                callback_data=StatAdminCallback(action="broadcast_list", page=0).pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="Создать новую рассылку",
                icon_custom_emoji_id=PE_SEND_UP,
                callback_data=StatAdminCallback(action="create_broadcast").pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="Скачать бэкап базы данных",
                icon_custom_emoji_id=PE_FILE,
                callback_data=StatAdminCallback(action="backup").pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="Обновить показатели",
                icon_custom_emoji_id=PE_REPEAT,
                callback_data=StatAdminCallback(action="menu").pack()
            )
        ]
    ]
    if is_full_admin:
        kb.append([
            InlineKeyboardButton(
                text="Панель администратора (/admin)",
                icon_custom_emoji_id=PE_SETTINGS,
                callback_data=AdminCallback(action="panel").pack()
            )
        ])
    kb.append([
        InlineKeyboardButton(
            text="Закрыть панель",
            icon_custom_emoji_id=PE_CROSS,
            callback_data=StatAdminCallback(action="close").pack()
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def get_stat_admin_bot_stats_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура под экраном общей статистики бота."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Обновить",
                icon_custom_emoji_id=PE_REPEAT,
                callback_data=StatAdminCallback(action="bot_stats").pack()
            ),
            InlineKeyboardButton(
                text="К рассылкам",
                icon_custom_emoji_id=PE_MEGAPHONE,
                callback_data=StatAdminCallback(action="broadcast_list", page=0).pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="Назад в меню аналитики",
                icon_custom_emoji_id=PE_ARROW_LEFT,
                callback_data=StatAdminCallback(action="menu").pack()
            )
        ]
    ])


def get_broadcast_list_keyboard(
    broadcasts: List[Dict[str, Any]],
    page: int,
    total_pages: int
) -> InlineKeyboardMarkup:
    """Клавиатура со списком рассылок и пагинацией."""
    kb: List[List[InlineKeyboardButton]] = []

    # Кнопки для каждой рассылки
    for bc in broadcasts:
        bc_id = bc["id"]
        status = bc.get("status", "")
        # Иконка статуса
        is_daily = (bc.get("repeat_type") == "daily")
        rep_time = bc.get("repeat_time") or "07:00"
        if status == "completed":
            status_text = f"Завершена ({bc.get('sent_count', 0)})"
            icon = PE_CHECK
        elif status == "scheduled":
            if is_daily:
                status_text = f"Ежедневно в {rep_time}"
                icon = PE_REPEAT
            else:
                sch = bc.get("scheduled_at") or ""
                sch_short = sch[5:16] if len(sch) >= 16 else sch
                status_text = f"План: {sch_short}"
                icon = PE_CLOCK
        elif status == "in_progress":
            status_text = "Отправляется..."
            icon = PE_REPEAT
        elif status == "cancelled":
            status_text = "Отменена"
            icon = PE_CROSS
        else:
            status_text = status
            icon = PE_INFO

        kb.append([
            InlineKeyboardButton(
                text=f"Рассылка #{bc_id} • {status_text}",
                icon_custom_emoji_id=icon,
                callback_data=StatAdminCallback(action="broadcast_detail", bc_id=bc_id, page=page).pack()
            )
        ])

    # Пагинация
    nav_row: List[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(
                text=f"Стр. {page}",
                icon_custom_emoji_id=PE_ARROW_LEFT,
                callback_data=StatAdminCallback(action="broadcast_list", page=page - 1).pack()
            )
        )
    if page < total_pages - 1:
        nav_row.append(
            InlineKeyboardButton(
                text=f"Стр. {page + 2}",
                icon_custom_emoji_id=PE_ARROW_RIGHT,
                callback_data=StatAdminCallback(action="broadcast_list", page=page + 1).pack()
            )
        )
    if nav_row:
        kb.append(nav_row)

    # Управление
    kb.append([
        InlineKeyboardButton(
            text="Создать новую рассылку",
            icon_custom_emoji_id=PE_SEND_UP,
            callback_data=StatAdminCallback(action="create_broadcast").pack()
        )
    ])
    kb.append([
        InlineKeyboardButton(
            text="Обновить список",
            icon_custom_emoji_id=PE_REPEAT,
            callback_data=StatAdminCallback(action="broadcast_list", page=page).pack()
        ),
        InlineKeyboardButton(
            text="В меню аналитики",
            icon_custom_emoji_id=PE_HOUSE,
            callback_data=StatAdminCallback(action="menu").pack()
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=kb)


def get_broadcast_detail_keyboard(
    bc_id: int,
    is_scheduled: bool,
    page: int = 0
) -> InlineKeyboardMarkup:
    """Клавиатура детального просмотра рассылки."""
    kb: List[List[InlineKeyboardButton]] = []

    if is_scheduled:
        kb.append([
            InlineKeyboardButton(
                text="Отменить запланированную рассылку",
                icon_custom_emoji_id=PE_CROSS,
                callback_data=StatAdminCallback(action="broadcast_cancel", bc_id=bc_id, page=page).pack()
            )
        ])

    kb.append([
        InlineKeyboardButton(
            text="К списку рассылок",
            icon_custom_emoji_id=PE_ARROW_LEFT,
            callback_data=StatAdminCallback(action="broadcast_list", page=page).pack()
        ),
        InlineKeyboardButton(
            text="В меню аналитики",
            icon_custom_emoji_id=PE_HOUSE,
            callback_data=StatAdminCallback(action="menu").pack()
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=kb)

