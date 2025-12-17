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

# Update interval - check for new data every hour
UPDATE_INTERVAL = timedelta(hours=1)

# Service names
SERVICE_IMPORT_HOURLY = "import_hourly_data"
SERVICE_IMPORT_DAILY = "import_daily_data"

# Error messages
ERROR_LOGIN_FAILED = "Failed to login to ACWD portal"

# Date format for ACWD API
DATE_FORMAT_ACWD = "%m/%d/%Y"

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

    # Import yesterday's data on first setup to provide immediate feedback
    await _async_import_initial_yesterday_data(hass, coordinator)

    # Register services
    async def handle_import_hourly(call: ServiceCall) -> None:
        """Handle the import_hourly_data service call."""
        date = call.data["date"]
        granularity = call.data["granularity"]

        # Ensure date is at least 1 day ago due to ACWD's reporting delay
        one_day_ago = (datetime.now() - timedelta(days=1)).date()
        if date > one_day_ago:
            _LOGGER.error(
                f"Cannot import data for {date}. Date must be at least 1 day ago "
                "due to ACWD's reporting delay."
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
                _LOGGER.error(ERROR_LOGIN_FAILED)
                return

            # Format date for API
            date_str = date.strftime(DATE_FORMAT_ACWD)

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
                _LOGGER.error(ERROR_LOGIN_FAILED)
                return

            # Format dates for API
            start_str = start_date.strftime(DATE_FORMAT_ACWD)
            end_str = end_date.strftime(DATE_FORMAT_ACWD)

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
                _LOGGER.warning("No daily data available for date range")
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


async def _async_import_initial_yesterday_data(
    hass: HomeAssistant,
    coordinator: "ACWDDataUpdateCoordinator"
) -> None:
    """Import yesterday's data on first setup to provide immediate feedback to users.

    This is a one-time import that runs when the integration is first installed.
    It gives users immediate data to see in the Energy Dashboard.
    """
    try:
        yesterday = (datetime.now() - timedelta(days=1)).date()
        _LOGGER.info(f"Initial setup: Importing yesterday's data ({yesterday})")

        # Create a fresh client instance to avoid session conflicts
        from .acwd_api import ACWDClient
        username = coordinator.entry.data.get(CONF_USERNAME)
        password = coordinator.entry.data.get(CONF_PASSWORD)
        fresh_client = ACWDClient(username, password)

        # Format date for API
        date_str = yesterday.strftime(DATE_FORMAT_ACWD)

        # Login
        logged_in = await hass.async_add_executor_job(fresh_client.login)
        if not logged_in:
            _LOGGER.warning(f"Initial import: {ERROR_LOGIN_FAILED}")
            return

        # Fetch hourly data
        data = await hass.async_add_executor_job(
            fresh_client.get_usage_data,
            'H',  # mode
            None,  # date_from
            None,  # date_to
            date_str,  # str_date
            'H'  # hourly_type
        )

        # Logout
        await hass.async_add_executor_job(fresh_client.logout)

        if not data:
            _LOGGER.debug(f"Initial import: No data returned for {yesterday}")
            return

        # Get meter number
        meter_number = fresh_client.meter_number
        if not meter_number:
            _LOGGER.debug("Initial import: Meter number not available")
            return

        # Extract hourly records
        hourly_records = data.get("objUsageGenerationResultSetTwo", [])

        if not hourly_records:
            _LOGGER.debug(f"Initial import: No hourly records for {yesterday}")
            return

        # Import into statistics
        # Create datetime in local timezone for proper timestamp handling
        from homeassistant.util import dt as dt_util
        local_tz = dt_util.get_default_time_zone()
        date_dt = datetime.combine(yesterday, datetime.min.time())
        date_dt = date_dt.replace(tzinfo=local_tz)
        await async_import_hourly_statistics(
            hass, meter_number, hourly_records, date_dt
        )

        _LOGGER.info(f"Initial setup: Successfully imported {len(hourly_records)} hours for {yesterday}")

    except Exception as err:
        _LOGGER.warning(f"Initial import failed (non-critical): {err}")


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
                raise UpdateFailed(ERROR_LOGIN_FAILED)

            # Get billing cycle data (mode='B' for complete summary data)
            data = await self.hass.async_add_executor_job(
                self.client.get_usage_data, 'B'
            )

            if not data:
                raise UpdateFailed("No data returned from ACWD portal")

            # Automatically import today's hourly data
            await self._import_today_hourly_data()

            # Also import yesterday's data during early morning hours (0-6 AM)
            # to catch the last few hours that become available overnight
            await self._import_yesterday_complete_data()

            # Logout
            await self.hass.async_add_executor_job(self.client.logout)

            return data

        except Exception as err:
            raise UpdateFailed(f"Error communicating with ACWD: {err}") from err

    async def _import_today_hourly_data(self):
        """Automatically import today's hourly data into statistics.

        Imports today's partial data every hour (accounting for variable ACWD delay).
        The statistics system automatically handles duplicates by replacing data
        with the same timestamp, so importing multiple times is safe.
        """
        # Import today's data (partial, accounting for variable delay)
        today = datetime.now().date()

        try:
            _LOGGER.debug(f"Checking for hourly data for {today}")

            # Format date for API
            date_str = today.strftime(DATE_FORMAT_ACWD)

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
                _LOGGER.debug(f"No hourly data returned for {today}")
                return

            # Get meter number from client
            meter_number = self.client.meter_number
            if not meter_number:
                _LOGGER.debug("Meter number not available for hourly import")
                return

            # Extract hourly records
            hourly_records = data.get("objUsageGenerationResultSetTwo", [])

            if not hourly_records:
                _LOGGER.debug(f"No hourly records available for {today}")
                return

            # Find last hour with usage > 0 to determine actual data availability
            last_nonzero_hour = None
            last_nonzero_index = -1
            for i, record in enumerate(reversed(hourly_records)):
                usage = record.get("UsageValue", 0)
                if usage > 0:
                    last_nonzero_hour = record.get("Hourly", "unknown")
                    last_nonzero_index = len(hourly_records) - 1 - i
                    break

            if last_nonzero_hour:
                _LOGGER.info(f"Latest available data for {today}: {last_nonzero_hour} ({last_nonzero_index + 1} hours)")
            else:
                _LOGGER.debug(f"No non-zero usage found for {today}")

            # Import into statistics (duplicates are automatically handled)
            # Create datetime in local timezone for proper timestamp handling
            from homeassistant.util import dt as dt_util
            local_tz = dt_util.get_default_time_zone()
            date_dt = datetime.combine(today, datetime.min.time())
            date_dt = date_dt.replace(tzinfo=local_tz)
            await async_import_hourly_statistics(
                self.hass, meter_number, hourly_records, date_dt
            )

            _LOGGER.info(f"Imported {len(hourly_records)} hourly records for {today}")

        except Exception as err:
            _LOGGER.warning(f"Failed to auto-import hourly data for {today}: {err}")

    async def _import_yesterday_complete_data(self):
        """Import yesterday's complete data during morning hours (0-12 PM).

        This catches yesterday's final hours (typically 9 PM - 11 PM) that only
        become available after midnight due to ACWD's 3-4 hour reporting delay.

        Only runs between midnight and noon to avoid unnecessary API calls.
        """
        current_hour = datetime.now().hour

        # Only run during morning hours (0-12 PM)
        if current_hour >= 12:
            return

        yesterday = (datetime.now() - timedelta(days=1)).date()

        try:
            _LOGGER.debug(f"Early morning check: Importing complete data for {yesterday}")

            # Format date for API
            date_str = yesterday.strftime(DATE_FORMAT_ACWD)

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

            # Import into statistics (duplicates are automatically handled)
            # Create datetime in local timezone for proper timestamp handling
            from homeassistant.util import dt as dt_util
            local_tz = dt_util.get_default_time_zone()
            date_dt = datetime.combine(yesterday, datetime.min.time())
            date_dt = date_dt.replace(tzinfo=local_tz)
            await async_import_hourly_statistics(
                self.hass, meter_number, hourly_records, date_dt
            )

            _LOGGER.info(f"Early morning import: Updated {len(hourly_records)} hourly records for {yesterday}")

        except Exception as err:
            _LOGGER.warning(f"Failed to import complete yesterday data for {yesterday}: {err}")
