"""Тесты виджета «Расписание» (Bot API 10.4)."""
import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import widget
import widget_handlers


def make_sched(pairs=5, subgroups=1):
    lessons = []
    for n in range(1, pairs + 1):
        items = [{
            "subgroup": f"п/гр {k + 1}" if subgroups > 1 else "",
            "subject": "Основы проектирования баз данных и информационных систем",
            "audience": "305",
            "teacher": "Иванов Иван Иванович",
        } for k in range(subgroups)]
        lessons.append({"pair": str(n), "time": f"{8 + n}:00 - {9 + n}:30", "items": items})
    return {"success": True, "lessons": lessons, "practices": [], "consultations": [], "alerts": []}


class WidgetPayloadTests(unittest.TestCase):
    def test_short_fio(self):
        self.assertEqual(widget.short_fio("Иванов Иван Иванович"), "Иванов И.И.")
        self.assertEqual(widget.short_fio("Иванов И.И."), "Иванов И.И.")
        self.assertEqual(widget.short_fio(""), "")

    def test_payload_has_pairs_and_times(self):
        payload = widget.build_day_payload(make_sched(2), "АПТ-242", "2026-11-17")
        self.assertEqual(payload["g"], "АПТ-242")
        self.assertEqual(len(payload["p"]), 2)
        self.assertEqual(payload["p"][0][:3], ["1", "09:00", "10:30"])
        self.assertEqual(payload["p"][0][3][0][2], "Иванов И.И.")

    def test_empty_day_gets_message(self):
        sched = {"success": True, "lessons": [], "practices": [], "consultations": [], "alerts": []}
        self.assertIn("m", widget.build_day_payload(sched, "Г", "2026-11-17"))

    def test_error_is_passed_to_widget(self):
        payload = widget.build_day_payload({"success": False, "error": "сайт лежит"}, "Г", "2026-11-17")
        self.assertEqual(payload["e"], "сайт лежит")

    def test_fit_payload_respects_answer_limit(self):
        for pairs, subgroups in [(2, 1), (5, 1), (6, 3), (8, 4)]:
            payload = widget.build_day_payload(make_sched(pairs, subgroups), "АПТ-242", "2026-11-17")
            fitted = widget.fit_payload(payload)
            self.assertLessEqual(len(fitted.encode("utf-8")), widget.ANSWER_LIMIT_BYTES, (pairs, subgroups))
            json.loads(fitted)

    def test_fit_payload_keeps_small_payload_intact(self):
        payload = widget.build_day_payload(make_sched(2), "АПТ-242", "2026-11-17")
        self.assertEqual(json.loads(widget.fit_payload(payload)), payload)


class WidgetHtmlTests(unittest.TestCase):
    def test_html_within_telegram_limits(self):
        payload = widget.build_day_payload(make_sched(6, 2), "АПТ-242", "2026-11-17")
        widget.check_widget_size(widget.build_widget_html(payload))

    def test_data_cannot_break_out_of_script(self):
        payload = {"d": "2026-11-17", "g": "</script><b>x", "p": []}
        html_text = widget.build_widget_html(payload)
        self.assertEqual(html_text.count("</script>"), 1)
        self.assertNotIn("__DATA__", html_text)
        self.assertNotIn("__TZ__", html_text)

    def test_oversized_html_rejected(self):
        with self.assertRaises(ValueError):
            widget.check_widget_size("x" * (widget.HTML_LIMIT_BYTES + 1))

    def test_allowed_dates(self):
        today = widget.now_local().strftime("%Y-%m-%d")
        self.assertTrue(widget.is_allowed_date(today))
        for bad in ("", "2026-13-40", "abc", "2026-11-17; DROP", "2099-01-01", "2000-01-01"):
            self.assertFalse(widget.is_allowed_date(bad), bad)


class WidgetQueryTests(unittest.IsolatedAsyncioTestCase):
    def make_query(self, data):
        return SimpleNamespace(id="q1", data=data, from_user=SimpleNamespace(id=42))

    async def run_query(self, data, user, sched=None):
        bot = SimpleNamespace(answer_widget_query=AsyncMock())
        with patch.object(widget_handlers, "get_user", AsyncMock(return_value=user)), \
             patch.object(widget_handlers, "get_group_schedule", AsyncMock(return_value=sched or make_sched(2))):
            await widget_handlers.on_widget_query(self.make_query(data), bot)
        bot.answer_widget_query.assert_awaited_once()
        kwargs = bot.answer_widget_query.await_args.kwargs
        self.assertEqual(kwargs["widget_query_id"], "q1")
        return json.loads(kwargs["data"])

    async def test_valid_query_returns_day(self):
        today = widget.now_local().strftime("%Y-%m-%d")
        answer = await self.run_query(f"d:{today}", {"group_id": "1", "group_name": "АПТ-242"})
        self.assertEqual(answer["d"], today)
        self.assertEqual(len(answer["p"]), 2)

    async def test_bad_query_is_answered_with_error(self):
        answer = await self.run_query("hack", {"group_id": "1", "group_name": "Г"})
        self.assertIn("e", answer)

    async def test_user_without_group_is_answered(self):
        today = widget.now_local().strftime("%Y-%m-%d")
        answer = await self.run_query(f"d:{today}", None)
        self.assertIn("e", answer)

    async def test_slow_site_still_gets_answer(self):
        async def slow(*_a, **_k):
            await asyncio.sleep(1)
        today = widget.now_local().strftime("%Y-%m-%d")
        bot = SimpleNamespace(answer_widget_query=AsyncMock())
        with patch.object(widget_handlers, "WIDGET_ANSWER_DEADLINE", 0.05), \
             patch.object(widget_handlers, "get_user", AsyncMock(return_value={"group_id": "1", "group_name": "Г"})), \
             patch.object(widget_handlers, "get_group_schedule", slow):
            await widget_handlers.on_widget_query(self.make_query(f"d:{today}"), bot)
        self.assertIn("e", json.loads(bot.answer_widget_query.await_args.kwargs["data"]))


if __name__ == "__main__":
    unittest.main()
