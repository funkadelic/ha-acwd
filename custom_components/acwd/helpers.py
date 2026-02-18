"""Shared utility functions for the ACWD Water Usage integration."""
from __future__ import annotations

from datetime import date, datetime

from homeassistant.util import dt as dt_util


def local_midnight(d: date) -> datetime:
    """Return midnight of the given date as a timezone-aware datetime in HA's local timezone.

    This ensures consistent timezone-aware midnight calculations across the integration,
    preventing UTC-vs-local baseline bugs in statistics cumulative sums.
    """
    local_tz = dt_util.get_default_time_zone()
    return datetime.combine(d, datetime.min.time()).replace(tzinfo=local_tz)
