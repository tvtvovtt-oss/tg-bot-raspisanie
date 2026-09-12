import aiosqlite
import logging
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Set
from config import DATABASE_PATH, ADMIN_IDS, STAT_ADMIN_IDS

logger = logging.getLogger(__name__)

_MAINTENANCE_CACHE: Optional[bool] = None
_ADMIN_IDS_CACHE: Optional[Set[int]] = None
_STAT_ADMIN_IDS_CACHE: Optional[Set[int]] = None


async def init_db(recover_interrupted: bool = False):
    global _MAINTENANCE_CACHE, _ADMIN_IDS_CACHE, _STAT_ADMIN_IDS_CACHE

    db_path = Path(DATABASE_PATH)
    if db_path.parent and not db_path.parent.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)

    # Авто-миграция: если база в новом расположении пуста, но существует локальная bot.db
    legacy_db = Path("bot.db")
    if (not db_path.exists() or db_path.stat().st_size == 0) and legacy_db.exists():
        try:
            if legacy_db.resolve() != db_path.resolve():
                logger.info(f"Копирование существующей базы {legacy_db} в постоянное хранилище {db_path}")
                shutil.copy2(legacy_db, db_path)
        except Exception as e:
            logger.warning(f"Не удалось скопировать старую базу: {e}")

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA busy_timeout=5000;")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                group_id TEXT,
                group_name TEXT,
                teacher_id TEXT,
                teacher_name TEXT,
                notifications INTEGER DEFAULT 1,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Автоматическая миграция недостающих колонок в таблице users
        cursor = await db.execute("PRAGMA table_info(users)")
        existing_cols = {row[1] for row in await cursor.fetchall()}
        col_defs = {
            "username": "TEXT",
            "first_name": "TEXT",
            "group_id": "TEXT",
            "group_name": "TEXT",
            "teacher_id": "TEXT",
            "teacher_name": "TEXT",
            "notifications": "INTEGER DEFAULT 1",
            "updated_at": "TIMESTAMP"
        }
        for col_name, col_type in col_defs.items():
            if col_name not in existing_cols:
                try:
                    await db.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
                except Exception as e:
                    logger.debug(f"Migrate column {col_name} note: {e}")

        if "updated_at" not in existing_cols:
            try:
                await db.execute("UPDATE users SET updated_at = datetime('now') WHERE updated_at IS NULL")
            except Exception:
                pass

        await db.execute("""
            CREATE TABLE IF NOT EXISTS notified_schedules (
                user_id INTEGER,
                target_type TEXT,
                target_id TEXT,
                schedule_date TEXT,
                schedule_fingerprint TEXT,
                notified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, target_type, target_id, schedule_date)
            )
        """)
        notified_cursor = await db.execute("PRAGMA table_info(notified_schedules)")
        notified_columns = {row[1] for row in await notified_cursor.fetchall()}
        if "schedule_fingerprint" not in notified_columns:
            await db.execute("ALTER TABLE notified_schedules ADD COLUMN schedule_fingerprint TEXT")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_admins (
                user_id INTEGER PRIMARY KEY,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_stat_admins (
                user_id INTEGER PRIMARY KEY,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS broadcasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_by INTEGER,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                scheduled_at TEXT,
                message_text TEXT,
                pin_message INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                repeat_type TEXT DEFAULT 'once',
                repeat_time TEXT,
                total_targets INTEGER DEFAULT 0,
                sent_count INTEGER DEFAULT 0,
                blocked_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                completed_at TEXT
            )
        """)
        try:
            await db.execute("ALTER TABLE broadcasts ADD COLUMN repeat_type TEXT DEFAULT 'once'")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE broadcasts ADD COLUMN repeat_time TEXT")
        except Exception:
            pass

        if recover_interrupted:
            # A process can stop in the middle of a delivery. Such broadcasts
            # cannot be resumed safely without per-recipient delivery state.
            await db.execute("""
                UPDATE broadcasts
                SET status = 'failed', completed_at = COALESCE(completed_at, datetime('now', 'localtime'))
                WHERE status = 'in_progress'
            """)

        # Clean up any mistakenly recorded future dates so users will receive the real notifications once published
        try:
            tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            await db.execute("DELETE FROM notified_schedules WHERE schedule_date > ?", (tomorrow_str,))
        except Exception:
            pass

        # Seed bot_admins from config.ADMIN_IDS
        for a_id in ADMIN_IDS:
            await db.execute("INSERT OR IGNORE INTO bot_admins (user_id) VALUES (?)", (a_id,))

        # Seed bot_stat_admins from config.STAT_ADMIN_IDS
        for sa_id in STAT_ADMIN_IDS:
            await db.execute("INSERT OR IGNORE INTO bot_stat_admins (user_id) VALUES (?)", (sa_id,))

        await db.commit()

        # Load maintenance cache
        try:
            async with db.execute("SELECT value FROM bot_settings WHERE key = 'maintenance_mode'") as cursor:
                row = await cursor.fetchone()
                _MAINTENANCE_CACHE = (row[0] == "1") if row else False
        except Exception:
            _MAINTENANCE_CACHE = False

        # Load admin ids cache
        try:
            async with db.execute("SELECT user_id FROM bot_admins") as cursor:
                rows = await cursor.fetchall()
                _ADMIN_IDS_CACHE = set(ADMIN_IDS) | {r[0] for r in rows}
        except Exception:
            _ADMIN_IDS_CACHE = set(ADMIN_IDS)

        # Load stat admin ids cache
        try:
            async with db.execute("SELECT user_id FROM bot_stat_admins") as cursor:
                rows = await cursor.fetchall()
                _STAT_ADMIN_IDS_CACHE = set(STAT_ADMIN_IDS) | {r[0] for r in rows}
        except Exception:
            _STAT_ADMIN_IDS_CACHE = set(STAT_ADMIN_IDS)


async def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None


async def ensure_user(
    user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None
):
    """Регистрирует пользователя при первом обращении, если его ещё нет в базе."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        now = datetime.now().isoformat()
        await db.execute("""
            INSERT INTO users (user_id, username, first_name, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = COALESCE(excluded.username, users.username),
                first_name = COALESCE(excluded.first_name, users.first_name),
                updated_at = excluded.updated_at
        """, (user_id, username, first_name, now))
        await db.commit()


async def set_user_group(
    user_id: int,
    group_id: str,
    group_name: str,
    username: Optional[str] = None,
    first_name: Optional[str] = None
):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        now = datetime.now().isoformat()
        await db.execute("""
            INSERT INTO users (user_id, username, first_name, group_id, group_name, notifications, updated_at)
            VALUES (?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = COALESCE(excluded.username, users.username),
                first_name = COALESCE(excluded.first_name, users.first_name),
                group_id = excluded.group_id,
                group_name = excluded.group_name,
                updated_at = excluded.updated_at
        """, (user_id, username, first_name, str(group_id), group_name, now))
        await db.commit()


async def set_user_teacher(
    user_id: int,
    teacher_id: str,
    teacher_name: str
):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        now = datetime.now().isoformat()
        await db.execute("""
            INSERT INTO users (user_id, teacher_id, teacher_name, notifications, updated_at)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                teacher_id = excluded.teacher_id,
                teacher_name = excluded.teacher_name,
                updated_at = excluded.updated_at
        """, (user_id, str(teacher_id), teacher_name, now))
        await db.commit()


async def toggle_user_notifications(user_id: int) -> bool:
    """Toggles notifications for user. Returns new state: True if enabled, False if disabled."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT notifications FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            curr = row["notifications"] if row and row["notifications"] is not None else 1
            new_val = 0 if curr == 1 else 1
        
        await db.execute(
            "UPDATE users SET notifications = ?, updated_at = ? WHERE user_id = ?",
            (new_val, datetime.now().isoformat(), user_id)
        )
        await db.commit()
        return (new_val == 1)


async def disable_user_notifications(user_id: int):
    """Disables notifications for a user who permanently blocked the bot."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE users SET notifications = 0 WHERE user_id = ?", (user_id,))
        await db.commit()


