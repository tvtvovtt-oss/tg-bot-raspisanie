import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from config import BOT_TOKEN, ENABLE_NOTIFICATIONS, BACKUP_CHANNEL_ID
from handlers import router
from parser import get_groups, get_available_dates
from notifier import schedule_notification_worker
from broadcast_service import broadcast_scheduler_worker
from backup_service import auto_restore_if_needed, backup_scheduler_worker, send_backup_to_channel
from middlewares import MaintenanceMiddleware, UserActivityMiddleware

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


async def set_bot_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="today", description="Расписание на сегодня"),
        BotCommand(command="tomorrow", description="Расписание на завтра"),
        BotCommand(command="dates", description="Выбрать дату"),
        BotCommand(command="mygroup", description="Моя группа"),
        BotCommand(command="help", description="Справка и помощь"),
    ]
    await bot.set_my_commands(commands)


async def main():
    logger.info("Создание экземпляра Telegram-бота...")
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    logger.info("Инициализация базы данных и проверка авто-восстановления...")
    await auto_restore_if_needed(bot)

    logger.info("Предзагрузка списка групп и дат с almetpt.ru...")
    try:
        groups = await get_groups(force_refresh=True)
        dates = await get_available_dates(force_refresh=True)
        logger.info(f"Успешно загружено {len(groups)} групп и {len(dates.get('dates', []))} дат.")
    except Exception as e:
        logger.warning(f"Ошибка при предварительной загрузке: {e}")

    dp = Dispatcher()
    dp.message.outer_middleware(UserActivityMiddleware())
    dp.callback_query.outer_middleware(UserActivityMiddleware())
    dp.message.outer_middleware(MaintenanceMiddleware())
    dp.callback_query.outer_middleware(MaintenanceMiddleware())
    dp.include_router(router)

    # Set commands menu in Telegram UI
    await set_bot_commands(bot)

    # Delete webhook to prevent conflicts and drop pending updates
    await bot.delete_webhook(drop_pending_updates=True)

    # Start background notifier worker (if enabled in config)
    notifier_task = None
    if ENABLE_NOTIFICATIONS:
        notifier_task = asyncio.create_task(schedule_notification_worker(bot))
        logger.info("Фоновый сервис уведомлений о расписании запущен.")
    else:
        logger.info("Фоновые уведомления о новом расписании отключены (ENABLE_NOTIFICATIONS=false).")

    # Start background broadcast scheduler worker
    broadcast_task = asyncio.create_task(broadcast_scheduler_worker(bot))
    logger.info("Фоновый планировщик отложенных рассылок запущен.")

    # Start background backup scheduler worker (every 30 minutes)
    backup_task = asyncio.create_task(backup_scheduler_worker(bot))
    logger.info("Фоновый сервис автоматического резервного копирования запущен (раз в 30 мин).")

    logger.info("Бот успешно запущен и готов к работе!")
    try:
        # Keep the session alive until the final backup has been sent below.
        await dp.start_polling(bot, close_bot_session=False)
    finally:
        background_tasks = [task for task in (notifier_task, broadcast_task, backup_task) if task]
        for task in background_tasks:
            task.cancel()
        if background_tasks:
            await asyncio.gather(*background_tasks, return_exceptions=True)
        try:
            if BACKUP_CHANNEL_ID:
                logger.info("Сохранение финального бэкапа перед завершением работы...")
                await send_backup_to_channel(bot, caption_extra="Финальный авто-бэкап перед перезапуском контейнера")
        except Exception as e:
            logger.debug(f"Не удалось отправить финальный бэкап: {e}")
        await bot.session.close()
        logger.info("Бот остановлен.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот завершил работу.")
