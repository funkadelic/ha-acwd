"""Tests for ACWD __init__.py service lifecycle.

Validates the domain-level service registration contract (SRVC-01, SRVC-02, QUAL-03)
implemented in Phase 2 Plan 02.
"""

import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
import requests
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.acwd import (
    DOMAIN,
    SERVICE_IMPORT_DAILY,
    SERVICE_IMPORT_HOURLY,
    _get_coordinator,
    async_setup,
    async_setup_entry,
    async_unload_entry,
    handle_import_daily,
    handle_import_hourly,
)
from tests.helpers import make_mock_coordinator as _make_mock_coordinator
from tests.helpers import make_mock_entry as _make_mock_entry
from tests.helpers import make_mock_hass as _make_mock_hass

# ---------------------------------------------------------------------------
# SRVC-01: Domain-level service registration
# ---------------------------------------------------------------------------


class TestServiceRegistration:
    """Tests for SRVC-01: services registered in async_setup at domain level."""

    async def test_async_setup_registers_services(self):
        """async_setup registers both services exactly once each."""
        hass = _make_mock_hass()
        await async_setup(hass, {})

        assert hass.services.async_register.call_count == 2
        calls = hass.services.async_register.call_args_list
        registered = {(c.args[0], c.args[1]) for c in calls}
        assert (DOMAIN, SERVICE_IMPORT_HOURLY) in registered
        assert (DOMAIN, SERVICE_IMPORT_DAILY) in registered

    async def test_async_setup_idempotent(self):
        """async_setup skips registration if services already exist."""
        hass = _make_mock_hass()
        hass.services.has_service = Mock(return_value=True)

        await async_setup(hass, {})

        hass.services.async_register.assert_not_called()

    async def test_async_setup_returns_true(self):
        """async_setup returns True on success."""
        hass = _make_mock_hass()
        result = await async_setup(hass, {})
        assert result is True

    async def test_async_setup_entry_does_not_register_services(self):
        """async_setup_entry must NOT register services (registration moved to async_setup)."""
        hass = _make_mock_hass()
        entry = _make_mock_entry()

        with (
            patch("custom_components.acwd.ACWDDataUpdateCoordinator") as mock_coord_cls,
            patch(
                "custom_components.acwd._async_import_initial_yesterday_data",
                new_callable=AsyncMock,
            ),
        ):
            mock_coord = MagicMock()
            mock_coord.async_config_entry_first_refresh = AsyncMock()
            mock_coord_cls.return_value = mock_coord

            await async_setup_entry(hass, entry)

        hass.services.async_register.assert_not_called()


# ---------------------------------------------------------------------------
# SRVC-02: Service unregistration on last entry removal
# ---------------------------------------------------------------------------


class TestServiceUnregistration:
    """Tests for SRVC-02: services removed when last config entry is unloaded."""

    async def test_last_entry_removes_services(self):
        """When the last entry is removed, both services are unregistered."""
        hass = _make_mock_hass()
        entry = _make_mock_entry("entry_a")
        coordinator = _make_mock_coordinator(entry)

        hass.data[DOMAIN] = {entry.entry_id: coordinator}
        # No remaining loaded entries after this one is removed.
        hass.config_entries.async_loaded_entries = Mock(return_value=[])

        await async_unload_entry(hass, entry)

        assert hass.services.async_remove.call_count == 2
        removed = {c.args for c in hass.services.async_remove.call_args_list}
        assert (DOMAIN, SERVICE_IMPORT_HOURLY) in removed
        assert (DOMAIN, SERVICE_IMPORT_DAILY) in removed
        assert entry.entry_id not in hass.data.get(DOMAIN, {})

    async def test_unload_failure_skips_cleanup(self):
        """When platform unload fails, data and services are left untouched."""
        hass = _make_mock_hass()
        entry = _make_mock_entry("entry_a")
        coordinator = _make_mock_coordinator(entry)

        hass.data[DOMAIN] = {entry.entry_id: coordinator}
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)

        result = await async_unload_entry(hass, entry)

        assert result is False
        assert entry.entry_id in hass.data[DOMAIN]
        hass.services.async_remove.assert_not_called()

    async def test_non_last_entry_keeps_services(self):
        """When other entries remain, services are NOT unregistered."""
        hass = _make_mock_hass()
        entry_a = _make_mock_entry("entry_a")
        entry_b = _make_mock_entry("entry_b")

        coordinator_a = _make_mock_coordinator(entry_a)
        coordinator_b = _make_mock_coordinator(entry_b)

        hass.data[DOMAIN] = {
            entry_a.entry_id: coordinator_a,
            entry_b.entry_id: coordinator_b,
        }
        # One entry still loaded after entry_a is removed.
        hass.config_entries.async_loaded_entries = Mock(return_value=[entry_b])

        await async_unload_entry(hass, entry_a)

        hass.services.async_remove.assert_not_called()


# ---------------------------------------------------------------------------
# QUAL-03: ServiceValidationError on invalid inputs
# ---------------------------------------------------------------------------