async def get_users_for_notifications() -> list:
    """Returns all users with notifications enabled and assigned group or teacher."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = """
            SELECT user_id, username, first_name, group_id, group_name, teacher_id, teacher_name
            FROM users
            WHERE (notifications IS NULL OR notifications = 1)
              AND ((group_id IS NOT NULL AND group_id != '') OR (teacher_id IS NOT NULL AND teacher_id != ''))
        """
        async with db.execute(query) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def is_user_notified(
    user_id: int,
    target_type: str,
    target_id: str,
    schedule_date: str,
    schedule_fingerprint: Optional[str] = None
) -> bool:
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            query = """
                SELECT schedule_fingerprint FROM notified_schedules
                WHERE user_id = ? AND target_type = ? AND target_id = ? AND schedule_date = ?
            """
            async with db.execute(query, (user_id, target_type, str(target_id), schedule_date)) as cursor:
                row = await cursor.fetchone()
                if row is None:
                    return False
                if schedule_fingerprint is None:
                    return True
                return row[0] == schedule_fingerprint
    except Exception as e:
        logger.warning(f"Ошибка при проверке уведомления пользователя {user_id}: {e}")
        try:
            await init_db()
        except Exception:
            pass
        return False


async def mark_user_notified(
    user_id: int,
    target_type: str,
    target_id: str,
    schedule_date: str,
    schedule_fingerprint: Optional[str] = None
):
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            query = """
                INSERT INTO notified_schedules (
                    user_id, target_type, target_id, schedule_date, schedule_fingerprint
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, target_type, target_id, schedule_date) DO UPDATE SET
                    schedule_fingerprint = excluded.schedule_fingerprint,
                    notified_at = CURRENT_TIMESTAMP
            """
            await db.execute(
                query,
                (user_id, target_type, str(target_id), schedule_date, schedule_fingerprint)
            )
            await db.commit()
    except Exception as e:
        logger.warning(f"Ошибка при сохранении уведомления пользователя {user_id}: {e}")
        try:
            await init_db()
        except Exception:
            pass


async def is_maintenance_mode() -> bool:
    """Проверяет, включен ли режим технического обслуживания."""
    global _MAINTENANCE_CACHE
    if _MAINTENANCE_CACHE is not None:
        return _MAINTENANCE_CACHE
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT value FROM bot_settings WHERE key = 'maintenance_mode'") as cursor:
                row = await cursor.fetchone()
                val = (row[0] == "1") if row else False
                _MAINTENANCE_CACHE = val
                return val
    except Exception:
        return False


async def set_maintenance_mode(enabled: bool):
    """Включает или выключает технический перерыв."""
    global _MAINTENANCE_CACHE
    val_str = "1" if enabled else "0"
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("""
                INSERT INTO bot_settings (key, value) VALUES ('maintenance_mode', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """, (val_str,))
            await db.commit()
        _MAINTENANCE_CACHE = enabled
    except Exception as e:
        logger.error(f"Ошибка сохранения maintenance_mode: {e}")
        raise


async def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором."""
    if user_id in ADMIN_IDS:
        return True
    if _ADMIN_IDS_CACHE is not None:
        return user_id in _ADMIN_IDS_CACHE
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT 1 FROM bot_admins WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return True
    except Exception:
        pass
    return False


async def add_admin(user_id: int):
    """Добавляет нового администратора в базу данных."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO bot_admins (user_id) VALUES (?)", (user_id,))
        await db.commit()
    if _ADMIN_IDS_CACHE is not None:
        _ADMIN_IDS_CACHE.add(user_id)


async def remove_admin(user_id: int) -> bool:
    """Удаляет администратора (кроме корневых из конфига)."""
    if user_id in ADMIN_IDS:
        return False
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM bot_admins WHERE user_id = ?", (user_id,))
        await db.commit()
    if _ADMIN_IDS_CACHE is not None:
        _ADMIN_IDS_CACHE.discard(user_id)
    return True


async def get_admins() -> List[int]:
    """Возвращает список ID всех администраторов."""
    global _ADMIN_IDS_CACHE
    if _ADMIN_IDS_CACHE is not None:
        return list(_ADMIN_IDS_CACHE)
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT user_id FROM bot_admins") as cursor:
                rows = await cursor.fetchall()
                s = set(ADMIN_IDS) | {r[0] for r in rows}
                _ADMIN_IDS_CACHE = s
                return list(s)
    except Exception:
        return list(ADMIN_IDS)


async def is_stat_admin(user_id: int) -> bool:
    """Проверяет, имеет ли пользователь доступ к просмотру статистики."""
    if await is_admin(user_id):
        return True
    if user_id in STAT_ADMIN_IDS:
        return True
    if _STAT_ADMIN_IDS_CACHE is not None:
        return user_id in _STAT_ADMIN_IDS_CACHE
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT 1 FROM bot_stat_admins WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return True
    except Exception:
        pass
    return False


async def add_stat_admin(user_id: int):
    """Добавляет пользователя с правами просмотра статистики."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO bot_stat_admins (user_id) VALUES (?)", (user_id,))
        await db.commit()
    if _STAT_ADMIN_IDS_CACHE is not None:
        _STAT_ADMIN_IDS_CACHE.add(user_id)


