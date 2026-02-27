"""Tests for ACWD __init__.py service lifecycle.

Validates the domain-level service registration contract (SRVC-01, SRVC-02, QUAL-03)
implemented in Phase 2 Plan 02.
"""
import datetime
import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from tests.conftest import dt_util

from custom_components.acwd import (
    async_setup,
    async_setup_entry,
    async_unload_entry,
    handle_import_hourly,
    handle_import_daily,
    DOMAIN,
    SERVICE_IMPORT_HOURLY,
    SERVICE_IMPORT_DAILY,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_mock_hass():
    """Return a MagicMock hass suitable for service lifecycle tests."""
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


def _make_mock_entry(entry_id="test_entry_id"):
    """Return a MagicMock config entry."""
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.data = {"username": "test_user", "password": "test_pass"}
    return entry


def _make_mock_coordinator(entry):
    """Return a MagicMock coordinator."""
    coordinator = MagicMock()
    coordinator.entry = entry
    coordinator.client.user_info = {"AccountNumber": "12345"}
    coordinator.client.meter_number = "230057301"
    return coordinator


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
        from homeassistant.exceptions import ServiceValidationError

        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)
        hass.data[DOMAIN] = {entry.entry_id: coordinator}

        future_date = datetime.date.today()  # today counts as future per CONTEXT.md
        call = MagicMock()
        call.hass = hass
        call.data = {"date": future_date, "granularity": "hourly"}

        with pytest.raises(ServiceValidationError):
            await handle_import_hourly(call)

    async def test_valid_past_date_no_validation_error(self):
        """A past date does not raise ServiceValidationError."""
        from homeassistant.exceptions import ServiceValidationError

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
            patch("custom_components.acwd.async_import_hourly_statistics", new_callable=AsyncMock),
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
        from homeassistant.exceptions import HomeAssistantError

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
        from homeassistant.exceptions import ServiceValidationError

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
        from homeassistant.exceptions import ServiceValidationError

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
            patch("custom_components.acwd.async_import_daily_statistics", new_callable=AsyncMock),
        ):
            mock_client = MagicMock()
            mock_client.login.return_value = True
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
