"""Tests for sensor.py - ACWD sensor entities."""
import sys
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Import sensor module via importlib (avoids pulling in __init__.py)
_sensor_path = Path(__file__).parent.parent / "custom_components" / "acwd" / "sensor.py"
_sensor_spec = importlib.util.spec_from_file_location(
    "custom_components.acwd.sensor",
    _sensor_path,
)
assert _sensor_spec is not None and _sensor_spec.loader is not None, (
    f"Failed to create module spec from {_sensor_path}"
)
_sensor_module = importlib.util.module_from_spec(_sensor_spec)
_sensor_spec.loader.exec_module(_sensor_module)
sys.modules["custom_components.acwd.sensor"] = _sensor_module

HCF_TO_GALLONS = _sensor_module.HCF_TO_GALLONS

# Extract classes for direct use
ACWDSensorBase = _sensor_module.ACWDSensorBase
ACWDCurrentUsageSensor = _sensor_module.ACWDCurrentUsageSensor
ACWDCurrentCycleSensor = _sensor_module.ACWDCurrentCycleSensor
ACWDLastBillingCycleSensor = _sensor_module.ACWDLastBillingCycleSensor
ACWDAverageSensor = _sensor_module.ACWDAverageSensor
ACWDHighestSensor = _sensor_module.ACWDHighestSensor
async_setup_entry = _sensor_module.async_setup_entry


# -- Fixtures ----------------------------------------------------------------

SAMPLE_COORDINATOR_DATA = {
    "getTentativeData": [{
        "SoFar": 5000.50,
        "ExpectedUsage": 8000.75,
        "Average": 6500.25,
        "Highest": 12000.00,
        "UsageDate": "01/15/2026",
    }],
    "objUsageGenerationResultSetTwo": [{
        "UsageValue": 7500.00,
        "FromDate": "11/01/2025",
        "ToDate": "12/31/2025",
        "UsageDate": "01/01/2026",
        "ServiceCharge": 45.50,
        "HighUsage": "No",
    }],
}


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator with sample data."""
    coordinator = MagicMock()
    coordinator.client.user_info = {"AccountNumber": "12345", "Name": "Test User"}
    coordinator.data = SAMPLE_COORDINATOR_DATA
    return coordinator


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    return entry


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

    def test_unique_id(self, mock_coordinator, mock_config_entry):
        sensor = ACWDCurrentUsageSensor(mock_coordinator, mock_config_entry)
        assert sensor._attr_unique_id == "12345_current_usage"


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

    def test_extra_state_attributes(self, mock_coordinator, mock_config_entry):
        sensor = ACWDLastBillingCycleSensor(mock_coordinator, mock_config_entry)
        attrs = sensor.extra_state_attributes
        assert attrs["from_date"] == "11/01/2025"
        assert attrs["to_date"] == "12/31/2025"
        assert attrs["usage_date"] == "01/01/2026"
        assert attrs["service_charge"] == pytest.approx(45.50)
        assert "usage_hcf" in attrs
        assert attrs["high_usage_level"] == "No"


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

        await async_setup_entry(mock_hass, mock_config_entry, mock_add_entities)

        mock_add_entities.assert_called_once()
        entities = mock_add_entities.call_args[0][0]
        assert len(entities) == 5
        assert isinstance(entities[0], ACWDCurrentUsageSensor)
        assert isinstance(entities[1], ACWDCurrentCycleSensor)
        assert isinstance(entities[2], ACWDLastBillingCycleSensor)
        assert isinstance(entities[3], ACWDAverageSensor)
        assert isinstance(entities[4], ACWDHighestSensor)
