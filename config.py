import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ALMETPT_BASE_URL = os.getenv("ALMETPT_BASE_URL", "https://almetpt.ru").rstrip("/")
DATABASE_PATH = os.getenv("DATABASE_PATH", str(BASE_DIR / "bot.db"))
PROXY_URL = os.getenv("PROXY_URL", os.getenv("HTTPS_PROXY", os.getenv("HTTP_PROXY", "")))


def parse_admin_ids(raw_str: str) -> list[int]:
    ids = []
    for x in raw_str.replace(";", ",").split(","):
        x = x.strip()
        if x.isdigit():
            ids.append(int(x))
    return ids


ADMIN_IDS = parse_admin_ids(os.getenv("ADMIN_IDS", "5966353805,7218741941"))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан в .env файле!")