class TestServiceValidation:
    """Tests for QUAL-03: ServiceValidationError raised for invalid service call inputs."""

    async def test_future_date_raises_validation_error(self):
        """A future date (today or later) raises ServiceValidationError."""

        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)
        hass.data[DOMAIN] = {entry.entry_id: coordinator}

        future_date = datetime.date(2099, 1, 1)
        call = MagicMock()
        call.hass = hass
        call.data = {"date": future_date, "granularity": "hourly"}

        with pytest.raises(ServiceValidationError):
            await handle_import_hourly(call)

    async def test_valid_past_date_no_validation_error(self):
        """A past date does not raise ServiceValidationError."""

        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)
        hass.data[DOMAIN] = {entry.entry_id: coordinator}

        past_date = datetime.date.today() - datetime.timedelta(days=2)
        call = MagicMock()
        call.hass = hass
        call.data = {"date": past_date, "granularity": "hourly"}

        with (
            patch("custom_components.acwd.ACWDClient") as mock_client_cls,
            patch(
                "custom_components.acwd.async_import_hourly_statistics",
                new_callable=AsyncMock,
            ),
        ):
            mock_client = MagicMock()
            mock_client.login.return_value = True
            mock_client.get_usage_data.return_value = {
                "objUsageGenerationResultSetTwo": [
                    {"Hourly": "12:00 AM", "UsageValue": 1.0},
                ]
            }
            mock_client.meter_number = "230057301"
            mock_client.logout.return_value = None
            mock_client_cls.return_value = mock_client

            try:
                await handle_import_hourly(call)
            except ServiceValidationError:
                pytest.fail("ServiceValidationError raised for a valid past date")

    async def test_no_config_raises_error(self):
        """When hass.data has no DOMAIN entry, handler raises HomeAssistantError."""

        hass = _make_mock_hass()
        hass.data = {}  # No domain data at all

        past_date = datetime.date.today() - datetime.timedelta(days=2)
        call = MagicMock()
        call.hass = hass
        call.data = {"date": past_date, "granularity": "hourly"}

        with pytest.raises(HomeAssistantError):
            await handle_import_hourly(call)

    async def test_daily_invalid_range_raises_validation_error(self):
        """start_date > end_date raises ServiceValidationError."""

        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)
        hass.data[DOMAIN] = {entry.entry_id: coordinator}

        call = MagicMock()
        call.hass = hass
        call.data = {
            "start_date": datetime.date(2025, 12, 10),
            "end_date": datetime.date(2025, 12, 5),
        }

        with pytest.raises(ServiceValidationError):
            await handle_import_daily(call)

    async def test_daily_valid_range_no_validation_error(self):
        """A valid past date range does not raise ServiceValidationError."""

        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)
        hass.data[DOMAIN] = {entry.entry_id: coordinator}

        call = MagicMock()
        call.hass = hass
        call.data = {
            "start_date": datetime.date(2025, 12, 1),
            "end_date": datetime.date(2025, 12, 5),
        }

        with (
            patch("custom_components.acwd.ACWDClient") as mock_client_cls,
            patch(
                "custom_components.acwd.async_import_daily_statistics",
                new_callable=AsyncMock,
            ) as mock_import_daily,
        ):
            mock_client = MagicMock()
            mock_client.login.return_value = True
            mock_client.meter_number = "230057301"
            mock_client.get_usage_data.return_value = {
                "objUsageGenerationResultSetTwo": [
                    {"Date": "12/01/2025", "UsageValue": 50.0},
                ]
            }
            mock_client.logout.return_value = None
            mock_client_cls.return_value = mock_client

            try:
                await handle_import_daily(call)
            except ServiceValidationError:
                pytest.fail("ServiceValidationError raised for a valid date range")

            # Verify meter_number (not account_number) is passed to import function
            mock_import_daily.assert_called_once()
            assert mock_import_daily.call_args[0][1] == "230057301"


# ---------------------------------------------------------------------------
# _get_coordinator: entry_id disambiguation logic
# ---------------------------------------------------------------------------


class TestGetCoordinator:
    """Tests for _get_coordinator entry_id lookup and multi-entry disambiguation."""

    def test_entry_id_found(self):
        """Returns coordinator when entry_id matches a known entry."""
        entry = _make_mock_entry("entry_a")
        coordinator = _make_mock_coordinator(entry)
        domain_data = {"entry_a": coordinator}

        result = _get_coordinator(domain_data, "entry_a")
        assert result is coordinator

    def test_entry_id_not_found(self):
        """Raises ServiceValidationError when entry_id doesn't match any entry."""

        entry = _make_mock_entry("entry_a")
        coordinator = _make_mock_coordinator(entry)
        domain_data = {"entry_a": coordinator}

        with pytest.raises(ServiceValidationError, match="Unknown entry_id"):
            _get_coordinator(domain_data, "nonexistent")

    def test_single_entry_no_entry_id(self):
        """Returns the only coordinator when no entry_id given and one entry exists."""
        entry = _make_mock_entry("entry_a")
        coordinator = _make_mock_coordinator(entry)
        domain_data = {"entry_a": coordinator}

        result = _get_coordinator(domain_data, None)
        assert result is coordinator

    def test_multiple_entries_no_entry_id(self):
        """Raises ServiceValidationError when multiple entries exist and no entry_id given."""

        entry_a = _make_mock_entry("entry_a")
        entry_b = _make_mock_entry("entry_b")
        domain_data = {
            "entry_a": _make_mock_coordinator(entry_a),
            "entry_b": _make_mock_coordinator(entry_b),
        }

        with pytest.raises(ServiceValidationError, match="Multiple ACWD entries"):
            _get_coordinator(domain_data, None)


# ---------------------------------------------------------------------------
# handle_import_hourly: error paths
# ---------------------------------------------------------------------------


