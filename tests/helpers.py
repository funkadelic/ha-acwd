"""Shared mock factories for ACWD tests."""

from contextlib import contextmanager
from datetime import timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch


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


@contextmanager
def patch_statistics(mock_get_instance, mock_async_add_external_statistics,
                     mock_get_last_stats, tz):
    """Common patches for statistics module tests.

    Args:
        mock_get_instance: Mock for recorder.get_instance.
        mock_async_add_external_statistics: Mock for recorder.async_add_external_statistics.
        mock_get_last_stats: Mock or callable for recorder.get_last_statistics.
        tz: Timezone to return from dt_util.get_default_time_zone.
    """
    last_stats_kwargs = (
        {"side_effect": mock_get_last_stats}
        if callable(mock_get_last_stats) and not isinstance(mock_get_last_stats, Mock)
        else {"new": mock_get_last_stats}
    )
    with patch("custom_components.acwd.statistics.get_instance", mock_get_instance), \
         patch("custom_components.acwd.statistics.get_last_statistics", **last_stats_kwargs), \
         patch("custom_components.acwd.statistics.async_add_external_statistics", mock_async_add_external_statistics), \
         patch("custom_components.acwd.statistics.dt_util.get_default_time_zone", return_value=tz), \
         patch("custom_components.acwd.statistics.dt_util.as_utc", side_effect=lambda dt: dt.astimezone(timezone.utc)):
        yield
