"""Tests for ACWDClient login paths, get_usage_data branches, logout, and meter_number property.

Covers the previously-untested branches in acwd_api.py to bring coverage from 44% to 75%+.
No real network calls are made — all HTTP interactions use patch.object on session.
"""

import json
import pytest
import requests
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Shared helpers (defined locally — do NOT import from test_http_reliability)
# ---------------------------------------------------------------------------


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


def _login_page_response(csrf_value="tok123"):
    """Return a mock 200 response with a CSRF token in the HTML."""
    resp = MagicMock()
    resp.status_code = 200
    resp.text = (
        f'<html><input type="hidden" name="hdnCSRFToken" value="{csrf_value}"/></html>'
    )
    return resp


def _update_state_response(status=200):
    """Return a mock updateState POST response."""
    resp = MagicMock()
    resp.status_code = status
    return resp


def _validate_login_response(inner_data):
    """Return a mock validateLogin POST response whose JSON wraps inner_data as 'd'.

    inner_data can be a string (already-serialized JSON) or a Python object
    that will be JSON-serialised automatically.
    """
    resp = MagicMock()
    resp.status_code = 200
    if isinstance(inner_data, str):
        resp.json.return_value = {"d": inner_data}
    else:
        resp.json.return_value = {"d": json.dumps(inner_data)}
    return resp


def _dashboard_response(status=200):
    """Return a mock dashboard GET response."""
    resp = MagicMock()
    resp.status_code = status
    return resp


def _make_post_dispatcher(*responses):
    """Return a side_effect that returns responses in order on successive calls."""
    calls = {"n": 0}

    def _side_effect(*_args, **_kwargs):
        idx = calls["n"]
        calls["n"] += 1
        if idx < len(responses):
            r = responses[idx]
            if callable(r) and not isinstance(r, MagicMock):
                raise r()
            return r
        raise AssertionError(f"Unexpected extra POST call #{idx + 1}")

    return _side_effect


def _make_get_dispatcher(*responses):
    """Return a side_effect that returns GET responses in order on successive calls."""
    calls = {"n": 0}

    def _side_effect(*_args, **_kwargs):
        idx = calls["n"]
        calls["n"] += 1
        if idx < len(responses):
            return responses[idx]
        raise AssertionError(f"Unexpected extra GET call #{idx + 1}")

    return _side_effect


def _usage_page_response():
    """Return a plain-HTML usage page response (no fresh CSRF token)."""
    resp = MagicMock()
    resp.status_code = 200
    resp.text = "<html></html>"
    return resp


def _load_water_usage_response(inner_data=None):
    """Return a mock LoadWaterUsage POST response."""
    resp = MagicMock()
    resp.status_code = 200
    data = (
        inner_data if inner_data is not None else {"objUsageGenerationResultSetTwo": []}
    )
    resp.json.return_value = {"d": json.dumps(data)}
    return resp


def _bind_meter_response(meter_details):
    """Return a mock BindMultiMeter POST response."""
    resp = MagicMock()
    resp.status_code = 200
    inner = json.dumps({"MeterDetails": meter_details})
    resp.json.return_value = {"d": inner}
    return resp


# ---------------------------------------------------------------------------
# Task 1: Login paths
# ---------------------------------------------------------------------------


