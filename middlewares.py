from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

import logging

from database import ensure_user, is_maintenance_mode, is_admin, is_stat_admin
from premium_emoji import te, PE_SETTINGS


logger = logging.getLogger(__name__)


class UserActivityMiddleware(BaseMiddleware):
    """Registers every interaction and keeps activity statistics current."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = data.get("event_from_user")
        if user:
            try:
                await ensure_user(
                    user_id=user.id,
                    username=user.username,
                    first_name=user.first_name
                )
            except Exception as exc:
                # A temporary database failure should not make the whole bot
                # stop responding to an otherwise valid Telegram update.
                logger.warning("Failed to update activity for user %s: %s", user.id, exc)
        return await handler(event, data)


class MaintenanceMiddleware(BaseMiddleware):
    """
    Перехватывает все входящие сообщения и callback-запросы.
    Если включен технический перерыв:
    - Администраторы и аналитики имеют полный доступ.
    - Обычные пользователи получают уведомление о тех. перерыве и их запрос не обрабатывается.
    """
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Проверяем, активен ли режим тех. обслуживания
        maint_active = await is_maintenance_mode()
        if not maint_active:
            return await handler(event, data)

        # Извлекаем пользователя из данных события
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)

        # Администраторы и аналитики имеют беспрепятственный доступ
        if await is_admin(user.id) or await is_stat_admin(user.id):
            return await handler(event, data)

        # Обычные пользователи блокируются с уведомлением
        if isinstance(event, Message):
            await event.answer(
                f"{te(PE_SETTINGS, '⚙️')} <b>Бот временно закрыт на технический перерыв</b>\n\n"
                "Ведутся технические работы или обновление данных.\n"
                "Пожалуйста, попробуйте немного позже!",
                parse_mode="HTML"
            )
            return None
        elif isinstance(event, CallbackQuery):
            await event.answer(
                "Бот временно закрыт на тех. перерыв. Попробуйте позже!",
                show_alert=True
            )
            return None

        return None
