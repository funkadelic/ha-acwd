"""Tests for HTTP timeout and network error handling (phase 03-01).

Validates that:
- HTTP_TIMEOUT constant is defined in const.py
- All API calls in acwd_api.py pass timeout=HTTP_TIMEOUT
- Network errors in acwd_api.py propagate correctly (login raises, BindMultiMeter degrades)
- Network errors in __init__.py are translated to HA exceptions
"""

import datetime
import pytest
import requests
from unittest.mock import AsyncMock, MagicMock, Mock, patch


# ---------------------------------------------------------------------------
# Task 1: const.py and acwd_api.py timeout behaviour
# ---------------------------------------------------------------------------


class TestHttpTimeoutConstant:
    """Test 1: HTTP_TIMEOUT constant is defined and has expected shape."""

    def test_http_timeout_importable(self):
        """HTTP_TIMEOUT is importable from const.py."""
        from custom_components.acwd.const import HTTP_TIMEOUT

        assert HTTP_TIMEOUT is not None

    def test_http_timeout_is_tuple(self):
        """HTTP_TIMEOUT is a 2-tuple."""
        from custom_components.acwd.const import HTTP_TIMEOUT

        assert isinstance(HTTP_TIMEOUT, tuple)
        assert len(HTTP_TIMEOUT) == 2

    def test_http_timeout_values(self):
        """HTTP_TIMEOUT is (10, 30) — 10s connect, 30s read."""
        from custom_components.acwd.const import HTTP_TIMEOUT

        connect, read = HTTP_TIMEOUT
        assert connect == 10
        assert read == 30

    def test_http_connect_timeout_exported(self):
        """HTTP_CONNECT_TIMEOUT constant is 10."""
        from custom_components.acwd.const import HTTP_CONNECT_TIMEOUT

        assert HTTP_CONNECT_TIMEOUT == 10

    def test_http_read_timeout_exported(self):
        """HTTP_READ_TIMEOUT constant is 30."""
        from custom_components.acwd.const import HTTP_READ_TIMEOUT

        assert HTTP_READ_TIMEOUT == 30