class TestHandleImportHourlyErrors:
    """Tests for handle_import_hourly error paths beyond validation."""

    async def test_login_failure_raises_error(self):
        """Login returning False raises HomeAssistantError."""

        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)
        hass.data[DOMAIN] = {entry.entry_id: coordinator}

        past_date = datetime.date.today() - datetime.timedelta(days=2)
        call = MagicMock()
        call.hass = hass
        call.data = {"date": past_date, "granularity": "hourly"}

        with patch("custom_components.acwd.ACWDClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.login.return_value = False
            mock_client.logout.return_value = None
            mock_client_cls.return_value = mock_client

            with pytest.raises(HomeAssistantError, match="Failed to login"):
                await handle_import_hourly(call)

    async def test_no_data_returned_raises_error(self):
        """API returning None raises HomeAssistantError."""

        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)
        hass.data[DOMAIN] = {entry.entry_id: coordinator}

        past_date = datetime.date.today() - datetime.timedelta(days=2)
        call = MagicMock()
        call.hass = hass
        call.data = {"date": past_date, "granularity": "hourly"}

        with patch("custom_components.acwd.ACWDClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.login.return_value = True
            mock_client.get_usage_data.return_value = None
            mock_client.logout.return_value = None
            mock_client_cls.return_value = mock_client

            with pytest.raises(HomeAssistantError, match="No data returned"):
                await handle_import_hourly(call)

    async def test_no_meter_number_raises_error(self):
        """Missing meter number raises HomeAssistantError."""

        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)
        hass.data[DOMAIN] = {entry.entry_id: coordinator}

        past_date = datetime.date.today() - datetime.timedelta(days=2)
        call = MagicMock()
        call.hass = hass
        call.data = {"date": past_date, "granularity": "hourly"}

        with patch("custom_components.acwd.ACWDClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.login.return_value = True
            mock_client.get_usage_data.return_value = {
                "objUsageGenerationResultSetTwo": [{"Hourly": "12:00 AM", "UsageValue": 1.0}]
            }
            mock_client.meter_number = None
            mock_client.logout.return_value = None
            mock_client_cls.return_value = mock_client

            with pytest.raises(HomeAssistantError, match="Meter number not available"):
                await handle_import_hourly(call)

    async def test_no_hourly_records_raises_error(self):
        """Empty hourly records list raises HomeAssistantError."""

        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)
        hass.data[DOMAIN] = {entry.entry_id: coordinator}

        past_date = datetime.date.today() - datetime.timedelta(days=2)
        call = MagicMock()
        call.hass = hass
        call.data = {"date": past_date, "granularity": "hourly"}

        with patch("custom_components.acwd.ACWDClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.login.return_value = True
            mock_client.get_usage_data.return_value = {"objUsageGenerationResultSetTwo": []}
            mock_client.meter_number = "230057301"
            mock_client.logout.return_value = None
            mock_client_cls.return_value = mock_client

            with pytest.raises(HomeAssistantError, match="No hourly data available"):
                await handle_import_hourly(call)


# ---------------------------------------------------------------------------
# handle_import_daily: error paths
# ---------------------------------------------------------------------------


class TestHandleImportDailyErrors:
    """Tests for handle_import_daily error paths beyond validation."""

    async def test_login_failure_raises_error(self):
        """Login returning False raises HomeAssistantError."""

        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)
        hass.data[DOMAIN] = {entry.entry_id: coordinator}

        call = MagicMock()
        call.hass = hass
        call.data = {
            "start_date": datetime.date(2025, 12, 1),
            "end_date": datetime.date(2025, 12, 5),
        }

        with patch("custom_components.acwd.ACWDClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.login.return_value = False
            mock_client.logout.return_value = None
            mock_client_cls.return_value = mock_client

            with pytest.raises(HomeAssistantError, match="Failed to login"):
                await handle_import_daily(call)

    async def test_no_data_returned_raises_error(self):
        """API returning None raises HomeAssistantError."""

        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)
        hass.data[DOMAIN] = {entry.entry_id: coordinator}

        call = MagicMock()
        call.hass = hass
        call.data = {
            "start_date": datetime.date(2025, 12, 1),
            "end_date": datetime.date(2025, 12, 5),
        }

        with patch("custom_components.acwd.ACWDClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.login.return_value = True
            mock_client.meter_number = "12345"
            mock_client.get_usage_data.return_value = None
            mock_client.logout.return_value = None
            mock_client_cls.return_value = mock_client

            with pytest.raises(HomeAssistantError, match="No data returned"):
                await handle_import_daily(call)

    async def test_no_meter_number_raises_error(self):
        """Missing meter number raises HomeAssistantError."""

        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)
        hass.data[DOMAIN] = {entry.entry_id: coordinator}

        call = MagicMock()
        call.hass = hass
        call.data = {
            "start_date": datetime.date(2025, 12, 1),
            "end_date": datetime.date(2025, 12, 5),
        }

        with patch("custom_components.acwd.ACWDClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.login.return_value = True
            mock_client.get_usage_data.return_value = {"objUsageGenerationResultSetTwo": [{"Date": "12/01/2025"}]}
            mock_client.meter_number = None
            mock_client.logout.return_value = None
            mock_client_cls.return_value = mock_client

            with pytest.raises(HomeAssistantError, match="Meter number not available"):
                await handle_import_daily(call)

    async def test_no_daily_records_raises_error(self):
        """Empty daily records list raises HomeAssistantError."""

        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)
        hass.data[DOMAIN] = {entry.entry_id: coordinator}

        call = MagicMock()
        call.hass = hass
        call.data = {
            "start_date": datetime.date(2025, 12, 1),
            "end_date": datetime.date(2025, 12, 5),
        }

        with patch("custom_components.acwd.ACWDClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.login.return_value = True
            mock_client.meter_number = "12345"
            mock_client.get_usage_data.return_value = {"objUsageGenerationResultSetTwo": []}
            mock_client.logout.return_value = None
            mock_client_cls.return_value = mock_client

            with pytest.raises(HomeAssistantError, match="No daily data available"):
                await handle_import_daily(call)


# ---------------------------------------------------------------------------
# handle_import_hourly: additional edge cases (quarter_hourly, network, logout)
# ---------------------------------------------------------------------------


class TestHandleImportHourlyEdgeCases:
    """Tests for handle_import_hourly edge cases not covered above."""

    async def test_quarter_hourly_granularity_calls_quarter_hourly_import(self):
        """Quarter-hourly granularity calls async_import_quarter_hourly_statistics."""
        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)
        hass.data[DOMAIN] = {entry.entry_id: coordinator}

        past_date = datetime.date.today() - datetime.timedelta(days=2)
        call = MagicMock()
        call.hass = hass
        call.data = {"date": past_date, "granularity": "quarter_hourly"}

        with (
            patch("custom_components.acwd.ACWDClient") as mock_client_cls,
            patch(
                "custom_components.acwd.async_import_quarter_hourly_statistics",
                new_callable=AsyncMock,
            ) as mock_qh_import,
            patch(
                "custom_components.acwd.async_import_hourly_statistics",
                new_callable=AsyncMock,
            ) as mock_h_import,
        ):
            mock_client = MagicMock()
            mock_client.login.return_value = True
            mock_client.get_usage_data.return_value = {
                "objUsageGenerationResultSetTwo": [
                    {"Hourly": "12:00 AM", "UsageValue": 1.0},
                ]
            }
            mock_client.meter_number = "230057301"
            mock_client.logout.return_value = None
            mock_client_cls.return_value = mock_client

            await handle_import_hourly(call)

            mock_qh_import.assert_called_once()
            mock_h_import.assert_not_called()

    async def test_requests_timeout_raises_home_assistant_error(self):
        """requests.Timeout during import raises HomeAssistantError with network message."""
        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)
        hass.data[DOMAIN] = {entry.entry_id: coordinator}

        past_date = datetime.date.today() - datetime.timedelta(days=2)
        call = MagicMock()
        call.hass = hass
        call.data = {"date": past_date, "granularity": "hourly"}

        with patch("custom_components.acwd.ACWDClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.login.side_effect = requests.Timeout("timed out")
            mock_client.logout.return_value = None
            mock_client_cls.return_value = mock_client

            with pytest.raises(HomeAssistantError, match="Network error"):
                await handle_import_hourly(call)

    async def test_requests_connection_error_raises_home_assistant_error(self):
        """requests.ConnectionError during import raises HomeAssistantError."""
        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)
        hass.data[DOMAIN] = {entry.entry_id: coordinator}

        past_date = datetime.date.today() - datetime.timedelta(days=2)
        call = MagicMock()
        call.hass = hass
        call.data = {"date": past_date, "granularity": "hourly"}

        with patch("custom_components.acwd.ACWDClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.login.side_effect = requests.ConnectionError("refused")
            mock_client.logout.return_value = None
            mock_client_cls.return_value = mock_client

            with pytest.raises(HomeAssistantError, match="Network error"):
                await handle_import_hourly(call)

    async def test_generic_exception_wraps_in_home_assistant_error(self):
        """A generic exception during import wraps in HomeAssistantError."""
        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)
        hass.data[DOMAIN] = {entry.entry_id: coordinator}

        past_date = datetime.date.today() - datetime.timedelta(days=2)
        call = MagicMock()
        call.hass = hass
        call.data = {"date": past_date, "granularity": "hourly"}

        with patch("custom_components.acwd.ACWDClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.login.return_value = True
            mock_client.get_usage_data.side_effect = RuntimeError("unexpected")
            mock_client.logout.return_value = None
            mock_client_cls.return_value = mock_client

            with pytest.raises(HomeAssistantError, match="Error importing hourly data"):
                await handle_import_hourly(call)

    async def test_logout_failure_silently_caught(self):
        """Logout failure after hourly import does not propagate."""
        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)
        hass.data[DOMAIN] = {entry.entry_id: coordinator}

        past_date = datetime.date.today() - datetime.timedelta(days=2)
        call = MagicMock()
        call.hass = hass
        call.data = {"date": past_date, "granularity": "hourly"}

        with (
            patch("custom_components.acwd.ACWDClient") as mock_client_cls,
            patch(
                "custom_components.acwd.async_import_hourly_statistics",
                new_callable=AsyncMock,
            ),
        ):
            mock_client = MagicMock()
            mock_client.login.return_value = True
            mock_client.get_usage_data.return_value = {
                "objUsageGenerationResultSetTwo": [
                    {"Hourly": "12:00 AM", "UsageValue": 1.0},
                ]
            }
            mock_client.meter_number = "230057301"
            mock_client.logout.side_effect = RuntimeError("logout failed")
            mock_client_cls.return_value = mock_client

            # Should not raise despite logout failure
            await handle_import_hourly(call)

            mock_client.logout.assert_called_once()


