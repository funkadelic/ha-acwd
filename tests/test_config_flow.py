"""Tests for config_flow.py - ACWD configuration flow."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import requests

from custom_components.acwd.config_flow import (
    CannotConnect,
    ConfigFlow,
    InvalidAuth,
    validate_input,
)

# -- Fixtures ----------------------------------------------------------------


USER_INPUT = {"username": "testuser", "password": "testpass"}  # NOSONAR


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

        with patch(
            "custom_components.acwd.config_flow.ACWDClient",
            return_value=mock_client,
        ):
            result = await validate_input(mock_hass, USER_INPUT)

        assert result["title"] == "ACWD - Test User"
        assert result["account_number"] == "12345"
        assert result["account_name"] == "Test User"

    async def test_validate_input_missing_account_number(self, mock_hass):
        """Verify CannotConnect raised when AccountNumber is missing from user_info."""
        mock_client = MagicMock()
        mock_client.login.return_value = True
        mock_client.user_info = {"Name": "Test User"}
        mock_client.logout.return_value = None

        with (
            patch(
                "custom_components.acwd.config_flow.ACWDClient",
                return_value=mock_client,
            ),
            pytest.raises(CannotConnect, match="Unable to retrieve account number"),
        ):
            await validate_input(mock_hass, USER_INPUT)

    async def test_validate_input_invalid_auth(self, mock_hass):
        """Verify failed login raises InvalidAuth."""
        mock_client = MagicMock()
        mock_client.login.return_value = False

        with (
            patch(
                "custom_components.acwd.config_flow.ACWDClient",
                return_value=mock_client,
            ),
            pytest.raises(InvalidAuth),
        ):
            await validate_input(mock_hass, USER_INPUT)


# -- ConfigFlow.async_step_user tests ----------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
class TestConfigFlowAsyncStepUser:
    """Tests for ConfigFlow.async_step_user."""

    @staticmethod
    def _make_flow(mock_hass):
        """Create a ConfigFlow with hass and a mutable context."""
        flow = ConfigFlow()
        flow.hass = mock_hass
        flow.context = {}
        return flow

    async def test_show_form(self, mock_hass):
        """Verify form is shown when no user input."""
        flow = self._make_flow(mock_hass)
        result = await flow.async_step_user(user_input=None)
        assert result["type"] == "form"
        assert result["step_id"] == "user"

    async def test_successful_login(self, mock_hass):
        """Verify create_entry on successful validation."""
        flow = self._make_flow(mock_hass)

        info = {
            "title": "ACWD - Test User",
            "account_number": "12345",
            "account_name": "Test User",
        }

        with (
            patch(
                "custom_components.acwd.config_flow.validate_input",
                new_callable=AsyncMock,
                return_value=info,
            ),
            patch.object(flow, "_abort_if_unique_id_configured"),
        ):
            result = await flow.async_step_user(user_input=USER_INPUT)

        assert result["type"] == "create_entry"
        assert result["title"] == "ACWD - Test User"
        assert result["data"] == USER_INPUT

    async def test_invalid_auth(self, mock_hass):
        """Verify invalid_auth error on InvalidAuth."""
        flow = self._make_flow(mock_hass)

        with patch(
            "custom_components.acwd.config_flow.validate_input",
            new_callable=AsyncMock,
            side_effect=InvalidAuth,
        ):
            result = await flow.async_step_user(user_input=USER_INPUT)

        assert result["type"] == "form"
        assert result["errors"] == {"base": "invalid_auth"}

    async def test_cannot_connect(self, mock_hass):
        """Verify cannot_connect error on CannotConnect."""
        flow = self._make_flow(mock_hass)

        with patch(
            "custom_components.acwd.config_flow.validate_input",
            new_callable=AsyncMock,
            side_effect=CannotConnect,
        ):
            result = await flow.async_step_user(user_input=USER_INPUT)

        assert result["type"] == "form"
        assert result["errors"] == {"base": "cannot_connect"}

    async def test_unknown_error(self, mock_hass):
        """Verify unknown error on generic Exception."""
        flow = self._make_flow(mock_hass)

        with patch(
            "custom_components.acwd.config_flow.validate_input",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            result = await flow.async_step_user(user_input=USER_INPUT)

        assert result["type"] == "form"
        assert result["errors"] == {"base": "unknown"}

    async def test_form_connection_timeout(self, mock_hass):
        """Verify cannot_connect error when requests.Timeout is raised."""
        flow = self._make_flow(mock_hass)

        with patch(
            "custom_components.acwd.config_flow.validate_input",
            new_callable=AsyncMock,
            side_effect=requests.Timeout("timed out"),
        ):
            result = await flow.async_step_user(user_input=USER_INPUT)

        assert result["type"] == "form"
        assert result["errors"] == {"base": "cannot_connect"}

    async def test_form_connection_error(self, mock_hass):
        """Verify cannot_connect error when requests.ConnectionError is raised."""
        flow = self._make_flow(mock_hass)

        with patch(
            "custom_components.acwd.config_flow.validate_input",
            new_callable=AsyncMock,
            side_effect=requests.ConnectionError("connection refused"),
        ):
            result = await flow.async_step_user(user_input=USER_INPUT)

        assert result["type"] == "form"
        assert result["errors"] == {"base": "cannot_connect"}