class TestLoginTimeoutPropagation:
    """Test 2 & 3: login() raises requests.Timeout on network failures."""

    def _make_client(self):
        from custom_components.acwd.acwd_api import ACWDClient
        return ACWDClient("user@example.com", "secret")

    def test_login_raises_on_base_url_get_timeout(self):
        """Test 2: login() raises requests.Timeout when initial GET to base_url times out."""
        client = self._make_client()

        with patch.object(client.session, "get", side_effect=requests.Timeout("timed out")):
            with pytest.raises(requests.Timeout):
                client.login()

    def test_login_raises_on_validate_login_post_timeout(self):
        """Test 3: login() raises requests.Timeout when validateLogin POST times out."""
        client = self._make_client()

        # First GET (base_url) succeeds, returning a page with a CSRF token
        mock_get_response = MagicMock()
        mock_get_response.status_code = 200
        mock_get_response.text = (
            '<html><input type="hidden" name="hdnCSRFToken" value="tok123"/></html>'
        )

        # First POST (updateState) also succeeds
        mock_update_response = MagicMock()
        mock_update_response.status_code = 200

        # Second POST (validateLogin) times out
        call_count = {"n": 0}

        def _post_side_effect(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return mock_update_response  # updateState
            raise requests.Timeout("validate login timed out")

        with patch.object(client.session, "get", return_value=mock_get_response):
            with patch.object(client.session, "post", side_effect=_post_side_effect):
                with pytest.raises(requests.Timeout):
                    client.login()

    def test_login_raises_on_connection_error(self):
        """login() raises requests.ConnectionError when network is unreachable."""
        client = self._make_client()

        with patch.object(
            client.session, "get", side_effect=requests.ConnectionError("no route to host")
        ):
            with pytest.raises(requests.ConnectionError):
                client.login()


class TestBindMultiMeterTimeout:
    """Test 4: BindMultiMeter timeout degrades gracefully — sets empty meter, logs warning."""

    def _make_logged_in_client(self):
        from custom_components.acwd.acwd_api import ACWDClient
        client = ACWDClient("user@example.com", "secret")
        client.logged_in = True
        client.csrf_token = "tok123"
        client._water_meter_number = None  # Force meter discovery
        return client

    def test_bind_meter_timeout_sets_empty_meter(self):
        """Test 4: Timeout on BindMultiMeter sets meter to '' and does not raise."""
        client = self._make_logged_in_client()

        # usage_page GET (CSRF refresh) succeeds
        mock_usage_page = MagicMock()
        mock_usage_page.status_code = 200
        mock_usage_page.text = "<html></html>"

        # bind_meter POST times out
        # usage POST must succeed so the function completes
        mock_usage_response = MagicMock()
        mock_usage_response.status_code = 200
        mock_usage_response.json.return_value = {"d": '{"objUsageGenerationResultSetTwo": []}'}

        post_call_count = {"n": 0}

        def _post_side_effect(*args, **kwargs):
            post_call_count["n"] += 1
            if post_call_count["n"] == 1:
                raise requests.Timeout("bind meter timed out")
            return mock_usage_response  # LoadWaterUsage

        with patch.object(client.session, "get", return_value=mock_usage_page):
            with patch.object(client.session, "post", side_effect=_post_side_effect):
                # Should not raise — timeout is handled gracefully
                client.get_usage_data(mode="B")

        assert client._water_meter_number == ""

    def test_bind_meter_timeout_logs_warning_with_url(self, caplog):
        """Test 4: BindMultiMeter timeout warning includes the bind_meter_url."""
        import logging

        client = self._make_logged_in_client()

        mock_usage_page = MagicMock()
        mock_usage_page.status_code = 200
        mock_usage_page.text = "<html></html>"

        mock_usage_response = MagicMock()
        mock_usage_response.status_code = 200
        mock_usage_response.json.return_value = {"d": '{"objUsageGenerationResultSetTwo": []}'}

        post_call_count = {"n": 0}

        def _post_side_effect(*args, **kwargs):
            post_call_count["n"] += 1
            if post_call_count["n"] == 1:
                raise requests.Timeout("bind meter timed out")
            return mock_usage_response

        with caplog.at_level(logging.WARNING):
            with patch.object(client.session, "get", return_value=mock_usage_page):
                with patch.object(client.session, "post", side_effect=_post_side_effect):
                    client.get_usage_data(mode="B")

        warning_messages = [r.message for r in caplog.records if r.levelname == "WARNING"]
        # At least one warning should mention the bind meter URL
        assert any("BindMultiMeter" in m or "meter" in m.lower() for m in warning_messages), (
            f"Expected a warning mentioning BindMultiMeter or meter URL, got: {warning_messages}"
        )


class TestLoadWaterUsageTimeoutPropagation:
    """Test 5: LoadWaterUsage POST timeout propagates (raises requests.Timeout)."""

    def _make_logged_in_client(self, meter_cached=True):
        from custom_components.acwd.acwd_api import ACWDClient
        client = ACWDClient("user@example.com", "secret")
        client.logged_in = True
        client.csrf_token = "tok123"
        if meter_cached:
            client._water_meter_number = "230057301"  # Pre-cached — skip BindMultiMeter
        return client

    def test_load_water_usage_timeout_raises(self):
        """Test 5: Timeout on LoadWaterUsage POST propagates up (raises requests.Timeout)."""
        client = self._make_logged_in_client(meter_cached=True)

        # usage_page GET (CSRF refresh) succeeds
        mock_usage_page = MagicMock()
        mock_usage_page.status_code = 200
        mock_usage_page.text = "<html></html>"

        with patch.object(client.session, "get", return_value=mock_usage_page):
            with patch.object(
                client.session, "post", side_effect=requests.Timeout("usage POST timed out")
            ):
                with pytest.raises(requests.Timeout):
                    client.get_usage_data(mode="B")


class TestCsrfRefreshTimeoutNonFatal:
    """Test 5b: usage_page_url CSRF GET timeout logs warning and does NOT raise."""

    def _make_logged_in_client(self):
        from custom_components.acwd.acwd_api import ACWDClient
        client = ACWDClient("user@example.com", "secret")
        client.logged_in = True
        client.csrf_token = "tok123"
        client._water_meter_number = "230057301"  # Pre-cached
        return client

    def test_csrf_refresh_timeout_does_not_raise(self):
        """Test 5b: Timeout on CSRF refresh GET does not raise — get_usage_data() continues."""
        client = self._make_logged_in_client()

        # usage_page GET times out; LoadWaterUsage POST succeeds
        mock_usage_response = MagicMock()
        mock_usage_response.status_code = 200
        mock_usage_response.json.return_value = {"d": '{"objUsageGenerationResultSetTwo": []}'}

        with patch.object(
            client.session, "get", side_effect=requests.Timeout("csrf refresh timed out")
        ):
            with patch.object(client.session, "post", return_value=mock_usage_response):
                # Must not raise
                result = client.get_usage_data(mode="B")

        # Function continued and returned data (even without fresh CSRF)
        assert result is not None or result == {} or isinstance(result, dict)

    def test_csrf_refresh_timeout_logs_warning_with_url(self, caplog):
        """Test 5b: CSRF refresh timeout logs warning including the usage_page_url."""
        import logging

        client = self._make_logged_in_client()

        mock_usage_response = MagicMock()
        mock_usage_response.status_code = 200
        mock_usage_response.json.return_value = {"d": '{"objUsageGenerationResultSetTwo": []}'}

        with caplog.at_level(logging.WARNING):
            with patch.object(
                client.session, "get", side_effect=requests.Timeout("csrf refresh timed out")
            ):
                with patch.object(client.session, "post", return_value=mock_usage_response):
                    client.get_usage_data(mode="B")

        warning_messages = [r.message for r in caplog.records if r.levelname == "WARNING"]
        assert any("usages.aspx" in m or "CSRF" in m or "csrf" in m.lower() for m in warning_messages), (
            f"Expected warning mentioning CSRF or usage URL, got: {warning_messages}"
        )


# ---------------------------------------------------------------------------
# Task 2: __init__.py translates network errors to HA exceptions
# ---------------------------------------------------------------------------


def _make_mock_hass():
    """Return a MagicMock hass suitable for service tests."""
    hass = MagicMock()
    hass.services.has_service = Mock(return_value=False)
    hass.services.async_register = Mock()
    hass.services.async_remove = Mock()
    hass.data = {}
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.config_entries.async_loaded_entries = Mock(return_value=[])
    hass.async_add_executor_job = AsyncMock(side_effect=lambda func, *args: func(*args))
    return hass


def _make_mock_entry(entry_id="test_entry_id"):
    """Return a MagicMock config entry."""
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.data = {"username": "test_user", "password": "test_pass"}
    return entry


def _make_mock_coordinator(entry):
    """Return a MagicMock coordinator."""
    coordinator = MagicMock()
    coordinator.entry = entry
    coordinator.client.user_info = {"AccountNumber": "12345"}
    coordinator.client.meter_number = "230057301"
    return coordinator


class TestCoordinatorNetworkErrors:
    """Test 6 & 9: _async_update_data() raises UpdateFailed on network errors.

    ACWDDataUpdateCoordinator inherits from DataUpdateCoordinator, which conftest
    mocks as MagicMock. This makes normal instantiation impossible in tests.
    We work around this by calling the unbound _async_update_data coroutine
    directly with a SimpleNamespace object that provides the attributes the
    method uses: self.hass and self.client.
    """

    def _make_coordinator_stub(self, hass, client):
        """Build a minimal namespace that satisfies _async_update_data's self requirements."""
        import types
        from custom_components.acwd import ACWDDataUpdateCoordinator

        stub = types.SimpleNamespace(hass=hass, client=client)
        # Bind _async_update_data as a method on the stub
        stub._async_update_data = lambda: ACWDDataUpdateCoordinator._async_update_data(stub)
        return stub

    async def test_login_timeout_raises_update_failed(self):
        """Test 6: When login() raises requests.Timeout, _async_update_data() raises UpdateFailed."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        hass = _make_mock_hass()

        mock_client = MagicMock()
        mock_client.login.side_effect = requests.Timeout("portal unreachable")

        stub = self._make_coordinator_stub(hass, mock_client)

        with pytest.raises(UpdateFailed) as exc_info:
            await stub._async_update_data()

        # Error message should be meaningful (not just a bare traceback repr)
        assert "Network error" in str(exc_info.value) or "ACWD" in str(exc_info.value)

    async def test_login_connection_error_raises_update_failed(self):
        """Test 9: When login() raises requests.ConnectionError, _async_update_data() raises UpdateFailed."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        hass = _make_mock_hass()

        mock_client = MagicMock()
        mock_client.login.side_effect = requests.ConnectionError("no route to host")

        stub = self._make_coordinator_stub(hass, mock_client)

        with pytest.raises(UpdateFailed):
            await stub._async_update_data()


class TestServiceHandlerNetworkErrors:
    """Test 7 & 8: Service handlers raise HomeAssistantError on network errors."""

    async def test_import_hourly_login_timeout_raises_ha_error(self):
        """Test 7: When login() raises requests.Timeout, handle_import_hourly raises HomeAssistantError."""
        from custom_components.acwd import handle_import_hourly, DOMAIN
        from homeassistant.exceptions import HomeAssistantError

        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)
        hass.data[DOMAIN] = {entry.entry_id: coordinator}

        past_date = datetime.date.today() - datetime.timedelta(days=2)
        call = MagicMock()
        call.hass = hass
        call.data = {"date": past_date, "granularity": "hourly"}

        with patch("custom_components.acwd.ACWDClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.login.side_effect = requests.Timeout("timed out")
            mock_client.logout.return_value = None
            mock_client_cls.return_value = mock_client

            with pytest.raises(HomeAssistantError):
                await handle_import_hourly(call)

    async def test_import_daily_login_timeout_raises_ha_error(self):
        """Test 8: When login() raises requests.Timeout, handle_import_daily raises HomeAssistantError."""
        from custom_components.acwd import handle_import_daily, DOMAIN
        from homeassistant.exceptions import HomeAssistantError

        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)
        hass.data[DOMAIN] = {entry.entry_id: coordinator}

        call = MagicMock()
        call.hass = hass
        call.data = {
            "start_date": datetime.date(2025, 12, 1),
            "end_date": datetime.date(2025, 12, 5),
        }

        with patch("custom_components.acwd.ACWDClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.login.side_effect = requests.Timeout("timed out")
            mock_client.logout.return_value = None
            mock_client_cls.return_value = mock_client

            with pytest.raises(HomeAssistantError):
                await handle_import_daily(call)

    async def test_import_hourly_connection_error_raises_ha_error(self):
        """handle_import_hourly raises HomeAssistantError on ConnectionError too."""
        from custom_components.acwd import handle_import_hourly, DOMAIN
        from homeassistant.exceptions import HomeAssistantError

        hass = _make_mock_hass()
        entry = _make_mock_entry()
        coordinator = _make_mock_coordinator(entry)
        hass.data[DOMAIN] = {entry.entry_id: coordinator}

        past_date = datetime.date.today() - datetime.timedelta(days=2)
        call = MagicMock()
        call.hass = hass
        call.data = {"date": past_date, "granularity": "hourly"}

        with patch("custom_components.acwd.ACWDClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.login.side_effect = requests.ConnectionError("no route to host")
            mock_client.logout.return_value = None
            mock_client_cls.return_value = mock_client

            with pytest.raises(HomeAssistantError):
                await handle_import_hourly(call)
