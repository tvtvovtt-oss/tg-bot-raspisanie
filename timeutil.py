"""Единый источник «текущего времени» бота в часовом поясе техникума."""
import logging
from datetime import datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config import TIMEZONE

logger = logging.getLogger(__name__)

# Запасной вариант, если в системе нет базы часовых поясов (нужен пакет tzdata).
_FALLBACK_TZ = timezone(timedelta(hours=3), "MSK")


def _load_timezone() -> tzinfo:
    try:
        return ZoneInfo(TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        logger.warning(
            "Часовой пояс %r недоступен (%s). Установите пакет tzdata. "
            "Используется запасной UTC+3.", TIMEZONE, exc
        )
        return _FALLBACK_TZ


BOT_TZ: tzinfo = _load_timezone()


def now_local() -> datetime:
    """Текущее время техникума без tzinfo (naive) — в том же виде, в каком оно хранится в БД."""
    return datetime.now(BOT_TZ).replace(tzinfo=None)


def today_local_str() -> str:
    return now_local().strftime("%Y-%m-%d")
