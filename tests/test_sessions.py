"""Tests del detector de sesiones."""
from __future__ import annotations

from datetime import datetime, timezone

from src.sessions import DEFAULT_SESSIONS, current_session, parse_sessions


def _utc(hour: int) -> datetime:
    return datetime(2026, 4, 9, hour, 0, 0, tzinfo=timezone.utc)


def test_current_session_london():
    s = current_session(now=_utc(8))
    assert s is not None
    assert s.name == "Londres"


def test_current_session_ny():
    s = current_session(now=_utc(14))
    assert s is not None
    assert s.name == "Nueva York"


def test_current_session_outside():
    assert current_session(now=_utc(3)) is None
    assert current_session(now=_utc(20)) is None


def test_parse_sessions_default_when_empty():
    assert parse_sessions("") == DEFAULT_SESSIONS


def test_parse_sessions_custom():
    sessions = parse_sessions("Asia:0-6,Europa:7-11")
    assert len(sessions) == 2
    assert sessions[0].name == "Asia"
    assert sessions[0].start_hour_utc == 0
    assert sessions[0].end_hour_utc == 6
    assert sessions[1].name == "Europa"
