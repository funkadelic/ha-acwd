"""Tests for the hourly cost statistic imported alongside hourly usage."""

from datetime import UTC, date, datetime, timedelta
from unittest.mock import Mock

import pytest

from custom_components.acwd.statistics import async_import_hourly_statistics
from tests.helpers import make_date_dt, patch_statistics

METER = "230057301"
USAGE_ID = f"acwd:{METER}_hourly_usage"
COST_ID = f"acwd:{METER}_hourly_cost"
RECORDS = [
    {"Hourly": "12:00 AM", "UsageValue": 748},
    {"Hourly": "1:00 AM", "UsageValue": 374},
]


def _history(by_id):
    """Return a get_last_statistics stand-in serving stored rows per statistic id, newest first."""

    def _get_last_stats(_hass, count, statistic_id, *_args):
        rows = by_id.get(statistic_id, [])[:count]
        return {statistic_id: rows} if rows else {}

    return _get_last_stats


async def _import(hass, get_instance, history, day, tz, rate, previous_sums=None):
    """Import RECORDS for day and return {statistic_id: (metadata, statistics)} for each write."""
    writes, _ = await _import_with_result(hass, get_instance, history, day, tz, rate, previous_sums)
    return writes


async def _import_with_result(hass, get_instance, history, day, tz, rate, previous_sums=None):
    """Import RECORDS for day and return (writes, the import's returned final sums)."""
    add = Mock()
    with patch_statistics(get_instance, add, _history(history), tz):
        result = await async_import_hourly_statistics(hass, METER, RECORDS, make_date_dt(day, tz), rate, previous_sums)
    return {call.args[1]["statistic_id"]: (call.args[1], call.args[2]) for call in add.call_args_list}, result


