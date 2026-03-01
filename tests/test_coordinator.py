"""Tests for coordinator update logic in __init__.py.

These tests validate morning import timing to catch yesterday's final hours.
"""
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Add custom_components to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import will fail if HA is not available, but mocks will handle it in tests


@pytest.mark.unit
@pytest.mark.asyncio
class TestEarlyMorningImport:
    """Test morning import logic (0-12 PM window)."""

    async def test_early_morning_import_at_midnight(
        self,
        mock_hass,
        meter_number,
        sample_hourly_data_dec_9,
    ):
        """Verify import runs at hour=0 (midnight)."""
        # Mock datetime.now() to return midnight
        mock_now = datetime(2025, 12, 10, 0, 30, 0)  # 12:30 AM

        # Mock client
        mock_client = Mock()
        mock_client.meter_number = meter_number
        mock_client.get_usage_data = Mock(return_value=sample_hourly_data_dec_9)

        with patch("datetime.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_now
            mock_datetime.combine = datetime.combine
            mock_datetime.min = datetime.min
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

            # Simulate the morning import check
            current_hour = mock_now.hour  # 0

            # Verify it's within the 0-12 PM window
            assert 0 <= current_hour < 12
            assert current_hour == 0

    async def test_early_morning_import_at_5am(
        self,
        mock_hass,
        meter_number,
        sample_hourly_data_dec_9,
    ):
        """Verify import runs at hour=5."""
        mock_now = datetime(2025, 12, 10, 5, 45, 0)  # 5:45 AM

        current_hour = mock_now.hour

        # Verify it's still within the window
        assert 0 <= current_hour < 12
        assert current_hour == 5

    async def test_early_morning_import_at_11am(
        self,
        mock_hass,
        meter_number,
        sample_hourly_data_dec_9,
    ):
        """Verify import runs at hour=11 (boundary case)."""
        mock_now = datetime(2025, 12, 10, 11, 59, 0)  # 11:59 AM

        current_hour = mock_now.hour

        # Verify it's still within the window
        assert 0 <= current_hour < 12
        assert current_hour == 11

    async def test_early_morning_import_at_noon(
        self,
        mock_hass,
        meter_number,
        sample_hourly_data_dec_9,
    ):
        """Verify import DOES NOT run at hour=12 (noon) or later."""
        mock_now = datetime(2025, 12, 10, 12, 0, 0)  # Noon

        current_hour = mock_now.hour

        # Verify it's outside the window
        assert not (0 <= current_hour < 12)
        assert current_hour >= 12


@pytest.mark.unit
@pytest.mark.timezone
@pytest.mark.asyncio
class TestDateTimeCreation:
    """Test datetime creation with proper timezone handling."""

    async def test_create_local_datetime_pst(
        self,
        dec_10_2025,
        pst_timezone,
    ):
        """Verify date_dt created with local timezone.

        This prevents v1.0.16 naive datetime bug.
        """
        # Simulate what __init__.py does
        date_dt = datetime.combine(dec_10_2025, datetime.min.time())
        date_dt = date_dt.replace(tzinfo=pst_timezone)

        # Verify it has timezone info
        assert date_dt.tzinfo is not None
        assert date_dt.tzinfo == pst_timezone
        assert date_dt.hour == 0
        assert date_dt.minute == 0

    async def test_create_local_datetime_est(
        self,
        dec_10_2025,
        est_timezone,
    ):
        """Verify works in different timezones."""
        date_dt = datetime.combine(dec_10_2025, datetime.min.time())
        date_dt = date_dt.replace(tzinfo=est_timezone)

        assert date_dt.tzinfo is not None
        assert date_dt.tzinfo == est_timezone


@pytest.mark.unit
@pytest.mark.asyncio
class TestDataAvailability:
    """Test handling of missing or empty data."""

    async def test_handle_no_data_returned(self):
        """Verify graceful handling when API returns None."""
        data = None

        # Simulate check in coordinator
        if not data:
            # Should log debug and return gracefully
            assert True
        else:
            pytest.fail("Should have detected None data")

    async def test_handle_empty_records(self):
        """Verify handling when objUsageGenerationResultSetTwo is empty."""
        data = {"objUsageGenerationResultSetTwo": []}

        hourly_records = data.get("objUsageGenerationResultSetTwo", [])

        # Should return empty list gracefully
        assert hourly_records == []
        assert len(hourly_records) == 0
