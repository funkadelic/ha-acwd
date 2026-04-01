"""Shared pytest fixtures and configuration for ACWD tests."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock
from zoneinfo import ZoneInfo

import pytest


@pytest.fixture
def mock_hass():
    """Create a mocked HomeAssistant instance."""
    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock(side_effect=lambda func, *args: func(*args))
    return hass


@pytest.fixture
def pst_timezone():
    """Return Pacific Standard Time timezone."""
    return ZoneInfo("America/Los_Angeles")


@pytest.fixture
def est_timezone():
    """Return Eastern Standard Time timezone."""
    return ZoneInfo("America/New_York")


@pytest.fixture
def mock_get_default_timezone(pst_timezone):
    """Mock dt_util.get_default_time_zone to return PST."""
    return Mock(return_value=pst_timezone)


@pytest.fixture
def mock_recorder_instance():
    """Create a mocked recorder instance."""
    instance = MagicMock()

    async def _async_executor(func, *args, **kwargs):
        return func(*args, **kwargs)

    instance.async_add_executor_job = _async_executor
    return instance


@pytest.fixture
def mock_get_instance(mock_recorder_instance):
    """Mock homeassistant.components.recorder.get_instance."""
    return Mock(return_value=mock_recorder_instance)


@pytest.fixture
def mock_get_last_statistics():
    """Mock homeassistant.components.recorder.get_last_statistics."""

    def _get_last_stats(*_args, **_kwargs):
        """Return empty statistics by default."""
        return {}

    return Mock(side_effect=_get_last_stats)


@pytest.fixture
def mock_async_add_external_statistics():
    """Mock homeassistant.components.recorder.async_add_external_statistics."""
    return AsyncMock()


@pytest.fixture
def sample_hourly_data_dec_9():
    """Return realistic hourly data for Dec 9, 2025 (complete 24 hours)."""
    return {
        "objUsageGenerationResultSetTwo": [
            {"Hourly": "12:00 AM", "UsageValue": 2.17},
            {"Hourly": "1:00 AM", "UsageValue": 2.69},
            {"Hourly": "2:00 AM", "UsageValue": 4.11},
            {"Hourly": "3:00 AM", "UsageValue": 5.31},
            {"Hourly": "4:00 AM", "UsageValue": 2.77},
            {"Hourly": "5:00 AM", "UsageValue": 2.32},
            {"Hourly": "6:00 AM", "UsageValue": 2.39},
            {"Hourly": "7:00 AM", "UsageValue": 2.17},
            {"Hourly": "8:00 AM", "UsageValue": 2.39},
            {"Hourly": "9:00 AM", "UsageValue": 2.54},
            {"Hourly": "10:00 AM", "UsageValue": 2.62},
            {"Hourly": "11:00 AM", "UsageValue": 2.39},
            {"Hourly": "12:00 PM", "UsageValue": 41.97},
            {"Hourly": "1:00 PM", "UsageValue": 58.87},
            {"Hourly": "2:00 PM", "UsageValue": 26.91},
            {"Hourly": "3:00 PM", "UsageValue": 4.19},
            {"Hourly": "4:00 PM", "UsageValue": 4.04},
            {"Hourly": "5:00 PM", "UsageValue": 5.09},
            {"Hourly": "6:00 PM", "UsageValue": 4.19},
            {"Hourly": "7:00 PM", "UsageValue": 6.13},
            {"Hourly": "8:00 PM", "UsageValue": 3.83},
            {"Hourly": "9:00 PM", "UsageValue": 4.14},
            {"Hourly": "10:00 PM", "UsageValue": 7.26},
            {"Hourly": "11:00 PM", "UsageValue": 3.82},
        ]
    }


@pytest.fixture
def sample_hourly_data_dec_10_partial():
    """Return realistic hourly data for Dec 10, 2025 (partial through 12 PM)."""
    return {
        "objUsageGenerationResultSetTwo": [
            {"Hourly": "12:00 AM", "UsageValue": 3.89},
            {"Hourly": "1:00 AM", "UsageValue": 2.54},
            {"Hourly": "2:00 AM", "UsageValue": 2.77},
            {"Hourly": "3:00 AM", "UsageValue": 5.31},
            {"Hourly": "4:00 AM", "UsageValue": 4.11},
            {"Hourly": "5:00 AM", "UsageValue": 2.32},
            {"Hourly": "6:00 AM", "UsageValue": 2.39},
            {"Hourly": "7:00 AM", "UsageValue": 3.89},
            {"Hourly": "8:00 AM", "UsageValue": 2.39},
            {"Hourly": "9:00 AM", "UsageValue": 2.32},
            {"Hourly": "10:00 AM", "UsageValue": 2.54},
            {"Hourly": "11:00 AM", "UsageValue": 3.22},
            {"Hourly": "12:00 PM", "UsageValue": 2.24},
        ]
    }


@pytest.fixture
def meter_number():
    """Return the test meter number."""
    return "230057301"


@pytest.fixture
def statistic_id(meter_number):
    """Return the statistic ID for the test meter."""
    return f"acwd:{meter_number}_hourly_usage"


@pytest.fixture
def dec_9_2025():
    """Return December 9, 2025 date."""
    return datetime(2025, 12, 9).date()


@pytest.fixture
def dec_10_2025():
    """Return December 10, 2025 date."""
    return datetime(2025, 12, 10).date()


@pytest.fixture
def expected_dec_9_total(sample_hourly_data_dec_9):
    """Calculate expected total for Dec 9 data."""
    records = sample_hourly_data_dec_9["objUsageGenerationResultSetTwo"]
    return sum(r["UsageValue"] for r in records)


@pytest.fixture
def expected_dec_10_partial_total(sample_hourly_data_dec_10_partial):
    """Calculate expected total for Dec 10 partial data."""
    records = sample_hourly_data_dec_10_partial["objUsageGenerationResultSetTwo"]
    return sum(r["UsageValue"] for r in records)
