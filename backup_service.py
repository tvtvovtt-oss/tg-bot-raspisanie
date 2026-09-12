import os
import sqlite3
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

from aiogram import Bot
from aiogram.types import FSInputFile, Message

from config import DATABASE_PATH, BACKUP_CHANNEL_ID, ADMIN_IDS
from database import get_bot_stats, init_db
from premium_emoji import te, PE_FILE

logger = logging.getLogger(__name__)
_RESTORE_LOCK = asyncio.Lock()


REQUIRED_TABLE_COLUMNS = {
    "users": {"user_id", "notifications"},
    "broadcasts": {"id", "status", "message_text"},
    "bot_admins": {"user_id"},
    "bot_stat_admins": {"user_id"},
    "bot_settings": {"key", "value"},
    "notified_schedules": {"user_id", "target_type", "target_id", "schedule_date"},
}


def remove_local_file(path: Optional[str]):
    if not path:
        return
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError as exc:
        logger.warning("Не удалось удалить временный файл %s: %s", path, exc)


def validate_sqlite_backup(path: str) -> int:
    """Validates integrity and the minimum schema expected by this bot."""
    conn = sqlite3.connect(f"file:{Path(path).resolve().as_posix()}?mode=ro", uri=True)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise ValueError(f"SQLite integrity_check failed: {integrity[0] if integrity else 'no result'}")

        tables = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        missing_tables = set(REQUIRED_TABLE_COLUMNS) - tables
        if missing_tables:
            raise ValueError(f"Missing required tables: {', '.join(sorted(missing_tables))}")

        for table, required_columns in REQUIRED_TABLE_COLUMNS.items():
            columns = {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}
            missing_columns = required_columns - columns
            if missing_columns:
                raise ValueError(
                    f"Table {table} is missing columns: {', '.join(sorted(missing_columns))}"
                )
        return int(conn.execute("SELECT count(*) FROM users").fetchone()[0])
    finally:
        conn.close()


def restore_sqlite_backup(source_path: str, destination_path: str) -> int:
    """Validates a backup and atomically copies it through SQLite Backup API."""
    user_count = validate_sqlite_backup(source_path)
    src_conn = sqlite3.connect(source_path)
    dst_conn = sqlite3.connect(destination_path)
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()
    return user_count


async def restore_sqlite_backup_async(source_path: str, destination_path: str) -> int:
    """Serializes restores and keeps blocking SQLite work off the event loop."""
    async with _RESTORE_LOCK:
        return await asyncio.to_thread(
            restore_sqlite_backup,
            source_path,
            destination_path
        )


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
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    dst_path = backup_dir / f"backup_{timestamp}_{uuid4().hex[:8]}.db"

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
        remove_local_file(str(dst_path))
        return None


async def create_safe_sqlite_backup_async() -> Optional[str]:
    """Runs the blocking SQLite backup outside the bot event loop."""
    return await asyncio.to_thread(create_safe_sqlite_backup)


async def send_backup_to_channel(
    bot: Bot,
    caption_extra: str = "",
    backup_file_path: Optional[str] = None,
    cleanup_local: bool = True
) -> Optional[Message]:
    """
    Создает снимок базы данных и отправляет его в Telegram-канал (или админу), закрепляя сообщение.
    """
    target_chat = BACKUP_CHANNEL_ID
    if not target_chat:
        if ADMIN_IDS:
            target_chat = ADMIN_IDS[0]
        else:
            logger.warning("[BACKUP] Ни BACKUP_CHANNEL_ID, ни ADMIN_IDS не заданы. Пропуск отправки бэкапа.")
            if cleanup_local:
                remove_local_file(backup_file_path)
            return None

    backup_file_path = backup_file_path or await create_safe_sqlite_backup_async()
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
            import html
            caption += f"\n<i>{html.escape(caption_extra)}</i>"

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

        return sent_msg

    except Exception as e:
        logger.error(f"[BACKUP] Ошибка отправки резервной копии в Telegram: {e}")
        return None
    finally:
        if cleanup_local:
            remove_local_file(backup_file_path)


async def restore_database_from_channel(bot: Bot) -> bool:
    """
    Восстанавливает базу данных из закрепленного сообщения в Telegram-канале бэкапов.
    """
    target_chat = BACKUP_CHANNEL_ID
    if not target_chat:
        logger.info("[BACKUP] BACKUP_CHANNEL_ID не задан. Авто-восстановление пропущено.")
        return False

    temp_restore_path = str(Path(DATABASE_PATH)) + f".{uuid4().hex}.restore_temp"
    try:
        logger.info(f"[BACKUP] Проверяю закрепленное сообщение в канале {target_chat} для восстановления...")
        chat = await bot.get_chat(target_chat)
        pinned = chat.pinned_message
        if not pinned or not pinned.document:
            logger.warning("[BACKUP] В канале бэкапов нет закрепленного сообщения с файлом базы данных.")
            return False

        doc = pinned.document
        if not (doc.file_name and doc.file_name.lower().endswith((".db", ".sqlite", ".sqlite3"))):
            logger.warning(f"[BACKUP] Закрепленный документ {doc.file_name} не является базой данных.")
            return False

        dst_path = Path(DATABASE_PATH)
        dst_path.parent.mkdir(parents=True, exist_ok=True)

        await bot.download(doc.file_id, destination=temp_restore_path)

        user_count = await restore_sqlite_backup_async(temp_restore_path, DATABASE_PATH)

        logger.info(f"[BACKUP] УСПЕШНО ВОССТАНОВЛЕНА база данных из Telegram! Пользователей в базе: {user_count}")
        return True

    except Exception as e:
        logger.error(f"[BACKUP] Ошибка авто-восстановления базы из канала: {e}")
        return False
    finally:
        remove_local_file(temp_restore_path)


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
            await init_db(recover_interrupted=True)
            return

    await init_db(recover_interrupted=True)


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
