"""Sensor platform for ACWD Water Usage integration."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, HCF_TO_GALLONS

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
    """Sensor for current billing cycle usage total.

    Note: This shows the total water used in the current billing cycle (typically 2 months).
    For daily/hourly consumption in the Energy Dashboard, use the imported statistics instead.
    """

    _attr_device_class = SensorDeviceClass.WATER
    # No state_class - this is a snapshot of billing cycle total, not for Energy Dashboard
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

        # Get current usage (already in gallons from API)
        current_gallons = tentative_data[0].get("SoFar", 0)

        return round(current_gallons, 2)

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional attributes."""
        if not self.coordinator.data:
            return {}

        tentative_data = self.coordinator.data.get("getTentativeData", [])
        if not tentative_data:
            return {}

        data = tentative_data[0]

        # API returns values already in gallons
        current_gallons = data.get("SoFar", 0)
        expected_gallons = data.get("ExpectedUsage", 0)

        return {
            "usage_hcf": round(current_gallons / HCF_TO_GALLONS, 2),
            "usage_gallons": round(current_gallons, 2),
            "expected_total_hcf": round(expected_gallons / HCF_TO_GALLONS, 2),
            "expected_total_gallons": round(expected_gallons, 2),
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

        # API returns gallons already
        expected_gallons = tentative_data[0].get("ExpectedUsage", 0)
        return round(expected_gallons, 2)


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
        # API returns gallons already
        usage_gallons = last_cycle.get("UsageValue", 0)

        return round(usage_gallons, 2)

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional attributes."""
        if not self.coordinator.data:
            return {}

        usage_records = self.coordinator.data.get("objUsageGenerationResultSetTwo", [])
        if not usage_records:
            return {}

        last_cycle = usage_records[-1]
        # API returns gallons already
        usage_gallons = last_cycle.get("UsageValue", 0)

        return {
            "from_date": last_cycle.get("FromDate"),
            "to_date": last_cycle.get("ToDate"),
            "usage_date": last_cycle.get("UsageDate"),
            "service_charge": last_cycle.get("ServiceCharge"),
            "usage_hcf": round(usage_gallons / HCF_TO_GALLONS, 2),
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

        # API returns gallons already
        average_gallons = tentative_data[0].get("Average", 0)
        return round(average_gallons, 2)


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

        # API returns gallons already
        highest_gallons = tentative_data[0].get("Highest", 0)
        return round(highest_gallons, 2)
