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
# Shared helpers
# ---------------------------------------------------------------------------


def _assert_timeout(kwargs):
    """Assert that the caller passed timeout=HTTP_TIMEOUT."""
    from custom_components.acwd.const import HTTP_TIMEOUT
    actual = kwargs.get("timeout")
    assert actual == HTTP_TIMEOUT, f"Expected timeout={HTTP_TIMEOUT}, got timeout={actual}"


def _raising(error):
    """Return a side_effect that asserts timeout and raises *error*."""
    def _fn(*args, **kwargs):
        _assert_timeout(kwargs)
        raise error
    return _fn


def _returning(value):
    """Return a side_effect that asserts timeout and returns *value*."""
    def _fn(*args, **kwargs):
        _assert_timeout(kwargs)
        return value
    return _fn


def _make_client():
    """Return a fresh ACWDClient instance."""
    from custom_components.acwd.acwd_api import ACWDClient
    return ACWDClient("user@example.com", "secret")


def _make_logged_in_client(meter_cached=True):
    """Return a logged-in ACWDClient with optional pre-cached meter."""
    client = _make_client()
    client.logged_in = True
    client.csrf_token = "tok123"
    client._water_meter_number = "230057301" if meter_cached else None
    return client


def _mock_usage_page():
    """Return a mock response for the usage page GET."""
    resp = MagicMock()
    resp.status_code = 200
    resp.text = "<html></html>"
    return resp


