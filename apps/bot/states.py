"""FSM только для ожидания свободного ввода. Прогресс опроса живёт в Postgres."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class TriageFlow(StatesGroup):
    waiting_complaint = State()
    waiting_answer_text = State()
    confirming_pain_point = State()
    choosing_route = State()
    waiting_self_rehab_consent = State()


class TrackerFlow(StatesGroup):
    waiting_reminder_time = State()
    collecting_tasks = State()
    waiting_note = State()
