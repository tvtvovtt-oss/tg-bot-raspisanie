from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from database import is_maintenance_mode, is_admin
from premium_emoji import te, PE_SETTINGS


class MaintenanceMiddleware(BaseMiddleware):
    """
    Перехватывает все входящие сообщения и callback-запросы.
    Если включен технический перерыв:
    - Администраторы имеют полный доступ без ограничений.
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

        # Администраторы имеют беспрепятственный доступ
        if await is_admin(user.id):
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
