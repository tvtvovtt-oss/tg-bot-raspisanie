import os
import shutil
import sqlite3
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

from aiogram import Bot
from aiogram.types import FSInputFile, Message

from config import DATABASE_PATH, BACKUP_CHANNEL_ID, ADMIN_IDS
from database import get_bot_stats, init_db
from premium_emoji import te, PE_FILE

logger = logging.getLogger(__name__)


def create_safe_sqlite_backup() -> Optional[str]:
    """
    Создает целостный снимок базы данных SQLite с помощью официального Online Backup API.
    Корректно работает при включенном WAL-режиме и активных транзакциях.
    """
    src_path = Path(DATABASE_PATH)
    if not src_path.exists():
        return None

    backup_dir = src_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst_path = backup_dir / f"backup_{timestamp}.db"

    try:
        src_conn = sqlite3.connect(src_path)
        dst_conn = sqlite3.connect(dst_path)
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
            src_conn.close()
        return str(dst_path)
    except Exception as e:
        logger.error(f"Ошибка создания локального бэкапа SQLite: {e}")
        return None


async def send_backup_to_channel(bot: Bot, caption_extra: str = "") -> Optional[Message]:
    """
    Создает снимок базы данных и отправляет его в Telegram-канал (или админу), закрепляя сообщение.
    """
    target_chat = BACKUP_CHANNEL_ID
    if not target_chat:
        if ADMIN_IDS:
            target_chat = ADMIN_IDS[0]
        else:
            logger.warning("[BACKUP] Ни BACKUP_CHANNEL_ID, ни ADMIN_IDS не заданы. Пропуск отправки бэкапа.")
            return None

    backup_file_path = create_safe_sqlite_backup()
    if not backup_file_path or not os.path.exists(backup_file_path):
        logger.error("[BACKUP] Не удалось создать файл резервной копии.")
        return None

    try:
        stats = await get_bot_stats()
        now_str = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        caption = (
            f"{te(PE_FILE)} #backup <b>Автоматическая резервная копия базы данных</b>\n\n"
            f"📅 Время создания: <code>{now_str}</code>\n"
            f"👥 Всего пользователей: <b>{stats.get('total', 0)}</b> чел.\n"
            f"🔔 С уведомлениями: <b>{stats.get('with_notif', 0)}</b> чел.\n"
            f"📣 Проведено рассылок: <b>{stats.get('total_broadcasts', 0)}</b>\n"
        )
        if caption_extra:
            caption += f"\n<i>{caption_extra}</i>"

        doc = FSInputFile(backup_file_path, filename="bot.db")
        sent_msg = await bot.send_document(
            chat_id=target_chat,
            document=doc,
            caption=caption,
            parse_mode="HTML"
        )

        # Закрепляем сообщение в канале
        try:
            await bot.pin_chat_message(
                chat_id=target_chat,
                message_id=sent_msg.message_id,
                disable_notification=True
            )
            logger.info(f"[BACKUP] Резервная копия #{sent_msg.message_id} успешно сохранена и закреплена в {target_chat}!")
        except Exception as e:
            logger.debug(f"[BACKUP] Не удалось закрепить сообщение бэкапа: {e}")

        # Удаляем локальный временный файл бэкапа
        try:
            os.remove(backup_file_path)
        except Exception:
            pass

        return sent_msg

    except Exception as e:
        logger.error(f"[BACKUP] Ошибка отправки резервной копии в Telegram: {e}")
        return None


async def restore_database_from_channel(bot: Bot) -> bool:
    """
    Восстанавливает базу данных из закрепленного сообщения в Telegram-канале бэкапов.
    """
    target_chat = BACKUP_CHANNEL_ID
    if not target_chat:
        logger.info("[BACKUP] BACKUP_CHANNEL_ID не задан. Авто-восстановление пропущено.")
        return False

    try:
        logger.info(f"[BACKUP] Проверяю закрепленное сообщение в канале {target_chat} для восстановления...")
        chat = await bot.get_chat(target_chat)
        pinned = chat.pinned_message
        if not pinned or not pinned.document:
            logger.warning("[BACKUP] В канале бэкапов нет закрепленного сообщения с файлом базы данных.")
            return False

        doc = pinned.document
        if not (doc.file_name and doc.file_name.endswith((".db", ".sqlite", ".sqlite3"))):
            logger.warning(f"[BACKUP] Закрепленный документ {doc.file_name} не является базой данных.")
            return False

        dst_path = Path(DATABASE_PATH)
        dst_path.parent.mkdir(parents=True, exist_ok=True)

        temp_restore_path = str(dst_path) + ".restore_temp"
        await bot.download(doc.file_id, destination=temp_restore_path)

        # Проверяем целостность скачанной базы
        conn = sqlite3.connect(temp_restore_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT count(*) FROM users")
            user_count = cursor.fetchone()[0]
        finally:
            conn.close()

        # Безопасно восстанавливаем базу данных с помощью SQLite Online Backup API
        src_conn = sqlite3.connect(temp_restore_path)
        dst_conn = sqlite3.connect(DATABASE_PATH)
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
            src_conn.close()

        try:
            os.remove(temp_restore_path)
        except Exception:
            pass

        logger.info(f"[BACKUP] УСПЕШНО ВОССТАНОВЛЕНА база данных из Telegram! Пользователей в базе: {user_count}")
        return True

    except Exception as e:
        logger.error(f"[BACKUP] Ошибка авто-восстановления базы из канала: {e}")
        if os.path.exists(temp_restore_path):
            try:
                os.remove(temp_restore_path)
            except Exception:
                pass
        return False


async def auto_restore_if_needed(bot: Bot):
    """
    Вызывается при запуске бота: если локальная база пуста или отсутствует,
    автоматически восстанавливает её из Telegram-канала.
    """
    src_path = Path(DATABASE_PATH)
    needs_restore = False

    if not src_path.exists() or src_path.stat().st_size == 0:
        needs_restore = True
    else:
        try:
            conn = sqlite3.connect(src_path)
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT count(*) FROM users")
                cnt = cursor.fetchone()[0]
                if cnt == 0:
                    needs_restore = True
            finally:
                conn.close()
        except Exception:
            needs_restore = True

    if needs_restore and BACKUP_CHANNEL_ID:
        logger.info("[BACKUP] Локальная база данных пуста или отсутствует. Пытаюсь восстановить из Telegram-канала...")
        restored = await restore_database_from_channel(bot)
        if restored:
            await init_db()
            return

    await init_db()


async def backup_scheduler_worker(bot: Bot):
    """
    Фоновый воркер: каждые 30 минут автоматически сохраняет свежий бэкап в Telegram-канал.
    """
    await asyncio.sleep(60)
    while True:
        try:
            if BACKUP_CHANNEL_ID:
                await send_backup_to_channel(bot, caption_extra="Периодический авто-бэкап (раз в 30 минут)")
        except Exception as e:
            logger.error(f"[BACKUP_WORKER] Ошибка в цикле авто-бэкапа: {e}")

        await asyncio.sleep(1800)
