"""The ACWD Water Usage integration."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .acwd_api import ACWDClient
from .statistics import (
    async_import_hourly_statistics,
    async_import_quarter_hourly_statistics,
    async_import_daily_statistics,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

# Update interval - ACWD has 24-hour data delay, update every 6 hours
UPDATE_INTERVAL = timedelta(hours=6)

# Service names
SERVICE_IMPORT_HOURLY = "import_hourly_data"
SERVICE_IMPORT_DAILY = "import_daily_data"

# Service schemas
SERVICE_IMPORT_HOURLY_SCHEMA = vol.Schema({
    vol.Required("date"): cv.date,
    vol.Optional("granularity", default="hourly"): vol.In(["hourly", "quarter_hourly"]),
})

SERVICE_IMPORT_DAILY_SCHEMA = vol.Schema({
    vol.Required("start_date"): cv.date,
    vol.Required("end_date"): cv.date,
})

# Configuration option keys
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ACWD Water Usage from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Create ACWD client
    client = ACWDClient(
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD]
    )

    # Create update coordinator
    coordinator = ACWDDataUpdateCoordinator(hass, client, entry)

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services
    async def handle_import_hourly(call: ServiceCall) -> None:
        """Handle the import_hourly_data service call."""
        date = call.data["date"]
        granularity = call.data["granularity"]

        # Ensure date is at least 2 days ago (24-hour delay + buffer)
        two_days_ago = (datetime.now() - timedelta(days=2)).date()
        if date > two_days_ago:
            _LOGGER.error(
                f"Cannot import data for {date}. Date must be at least 2 days ago "
                f"due to ACWD's 24-hour data delay."
            )
            return

        # Create a new client instance for the service call
        service_client = ACWDClient(
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD]
        )

        try:
            # Login with the new client
            logged_in = await hass.async_add_executor_job(service_client.login)
            if not logged_in:
                _LOGGER.error("Failed to login to ACWD portal")
                return

            # Format date for API
            date_str = date.strftime("%m/%d/%Y")

            # Fetch hourly data
            hourly_type = 'Q' if granularity == "quarter_hourly" else 'H'
            data = await hass.async_add_executor_job(
                service_client.get_usage_data,
                'H',  # mode
                None,  # date_from
                None,  # date_to
                date_str,  # str_date
                hourly_type  # hourly_type
            )

            if not data:
                _LOGGER.error(f"No data returned for {date}")
                return

            # Get meter number from client
            meter_number = service_client.meter_number
            if not meter_number:
                _LOGGER.error("Meter number not available")
                return

            # Extract hourly records
            hourly_records = data.get("objUsageGenerationResultSetTwo", [])

            if not hourly_records:
                _LOGGER.warning(f"No hourly data available for {date}")
                return

            # Import into statistics
            date_dt = datetime.combine(date, datetime.min.time())
            if granularity == "quarter_hourly":
                await async_import_quarter_hourly_statistics(
                    hass, meter_number, hourly_records, date_dt
                )
            else:
                await async_import_hourly_statistics(
                    hass, meter_number, hourly_records, date_dt
                )

            _LOGGER.info(f"Successfully imported {granularity} data for {date}")

        except Exception as err:
            _LOGGER.error(f"Error importing hourly data: {err}")
        finally:
            await hass.async_add_executor_job(service_client.logout)

    async def handle_import_daily(call: ServiceCall) -> None:
        """Handle the import_daily_data service call."""
        start_date = call.data["start_date"]
        end_date = call.data["end_date"]

        account_number = coordinator.client.user_info.get("AccountNumber")
        if not account_number:
            _LOGGER.error("Account number not available")
            return

        # Create a new client instance for the service call
        service_client = ACWDClient(
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD]
        )

        try:
            # Login with the new client
            logged_in = await hass.async_add_executor_job(service_client.login)
            if not logged_in:
                _LOGGER.error("Failed to login to ACWD portal")
                return

            # Format dates for API
            start_str = start_date.strftime("%m/%d/%Y")
            end_str = end_date.strftime("%m/%d/%Y")

            # Fetch daily data
            data = await hass.async_add_executor_job(
                service_client.get_usage_data,
                'D',  # mode
                start_str,  # date_from
                end_str,  # date_to
            )

            if not data:
                _LOGGER.error(f"No data returned for {start_date} to {end_date}")
                return

            # Extract daily records
            daily_records = data.get("objUsageGenerationResultSetTwo", [])

            if not daily_records:
                _LOGGER.warning(f"No daily data available for date range")
                return

            # Import into statistics
            await async_import_daily_statistics(
                hass, str(account_number), daily_records
            )

            _LOGGER.info(
                f"Successfully imported daily data from {start_date} to {end_date}"
            )

        except Exception as err:
            _LOGGER.error(f"Error importing daily data: {err}")
        finally:
            await hass.async_add_executor_job(service_client.logout)

    # Register services
    hass.services.async_register(
        DOMAIN,
        SERVICE_IMPORT_HOURLY,
        handle_import_hourly,
        schema=SERVICE_IMPORT_HOURLY_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_IMPORT_DAILY,
        handle_import_daily,
        schema=SERVICE_IMPORT_DAILY_SCHEMA,
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class ACWDDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching ACWD data."""

    def __init__(self, hass: HomeAssistant, client: ACWDClient, entry: ConfigEntry) -> None:
        """Initialize."""
        self.client = client
        self.entry = entry
        self._last_hourly_import_date = None

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )

    async def _async_update_data(self):
        """Fetch data from ACWD."""
        try:
            # Login and fetch data
            logged_in = await self.hass.async_add_executor_job(self.client.login)

            if not logged_in:
                raise UpdateFailed("Failed to login to ACWD portal")

            # Get billing cycle data (mode='B' for complete summary data)
            data = await self.hass.async_add_executor_job(
                self.client.get_usage_data, 'B'
            )

            if not data:
                raise UpdateFailed("No data returned from ACWD portal")

            # Automatically import yesterday's hourly data (once per day)
            await self._import_yesterday_hourly_data()

            # Logout
            await self.hass.async_add_executor_job(self.client.logout)

            return data

        except Exception as err:
            raise UpdateFailed(f"Error communicating with ACWD: {err}") from err

    async def _import_yesterday_hourly_data(self):
        """Automatically import yesterday's hourly data into statistics."""
        # Calculate yesterday's date (2 days ago to account for 24-hour delay)
        yesterday = (datetime.now() - timedelta(days=2)).date()

        # Only import once per day
        if self._last_hourly_import_date == yesterday:
            return

        try:
            _LOGGER.info(f"Importing hourly data for {yesterday}")

            # Format date for API
            date_str = yesterday.strftime("%m/%d/%Y")

            # Fetch hourly data (already logged in)
            data = await self.hass.async_add_executor_job(
                self.client.get_usage_data,
                'H',  # mode
                None,  # date_from
                None,  # date_to
                date_str,  # str_date
                'H'  # hourly_type (hourly, not quarter-hourly)
            )

            if not data:
                _LOGGER.debug(f"No hourly data returned for {yesterday}")
                return

            # Get meter number from client
            meter_number = self.client.meter_number
            if not meter_number:
                _LOGGER.debug("Meter number not available for hourly import")
                return

            # Extract hourly records
            hourly_records = data.get("objUsageGenerationResultSetTwo", [])

            if not hourly_records:
                _LOGGER.debug(f"No hourly records available for {yesterday}")
                return

            # Import into statistics
            date_dt = datetime.combine(yesterday, datetime.min.time())
            await async_import_hourly_statistics(
                self.hass, meter_number, hourly_records, date_dt
            )

            # Mark as imported
            self._last_hourly_import_date = yesterday
            _LOGGER.info(f"Successfully auto-imported hourly data for {yesterday}")

        except Exception as err:
            _LOGGER.warning(f"Failed to auto-import hourly data for {yesterday}: {err}")
