"""Tests for statistics.py - baseline calculation and timezone handling.

These tests prevent regressions of critical bugs:
- v1.0.13: Negative midnight values (baseline calculation)
- v1.0.14: Type conversion errors (float vs datetime timestamps)
- v1.0.16: Timezone handling (naive datetime causing wrong UTC conversions)

NOTE: These tests are currently skipped pending Home Assistant mocking improvements.
      Only coordinator tests are active for Phase 1 CI/CD validation.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import pytest

# Import mocks - conftest sets up homeassistant module mocks
# The actual modules will now be importable
from homeassistant.components.recorder import StatisticData
from homeassistant.const import UnitOfVolume
from homeassistant.util import dt as dt_util

# Import statistics module directly without triggering __init__.py
import importlib.util

# Create real module objects for the integration (avoids silent attribute absorption)
import types
from homeassistant.util import dt as _dt_util

_custom_components = types.ModuleType("custom_components")
_custom_components.__path__ = []

_acwd_package = types.ModuleType("custom_components.acwd")
_acwd_package.__path__ = []

_const_module = types.ModuleType("custom_components.acwd.const")
_const_module.DOMAIN = "acwd"
_const_module.DATE_FORMAT_LONG = "%B %d, %Y"
_const_module.TIME_FORMAT_12HR = "%I:%M %p"

_helpers_module = types.ModuleType("custom_components.acwd.helpers")

def _local_midnight(d):
    local_tz = _dt_util.get_default_time_zone()
    return datetime.combine(d, datetime.min.time()).replace(tzinfo=local_tz)

_helpers_module.local_midnight = _local_midnight

sys.modules["custom_components"] = _custom_components
sys.modules["custom_components.acwd"] = _acwd_package
sys.modules["custom_components.acwd.const"] = _const_module
sys.modules["custom_components.acwd.helpers"] = _helpers_module

_stats_spec = importlib.util.spec_from_file_location(
    "custom_components.acwd.statistics",
    Path(__file__).parent.parent / "custom_components" / "acwd" / "statistics.py"
)
_stats_module = importlib.util.module_from_spec(_stats_spec)
_stats_spec.loader.exec_module(_stats_module)
async_import_hourly_statistics = _stats_module.async_import_hourly_statistics


@pytest.mark.skip(reason="Pending Home Assistant mocking improvements - Phase 2")
@pytest.mark.unit
@pytest.mark.asyncio
class TestBaselineCalculation:
    """Test baseline calculation logic to prevent v1.0.13 regression."""

    async def test_baseline_from_yesterday_final_hour(
        self,
        mock_hass,
        mock_get_instance,
        mock_async_add_external_statistics,
        statistic_id,
        meter_number,
        dec_10_2025,
        pst_timezone,
        sample_hourly_data_dec_10_partial,
    ):
        """Verify baseline uses yesterday's 11 PM hour (23:00 local = 07:00 UTC next day).

        This is the PRIMARY test preventing v1.0.13 negative midnight values bug.
        """
        # Mock yesterday's final hour (Dec 9 at 11 PM PST = Dec 10 at 07:00 UTC)
        yesterday_final_sum = 931.18  # Cumulative sum at end of Dec 9
        yesterday_11pm_utc = datetime(2025, 12, 10, 7, 0, 0, tzinfo=dt_util.UTC)

        mock_get_last_stats = Mock(return_value={
            statistic_id: [{
                "start": yesterday_11pm_utc,
                "sum": yesterday_final_sum,
            }]
        })

        with patch("custom_components.acwd.statistics.get_instance", mock_get_instance), \
             patch("custom_components.acwd.statistics.get_last_statistics", mock_get_last_stats), \
             patch("custom_components.acwd.statistics.async_add_external_statistics", mock_async_add_external_statistics), \
             patch("custom_components.acwd.statistics.dt_util.get_default_time_zone", return_value=pst_timezone), \
             patch("custom_components.acwd.statistics.dt_util.as_utc", side_effect=lambda dt: dt.astimezone(dt_util.UTC)):

            # Import today's partial data
            hourly_records = sample_hourly_data_dec_10_partial["objUsageGenerationResultSetTwo"]
            date_dt = datetime.combine(dec_10_2025, datetime.min.time()).replace(tzinfo=pst_timezone)

            await async_import_hourly_statistics(mock_hass, meter_number, hourly_records, date_dt)

            # Verify statistics were imported
            assert mock_async_add_external_statistics.called
            call_args = mock_async_add_external_statistics.call_args
            statistics = call_args[0][1]  # Second argument is the statistics list

            # First hour should be: yesterday_final + first_hour_usage
            first_hour_usage = hourly_records[0]["UsageValue"]  # 3.89 gallons
            expected_first_cumulative = yesterday_final_sum + first_hour_usage  # 931.18 + 3.89 = 935.07

            assert len(statistics) == len(hourly_records)
            assert statistics[0].sum == pytest.approx(expected_first_cumulative, rel=0.01)
            assert statistics[0].sum > 0, "First hour cumulative must be positive (prevents v1.0.13 bug)"

    async def test_baseline_when_no_previous_data(
        self,
        mock_hass,
        mock_get_instance,
        mock_async_add_external_statistics,
        statistic_id,
        meter_number,
        dec_9_2025,
        pst_timezone,
        sample_hourly_data_dec_9,
    ):
        """Verify baseline = 0 when no historical statistics exist."""
        # Mock empty statistics (first time import)
        mock_get_last_stats = Mock(return_value={})

        with patch("custom_components.acwd.statistics.get_instance", mock_get_instance), \
             patch("custom_components.acwd.statistics.get_last_statistics", mock_get_last_stats), \
             patch("custom_components.acwd.statistics.async_add_external_statistics", mock_async_add_external_statistics), \
             patch("custom_components.acwd.statistics.dt_util.get_default_time_zone", return_value=pst_timezone), \
             patch("custom_components.acwd.statistics.dt_util.as_utc", side_effect=lambda dt: dt.astimezone(dt_util.UTC)):

            hourly_records = sample_hourly_data_dec_9["objUsageGenerationResultSetTwo"]
            date_dt = datetime.combine(dec_9_2025, datetime.min.time()).replace(tzinfo=pst_timezone)

            await async_import_hourly_statistics(mock_hass, meter_number, hourly_records, date_dt)

            # Verify first hour starts from 0
            assert mock_async_add_external_statistics.called
            statistics = mock_async_add_external_statistics.call_args[0][1]

            first_hour_usage = hourly_records[0]["UsageValue"]  # 2.17 gallons
            assert statistics[0].sum == pytest.approx(first_hour_usage, rel=0.01)

    async def test_baseline_with_today_partial_data_exists(
        self,
        mock_hass,
        mock_get_instance,
        mock_async_add_external_statistics,
        statistic_id,
        meter_number,
        dec_10_2025,
        pst_timezone,
        sample_hourly_data_dec_10_partial,
    ):
        """Verify extended 48-hour search when last stat is from today.

        This prevents v1.0.13 bug where today's partial sum was reused as baseline.
        """
        # Mock last statistic being from today at 8 AM (partial data)
        today_8am_pst = datetime(2025, 12, 10, 8, 0, 0, tzinfo=pst_timezone)
        today_8am_utc = today_8am_pst.astimezone(dt_util.UTC)
        today_partial_sum = 950.0  # This should NOT be used as baseline

        # Yesterday's final hour (correct baseline)
        yesterday_final_sum = 931.18
        yesterday_11pm_utc = datetime(2025, 12, 10, 7, 0, 0, tzinfo=dt_util.UTC)

        # First call returns today's stat, extended search returns yesterday's
        mock_get_last_stats_first = Mock(return_value={
            statistic_id: [{"start": today_8am_utc, "sum": today_partial_sum}]
        })
        mock_get_last_stats_extended = Mock(return_value={
            statistic_id: [
                {"start": today_8am_utc, "sum": today_partial_sum},
                {"start": yesterday_11pm_utc, "sum": yesterday_final_sum},
            ]
        })

        call_count = {"count": 0}

        def get_last_stats_side_effect(hass, count, stat_id, convert, types):
            call_count["count"] += 1
            if call_count["count"] == 1:
                return mock_get_last_stats_first(hass, count, stat_id, convert, types)
            return mock_get_last_stats_extended(hass, count, stat_id, convert, types)

        with patch("custom_components.acwd.statistics.get_instance", mock_get_instance), \
             patch("custom_components.acwd.statistics.get_last_statistics", side_effect=get_last_stats_side_effect), \
             patch("custom_components.acwd.statistics.async_add_external_statistics", mock_async_add_external_statistics), \
             patch("custom_components.acwd.statistics.dt_util.get_default_time_zone", return_value=pst_timezone), \
             patch("custom_components.acwd.statistics.dt_util.as_utc", side_effect=lambda dt: dt.astimezone(dt_util.UTC)):

            hourly_records = sample_hourly_data_dec_10_partial["objUsageGenerationResultSetTwo"]
            date_dt = datetime.combine(dec_10_2025, datetime.min.time()).replace(tzinfo=pst_timezone)

            await async_import_hourly_statistics(mock_hass, meter_number, hourly_records, date_dt)

            # Verify it used yesterday's final sum, not today's partial
            statistics = mock_async_add_external_statistics.call_args[0][1]
            first_hour_usage = hourly_records[0]["UsageValue"]
            expected_first_cumulative = yesterday_final_sum + first_hour_usage

            assert statistics[0].sum == pytest.approx(expected_first_cumulative, rel=0.01)
            assert statistics[0].sum != pytest.approx(today_partial_sum + first_hour_usage, rel=0.01)

    async def test_baseline_timestamp_as_float(
        self,
        mock_hass,
        mock_get_instance,
        mock_async_add_external_statistics,
        statistic_id,
        meter_number,
        dec_10_2025,
        pst_timezone,
        sample_hourly_data_dec_10_partial,
    ):
        """Verify float Unix timestamp is converted to datetime.

        This prevents v1.0.14 type comparison error.
        """
        # Mock last statistic with Unix timestamp (float) instead of datetime
        yesterday_final_sum = 931.18
        yesterday_11pm_utc = datetime(2025, 12, 10, 7, 0, 0, tzinfo=dt_util.UTC)
        unix_timestamp = yesterday_11pm_utc.timestamp()  # Convert to float

        mock_get_last_stats = Mock(return_value={
            statistic_id: [{
                "start": unix_timestamp,  # Float instead of datetime
                "sum": yesterday_final_sum,
            }]
        })

        with patch("custom_components.acwd.statistics.get_instance", mock_get_instance), \
             patch("custom_components.acwd.statistics.get_last_statistics", mock_get_last_stats), \
             patch("custom_components.acwd.statistics.async_add_external_statistics", mock_async_add_external_statistics), \
             patch("custom_components.acwd.statistics.dt_util.get_default_time_zone", return_value=pst_timezone), \
             patch("custom_components.acwd.statistics.dt_util.as_utc", side_effect=lambda dt: dt.astimezone(dt_util.UTC)):

            hourly_records = sample_hourly_data_dec_10_partial["objUsageGenerationResultSetTwo"]
            date_dt = datetime.combine(dec_10_2025, datetime.min.time()).replace(tzinfo=pst_timezone)

            # Should not raise TypeError
            await async_import_hourly_statistics(mock_hass, meter_number, hourly_records, date_dt)

            # Verify baseline was used correctly
            statistics = mock_async_add_external_statistics.call_args[0][1]
            first_hour_usage = hourly_records[0]["UsageValue"]
            expected_first_cumulative = yesterday_final_sum + first_hour_usage

            assert statistics[0].sum == pytest.approx(expected_first_cumulative, rel=0.01)

    async def test_baseline_timestamp_as_datetime(
        self,
        mock_hass,
        mock_get_instance,
        mock_async_add_external_statistics,
        statistic_id,
        meter_number,
        dec_10_2025,
        pst_timezone,
        sample_hourly_data_dec_10_partial,
    ):
        """Verify datetime timestamp is used directly without conversion."""
        yesterday_final_sum = 931.18
        yesterday_11pm_utc = datetime(2025, 12, 10, 7, 0, 0, tzinfo=dt_util.UTC)

        mock_get_last_stats = Mock(return_value={
            statistic_id: [{
                "start": yesterday_11pm_utc,  # Already a datetime
                "sum": yesterday_final_sum,
            }]
        })

        with patch("custom_components.acwd.statistics.get_instance", mock_get_instance), \
             patch("custom_components.acwd.statistics.get_last_statistics", mock_get_last_stats), \
             patch("custom_components.acwd.statistics.async_add_external_statistics", mock_async_add_external_statistics), \
             patch("custom_components.acwd.statistics.dt_util.get_default_time_zone", return_value=pst_timezone), \
             patch("custom_components.acwd.statistics.dt_util.as_utc", side_effect=lambda dt: dt.astimezone(dt_util.UTC)):

            hourly_records = sample_hourly_data_dec_10_partial["objUsageGenerationResultSetTwo"]
            date_dt = datetime.combine(dec_10_2025, datetime.min.time()).replace(tzinfo=pst_timezone)

            await async_import_hourly_statistics(mock_hass, meter_number, hourly_records, date_dt)

            # Verify baseline was used
            statistics = mock_async_add_external_statistics.call_args[0][1]
            first_hour_usage = hourly_records[0]["UsageValue"]
            expected_first_cumulative = yesterday_final_sum + first_hour_usage

            assert statistics[0].sum == pytest.approx(expected_first_cumulative, rel=0.01)


@pytest.mark.unit
@pytest.mark.skip(reason="Pending Home Assistant mocking improvements - Phase 2")
@pytest.mark.timezone
@pytest.mark.asyncio
class TestTimezoneHandling:
    """Test timezone handling to prevent v1.0.16 regression."""

    async def test_timezone_midnight_conversion_pst(
        self,
        mock_hass,
        mock_get_instance,
        mock_async_add_external_statistics,
        meter_number,
        dec_10_2025,
        pst_timezone,
        sample_hourly_data_dec_10_partial,
    ):
        """Verify Dec 10 00:00 PST = Dec 10 08:00 UTC.

        This is the PRIMARY test preventing v1.0.16 timezone bug.
        """
        mock_get_last_stats = Mock(return_value={})

        with patch("custom_components.acwd.statistics.get_instance", mock_get_instance), \
             patch("custom_components.acwd.statistics.get_last_statistics", mock_get_last_stats), \
             patch("custom_components.acwd.statistics.async_add_external_statistics", mock_async_add_external_statistics), \
             patch("custom_components.acwd.statistics.dt_util.get_default_time_zone", return_value=pst_timezone), \
             patch("custom_components.acwd.statistics.dt_util.as_utc", side_effect=lambda dt: dt.astimezone(dt_util.UTC)):

            hourly_records = sample_hourly_data_dec_10_partial["objUsageGenerationResultSetTwo"]
            date_dt = datetime.combine(dec_10_2025, datetime.min.time()).replace(tzinfo=pst_timezone)

            await async_import_hourly_statistics(mock_hass, meter_number, hourly_records, date_dt)

            # Verify midnight hour timestamp is correct in UTC
            statistics = mock_async_add_external_statistics.call_args[0][1]
            midnight_stat = statistics[0]

            # Dec 10 00:00 PST should be Dec 10 08:00 UTC
            expected_midnight_utc = datetime(2025, 12, 10, 8, 0, 0, tzinfo=dt_util.UTC)
            assert midnight_stat.start == expected_midnight_utc

    async def test_timezone_midnight_conversion_est(
        self,
        mock_hass,
        mock_get_instance,
        mock_async_add_external_statistics,
        meter_number,
        dec_10_2025,
        est_timezone,
        sample_hourly_data_dec_10_partial,
    ):
        """Verify Dec 10 00:00 EST = Dec 10 05:00 UTC."""
        mock_get_last_stats = Mock(return_value={})

        with patch("custom_components.acwd.statistics.get_instance", mock_get_instance), \
             patch("custom_components.acwd.statistics.get_last_statistics", mock_get_last_stats), \
             patch("custom_components.acwd.statistics.async_add_external_statistics", mock_async_add_external_statistics), \
             patch("custom_components.acwd.statistics.dt_util.get_default_time_zone", return_value=est_timezone), \
             patch("custom_components.acwd.statistics.dt_util.as_utc", side_effect=lambda dt: dt.astimezone(dt_util.UTC)):

            hourly_records = sample_hourly_data_dec_10_partial["objUsageGenerationResultSetTwo"]
            date_dt = datetime.combine(dec_10_2025, datetime.min.time()).replace(tzinfo=est_timezone)

            await async_import_hourly_statistics(mock_hass, meter_number, hourly_records, date_dt)

            statistics = mock_async_add_external_statistics.call_args[0][1]
            midnight_stat = statistics[0]

            # Dec 10 00:00 EST should be Dec 10 05:00 UTC
            expected_midnight_utc = datetime(2025, 12, 10, 5, 0, 0, tzinfo=dt_util.UTC)
            assert midnight_stat.start == expected_midnight_utc

    async def test_create_local_datetime_pst(
        self,
        mock_hass,
        mock_get_instance,
        mock_async_add_external_statistics,
        meter_number,
        dec_10_2025,
        pst_timezone,
        sample_hourly_data_dec_10_partial,
    ):
        """Verify date_dt created with local timezone (PST).

        This prevents v1.0.16 naive datetime bug.
        """
        mock_get_last_stats = Mock(return_value={})

        with patch("custom_components.acwd.statistics.get_instance", mock_get_instance), \
             patch("custom_components.acwd.statistics.get_last_statistics", mock_get_last_stats), \
             patch("custom_components.acwd.statistics.async_add_external_statistics", mock_async_add_external_statistics), \
             patch("custom_components.acwd.statistics.dt_util.get_default_time_zone", return_value=pst_timezone), \
             patch("custom_components.acwd.statistics.dt_util.as_utc", side_effect=lambda dt: dt.astimezone(dt_util.UTC)):

            hourly_records = sample_hourly_data_dec_10_partial["objUsageGenerationResultSetTwo"]

            # Create date_dt with timezone (this is what __init__.py does)
            date_dt = datetime.combine(dec_10_2025, datetime.min.time()).replace(tzinfo=pst_timezone)

            # Verify it has timezone info
            assert date_dt.tzinfo is not None
            assert date_dt.tzinfo == pst_timezone

            await async_import_hourly_statistics(mock_hass, meter_number, hourly_records, date_dt)

            # All timestamps should be properly converted to UTC
            statistics = mock_async_add_external_statistics.call_args[0][1]
            for stat in statistics:
                assert stat.start.tzinfo == dt_util.UTC

    async def test_create_local_datetime_est(
        self,
        mock_hass,
        mock_get_instance,
        mock_async_add_external_statistics,
        meter_number,
        dec_10_2025,
        est_timezone,
        sample_hourly_data_dec_10_partial,
    ):
        """Verify works in different timezones (EST)."""
        mock_get_last_stats = Mock(return_value={})

        with patch("custom_components.acwd.statistics.get_instance", mock_get_instance), \
             patch("custom_components.acwd.statistics.get_last_statistics", mock_get_last_stats), \
             patch("custom_components.acwd.statistics.async_add_external_statistics", mock_async_add_external_statistics), \
             patch("custom_components.acwd.statistics.dt_util.get_default_time_zone", return_value=est_timezone), \
             patch("custom_components.acwd.statistics.dt_util.as_utc", side_effect=lambda dt: dt.astimezone(dt_util.UTC)):

            hourly_records = sample_hourly_data_dec_10_partial["objUsageGenerationResultSetTwo"]
            date_dt = datetime.combine(dec_10_2025, datetime.min.time()).replace(tzinfo=est_timezone)

            await async_import_hourly_statistics(mock_hass, meter_number, hourly_records, date_dt)

            statistics = mock_async_add_external_statistics.call_args[0][1]

            # Verify all timestamps are in UTC
            for stat in statistics:
                assert stat.start.tzinfo == dt_util.UTC


@pytest.mark.skip(reason="Pending Home Assistant mocking improvements - Phase 2")
@pytest.mark.unit
@pytest.mark.asyncio
class TestCumulativeSumCalculation:
    """Test cumulative sum calculations."""

    async def test_cumulative_sum_basic(
        self,
        mock_hass,
        mock_get_instance,
        mock_async_add_external_statistics,
        meter_number,
        dec_9_2025,
        pst_timezone,
    ):
        """Verify cumulative sum calculation: baseline + hour1 + hour2 + ..."""
        baseline = 100.0
        yesterday_11pm_utc = datetime(2025, 12, 9, 7, 0, 0, tzinfo=dt_util.UTC)

        mock_get_last_stats = Mock(return_value={
            f"acwd:{meter_number}_hourly_usage": [{
                "start": yesterday_11pm_utc,
                "sum": baseline,
            }]
        })

        hourly_records = [
            {"Hourly": "12:00 AM", "UsageValue": 10.0},
            {"Hourly": "1:00 AM", "UsageValue": 20.0},
            {"Hourly": "2:00 AM", "UsageValue": 30.0},
        ]

        with patch("custom_components.acwd.statistics.get_instance", mock_get_instance), \
             patch("custom_components.acwd.statistics.get_last_statistics", mock_get_last_stats), \
             patch("custom_components.acwd.statistics.async_add_external_statistics", mock_async_add_external_statistics), \
             patch("custom_components.acwd.statistics.dt_util.get_default_time_zone", return_value=pst_timezone), \
             patch("custom_components.acwd.statistics.dt_util.as_utc", side_effect=lambda dt: dt.astimezone(dt_util.UTC)):

            date_dt = datetime.combine(dec_9_2025, datetime.min.time()).replace(tzinfo=pst_timezone)
            await async_import_hourly_statistics(mock_hass, meter_number, hourly_records, date_dt)

            statistics = mock_async_add_external_statistics.call_args[0][1]

            # Verify cumulative progression
            assert statistics[0].sum == pytest.approx(110.0, rel=0.01)  # 100 + 10
            assert statistics[1].sum == pytest.approx(130.0, rel=0.01)  # 110 + 20
            assert statistics[2].sum == pytest.approx(160.0, rel=0.01)  # 130 + 30

    async def test_cumulative_sum_with_zero_usage(
        self,
        mock_hass,
        mock_get_instance,
        mock_async_add_external_statistics,
        meter_number,
        dec_9_2025,
        pst_timezone,
    ):
        """Verify zero usage hours don't break cumulation."""
        mock_get_last_stats = Mock(return_value={})

        hourly_records = [
            {"Hourly": "12:00 AM", "UsageValue": 0.0},
            {"Hourly": "1:00 AM", "UsageValue": 0.0},
            {"Hourly": "2:00 AM", "UsageValue": 5.0},
            {"Hourly": "3:00 AM", "UsageValue": 0.0},
        ]

        with patch("custom_components.acwd.statistics.get_instance", mock_get_instance), \
             patch("custom_components.acwd.statistics.get_last_statistics", mock_get_last_stats), \
             patch("custom_components.acwd.statistics.async_add_external_statistics", mock_async_add_external_statistics), \
             patch("custom_components.acwd.statistics.dt_util.get_default_time_zone", return_value=pst_timezone), \
             patch("custom_components.acwd.statistics.dt_util.as_utc", side_effect=lambda dt: dt.astimezone(dt_util.UTC)):

            date_dt = datetime.combine(dec_9_2025, datetime.min.time()).replace(tzinfo=pst_timezone)
            await async_import_hourly_statistics(mock_hass, meter_number, hourly_records, date_dt)

            statistics = mock_async_add_external_statistics.call_args[0][1]

            assert statistics[0].sum == pytest.approx(0.0, rel=0.01)
            assert statistics[1].sum == pytest.approx(0.0, rel=0.01)
            assert statistics[2].sum == pytest.approx(5.0, rel=0.01)
            assert statistics[3].sum == pytest.approx(5.0, rel=0.01)

    async def test_cumulative_sum_precision(
        self,
        mock_hass,
        mock_get_instance,
        mock_async_add_external_statistics,
        meter_number,
        dec_9_2025,
        pst_timezone,
    ):
        """Verify floating-point precision in large cumulative values."""
        large_baseline = 999999.99
        yesterday_11pm_utc = datetime(2025, 12, 9, 7, 0, 0, tzinfo=dt_util.UTC)

        mock_get_last_stats = Mock(return_value={
            f"acwd:{meter_number}_hourly_usage": [{
                "start": yesterday_11pm_utc,
                "sum": large_baseline,
            }]
        })

        hourly_records = [
            {"Hourly": "12:00 AM", "UsageValue": 0.01},
        ]

        with patch("custom_components.acwd.statistics.get_instance", mock_get_instance), \
             patch("custom_components.acwd.statistics.get_last_statistics", mock_get_last_stats), \
             patch("custom_components.acwd.statistics.async_add_external_statistics", mock_async_add_external_statistics), \
             patch("custom_components.acwd.statistics.dt_util.get_default_time_zone", return_value=pst_timezone), \
             patch("custom_components.acwd.statistics.dt_util.as_utc", side_effect=lambda dt: dt.astimezone(dt_util.UTC)):

            date_dt = datetime.combine(dec_9_2025, datetime.min.time()).replace(tzinfo=pst_timezone)
            await async_import_hourly_statistics(mock_hass, meter_number, hourly_records, date_dt)

            statistics = mock_async_add_external_statistics.call_args[0][1]

            # Verify precision is maintained
            expected = large_baseline + 0.01
            assert statistics[0].sum == pytest.approx(expected, rel=1e-6)
