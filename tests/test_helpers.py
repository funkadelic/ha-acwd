"""Tests for helpers.py — local_midnight() timezone-aware datetime utility.

Phase 01 introduced local_midnight() to replace duplicated 3-line timezone
patterns across the integration. These tests verify the function returns
correct timezone-aware midnight datetimes.
"""
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

# Add custom_components to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from custom_components.acwd.helpers import local_midnight


@pytest.mark.unit
class TestLocalMidnight:
    """Tests for local_midnight() utility function."""

    def test_returns_timezone_aware_datetime(self, pst_timezone):
        """local_midnight() must return a timezone-aware datetime (never naive)."""
        with patch(
            "homeassistant.util.dt.get_default_time_zone",
            return_value=pst_timezone,
        ):
            d = date(2025, 12, 10)
            result = local_midnight(d)

            assert result.tzinfo is not None

    def test_returns_midnight(self, pst_timezone):
        """Result is midnight: hour=0, minute=0, second=0, microsecond=0."""
        with patch(
            "homeassistant.util.dt.get_default_time_zone",
            return_value=pst_timezone,
        ):
            d = date(2025, 12, 10)
            result = local_midnight(d)

            assert result.hour == 0
            assert result.minute == 0
            assert result.second == 0
            assert result.microsecond == 0

    def test_preserves_date(self, pst_timezone):
        """Result date matches the input date."""
        with patch(
            "homeassistant.util.dt.get_default_time_zone",
            return_value=pst_timezone,
        ):
            d = date(2025, 12, 10)
            result = local_midnight(d)

            assert result.year == 2025
            assert result.month == 12
            assert result.day == 10

    def test_uses_ha_default_timezone_pst(self, pst_timezone):
        """Result uses HA's default timezone (PST in test fixtures)."""
        with patch(
            "homeassistant.util.dt.get_default_time_zone",
            return_value=pst_timezone,
        ):
            d = date(2025, 12, 10)
            result = local_midnight(d)

            assert result.tzinfo == pst_timezone

    def test_uses_ha_default_timezone_est(self, est_timezone):
        """Result uses HA's default timezone when set to EST."""
        with patch(
            "homeassistant.util.dt.get_default_time_zone",
            return_value=est_timezone,
        ):
            d = date(2025, 12, 10)
            result = local_midnight(d)

            assert result.tzinfo == est_timezone

    def test_pst_midnight_converts_to_correct_utc(self, pst_timezone):
        """Dec 10 00:00 PST converts to Dec 10 08:00 UTC."""
        with patch(
            "homeassistant.util.dt.get_default_time_zone",
            return_value=pst_timezone,
        ):
            d = date(2025, 12, 10)
            result = local_midnight(d)
            result_utc = result.astimezone(timezone.utc)

            assert result_utc == datetime(2025, 12, 10, 8, 0, 0, tzinfo=timezone.utc)


from custom_components.acwd.helpers import parse_api_response


@pytest.mark.unit
class TestParseApiResponse:
    """Tests for parse_api_response() helper function."""

    def test_parses_dict_response(self):
        """parse_api_response returns parsed dict when 'd' contains a JSON object."""
        result = parse_api_response({"d": '{"key": "value"}'})
        assert result == {"key": "value"}

    def test_parses_list_response(self):
        """parse_api_response returns parsed list when 'd' contains a JSON array."""
        result = parse_api_response({"d": '[{"STATUS": "1"}]'})
        assert result == [{"STATUS": "1"}]

    def test_missing_d_property_raises_value_error(self):
        """parse_api_response raises ValueError when 'd' key is absent."""
        with pytest.raises(ValueError) as exc_info:
            parse_api_response({})
        assert "missing 'd' property" in str(exc_info.value)

    def test_missing_d_includes_endpoint_in_error(self):
        """ValueError for missing 'd' includes the endpoint name."""
        with pytest.raises(ValueError) as exc_info:
            parse_api_response({}, endpoint="LoadWaterUsage")
        assert "LoadWaterUsage" in str(exc_info.value)

    def test_malformed_json_raises_value_error(self):
        """parse_api_response raises ValueError (not JSONDecodeError) for bad JSON."""
        with pytest.raises(ValueError):
            parse_api_response({"d": "not-json"})

    def test_malformed_json_includes_endpoint_in_error(self):
        """ValueError for malformed JSON includes the endpoint name."""
        with pytest.raises(ValueError) as exc_info:
            parse_api_response({"d": "not-json"}, endpoint="LoadWaterUsage")
        assert "LoadWaterUsage" in str(exc_info.value)

    def test_valid_response_with_endpoint_name_succeeds(self):
        """Endpoint name does not affect parsing of valid responses."""
        result = parse_api_response({"d": '{"k": "v"}'}, endpoint="LoadWaterUsage")
        assert result == {"k": "v"}

    def test_migrated_user_found_raises_value_error(self):
        """'Migrated User Found' string is not valid JSON — raises ValueError."""
        with pytest.raises(ValueError):
            parse_api_response({"d": "Migrated User Found"})
