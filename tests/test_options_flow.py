"""Tests for the options flow that sets the water rate."""

from unittest.mock import MagicMock

import pytest

from custom_components.acwd.config_flow import ConfigFlow
from tests.helpers import make_mock_entry


def _make_flow(mock_hass, options=None):
    """Return an options flow bound to a config entry with the given options."""
    entry = make_mock_entry()
    entry.options = options or {}
    mock_hass.config_entries.async_get_known_entry = MagicMock(return_value=entry)
    flow = ConfigFlow.async_get_options_flow(entry)
    flow.hass = mock_hass
    flow.handler = entry.entry_id
    return flow


@pytest.mark.unit
@pytest.mark.asyncio
class TestOptionsFlow:
    """Rate option behavior."""

    async def test_form_defaults_to_current_rate(self, mock_hass):
        """The form offers $5.38 when unset, otherwise the stored rate."""
        fresh = await _make_flow(mock_hass).async_step_init()
        stored = await _make_flow(mock_hass, {"rate_per_unit": 7.25}).async_step_init()

        assert fresh["data_schema"]({}) == {"rate_per_unit": 5.38}
        assert stored["data_schema"]({}) == {"rate_per_unit": 7.25}

    async def test_valid_rate_is_saved(self, mock_hass):
        """A positive rate is stored as a float."""
        result = await _make_flow(mock_hass).async_step_init({"rate_per_unit": "6.10"})

        assert result["type"] == "create_entry"
        assert result["data"] == {"rate_per_unit": 6.10}

    @pytest.mark.parametrize("rate", [0, -1.5, "abc", None])
    async def test_invalid_rate_is_rejected(self, mock_hass, rate):
        """Zero, negative, and non-numeric rates re-show the form with an error."""
        result = await _make_flow(mock_hass).async_step_init({"rate_per_unit": rate})

        assert result["type"] == "form"
        assert result["errors"] == {"rate_per_unit": "invalid_rate"}
