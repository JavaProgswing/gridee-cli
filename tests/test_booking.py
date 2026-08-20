from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from gridee.booking import (
    BookingError,
    by_text,
    nodes_from_root,
    normalized,
    parse_hhmm,
    resolve_schedule,
    round_up,
    venue_score,
)
from gridee.cli import make_parser


def schedule_args(**overrides):
    values = {
        "date": None,
        "open_at": parse_hhmm("05:00"),
        "start": parse_hhmm("08:00"),
        "end": parse_hhmm("17:00"),
        "late_buffer_minutes": 5,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_round_up_to_next_five_minutes():
    assert round_up(datetime(2026, 8, 20, 8, 1, 1)) == datetime(2026, 8, 20, 8, 5)
    assert round_up(datetime(2026, 8, 20, 8, 5, 0)) == datetime(2026, 8, 20, 8, 5)


def test_late_same_day_booking_uses_buffer_and_rounding():
    _, start, end = resolve_schedule(schedule_args(), datetime(2026, 8, 20, 9, 2, 30))
    assert start == datetime(2026, 8, 20, 9, 10)
    assert end == datetime(2026, 8, 20, 17, 0)


def test_after_end_rolls_implicit_date_to_tomorrow():
    open_at, start, _ = resolve_schedule(schedule_args(), datetime(2026, 8, 20, 18, 0))
    assert open_at == datetime(2026, 8, 21, 5, 0)
    assert start == datetime(2026, 8, 21, 8, 0)


def test_explicit_expired_window_is_rejected():
    args = schedule_args(date=date(2026, 8, 20))
    with pytest.raises(BookingError, match="already ended"):
        resolve_schedule(args, datetime(2026, 8, 20, 16, 59))


def test_venue_alias_scoring():
    assert normalized("TP Avenue") == "tech park avenue"
    assert venue_score("TP Avenue", "Tech Park Avenue - STEP") > 0.7


def test_imported_ui_fixture_detects_closed_state():
    fixture = Path(__file__).parents[1] / "analysis" / "gridee-booking-home.xml"
    nodes = nodes_from_root(ET.parse(fixture).getroot())
    closed = by_text(nodes, r"bookings are closed")
    assert closed is not None


def test_booking_parser_is_dry_run_by_default():
    args = make_parser().parse_args(["booking", "--venue", "TP Avenue"])
    assert args.command == "booking"
    assert args.execute is False
    assert args.venue == "TP Avenue"
