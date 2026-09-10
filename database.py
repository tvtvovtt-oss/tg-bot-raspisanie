import aiosqlite
from datetime import datetime
from typing import Optional, Dict, Any
from config import DATABASE_PATH


async def init_db():
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
        await db.commit()


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
    async with aiosqlite.connect(DATABASE_PATH) as db:
        query = """
            SELECT 1 FROM notified_schedules
            WHERE user_id = ? AND target_type = ? AND target_id = ? AND schedule_date = ?
        """
        async with db.execute(query, (user_id, target_type, str(target_id), schedule_date)) as cursor:
            row = await cursor.fetchone()
            return row is not None


async def mark_user_notified(user_id: int, target_type: str, target_id: str, schedule_date: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        query = """
            INSERT OR IGNORE INTO notified_schedules (user_id, target_type, target_id, schedule_date)
            VALUES (?, ?, ?, ?)
        """
        await db.execute(query, (user_id, target_type, str(target_id), schedule_date))
        await db.commit()
