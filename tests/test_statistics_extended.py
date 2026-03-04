"""Extended statistics tests — quarter-hourly, daily, and hourly edge cases.

Covers previously-untested branches in statistics.py to bring coverage from 46% to 80%+:
- async_import_hourly_statistics: missing/unparseable Hourly field, float timestamp, empty data
- async_import_quarter_hourly_statistics: all branches
- async_import_daily_statistics: all branches
"""

import importlib.util
import sys
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

# Import mocks - conftest sets up homeassistant module mocks.
from tests.helpers import make_baseline_mock, make_date_dt, patch_statistics
from homeassistant.util import dt as dt_util

# Load statistics module directly (same pattern as test_statistics.py).
# Re-use an already-loaded module if test_statistics.py ran first — re-executing
# exec_module() would overwrite sys.modules with a new object and break patches
# that the other test file bound against the first object.
if "custom_components.acwd.statistics" in sys.modules:
    _stats_module = sys.modules["custom_components.acwd.statistics"]
else:
    _stats_spec = importlib.util.spec_from_file_location(
        "custom_components.acwd.statistics",
        Path(__file__).parent.parent / "custom_components" / "acwd" / "statistics.py",
    )
    assert _stats_spec is not None and _stats_spec.loader is not None
    _stats_module = importlib.util.module_from_spec(_stats_spec)
    _stats_spec.loader.exec_module(_stats_module)
    sys.modules["custom_components.acwd.statistics"] = _stats_module
    sys.modules["custom_components.acwd"].statistics = _stats_module

async_import_hourly_statistics = _stats_module.async_import_hourly_statistics
async_import_quarter_hourly_statistics = (
    _stats_module.async_import_quarter_hourly_statistics
)
async_import_daily_statistics = _stats_module.async_import_daily_statistics