# ---------------------------------------------------------------------------
# handle_import_daily: additional edge cases (network, logout)
# ---------------------------------------------------------------------------


class TestHandleImportDailyEdgeCases:
    """Tests for handle_import_daily edge cases not covered above."""

    async def test_requests_timeout_raises_home_assistant_error(self):
        """requests.Timeout during daily import raises HomeAssistantError."""
        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)
        hass.data[DOMAIN] = {entry.entry_id: coordinator}

        call = MagicMock()
        call.hass = hass
        call.data = {
            "start_date": datetime.date(2025, 12, 1),
            "end_date": datetime.date(2025, 12, 5),
        }

        with patch("custom_components.acwd.ACWDClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.login.side_effect = requests.Timeout("timed out")
            mock_client.logout.return_value = None
            mock_client_cls.return_value = mock_client

            with pytest.raises(HomeAssistantError, match="Network error"):
                await handle_import_daily(call)

    async def test_requests_connection_error_raises_home_assistant_error(self):
        """requests.ConnectionError during daily import raises HomeAssistantError."""
        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)
        hass.data[DOMAIN] = {entry.entry_id: coordinator}

        call = MagicMock()
        call.hass = hass
        call.data = {
            "start_date": datetime.date(2025, 12, 1),
            "end_date": datetime.date(2025, 12, 5),
        }

        with patch("custom_components.acwd.ACWDClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.login.side_effect = requests.ConnectionError("refused")
            mock_client.logout.return_value = None
            mock_client_cls.return_value = mock_client

            with pytest.raises(HomeAssistantError, match="Network error"):
                await handle_import_daily(call)

    async def test_generic_exception_wraps_in_home_assistant_error(self):
        """A generic exception during daily import wraps in HomeAssistantError."""
        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)
        hass.data[DOMAIN] = {entry.entry_id: coordinator}

        call = MagicMock()
        call.hass = hass
        call.data = {
            "start_date": datetime.date(2025, 12, 1),
            "end_date": datetime.date(2025, 12, 5),
        }

        with patch("custom_components.acwd.ACWDClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.login.return_value = True
            mock_client.meter_number = "12345"
            mock_client.get_usage_data.side_effect = RuntimeError("unexpected")
            mock_client.logout.return_value = None
            mock_client_cls.return_value = mock_client

            with pytest.raises(HomeAssistantError, match="Error importing daily data"):
                await handle_import_daily(call)

    async def test_logout_failure_silently_caught(self):
        """Logout failure after daily import does not propagate."""
        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)
        hass.data[DOMAIN] = {entry.entry_id: coordinator}

        call = MagicMock()
        call.hass = hass
        call.data = {
            "start_date": datetime.date(2025, 12, 1),
            "end_date": datetime.date(2025, 12, 5),
        }

        with (
            patch("custom_components.acwd.ACWDClient") as mock_client_cls,
            patch(
                "custom_components.acwd.async_import_daily_statistics",
                new_callable=AsyncMock,
            ),
        ):
            mock_client = MagicMock()
            mock_client.login.return_value = True
            mock_client.meter_number = "230057301"
            mock_client.get_usage_data.return_value = {
                "objUsageGenerationResultSetTwo": [
                    {"Date": "12/01/2025", "UsageValue": 50.0},
                ]
            }
            mock_client.logout.side_effect = RuntimeError("logout failed")
            mock_client_cls.return_value = mock_client

            # Should not raise despite logout failure
            await handle_import_daily(call)

            mock_client.logout.assert_called_once()


# ---------------------------------------------------------------------------
# _async_import_initial_yesterday_data
# ---------------------------------------------------------------------------


