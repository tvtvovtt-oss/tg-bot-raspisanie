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
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            INSERT INTO users (user_id, username, first_name, group_id, group_name, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
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
            INSERT INTO users (user_id, teacher_id, teacher_name, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                teacher_id = excluded.teacher_id,
                teacher_name = excluded.teacher_name,
                updated_at = excluded.updated_at
        """, (user_id, str(teacher_id), teacher_name, now))
        await db.commit()
