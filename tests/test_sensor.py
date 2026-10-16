"""Tests for sensor.py - ACWD sensor entities."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.acwd.const import DOMAIN, HCF_TO_GALLONS
from custom_components.acwd.sensor import (
    ACWDAverageSensor,
    ACWDCurrentCycleSensor,
    ACWDCurrentUsageSensor,
    ACWDHighestSensor,
    ACWDLastBillingCycleSensor,
    ACWDSensorBase,
    _migrate_unknown_account_ids,
    async_setup_entry,
)

# -- Fixtures ----------------------------------------------------------------

SAMPLE_COORDINATOR_DATA = {
    "getTentativeData": [
        {
            "SoFar": 5000.50,
            "ExpectedUsage": 8000.75,
            "Average": 6500.25,
            "Highest": 12000.00,
            "UsageDate": "01/15/2026",
        }
    ],
    "objUsageGenerationResultSetTwo": [
        {
            "UsageValue": 7500.00,
            "FromDate": "11/01/2025",
            "ToDate": "12/31/2025",
            "UsageDate": "01/01/2026",
            "ServiceCharge": 45.50,
            "HighUsage": "No",
        }
    ],
}


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator with sample data."""
    coordinator = MagicMock()
    # Cleared on logout before the sensors are created, so sensors must not read it.
    coordinator.client.user_info = {}
    coordinator.data = SAMPLE_COORDINATOR_DATA
    return coordinator


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.unique_id = "12345"
    entry.title = "ACWD - Test User"
    return entry


# -- ACWDSensorBase -----------------------------------------------------------


@pytest.mark.unit
class TestACWDSensorBase:
    """Tests for the shared device info and entity naming on ACWDSensorBase."""

    def test_device_info(self, mock_coordinator, mock_config_entry):
        sensor = ACWDSensorBase(mock_coordinator, mock_config_entry)
        assert sensor._attr_has_entity_name is True
        assert sensor._attr_device_info == DeviceInfo(
            identifiers={(DOMAIN, "12345")},
            name="ACWD - Test User",
            manufacturer="Alameda County Water District",
            model="Water Meter",
            configuration_url="https://portal.acwd.org/portal/",
        )

    def test_device_info_defaults_when_entry_has_no_unique_id(self, mock_coordinator, mock_config_entry):
        mock_config_entry.unique_id = None
        sensor = ACWDSensorBase(mock_coordinator, mock_config_entry)
        assert sensor._attr_device_info == DeviceInfo(
            identifiers={(DOMAIN, "Unknown")},
            name="ACWD - Test User",
            manufacturer="Alameda County Water District",
            model="Water Meter",
            configuration_url="https://portal.acwd.org/portal/",
        )


# -- ACWDCurrentUsageSensor --------------------------------------------------


@pytest.mark.unit
class TestACWDCurrentUsageSensor:
    """Tests for the current usage sensor."""

    def test_native_value_with_data(self, mock_coordinator, mock_config_entry):
        sensor = ACWDCurrentUsageSensor(mock_coordinator, mock_config_entry)
        assert sensor.native_value == round(5000.50, 2)

    def test_native_value_no_data(self, mock_coordinator, mock_config_entry):
        mock_coordinator.data = None
        sensor = ACWDCurrentUsageSensor(mock_coordinator, mock_config_entry)
        assert sensor.native_value is None

    def test_native_value_empty_tentative(self, mock_coordinator, mock_config_entry):
        mock_coordinator.data = {"getTentativeData": []}
        sensor = ACWDCurrentUsageSensor(mock_coordinator, mock_config_entry)
        assert sensor.native_value is None

    def test_extra_state_attributes(self, mock_coordinator, mock_config_entry):
        sensor = ACWDCurrentUsageSensor(mock_coordinator, mock_config_entry)
        attrs = sensor.extra_state_attributes
        assert "usage_hcf" in attrs
        assert "usage_gallons" in attrs
        assert "expected_total_hcf" in attrs
        assert "expected_total_gallons" in attrs
        assert "cycle_date" in attrs
        assert attrs["usage_hcf"] == pytest.approx(round(5000.50 / HCF_TO_GALLONS, 2))
        assert attrs["usage_gallons"] == pytest.approx(round(5000.50, 2))
        assert attrs["cycle_date"] == "01/15/2026"

    def test_extra_state_attributes_no_data(self, mock_coordinator, mock_config_entry):
        mock_coordinator.data = None
        sensor = ACWDCurrentUsageSensor(mock_coordinator, mock_config_entry)
        assert sensor.extra_state_attributes == {}

    def test_extra_state_attributes_empty_tentative(self, mock_coordinator, mock_config_entry):
        mock_coordinator.data = {"getTentativeData": []}
        sensor = ACWDCurrentUsageSensor(mock_coordinator, mock_config_entry)
        assert sensor.extra_state_attributes == {}

    def test_unique_id(self, mock_coordinator, mock_config_entry):
        sensor = ACWDCurrentUsageSensor(mock_coordinator, mock_config_entry)
        assert sensor.unique_id == "12345_current_usage"

    def test_name_and_translation_key(self, mock_coordinator, mock_config_entry):
        sensor = ACWDCurrentUsageSensor(mock_coordinator, mock_config_entry)
        assert sensor._attr_name == "Current Billing Cycle Usage"
        assert sensor._attr_translation_key == "current_usage"

    def test_unique_id_defaults_when_entry_has_no_unique_id(self, mock_coordinator, mock_config_entry):
        mock_config_entry.unique_id = None
        sensor = ACWDCurrentUsageSensor(mock_coordinator, mock_config_entry)
        assert sensor.unique_id == "unknown_current_usage"


