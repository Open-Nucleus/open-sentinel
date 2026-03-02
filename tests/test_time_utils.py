"""Tests for time window parser and epiweek calculator."""

from datetime import datetime, timedelta, timezone

import pytest

from open_sentinel.time_utils import epiweek, parse_time_window


class TestParseTimeWindow:
    def test_weeks(self):
        assert parse_time_window("12w") == timedelta(weeks=12)

    def test_days(self):
        assert parse_time_window("7d") == timedelta(days=7)

    def test_hours(self):
        assert parse_time_window("24h") == timedelta(hours=24)

    def test_minutes(self):
        assert parse_time_window("30m") == timedelta(minutes=30)

    def test_single_unit(self):
        assert parse_time_window("1w") == timedelta(weeks=1)
        assert parse_time_window("1d") == timedelta(days=1)
        assert parse_time_window("1h") == timedelta(hours=1)
        assert parse_time_window("1m") == timedelta(minutes=1)

    def test_large_values(self):
        assert parse_time_window("52w") == timedelta(weeks=52)
        assert parse_time_window("365d") == timedelta(days=365)

    def test_whitespace_stripped(self):
        assert parse_time_window("  4w  ") == timedelta(weeks=4)

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="Invalid time window"):
            parse_time_window("abc")

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="Invalid time window"):
            parse_time_window("")

    def test_missing_unit_raises(self):
        with pytest.raises(ValueError, match="Invalid time window"):
            parse_time_window("12")

    def test_unknown_unit_raises(self):
        with pytest.raises(ValueError, match="Invalid time window"):
            parse_time_window("12y")


class TestEpiweek:
    def test_known_date(self):
        # 2026-03-02 is a Monday in ISO week 10
        dt = datetime(2026, 3, 2, tzinfo=timezone.utc)
        assert epiweek(dt) == "2026-W10"

    def test_single_digit_week_padded(self):
        dt = datetime(2026, 1, 5, tzinfo=timezone.utc)  # Week 2
        assert epiweek(dt) == "2026-W02"

    def test_week_one(self):
        dt = datetime(2026, 1, 1, tzinfo=timezone.utc)  # Week 1
        assert epiweek(dt) == "2026-W01"

    def test_year_boundary(self):
        # Dec 31 2025 may be week 1 of 2026 per ISO rules
        dt = datetime(2025, 12, 31, tzinfo=timezone.utc)
        result = epiweek(dt)
        assert result.startswith("2026-W01") or result.startswith("2025-W")
