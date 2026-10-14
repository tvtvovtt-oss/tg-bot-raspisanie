"""Тесты на исправления по результатам аудита проекта."""
import asyncio
import sqlite3
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.methods import SendMessage
from aiogram.types import Message

import backup_service
import broadcast_service
import database
import delivery
import handlers
import keyboards
import middlewares
import notifier
import parser
import timeutil
from config import MAX_LIST_BUTTONS
from premium_emoji import te


def make_group(i):
    return {"id": str(i), "name": f"ИС-{i}", "out_name": f"ИС-{i}", "kurs": 1, "form": "fulltime"}


async def make_temp_db(test):
    """Подменяет путь к БД во всех модулях на временный файл."""
    test.temp_dir = tempfile.TemporaryDirectory()
    test.db_path = str(Path(test.temp_dir.name) / "test.db")
    # Не даём init_db подтянуть локальный bot.db из рабочей папки.
    conn = sqlite3.connect(test.db_path)
    conn.execute("PRAGMA user_version = 1")
    conn.close()
    test.original_paths = (database.DATABASE_PATH, backup_service.DATABASE_PATH)
    database.DATABASE_PATH = test.db_path
    backup_service.DATABASE_PATH = test.db_path
    await database.init_db()


def drop_temp_db(test):
    database.DATABASE_PATH, backup_service.DATABASE_PATH = test.original_paths
    test.temp_dir.cleanup()


