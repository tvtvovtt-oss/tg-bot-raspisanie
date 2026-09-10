"""Премиум-эмодзи Telegram (custom_emoji_id).

Используется в двух режимах:

1. Внутри HTML-сообщений через тег ``<tg-emoji emoji-id="...">⚙</tg-emoji>``.
   Помощник :func:`te` собирает такой тег, оставляя обычный эмодзи как
   fallback для не-премиум пользователей.
2. Как иконка кнопки (``icon_custom_emoji_id``) у :class:`KeyboardButton` и
   :class:`InlineKeyboardButton`. Telegram сам нарисует анимированную иконку
   слева от текста для премиум-юзеров; не-премиум видят обычный текст.

Все ID — стандартный пак Telegram, доступный любому боту."""

# ---- Ассортимент ID (название → ID) ----
PE_SETTINGS         = "5870982283724328568"  # ⚙ Настройки
PE_PROFILE          = "5870994129244131212"  # 👤 Профиль
PE_PEOPLE           = "5870772616305839506"  # 👥 Люди
PE_PERSON_CHECK     = "5891207662678317861"  # 👤✅ Человек и галочка
PE_PERSON_CROSS     = "5893192487324880883"  # 👤❌ Человек и крестик
PE_FILE             = "5870528606328852614"  # 📁 Файл
PE_SMILE            = "5870764288364252592"  # 🙂 Улыбка
PE_CHART_GROW       = "5870930636742595124"  # 📊 Рост / график
PE_CHART_STATS      = "5870921681735781843"  # 📊 Статистика
PE_HOUSE            = "5873147866364514353"  # 🏘 Дом
PE_LOCK_CLOSED      = "6037249452824072506"  # 🔒 Замок закрытый
PE_LOCK_OPEN        = "6037496202990194718"  # 🔓 Замок открытый
PE_MEGAPHONE        = "6039422865189638057"  # 📣 Рупор
PE_CHECK            = "6030839471832829491"  # ✅ Галочка (премиум-пак)
PE_CROSS            = "5870657884844462243"  # ❌ Крестик
PE_PENCIL           = "5870676941614354370"  # 🖋 Карандаш
PE_TRASH            = "5870875489362513438"  # 🗑 Мусор
PE_ARROW_DOWN_LIST  = "5893057118545646106"  # 📰 Вниз / список
PE_PAPERCLIP        = "6039451237743595514"  # 📎 Скрепка
PE_LINK             = "5769289093221454192"  # 🔗 Ссылка
PE_INFO             = "6028435952299413210"  # ℹ Инфо
PE_BOT              = "6030400221232501136"  # 🤖 Бот
PE_EYE              = "6037397706505195857"  # 👁 Глаз
PE_EYE_HIDDEN       = "6037243349675544634"  # 👁‍🗨 Скрыто
PE_SEND_UP          = "5963103826075456248"  # ⬆ Отправить
PE_DOWNLOAD         = "6039802767931871481"  # ⬇ Скачать
PE_BELL             = "6039486778597970865"  # 🔔 Уведомление
PE_GIFT             = "6032644646587338669"  # 🎁 Подарок
PE_CLOCK            = "5983150113483134607"  # ⏰ Часы
PE_PARTY            = "6041731551845159060"  # 🎉 Ура
PE_FONT             = "5870801517140775623"  # 🔤 Шрифт
PE_WRITE            = "5870753782874246579"  # ✍ Писать
PE_MEDIA_PHOTO      = "6035128606563241721"  # 🖼 Медиа / фото
PE_GEOTAG           = "6042011682497106307"  # 📍 Геометка
PE_WALLET           = "5769126056262898415"  # 👛 Кошелёк
PE_BOX              = "5884479287171485878"  # 📦 Коробка
PE_CRYPTO_BOT       = "5260752406890711732"  # 👾 Криптобот
PE_CALENDAR         = "5890937706803894250"  # 📅 Календарь
PE_TAG              = "5886285355279193209"  # 🏷 Бирка
PE_TIME_PASSED      = "5775896410780079073"  # 🕓 Время прошло
PE_APPS             = "5778672437122045013"  # 📦 Приложения
PE_BRUSH            = "6050679691004612757"  # 🖌 Кисточка
PE_ADD_TEXT         = "5771851822897566479"  # 🔡 Добавить текст
PE_RESIZE           = "5778479949572738874"  # ↔ Разрешение
PE_COIN             = "5904462880941545555"  # 🪙 Деньги
PE_COIN_SEND        = "5890848474563352982"  # 🪙↗ Отправить деньги
PE_COIN_RECV        = "5879814368572478751"  # 🏧 Принять деньги
PE_CODE             = "5940433880585605708"  # </> Код
PE_LOADING          = "5345906554510012647"  # 🔄 Загрузка
PE_REPEAT           = "6030657343744644592"  # 🔁 Повтор / попытка
PE_ARROW_RIGHT      = "6037622221625626773"  # ➡️ Вперёд / далее
PE_ARROW_LEFT       = "6039539366177541657"  # ⬅️ Назад