class TestAsyncImportInitialYesterdayData:
    """Tests for _async_import_initial_yesterday_data."""

    async def test_happy_path_imports_statistics(self):
        """Happy path: login, data returned, hourly records exist, imports statistics."""
        from custom_components.acwd import _async_import_initial_yesterday_data

        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)

        mock_client = MagicMock()
        mock_client.login.return_value = True
        mock_client.get_usage_data.return_value = {
            "objUsageGenerationResultSetTwo": [
                {"Hourly": "12:00 AM", "UsageValue": 2.0},
            ]
        }
        mock_client.meter_number = "230057301"
        mock_client.logout.return_value = None

        with (
            patch(
                "custom_components.acwd.acwd_api.ACWDClient",
                return_value=mock_client,
            ),
            patch(
                "custom_components.acwd.async_import_hourly_statistics",
                new_callable=AsyncMock,
            ) as mock_import,
            patch("custom_components.acwd.dt_util") as mock_dt_util,
            patch("custom_components.acwd.local_midnight") as mock_midnight,
        ):
            mock_dt_util.now.return_value = datetime.datetime(2025, 12, 10, 14, 0, 0)
            mock_midnight.return_value = datetime.datetime(2025, 12, 9, 0, 0, 0)

            await _async_import_initial_yesterday_data(hass, coordinator)

            mock_import.assert_called_once()
            assert mock_import.call_args[0][1] == "230057301"

    async def test_login_failure_returns_without_raising(self):
        """Login failure returns gracefully without raising."""
        from custom_components.acwd import _async_import_initial_yesterday_data

        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)

        mock_client = MagicMock()
        mock_client.login.return_value = False

        with (
            patch(
                "custom_components.acwd.acwd_api.ACWDClient",
                return_value=mock_client,
            ),
            patch(
                "custom_components.acwd.async_import_hourly_statistics",
                new_callable=AsyncMock,
            ) as mock_import,
            patch("custom_components.acwd.dt_util") as mock_dt_util,
        ):
            mock_dt_util.now.return_value = datetime.datetime(2025, 12, 10, 14, 0, 0)

            await _async_import_initial_yesterday_data(hass, coordinator)

            mock_import.assert_not_called()

    async def test_no_data_returns_gracefully(self):
        """No data returned from API returns gracefully."""
        from custom_components.acwd import _async_import_initial_yesterday_data

        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)

        mock_client = MagicMock()
        mock_client.login.return_value = True
        mock_client.get_usage_data.return_value = None
        mock_client.logout.return_value = None

        with (
            patch(
                "custom_components.acwd.acwd_api.ACWDClient",
                return_value=mock_client,
            ),
            patch(
                "custom_components.acwd.async_import_hourly_statistics",
                new_callable=AsyncMock,
            ) as mock_import,
            patch("custom_components.acwd.dt_util") as mock_dt_util,
        ):
            mock_dt_util.now.return_value = datetime.datetime(2025, 12, 10, 14, 0, 0)

            await _async_import_initial_yesterday_data(hass, coordinator)

            mock_import.assert_not_called()

    async def test_no_meter_number_returns_gracefully(self):
        """No meter number available returns gracefully."""
        from custom_components.acwd import _async_import_initial_yesterday_data

        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)

        mock_client = MagicMock()
        mock_client.login.return_value = True
        mock_client.get_usage_data.return_value = {
            "objUsageGenerationResultSetTwo": [
                {"Hourly": "12:00 AM", "UsageValue": 2.0},
            ]
        }
        mock_client.meter_number = None
        mock_client.logout.return_value = None

        with (
            patch(
                "custom_components.acwd.acwd_api.ACWDClient",
                return_value=mock_client,
            ),
            patch(
                "custom_components.acwd.async_import_hourly_statistics",
                new_callable=AsyncMock,
            ) as mock_import,
            patch("custom_components.acwd.dt_util") as mock_dt_util,
        ):
            mock_dt_util.now.return_value = datetime.datetime(2025, 12, 10, 14, 0, 0)

            await _async_import_initial_yesterday_data(hass, coordinator)

            mock_import.assert_not_called()

    async def test_no_hourly_records_returns_gracefully(self):
        """Empty hourly records list returns gracefully."""
        from custom_components.acwd import _async_import_initial_yesterday_data

        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)

        mock_client = MagicMock()
        mock_client.login.return_value = True
        mock_client.get_usage_data.return_value = {"objUsageGenerationResultSetTwo": []}
        mock_client.meter_number = "230057301"
        mock_client.logout.return_value = None

        with (
            patch(
                "custom_components.acwd.acwd_api.ACWDClient",
                return_value=mock_client,
            ),
            patch(
                "custom_components.acwd.async_import_hourly_statistics",
                new_callable=AsyncMock,
            ) as mock_import,
            patch("custom_components.acwd.dt_util") as mock_dt_util,
        ):
            mock_dt_util.now.return_value = datetime.datetime(2025, 12, 10, 14, 0, 0)

            await _async_import_initial_yesterday_data(hass, coordinator)

            mock_import.assert_not_called()

    async def test_exception_caught_and_logged(self):
        """Exception during initial import is caught (non-critical)."""
        from custom_components.acwd import _async_import_initial_yesterday_data

        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)

        mock_client = MagicMock()
        mock_client.login.side_effect = RuntimeError("boom")

        with (
            patch(
                "custom_components.acwd.acwd_api.ACWDClient",
                return_value=mock_client,
            ),
            patch("custom_components.acwd.dt_util") as mock_dt_util,
        ):
            mock_dt_util.now.return_value = datetime.datetime(2025, 12, 10, 14, 0, 0)

            # Should not raise
            await _async_import_initial_yesterday_data(hass, coordinator)

    async def test_logout_called_on_exception(self):
        """Logout is called via finally even when login raises RuntimeError."""
        from custom_components.acwd import _async_import_initial_yesterday_data

        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)

        mock_client = MagicMock()
        mock_client.login.side_effect = RuntimeError("boom")
        mock_client.logout.return_value = None

        with (
            patch(
                "custom_components.acwd.acwd_api.ACWDClient",
                return_value=mock_client,
            ),
            patch("custom_components.acwd.dt_util") as mock_dt_util,
        ):
            mock_dt_util.now.return_value = datetime.datetime(2025, 12, 10, 14, 0, 0)

            await _async_import_initial_yesterday_data(hass, coordinator)

            mock_client.logout.assert_called_once()

    async def test_logout_called_on_happy_path(self):
        """Logout is called via finally on the happy path."""
        from custom_components.acwd import _async_import_initial_yesterday_data

        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)

        mock_client = MagicMock()
        mock_client.login.return_value = True
        mock_client.get_usage_data.return_value = {
            "objUsageGenerationResultSetTwo": [
                {"Hourly": "12:00 AM", "UsageValue": 2.0},
            ]
        }
        mock_client.meter_number = "230057301"
        mock_client.logout.return_value = None

        with (
            patch(
                "custom_components.acwd.acwd_api.ACWDClient",
                return_value=mock_client,
            ),
            patch(
                "custom_components.acwd.async_import_hourly_statistics",
                new_callable=AsyncMock,
            ),
            patch("custom_components.acwd.dt_util") as mock_dt_util,
            patch("custom_components.acwd.local_midnight") as mock_midnight,
        ):
            mock_dt_util.now.return_value = datetime.datetime(2025, 12, 10, 14, 0, 0)
            mock_midnight.return_value = datetime.datetime(2025, 12, 9, 0, 0, 0)

            await _async_import_initial_yesterday_data(hass, coordinator)

            assert mock_client.logout.call_count == 1

    async def test_logout_called_when_get_usage_data_fails(self):
        """Logout is called via finally when get_usage_data raises RuntimeError."""
        from custom_components.acwd import _async_import_initial_yesterday_data

        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)

        mock_client = MagicMock()
        mock_client.login.return_value = True
        mock_client.get_usage_data.side_effect = RuntimeError("api error")
        mock_client.logout.return_value = None

        with (
            patch(
                "custom_components.acwd.acwd_api.ACWDClient",
                return_value=mock_client,
            ),
            patch("custom_components.acwd.dt_util") as mock_dt_util,
        ):
            mock_dt_util.now.return_value = datetime.datetime(2025, 12, 10, 14, 0, 0)

            await _async_import_initial_yesterday_data(hass, coordinator)

            mock_client.logout.assert_called_once()

    async def test_transient_timeout_logs_network_warning(self):
        """requests.Timeout logs warning with 'Network error' and 'retried on the next update cycle'."""
        from custom_components.acwd import _async_import_initial_yesterday_data

        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)

        mock_client = MagicMock()
        mock_client.login.side_effect = requests.Timeout("timed out")
        mock_client.logout.return_value = None

        with (
            patch(
                "custom_components.acwd.acwd_api.ACWDClient",
                return_value=mock_client,
            ),
            patch("custom_components.acwd.dt_util") as mock_dt_util,
            patch("custom_components.acwd._LOGGER") as mock_logger,
        ):
            mock_dt_util.now.return_value = datetime.datetime(2025, 12, 10, 14, 0, 0)

            await _async_import_initial_yesterday_data(hass, coordinator)

            warning_calls = mock_logger.warning.call_args_list
            assert any(
                "Network error" in str(call) and "retried on the next update cycle" in str(call) for call in warning_calls
            ), f"Expected network warning not found. Calls: {warning_calls}"
            mock_client.logout.assert_called_once()

    async def test_transient_connection_error_logs_network_warning(self):
        """requests.ConnectionError logs warning with 'Network error' and 'retried on the next update cycle'."""
        from custom_components.acwd import _async_import_initial_yesterday_data

        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)

        mock_client = MagicMock()
        mock_client.login.side_effect = requests.ConnectionError("refused")
        mock_client.logout.return_value = None

        with (
            patch(
                "custom_components.acwd.acwd_api.ACWDClient",
                return_value=mock_client,
            ),
            patch("custom_components.acwd.dt_util") as mock_dt_util,
            patch("custom_components.acwd._LOGGER") as mock_logger,
        ):
            mock_dt_util.now.return_value = datetime.datetime(2025, 12, 10, 14, 0, 0)

            await _async_import_initial_yesterday_data(hass, coordinator)

            warning_calls = mock_logger.warning.call_args_list
            assert any(
                "Network error" in str(call) and "retried on the next update cycle" in str(call) for call in warning_calls
            ), f"Expected network warning not found. Calls: {warning_calls}"
            mock_client.logout.assert_called_once()

    async def test_logout_failure_in_finally_is_silenced(self):
        """Logout failure in finally block is logged at debug level and does not propagate."""
        from custom_components.acwd import _async_import_initial_yesterday_data

        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)

        mock_client = MagicMock()
        mock_client.login.side_effect = RuntimeError("boom")
        mock_client.logout.side_effect = RuntimeError("logout failed")

        with (
            patch(
                "custom_components.acwd.acwd_api.ACWDClient",
                return_value=mock_client,
            ),
            patch("custom_components.acwd.dt_util") as mock_dt_util,
        ):
            mock_dt_util.now.return_value = datetime.datetime(2025, 12, 10, 14, 0, 0)

            # Must not raise despite both login and logout failing
            await _async_import_initial_yesterday_data(hass, coordinator)

            mock_client.logout.assert_called_once()