# ---------------------------------------------------------------- время
class TimezoneTests(unittest.TestCase):
    def test_now_local_follows_configured_timezone_not_server_clock(self):
        plus_five = timezone(timedelta(hours=5))
        with patch.object(timeutil, "BOT_TZ", plus_five):
            expected = datetime.now(plus_five).replace(tzinfo=None)
            self.assertLess(abs((timeutil.now_local() - expected).total_seconds()), 5)
            self.assertIsNone(timeutil.now_local().tzinfo)

    def test_next_daily_run_is_tomorrow_at_requested_time(self):
        self.assertEqual(
            database.next_daily_run_str("07:00", datetime(2026, 10, 14, 6, 0)),
            "2026-10-15 07:00:00",
        )

    def test_dockerfile_pins_the_timezone(self):
        dockerfile = (Path(__file__).resolve().parent.parent / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("TZ=", dockerfile)


# ---------------------------------------------------------------- парсинг ввода времени
class CustomTimeParsingTests(unittest.TestCase):
    NOW = datetime(2026, 10, 14, 15, 0)

    def parse(self, raw):
        with patch.object(handlers, "now_local", return_value=self.NOW):
            return handlers.parse_custom_scheduled_time(raw)

    def test_time_with_colon_is_accepted(self):
        dt, err = self.parse("18:30")
        self.assertIsNone(err)
        self.assertEqual(dt, datetime(2026, 10, 14, 18, 30))

    def test_time_already_passed_moves_to_tomorrow(self):
        dt, _ = self.parse("10:00")
        self.assertEqual(dt, datetime(2026, 10, 15, 10, 0))

    def test_bare_date_is_not_mistaken_for_time(self):
        dt, err = self.parse("12.09")
        self.assertIsNone(dt)
        self.assertIn("ДД.ММ ЧЧ:ММ", err)

    def test_past_date_without_year_is_rejected_instead_of_jumping_a_year(self):
        dt, err = self.parse("12.09 10:00")
        self.assertIsNone(dt)
        self.assertIn("ГГГГ", err)

    def test_future_date_without_year_is_accepted(self):
        dt, err = self.parse("12.12 10:00")
        self.assertIsNone(err)
        self.assertEqual(dt, datetime(2026, 12, 12, 10, 0))

    def test_explicit_year_in_the_past_is_rejected(self):
        dt, err = self.parse("12.09.2026 10:00")
        self.assertIsNone(dt)
        self.assertIn("прошло", err)


# ---------------------------------------------------------------- поиск и списки
class SearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_punctuation_only_teacher_query_returns_nothing(self):
        staff = {
            str(i): {"id": str(i), "fio": f"Фамилия{i} Имя Отчество", "short_fio": f"Ф{i}", "is_teacher": 1}
            for i in range(1, 30)
        }
        with patch.object(parser, "get_staffs", AsyncMock(return_value=staff)):
            for query in ("-", "...", "()", "  ", "_"):
                self.assertEqual(await parser.search_teachers(query), [], query)
            self.assertEqual(len(await parser.search_teachers("Фамилия1")), 11)

    async def test_group_search_is_not_truncated_by_the_parser(self):
        groups = {str(i): make_group(i) for i in range(100, 200)}
        with patch.object(parser, "get_groups", AsyncMock(return_value=groups)):
            self.assertEqual(len(await parser.search_groups("ис")), 100)

    async def test_teachers_by_letter_returns_all(self):
        staff = {
            str(i): {"id": str(i), "fio": f"Иванов{i} Иван Иванович", "short_fio": f"И{i}", "is_teacher": 1}
            for i in range(60)
        }
        with patch.object(parser, "get_staffs", AsyncMock(return_value=staff)):
            self.assertEqual(len(await parser.get_teachers_by_letter("И")), 60)


class ListTruncationTests(unittest.TestCase):
    def test_keyboards_cap_buttons_below_telegram_limit(self):
        groups = [make_group(i) for i in range(200)]
        kb = keyboards.get_groups_search_inline_keyboard(groups, with_back_course=True)
        total_buttons = sum(len(row) for row in kb.inline_keyboard)
        self.assertLessEqual(total_buttons, 100)
        selects = [b for row in kb.inline_keyboard for b in row if b.callback_data.startswith("grp:select")]
        self.assertEqual(len(selects), MAX_LIST_BUTTONS)

        teachers = [{"id": str(i), "fio": f"Т{i}", "short_fio": f"Т{i}"} for i in range(200)]
        kb = keyboards.get_teachers_search_inline_keyboard(teachers)
        self.assertLessEqual(sum(len(row) for row in kb.inline_keyboard), 100)

        dates = [{"date": f"2026-01-{(i % 28) + 1:02d}"} for i in range(300)]
        kb = keyboards.get_dates_inline_keyboard(dates, today_str="2026-01-01")
        self.assertLessEqual(sum(len(row) for row in kb.inline_keyboard), 100)

    def test_headers_say_when_a_list_is_shortened(self):
        self.assertEqual(handlers.shown_of(12), "12")
        self.assertEqual(handlers.shown_of(MAX_LIST_BUTTONS), str(MAX_LIST_BUTTONS))
        self.assertEqual(
            handlers.shown_of(MAX_LIST_BUTTONS + 50),
            f"показаны первые {MAX_LIST_BUTTONS} из {MAX_LIST_BUTTONS + 50}",
        )


class CallsTableTests(unittest.TestCase):
    def test_calls_text_and_breaks_come_from_one_table(self):
        text = parser.get_calls_text()
        self.assertEqual(text.count("пара:"), 8)
        self.assertIn("<code>08:00 – 09:20</code> <i>(перемена 10 мин)</i>", text)
        self.assertIn("большая перемена 30 мин", text)
        self.assertTrue(text.rstrip().endswith("<code>18:40 – 20:00</code>"))
        self.assertEqual(parser.STANDARD_BREAKS, {1: 10, 2: 30, 3: 10, 4: 10, 5: 10, 6: 5, 7: 5})


# ---------------------------------------------------------------- кэш и устойчивость к сбоям сайта
class ScheduleCacheTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        parser._SCHEDULE_CACHE.clear()
        parser._FAILED_AT.clear()

    def tearDown(self):
        parser._SCHEDULE_CACHE.clear()
        parser._FAILED_AT.clear()

    async def test_repeated_requests_hit_the_cache_and_refresh_bypasses_it(self):
        calls = []

        async def loader(target_id, date_str):
            calls.append((target_id, date_str))
            return {"success": True, "lessons": [], "practices": [], "consultations": []}

        with patch.object(parser, "_load_group_schedule", loader):
            await parser.get_group_schedule("7", "2026-10-14")
            await parser.get_group_schedule("7", "2026-10-14")
            self.assertEqual(len(calls), 1)
            await parser.get_group_schedule("7", "2026-10-14", force_refresh=True)
            self.assertEqual(len(calls), 2)
            await parser.get_group_schedule("7", "2026-10-15")
            self.assertEqual(len(calls), 3)

    async def test_errors_are_not_cached(self):
        calls = []

        async def loader(target_id, date_str):
            calls.append(1)
            return {"success": False, "error": "boom", "lessons": []}

        with patch.object(parser, "_load_group_schedule", loader):
            await parser.get_group_schedule("7", "2026-10-14")
            await parser.get_group_schedule("7", "2026-10-14")
        self.assertEqual(len(calls), 2)

    async def test_site_outage_answers_fast_instead_of_waiting_for_timeout(self):
        parser._FAILED_AT["schedule"] = time.time()
        loader = AsyncMock()
        with patch.object(parser, "_load_group_schedule", loader):
            result = await parser.get_group_schedule("7", "2026-10-14")
            self.assertFalse(result["success"])
            loader.assert_not_awaited()
            # Принудительное обновление (уведомления) всё равно пытается дойти до сайта.
            loader.return_value = {"success": True, "lessons": []}
            await parser.get_group_schedule("7", "2026-10-14", force_refresh=True)
            loader.assert_awaited_once()

    async def test_invalid_identifiers_never_reach_the_site(self):
        loader = AsyncMock()
        with patch.object(parser, "_load_group_schedule", loader):
            for group_id, date_str in (("../x", "2026-10-14"), ("7", "2026-10-14/../../x"), ("7", "")):
                result = await parser.get_group_schedule(group_id, date_str)
                self.assertFalse(result["success"])
        loader.assert_not_awaited()

    async def test_cache_size_is_bounded(self):
        async def loader(target_id, date_str):
            return {"success": True, "lessons": []}

        with patch.object(parser, "_load_group_schedule", loader), \
                patch.object(parser, "SCHEDULE_CACHE_MAX_ENTRIES", 5):
            for i in range(20):
                await parser.get_group_schedule(str(i), "2026-10-14")
        self.assertLessEqual(len(parser._SCHEDULE_CACHE), 5)


class DatesFallbackTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.saved = (parser._DATES_CACHE, parser._DATES_CACHE_TIME)
        parser._FAILED_AT.clear()

    def tearDown(self):
        parser._DATES_CACHE, parser._DATES_CACHE_TIME = self.saved
        parser._FAILED_AT.clear()

    async def test_outage_returns_last_known_dates_and_stops_retrying(self):
        today = timeutil.today_local_str()
        cached = {"today": today, "selected": today, "dates": [{"date": today, "on_site": True}]}
        parser._DATES_CACHE = cached
        parser._DATES_CACHE_TIME = 0  # кэш устарел
        fetch = AsyncMock(side_effect=RuntimeError("site down"))
        with patch.object(parser, "_fetch_dates", fetch):
            self.assertIs(await parser.get_available_dates(), cached)
            self.assertIs(await parser.get_available_dates(), cached)
        fetch.assert_awaited_once()  # второй вызов — в паузе после сбоя, без ожидания таймаута

    async def test_outage_without_cache_uses_generated_dates(self):
        parser._DATES_CACHE = {}
        with patch.object(parser, "_fetch_dates", AsyncMock(return_value=None)):
            result = await parser.get_available_dates()
        self.assertEqual(result["today"], timeutil.today_local_str())
        self.assertTrue(result["dates"])


# ---------------------------------------------------------------- база данных
class DatabaseFixTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await make_temp_db(self)

    async def asyncTearDown(self):
        drop_temp_db(self)

    async def baseline_flag(self, user_id):
        users = await database.get_users_for_notifications()
        return {u["user_id"]: u["baseline_pending"] for u in users}[user_id]

    async def test_new_target_requires_a_silent_baseline(self):
        await database.set_user_group(1, "7", "ИС-26")
        self.assertEqual(await self.baseline_flag(1), 1)

        await database.clear_baseline_pending([1])
        await database.set_user_group(1, "7", "ИС-26")  # та же группа
        self.assertEqual(await self.baseline_flag(1), 0)

        await database.set_user_group(1, "8", "ИС-25")  # другая группа
        self.assertEqual(await self.baseline_flag(1), 1)

        await database.clear_baseline_pending([1])
        await database.set_user_teacher(1, "99", "Агеева А.П.")
        self.assertEqual(await self.baseline_flag(1), 1)

    async def test_reenabling_notifications_requires_a_baseline(self):
        await database.set_user_group(1, "7", "ИС-26")
        await database.clear_baseline_pending([1])
        self.assertFalse(await database.toggle_user_notifications(1))  # выключили
        await database.toggle_user_notifications(1)                    # включили
        self.assertEqual(await self.baseline_flag(1), 1)

    async def test_bulk_notified_lookup(self):
        await database.mark_user_notified(1, "group", "7", "2099-01-01", "fp-a")
        await database.mark_user_notified(2, "group", "7", "2099-01-01", "fp-b")
        await database.mark_user_notified(3, "group", "8", "2099-01-01", "fp-c")
        self.assertEqual(
            await database.get_notified_fingerprints("group", "7", "2099-01-01"),
            {1: "fp-a", 2: "fp-b"},
        )

    async def test_old_notification_log_is_pruned_and_future_rows_survive_runtime_init(self):
        await database.mark_user_notified(1, "group", "7", "2000-01-01", "old")
        await database.mark_user_notified(1, "group", "7", "2099-01-01", "future")

        await database.init_db()  # повторный init во время работы
        self.assertEqual(await database.get_notified_fingerprints("group", "7", "2000-01-01"), {})
        self.assertEqual(await database.get_notified_fingerprints("group", "7", "2099-01-01"), {1: "future"})

        await database.init_db(recover_interrupted=True)  # запуск бота
        self.assertEqual(await database.get_notified_fingerprints("group", "7", "2099-01-01"), {})

    async def test_notified_at_uses_the_bot_timezone(self):
        plus_five = timezone(timedelta(hours=5))
        with patch.object(timeutil, "BOT_TZ", plus_five):
            await database.mark_user_notified(1, "group", "7", "2099-01-01", "fp")
            expected = datetime.now(plus_five).replace(tzinfo=None)
        conn = sqlite3.connect(self.db_path)
        stored = conn.execute("SELECT notified_at FROM notified_schedules").fetchone()[0]
        conn.close()
        self.assertLess(abs((datetime.strptime(stored, "%Y-%m-%d %H:%M:%S") - expected).total_seconds()), 5)


# ---------------------------------------------------------------- уведомления
class NotifierFixTests(unittest.IsolatedAsyncioTestCase):
    USER = {"user_id": 42, "group_id": "7", "group_name": "ИС-26", "teacher_id": None}
    DATES = {"today": "2099-01-01", "dates": [{"date": "2099-01-01", "on_site": True}]}
    SCHEDULE = {"success": True, "lessons": [{"pair": "1"}], "practices": [], "consultations": [], "alerts": []}

    async def run_cycle(self, user, notified, send_outcome="sent"):
        mocks = {
            "send": AsyncMock(return_value=send_outcome),
            "mark": AsyncMock(),
            "clear": AsyncMock(),
        }
        original_first_run = notifier._IS_FIRST_RUN
        notifier._IS_FIRST_RUN = False
        try:
            with (
                patch("config.ENABLE_NOTIFICATIONS", True),
                patch.object(notifier, "is_maintenance_mode", AsyncMock(return_value=False)),
                patch.object(notifier, "get_available_dates", AsyncMock(return_value=self.DATES)),
                patch.object(notifier, "get_users_for_notifications", AsyncMock(return_value=[user])),
                patch.object(notifier, "get_notified_fingerprints", AsyncMock(return_value=notified)),
                patch.object(notifier, "get_group_schedule", AsyncMock(return_value=self.SCHEDULE)),
                patch.object(notifier, "format_schedule_message", return_value="schedule"),
                patch.object(notifier, "get_schedule_nav_inline_keyboard", return_value=None),
                patch.object(notifier, "_send_notification", mocks["send"]),
                patch.object(notifier, "mark_user_notified", mocks["mark"]),
                patch.object(notifier, "clear_baseline_pending", mocks["clear"]),
            ):
                await notifier.check_and_notify_users(object())
        finally:
            notifier._IS_FIRST_RUN = original_first_run
        return mocks

    async def test_new_subscriber_gets_no_burst_of_old_notifications(self):
        user = {**self.USER, "baseline_pending": 1}
        mocks = await self.run_cycle(user, notified={})
        mocks["send"].assert_not_awaited()
        mocks["mark"].assert_awaited_once()
        self.assertEqual(mocks["mark"].await_args.args[:4], (42, "group", "7", "2099-01-01"))
        mocks["clear"].assert_awaited_once_with([42])

    async def test_regular_subscriber_is_notified_about_new_schedule(self):
        mocks = await self.run_cycle({**self.USER, "baseline_pending": 0}, notified={})
        mocks["send"].assert_awaited_once()
        mocks["mark"].assert_awaited_once()

    async def test_unchanged_schedule_is_not_sent_twice_but_a_changed_one_is(self):
        fingerprint = notifier.schedule_fingerprint(self.SCHEDULE)
        mocks = await self.run_cycle({**self.USER, "baseline_pending": 0}, notified={42: fingerprint})
        mocks["send"].assert_not_awaited()

        mocks = await self.run_cycle({**self.USER, "baseline_pending": 0}, notified={42: "old-fingerprint"})
        mocks["send"].assert_awaited_once()

    async def test_blocked_user_is_switched_off(self):
        with (
            patch.object(notifier, "disable_user_notifications", AsyncMock()) as disable,
            patch.object(notifier, "mark_user_blocked", AsyncMock()) as blocked,
        ):
            mocks = await self.run_cycle({**self.USER, "baseline_pending": 0}, notified={}, send_outcome="blocked")
        mocks["mark"].assert_not_awaited()
        disable.assert_awaited_once_with(42)
        blocked.assert_awaited_once_with(42)

    async def test_cycle_is_skipped_while_database_is_being_restored(self):
        database.set_restore_in_progress(True)
        try:
            get_users = AsyncMock()
            with (
                patch("config.ENABLE_NOTIFICATIONS", True),
                patch.object(notifier, "is_maintenance_mode", AsyncMock(return_value=False)),
                patch.object(notifier, "get_users_for_notifications", get_users),
            ):
                await notifier.check_and_notify_users(object())
            get_users.assert_not_awaited()
        finally:
            database.set_restore_in_progress(False)


# ---------------------------------------------------------------- доставка
class DeliveryTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def method():
        return SendMessage(chat_id=1, text="x")

    class FakeBot:
        def __init__(self, errors):
            self.errors = list(errors)
            self.calls = []

        async def send_message(self, **kwargs):
            self.calls.append(kwargs)
            if self.errors:
                error = self.errors.pop(0)
                if error:
                    raise error
            return SimpleNamespace(message_id=10)

    async def test_blocked_user(self):
        bot = self.FakeBot([TelegramForbiddenError(self.method(), "Forbidden: bot was blocked")])
        message, outcome = await delivery.send_with_retry(bot, 1, "hi")
        self.assertEqual((message, outcome), (None, "blocked"))
        self.assertEqual(len(bot.calls), 1)

    async def test_flood_control_is_retried(self):
        bot = self.FakeBot([TelegramRetryAfter(self.method(), "Too Many Requests", 1)])
        with patch.object(delivery.asyncio, "sleep", AsyncMock()) as sleep:
            message, outcome = await delivery.send_with_retry(bot, 1, "hi", parse_mode="HTML")
        self.assertEqual(outcome, "sent")
        self.assertEqual(len(bot.calls), 2)
        sleep.assert_awaited_once()
        self.assertEqual(bot.calls[0]["parse_mode"], "HTML")

    async def test_markup_error_retries_without_custom_emoji_once(self):
        bad = TelegramBadRequest(self.method(), "Bad Request: can't parse entities")
        bot = self.FakeBot([bad])
        text = f"{te('123', '⚙️')} hello"
        _, outcome = await delivery.send_with_retry(bot, 1, text)
        self.assertEqual(outcome, "sent")
        self.assertIn("<tg-emoji", bot.calls[0]["text"])
        self.assertNotIn("<tg-emoji", bot.calls[1]["text"])

    async def test_plain_bad_request_is_a_failure_without_endless_retries(self):
        bot = self.FakeBot([TelegramBadRequest(self.method(), "message is too long")] * 5)
        _, outcome = await delivery.send_with_retry(bot, 1, "plain text")
        self.assertEqual(outcome, "failed")
        self.assertEqual(len(bot.calls), 1)


class BackgroundTaskTests(unittest.IsolatedAsyncioTestCase):
    async def test_spawned_tasks_are_referenced_and_cancelled_on_shutdown(self):
        started = asyncio.Event()

        async def long_running():
            started.set()
            await asyncio.sleep(60)

        task = broadcast_service.spawn_background(long_running())
        await started.wait()
        self.assertIn(task, broadcast_service._BACKGROUND_TASKS)

        await broadcast_service.cancel_background_tasks()
        self.assertTrue(task.cancelled())
        self.assertNotIn(task, broadcast_service._BACKGROUND_TASKS)


# ---------------------------------------------------------------- рассылка: ввод текста
class BroadcastTextValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_text_over_telegram_limit_is_rejected_immediately(self):
        state, answer = await self._submit_text("А" * 5000)
        state.update_data.assert_not_awaited()
        self.assertIn("слишком длинный", answer.await_args.args[1])

    async def test_length_is_counted_like_telegram_does(self):
        # 2100 эмодзи = 2100 символов Python, но 4200 в UTF-16 — это больше лимита.
        state, answer = await self._submit_text("😀" * 2100)
        state.update_data.assert_not_awaited()
        self.assertIn("слишком длинный", answer.await_args.args[1])

    async def test_media_without_text_is_rejected_with_a_clear_message(self):
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=1), text=None, caption="подпись к фото", html_text="подпись к фото"
        )
        state, answer = AsyncMock(), AsyncMock()
        with (
            patch.object(handlers, "is_admin", AsyncMock(return_value=True)),
            patch.object(handlers, "safe_answer", answer),
        ):
            await handlers.handle_broadcast_text_input(message, state)
        state.update_data.assert_not_awaited()
        self.assertIn("текстовое", answer.await_args.args[1])

    async def test_normal_text_is_accepted(self):
        state, answer = await self._submit_text("Всем привет!", html_text="<b>Всем привет!</b>")
        state.update_data.assert_awaited_once()
        self.assertEqual(state.update_data.await_args.kwargs["broadcast_text"], "<b>Всем привет!</b>")
        self.assertEqual(state.update_data.await_args.kwargs["total_users"], 3)

    async def test_exactly_at_the_limit_is_accepted(self):
        state, _ = await self._submit_text("А" * 4096)
        state.update_data.assert_awaited_once()

    async def _submit_text(self, text, html_text=None):
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=1), text=text, caption=None, html_text=html_text or text
        )
        state, answer = AsyncMock(), AsyncMock()
        with (
            patch.object(handlers, "is_admin", AsyncMock(return_value=True)),
            patch.object(handlers, "get_all_user_ids", AsyncMock(return_value=[1, 2, 3])),
            patch.object(handlers, "safe_answer", answer),
        ):
            await handlers.handle_broadcast_text_input(message, state)
        return state, answer


