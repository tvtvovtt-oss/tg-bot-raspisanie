"""Общая отправка сообщений пользователям: повторы при flood-control и запасной вариант без premium-эмодзи."""
import asyncio
import logging
from typing import Any, Optional, Tuple

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import Message

from premium_emoji import strip_tg_emoji

logger = logging.getLogger(__name__)

SENT = "sent"
BLOCKED = "blocked"
FAILED = "failed"

MAX_ATTEMPTS = 3

# Лимит Telegram на длину одного текстового сообщения (в символах после разбора разметки).
TELEGRAM_MAX_TEXT_LENGTH = 4096


async def send_with_retry(
    bot: Bot,
    user_id: int,
    text: str,
    **kwargs: Any
) -> Tuple[Optional[Message], str]:
    """
    Отправляет сообщение и возвращает (сообщение | None, исход), где исход — sent, blocked или failed.

    - flood-control (RetryAfter) — ждём и повторяем, не более MAX_ATTEMPTS раз;
    - пользователь заблокировал бота — blocked (повторять бессмысленно);
    - ошибка разметки — один повтор без <tg-emoji>, дальше failed;
    - прочие временные ошибки — failed (вызывающий код может повторить позже).
    """
    current_text = text
    fallback_used = False
    for attempt in range(MAX_ATTEMPTS):
        try:
            message = await bot.send_message(
                chat_id=user_id,
                text=current_text,
                disable_web_page_preview=True,
                **kwargs
            )
            return message, SENT
        except TelegramRetryAfter as exc:
            if attempt == MAX_ATTEMPTS - 1:
                logger.warning("Telegram rate limit persisted for user %s", user_id)
                return None, FAILED
            await asyncio.sleep(max(float(exc.retry_after), 0.1) + 0.1)
        except TelegramForbiddenError:
            return None, BLOCKED
        except TelegramBadRequest as exc:
            if not fallback_used:
                clean_text = strip_tg_emoji(current_text)
                if clean_text != current_text:
                    current_text = clean_text
                    fallback_used = True
                    continue
            logger.warning("Не удалось отправить сообщение пользователю %s: %s", user_id, exc)
            return None, FAILED
        except Exception as exc:
            error_text = str(exc).lower()
            if "forbidden" in error_text or "blocked" in error_text or "chat not found" in error_text:
                return None, BLOCKED
            logger.warning("Не удалось отправить сообщение пользователю %s: %s", user_id, exc)
            return None, FAILED
    return None, FAILED