async def remove_stat_admin(user_id: int) -> bool:
    """Удаляет права просмотра статистики у пользователя."""
    if user_id in STAT_ADMIN_IDS:
        return False
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM bot_stat_admins WHERE user_id = ?", (user_id,))
        await db.commit()
    if _STAT_ADMIN_IDS_CACHE is not None:
        _STAT_ADMIN_IDS_CACHE.discard(user_id)
    return True


async def get_stat_admins() -> List[int]:
    """Возвращает список ID всех администраторов статистики."""
    global _STAT_ADMIN_IDS_CACHE
    if _STAT_ADMIN_IDS_CACHE is not None:
        return list(_STAT_ADMIN_IDS_CACHE)
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT user_id FROM bot_stat_admins") as cursor:
                rows = await cursor.fetchall()
                s = set(STAT_ADMIN_IDS) | {r[0] for r in rows}
                _STAT_ADMIN_IDS_CACHE = s
                return list(s)
    except Exception:
        return list(STAT_ADMIN_IDS)


async def get_bot_stats() -> Dict[str, Any]:
    """Возвращает расширенную статистику по пользователям и активности для админ-панели."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT count(*) FROM users") as c:
            total_users = (await c.fetchone())[0]

        async with db.execute("SELECT count(*) FROM users WHERE notifications = 1") as c:
            with_notif = (await c.fetchone())[0]

        async with db.execute("SELECT count(*) FROM users WHERE group_id IS NOT NULL AND group_id != ''") as c:
            with_group = (await c.fetchone())[0]

        async with db.execute("SELECT count(*) FROM users WHERE teacher_id IS NOT NULL AND teacher_id != ''") as c:
            with_teacher = (await c.fetchone())[0]

        # Активность за последние 24 часа и 7 дней
        now = datetime.now()
        day_ago = (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

        async with db.execute(
            "SELECT count(*) FROM users WHERE datetime(updated_at) >= datetime(?)",
            (day_ago,)
        ) as c:
            active_today = (await c.fetchone())[0]

        async with db.execute(
            "SELECT count(*) FROM users WHERE datetime(updated_at) >= datetime(?)",
            (week_ago,)
        ) as c:
            active_week = (await c.fetchone())[0]

        async with db.execute("""
            SELECT group_name, count(*) as cnt
            FROM users
            WHERE group_name IS NOT NULL AND group_name != ''
            GROUP BY group_name
            ORDER BY cnt DESC
            LIMIT 5
        """) as c:
            top_groups = await c.fetchall()

        # Общая статистика по рассылкам
        async with db.execute("SELECT count(*) FROM broadcasts") as c:
            total_broadcasts = (await c.fetchone())[0]

        async with db.execute("SELECT count(*) FROM broadcasts WHERE status = 'scheduled'") as c:
            scheduled_broadcasts = (await c.fetchone())[0]

        async with db.execute("SELECT COALESCE(SUM(sent_count), 0) FROM broadcasts WHERE status = 'completed'") as c:
            total_sent_broadcast_messages = (await c.fetchone())[0]

        return {
            "total": total_users,
            "with_notif": with_notif,
            "with_group": with_group,
            "with_teacher": with_teacher,
            "active_today": active_today,
            "active_week": active_week,
            "top_groups": [(r[0], r[1]) for r in top_groups],
            "total_broadcasts": total_broadcasts,
            "scheduled_broadcasts": scheduled_broadcasts,
            "total_sent_broadcast_messages": total_sent_broadcast_messages
        }


async def get_all_user_ids() -> List[int]:
    """Возвращает список ID всех пользователей для рассылки."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT user_id FROM users") as c:
            rows = await c.fetchall()
            return [r[0] for r in rows]


