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
CONF_INITIAL_IMPORT_DONE = "initial_import_done"
INITIAL_IMPORT_DAYS = 7  # Import last 7 days on first setup


async def _async_import_initial_history(
    hass: HomeAssistant, coordinator: ACWDDataUpdateCoordinator
) -> None:
    """Import initial historical data on first setup.

    Imports the last 7 days of hourly data when the integration is first installed.
    This runs in the background and won't block setup if it fails.
    """
    # Check if initial import has already been done
    if coordinator.entry.data.get(CONF_INITIAL_IMPORT_DONE, False):
        _LOGGER.debug("Initial history import already completed, skipping")
        return

    account_number = coordinator.client.user_info.get("AccountNumber")
    if not account_number:
        _LOGGER.warning("Cannot import initial history: account number not available")
        return

    _LOGGER.info(f"Starting initial import of last {INITIAL_IMPORT_DAYS} days of hourly data")

    try:
        # Calculate date range (ending 2 days ago due to 24-hour delay)
        end_date = (datetime.now() - timedelta(days=2)).date()
        start_date = end_date - timedelta(days=INITIAL_IMPORT_DAYS - 1)

        # Login once and reuse the session for all imports
        logged_in = await hass.async_add_executor_job(coordinator.client.login)
        if not logged_in:
            _LOGGER.error("Failed to login for initial history import")
            hass.config_entries.async_update_entry(
                coordinator.entry,
                data={**coordinator.entry.data, CONF_INITIAL_IMPORT_DONE: True}
            )
            return

        # Import each day's hourly data
        successful_imports = 0
        failed_imports = 0

        for day_offset in range(INITIAL_IMPORT_DAYS):
            import_date = start_date + timedelta(days=day_offset)

            try:
                # Format date for API
                date_str = import_date.strftime("%m/%d/%Y")

                # Fetch hourly data (already logged in)
                data = await hass.async_add_executor_job(
                    coordinator.client.get_usage_data,
                    'H',  # mode
                    None,  # date_from
                    None,  # date_to
                    date_str,  # str_date
                    'H'  # hourly_type
                )

                if not data:
                    _LOGGER.debug(f"No data returned for initial import of {import_date}")
                    failed_imports += 1
                    continue

                # Extract hourly records
                hourly_records = data.get("objUsageGenerationResultSetTwo", [])

                if not hourly_records:
                    _LOGGER.debug(f"No hourly records for {import_date}")
                    failed_imports += 1
                    continue

                # Import into statistics
                date_dt = datetime.combine(import_date, datetime.min.time())
                await async_import_hourly_statistics(
                    hass, str(account_number), hourly_records, date_dt
                )

                successful_imports += 1
                _LOGGER.info(f"Initial import: imported {import_date} ({successful_imports}/{INITIAL_IMPORT_DAYS})")

            except Exception as err:
                _LOGGER.warning(f"Failed to import initial data for {import_date}: {err}")
                failed_imports += 1

        # Logout once at the end
        try:
            await hass.async_add_executor_job(coordinator.client.logout)
        except Exception as err:
            _LOGGER.debug(f"Error during logout: {err}")

        # Mark initial import as done (even if some days failed)
        hass.config_entries.async_update_entry(
            coordinator.entry,
            data={**coordinator.entry.data, CONF_INITIAL_IMPORT_DONE: True}
        )

        _LOGGER.info(
            f"Initial history import completed: {successful_imports} successful, "
            f"{failed_imports} failed out of {INITIAL_IMPORT_DAYS} days"
        )

    except Exception as err:
        _LOGGER.error(f"Error during initial history import: {err}")
        # Mark as done anyway to avoid retrying on every restart
        hass.config_entries.async_update_entry(
            coordinator.entry,
            data={**coordinator.entry.data, CONF_INITIAL_IMPORT_DONE: True}
        )


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

    # First-run: Import last 7 days of historical hourly data
    await _async_import_initial_history(hass, coordinator)

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

            # Extract hourly records
            hourly_records = data.get("objUsageGenerationResultSetTwo", [])

            if not hourly_records:
                _LOGGER.warning(f"No hourly data available for {date}")
                return

            # Import into statistics
            date_dt = datetime.combine(date, datetime.min.time())
            if granularity == "quarter_hourly":
                await async_import_quarter_hourly_statistics(
                    hass, str(account_number), hourly_records, date_dt
                )
            else:
                await async_import_hourly_statistics(
                    hass, str(account_number), hourly_records, date_dt
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

        account_number = self.client.user_info.get("AccountNumber")
        if not account_number:
            _LOGGER.debug("Account number not available for hourly import")
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

            # Extract hourly records
            hourly_records = data.get("objUsageGenerationResultSetTwo", [])

            if not hourly_records:
                _LOGGER.debug(f"No hourly records available for {yesterday}")
                return

            # Import into statistics
            date_dt = datetime.combine(yesterday, datetime.min.time())
            await async_import_hourly_statistics(
                self.hass, str(account_number), hourly_records, date_dt
            )

            # Mark as imported
            self._last_hourly_import_date = yesterday
            _LOGGER.info(f"Successfully auto-imported hourly data for {yesterday}")

        except Exception as err:
            _LOGGER.warning(f"Failed to auto-import hourly data for {yesterday}: {err}")