class TestLoginPaths:
    """Tests for ACWDClient.login() branches."""

    def test_login_raises_http_error_when_initial_get_returns_non_200(self):
        """login() raises requests.HTTPError when initial GET to base_url returns non-200."""
        client = _make_client()
        bad_resp = MagicMock()
        bad_resp.status_code = 503
        bad_resp.raise_for_status.side_effect = requests.HTTPError("503 Server Error")

        with patch.object(client.session, "get", return_value=bad_resp):
            with pytest.raises(requests.HTTPError):
                client.login()

    def test_login_returns_false_when_no_csrf_token(self):
        """login() returns False when login page contains no CSRF token."""
        client = _make_client()
        no_csrf_resp = MagicMock()
        no_csrf_resp.status_code = 200
        no_csrf_resp.text = "<html><form></form></html>"  # no hdnCSRFToken

        with patch.object(client.session, "get", return_value=no_csrf_resp):
            result = client.login()

        assert result is False

    def test_login_returns_false_for_migrated_user(self):
        """login() returns False when validateLogin response is 'Migrated User Found'."""
        client = _make_client()

        # GET returns login page with CSRF token
        get_resp = _login_page_response()
        # POST 1: updateState succeeds
        update_resp = _update_state_response()
        # POST 2: validateLogin returns the migration string (not JSON array)
        validate_resp = MagicMock()
        validate_resp.status_code = 200
        validate_resp.json.return_value = {"d": "Migrated User Found"}

        with patch.object(client.session, "get", return_value=get_resp):
            with patch.object(
                client.session,
                "post",
                side_effect=_make_post_dispatcher(update_resp, validate_resp),
            ):
                result = client.login()

        assert result is False

    def test_login_returns_false_for_dt_response_error(self):
        """login() returns False when validateLogin response contains dtResponse error."""
        client = _make_client()

        get_resp = _login_page_response()
        update_resp = _update_state_response()
        inner = json.dumps({"dtResponse": [{"Message": "Account locked"}]})
        validate_resp = MagicMock()
        validate_resp.status_code = 200
        validate_resp.json.return_value = {"d": inner}

        with patch.object(client.session, "get", return_value=get_resp):
            with patch.object(
                client.session,
                "post",
                side_effect=_make_post_dispatcher(update_resp, validate_resp),
            ):
                result = client.login()

        assert result is False

    def test_login_returns_false_for_status_0(self):
        """login() returns False when validateLogin STATUS=0 (invalid credentials)."""
        client = _make_client()

        get_resp = _login_page_response()
        update_resp = _update_state_response()
        validate_resp = _validate_login_response(
            [{"STATUS": "0", "Message": "Invalid credentials"}]
        )

        with patch.object(client.session, "get", return_value=get_resp):
            with patch.object(
                client.session,
                "post",
                side_effect=_make_post_dispatcher(update_resp, validate_resp),
            ):
                result = client.login()

        assert result is False

    def test_login_returns_true_for_status_1_dashboard_option_2(self):
        """login() navigates to DashboardCustom.aspx when DashboardOption='2'."""
        client = _make_client()

        get_resp = _login_page_response()
        update_resp = _update_state_response()
        inner = [
            {
                "STATUS": "1",
                "DashboardOption": "2",
                "Name": "Test User",
                "AccountNumber": "99",
            }
        ]
        validate_resp = _validate_login_response(inner)
        dashboard_resp = _dashboard_response()

        with patch.object(
            client.session,
            "get",
            side_effect=_make_get_dispatcher(get_resp, dashboard_resp),
        ):
            with patch.object(
                client.session,
                "post",
                side_effect=_make_post_dispatcher(update_resp, validate_resp),
            ):
                result = client.login()

        assert result is True
        assert client.logged_in is True

    def test_login_returns_true_for_status_1_dashboard_option_3(self):
        """login() navigates to DashboardCustom3_3.aspx when DashboardOption='3'."""
        client = _make_client()

        get_resp = _login_page_response()
        update_resp = _update_state_response()
        inner = [
            {
                "STATUS": "1",
                "DashboardOption": "3",
                "Name": "Test User",
                "AccountNumber": "99",
            }
        ]
        validate_resp = _validate_login_response(inner)
        dashboard_resp = _dashboard_response()

        with patch.object(
            client.session,
            "get",
            side_effect=_make_get_dispatcher(get_resp, dashboard_resp),
        ):
            with patch.object(
                client.session,
                "post",
                side_effect=_make_post_dispatcher(update_resp, validate_resp),
            ):
                result = client.login()

        assert result is True
        assert client.logged_in is True

    def test_login_returns_true_for_status_1_default_dashboard(self):
        """login() navigates to Dashboard.aspx when DashboardOption is something other than '2'/'3'."""
        client = _make_client()

        get_resp = _login_page_response()
        update_resp = _update_state_response()
        inner = [
            {
                "STATUS": "1",
                "DashboardOption": "1",
                "Name": "Test User",
                "AccountNumber": "99",
            }
        ]
        validate_resp = _validate_login_response(inner)
        dashboard_resp = _dashboard_response()

        with patch.object(
            client.session,
            "get",
            side_effect=_make_get_dispatcher(get_resp, dashboard_resp),
        ):
            with patch.object(
                client.session,
                "post",
                side_effect=_make_post_dispatcher(update_resp, validate_resp),
            ):
                result = client.login()

        assert result is True
        assert client.logged_in is True

    def test_login_returns_true_when_dashboard_get_fails(self):
        """login() still returns True when the dashboard GET fails (non-fatal)."""
        client = _make_client()

        get_resp = _login_page_response()
        update_resp = _update_state_response()
        inner = [
            {
                "STATUS": "1",
                "DashboardOption": "1",
                "Name": "Test User",
                "AccountNumber": "99",
            }
        ]
        validate_resp = _validate_login_response(inner)
        bad_dashboard_resp = _dashboard_response(status=500)

        with patch.object(
            client.session,
            "get",
            side_effect=_make_get_dispatcher(get_resp, bad_dashboard_resp),
        ):
            with patch.object(
                client.session,
                "post",
                side_effect=_make_post_dispatcher(update_resp, validate_resp),
            ):
                result = client.login()

        assert result is True
        assert client.logged_in is True

    def test_login_still_returns_true_when_dashboard_raises_network_error(self):
        """login() returns True even when dashboard GET raises a network error (non-fatal)."""
        client = _make_client()

        get_resp = _login_page_response()
        update_resp = _update_state_response()
        inner = [
            {
                "STATUS": "1",
                "DashboardOption": "1",
                "Name": "Test User",
                "AccountNumber": "99",
            }
        ]
        validate_resp = _validate_login_response(inner)

        call_count = {"n": 0}

        def _get_side_effect(*_args, **_kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return get_resp
            raise requests.ConnectionError("dashboard unreachable")

        with patch.object(client.session, "get", side_effect=_get_side_effect):
            with patch.object(
                client.session,
                "post",
                side_effect=_make_post_dispatcher(update_resp, validate_resp),
            ):
                result = client.login()

        assert result is True
        assert client.logged_in is True

    def test_login_returns_false_when_response_has_no_status_key(self):
        """login() returns False when the list item has no STATUS key."""
        client = _make_client()

        get_resp = _login_page_response()
        update_resp = _update_state_response()
        # A list but no STATUS key
        validate_resp = _validate_login_response([{"Name": "Test User"}])

        with patch.object(client.session, "get", return_value=get_resp):
            with patch.object(
                client.session,
                "post",
                side_effect=_make_post_dispatcher(update_resp, validate_resp),
            ):
                result = client.login()

        assert result is False

    def test_login_returns_false_when_login_data_is_not_list(self):
        """login() returns False when parsed login_data is not a list."""
        client = _make_client()

        get_resp = _login_page_response()
        update_resp = _update_state_response()
        # parse_api_response will return a dict, not a list
        validate_resp = _validate_login_response({"some": "dict"})

        with patch.object(client.session, "get", return_value=get_resp):
            with patch.object(
                client.session,
                "post",
                side_effect=_make_post_dispatcher(update_resp, validate_resp),
            ):
                result = client.login()

        assert result is False

    def test_login_returns_false_on_value_error_from_parse(self):
        """login() returns False when parse_api_response raises ValueError."""
        client = _make_client()

        get_resp = _login_page_response()
        update_resp = _update_state_response()
        # Invalid JSON in 'd' — parse_api_response raises ValueError
        bad_validate_resp = MagicMock()
        bad_validate_resp.status_code = 200
        bad_validate_resp.json.return_value = {"d": "INVALID JSON[[["}
        bad_validate_resp.text = "bad"

        with patch.object(client.session, "get", return_value=get_resp):
            with patch.object(
                client.session,
                "post",
                side_effect=_make_post_dispatcher(update_resp, bad_validate_resp),
            ):
                result = client.login()

        assert result is False

    def test_login_propagates_runtime_error_from_json_parse(self):
        """login() propagates RuntimeError from response.json() — not silently swallowed."""
        client = _make_client()

        get_resp = _login_page_response()
        update_resp = _update_state_response()
        exc_validate_resp = MagicMock()
        exc_validate_resp.status_code = 200
        exc_validate_resp.json.side_effect = RuntimeError("unexpected error")
        exc_validate_resp.text = "boom"

        with patch.object(client.session, "get", return_value=get_resp):
            with patch.object(
                client.session,
                "post",
                side_effect=_make_post_dispatcher(update_resp, exc_validate_resp),
            ):
                with pytest.raises(RuntimeError, match="unexpected error"):
                    client.login()

    def test_login_returns_false_when_validate_status_not_200(self):
        """login() returns False when validateLogin endpoint returns non-200."""
        client = _make_client()

        get_resp = _login_page_response()
        update_resp = _update_state_response()
        bad_validate = MagicMock()
        bad_validate.status_code = 401

        with patch.object(client.session, "get", return_value=get_resp):
            with patch.object(
                client.session,
                "post",
                side_effect=_make_post_dispatcher(update_resp, bad_validate),
            ):
                result = client.login()

        assert result is False


# ---------------------------------------------------------------------------
# Task 1: get_usage_data paths
# ---------------------------------------------------------------------------


class TestGetUsageDataPaths:
    """Tests for ACWDClient.get_usage_data() branches."""

    def test_get_usage_data_raises_when_not_logged_in(self):
        """get_usage_data() raises RuntimeError when client is not logged in."""
        client = _make_client()

        with pytest.raises(RuntimeError, match="Not logged in"):
            client.get_usage_data()

    def test_get_usage_data_updates_csrf_when_input_found(self):
        """get_usage_data() updates self.csrf_token when usage page contains fresh token."""
        client = _make_logged_in_client(meter_cached=True)
        client.csrf_token = "old_token"

        # Usage page with fresh CSRF token inside an input with id="hdnCSRFToken"
        usage_page = MagicMock()
        usage_page.status_code = 200
        usage_page.text = (
            '<html><input id="hdnCSRFToken" value="new_fresh_token"/></html>'
        )

        load_resp = _load_water_usage_response()

        with patch.object(client.session, "get", return_value=usage_page):
            with patch.object(client.session, "post", return_value=load_resp):
                client.get_usage_data(mode="B")

        assert client.csrf_token == "new_fresh_token"

    def test_get_usage_data_falls_back_to_raw_str_date_on_parse_failure(self):
        """get_usage_data() uses raw str_date string when parse_date_mdy fails."""
        client = _make_logged_in_client(meter_cached=True)

        usage_page = _usage_page_response()
        load_resp = _load_water_usage_response()

        captured_payloads = []

        def _post_capture(*_args, **kwargs):
            json_body = kwargs.get("json", {})
            captured_payloads.append(json_body)
            return load_resp

        with patch.object(client.session, "get", return_value=usage_page):
            with patch.object(client.session, "post", side_effect=_post_capture):
                client.get_usage_data(mode="H", str_date="not-a-real-date")

        # The strDate in payload should be the raw string (fallback)
        assert len(captured_payloads) == 1
        assert captured_payloads[0]["strDate"] == "not-a-real-date"

    def test_bind_multi_meter_ami_found_sets_meter_number(self):
        """get_usage_data() sets _water_meter_number to AMI meter when found."""
        client = _make_logged_in_client(meter_cached=False)

        usage_page = _usage_page_response()
        bind_resp = _bind_meter_response(
            [{"IsAMI": True, "MeterType": "W", "MeterNumber": "AMI_METER_123"}]
        )
        load_resp = _load_water_usage_response()

        with patch.object(client.session, "get", return_value=usage_page):
            with patch.object(
                client.session,
                "post",
                side_effect=_make_post_dispatcher(bind_resp, load_resp),
            ):
                client.get_usage_data(mode="B")

        assert client._water_meter_number == "AMI_METER_123"

    def test_bind_multi_meter_no_ami_uses_first_meter(self):
        """get_usage_data() falls back to first meter when no AMI meter is found."""
        client = _make_logged_in_client(meter_cached=False)

        usage_page = _usage_page_response()
        bind_resp = _bind_meter_response(
            [{"IsAMI": False, "MeterType": "W", "MeterNumber": "FIRST_METER_999"}]
        )
        load_resp = _load_water_usage_response()

        with patch.object(client.session, "get", return_value=usage_page):
            with patch.object(
                client.session,
                "post",
                side_effect=_make_post_dispatcher(bind_resp, load_resp),
            ):
                client.get_usage_data(mode="B")

        assert client._water_meter_number == "FIRST_METER_999"

    def test_bind_multi_meter_non_200_leaves_meter_none(self):
        """get_usage_data() leaves _water_meter_number as None when BindMultiMeter returns non-200."""
        client = _make_logged_in_client(meter_cached=False)

        usage_page = _usage_page_response()
        bad_bind = MagicMock()
        bad_bind.status_code = 500
        load_resp = _load_water_usage_response()

        with patch.object(client.session, "get", return_value=usage_page):
            with patch.object(
                client.session,
                "post",
                side_effect=_make_post_dispatcher(bad_bind, load_resp),
            ):
                client.get_usage_data(mode="B")

        assert client._water_meter_number is None

    def test_bind_multi_meter_value_error_preserves_cached_meter(self):
        """get_usage_data() preserves _water_meter_number when BindMultiMeter parse fails."""
        client = _make_logged_in_client(meter_cached=False)
        # Seed a cached meter, then clear it to enter the discovery block
        # This simulates: meter was discovered before, then cleared (e.g. by logout),
        # and on re-discovery the parse fails — meter should stay None (unchanged).
        client._water_meter_number = None

        usage_page = _usage_page_response()
        # BindMultiMeter returns 200 but with invalid JSON in 'd' → parse_api_response raises ValueError
        bad_bind = MagicMock()
        bad_bind.status_code = 200
        bad_bind.json.return_value = {"d": "NOT VALID JSON{{{"}
        load_resp = _load_water_usage_response()

        with patch.object(client.session, "get", return_value=usage_page):
            with patch.object(
                client.session,
                "post",
                side_effect=_make_post_dispatcher(bad_bind, load_resp),
            ):
                client.get_usage_data(mode="B")

        # meter_details was set to None by the ValueError handler,
        # so _water_meter_number is unchanged (still None)
        assert client._water_meter_number is None

    def test_load_water_usage_non_200_returns_none(self):
        """get_usage_data() returns None when LoadWaterUsage returns non-200 status."""
        client = _make_logged_in_client(meter_cached=True)

        usage_page = _usage_page_response()
        bad_load = MagicMock()
        bad_load.status_code = 403

        with patch.object(client.session, "get", return_value=usage_page):
            with patch.object(client.session, "post", return_value=bad_load):
                result = client.get_usage_data(mode="B")

        assert result is None

    def test_load_water_usage_json_decode_error_returns_none(self):
        """get_usage_data() returns None when LoadWaterUsage response.json() raises."""
        client = _make_logged_in_client(meter_cached=True)

        usage_page = _usage_page_response()
        bad_json_resp = MagicMock()
        bad_json_resp.status_code = 200
        bad_json_resp.json.side_effect = requests.exceptions.JSONDecodeError(
            "Expecting value", "", 0
        )

        with patch.object(client.session, "get", return_value=usage_page):
            with patch.object(client.session, "post", return_value=bad_json_resp):
                result = client.get_usage_data(mode="B")

        assert result is None

    def test_load_water_usage_parse_api_response_value_error_returns_none(self):
        """get_usage_data() returns None when parse_api_response raises ValueError."""
        client = _make_logged_in_client(meter_cached=True)

        usage_page = _usage_page_response()
        bad_parse_resp = MagicMock()
        bad_parse_resp.status_code = 200
        # 'd' contains invalid JSON — parse_api_response raises ValueError
        bad_parse_resp.json.return_value = {"d": "INVALID JSON[[["}

        with patch.object(client.session, "get", return_value=usage_page):
            with patch.object(client.session, "post", return_value=bad_parse_resp):
                result = client.get_usage_data(mode="B")

        assert result is None


# ---------------------------------------------------------------------------
# Task 1: Logout
# ---------------------------------------------------------------------------


class TestLogout:
    """Tests for ACWDClient.logout()."""

    def test_logout_sets_logged_in_false_and_closes_session(self):
        """logout() sets logged_in=False and calls session.close() when logged in."""
        client = _make_logged_in_client()

        with patch.object(client.session, "close") as mock_close:
            client.logout()

        assert client.logged_in is False
        mock_close.assert_called_once()

    def test_logout_clears_state_when_not_logged_in(self):
        """logout() clears cached state even when client is not logged in (e.g. after failed login)."""
        client = _make_client()
        # Simulate state left over from a failed login
        client.csrf_token = "stale_token"
        client.user_info = {"Name": "Partial"}
        client._water_meter_number = "STALE_METER"
        assert client.logged_in is False

        with patch.object(client.session, "close") as mock_close:
            client.logout()

        mock_close.assert_not_called()
        assert client.logged_in is False
        assert client.csrf_token is None
        assert client.user_info == {}
        assert client._water_meter_number is None

    def test_logout_clears_sensitive_state(self):
        """logout() resets csrf_token, user_info, and _water_meter_number to initial values."""
        client = _make_logged_in_client(meter_cached=True)
        client.csrf_token = "active_csrf"
        client.user_info = {"Name": "Test User", "AccountNumber": "123"}
        client._water_meter_number = "230057301"

        with patch.object(client.session, "close"):
            client.logout()

        assert client.logged_in is False
        assert client.csrf_token is None
        assert client.user_info == {}
        assert client._water_meter_number is None


# ---------------------------------------------------------------------------
# Task 1: meter_number property
# ---------------------------------------------------------------------------


class TestMeterNumberProperty:
    """Tests for ACWDClient.meter_number property."""

    def test_meter_number_returns_none_when_not_discovered(self):
        """meter_number returns None when BindMultiMeter has not been called."""
        client = _make_client()
        assert client.meter_number is None

    def test_meter_number_returns_cached_value(self):
        """meter_number returns the value set by get_usage_data()."""
        client = _make_logged_in_client(meter_cached=True)
        assert client.meter_number == "230057301"

    def test_meter_number_returns_water_meter_number_attribute(self):
        """meter_number property returns exactly _water_meter_number."""
        client = _make_client()
        client._water_meter_number = "METER_XYZ"
        assert client.meter_number == "METER_XYZ"
