"""Shared utility functions for the ACWD Water Usage integration."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any

from homeassistant.util import dt as dt_util

from .const import DATE_FORMAT_LONG, DATE_FORMAT_SLASH_MDY, KEY_D, TIME_FORMAT_12HR

_LOGGER = logging.getLogger(__name__)


def parse_api_response(result: dict, endpoint: str = "unknown") -> Any:
    """Parse an ASP.NET WebMethods response envelope and return the inner object.

    The ACWD portal wraps all API responses in a JSON object with a single 'd' key
    whose value is a JSON-encoded string. This helper extracts and parses that inner
    value, providing consistent error messages on failure.

    Args:
        result: The decoded JSON response dict from the API (must contain 'd' key).
        endpoint: API endpoint name used in error messages for easier debugging.

    Returns:
        The parsed Python object (dict, list, etc.) from result['d'].

    Raises:
        ValueError: If 'd' is absent or its value is not valid JSON.
    """
    if KEY_D not in result:
        raise ValueError(
            f"Unexpected API response from {endpoint}: missing '{KEY_D}' property"
        )
    raw = result[KEY_D]
    if not isinstance(raw, str):
        raise ValueError(
            f"Unexpected API response from {endpoint}: '{KEY_D}' is {type(raw).__name__}, expected str (got: {raw!r})"
        )
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        snippet = raw[:200]
        raise ValueError(
            f"Failed to parse API response from {endpoint}: {e} (got: {snippet!r})"
        ) from e


def local_midnight(d: date) -> datetime:
    """Return midnight of the given date as a timezone-aware datetime in HA's local timezone.

    This ensures consistent timezone-aware midnight calculations across the integration,
    preventing UTC-vs-local baseline bugs in statistics cumulative sums.
    """
    local_tz = dt_util.get_default_time_zone()
    return datetime.combine(d, datetime.min.time()).replace(tzinfo=local_tz)


def parse_date_mdy(date_str: str | None) -> datetime | None:
    """Parse a MM/DD/YYYY date string and return a datetime, or None on failure.

    Args:
        date_str: Date string in MM/DD/YYYY format (e.g. "01/15/2026"), or None.

    Returns:
        Parsed datetime on success, None if date_str is None or not a valid date.
    """
    if date_str is None:
        return None
    try:
        return datetime.strptime(date_str, DATE_FORMAT_SLASH_MDY)
    except (ValueError, TypeError):
        _LOGGER.warning("Could not parse date (MM/DD/YYYY): %r", date_str)
        return None


def parse_time_12hr(time_str: str | None) -> int | None:
    """Parse an H:MM AM/PM time string and return the hour (0-23), or None on failure.

    Args:
        time_str: Time string in 12-hour format (e.g. "1:00 AM", "12:00 PM"), or None.

    Returns:
        Hour as int (0-23) on success, None if time_str is None or not a valid time.
    """
    if time_str is None:
        return None
    try:
        return datetime.strptime(time_str, TIME_FORMAT_12HR).hour
    except (ValueError, TypeError):
        _LOGGER.warning("Could not parse time (H:MM AM/PM): %r", time_str)
        return None


def parse_date_long(date_str: str | None) -> datetime | None:
    """Parse a "Month D, YYYY" date string and return a datetime, or None on failure.

    Args:
        date_str: Date string in long format (e.g. "December 3, 2025"), or None.

    Returns:
        Parsed datetime on success, None if date_str is None or not a valid date.
    """
    if date_str is None:
        return None
    try:
        return datetime.strptime(date_str, DATE_FORMAT_LONG)
    except (ValueError, TypeError):
        _LOGGER.warning("Could not parse date (Month D, YYYY): %r", date_str)
        return None