# -- ACWDCurrentCycleSensor --------------------------------------------------


@pytest.mark.unit
class TestACWDCurrentCycleSensor:
    """Tests for the current cycle projected sensor."""

    def test_native_value(self, mock_coordinator, mock_config_entry):
        sensor = ACWDCurrentCycleSensor(mock_coordinator, mock_config_entry)
        assert sensor.native_value == round(8000.75, 2)

    def test_native_value_no_data(self, mock_coordinator, mock_config_entry):
        mock_coordinator.data = None
        sensor = ACWDCurrentCycleSensor(mock_coordinator, mock_config_entry)
        assert sensor.native_value is None

    def test_native_value_empty_tentative(self, mock_coordinator, mock_config_entry):
        mock_coordinator.data = {"getTentativeData": []}
        sensor = ACWDCurrentCycleSensor(mock_coordinator, mock_config_entry)
        assert sensor.native_value is None

    def test_unique_id_and_name(self, mock_coordinator, mock_config_entry):
        sensor = ACWDCurrentCycleSensor(mock_coordinator, mock_config_entry)
        assert sensor.unique_id == "12345_current_cycle_projected"
        assert sensor._attr_name == "Current Billing Cycle Projected"

    def test_unique_id_defaults_when_entry_has_no_unique_id(self, mock_coordinator, mock_config_entry):
        mock_config_entry.unique_id = None
        sensor = ACWDCurrentCycleSensor(mock_coordinator, mock_config_entry)
        assert sensor.unique_id == "unknown_current_cycle_projected"


# -- ACWDLastBillingCycleSensor ----------------------------------------------


@pytest.mark.unit
class TestACWDLastBillingCycleSensor:
    """Tests for the last billing cycle sensor."""

    def test_native_value(self, mock_coordinator, mock_config_entry):
        sensor = ACWDLastBillingCycleSensor(mock_coordinator, mock_config_entry)
        assert sensor.native_value == round(7500.00, 2)

    def test_native_value_no_data(self, mock_coordinator, mock_config_entry):
        mock_coordinator.data = None
        sensor = ACWDLastBillingCycleSensor(mock_coordinator, mock_config_entry)
        assert sensor.native_value is None

    def test_native_value_empty_usage_records(self, mock_coordinator, mock_config_entry):
        mock_coordinator.data = {"objUsageGenerationResultSetTwo": []}
        sensor = ACWDLastBillingCycleSensor(mock_coordinator, mock_config_entry)
        assert sensor.native_value is None

    def test_extra_state_attributes(self, mock_coordinator, mock_config_entry):
        sensor = ACWDLastBillingCycleSensor(mock_coordinator, mock_config_entry)
        attrs = sensor.extra_state_attributes
        assert attrs["from_date"] == "11/01/2025"
        assert attrs["to_date"] == "12/31/2025"
        assert attrs["usage_date"] == "01/01/2026"
        assert attrs["service_charge"] == pytest.approx(45.50)
        assert "usage_hcf" in attrs
        assert attrs["high_usage_level"] == "No"

    def test_extra_state_attributes_no_data(self, mock_coordinator, mock_config_entry):
        mock_coordinator.data = None
        sensor = ACWDLastBillingCycleSensor(mock_coordinator, mock_config_entry)
        assert sensor.extra_state_attributes == {}

    def test_extra_state_attributes_empty_usage_records(self, mock_coordinator, mock_config_entry):
        mock_coordinator.data = {"objUsageGenerationResultSetTwo": []}
        sensor = ACWDLastBillingCycleSensor(mock_coordinator, mock_config_entry)
        assert sensor.extra_state_attributes == {}

    def test_unique_id_and_name(self, mock_coordinator, mock_config_entry):
        sensor = ACWDLastBillingCycleSensor(mock_coordinator, mock_config_entry)
        assert sensor.unique_id == "12345_last_billing_cycle"
        assert sensor._attr_name == "Last Billing Cycle Usage"

    def test_unique_id_defaults_when_entry_has_no_unique_id(self, mock_coordinator, mock_config_entry):
        mock_config_entry.unique_id = None
        sensor = ACWDLastBillingCycleSensor(mock_coordinator, mock_config_entry)
        assert sensor.unique_id == "unknown_last_billing_cycle"