@pytest.mark.unit
@pytest.mark.asyncio
class TestHourlyCost:
    """Cost statistic behavior."""

    async def test_cost_per_hour_is_gallons_over_748_times_rate(self, mock_hass, mock_get_instance, pst_timezone):
        """748 gallons at $5.38/unit costs $5.38; 374 gallons costs $2.69."""
        writes = await _import(mock_hass, mock_get_instance, {}, date(2026, 3, 2), pst_timezone, 5.38)

        _, cost = writes[COST_ID]
        assert [s["state"] for s in cost] == pytest.approx([5.38, 2.69])
        assert [s["sum"] for s in cost] == pytest.approx([5.38, 8.07])

    async def test_cost_hours_match_usage_hours(self, mock_hass, mock_get_instance, pst_timezone):
        """Cost rows land on the same hour starts as usage rows."""
        writes = await _import(mock_hass, mock_get_instance, {}, date(2026, 3, 2), pst_timezone, 5.38)

        assert [s["start"] for s in writes[COST_ID][1]] == [s["start"] for s in writes[USAGE_ID][1]]

    async def test_metadata(self, mock_hass, mock_get_instance, pst_timezone):
        """Cost statistic has no unit (currency comes from HA) and keeps a running sum."""
        writes = await _import(mock_hass, mock_get_instance, {}, date(2026, 3, 2), pst_timezone, 5.38)

        meta, _ = writes[COST_ID]
        assert meta["unit_of_measurement"] is None
        assert meta["has_sum"] is True
        assert meta["name"] == f"ACWD Water Hourly Cost - Meter {METER}"

    async def test_usage_statistic_unchanged(self, mock_hass, mock_get_instance, pst_timezone):
        """Usage is still gallons with a gallon sum, whether or not a rate is given."""
        with_rate = await _import(mock_hass, mock_get_instance, {}, date(2026, 3, 2), pst_timezone, 5.38)
        without_rate = await _import(mock_hass, mock_get_instance, {}, date(2026, 3, 2), pst_timezone, None)

        assert with_rate[USAGE_ID] == without_rate[USAGE_ID]
        assert with_rate[USAGE_ID][0]["unit_of_measurement"] == "gal"
        assert [s["sum"] for s in with_rate[USAGE_ID][1]] == [748, 1122]
        assert COST_ID not in without_rate

    async def test_sum_resumes_from_stored_cost(self, mock_hass, mock_get_instance, pst_timezone):
        """The first hour of a new day continues from the previous day's last cost sum."""
        prev_11pm = datetime(2026, 3, 2, 7, tzinfo=UTC)  # Mar 1, 11 PM PST
        history = {COST_ID: [{"start": prev_11pm, "sum": 100.0}]}

        writes = await _import(mock_hass, mock_get_instance, history, date(2026, 3, 2), pst_timezone, 5.38)

        assert [s["sum"] for s in writes[COST_ID][1]] == pytest.approx([105.38, 108.07])

    async def test_reimport_same_day_does_not_inflate_sum(self, mock_hass, mock_get_instance, pst_timezone):
        """Re-importing today rebuilds from yesterday's final sum, not today's partial sum."""
        prev_11pm = datetime(2026, 3, 2, 7, tzinfo=UTC)
        today_1am = datetime(2026, 3, 2, 9, tzinfo=UTC)
        history = {COST_ID: [{"start": today_1am, "sum": 108.07}, {"start": prev_11pm, "sum": 100.0}]}

        writes = await _import(mock_hass, mock_get_instance, history, date(2026, 3, 2), pst_timezone, 5.38)

        assert [s["sum"] for s in writes[COST_ID][1]] == pytest.approx([105.38, 108.07])

    async def test_rate_change_prices_only_newly_imported_hours(self, mock_hass, mock_get_instance, pst_timezone):
        """A new rate prices the next day's hours and leaves the stored day alone."""
        day1, day2 = date(2026, 3, 2), date(2026, 3, 3)
        first = await _import(mock_hass, mock_get_instance, {}, day1, pst_timezone, 5.38)
        day1_cost = first[COST_ID][1]
        stored = {COST_ID: list(reversed(day1_cost))}

        second = await _import(mock_hass, mock_get_instance, stored, day2, pst_timezone, 6.00)

        day2_cost = second[COST_ID][1]
        day2_start = make_date_dt(day2, pst_timezone)
        assert all(s["start"] >= day2_start for s in day2_cost)
        assert [s["state"] for s in day2_cost] == pytest.approx([6.00, 3.00])
        assert [s["sum"] for s in day2_cost] == pytest.approx([8.07 + 6.00, 8.07 + 9.00])
        assert day2_cost[0]["start"] - day1_cost[-1]["start"] == timedelta(hours=23)

    async def test_rate_change_reprices_reimported_day_from_prior_baseline(self, mock_hass, mock_get_instance, pst_timezone):
        """Re-importing today at a new rate re-prices today's hours and keeps yesterday's final sum as the base."""
        prev_11pm = datetime(2026, 3, 2, 7, tzinfo=UTC)
        today_1am = datetime(2026, 3, 2, 9, tzinfo=UTC)
        history = {COST_ID: [{"start": today_1am, "sum": 108.07}, {"start": prev_11pm, "sum": 100.0}]}

        writes = await _import(mock_hass, mock_get_instance, history, date(2026, 3, 2), pst_timezone, 6.00)

        cost = writes[COST_ID][1]
        assert [s["state"] for s in cost] == pytest.approx([6.00, 3.00])
        assert [s["sum"] for s in cost] == pytest.approx([106.00, 109.00])

    async def test_next_day_continues_from_returned_sums_before_recorder_saves(self, mock_hass, mock_get_instance, pst_timezone):
        """Today continues from yesterday's returned sums even when the recorder has saved nothing yet."""
        _, yesterday_sums = await _import_with_result(mock_hass, mock_get_instance, {}, date(2026, 3, 2), pst_timezone, 5.38)

        writes = await _import(mock_hass, mock_get_instance, {}, date(2026, 3, 3), pst_timezone, 5.38, yesterday_sums)

        assert yesterday_sums == pytest.approx((1122, 8.07))
        assert [s["sum"] for s in writes[USAGE_ID][1]] == [1870, 2244]
        assert [s["sum"] for s in writes[COST_ID][1]] == pytest.approx([13.45, 16.14])

    async def test_missing_cost_sum_falls_back_to_stored_cost(self, mock_hass, mock_get_instance, pst_timezone):
        """If the previous import carried no cost sum, cost resumes from the stored cost statistic."""
        prev_11pm = datetime(2026, 3, 2, 7, tzinfo=UTC)
        history = {COST_ID: [{"start": prev_11pm, "sum": 100.0}]}

        writes = await _import(mock_hass, mock_get_instance, history, date(2026, 3, 2), pst_timezone, 5.38, (1000, None))

        assert [s["sum"] for s in writes[USAGE_ID][1]] == [1748, 2122]
        assert [s["sum"] for s in writes[COST_ID][1]] == pytest.approx([105.38, 108.07])

    async def test_import_without_rate_returns_no_cost_sum(self, mock_hass, mock_get_instance, pst_timezone):
        """Without a rate, the import returns the usage sum and no cost sum."""
        _, result = await _import_with_result(mock_hass, mock_get_instance, {}, date(2026, 3, 2), pst_timezone, None)

        assert result == (1122, None)
