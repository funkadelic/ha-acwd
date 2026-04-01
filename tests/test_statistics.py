"""Tests for statistics.py - baseline calculation and timezone handling.

These tests prevent regressions of critical bugs:
- v1.0.13: Negative midnight values (baseline calculation)
- v1.0.14: Type conversion errors (float vs datetime timestamps)
- v1.0.16: Timezone handling (naive datetime causing wrong UTC conversions)

"""

from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from custom_components.acwd.statistics import (
    _ensure_datetime,
    _find_baseline_in_stats,
    async_import_hourly_statistics,
)
from tests.helpers import (
    make_baseline_mock,
    make_date_dt,
    patch_statistics,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _import_hourly(
    mock_hass,
    mock_get_instance,
    mock_async_add_external_statistics,
    mock_get_last_stats,
    meter_number,
    hourly_records,
    date_dt,
    tz,
):
    """Run hourly import within patch_statistics and return the statistics list."""
    with patch_statistics(
        mock_get_instance,
        mock_async_add_external_statistics,
        mock_get_last_stats,
        tz,
    ):
        await async_import_hourly_statistics(mock_hass, meter_number, hourly_records, date_dt)
    assert mock_async_add_external_statistics.call_args is not None, "async_add_external_statistics was not called"
    return mock_async_add_external_statistics.call_args[0][2]


async def _import_hourly_from_sample(
    mock_hass,
    mock_get_instance,
    mock_async_add_external_statistics,
    mock_get_last_stats,
    meter_number,
    sample_data,
    date,
    tz,
):
    """Extract records from sample data, build date_dt, import, return statistics."""
    hourly_records = sample_data["objUsageGenerationResultSetTwo"]
    date_dt = make_date_dt(date, tz)
    return await _import_hourly(
        mock_hass,
        mock_get_instance,
        mock_async_add_external_statistics,
        mock_get_last_stats,
        meter_number,
        hourly_records,
        date_dt,
        tz,
    )


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
        yesterday_final_sum = 931.18
        yesterday_11pm_utc = datetime(2025, 12, 10, 7, 0, 0, tzinfo=UTC)

        mock_get_last_stats = make_baseline_mock(statistic_id, yesterday_11pm_utc, yesterday_final_sum)

        hourly_records = sample_hourly_data_dec_10_partial["objUsageGenerationResultSetTwo"]
        statistics = await _import_hourly(
            mock_hass,
            mock_get_instance,
            mock_async_add_external_statistics,
            mock_get_last_stats,
            meter_number,
            hourly_records,
            make_date_dt(dec_10_2025, pst_timezone),
            pst_timezone,
        )

        first_hour_usage = hourly_records[0]["UsageValue"]
        expected_first_cumulative = yesterday_final_sum + first_hour_usage

        assert len(statistics) == len(hourly_records)
        assert statistics[0]["sum"] == pytest.approx(expected_first_cumulative, rel=0.01)
        assert statistics[0]["sum"] > 0, "First hour cumulative must be positive (prevents v1.0.13 bug)"

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
        statistics = await _import_hourly_from_sample(
            mock_hass,
            mock_get_instance,
            mock_async_add_external_statistics,
            Mock(return_value={}),
            meter_number,
            sample_hourly_data_dec_9,
            dec_9_2025,
            pst_timezone,
        )

        first_hour_usage = sample_hourly_data_dec_9["objUsageGenerationResultSetTwo"][0]["UsageValue"]
        assert statistics[0]["sum"] == pytest.approx(first_hour_usage, rel=0.01)

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
        today_8am_pst = datetime(2025, 12, 10, 8, 0, 0, tzinfo=pst_timezone)
        today_8am_utc = today_8am_pst.astimezone(UTC)
        today_partial_sum = 950.0

        yesterday_final_sum = 931.18
        yesterday_11pm_utc = datetime(2025, 12, 10, 7, 0, 0, tzinfo=UTC)

        first_response = {statistic_id: [{"start": today_8am_utc, "sum": today_partial_sum}]}
        extended_response = {
            statistic_id: [
                {"start": today_8am_utc, "sum": today_partial_sum},
                {"start": yesterday_11pm_utc, "sum": yesterday_final_sum},
            ]
        }

        call_count = {"count": 0}

        def get_last_stats_side_effect(*_args, **_kwargs):
            call_count["count"] += 1
            return first_response if call_count["count"] == 1 else extended_response

        statistics = await _import_hourly_from_sample(
            mock_hass,
            mock_get_instance,
            mock_async_add_external_statistics,
            get_last_stats_side_effect,
            meter_number,
            sample_hourly_data_dec_10_partial,
            dec_10_2025,
            pst_timezone,
        )

        hourly_records = sample_hourly_data_dec_10_partial["objUsageGenerationResultSetTwo"]
        first_hour_usage = hourly_records[0]["UsageValue"]
        expected_first_cumulative = yesterday_final_sum + first_hour_usage

        assert statistics[0]["sum"] == pytest.approx(expected_first_cumulative, rel=0.01)
        assert statistics[0]["sum"] != pytest.approx(today_partial_sum + first_hour_usage, rel=0.01)

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
        yesterday_final_sum = 931.18
        yesterday_11pm_utc = datetime(2025, 12, 10, 7, 0, 0, tzinfo=UTC)
        unix_timestamp = yesterday_11pm_utc.timestamp()

        mock_get_last_stats = make_baseline_mock(statistic_id, unix_timestamp, yesterday_final_sum)

        statistics = await _import_hourly_from_sample(
            mock_hass,
            mock_get_instance,
            mock_async_add_external_statistics,
            mock_get_last_stats,
            meter_number,
            sample_hourly_data_dec_10_partial,
            dec_10_2025,
            pst_timezone,
        )

        hourly_records = sample_hourly_data_dec_10_partial["objUsageGenerationResultSetTwo"]
        first_hour_usage = hourly_records[0]["UsageValue"]
        expected_first_cumulative = yesterday_final_sum + first_hour_usage

        assert statistics[0]["sum"] == pytest.approx(expected_first_cumulative, rel=0.01)

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
        yesterday_11pm_utc = datetime(2025, 12, 10, 7, 0, 0, tzinfo=UTC)

        mock_get_last_stats = make_baseline_mock(statistic_id, yesterday_11pm_utc, yesterday_final_sum)

        statistics = await _import_hourly_from_sample(
            mock_hass,
            mock_get_instance,
            mock_async_add_external_statistics,
            mock_get_last_stats,
            meter_number,
            sample_hourly_data_dec_10_partial,
            dec_10_2025,
            pst_timezone,
        )

        hourly_records = sample_hourly_data_dec_10_partial["objUsageGenerationResultSetTwo"]
        first_hour_usage = hourly_records[0]["UsageValue"]
        expected_first_cumulative = yesterday_final_sum + first_hour_usage

        assert statistics[0]["sum"] == pytest.approx(expected_first_cumulative, rel=0.01)


@pytest.mark.unit
class TestEnsureDatetime:
    """Tests for _ensure_datetime helper."""

    def test_none_returns_none(self):
        assert _ensure_datetime(None) is None

    def test_float_returns_datetime(self):
        ts = 1733828400.0
        result = _ensure_datetime(ts)
        assert isinstance(result, datetime)
        assert result.tzinfo == UTC

    def test_datetime_returned_unchanged(self):
        dt = datetime(2025, 12, 10, 7, 0, 0, tzinfo=UTC)
        assert _ensure_datetime(dt) is dt


@pytest.mark.unit
class TestFindBaselineInStats:
    """Tests for _find_baseline_in_stats helper."""

    def test_no_stat_before_target_returns_none(self):
        target = datetime(2025, 12, 10, 8, 0, 0, tzinfo=UTC)
        stats = [
            {"start": datetime(2025, 12, 10, 9, 0, 0, tzinfo=UTC), "sum": 100},
            {"start": datetime(2025, 12, 10, 10, 0, 0, tzinfo=UTC), "sum": 200},
        ]
        assert _find_baseline_in_stats(stats, target) is None

    def test_returns_first_stat_before_target(self):
        target = datetime(2025, 12, 10, 8, 0, 0, tzinfo=UTC)
        stats = [
            {"start": datetime(2025, 12, 10, 9, 0, 0, tzinfo=UTC), "sum": 200},
            {"start": datetime(2025, 12, 10, 7, 0, 0, tzinfo=UTC), "sum": 100},
        ]
        assert _find_baseline_in_stats(stats, target) == 100


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetBaselineSum:
    """Tests for _get_baseline_sum edge cases."""

    async def test_extended_lookback_empty_returns_zero(
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
        """When extended lookback returns empty, baseline falls back to 0."""
        today_8am_utc = datetime(2025, 12, 10, 16, 0, 0, tzinfo=UTC)

        first_response = {statistic_id: [{"start": today_8am_utc, "sum": 950.0}]}
        call_count = {"count": 0}

        def get_last_stats_side_effect(*_args, **_kwargs):
            call_count["count"] += 1
            return first_response if call_count["count"] == 1 else {}

        statistics = await _import_hourly_from_sample(
            mock_hass,
            mock_get_instance,
            mock_async_add_external_statistics,
            get_last_stats_side_effect,
            meter_number,
            sample_hourly_data_dec_10_partial,
            dec_10_2025,
            pst_timezone,
        )

        first_hour_usage = sample_hourly_data_dec_10_partial["objUsageGenerationResultSetTwo"][0]["UsageValue"]
        assert statistics[0]["sum"] == pytest.approx(first_hour_usage, rel=0.01)


@pytest.mark.unit
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
        statistics = await _import_hourly_from_sample(
            mock_hass,
            mock_get_instance,
            mock_async_add_external_statistics,
            Mock(return_value={}),
            meter_number,
            sample_hourly_data_dec_10_partial,
            dec_10_2025,
            pst_timezone,
        )

        expected_midnight_utc = datetime(2025, 12, 10, 8, 0, 0, tzinfo=UTC)
        assert statistics[0]["start"] == expected_midnight_utc

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
        statistics = await _import_hourly_from_sample(
            mock_hass,
            mock_get_instance,
            mock_async_add_external_statistics,
            Mock(return_value={}),
            meter_number,
            sample_hourly_data_dec_10_partial,
            dec_10_2025,
            est_timezone,
        )

        expected_midnight_utc = datetime(2025, 12, 10, 5, 0, 0, tzinfo=UTC)
        assert statistics[0]["start"] == expected_midnight_utc

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
        date_dt = make_date_dt(dec_10_2025, pst_timezone)

        assert date_dt.tzinfo is not None
        assert date_dt.tzinfo == pst_timezone

        statistics = await _import_hourly_from_sample(
            mock_hass,
            mock_get_instance,
            mock_async_add_external_statistics,
            Mock(return_value={}),
            meter_number,
            sample_hourly_data_dec_10_partial,
            dec_10_2025,
            pst_timezone,
        )

        for stat in statistics:
            assert stat["start"].tzinfo == UTC

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
        statistics = await _import_hourly_from_sample(
            mock_hass,
            mock_get_instance,
            mock_async_add_external_statistics,
            Mock(return_value={}),
            meter_number,
            sample_hourly_data_dec_10_partial,
            dec_10_2025,
            est_timezone,
        )

        for stat in statistics:
            assert stat["start"].tzinfo == UTC


@pytest.mark.unit
@pytest.mark.asyncio
class TestCumulativeSumCalculation:
    """Test cumulative sum calculations."""

    async def test_cumulative_sum_basic(
        self,
        mock_hass,
        mock_get_instance,
        mock_async_add_external_statistics,
        statistic_id,
        meter_number,
        dec_9_2025,
        pst_timezone,
    ):
        """Verify cumulative sum calculation: baseline + hour1 + hour2 + ..."""
        baseline = 100.0
        yesterday_11pm_utc = datetime(2025, 12, 9, 7, 0, 0, tzinfo=UTC)

        hourly_records = [
            {"Hourly": "12:00 AM", "UsageValue": 10.0},
            {"Hourly": "1:00 AM", "UsageValue": 20.0},
            {"Hourly": "2:00 AM", "UsageValue": 30.0},
        ]

        statistics = await _import_hourly(
            mock_hass,
            mock_get_instance,
            mock_async_add_external_statistics,
            make_baseline_mock(statistic_id, yesterday_11pm_utc, baseline),
            meter_number,
            hourly_records,
            make_date_dt(dec_9_2025, pst_timezone),
            pst_timezone,
        )

        assert statistics[0]["sum"] == pytest.approx(110.0, rel=0.01)
        assert statistics[1]["sum"] == pytest.approx(130.0, rel=0.01)
        assert statistics[2]["sum"] == pytest.approx(160.0, rel=0.01)

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
        hourly_records = [
            {"Hourly": "12:00 AM", "UsageValue": 0.0},
            {"Hourly": "1:00 AM", "UsageValue": 0.0},
            {"Hourly": "2:00 AM", "UsageValue": 5.0},
            {"Hourly": "3:00 AM", "UsageValue": 0.0},
        ]

        statistics = await _import_hourly(
            mock_hass,
            mock_get_instance,
            mock_async_add_external_statistics,
            Mock(return_value={}),
            meter_number,
            hourly_records,
            make_date_dt(dec_9_2025, pst_timezone),
            pst_timezone,
        )

        assert statistics[0]["sum"] == pytest.approx(0.0, rel=0.01)
        assert statistics[1]["sum"] == pytest.approx(0.0, rel=0.01)
        assert statistics[2]["sum"] == pytest.approx(5.0, rel=0.01)
        assert statistics[3]["sum"] == pytest.approx(5.0, rel=0.01)

    async def test_cumulative_sum_precision(
        self,
        mock_hass,
        mock_get_instance,
        mock_async_add_external_statistics,
        statistic_id,
        meter_number,
        dec_9_2025,
        pst_timezone,
    ):
        """Verify floating-point precision in large cumulative values."""
        large_baseline = 999999.99
        yesterday_11pm_utc = datetime(2025, 12, 9, 7, 0, 0, tzinfo=UTC)

        hourly_records = [
            {"Hourly": "12:00 AM", "UsageValue": 0.01},
        ]

        statistics = await _import_hourly(
            mock_hass,
            mock_get_instance,
            mock_async_add_external_statistics,
            make_baseline_mock(statistic_id, yesterday_11pm_utc, large_baseline),
            meter_number,
            hourly_records,
            make_date_dt(dec_9_2025, pst_timezone),
            pst_timezone,
        )

        expected = large_baseline + 0.01
        assert statistics[0]["sum"] == pytest.approx(expected, rel=1e-6)