# ---------------------------------------------------------------------------
# Hourly edge cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
class TestHourlyEdgeCases:
    """Edge cases for async_import_hourly_statistics()."""

    async def test_missing_hourly_field_none_is_skipped(
        self,
        mock_hass,
        mock_get_instance,
        mock_async_add_external_statistics,
        meter_number,
        pst_timezone,
    ):
        """Records with Hourly=None are skipped; only valid records are imported."""
        mock_get_last_stats = Mock(return_value={})
        date_dt = make_date_dt(date(2025, 12, 9), pst_timezone)

        hourly_records = [
            {"Hourly": None, "UsageValue": 5.0},
            {"Hourly": "", "UsageValue": 5.0},
            {"Hourly": "12:00 AM", "UsageValue": 3.0},  # only valid record
        ]

        with patch_statistics(
            mock_get_instance,
            mock_async_add_external_statistics,
            mock_get_last_stats,
            pst_timezone,
        ):
            await async_import_hourly_statistics(
                mock_hass, meter_number, hourly_records, date_dt
            )

        assert mock_async_add_external_statistics.called
        statistics = mock_async_add_external_statistics.call_args[0][2]
        # Only the one valid record should produce a statistic
        assert len(statistics) == 1
        assert statistics[0].sum == pytest.approx(3.0, rel=0.01)

    async def test_unparseable_hourly_value_is_skipped(
        self,
        mock_hass,
        mock_get_instance,
        mock_async_add_external_statistics,
        meter_number,
        pst_timezone,
    ):
        """Records with an unparseable Hourly string are skipped."""
        mock_get_last_stats = Mock(return_value={})
        date_dt = make_date_dt(date(2025, 12, 9), pst_timezone)

        hourly_records = [
            {"Hourly": "bad-time", "UsageValue": 5.0},  # skipped
            {"Hourly": "1:00 AM", "UsageValue": 2.0},  # valid
        ]

        with patch_statistics(
            mock_get_instance,
            mock_async_add_external_statistics,
            mock_get_last_stats,
            pst_timezone,
        ):
            await async_import_hourly_statistics(
                mock_hass, meter_number, hourly_records, date_dt
            )

        statistics = mock_async_add_external_statistics.call_args[0][2]
        assert len(statistics) == 1
        assert statistics[0].sum == pytest.approx(2.0, rel=0.01)

    async def test_float_timestamp_in_extended_search_is_converted_to_datetime(
        self,
        mock_hass,
        mock_get_instance,
        mock_async_add_external_statistics,
        meter_number,
        pst_timezone,
    ):
        """Float Unix timestamp in extended 48-hour search is converted to datetime."""
        statistic_id = f"acwd:{meter_number}_hourly_usage"
        date_dt = make_date_dt(date(2025, 12, 10), pst_timezone)

        # Today's stat — forces the extended search
        today_8am_utc = datetime(2025, 12, 10, 16, 0, 0, tzinfo=dt_util.UTC)
        today_float_ts = today_8am_utc.timestamp()  # float

        # Yesterday's stat — correct baseline, also as float
        yesterday_11pm_utc = datetime(2025, 12, 10, 7, 0, 0, tzinfo=dt_util.UTC)
        yesterday_float_ts = yesterday_11pm_utc.timestamp()  # float
        yesterday_sum = 500.0

        call_count = {"n": 0}

        def _get_last_stats(hass, count, stat_id, convert, types):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # First call: return today's stat as float timestamp
                return {
                    statistic_id: [
                        {"start": today_float_ts, "sum": 800.0},
                    ]
                }
            else:
                # Extended call: two stats — today (float) + yesterday (float)
                return {
                    statistic_id: [
                        {"start": today_float_ts, "sum": 800.0},
                        {"start": yesterday_float_ts, "sum": yesterday_sum},
                    ]
                }

        hourly_records = [{"Hourly": "12:00 AM", "UsageValue": 10.0}]

        with patch_statistics(
            mock_get_instance,
            mock_async_add_external_statistics,
            _get_last_stats,
            pst_timezone,
        ):
            await async_import_hourly_statistics(
                mock_hass, meter_number, hourly_records, date_dt
            )

        statistics = mock_async_add_external_statistics.call_args[0][2]
        # Baseline is yesterday's sum, so first stat = 500 + 10 = 510
        assert statistics[0].sum == pytest.approx(510.0, rel=0.01)
        assert call_count["n"] == 2  # Both calls were made

    async def test_empty_hourly_data_does_not_call_add_external_statistics(
        self,
        mock_hass,
        mock_get_instance,
        mock_async_add_external_statistics,
        meter_number,
        pst_timezone,
    ):
        """Empty hourly_data list: async_add_external_statistics is NOT called."""
        mock_get_last_stats = Mock(return_value={})
        date_dt = make_date_dt(date(2025, 12, 9), pst_timezone)

        with patch_statistics(
            mock_get_instance,
            mock_async_add_external_statistics,
            mock_get_last_stats,
            pst_timezone,
        ):
            await async_import_hourly_statistics(mock_hass, meter_number, [], date_dt)

        assert not mock_async_add_external_statistics.called


