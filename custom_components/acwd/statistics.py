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


def _ensure_datetime(value: float | datetime | None) -> datetime | None:
    """Coerce a possible Unix timestamp to a timezone-aware datetime."""
    if value is None:
        return None
    if not isinstance(value, datetime):
        return datetime.fromtimestamp(value, tz=dt_util.UTC)
    return value


def _find_baseline_in_stats(
    stats: list[dict[str, Any]],
    target_date_start: datetime,
) -> float | None:
    """Search a list of statistic records for the latest sum before target_date_start."""
    _LOGGER.debug("Searching %d historical stats for baseline", len(stats))
    for i, stat in enumerate(stats):
        stat_time = _ensure_datetime(stat.get("start"))
        stat_sum = stat.get("sum") or 0

        _LOGGER.debug(
            "  Stat %d: time=%s, sum=%s, before_target=%s",
            i,
            stat_time,
            stat_sum,
            stat_time < target_date_start if stat_time else None,
        )

        if stat_time and stat_time < target_date_start:
            _LOGGER.debug("Found baseline sum %s from %s", stat_sum, stat_time)
            return stat_sum

    return None


async def _get_baseline_sum(
    hass: HomeAssistant,
    statistic_id: str,
    target_date_start: datetime,
    extended_lookback: int = 48,
) -> float:
    """Return the cumulative sum baseline from before target_date_start.

    Fetches the most recent statistic. If it is from the target date or later,
    performs an extended lookback (up to `extended_lookback` records) to find
    the last stat that precedes target_date_start.

    Returns 0.0 if no suitable baseline is found.
    """
    last_stats = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, statistic_id, True, {"sum"}
    )

    stats_list = last_stats.get(statistic_id, [])
    if not stats_list:
        return 0.0

    last_stat_time = _ensure_datetime(stats_list[0].get("start"))
    last_stat_sum = stats_list[0].get("sum") or 0

    _LOGGER.debug(
        "Last statistic: time=%s, sum=%s, target_date_start=%s",
        last_stat_time,
        last_stat_sum,
        target_date_start,
    )

    # Only use the last sum if it's from before the target date
    # Otherwise, we'd be adding today's values on top of today's partial sum
    if last_stat_time and last_stat_time < target_date_start:
        _LOGGER.debug(
            "Using last sum %s from %s as baseline", last_stat_sum, last_stat_time
        )
        return last_stat_sum

    # Last statistic is from target date, need to get sum from day before
    _LOGGER.debug(
        "Last statistic is from target date %s, fetching baseline from previous day",
        target_date_start.date(),
    )
    last_stats_extended = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, extended_lookback, statistic_id, True, {"sum"}
    )
    extended_list = last_stats_extended.get(statistic_id, [])
    if not extended_list:
        return 0.0

    result = _find_baseline_in_stats(extended_list, target_date_start)
    return result if result is not None else 0.0


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

    # Start cumulative sum from last known value before the target date
    last_sum = await _get_baseline_sum(hass, statistic_id, target_date_start)

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
        _LOGGER.info(
            "Imported %d hourly statistics for %s", len(statistics), date.date()
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

    # Start cumulative sum from last known value before the target date
    last_sum = await _get_baseline_sum(
        hass, statistic_id, target_date_start, extended_lookback=192
    )

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
        _LOGGER.info(
            "Imported %d 15-minute statistics for %s", len(statistics), date.date()
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