def _mock_usage_json():
    """Return a mock response for LoadWaterUsage POST."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"d": '{"objUsageGenerationResultSetTwo": []}'}
    return resp


def _post_failing_first(error):
    """Return a post side_effect that asserts timeout, raises on first call, succeeds after."""
    usage_resp = _mock_usage_json()
    calls = {"n": 0}

    def _side_effect(*args, **kwargs):
        _assert_timeout(kwargs)
        calls["n"] += 1
        if calls["n"] == 1:
            raise error
        return usage_resp

    return _side_effect


from tests.helpers import make_mock_hass as _make_mock_hass
from tests.helpers import make_mock_entry as _make_mock_entry
from tests.helpers import make_mock_coordinator as _make_mock_coordinator


def _setup_service_handler_mocks():
    """Return (hass, entry, coordinator) wired together for service handler tests."""
    from custom_components.acwd import DOMAIN

    hass = _make_mock_hass()
    entry = _make_mock_entry()
    coordinator = _make_mock_coordinator(entry)
    hass.data[DOMAIN] = {entry.entry_id: coordinator}
    return hass, entry, coordinator


def _make_failing_client_patch(error):
    """Return a patch context manager for ACWDClient that fails on login."""
    mock_client = MagicMock()
    mock_client.login.side_effect = error
    mock_client.logout.return_value = None

    patcher = patch("custom_components.acwd.ACWDClient", return_value=mock_client)
    return patcher


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

    def test_login_raises_on_base_url_get_timeout(self):
        """Test 2: login() raises requests.Timeout when initial GET to base_url times out."""
        client = _make_client()

        with patch.object(client.session, "get", side_effect=_raising(requests.Timeout("timed out"))):
            with pytest.raises(requests.Timeout):
                client.login()

    def test_login_raises_on_validate_login_post_timeout(self):
        """Test 3: login() raises requests.Timeout when validateLogin POST times out."""
        client = _make_client()

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
            _assert_timeout(kwargs)
            call_count["n"] += 1
            if call_count["n"] == 1:
                return mock_update_response  # updateState
            raise requests.Timeout("validate login timed out")

        with patch.object(client.session, "get", side_effect=_returning(mock_get_response)):
            with patch.object(client.session, "post", side_effect=_post_side_effect):
                with pytest.raises(requests.Timeout):
                    client.login()

    def test_login_raises_on_connection_error(self):
        """login() raises requests.ConnectionError when network is unreachable."""
        client = _make_client()

        with patch.object(
            client.session, "get", side_effect=_raising(requests.ConnectionError("no route to host"))
        ):
            with pytest.raises(requests.ConnectionError):
                client.login()


class TestBindMultiMeterTimeout:
    """Test 4: BindMultiMeter timeout degrades gracefully — sets empty meter, logs warning."""

    def test_bind_meter_timeout_sets_empty_meter(self):
        """Test 4: Timeout on BindMultiMeter sets meter to '' and does not raise."""
        client = _make_logged_in_client(meter_cached=False)

        with patch.object(client.session, "get", side_effect=_returning(_mock_usage_page())):
            with patch.object(
                client.session, "post",
                side_effect=_post_failing_first(requests.Timeout("bind meter timed out")),
            ):
                client.get_usage_data(mode="B")

        assert client._water_meter_number == ""

    def test_bind_meter_timeout_logs_warning_with_url(self, caplog):
        """Test 4: BindMultiMeter timeout warning includes the bind_meter_url."""
        import logging

        client = _make_logged_in_client(meter_cached=False)

        with caplog.at_level(logging.WARNING):
            with patch.object(client.session, "get", side_effect=_returning(_mock_usage_page())):
                with patch.object(
                    client.session, "post",
                    side_effect=_post_failing_first(requests.Timeout("bind meter timed out")),
                ):
                    client.get_usage_data(mode="B")

        warning_messages = [
            r.message for r in caplog.records
            if r.levelname == "WARNING" and r.name == "custom_components.acwd.acwd_api"
        ]
        assert any("BindMultiMeter" in m for m in warning_messages), (
            f"Expected a warning mentioning BindMultiMeter, got: {warning_messages}"
        )


class TestLoadWaterUsageTimeoutPropagation:
    """Test 5: LoadWaterUsage POST timeout propagates (raises requests.Timeout)."""

    def test_load_water_usage_timeout_raises(self):
        """Test 5: Timeout on LoadWaterUsage POST propagates up (raises requests.Timeout)."""
        client = _make_logged_in_client(meter_cached=True)

        with patch.object(client.session, "get", side_effect=_returning(_mock_usage_page())):
            with patch.object(
                client.session, "post", side_effect=_raising(requests.Timeout("usage POST timed out"))
            ):
                with pytest.raises(requests.Timeout):
                    client.get_usage_data(mode="B")


class TestCsrfRefreshTimeoutNonFatal:
    """Test 5b: usage_page_url CSRF GET timeout logs warning and does NOT raise."""

    def test_csrf_refresh_timeout_does_not_raise(self):
        """Test 5b: Timeout on CSRF refresh GET does not raise — get_usage_data() continues."""
        client = _make_logged_in_client(meter_cached=True)

        with patch.object(
            client.session, "get", side_effect=requests.Timeout("csrf refresh timed out")
        ):
            with patch.object(client.session, "post", return_value=_mock_usage_json()) as mock_post:
                result = client.get_usage_data(mode="B")

        mock_post.assert_called_once()
        assert result == {"objUsageGenerationResultSetTwo": []}

    def test_csrf_refresh_timeout_logs_warning_with_url(self, caplog):
        """Test 5b: CSRF refresh timeout logs warning including the usage_page_url."""
        import logging

        client = _make_logged_in_client(meter_cached=True)

        with caplog.at_level(logging.WARNING):
            with patch.object(
                client.session, "get", side_effect=requests.Timeout("csrf refresh timed out")
            ):
                with patch.object(client.session, "post", return_value=_mock_usage_json()):
                    client.get_usage_data(mode="B")

        warning_messages = [
            r.message for r in caplog.records
            if r.levelname == "WARNING" and r.name == "custom_components.acwd.acwd_api"
        ]
        assert any("usages.aspx" in m for m in warning_messages), (
            f"Expected a warning mentioning usages.aspx URL, got: {warning_messages}"
        )


# ---------------------------------------------------------------------------
# Task 2: __init__.py translates network errors to HA exceptions
# ---------------------------------------------------------------------------


class TestCoordinatorNetworkErrors:
    """Test 6 & 9: _async_update_data() raises UpdateFailed on network errors."""

    def _make_coordinator_stub(self, hass, client):
        """Build a minimal namespace that satisfies _async_update_data's self requirements."""
        import types
        from custom_components.acwd import ACWDDataUpdateCoordinator

        stub = types.SimpleNamespace(hass=hass, client=client)
        stub._async_update_data = lambda: ACWDDataUpdateCoordinator._async_update_data(stub)
        return stub

    @pytest.mark.parametrize("error", [
        requests.Timeout("portal unreachable"),
        requests.ConnectionError("no route to host"),
    ], ids=["timeout", "connection_error"])
    async def test_network_error_raises_update_failed(self, error):
        """_async_update_data() raises UpdateFailed on network errors."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        hass = _make_mock_hass()
        mock_client = MagicMock()
        mock_client.login.side_effect = error

        stub = self._make_coordinator_stub(hass, mock_client)

        with pytest.raises(UpdateFailed) as exc_info:
            await stub._async_update_data()

        assert "Network error" in str(exc_info.value) or "ACWD" in str(exc_info.value)


class TestServiceHandlerNetworkErrors:
    """Test 7 & 8: Service handlers raise HomeAssistantError on network errors."""

    @pytest.mark.parametrize("handler_name,call_data", [
        ("handle_import_hourly", {"date": datetime.date.today() - datetime.timedelta(days=2), "granularity": "hourly"}),
        ("handle_import_daily", {"start_date": datetime.date(2025, 12, 1), "end_date": datetime.date(2025, 12, 5)}),
    ], ids=["hourly", "daily"])
    @pytest.mark.parametrize("error", [
        requests.Timeout("timed out"),
        requests.ConnectionError("no route to host"),
    ], ids=["timeout", "connection_error"])
    async def test_service_handler_network_error_raises_ha_error(self, handler_name, call_data, error):
        """Service handlers raise HomeAssistantError on network errors."""
        import custom_components.acwd as acwd_module
        from homeassistant.exceptions import HomeAssistantError

        hass, _, _ = _setup_service_handler_mocks()

        call = MagicMock()
        call.hass = hass
        call.data = call_data

        handler = getattr(acwd_module, handler_name)

        with _make_failing_client_patch(error):
            with pytest.raises(HomeAssistantError):
                await handler(call)
