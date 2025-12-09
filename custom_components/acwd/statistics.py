"""Statistics import for ACWD Water Usage integration."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    StatisticData,
    StatisticMetaData,
)
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_import_hourly_statistics(
    hass: HomeAssistant,
    meter_number: str,
    hourly_data: list[dict[str, Any]],
    date: datetime,
) -> None:
    """Import hourly water usage data as statistics.

    This function imports hourly water usage data into Home Assistant's
    long-term statistics database, making it available in the Energy Dashboard.

    Args:
        hass: Home Assistant instance
        meter_number: Water meter number
        hourly_data: List of hourly usage records from ACWD API
        date: The date for which this hourly data applies
    """
    statistic_id = f"{DOMAIN}:{meter_number}_hourly_usage"

    # Create metadata for the statistics
    metadata = StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name=f"ACWD Water Hourly Usage - Meter {meter_number}",
        source=DOMAIN,
        statistic_id=statistic_id,
        unit_of_measurement=UnitOfVolume.GALLONS.value,
        unit_class="volume",
    )

    # Get the last statistic from BEFORE the target date to get the correct baseline
    # This ensures we start from yesterday's final sum, not from earlier today
    target_date_start = dt_util.as_utc(date.replace(hour=0, minute=0, second=0, microsecond=0))

    last_stats = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, statistic_id, True, {"sum"}
    )

    # Start cumulative sum from last known value or 0
    # If the last statistic is from the target date, we need to look further back
    last_sum = 0
    if statistic_id in last_stats:
        stats_list = last_stats[statistic_id]
        if stats_list:
            last_stat_time = stats_list[0].get("start")

            # Ensure last_stat_time is a datetime object (might be float/Unix timestamp)
            if last_stat_time and not isinstance(last_stat_time, datetime):
                from datetime import datetime as dt_class
                last_stat_time = dt_class.fromtimestamp(last_stat_time, tz=dt_util.UTC)

            # Only use the last sum if it's from before the target date
            # Otherwise, we'd be adding today's values on top of today's partial sum
            if last_stat_time and last_stat_time < target_date_start:
                last_sum = stats_list[0]["sum"]
            else:
                # Last statistic is from target date, need to get sum from day before
                _LOGGER.debug(f"Last statistic is from target date {date.date()}, fetching baseline from previous day")
                # Get more history to find the last stat before target date
                last_stats_extended = await get_instance(hass).async_add_executor_job(
                    get_last_statistics, hass, 48, statistic_id, True, {"sum"}  # Get up to 48 hours
                )
                if statistic_id in last_stats_extended:
                    for stat in last_stats_extended[statistic_id]:
                        stat_time = stat.get("start")
                        # Ensure it's a datetime object
                        if stat_time and not isinstance(stat_time, datetime):
                            from datetime import datetime as dt_class
                            stat_time = dt_class.fromtimestamp(stat_time, tz=dt_util.UTC)

                        if stat_time and stat_time < target_date_start:
                            last_sum = stat["sum"]
                            _LOGGER.debug(f"Found baseline sum {last_sum} from {stat_time}")
                            break

    # Convert hourly data to statistics
    statistics: list[StatisticData] = []
    cumulative_sum = last_sum

    for record in hourly_data:
        # Parse the hour and usage value
        hourly_str = record.get("Hourly", "12:00 AM")  # Format: "12:00 AM", "1:00 AM", etc.
        usage_gallons = record.get("UsageValue", 0)

        # Parse hour from "HH:MM AM/PM" format
        try:
            time_obj = datetime.strptime(hourly_str, "%I:%M %p")
            hour = time_obj.hour
        except (ValueError, TypeError):
            _LOGGER.warning(f"Could not parse hourly time: {hourly_str}")
            hour = 0

        # Add to cumulative sum
        cumulative_sum += usage_gallons

        # Create timestamp for this hour
        timestamp = date.replace(hour=hour, minute=0, second=0, microsecond=0)
        timestamp_utc = dt_util.as_utc(timestamp)

        statistics.append(
            StatisticData(
                start=timestamp_utc,
                sum=cumulative_sum,
                state=usage_gallons,  # Individual hour usage
            )
        )

    # Import the statistics
    if statistics:
        async_add_external_statistics(hass, metadata, statistics)
        _LOGGER.info(
            f"Imported {len(statistics)} hourly statistics for {date.date()}"
        )


async def async_import_quarter_hourly_statistics(
    hass: HomeAssistant,
    meter_number: str,
    quarter_hourly_data: list[dict[str, Any]],
    date: datetime,
) -> None:
    """Import 15-minute water usage data as statistics.

    This function imports 15-minute interval water usage data into Home Assistant's
    long-term statistics database for highly granular tracking.

    Args:
        hass: Home Assistant instance
        meter_number: Water meter number
        quarter_hourly_data: List of 15-minute usage records from ACWD API
        date: The date for which this data applies
    """
    statistic_id = f"{DOMAIN}:{meter_number}_quarter_hourly_usage"

    # Create metadata for the statistics
    metadata = StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name=f"ACWD Water 15-Min Usage - Meter {meter_number}",
        source=DOMAIN,
        statistic_id=statistic_id,
        unit_of_measurement=UnitOfVolume.GALLONS.value,
        unit_class="volume",
    )

    # Get the last imported statistics
    last_stats = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, statistic_id, True, {"sum"}
    )

    last_sum = 0
    if statistic_id in last_stats:
        stats_list = last_stats[statistic_id]
        if stats_list:
            last_sum = stats_list[0]["sum"]

    # Convert 15-minute data to statistics
    statistics: list[StatisticData] = []
    cumulative_sum = last_sum

    for record in quarter_hourly_data:
        # Parse the timestamp and usage
        # Assuming API returns Hour and Quarter (0, 15, 30, 45)
        hour = record.get("Hour", 0)
        minute = record.get("Minute", 0)  # Should be 0, 15, 30, or 45
        usage_gallons = record.get("UsageValue", 0)

        # Add to cumulative sum
        cumulative_sum += usage_gallons

        # Create timestamp
        timestamp = date.replace(hour=hour, minute=minute, second=0, microsecond=0)
        timestamp_utc = dt_util.as_utc(timestamp)

        statistics.append(
            StatisticData(
                start=timestamp_utc,
                sum=cumulative_sum,
                state=usage_gallons,
            )
        )

    # Import the statistics
    if statistics:
        async_add_external_statistics(hass, metadata, statistics)
        _LOGGER.info(
            f"Imported {len(statistics)} 15-minute statistics for {date.date()}"
        )


async def async_import_daily_statistics(
    hass: HomeAssistant,
    meter_number: str,
    daily_data: list[dict[str, Any]],
) -> None:
    """Import daily water usage data as statistics.

    This function imports daily water usage summaries, useful for filling in
    historical data or when hourly data is not available.

    Args:
        hass: Home Assistant instance
        meter_number: Water meter number
        daily_data: List of daily usage records from ACWD API
    """
    statistic_id = f"{DOMAIN}:{meter_number}_daily_usage"

    # Create metadata
    metadata = StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name=f"ACWD Water Daily Usage - Meter {meter_number}",
        source=DOMAIN,
        statistic_id=statistic_id,
        unit_of_measurement=UnitOfVolume.GALLONS.value,
        unit_class="volume",
    )

    # Get last statistics
    last_stats = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, statistic_id, True, {"sum"}
    )

    last_sum = 0
    if statistic_id in last_stats:
        stats_list = last_stats[statistic_id]
        if stats_list:
            last_sum = stats_list[0]["sum"]

    # Convert daily data to statistics
    statistics: list[StatisticData] = []
    cumulative_sum = last_sum

    for record in daily_data:
        # Parse date and usage
        date_str = record.get("UsageDate")  # Format: "December 3, 2025"
        usage_gallons = record.get("UsageValue", 0)

        if not date_str:
            continue

        # Parse the date string
        try:
            date_obj = datetime.strptime(date_str, "%B %d, %Y")
        except (ValueError, TypeError):
            _LOGGER.warning(f"Could not parse date: {date_str}")
            continue

        # Add to cumulative sum
        cumulative_sum += usage_gallons

        # Create timestamp (start of day)
        timestamp = date_obj.replace(hour=0, minute=0, second=0, microsecond=0)
        timestamp_utc = dt_util.as_utc(timestamp)

        statistics.append(
            StatisticData(
                start=timestamp_utc,
                sum=cumulative_sum,
                state=usage_gallons,
            )
        )

    # Import the statistics
    if statistics:
        async_add_external_statistics(hass, metadata, statistics)
        _LOGGER.info(f"Imported {len(statistics)} daily statistics")
