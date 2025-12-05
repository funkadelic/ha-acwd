"""Sensor platform for ACWD Water Usage integration."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, GALLONS_TO_LITERS, HCF_TO_GALLONS

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ACWD sensors based on a config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    # Create sensors
    entities = [
        ACWDCurrentUsageSensor(coordinator, config_entry),
        ACWDCurrentCycleSensor(coordinator, config_entry),
        ACWDLastBillingCycleSensor(coordinator, config_entry),
        ACWDAverageSensor(coordinator, config_entry),
        ACWDHighestSensor(coordinator, config_entry),
    ]

    async_add_entities(entities)


class ACWDSensorBase(CoordinatorEntity, SensorEntity):
    """Base class for ACWD sensors."""

    def __init__(self, coordinator, config_entry):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_has_entity_name = True

        # Device info
        account_number = coordinator.client.user_info.get("AccountNumber", "Unknown")
        account_name = coordinator.client.user_info.get("Name", "ACWD Water")

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(account_number))},
            name=f"ACWD Water - {account_name}",
            manufacturer="Alameda County Water District",
            model="Water Meter",
            configuration_url="https://portal.acwd.org/portal/",
        )


class ACWDCurrentUsageSensor(ACWDSensorBase):
    """Sensor for current billing cycle usage (for Energy Dashboard)."""

    _attr_device_class = SensorDeviceClass.WATER
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfVolume.GALLONS
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator, config_entry):
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry)
        account_number = coordinator.client.user_info.get("AccountNumber", "unknown")
        self._attr_unique_id = f"{account_number}_current_usage"
        self._attr_name = "Current Cycle Usage"
        self._attr_translation_key = "current_usage"

    @property
    def native_value(self) -> float | None:
        """Return the current cycle usage in gallons."""
        if not self.coordinator.data:
            return None

        tentative_data = self.coordinator.data.get("getTentativeData", [])
        if not tentative_data:
            return None

        # Get current usage in HCF
        current_hcf = tentative_data[0].get("SoFar", 0)

        # Convert HCF -> Gallons
        gallons = current_hcf * HCF_TO_GALLONS

        return round(gallons, 2)

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional attributes."""
        if not self.coordinator.data:
            return {}

        tentative_data = self.coordinator.data.get("getTentativeData", [])
        if not tentative_data:
            return {}

        data = tentative_data[0]

        # Calculate values in different units
        current_hcf = data.get("SoFar", 0)
        current_gallons = current_hcf * HCF_TO_GALLONS

        return {
            "usage_hcf": current_hcf,
            "usage_gallons": round(current_gallons, 2),
            "expected_total_hcf": data.get("ExpectedUsage", 0),
            "expected_total_gallons": round(data.get("ExpectedUsage", 0) * HCF_TO_GALLONS, 2),
            "cycle_date": data.get("UsageDate"),
        }


class ACWDCurrentCycleSensor(ACWDSensorBase):
    """Sensor for current cycle projected total."""

    _attr_native_unit_of_measurement = UnitOfVolume.GALLONS
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:water"

    def __init__(self, coordinator, config_entry):
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry)
        account_number = coordinator.client.user_info.get("AccountNumber", "unknown")
        self._attr_unique_id = f"{account_number}_current_cycle_projected"
        self._attr_name = "Current Cycle Projected"

    @property
    def native_value(self) -> float | None:
        """Return the projected total for current cycle in gallons."""
        if not self.coordinator.data:
            return None

        tentative_data = self.coordinator.data.get("getTentativeData", [])
        if not tentative_data:
            return None

        expected_hcf = tentative_data[0].get("ExpectedUsage", 0)
        return round(expected_hcf * HCF_TO_GALLONS, 2)


class ACWDLastBillingCycleSensor(ACWDSensorBase):
    """Sensor for last completed billing cycle."""

    _attr_native_unit_of_measurement = UnitOfVolume.GALLONS
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:water-check"

    def __init__(self, coordinator, config_entry):
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry)
        account_number = coordinator.client.user_info.get("AccountNumber", "unknown")
        self._attr_unique_id = f"{account_number}_last_billing_cycle"
        self._attr_name = "Last Billing Cycle"

    @property
    def native_value(self) -> float | None:
        """Return the last billing cycle usage in gallons."""
        if not self.coordinator.data:
            return None

        usage_records = self.coordinator.data.get("objUsageGenerationResultSetTwo", [])
        if not usage_records:
            return None

        # Get the most recent completed billing cycle
        last_cycle = usage_records[-1]
        usage_hcf = last_cycle.get("UsageValue", 0)

        return round(usage_hcf * HCF_TO_GALLONS, 2)

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional attributes."""
        if not self.coordinator.data:
            return {}

        usage_records = self.coordinator.data.get("objUsageGenerationResultSetTwo", [])
        if not usage_records:
            return {}

        last_cycle = usage_records[-1]

        return {
            "from_date": last_cycle.get("FromDate"),
            "to_date": last_cycle.get("ToDate"),
            "usage_date": last_cycle.get("UsageDate"),
            "service_charge": last_cycle.get("ServiceCharge"),
            "usage_hcf": last_cycle.get("UsageValue"),
            "high_usage_level": last_cycle.get("HighUsage"),
        }


class ACWDAverageSensor(ACWDSensorBase):
    """Sensor for historical average usage."""

    _attr_native_unit_of_measurement = UnitOfVolume.GALLONS
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:chart-line"

    def __init__(self, coordinator, config_entry):
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry)
        account_number = coordinator.client.user_info.get("AccountNumber", "unknown")
        self._attr_unique_id = f"{account_number}_average_usage"
        self._attr_name = "Average Usage"

    @property
    def native_value(self) -> float | None:
        """Return the historical average usage in gallons."""
        if not self.coordinator.data:
            return None

        tentative_data = self.coordinator.data.get("getTentativeData", [])
        if not tentative_data:
            return None

        average_hcf = tentative_data[0].get("Average", 0)
        return round(average_hcf * HCF_TO_GALLONS, 2)


class ACWDHighestSensor(ACWDSensorBase):
    """Sensor for highest usage ever recorded."""

    _attr_native_unit_of_measurement = UnitOfVolume.GALLONS
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:arrow-up-bold"

    def __init__(self, coordinator, config_entry):
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry)
        account_number = coordinator.client.user_info.get("AccountNumber", "unknown")
        self._attr_unique_id = f"{account_number}_highest_usage"
        self._attr_name = "Highest Usage Ever"

    @property
    def native_value(self) -> float | None:
        """Return the highest usage ever in gallons."""
        if not self.coordinator.data:
            return None

        tentative_data = self.coordinator.data.get("getTentativeData", [])
        if not tentative_data:
            return None

        highest_hcf = tentative_data[0].get("Highest", 0)
        return round(highest_hcf * HCF_TO_GALLONS, 2)