# ---------------------------------------------------------------------------
# Task 2B: Quarter-hourly statistics
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
class TestQuarterHourlyStatistics:
    """Tests for async_import_quarter_hourly_statistics()."""

    async def test_basic_cumulative_sum_four_records(
        self,
        mock_hass,
        mock_get_instance,
        mock_async_add_external_statistics,
        meter_number,
        pst_timezone,
    ):
        """4 records across hour 0 (minutes 0/15/30/45) produce correct cumulative sum."""
        mock_get_last_stats = Mock(return_value={})
        date_dt = make_date_dt(date(2025, 12, 9), pst_timezone)

        quarter_records = [
            {"Hour": 0, "Minute": 0, "UsageValue": 5.0},
            {"Hour": 0, "Minute": 15, "UsageValue": 3.0},
            {"Hour": 0, "Minute": 30, "UsageValue": 7.0},
            {"Hour": 0, "Minute": 45, "UsageValue": 2.0},
        ]

        with patch_statistics(
            mock_get_instance,
            mock_async_add_external_statistics,
            mock_get_last_stats,
            pst_timezone,
        ):
            await async_import_quarter_hourly_statistics(
                mock_hass, meter_number, quarter_records, date_dt
            )

        assert mock_async_add_external_statistics.called
        statistics = mock_async_add_external_statistics.call_args[0][2]
        assert len(statistics) == 4
        assert statistics[0].sum == pytest.approx(5.0, rel=0.01)
        assert statistics[1].sum == pytest.approx(8.0, rel=0.01)
        assert statistics[2].sum == pytest.approx(15.0, rel=0.01)
        assert statistics[3].sum == pytest.approx(17.0, rel=0.01)

    async def test_statistic_id_uses_quarter_hourly_suffix(
        self,
        mock_hass,
        mock_get_instance,
        mock_async_add_external_statistics,
        meter_number,
        pst_timezone,
    ):
        """statistic_id for quarter-hourly uses the _quarter_hourly_usage suffix."""
        mock_get_last_stats = Mock(return_value={})
        date_dt = make_date_dt(date(2025, 12, 9), pst_timezone)

        quarter_records = [{"Hour": 0, "Minute": 0, "UsageValue": 1.0}]

        with patch_statistics(
            mock_get_instance,
            mock_async_add_external_statistics,
            mock_get_last_stats,
            pst_timezone,
        ):
            await async_import_quarter_hourly_statistics(
                mock_hass, meter_number, quarter_records, date_dt
            )

        metadata = mock_async_add_external_statistics.call_args[0][1]
        assert metadata.statistic_id == f"acwd:{meter_number}_quarter_hourly_usage"

    async def test_record_with_none_hour_is_skipped(
        self,
        mock_hass,
        mock_get_instance,
        mock_async_add_external_statistics,
        meter_number,
        pst_timezone,
    ):
        """Records with Hour=None are skipped."""
        mock_get_last_stats = Mock(return_value={})
        date_dt = make_date_dt(date(2025, 12, 9), pst_timezone)

        quarter_records = [
            {"Hour": None, "Minute": 0, "UsageValue": 1.0},  # skipped
            {"Hour": 0, "Minute": 15, "UsageValue": 4.0},  # valid
        ]

        with patch_statistics(
            mock_get_instance,
            mock_async_add_external_statistics,
            mock_get_last_stats,
            pst_timezone,
        ):
            await async_import_quarter_hourly_statistics(
                mock_hass, meter_number, quarter_records, date_dt
            )

        statistics = mock_async_add_external_statistics.call_args[0][2]
        assert len(statistics) == 1
        assert statistics[0].sum == pytest.approx(4.0, rel=0.01)

    async def test_record_with_none_minute_is_skipped(
        self,
        mock_hass,
        mock_get_instance,
        mock_async_add_external_statistics,
        meter_number,
        pst_timezone,
    ):
        """Records with Minute=None are skipped."""
        mock_get_last_stats = Mock(return_value={})
        date_dt = make_date_dt(date(2025, 12, 9), pst_timezone)

        quarter_records = [
            {"Hour": 0, "Minute": None, "UsageValue": 1.0},  # skipped
            {"Hour": 0, "Minute": 30, "UsageValue": 6.0},  # valid
        ]

        with patch_statistics(
            mock_get_instance,
            mock_async_add_external_statistics,
            mock_get_last_stats,
            pst_timezone,
        ):
            await async_import_quarter_hourly_statistics(
                mock_hass, meter_number, quarter_records, date_dt
            )

        statistics = mock_async_add_external_statistics.call_args[0][2]
        assert len(statistics) == 1
        assert statistics[0].sum == pytest.approx(6.0, rel=0.01)

    async def test_baseline_is_zero_when_no_prior_stats(
        self,
        mock_hass,
        mock_get_instance,
        mock_async_add_external_statistics,
        meter_number,
        pst_timezone,
    ):
        """Baseline = 0 when no prior statistics exist."""
        mock_get_last_stats = Mock(return_value={})
        date_dt = make_date_dt(date(2025, 12, 9), pst_timezone)

        quarter_records = [{"Hour": 0, "Minute": 0, "UsageValue": 10.0}]

        with patch_statistics(
            mock_get_instance,
            mock_async_add_external_statistics,
            mock_get_last_stats,
            pst_timezone,
        ):
            await async_import_quarter_hourly_statistics(
                mock_hass, meter_number, quarter_records, date_dt
            )

        statistics = mock_async_add_external_statistics.call_args[0][2]
        assert statistics[0].sum == pytest.approx(10.0, rel=0.01)

    async def test_baseline_from_yesterday_prior_to_target_date(
        self,
        mock_hass,
        mock_get_instance,
        mock_async_add_external_statistics,
        meter_number,
        pst_timezone,
    ):
        """Baseline uses sum from last stat BEFORE target date midnight."""
        statistic_id = f"acwd:{meter_number}_quarter_hourly_usage"
        date_dt = make_date_dt(date(2025, 12, 10), pst_timezone)

        # Yesterday's 11 PM PST = Dec 10 07:00 UTC (before Dec 10 08:00 UTC midnight)
        yesterday_stat_utc = datetime(2025, 12, 10, 7, 0, 0, tzinfo=dt_util.UTC)
        yesterday_sum = 250.0

        mock_get_last_stats = make_baseline_mock(
            statistic_id, yesterday_stat_utc, yesterday_sum
        )

        quarter_records = [{"Hour": 0, "Minute": 0, "UsageValue": 5.0}]

        with patch_statistics(
            mock_get_instance,
            mock_async_add_external_statistics,
            mock_get_last_stats,
            pst_timezone,
        ):
            await async_import_quarter_hourly_statistics(
                mock_hass, meter_number, quarter_records, date_dt
            )

        statistics = mock_async_add_external_statistics.call_args[0][2]
        assert statistics[0].sum == pytest.approx(yesterday_sum + 5.0, rel=0.01)

    async def test_extended_192_record_search_when_last_stat_is_from_today(
        self,
        mock_hass,
        mock_get_instance,
        mock_async_add_external_statistics,
        meter_number,
        pst_timezone,
    ):
        """Extended 192-record search is triggered when last stat is from target date."""
        statistic_id = f"acwd:{meter_number}_quarter_hourly_usage"
        date_dt = make_date_dt(date(2025, 12, 10), pst_timezone)

        # Today's stat (after midnight UTC) — triggers extended search
        today_stat_utc = datetime(2025, 12, 10, 12, 0, 0, tzinfo=dt_util.UTC)
        today_sum = 900.0

        # Yesterday's stat — correct baseline
        yesterday_stat_utc = datetime(2025, 12, 10, 7, 0, 0, tzinfo=dt_util.UTC)
        yesterday_sum = 300.0

        call_count = {"n": 0}

        def _get_last_stats(hass, count, stat_id, convert, types):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return {statistic_id: [{"start": today_stat_utc, "sum": today_sum}]}
            return {
                statistic_id: [
                    {"start": today_stat_utc, "sum": today_sum},
                    {"start": yesterday_stat_utc, "sum": yesterday_sum},
                ]
            }

        quarter_records = [{"Hour": 0, "Minute": 0, "UsageValue": 8.0}]

        with patch_statistics(
            mock_get_instance,
            mock_async_add_external_statistics,
            _get_last_stats,
            pst_timezone,
        ):
            await async_import_quarter_hourly_statistics(
                mock_hass, meter_number, quarter_records, date_dt
            )

        # Should have made 2 get_last_statistics calls
        assert call_count["n"] == 2
        # Baseline should be yesterday's sum
        statistics = mock_async_add_external_statistics.call_args[0][2]
        assert statistics[0].sum == pytest.approx(yesterday_sum + 8.0, rel=0.01)

    async def test_float_timestamp_in_quarter_hourly_extended_search_is_converted(
        self,
        mock_hass,
        mock_get_instance,
        mock_async_add_external_statistics,
        meter_number,
        pst_timezone,
    ):
        """Float Unix timestamps in quarter-hourly extended search are converted to datetime."""
        statistic_id = f"acwd:{meter_number}_quarter_hourly_usage"
        date_dt = make_date_dt(date(2025, 12, 10), pst_timezone)

        # Both timestamps as floats
        today_stat_utc = datetime(2025, 12, 10, 12, 0, 0, tzinfo=dt_util.UTC)
        today_float_ts = today_stat_utc.timestamp()

        yesterday_stat_utc = datetime(2025, 12, 10, 7, 0, 0, tzinfo=dt_util.UTC)
        yesterday_float_ts = yesterday_stat_utc.timestamp()
        yesterday_sum = 400.0

        call_count = {"n": 0}

        def _get_last_stats(hass, count, stat_id, convert, types):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return {statistic_id: [{"start": today_float_ts, "sum": 700.0}]}
            return {
                statistic_id: [
                    {"start": today_float_ts, "sum": 700.0},
                    {"start": yesterday_float_ts, "sum": yesterday_sum},
                ]
            }

        quarter_records = [{"Hour": 0, "Minute": 0, "UsageValue": 3.0}]

        with patch_statistics(
            mock_get_instance,
            mock_async_add_external_statistics,
            _get_last_stats,
            pst_timezone,
        ):
            # Should not raise TypeError on float timestamp comparison
            await async_import_quarter_hourly_statistics(
                mock_hass, meter_number, quarter_records, date_dt
            )

        statistics = mock_async_add_external_statistics.call_args[0][2]
        assert statistics[0].sum == pytest.approx(yesterday_sum + 3.0, rel=0.01)

    async def test_empty_quarter_hourly_data_does_not_call_add_external_statistics(
        self,
        mock_hass,
        mock_get_instance,
        mock_async_add_external_statistics,
        meter_number,
        pst_timezone,
    ):
        """Empty quarter_hourly_data list: async_add_external_statistics is NOT called."""
        mock_get_last_stats = Mock(return_value={})
        date_dt = make_date_dt(date(2025, 12, 9), pst_timezone)

        with patch_statistics(
            mock_get_instance,
            mock_async_add_external_statistics,
            mock_get_last_stats,
            pst_timezone,
        ):
            await async_import_quarter_hourly_statistics(
                mock_hass, meter_number, [], date_dt
            )

        assert not mock_async_add_external_statistics.called


