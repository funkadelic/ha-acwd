"""Shared pytest fixtures and configuration for ACWD tests."""
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, create_autospec
from zoneinfo import ZoneInfo

import pytest

# Export mock classes for use in test files
__all__ = ["StatisticData", "StatisticMetaData", "StatisticMeanType", "UnitOfVolume", "dt_util"]


# Mock Home Assistant classes and utilities
@dataclass
class StatisticData:
    """Mock StatisticData from Home Assistant recorder."""
    start: datetime
    state: float | None = None
    sum: float | None = None


@dataclass
class StatisticMetaData:
    """Mock StatisticMetaData from Home Assistant recorder."""
    has_mean: bool
    has_sum: bool
    name: str | None
    source: str
    statistic_id: str
    unit_of_measurement: str | None
    unit_class: str | None = None
    mean_type: str | None = None


class StatisticMeanType:
    """Mock StatisticMeanType enum from Home Assistant recorder."""
    NONE = "none"


class _GallonsUnit:
    """Mock gallons unit with value attribute."""
    value = "gal"


class UnitOfVolume:
    """Mock UnitOfVolume from Home Assistant."""
    GALLONS = _GallonsUnit()


class dt_util:
    """Mock dt_util from Home Assistant."""
    UTC = timezone.utc

    @staticmethod
    def get_default_time_zone():
        """Return default timezone (PST by default for tests)."""
        return ZoneInfo("America/Los_Angeles")

    @staticmethod
    def as_utc(dt: datetime) -> datetime:
        """Convert timezone-aware datetime to UTC."""
        if dt.tzinfo is None:
            raise ValueError("Cannot convert naive datetime to UTC")
        return dt.astimezone(timezone.utc)


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
def mock_as_utc():
    """Mock dt_util.as_utc to convert timezone-aware datetime to UTC."""
    def _as_utc(dt):
        if dt.tzinfo is None:
            raise ValueError("Cannot convert naive datetime to UTC")
        return dt.astimezone(dt_util.UTC)
    return Mock(side_effect=_as_utc)


@pytest.fixture
def mock_recorder_instance():
    """Create a mocked recorder instance."""
    instance = MagicMock()
    # async_add_executor_job executes a sync function in an executor and returns the result
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
    def _get_last_stats(hass, count, statistic_id, convert_units, types):
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


# Mock the homeassistant module before any tests import it
def _setup_homeassistant_mocks():
    """Set up mock homeassistant module for imports."""
    # Create mock homeassistant module structure
    ha_mock = MagicMock()

    # Create proper module mocks (not MagicMock) for nested imports
    from types import ModuleType

    # Create recorder module
    recorder_mock = ModuleType("recorder")
    recorder_mock.StatisticData = StatisticData
    recorder_mock.StatisticMetaData = StatisticMetaData
    recorder_mock.StatisticMeanType = StatisticMeanType
    recorder_mock.get_instance = Mock()
    recorder_mock.get_last_statistics = Mock()
    recorder_mock.async_add_external_statistics = AsyncMock()
    recorder_mock.statistics_during_period = Mock()

    # Create recorder.statistics submodule
    recorder_statistics_mock = ModuleType("statistics")
    recorder_statistics_mock.StatisticData = StatisticData
    recorder_statistics_mock.StatisticMetaData = StatisticMetaData
    recorder_statistics_mock.StatisticMeanType = StatisticMeanType
    recorder_statistics_mock.get_last_statistics = Mock()
    recorder_statistics_mock.async_add_external_statistics = AsyncMock()
    recorder_statistics_mock.statistics_during_period = Mock()

    # Create components module
    components_mock = ModuleType("components")
    components_mock.recorder = recorder_mock

    # Create const module
    const_mock = ModuleType("const")
    const_mock.UnitOfVolume = UnitOfVolume
    const_mock.CONF_PASSWORD = "password"
    const_mock.CONF_USERNAME = "username"
    const_mock.Platform = MagicMock()

    # Create util module
    util_mock = ModuleType("util")
    util_mock.dt = dt_util

    # Create helpers module
    helpers_mock = ModuleType("helpers")
    update_coordinator_mock = ModuleType("update_coordinator")
    update_coordinator_mock.DataUpdateCoordinator = MagicMock
    update_coordinator_mock.UpdateFailed = Exception
    helpers_mock.update_coordinator = update_coordinator_mock

    # Create core module
    core_mock = ModuleType("core")
    core_mock.HomeAssistant = MagicMock
    core_mock.ServiceCall = MagicMock
    core_mock.callback = lambda func: func

    # Create config_entries module
    config_entries_mock = ModuleType("config_entries")
    config_entries_mock.ConfigEntry = MagicMock

    # Set up main homeassistant module
    ha_mock.components = components_mock
    ha_mock.const = const_mock
    ha_mock.util = util_mock
    ha_mock.helpers = helpers_mock
    ha_mock.core = core_mock
    ha_mock.config_entries = config_entries_mock

    # Install all mocks in sys.modules
    sys.modules["homeassistant"] = ha_mock
    sys.modules["homeassistant.components"] = components_mock
    sys.modules["homeassistant.components.recorder"] = recorder_mock
    sys.modules["homeassistant.components.recorder.statistics"] = recorder_statistics_mock
    sys.modules["homeassistant.const"] = const_mock
    sys.modules["homeassistant.util"] = util_mock
    sys.modules["homeassistant.helpers"] = helpers_mock
    sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator_mock
    sys.modules["homeassistant.core"] = core_mock
    sys.modules["homeassistant.config_entries"] = config_entries_mock


# Set up mocks before pytest collects tests
_setup_homeassistant_mocks()