# ---------------------------------------------------------------------------
# ACWDDataUpdateCoordinator._async_update_data
# ---------------------------------------------------------------------------


class TestCoordinatorAsyncUpdateData:
    """Tests for ACWDDataUpdateCoordinator._async_update_data."""

    def _make_coordinator(self):
        """Create a coordinator stub using SimpleNamespace pattern (decision [03-01])."""
        import types

        from custom_components.acwd import ACWDDataUpdateCoordinator

        hass = _make_mock_hass()
        entry = _make_mock_entry()
        client = MagicMock()
        coord = types.SimpleNamespace(
            hass=hass,
            client=client,
            entry=entry,
            _last_hourly_import_date=None,
        )
        # Bind the real methods to our stub
        coord._async_update_data = ACWDDataUpdateCoordinator._async_update_data.__get__(coord)
        coord._import_today_hourly_data = ACWDDataUpdateCoordinator._import_today_hourly_data.__get__(coord)
        coord._import_yesterday_complete_data = ACWDDataUpdateCoordinator._import_yesterday_complete_data.__get__(coord)
        return coord

    async def test_happy_path_returns_data(self):
        """Happy path: login succeeds, billing data returned, sub-imports called."""
        coord = self._make_coordinator()
        coord.client.login.return_value = True
        coord.client.get_usage_data.return_value = {"summary": "data"}
        coord.client.logout.return_value = None

        # Replace bound methods with AsyncMock on SimpleNamespace
        mock_today = AsyncMock()
        mock_yesterday = AsyncMock()
        coord._import_today_hourly_data = mock_today
        coord._import_yesterday_complete_data = mock_yesterday

        result = await coord._async_update_data()

        assert result == {"summary": "data"}
        mock_today.assert_called_once()
        mock_yesterday.assert_called_once()

    async def test_login_failure_raises_update_failed(self):
        """Login returning False raises UpdateFailed."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        coord = self._make_coordinator()
        coord.client.login.return_value = False

        with pytest.raises(UpdateFailed, match="Failed to login"):
            await coord._async_update_data()

    async def test_no_data_raises_update_failed(self):
        """No data returned raises UpdateFailed."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        coord = self._make_coordinator()
        coord.client.login.return_value = True
        coord.client.get_usage_data.return_value = None

        with pytest.raises(UpdateFailed, match="No data returned"):
            await coord._async_update_data()

    async def test_requests_timeout_raises_update_failed(self):
        """requests.Timeout raises UpdateFailed with network error message and retry_after=300."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        coord = self._make_coordinator()
        coord.client.login.side_effect = requests.Timeout("timed out")

        with pytest.raises(UpdateFailed, match="Network error") as exc_info:
            await coord._async_update_data()

        assert exc_info.value.retry_after == 300

    async def test_requests_connection_error_raises_update_failed(self):
        """requests.ConnectionError raises UpdateFailed with network error message and retry_after=300."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        coord = self._make_coordinator()
        coord.client.login.side_effect = requests.ConnectionError("refused")

        with pytest.raises(UpdateFailed, match="Network error") as exc_info:
            await coord._async_update_data()

        assert exc_info.value.retry_after == 300

    async def test_generic_exception_raises_update_failed(self):
        """A generic exception raises UpdateFailed."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        coord = self._make_coordinator()
        coord.client.login.side_effect = RuntimeError("unexpected")

        with pytest.raises(UpdateFailed, match="Error communicating with ACWD"):
            await coord._async_update_data()

    async def test_logout_called_on_happy_path(self):
        """Logout is called via finally on the happy path."""
        coord = self._make_coordinator()
        coord.client.login.return_value = True
        coord.client.get_usage_data.return_value = {"summary": "data"}
        coord.client.logout.return_value = None

        coord._import_today_hourly_data = AsyncMock()
        coord._import_yesterday_complete_data = AsyncMock()

        await coord._async_update_data()

        assert coord.client.logout.call_count == 1

    async def test_logout_called_on_login_exception(self):
        """Logout is called via finally even when login raises RuntimeError."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        coord = self._make_coordinator()
        coord.client.login.side_effect = RuntimeError("boom")
        coord.client.logout.return_value = None

        with pytest.raises(UpdateFailed):
            await coord._async_update_data()

        coord.client.logout.assert_called_once()

    async def test_logout_called_on_sub_import_exception(self):
        """Logout is called via finally when a sub-import raises."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        coord = self._make_coordinator()
        coord.client.login.return_value = True
        coord.client.get_usage_data.return_value = {"summary": "data"}
        coord.client.logout.return_value = None

        coord._import_today_hourly_data = AsyncMock(side_effect=RuntimeError("sub error"))
        coord._import_yesterday_complete_data = AsyncMock()

        with pytest.raises(UpdateFailed):
            await coord._async_update_data()

        coord.client.logout.assert_called_once()

    async def test_generic_exception_has_no_retry_after(self):
        """A generic exception raises UpdateFailed without retry_after."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        coord = self._make_coordinator()
        coord.client.login.side_effect = RuntimeError("unexpected")

        with pytest.raises(UpdateFailed) as exc_info:
            await coord._async_update_data()

        assert exc_info.value.retry_after is None

    async def test_login_failure_update_failed_has_no_retry_after(self):
        """Login returning False raises UpdateFailed without retry_after."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        coord = self._make_coordinator()
        coord.client.login.return_value = False

        with pytest.raises(UpdateFailed) as exc_info:
            await coord._async_update_data()

        assert exc_info.value.retry_after is None

    async def test_logout_failure_in_finally_is_silenced(self):
        """Coordinator logout failure in finally block does not propagate."""
        coord = self._make_coordinator()
        coord.client.login.return_value = True
        coord.client.get_usage_data.return_value = {"summary": "data"}
        coord.client.logout.side_effect = RuntimeError("logout failed")

        coord._import_today_hourly_data = AsyncMock()
        coord._import_yesterday_complete_data = AsyncMock()

        # Should not raise despite logout failure
        result = await coord._async_update_data()
        assert result == {"summary": "data"}
        coord.client.logout.assert_called_once()


# ---------------------------------------------------------------------------
# ACWDDataUpdateCoordinator._import_today_hourly_data
# ---------------------------------------------------------------------------


class TestCoordinatorImportTodayHourlyData:
    """Tests for ACWDDataUpdateCoordinator._import_today_hourly_data."""

    def _make_coordinator(self):
        """Create a coordinator stub using SimpleNamespace pattern (decision [03-01])."""
        import types

        from custom_components.acwd import ACWDDataUpdateCoordinator

        hass = _make_mock_hass()
        entry = _make_mock_entry()
        client = MagicMock()
        coord = types.SimpleNamespace(
            hass=hass,
            client=client,
            entry=entry,
            _last_hourly_import_date=None,
        )
        coord._import_today_hourly_data = ACWDDataUpdateCoordinator._import_today_hourly_data.__get__(coord)
        return coord

    async def test_happy_path_imports_data(self):
        """Happy path: data with non-zero usage records triggers import."""
        coord = self._make_coordinator()
        coord.client.get_usage_data.return_value = {
            "objUsageGenerationResultSetTwo": [
                {"Hourly": "12:00 AM", "UsageValue": 2.0},
                {"Hourly": "1:00 AM", "UsageValue": 3.5},
            ]
        }
        coord.client.meter_number = "230057301"

        with (
            patch("custom_components.acwd.dt_util") as mock_dt_util,
            patch("custom_components.acwd.local_midnight") as mock_midnight,
            patch(
                "custom_components.acwd.async_import_hourly_statistics",
                new_callable=AsyncMock,
            ) as mock_import,
        ):
            mock_dt_util.now.return_value = datetime.datetime(2025, 12, 10, 14, 0, 0)
            mock_midnight.return_value = datetime.datetime(2025, 12, 10, 0, 0, 0)

            await coord._import_today_hourly_data()

            mock_import.assert_called_once()

    async def test_no_data_returns_gracefully(self):
        """No data returned from API returns without importing."""
        coord = self._make_coordinator()
        coord.client.get_usage_data.return_value = None

        with (
            patch("custom_components.acwd.dt_util") as mock_dt_util,
            patch(
                "custom_components.acwd.async_import_hourly_statistics",
                new_callable=AsyncMock,
            ) as mock_import,
        ):
            mock_dt_util.now.return_value = datetime.datetime(2025, 12, 10, 14, 0, 0)

            await coord._import_today_hourly_data()

            mock_import.assert_not_called()

    async def test_no_meter_number_returns_gracefully(self):
        """No meter number returns without importing."""
        coord = self._make_coordinator()
        coord.client.get_usage_data.return_value = {
            "objUsageGenerationResultSetTwo": [
                {"Hourly": "12:00 AM", "UsageValue": 2.0},
            ]
        }
        coord.client.meter_number = None

        with (
            patch("custom_components.acwd.dt_util") as mock_dt_util,
            patch(
                "custom_components.acwd.async_import_hourly_statistics",
                new_callable=AsyncMock,
            ) as mock_import,
        ):
            mock_dt_util.now.return_value = datetime.datetime(2025, 12, 10, 14, 0, 0)

            await coord._import_today_hourly_data()

            mock_import.assert_not_called()

    async def test_no_hourly_records_returns_gracefully(self):
        """Empty hourly records returns without importing."""
        coord = self._make_coordinator()
        coord.client.get_usage_data.return_value = {"objUsageGenerationResultSetTwo": []}
        coord.client.meter_number = "230057301"

        with (
            patch("custom_components.acwd.dt_util") as mock_dt_util,
            patch(
                "custom_components.acwd.async_import_hourly_statistics",
                new_callable=AsyncMock,
            ) as mock_import,
        ):
            mock_dt_util.now.return_value = datetime.datetime(2025, 12, 10, 14, 0, 0)

            await coord._import_today_hourly_data()

            mock_import.assert_not_called()

    async def test_all_zero_usage_still_imports(self):
        """All-zero usage records still imports (logs 'No non-zero usage found')."""
        coord = self._make_coordinator()
        coord.client.get_usage_data.return_value = {
            "objUsageGenerationResultSetTwo": [
                {"Hourly": "12:00 AM", "UsageValue": 0},
                {"Hourly": "1:00 AM", "UsageValue": 0},
            ]
        }
        coord.client.meter_number = "230057301"

        with (
            patch("custom_components.acwd.dt_util") as mock_dt_util,
            patch("custom_components.acwd.local_midnight") as mock_midnight,
            patch(
                "custom_components.acwd.async_import_hourly_statistics",
                new_callable=AsyncMock,
            ) as mock_import,
        ):
            mock_dt_util.now.return_value = datetime.datetime(2025, 12, 10, 14, 0, 0)
            mock_midnight.return_value = datetime.datetime(2025, 12, 10, 0, 0, 0)

            await coord._import_today_hourly_data()

            mock_import.assert_called_once()

    async def test_exception_caught_as_warning(self):
        """Exception during import is caught and logged as warning."""
        coord = self._make_coordinator()
        coord.client.get_usage_data.side_effect = RuntimeError("boom")

        with patch("custom_components.acwd.dt_util") as mock_dt_util:
            mock_dt_util.now.return_value = datetime.datetime(2025, 12, 10, 14, 0, 0)

            # Should not raise
            await coord._import_today_hourly_data()


# ---------------------------------------------------------------------------
# ACWDDataUpdateCoordinator._import_yesterday_complete_data
# ---------------------------------------------------------------------------


class TestCoordinatorImportYesterdayCompleteData:
    """Tests for ACWDDataUpdateCoordinator._import_yesterday_complete_data."""

    def _make_coordinator(self):
        """Create a coordinator stub using SimpleNamespace pattern (decision [03-01])."""
        import types

        from custom_components.acwd import ACWDDataUpdateCoordinator

        hass = _make_mock_hass()
        entry = _make_mock_entry()
        client = MagicMock()
        coord = types.SimpleNamespace(
            hass=hass,
            client=client,
            entry=entry,
            _last_hourly_import_date=None,
        )
        coord._import_yesterday_complete_data = ACWDDataUpdateCoordinator._import_yesterday_complete_data.__get__(coord)
        return coord

    async def test_runs_during_morning_hours(self):
        """Runs import when current hour < MORNING_IMPORT_END_HOUR."""
        coord = self._make_coordinator()
        coord.client.get_usage_data.return_value = {
            "objUsageGenerationResultSetTwo": [
                {"Hourly": "12:00 AM", "UsageValue": 2.0},
            ]
        }
        coord.client.meter_number = "230057301"

        with (
            patch("custom_components.acwd.dt_util") as mock_dt_util,
            patch("custom_components.acwd.local_midnight") as mock_midnight,
            patch(
                "custom_components.acwd.async_import_hourly_statistics",
                new_callable=AsyncMock,
            ) as mock_import,
        ):
            # hour=6, before noon cutoff
            mock_now = datetime.datetime(2025, 12, 10, 6, 0, 0)
            mock_dt_util.now.return_value = mock_now
            mock_midnight.return_value = datetime.datetime(2025, 12, 9, 0, 0, 0)

            await coord._import_yesterday_complete_data()

            mock_import.assert_called_once()

    async def test_skips_after_morning_hours(self):
        """Skips import when current hour >= MORNING_IMPORT_END_HOUR."""
        coord = self._make_coordinator()

        with (
            patch("custom_components.acwd.dt_util") as mock_dt_util,
            patch(
                "custom_components.acwd.async_import_hourly_statistics",
                new_callable=AsyncMock,
            ) as mock_import,
        ):
            # hour=14, after noon cutoff
            mock_now = datetime.datetime(2025, 12, 10, 14, 0, 0)
            mock_dt_util.now.return_value = mock_now

            await coord._import_yesterday_complete_data()

            mock_import.assert_not_called()

    async def test_no_data_returns_gracefully(self):
        """No data returned from API returns gracefully."""
        coord = self._make_coordinator()
        coord.client.get_usage_data.return_value = None

        with (
            patch("custom_components.acwd.dt_util") as mock_dt_util,
            patch(
                "custom_components.acwd.async_import_hourly_statistics",
                new_callable=AsyncMock,
            ) as mock_import,
        ):
            mock_now = datetime.datetime(2025, 12, 10, 6, 0, 0)
            mock_dt_util.now.return_value = mock_now

            await coord._import_yesterday_complete_data()

            mock_import.assert_not_called()

    async def test_no_meter_number_returns_gracefully(self):
        """No meter number returns gracefully."""
        coord = self._make_coordinator()
        coord.client.get_usage_data.return_value = {
            "objUsageGenerationResultSetTwo": [
                {"Hourly": "12:00 AM", "UsageValue": 2.0},
            ]
        }
        coord.client.meter_number = None

        with (
            patch("custom_components.acwd.dt_util") as mock_dt_util,
            patch(
                "custom_components.acwd.async_import_hourly_statistics",
                new_callable=AsyncMock,
            ) as mock_import,
        ):
            mock_now = datetime.datetime(2025, 12, 10, 6, 0, 0)
            mock_dt_util.now.return_value = mock_now

            await coord._import_yesterday_complete_data()

            mock_import.assert_not_called()

    async def test_no_hourly_records_returns_gracefully(self):
        """Empty hourly records returns gracefully."""
        coord = self._make_coordinator()
        coord.client.get_usage_data.return_value = {"objUsageGenerationResultSetTwo": []}
        coord.client.meter_number = "230057301"

        with (
            patch("custom_components.acwd.dt_util") as mock_dt_util,
            patch(
                "custom_components.acwd.async_import_hourly_statistics",
                new_callable=AsyncMock,
            ) as mock_import,
        ):
            mock_now = datetime.datetime(2025, 12, 10, 6, 0, 0)
            mock_dt_util.now.return_value = mock_now

            await coord._import_yesterday_complete_data()

            mock_import.assert_not_called()

    async def test_exception_caught_as_warning(self):
        """Exception during yesterday import is caught and logged as warning."""
        coord = self._make_coordinator()
        coord.client.get_usage_data.side_effect = RuntimeError("boom")

        with patch("custom_components.acwd.dt_util") as mock_dt_util:
            mock_now = datetime.datetime(2025, 12, 10, 6, 0, 0)
            mock_dt_util.now.return_value = mock_now

            # Should not raise
            await coord._import_yesterday_complete_data()


# ---------------------------------------------------------------------------
# ACWDDataUpdateCoordinator.__init__
# ---------------------------------------------------------------------------


class TestACWDDataUpdateCoordinatorInit:
    """Tests for ACWDDataUpdateCoordinator constructor attribute assignments."""

    def test_constructor_sets_attributes(self):
        """Instantiating ACWDDataUpdateCoordinator sets client, entry, and _last_hourly_import_date."""
        from custom_components.acwd import ACWDDataUpdateCoordinator

        hass = _make_mock_hass()
        client = MagicMock()
        entry = MagicMock()

        with patch("homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"):
            coordinator = ACWDDataUpdateCoordinator(hass, client, entry)

        assert coordinator.client is client
        assert coordinator.entry is entry
        assert coordinator._last_hourly_import_date is None