# ---------- Методы работы с рассылками (таблица broadcasts) ----------

async def create_broadcast(
    created_by: int,
    message_text: str,
    pin_message: bool = False,
    scheduled_at: Optional[str] = None,
    repeat_type: str = "once",
    repeat_time: Optional[str] = None
) -> int:
    """Создает запись о новой рассылке. Возвращает broadcast_id."""
    status = "scheduled" if scheduled_at else "pending"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO broadcasts (
                created_by, created_at, scheduled_at, message_text,
                pin_message, status, repeat_type, repeat_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            created_by,
            now_str,
            scheduled_at,
            message_text,
            1 if pin_message else 0,
            status,
            repeat_type,
            repeat_time
        ))
        await db.commit()
        return cursor.lastrowid


async def get_broadcast(broadcast_id: int) -> Optional[Dict[str, Any]]:
    """Возвращает информацию о конкретной рассылке."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM broadcasts WHERE id = ?", (broadcast_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_broadcasts(limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
    """Возвращает список рассылок, отсортированных по дате создания (новые сначала)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM broadcasts ORDER BY id DESC LIMIT ? OFFSET ?"
        async with db.execute(query, (limit, offset)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_broadcasts_count() -> int:
    """Возвращает общее количество созданных рассылок."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT count(*) FROM broadcasts") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def get_due_scheduled_broadcasts() -> List[Dict[str, Any]]:
    """Возвращает список запланированных рассылок, время выполнения которых уже наступило."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = """
            SELECT * FROM broadcasts
            WHERE status = 'scheduled' AND scheduled_at IS NOT NULL AND scheduled_at <= ?
            ORDER BY scheduled_at ASC
        """
        async with db.execute(query, (now_str,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def claim_broadcast(broadcast_id: int) -> bool:
    """Atomically reserves a pending/scheduled broadcast for exactly one worker."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("""
            UPDATE broadcasts
            SET status = 'in_progress'
            WHERE id = ? AND status IN ('pending', 'scheduled')
        """, (broadcast_id,))
        await db.commit()
        return cursor.rowcount == 1


async def update_broadcast_status(
    broadcast_id: int,
    status: str,
    total_targets: Optional[int] = None,
    sent_count: Optional[int] = None,
    blocked_count: Optional[int] = None,
    failed_count: Optional[int] = None,
    completed_at: Optional[str] = None,
    scheduled_at: Optional[str] = None
):
    """Обновляет статус и результаты выполнения рассылки."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            UPDATE broadcasts SET
                status = ?,
                total_targets = COALESCE(?, total_targets),
                sent_count = COALESCE(?, sent_count),
                blocked_count = COALESCE(?, blocked_count),
                failed_count = COALESCE(?, failed_count),
                completed_at = COALESCE(?, completed_at),
                scheduled_at = COALESCE(?, scheduled_at)
            WHERE id = ?
        """, (status, total_targets, sent_count, blocked_count, failed_count, completed_at, scheduled_at, broadcast_id))
        await db.commit()


async def fail_broadcast_if_in_progress(broadcast_id: int):
    """Marks only an actively claimed broadcast as failed."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            UPDATE broadcasts
            SET status = 'failed', completed_at = datetime('now', 'localtime')
            WHERE id = ? AND status = 'in_progress'
        """, (broadcast_id,))
        await db.commit()


async def cancel_broadcast(broadcast_id: int) -> bool:
    """Отменяет запланированную рассылку, если она еще не начала выполняться."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "UPDATE broadcasts SET status = 'cancelled' WHERE id = ? AND status = 'scheduled'",
            (broadcast_id,)
        )
        await db.commit()
        return cursor.rowcount == 1


