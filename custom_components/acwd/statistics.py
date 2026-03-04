"""Statistics import for ACWD Water Usage integration."""
from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .helpers import local_midnight, parse_date_long, parse_time_12hr

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
        mean_type=StatisticMeanType.NONE,
        name=f"ACWD Water Hourly Usage - Meter {meter_number}",
        source=DOMAIN,
        statistic_id=statistic_id,
        unit_of_measurement=UnitOfVolume.GALLONS.value,
        unit_class="volume",
    )

    # Get the last statistic from BEFORE the target date to get the correct baseline
    # This ensures we start from yesterday's final sum, not from earlier today
    # .date() since date param is datetime; timezone-aware to prevent UTC baseline bugs
    target_date_midnight_local = local_midnight(date.date())

    # Convert to UTC for comparison
    target_date_start = dt_util.as_utc(target_date_midnight_local)

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
            last_stat_sum = stats_list[0].get("sum") or 0

            # Ensure last_stat_time is a datetime object (might be float/Unix timestamp)
            if last_stat_time and not isinstance(last_stat_time, datetime):
                last_stat_time = datetime.fromtimestamp(last_stat_time, tz=dt_util.UTC)

            _LOGGER.debug("Last statistic: time=%s, sum=%s, target_date_start=%s", last_stat_time, last_stat_sum, target_date_start)

            # Only use the last sum if it's from before the target date
            # Otherwise, we'd be adding today's values on top of today's partial sum
            if last_stat_time and last_stat_time < target_date_start:
                last_sum = last_stat_sum
                _LOGGER.debug("Using last sum %s from %s as baseline", last_sum, last_stat_time)
            else:
                # Last statistic is from target date, need to get sum from day before
                _LOGGER.debug("Last statistic is from target date %s, fetching baseline from previous day", date.date())
                # Get more history to find the last stat before target date
                last_stats_extended = await get_instance(hass).async_add_executor_job(
                    get_last_statistics, hass, 48, statistic_id, True, {"sum"}  # Get up to 48 hours
                )
                if statistic_id in last_stats_extended:
                    _LOGGER.debug("Searching %d historical stats for baseline", len(last_stats_extended[statistic_id]))
                    for i, stat in enumerate(last_stats_extended[statistic_id]):
                        stat_time = stat.get("start")
                        stat_sum = stat.get("sum") or 0
                        # Ensure it's a datetime object
                        if stat_time and not isinstance(stat_time, datetime):
                            stat_time = datetime.fromtimestamp(stat_time, tz=dt_util.UTC)

                        _LOGGER.debug("  Stat %d: time=%s, sum=%s, before_target=%s", i, stat_time, stat_sum, stat_time < target_date_start if stat_time else None)

                        if stat_time and stat_time < target_date_start:
                            last_sum = stat_sum
                            _LOGGER.debug("Found baseline sum %s from %s", last_sum, stat_time)
                            break

    # Convert hourly data to statistics
    statistics: list[StatisticData] = []
    cumulative_sum = last_sum

    for record in hourly_data:
        # Parse the hour and usage value
        hourly_str = record.get("Hourly")  # Format: "12:00 AM", "1:00 AM", etc.
        usage_gallons = record.get("UsageValue") or 0

        if not hourly_str or not hourly_str.strip():
            _LOGGER.warning("Skipping record with missing Hourly field")
            continue

        # Parse hour from "HH:MM AM/PM" format
        hour = parse_time_12hr(hourly_str)
        if hour is None:
            _LOGGER.warning("Skipping record with unparseable hour: %r", hourly_str)
            continue

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
        _LOGGER.info("Imported %d hourly statistics for %s", len(statistics), date.date())


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
        mean_type=StatisticMeanType.NONE,
        name=f"ACWD Water 15-Min Usage - Meter {meter_number}",
        source=DOMAIN,
        statistic_id=statistic_id,
        unit_of_measurement=UnitOfVolume.GALLONS.value,
        unit_class="volume",
    )

    # Get the last statistic from BEFORE the target date to get the correct baseline
    # This ensures re-imports of the same date don't inflate cumulative sums
    target_date_midnight_local = local_midnight(date.date())
    target_date_start = dt_util.as_utc(target_date_midnight_local)

    last_stats = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, statistic_id, True, {"sum"}
    )

    last_sum = 0
    if statistic_id in last_stats:
        stats_list = last_stats[statistic_id]
        if stats_list:
            last_stat_time = stats_list[0].get("start")
            last_stat_sum = stats_list[0].get("sum") or 0

            if last_stat_time and not isinstance(last_stat_time, datetime):
                last_stat_time = datetime.fromtimestamp(last_stat_time, tz=dt_util.UTC)

            if last_stat_time and last_stat_time < target_date_start:
                last_sum = last_stat_sum
            else:
                # Last statistic is from target date, search further back
                last_stats_extended = await get_instance(hass).async_add_executor_job(
                    get_last_statistics, hass, 192, statistic_id, True, {"sum"}
                )
                if statistic_id in last_stats_extended:
                    for stat in last_stats_extended[statistic_id]:
                        stat_time = stat.get("start")
                        stat_sum = stat.get("sum") or 0
                        if stat_time and not isinstance(stat_time, datetime):
                            stat_time = datetime.fromtimestamp(stat_time, tz=dt_util.UTC)
                        if stat_time and stat_time < target_date_start:
                            last_sum = stat_sum
                            break

    # Convert 15-minute data to statistics
    statistics: list[StatisticData] = []
    cumulative_sum = last_sum

    for record in quarter_hourly_data:
        # Parse the timestamp and usage
        # Assuming API returns Hour and Quarter (0, 15, 30, 45)
        hour = record.get("Hour")
        minute = record.get("Minute")  # Should be 0, 15, 30, or 45
        usage_gallons = record.get("UsageValue") or 0

        if hour is None or minute is None:
            _LOGGER.warning("Skipping record with missing Hour or Minute field")
            continue

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
        _LOGGER.info("Imported %d 15-minute statistics for %s", len(statistics), date.date())


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
        mean_type=StatisticMeanType.NONE,
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
            last_sum = stats_list[0].get("sum") or 0

    # Convert daily data to statistics
    statistics: list[StatisticData] = []
    cumulative_sum = last_sum

    for record in daily_data:
        # Parse date and usage
        date_str = record.get("UsageDate")  # Format: "December 3, 2025"
        usage_gallons = record.get("UsageValue") or 0

        if not date_str:
            continue

        # Parse the date string
        date_obj = parse_date_long(date_str)
        if date_obj is None:
            _LOGGER.warning("Skipping record with unparseable date: %r", date_str)
            continue
        # Add to cumulative sum
        cumulative_sum += usage_gallons

        # Create timestamp (start of day in local timezone, converted to UTC)
        timestamp_utc = dt_util.as_utc(local_midnight(date_obj.date()))

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
        _LOGGER.info("Imported %d daily statistics", len(statistics))
