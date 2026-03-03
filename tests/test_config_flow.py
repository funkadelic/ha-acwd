"""Tests for config_flow.py - ACWD configuration flow."""
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure custom_components.acwd package exists
if "custom_components" not in sys.modules:
    _custom_components = types.ModuleType("custom_components")
    _custom_components.__path__ = []
    sys.modules["custom_components"] = _custom_components

if "custom_components.acwd" not in sys.modules:
    _acwd_package = types.ModuleType("custom_components.acwd")
    _acwd_package.__path__ = []
    sys.modules["custom_components.acwd"] = _acwd_package

# Set up const module
_const_module = types.ModuleType("custom_components.acwd.const")
_const_module.DOMAIN = "acwd"
sys.modules["custom_components.acwd.const"] = _const_module

# Set up acwd_api module mock (avoid importing real requests-based client)
_api_module = types.ModuleType("custom_components.acwd.acwd_api")
_api_module.ACWDClient = MagicMock
sys.modules["custom_components.acwd.acwd_api"] = _api_module

# Import config_flow module via importlib
import importlib.util

_flow_spec = importlib.util.spec_from_file_location(
    "custom_components.acwd.config_flow",
    Path(__file__).parent.parent / "custom_components" / "acwd" / "config_flow.py",
)
_flow_module = importlib.util.module_from_spec(_flow_spec)
_flow_spec.loader.exec_module(_flow_module)
sys.modules["custom_components.acwd.config_flow"] = _flow_module
sys.modules["custom_components.acwd"].config_flow = _flow_module

# Extract classes
ConfigFlow = _flow_module.ConfigFlow
validate_input = _flow_module.validate_input
InvalidAuth = _flow_module.InvalidAuth
CannotConnect = _flow_module.CannotConnect


# -- Fixtures ----------------------------------------------------------------

@pytest.fixture
def mock_hass():
    """Create a mock HomeAssistant instance for config flow tests."""
    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock(side_effect=lambda func, *args: func(*args))
    return hass


USER_INPUT = {"username": "testuser", "password": "testpass"}


# -- validate_input tests ----------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
class TestValidateInput:
    """Tests for the validate_input function."""

    async def test_validate_input_success(self, mock_hass):
        """Verify successful login returns account info."""
        mock_client = MagicMock()
        mock_client.login.return_value = True
        mock_client.user_info = {"Name": "Test User", "AccountNumber": "12345"}
        mock_client.logout.return_value = None

        with patch.object(_flow_module, "ACWDClient", return_value=mock_client):
            result = await validate_input(mock_hass, USER_INPUT)

        assert result["title"] == "ACWD - Test User"
        assert result["account_number"] == "12345"
        assert result["account_name"] == "Test User"

    async def test_validate_input_invalid_auth(self, mock_hass):
        """Verify failed login raises InvalidAuth."""
        mock_client = MagicMock()
        mock_client.login.return_value = False

        with patch.object(_flow_module, "ACWDClient", return_value=mock_client):
            with pytest.raises(InvalidAuth):
                await validate_input(mock_hass, USER_INPUT)


# -- ConfigFlow.async_step_user tests ----------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
class TestConfigFlowAsyncStepUser:
    """Tests for ConfigFlow.async_step_user."""

    async def test_show_form(self, mock_hass):
        """Verify form is shown when no user input."""
        flow = ConfigFlow()
        flow.hass = mock_hass
        result = await flow.async_step_user(user_input=None)
        assert result["type"] == "form"
        assert result["step_id"] == "user"

    async def test_successful_login(self, mock_hass):
        """Verify create_entry on successful validation."""
        flow = ConfigFlow()
        flow.hass = mock_hass

        info = {
            "title": "ACWD - Test User",
            "account_number": "12345",
            "account_name": "Test User",
        }

        with patch.object(
            _flow_module, "validate_input", new_callable=AsyncMock, return_value=info
        ):
            result = await flow.async_step_user(user_input=USER_INPUT)

        assert result["type"] == "create_entry"
        assert result["title"] == "ACWD - Test User"
        assert result["data"] == USER_INPUT

    async def test_invalid_auth(self, mock_hass):
        """Verify invalid_auth error on InvalidAuth."""
        flow = ConfigFlow()
        flow.hass = mock_hass

        with patch.object(
            _flow_module, "validate_input", new_callable=AsyncMock, side_effect=InvalidAuth
        ):
            result = await flow.async_step_user(user_input=USER_INPUT)

        assert result["type"] == "form"
        assert result["errors"] == {"base": "invalid_auth"}

    async def test_cannot_connect(self, mock_hass):
        """Verify cannot_connect error on CannotConnect."""
        flow = ConfigFlow()
        flow.hass = mock_hass

        with patch.object(
            _flow_module, "validate_input", new_callable=AsyncMock, side_effect=CannotConnect
        ):
            result = await flow.async_step_user(user_input=USER_INPUT)

        assert result["type"] == "form"
        assert result["errors"] == {"base": "cannot_connect"}

    async def test_unknown_error(self, mock_hass):
        """Verify unknown error on generic Exception."""
        flow = ConfigFlow()
        flow.hass = mock_hass

        with patch.object(
            _flow_module, "validate_input", new_callable=AsyncMock, side_effect=RuntimeError("boom")
        ):
            result = await flow.async_step_user(user_input=USER_INPUT)

        assert result["type"] == "form"
        assert result["errors"] == {"base": "unknown"}