async def get_broadcasts_summary() -> Dict[str, Any]:
    """Возвращает сводную статистику по всем рассылкам."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT count(*) FROM broadcasts") as c:
            total = (await c.fetchone())[0]

        async with db.execute("SELECT count(*) FROM broadcasts WHERE status = 'completed'") as c:
            completed = (await c.fetchone())[0]

        async with db.execute("SELECT count(*) FROM broadcasts WHERE status = 'scheduled'") as c:
            scheduled = (await c.fetchone())[0]

        async with db.execute("SELECT count(*) FROM broadcasts WHERE status = 'cancelled'") as c:
            cancelled = (await c.fetchone())[0]

        async with db.execute("SELECT count(*) FROM broadcasts WHERE status = 'failed'") as c:
            failed = (await c.fetchone())[0]

        async with db.execute("""
            SELECT
                COALESCE(SUM(total_targets), 0),
                COALESCE(SUM(sent_count), 0),
                COALESCE(SUM(blocked_count), 0),
                COALESCE(SUM(failed_count), 0)
            FROM broadcasts
            WHERE status = 'completed'
        """) as c:
            row = await c.fetchone()
            sum_targets, sum_sent, sum_blocked, sum_failed = row

        return {
            "total": total,
            "completed": completed,
            "scheduled": scheduled,
            "cancelled": cancelled,
            "failed": failed,
            "sum_targets": sum_targets,
            "sum_sent": sum_sent,
            "sum_blocked": sum_blocked,
            "sum_failed": sum_failed
        }
