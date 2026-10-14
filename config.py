import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ALMETPT_BASE_URL = os.getenv("ALMETPT_BASE_URL", "https://almetpt.ru").rstrip("/")
DATABASE_PATH = os.getenv("DATABASE_PATH", str(BASE_DIR / "bot.db"))

# Часовой пояс техникума. Все «локальные» времена бота (рассылки, расписание, отчёты)
# считаются в нём, а не в часовом поясе сервера (в Docker/Railway он обычно UTC).
TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow").strip() or "Europe/Moscow"

# Telegram разрешает до 100 кнопок в одном сообщении; запас оставлен под кнопки навигации.
MAX_LIST_BUTTONS = 90


def parse_bool(raw_val: str, default: bool = False) -> bool:
    raw_val = (raw_val or "").strip().lower()
    if not raw_val:
        return default
    return raw_val in ("true", "1", "yes", "on")


def parse_admin_ids(raw_str: str) -> list[int]:
    ids = []
    for x in raw_str.replace(";", ",").split(","):
        x = x.strip()
        if x.isdigit():
            ids.append(int(x))
    return ids


ADMIN_IDS = parse_admin_ids(os.getenv("ADMIN_IDS", ""))
STAT_ADMIN_IDS = parse_admin_ids(os.getenv("STAT_ADMIN_IDS", ""))
ENABLE_NOTIFICATIONS = parse_bool(os.getenv("ENABLE_NOTIFICATIONS", "false"))
# Сбрасывать ли накопленные во время простоя сообщения при запуске бота.
DROP_PENDING_UPDATES = parse_bool(os.getenv("DROP_PENDING_UPDATES", "false"))


def parse_chat_id(raw_val: str):
    raw_val = (raw_val or "").strip()
    if not raw_val:
        return None
    try:
        return int(raw_val)
    except ValueError:
        return raw_val


BACKUP_CHANNEL_ID = parse_chat_id(os.getenv("BACKUP_CHANNEL_ID", ""))


def validate_config() -> None:
    """Проверяет обязательные настройки. Вызывается при запуске бота, а не при импорте модуля."""
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN не задан в .env файле!")
