import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from config import BOT_TOKEN, PROXY_URL
from database import init_db
from handlers import router
from parser import get_groups, get_available_dates
from notifier import schedule_notification_worker
from middlewares import MaintenanceMiddleware

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
    logger.info("Инициализация базы данных...")
    await init_db()

    logger.info("Предзагрузка списка групп и дат с almetpt.ru...")
    try:
        groups = await get_groups(force_refresh=True)
        dates = await get_available_dates(force_refresh=True)
        logger.info(f"Успешно загружено {len(groups)} групп и {len(dates.get('dates', []))} дат.")
    except Exception as e:
        logger.warning(f"Ошибка при предварительной загрузке: {e}")

    # Set up session (with proxy if provided)
    if PROXY_URL:
        logger.info(f"Используется прокси для Telegram API: {PROXY_URL}")
        session = AiohttpSession(proxy=PROXY_URL)
    else:
        session = None

    logger.info("Запуск Telegram-бота...")
    bot = Bot(
        token=BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()
    dp.message.outer_middleware(MaintenanceMiddleware())
    dp.callback_query.outer_middleware(MaintenanceMiddleware())
    dp.include_router(router)

    # Set commands menu in Telegram UI
    await set_bot_commands(bot)

    # Delete webhook to prevent conflicts and drop pending updates
    await bot.delete_webhook(drop_pending_updates=True)

    # Start background notifier worker
    notifier_task = asyncio.create_task(schedule_notification_worker(bot))

    logger.info("Бот успешно запущен и готов к работе!")
    try:
        await dp.start_polling(bot)
    finally:
        notifier_task.cancel()
        await bot.session.close()
        logger.info("Бот остановлен.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот завершил работу.")
