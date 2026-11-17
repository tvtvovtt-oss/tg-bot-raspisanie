"""Хендлеры виджета «Расписание»: команда /widget и запросы виджета (widget_query)."""
import asyncio
import html
import logging
from typing import Optional

from aiogram import Router, Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, WidgetQuery

from database import get_user
from parser import (
    get_available_dates,
    get_group_schedule,
    format_schedule_message,
)
from timeutil import today_local_str
from widget import (
    build_day_payload,
    DEMO_PREFIX,
    build_demo_payload,
    build_widget_html,
    check_widget_size,
    fit_payload,
    is_allowed_date,
)

logger = logging.getLogger(__name__)
widget_router = Router()

# Telegram даёт 15 секунд на ответ виджету; запас оставляем на сам вызов API.
WIDGET_ANSWER_DEADLINE = 12.0


@widget_router.message(Command("widget"))
async def cmd_widget(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    if message.chat.type != "private":
        await message.answer("Виджет работает только в личном чате с ботом. Напиши мне в личку: /widget")
        return

    user = await get_user(message.from_user.id)
    if not user or not user.get("group_id"):
        await message.answer(
            "Сначала укажи свою группу: напиши в чат её номер или первые буквы "
            "(например: <code>253</code> или <code>ИС</code>), потом снова /widget."
        )
        return

    dates_info = await get_available_dates()
    today_str = dates_info.get("today") or today_local_str()
    sched = await get_group_schedule(user["group_id"], today_str)

    try:
        html_text = build_widget_html(build_day_payload(sched, user["group_name"], today_str))
        check_widget_size(html_text)
        await bot.send_widget(
            chat_id=message.chat.id,
            html=html_text,
            allow_queries=True,
            caption=f"Расписание группы {user['group_name']}",
            parse_mode=None,
        )
    except (TelegramAPIError, ValueError) as e:
        # Виджеты могут быть недоступны (клиент/сервер Telegram) — отвечаем обычным расписанием.
        logger.warning("Не удалось отправить виджет пользователю %s: %s", message.from_user.id, e)
        text = format_schedule_message(sched, user["group_name"], today_str, "Сегодня")
        await message.answer("Виджет сейчас недоступен, вот расписание обычным сообщением:\n\n" + text)


@widget_router.message(Command("widgettest", "widgetdemo"))
async def cmd_widget_demo(message: Message, state: FSMContext, bot: Bot):
    """Демо-виджет с выдуманным расписанием: не ходит на сайт и не требует группы."""
    await state.clear()
    if message.chat.type != "private":
        await message.answer("Виджет работает только в личном чате с ботом.")
        return
    try:
        html_text = build_widget_html(build_demo_payload(today_local_str()), prefix=DEMO_PREFIX)
        check_widget_size(html_text)
        await bot.send_widget(
            chat_id=message.chat.id,
            html=html_text,
            allow_queries=True,
            caption="Демо-виджет: расписание выдуманное, сайт техникума не используется",
            parse_mode=None,
        )
    except (TelegramAPIError, ValueError) as e:
        logger.warning("Демо-виджет не отправился пользователю %s: %s", message.from_user.id, e)
        await message.answer(f"Telegram не принял виджет: <code>{html.escape(str(e))}</code>")


async def _answer_for_query(query: WidgetQuery) -> str:
    """JSON ответа на запрос виджета 'd:ГГГГ-ММ-ДД'. Любая проблема — {"e": текст}, а не молчание (иначе TIMEOUT)."""
    data = query.data or ""
    if data.startswith(DEMO_PREFIX):
        if not is_allowed_date(data[2:]):
            return '{"e":"Некорректный запрос"}'
        return fit_payload(build_demo_payload(data[2:]))
    if not data.startswith("d:") or not is_allowed_date(data[2:]):
        return '{"e":"Некорректный запрос"}'
    date_str = data[2:]

    user = await get_user(query.from_user.id)
    if not user or not user.get("group_id"):
        return '{"e":"Сначала укажи группу в боте"}'

    sched = await get_group_schedule(user["group_id"], date_str)
    return fit_payload(build_day_payload(sched, user["group_name"], date_str))


@widget_router.widget_query()
async def on_widget_query(query: WidgetQuery, bot: Bot):
    answer: Optional[str]
    try:
        answer = await asyncio.wait_for(_answer_for_query(query), timeout=WIDGET_ANSWER_DEADLINE)
    except asyncio.TimeoutError:
        answer = '{"e":"Сайт техникума долго отвечает, попробуй ещё раз"}'
    except Exception:
        logger.exception("Ошибка обработки widget_query")
        answer = '{"e":"Внутренняя ошибка, попробуй позже"}'

    try:
        await bot.answer_widget_query(widget_query_id=query.id, data=answer)
    except TelegramAPIError as e:
        logger.warning("Не удалось ответить на widget_query: %s", e)