# ---- Добавлено: статусы/действия ----
PE_BAN              = "5346147394801138261"  # 🚫 Бан / блокировка
PE_BUG              = "5346020482812510423"  # 🐞 Баг-репорт
PE_TARGET           = "6032949275732742941"  # 🎯 Цель / ник нарушителя
PE_COMMENT          = "6034831751308644168"  # 💬 Комментарий админа форума
PE_SEARCH           = "6032850693348399258"  # 🔎 Поиск / проверка статуса
PE_STAR             = "6028338546736107668"  # ⭐️ Звезда / активное / избранное
PE_WARNING          = "6030563507299160824"  # ❗️ Предупреждение / важно

# Индикаторы форума — переиспользуем существующие «глаза»:
PE_FORUM_ONLINE     = PE_EYE         # 🟢 форум доступен
PE_FORUM_OFFLINE    = PE_EYE_HIDDEN  # 🔴 форум недоступен


EMOJI_FALLBACKS = {
    PE_SETTINGS: "⚙️",
    PE_PROFILE: "👤",
    PE_PEOPLE: "👥",
    PE_PERSON_CHECK: "👤",
    PE_PERSON_CROSS: "👤",
    PE_FILE: "📁",
    PE_SMILE: "🙂",
    PE_CHART_GROW: "📊",
    PE_CHART_STATS: "📊",
    PE_HOUSE: "🏠",
    PE_LOCK_CLOSED: "🔒",
    PE_LOCK_OPEN: "🔓",
    PE_MEGAPHONE: "📣",
    PE_CHECK: "✅",
    PE_CROSS: "❌",
    PE_PENCIL: "✏️",
    PE_TRASH: "🗑️",
    PE_ARROW_DOWN_LIST: "📰",
    PE_PAPERCLIP: "📎",
    PE_LINK: "🔗",
    PE_INFO: "ℹ️",
    PE_BOT: "🤖",
    PE_EYE: "👁️",
    PE_EYE_HIDDEN: "👁️",
    PE_SEND_UP: "⬆️",
    PE_DOWNLOAD: "⬇️",
    PE_BELL: "🔔",
    PE_GIFT: "🎁",
    PE_CLOCK: "⏰",
    PE_PARTY: "🎉",
    PE_FONT: "🔤",
    PE_WRITE: "✍️",
    PE_MEDIA_PHOTO: "🖼️",
    PE_GEOTAG: "📍",
    PE_WALLET: "👛",
    PE_BOX: "📦",
    PE_CRYPTO_BOT: "👾",
    PE_CALENDAR: "📅",
    PE_TAG: "🏷️",
    PE_TIME_PASSED: "📆",
    PE_APPS: "📦",
    PE_BRUSH: "🖌️",
    PE_ADD_TEXT: "🔡",
    PE_RESIZE: "↔️",
    PE_COIN: "🪙",
    PE_COIN_SEND: "🪙",
    PE_COIN_RECV: "🏧",
    PE_CODE: "💻",
    PE_LOADING: "🔄",
    PE_REPEAT: "🔄",
    PE_ARROW_RIGHT: "➡️",
    PE_ARROW_LEFT: "⬅️",
    PE_BAN: "🚫",
    PE_BUG: "🐞",
    PE_TARGET: "🎯",
    PE_COMMENT: "💬",
    PE_SEARCH: "🔍",
    PE_STAR: "⭐",
    PE_WARNING: "⚠️",
}


from typing import Optional
import re

def te(emoji_id: str, fallback: Optional[str] = None) -> str:
    """Собирает HTML-тег премиум-эмодзи.
    
    Внутри <tg-emoji> всегда подставляется валидный Unicode-эмодзи,
    соответствующий смыслу иконки, чтобы избежать ошибки Telegram 'Bad Request: ENTITY_TEXT_INVALID'.
    """
    if fallback is None or fallback in ("•", "-", "*", "."):
        fb = EMOJI_FALLBACKS.get(emoji_id, "🔹")
    elif fallback == "!":
        fb = "❗"
    elif fallback == "?":
        fb = "❓"
    else:
        fb = fallback
    return f'<tg-emoji emoji-id="{emoji_id}">{fb}</tg-emoji>'


def strip_tg_emoji(text: str) -> str:
    """Удаляет теги <tg-emoji>, оставляя внутри валидные Unicode-эмодзи."""
    return re.sub(r'<tg-emoji[^>]*>(.*?)</tg-emoji>', r'\1', text)


# ---- Цветные кнопки -------------------------------------------------------
# Telegram Bot API позволяет задать `style` у KeyboardButton/InlineKeyboardButton:
#   "danger"  — красная (❌ Отмена, 🗑 Удалить, 🚫 Бан)
#   "success" — зелёная (✅ Отправить, ✅ Подтвердить, ✅ Использовать)
#   "primary" — синяя  (📝 Подать жалобу, 🔐 Войти, 🔄 Синхронизировать)
# Если стиль не задан — используется дефолтный стиль приложения.
BTN_DANGER  = "danger"
BTN_SUCCESS = "success"
BTN_PRIMARY = "primary"