# -- ACWDAverageSensor -------------------------------------------------------


@pytest.mark.unit
class TestACWDAverageSensor:
    """Tests for the average usage sensor."""

    def test_native_value(self, mock_coordinator, mock_config_entry):
        sensor = ACWDAverageSensor(mock_coordinator, mock_config_entry)
        assert sensor.native_value == round(6500.25, 2)

    def test_native_value_no_data(self, mock_coordinator, mock_config_entry):
        mock_coordinator.data = None
        sensor = ACWDAverageSensor(mock_coordinator, mock_config_entry)
        assert sensor.native_value is None

    def test_native_value_empty_tentative(self, mock_coordinator, mock_config_entry):
        mock_coordinator.data = {"getTentativeData": []}
        sensor = ACWDAverageSensor(mock_coordinator, mock_config_entry)
        assert sensor.native_value is None

    def test_unique_id_and_name(self, mock_coordinator, mock_config_entry):
        sensor = ACWDAverageSensor(mock_coordinator, mock_config_entry)
        assert sensor.unique_id == "12345_average_usage"
        assert sensor._attr_name == "Average Usage"

    def test_unique_id_defaults_when_entry_has_no_unique_id(self, mock_coordinator, mock_config_entry):
        mock_config_entry.unique_id = None
        sensor = ACWDAverageSensor(mock_coordinator, mock_config_entry)
        assert sensor.unique_id == "unknown_average_usage"


# -- ACWDHighestSensor -------------------------------------------------------


@pytest.mark.unit
class TestACWDHighestSensor:
    """Tests for the highest usage sensor."""

    def test_native_value(self, mock_coordinator, mock_config_entry):
        sensor = ACWDHighestSensor(mock_coordinator, mock_config_entry)
        assert sensor.native_value == round(12000.00, 2)

    def test_native_value_no_data(self, mock_coordinator, mock_config_entry):
        mock_coordinator.data = None
        sensor = ACWDHighestSensor(mock_coordinator, mock_config_entry)
        assert sensor.native_value is None

    def test_native_value_empty_tentative(self, mock_coordinator, mock_config_entry):
        mock_coordinator.data = {"getTentativeData": []}
        sensor = ACWDHighestSensor(mock_coordinator, mock_config_entry)
        assert sensor.native_value is None

    def test_unique_id_and_name(self, mock_coordinator, mock_config_entry):
        sensor = ACWDHighestSensor(mock_coordinator, mock_config_entry)
        assert sensor.unique_id == "12345_highest_usage"
        assert sensor._attr_name == "Highest Usage Ever"

    def test_unique_id_defaults_when_entry_has_no_unique_id(self, mock_coordinator, mock_config_entry):
        mock_config_entry.unique_id = None
        sensor = ACWDHighestSensor(mock_coordinator, mock_config_entry)
        assert sensor.unique_id == "unknown_highest_usage"


