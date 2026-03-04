"""Shared utility functions for the ACWD Water Usage integration."""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from homeassistant.util import dt as dt_util


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
    if "d" not in result:
        raise ValueError(
            f"Unexpected API response from {endpoint}: missing 'd' property"
        )
    raw = result["d"]
    if not isinstance(raw, str):
        raise ValueError(
            f"Unexpected API response from {endpoint}: 'd' is {type(raw).__name__}, expected str (got: {raw!r})"
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