# ---------------------------------------------------------------------------
# Task 2C: Daily statistics
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
class TestDailyStatistics:
    """Tests for async_import_daily_statistics()."""

    async def test_basic_three_records_produce_cumulative_sum(
        self,
        mock_hass,
        mock_get_instance,
        mock_async_add_external_statistics,
        meter_number,
        pst_timezone,
    ):
        """3 records produce cumulative sums: 100, 300, 350."""
        mock_get_last_stats = Mock(return_value={})

        daily_records = [
            {"UsageDate": "December 1, 2025", "UsageValue": 100.0},
            {"UsageDate": "December 2, 2025", "UsageValue": 200.0},
            {"UsageDate": "December 3, 2025", "UsageValue": 50.0},
        ]

        with patch_statistics(
            mock_get_instance,
            mock_async_add_external_statistics,
            mock_get_last_stats,
            pst_timezone,
        ):
            await async_import_daily_statistics(mock_hass, meter_number, daily_records)

        assert mock_async_add_external_statistics.called
        statistics = mock_async_add_external_statistics.call_args[0][2]
        assert len(statistics) == 3
        assert statistics[0].sum == pytest.approx(100.0, rel=0.01)
        assert statistics[1].sum == pytest.approx(300.0, rel=0.01)
        assert statistics[2].sum == pytest.approx(350.0, rel=0.01)

    async def test_record_with_missing_usage_date_is_skipped(
        self,
        mock_hass,
        mock_get_instance,
        mock_async_add_external_statistics,
        meter_number,
        pst_timezone,
    ):
        """Records with UsageDate=None are skipped via 'continue' (not a warning)."""
        mock_get_last_stats = Mock(return_value={})

        daily_records = [
            {"UsageDate": None, "UsageValue": 5.0},  # skipped
            {"UsageDate": "December 1, 2025", "UsageValue": 100.0},  # valid
        ]

        with patch_statistics(
            mock_get_instance,
            mock_async_add_external_statistics,
            mock_get_last_stats,
            pst_timezone,
        ):
            await async_import_daily_statistics(mock_hass, meter_number, daily_records)

        statistics = mock_async_add_external_statistics.call_args[0][2]
        assert len(statistics) == 1
        assert statistics[0].sum == pytest.approx(100.0, rel=0.01)

    async def test_record_with_unparseable_date_string_is_skipped(
        self,
        mock_hass,
        mock_get_instance,
        mock_async_add_external_statistics,
        meter_number,
        pst_timezone,
    ):
        """Records with an unparseable date string are skipped (with warning logged)."""
        mock_get_last_stats = Mock(return_value={})

        daily_records = [
            {"UsageDate": "bad date", "UsageValue": 5.0},  # skipped
            {"UsageDate": "December 2, 2025", "UsageValue": 75.0},  # valid
        ]

        with patch_statistics(
            mock_get_instance,
            mock_async_add_external_statistics,
            mock_get_last_stats,
            pst_timezone,
        ):
            await async_import_daily_statistics(mock_hass, meter_number, daily_records)

        statistics = mock_async_add_external_statistics.call_args[0][2]
        assert len(statistics) == 1
        assert statistics[0].sum == pytest.approx(75.0, rel=0.01)

    async def test_baseline_uses_last_known_sum(
        self,
        mock_hass,
        mock_get_instance,
        mock_async_add_external_statistics,
        meter_number,
        pst_timezone,
    ):
        """Baseline from prior sum is applied to all cumulative sums."""
        statistic_id = f"acwd:{meter_number}_daily_usage"
        prior_sum = 500.0

        mock_get_last_stats = Mock(return_value={statistic_id: [{"sum": prior_sum}]})

        daily_records = [
            {"UsageDate": "December 1, 2025", "UsageValue": 100.0},
        ]

        with patch_statistics(
            mock_get_instance,
            mock_async_add_external_statistics,
            mock_get_last_stats,
            pst_timezone,
        ):
            await async_import_daily_statistics(mock_hass, meter_number, daily_records)

        statistics = mock_async_add_external_statistics.call_args[0][2]
        assert statistics[0].sum == pytest.approx(prior_sum + 100.0, rel=0.01)

    async def test_statistic_id_uses_daily_usage_suffix(
        self,
        mock_hass,
        mock_get_instance,
        mock_async_add_external_statistics,
        meter_number,
        pst_timezone,
    ):
        """statistic_id for daily statistics uses _daily_usage suffix."""
        mock_get_last_stats = Mock(return_value={})

        daily_records = [{"UsageDate": "December 1, 2025", "UsageValue": 50.0}]

        with patch_statistics(
            mock_get_instance,
            mock_async_add_external_statistics,
            mock_get_last_stats,
            pst_timezone,
        ):
            await async_import_daily_statistics(mock_hass, meter_number, daily_records)

        metadata = mock_async_add_external_statistics.call_args[0][1]
        assert metadata.statistic_id.endswith("_daily_usage")

    async def test_empty_daily_data_does_not_call_add_external_statistics(
        self,
        mock_hass,
        mock_get_instance,
        mock_async_add_external_statistics,
        meter_number,
        pst_timezone,
    ):
        """Empty daily_data list: async_add_external_statistics is NOT called."""
        mock_get_last_stats = Mock(return_value={})

        with patch_statistics(
            mock_get_instance,
            mock_async_add_external_statistics,
            mock_get_last_stats,
            pst_timezone,
        ):
            await async_import_daily_statistics(mock_hass, meter_number, [])

        assert not mock_async_add_external_statistics.called