# -- async_setup_entry -------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
class TestAsyncSetupEntry:
    """Tests for async_setup_entry."""

    async def test_async_setup_entry(self, mock_coordinator, mock_config_entry):
        """Verify async_setup_entry creates and adds 5 sensor entities."""
        mock_hass = MagicMock()
        mock_hass.data = {"acwd": {mock_config_entry.entry_id: mock_coordinator}}
        mock_add_entities = MagicMock()

        with patch("custom_components.acwd.sensor._migrate_unknown_account_ids") as mock_migrate:
            await async_setup_entry(mock_hass, mock_config_entry, mock_add_entities)

        mock_migrate.assert_called_once_with(mock_hass, mock_config_entry, "12345")
        mock_add_entities.assert_called_once()
        entities = mock_add_entities.call_args[0][0]
        assert len(entities) == 5
        assert isinstance(entities[0], ACWDCurrentUsageSensor)
        assert isinstance(entities[1], ACWDCurrentCycleSensor)
        assert isinstance(entities[2], ACWDLastBillingCycleSensor)
        assert isinstance(entities[3], ACWDAverageSensor)
        assert isinstance(entities[4], ACWDHighestSensor)
        # Every entity must receive the real config_entry, not None.
        for entity in entities:
            assert entity._config_entry is mock_config_entry

    async def test_async_setup_entry_skips_migration_without_unique_id(self, mock_coordinator, mock_config_entry):
        """An entry with no unique_id has no real account ID to migrate to."""
        mock_config_entry.unique_id = None
        mock_hass = MagicMock()
        mock_hass.data = {"acwd": {mock_config_entry.entry_id: mock_coordinator}}

        with patch("custom_components.acwd.sensor._migrate_unknown_account_ids") as mock_migrate:
            await async_setup_entry(mock_hass, mock_config_entry, MagicMock())

        mock_migrate.assert_not_called()


# -- _migrate_unknown_account_ids --------------------------------------------


@pytest.mark.integration
class TestMigrateUnknownAccountIds:
    """Moves sensors created under the fallback IDs onto the real account number."""

    @staticmethod
    def _setup(hass, *, with_stale: bool):
        entry = MockConfigEntry(domain=DOMAIN, unique_id="57784", title="ACWD - Test User")
        entry.add_to_hass(hass)
        ent_reg = er.async_get(hass)
        dev_reg = dr.async_get(hass)
        unknown_device = dev_reg.async_get_or_create(
            config_entry_id=entry.entry_id, identifiers={(DOMAIN, "Unknown")}, name="ACWD Water - ACWD Water"
        )
        live = ent_reg.async_get_or_create(
            "sensor", DOMAIN, "unknown_current_usage", config_entry=entry, device_id=unknown_device.id
        )
        stale = None
        if with_stale:
            stale_device = dev_reg.async_get_or_create(
                config_entry_id=entry.entry_id, identifiers={(DOMAIN, "57784")}, name="ACWD Water - Test User"
            )
            stale = ent_reg.async_get_or_create(
                "sensor", DOMAIN, "57784_current_usage", config_entry=entry, device_id=stale_device.id
            )
        return entry, ent_reg, dev_reg, unknown_device, live, stale

    async def test_moves_entity_and_device_to_account_number(self, hass):
        entry, ent_reg, dev_reg, unknown_device, live, _ = self._setup(hass, with_stale=False)

        _migrate_unknown_account_ids(hass, entry, "57784")

        assert ent_reg.async_get(live.entity_id).unique_id == "57784_current_usage"
        assert dev_reg.async_get(unknown_device.id).identifiers == {(DOMAIN, "57784")}

    async def test_current_entity_wins_over_stale_one(self, hass):
        """A stale entity and device already holding the real IDs are removed; the live entity_id is kept."""
        entry, ent_reg, dev_reg, unknown_device, live, stale = self._setup(hass, with_stale=True)

        _migrate_unknown_account_ids(hass, entry, "57784")

        assert ent_reg.async_get(stale.entity_id) is None
        assert ent_reg.async_get(live.entity_id).unique_id == "57784_current_usage"
        assert ent_reg.async_get(live.entity_id).device_id == unknown_device.id
        assert dev_reg.async_get(unknown_device.id).identifiers == {(DOMAIN, "57784")}
        assert len(dr.async_entries_for_config_entry(dev_reg, entry.entry_id)) == 1

    async def test_already_migrated_is_a_no_op(self, hass):
        entry = MockConfigEntry(domain=DOMAIN, unique_id="57784", title="ACWD - Test User")
        entry.add_to_hass(hass)
        ent_reg = er.async_get(hass)
        entity = ent_reg.async_get_or_create("sensor", DOMAIN, "57784_current_usage", config_entry=entry)

        _migrate_unknown_account_ids(hass, entry, "57784")

        assert ent_reg.async_get(entity.entity_id).unique_id == "57784_current_usage"