# ---------------------------------------------------------------- бэкапы и восстановление
class BackupFixTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await make_temp_db(self)

    async def asyncTearDown(self):
        drop_temp_db(self)

    class RecordingBot:
        def __init__(self):
            self.sent = []
            self.pinned = []

        async def send_document(self, **kwargs):
            self.sent.append(kwargs)
            return SimpleNamespace(message_id=77)

        async def pin_chat_message(self, **kwargs):
            self.pinned.append(kwargs)

    async def test_empty_snapshot_does_not_overwrite_the_good_backup(self):
        bot = self.RecordingBot()
        path = await backup_service.create_safe_sqlite_backup_async()
        with patch.object(backup_service, "BACKUP_CHANNEL_ID", -100123):
            result = await backup_service.send_backup_to_channel(bot, backup_file_path=path)
        self.assertIsNone(result)
        self.assertEqual(bot.sent, [])
        self.assertEqual(bot.pinned, [])

    async def test_snapshot_with_users_is_uploaded_and_pinned(self):
        await database.ensure_user(1, "user", "User")
        bot = self.RecordingBot()
        path = await backup_service.create_safe_sqlite_backup_async()
        with patch.object(backup_service, "BACKUP_CHANNEL_ID", -100123):
            result = await backup_service.send_backup_to_channel(bot, backup_file_path=path)
        self.assertIsNotNone(result)
        self.assertEqual(len(bot.sent), 1)
        self.assertEqual(bot.pinned[0]["message_id"], 77)

    async def test_corrupt_snapshot_is_not_uploaded(self):
        bad = Path(self.temp_dir.name) / "bad.db"
        bad.write_bytes(b"this is not a sqlite database" * 100)
        bot = self.RecordingBot()
        with patch.object(backup_service, "BACKUP_CHANNEL_ID", -100123):
            result = await backup_service.send_backup_to_channel(bot, backup_file_path=str(bad))
        self.assertIsNone(result)
        self.assertEqual(bot.sent, [])

    async def test_restore_flag_is_raised_during_restore_and_always_cleared(self):
        seen = []

        def fake_restore(source, destination):
            seen.append(database.is_restore_in_progress())
            return 3

        with patch.object(backup_service, "restore_sqlite_backup", fake_restore), \
                patch.object(backup_service, "RESTORE_GRACE_SECONDS", 0):
            self.assertEqual(await backup_service.restore_sqlite_backup_async("a", "b"), 3)
        self.assertEqual(seen, [True])
        self.assertFalse(database.is_restore_in_progress())

        def failing_restore(source, destination):
            raise ValueError("broken backup")

        with patch.object(backup_service, "restore_sqlite_backup", failing_restore), \
                patch.object(backup_service, "RESTORE_GRACE_SECONDS", 0):
            with self.assertRaises(ValueError):
                await backup_service.restore_sqlite_backup_async("a", "b")
        self.assertFalse(database.is_restore_in_progress())


class RestoreMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self):
        database.set_restore_in_progress(False)

    async def test_activity_is_not_written_while_restoring(self):
        database.set_restore_in_progress(True)
        handler = AsyncMock(return_value="ok")
        with patch.object(middlewares, "ensure_user", AsyncMock()) as ensure_user:
            result = await middlewares.UserActivityMiddleware()(
                handler, object(), {"event_from_user": SimpleNamespace(id=5, username="u", first_name="U")}
            )
        ensure_user.assert_not_awaited()
        handler.assert_awaited_once()
        self.assertEqual(result, "ok")

    async def test_regular_users_see_a_pause_message_but_admins_pass(self):
        database.set_restore_in_progress(True)
        event = MagicMock(spec=Message)
        event.answer = AsyncMock()
        data = {"event_from_user": SimpleNamespace(id=5)}
        handler = AsyncMock()

        with patch.object(middlewares, "is_maintenance_mode", AsyncMock(return_value=False)), \
                patch.object(middlewares, "is_admin", AsyncMock(return_value=False)), \
                patch.object(middlewares, "is_stat_admin", AsyncMock(return_value=False)):
            await middlewares.MaintenanceMiddleware()(handler, event, data)
        handler.assert_not_awaited()
        event.answer.assert_awaited_once()

        with patch.object(middlewares, "is_maintenance_mode", AsyncMock(return_value=False)), \
                patch.object(middlewares, "is_admin", AsyncMock(return_value=True)):
            await middlewares.MaintenanceMiddleware()(handler, event, data)
        handler.assert_awaited_once()


class ConfigTests(unittest.TestCase):
    def test_importing_config_does_not_require_a_token(self):
        import config
        with patch.object(config, "BOT_TOKEN", ""):
            with self.assertRaises(ValueError):
                config.validate_config()
        with patch.object(config, "BOT_TOKEN", "123:abc"):
            config.validate_config()

    def test_bool_parsing(self):
        import config
        self.assertTrue(config.parse_bool("Yes"))
        self.assertTrue(config.parse_bool("1"))
        self.assertFalse(config.parse_bool("no"))
        self.assertFalse(config.parse_bool(""))
        self.assertTrue(config.parse_bool("", default=True))


if __name__ == "__main__":
    unittest.main()
