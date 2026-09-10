import aiosqlite
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Set
from config import DATABASE_PATH, ADMIN_IDS

logger = logging.getLogger(__name__)

_MAINTENANCE_CACHE: Optional[bool] = None
_ADMIN_IDS_CACHE: Optional[Set[int]] = None


async def init_db():
    global _MAINTENANCE_CACHE, _ADMIN_IDS_CACHE
    async with aiosqlite.connect(DATABASE_PATH) as db:
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
        # In case the table already existed without notifications column
        try:
            await db.execute("ALTER TABLE users ADD COLUMN notifications INTEGER DEFAULT 1")
        except Exception:
            pass

        await db.execute("""
            CREATE TABLE IF NOT EXISTS notified_schedules (
                user_id INTEGER,
                target_type TEXT,
                target_id TEXT,
                schedule_date TEXT,
                notified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, target_type, target_id, schedule_date)
            )
        """)

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

        # Clean up any mistakenly recorded future dates so users will receive the real notifications once published
        try:
            tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            await db.execute("DELETE FROM notified_schedules WHERE schedule_date > ?", (tomorrow_str,))
        except Exception:
            pass

        # Seed bot_admins from config.ADMIN_IDS
        for a_id in ADMIN_IDS:
            await db.execute("INSERT OR IGNORE INTO bot_admins (user_id) VALUES (?)", (a_id,))

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


async def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None


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
        
        await db.execute("UPDATE users SET notifications = ? WHERE user_id = ?", (new_val, user_id))
        await db.commit()
        return (new_val == 1)


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


async def is_user_notified(user_id: int, target_type: str, target_id: str, schedule_date: str) -> bool:
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            query = """
                SELECT 1 FROM notified_schedules
                WHERE user_id = ? AND target_type = ? AND target_id = ? AND schedule_date = ?
            """
            async with db.execute(query, (user_id, target_type, str(target_id), schedule_date)) as cursor:
                row = await cursor.fetchone()
                return row is not None
    except Exception as e:
        logger.warning(f"Ошибка при проверке уведомления пользователя {user_id}: {e}")
        try:
            await init_db()
        except Exception:
            pass
        return False


async def mark_user_notified(user_id: int, target_type: str, target_id: str, schedule_date: str):
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            query = """
                INSERT OR IGNORE INTO notified_schedules (user_id, target_type, target_id, schedule_date)
                VALUES (?, ?, ?, ?)
            """
            await db.execute(query, (user_id, target_type, str(target_id), schedule_date))
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
    _MAINTENANCE_CACHE = enabled
    val_str = "1" if enabled else "0"
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("""
                INSERT INTO bot_settings (key, value) VALUES ('maintenance_mode', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """, (val_str,))
            await db.commit()
    except Exception as e:
        logger.error(f"Ошибка сохранения maintenance_mode: {e}")


async def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором."""
    global _ADMIN_IDS_CACHE
    if user_id in ADMIN_IDS:
        return True
    if _ADMIN_IDS_CACHE is not None and user_id in _ADMIN_IDS_CACHE:
        return True
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT 1 FROM bot_admins WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    if _ADMIN_IDS_CACHE is not None:
                        _ADMIN_IDS_CACHE.add(user_id)
                    return True
    except Exception:
        pass
    return False


async def add_admin(user_id: int):
    """Добавляет нового администратора в базу данных."""
    global _ADMIN_IDS_CACHE
    if _ADMIN_IDS_CACHE is not None:
        _ADMIN_IDS_CACHE.add(user_id)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO bot_admins (user_id) VALUES (?)", (user_id,))
        await db.commit()


async def remove_admin(user_id: int) -> bool:
    """Удаляет администратора (кроме корневых из конфига)."""
    global _ADMIN_IDS_CACHE
    if user_id in ADMIN_IDS:
        return False
    if _ADMIN_IDS_CACHE is not None and user_id in _ADMIN_IDS_CACHE:
        _ADMIN_IDS_CACHE.discard(user_id)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM bot_admins WHERE user_id = ?", (user_id,))
        await db.commit()
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


async def get_bot_stats() -> Dict[str, Any]:
    """Возвращает общую статистику по пользователям для админ-панели."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT count(*) FROM users") as c:
            total_users = (await c.fetchone())[0]

        async with db.execute("SELECT count(*) FROM users WHERE notifications = 1") as c:
            with_notif = (await c.fetchone())[0]

        async with db.execute("SELECT count(*) FROM users WHERE group_id IS NOT NULL AND group_id != ''") as c:
            with_group = (await c.fetchone())[0]

        async with db.execute("SELECT count(*) FROM users WHERE teacher_id IS NOT NULL AND teacher_id != ''") as c:
            with_teacher = (await c.fetchone())[0]

        async with db.execute("""
            SELECT group_name, count(*) as cnt
            FROM users
            WHERE group_name IS NOT NULL AND group_name != ''
            GROUP BY group_name
            ORDER BY cnt DESC
            LIMIT 5
        """) as c:
            top_groups = await c.fetchall()

        return {
            "total": total_users,
            "with_notif": with_notif,
            "with_group": with_group,
            "with_teacher": with_teacher,
            "top_groups": [(r[0], r[1]) for r in top_groups]
        }


async def get_all_user_ids() -> List[int]:
    """Возвращает список ID всех пользователей для рассылки."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT user_id FROM users") as c:
            rows = await c.fetchall()
            return [r[0] for r in rows]
