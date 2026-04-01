"""Shared mock factories for ACWD tests."""

from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from custom_components.acwd.acwd_api import ACWDClient


def make_mock_hass():
    """Return a MagicMock hass suitable for service and coordinator tests."""
    hass = MagicMock()
    hass.services.has_service = Mock(return_value=False)
    hass.services.async_register = Mock()
    hass.services.async_remove = Mock()
    hass.data = {}
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.config_entries.async_loaded_entries = Mock(return_value=[])
    hass.async_add_executor_job = AsyncMock(side_effect=lambda func, *args: func(*args))
    return hass


def make_mock_entry(entry_id="test_entry_id"):
    """Return a MagicMock config entry."""
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.data = {"username": "test_user", "password": "test_pass"}  # NOSONAR
    return entry


def make_mock_coordinator(entry):
    """Return a MagicMock coordinator."""
    coordinator = MagicMock()
    coordinator.entry = entry
    coordinator.client.user_info = {"AccountNumber": "12345"}
    coordinator.client.meter_number = "230057301"
    return coordinator


def make_date_dt(date, tz):
    """Return a timezone-aware datetime at midnight for the given date."""
    return datetime.combine(date, datetime.min.time()).replace(tzinfo=tz)


def make_client():
    """Return a fresh ACWDClient instance."""
    return ACWDClient("user@example.com", "secret")


def make_logged_in_client(meter_cached=True):
    """Return a logged-in ACWDClient with optional pre-cached meter."""
    client = make_client()
    client.logged_in = True
    client.csrf_token = "tok123"
    client._water_meter_number = "230057301" if meter_cached else None
    return client


def make_baseline_mock(statistic_id, start, sum_value):
    """Return a Mock for get_last_statistics with a single baseline entry."""
    return Mock(return_value={statistic_id: [{"start": start, "sum": sum_value}]})


@contextmanager
def patch_statistics(mock_get_instance, mock_async_add_external_statistics, mock_get_last_stats, tz):
    """Common patches for statistics module tests."""
    last_stats_kwargs = (
        {"side_effect": mock_get_last_stats}
        if callable(mock_get_last_stats) and not isinstance(mock_get_last_stats, Mock)
        else {"new": mock_get_last_stats}
    )
    with (
        patch("custom_components.acwd.statistics.get_instance", mock_get_instance),
        patch("custom_components.acwd.statistics.get_last_statistics", **last_stats_kwargs),
        patch(
            "custom_components.acwd.statistics.async_add_external_statistics",
            mock_async_add_external_statistics,
        ),
        patch(
            "custom_components.acwd.statistics.dt_util.get_default_time_zone",
            return_value=tz,
        ),
        patch(
            "custom_components.acwd.statistics.dt_util.as_utc",
            side_effect=lambda dt: dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC),
        ),
    ):
        yield
