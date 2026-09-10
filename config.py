import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ALMETPT_BASE_URL = os.getenv("ALMETPT_BASE_URL", "https://almetpt.ru").rstrip("/")
DATABASE_PATH = os.getenv("DATABASE_PATH", str(BASE_DIR / "bot.db"))
PROXY_URL = os.getenv("PROXY_URL", os.getenv("HTTPS_PROXY", os.getenv("HTTP_PROXY", "")))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан в .env файле!")
