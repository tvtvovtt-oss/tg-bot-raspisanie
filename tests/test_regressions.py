import os
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import backup_service
import database
import notifier
from handlers import render_broadcast_preview, render_broadcast_setup_text
from keyboards import get_broadcast_detail_keyboard, get_broadcast_list_keyboard, get_stat_admin_menu_keyboard
from parser import infer_course_from_group_name, parse_pair_times


def keyboard_texts(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


class ParserRegressionTests(unittest.TestCase):
    def test_course_uses_academic_year(self):
        self.assertEqual(
            infer_course_from_group_name("ИС-26", datetime(2026, 9, 1)),
            1,
        )
        self.assertEqual(
            infer_course_from_group_name("ИС-26", datetime(2027, 1, 15)),
            1,
        )
        self.assertEqual(
            infer_course_from_group_name("ИС-25", datetime(2027, 9, 1)),
            3,
        )

    def test_invalid_pair_time_does_not_crash_formatter(self):
        start, end, start_dt, end_dt = parse_pair_times("25:99-26:00")
        self.assertEqual((start, end), ("25:99", "26:00"))
        self.assertIsNone(start_dt)
        self.assertIsNone(end_dt)


class PermissionRegressionTests(unittest.TestCase):
    def test_stat_admin_keyboard_is_read_only(self):
        texts = keyboard_texts(get_stat_admin_menu_keyboard(is_full_admin=False))
        self.assertNotIn("Создать новую рассылку", texts)
        self.assertNotIn("Скачать бэкап базы данных", texts)

    def test_stat_admin_cannot_see_mutating_broadcast_buttons(self):
        list_texts = keyboard_texts(
            get_broadcast_list_keyboard([], page=0, total_pages=1, is_full_admin=False)
        )
        detail_texts = keyboard_texts(
            get_broadcast_detail_keyboard(1, is_scheduled=True, can_cancel=False)
        )
        self.assertNotIn("Создать новую рассылку", list_texts)
        self.assertNotIn("Отменить запланированную рассылку", detail_texts)

    def test_long_broadcast_preview_stays_within_telegram_limit(self):
        source = "<b>" + ("&lt;&amp;&gt;" * 2000) + "</b>"
        preview = render_broadcast_setup_text(source, False, None, 100)
        self.assertLess(len(preview), 4096)
        self.assertNotIn("<b><", preview)
        self.assertTrue(render_broadcast_preview(source).endswith("…"))


class DatabaseRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_path = database.DATABASE_PATH
        self.db_path = str(Path(self.temp_dir.name) / "test.db")
        # Prevent init_db from importing the workspace's legacy bot.db.
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA user_version = 1")
        conn.close()
        database.DATABASE_PATH = self.db_path
        await database.init_db()

    async def asyncTearDown(self):
        database.DATABASE_PATH = self.original_path
        self.temp_dir.cleanup()

    async def test_broadcast_claim_is_atomic(self):
        broadcast_id = await database.create_broadcast(1, "test")
        self.assertTrue(await database.claim_broadcast(broadcast_id))
        self.assertFalse(await database.claim_broadcast(broadcast_id))

    async def test_cancel_is_conditional_and_atomic(self):
        broadcast_id = await database.create_broadcast(
            1, "test", scheduled_at="2099-01-01 10:00:00"
        )
        self.assertTrue(await database.cancel_broadcast(broadcast_id))
        self.assertFalse(await database.cancel_broadcast(broadcast_id))

    async def test_interrupted_broadcast_is_recovered_as_failed(self):
        broadcast_id = await database.create_broadcast(1, "test")
        self.assertTrue(await database.claim_broadcast(broadcast_id))
        await database.init_db(recover_interrupted=True)
        broadcast = await database.get_broadcast(broadcast_id)
        self.assertEqual(broadcast["status"], "failed")

    async def test_existing_user_activity_timestamp_is_updated(self):
        await database.ensure_user(42, "old", "Old")
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE users SET updated_at = '2000-01-01 00:00:00' WHERE user_id = 42")
        conn.commit()
        conn.close()

        await database.ensure_user(42, "new", "New")
        user = await database.get_user(42)
        self.assertGreater(user["updated_at"], "2000-01-01 00:00:00")

    async def test_schedule_change_requires_a_new_notification(self):
        await database.mark_user_notified(42, "group", "7", "2099-01-01", "fingerprint-a")
        self.assertTrue(
            await database.is_user_notified(
                42, "group", "7", "2099-01-01", "fingerprint-a"
            )
        )
        self.assertFalse(
            await database.is_user_notified(
                42, "group", "7", "2099-01-01", "fingerprint-b"
            )
        )


class BackupRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "backup-source.db")
        self.original_database_path = database.DATABASE_PATH
        self.original_backup_path = backup_service.DATABASE_PATH
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA user_version = 1")
        conn.close()
        database.DATABASE_PATH = self.db_path
        backup_service.DATABASE_PATH = self.db_path
        await database.init_db()

    async def asyncTearDown(self):
        database.DATABASE_PATH = self.original_database_path
        backup_service.DATABASE_PATH = self.original_backup_path
        self.temp_dir.cleanup()

    async def test_backup_names_are_unique_and_valid(self):
        first = await backup_service.create_safe_sqlite_backup_async()
        second = await backup_service.create_safe_sqlite_backup_async()
        try:
            self.assertNotEqual(first, second)
            self.assertEqual(backup_service.validate_sqlite_backup(first), 0)
            self.assertEqual(backup_service.validate_sqlite_backup(second), 0)
        finally:
            backup_service.remove_local_file(first)
            backup_service.remove_local_file(second)

    async def test_failed_channel_send_removes_temporary_backup(self):
        class FailingBot:
            async def send_document(self, **kwargs):
                raise RuntimeError("network unavailable")

        backup_path = await backup_service.create_safe_sqlite_backup_async()
        with patch.object(backup_service, "BACKUP_CHANNEL_ID", -100123):
            result = await backup_service.send_backup_to_channel(
                FailingBot(), backup_file_path=backup_path, cleanup_local=True
            )
        self.assertIsNone(result)
        self.assertFalse(os.path.exists(backup_path))


class NotificationRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_transient_delivery_failure_is_not_marked_as_delivered(self):
        user = {
            "user_id": 42,
            "group_id": "7",
            "group_name": "ИС-26",
            "teacher_id": None,
        }
        dates = {
            "today": "2099-01-01",
            "dates": [{"date": "2099-01-01", "on_site": True}],
        }
        mark_mock = AsyncMock()
        original_first_run = notifier._IS_FIRST_RUN
        notifier._IS_FIRST_RUN = False
        try:
            with (
                patch("config.ENABLE_NOTIFICATIONS", True),
                patch.object(notifier, "is_maintenance_mode", AsyncMock(return_value=False)),
                patch.object(notifier, "get_available_dates", AsyncMock(return_value=dates)),
                patch.object(notifier, "get_users_for_notifications", AsyncMock(return_value=[user])),
                patch.object(notifier, "is_user_notified", AsyncMock(return_value=False)),
                patch.object(notifier, "get_group_schedule", AsyncMock(return_value={"lessons": [{}]})),
                patch.object(notifier, "is_schedule_published", return_value=True),
                patch.object(notifier, "format_schedule_message", return_value="schedule"),
                patch.object(notifier, "get_schedule_nav_inline_keyboard", return_value=None),
                patch.object(notifier, "_send_notification", AsyncMock(return_value="failed")),
                patch.object(notifier, "mark_user_notified", mark_mock),
            ):
                await notifier.check_and_notify_users(object())
        finally:
            notifier._IS_FIRST_RUN = original_first_run

        mark_mock.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
