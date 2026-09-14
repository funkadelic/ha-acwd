"""Payload/header/URL assertions for ACWDClient HTTP calls.

test_acwd_api.py covers branch outcomes (return values, state transitions). This
file asserts the exact request bodies, headers, and URLs sent to the ACWD portal,
and direct unit tests for the static/private helpers that build them.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
import requests
from bs4 import BeautifulSoup

from custom_components.acwd.acwd_api import USER_AGENT, ACWDClient
from custom_components.acwd.const import HTTP_TIMEOUT
from tests.helpers import make_client as _make_client
from tests.helpers import make_logged_in_client as _make_logged_in_client
from tests.test_acwd_api import (
    _bind_meter_response,
    _dashboard_response,
    _load_water_usage_response,
    _login_page_response,
    _update_state_response,
    _usage_page_response,
    _validate_login_response,
)

EXPECTED_LOGIN_HEADERS = {
    "Content-Type": "application/json; charset=UTF-8",
    "Referer": "https://portal.acwd.org/portal/",
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": USER_AGENT,
    "CSRFToken": "csrf_abc",
}


class TestInit:
    """Direct assertions on ACWDClient.__init__ initial state."""

    def test_init_sets_all_expected_attributes(self):
        client = ACWDClient("user1", "pass1")

        assert client.username == "user1"
        assert client.password == "pass1"
        assert client.base_url == "https://portal.acwd.org/portal/"
        assert client.logged_in is False
        assert client.user_info == {}
        assert client.csrf_token is None
        assert client._water_meter_number is None
        assert isinstance(client.session, requests.Session)


class TestGetHiddenFieldsDirect:
    """Direct assertions on ACWDClient._get_hidden_fields."""

    def test_hidden_fields_extraction(self):
        html = (
            "<html>"
            '<input type="hidden" name="a" value="1"/>'
            '<input type="hidden" name="b"/>'
            '<input type="text" name="c" value="ignored"/>'
            '<input type="hidden" value="orphan"/>'
            "</html>"
        )
        soup = BeautifulSoup(html, "html.parser")
        client = _make_client()

        fields = client._get_hidden_fields(soup)

        assert fields == {"a": "1", "b": ""}

    def test_ignores_non_input_tags_with_hidden_type(self):
        """Only <input> tags are considered, even if another tag has type="hidden"."""
        html = '<html><select type="hidden" name="sneaky">x</select></html>'
        soup = BeautifulSoup(html, "html.parser")
        client = _make_client()

        fields = client._get_hidden_fields(soup)

        assert fields == {}


class TestNavigateToDashboardDirect:
    """Direct assertions on ACWDClient._navigate_to_dashboard URL selection."""

    @pytest.mark.parametrize(
        "main_table,expected_suffix",
        [
            ({"DashboardOption": "2"}, "DashboardCustom.aspx"),
            ({"DashboardOption": "3"}, "DashboardCustom3_3.aspx"),
            ({"DashboardOption": "1"}, "Dashboard.aspx"),
            ({}, "Dashboard.aspx"),
            ({"DashboardOption": "99"}, "Dashboard.aspx"),
        ],
    )
    def test_dashboard_url_selection(self, main_table, expected_suffix):
        client = _make_client()
        resp = MagicMock(status_code=200)

        with patch.object(client.session, "get", return_value=resp) as mock_get:
            client._navigate_to_dashboard(main_table)

        mock_get.assert_called_once_with(f"{client.base_url}{expected_suffix}", timeout=HTTP_TIMEOUT)

    def test_catches_timeout(self):
        client = _make_client()
        with patch.object(client.session, "get", side_effect=requests.Timeout("x")):
            client._navigate_to_dashboard({"DashboardOption": "1"})  # must not raise


class TestParseValidateResponseDirect:
    """Direct assertions on ACWDClient._parse_validate_response branches."""

    @staticmethod
    def _resp(d_value):
        resp = MagicMock()
        resp.json.return_value = {"d": d_value} if isinstance(d_value, str) else {"d": json.dumps(d_value)}
        resp.text = "irrelevant"
        return resp

    def test_non_dict_json_returns_false(self):
        client = _make_client()
        resp = MagicMock()
        resp.json.return_value = [1, 2, 3]
        assert client._parse_validate_response(resp) is False

    def test_migrated_user_returns_false(self):
        client = _make_client()
        resp = self._resp("Migrated User Found")
        assert client._parse_validate_response(resp) is False

    def test_dt_response_error_returns_false(self):
        client = _make_client()
        resp = self._resp({"dtResponse": [{"Message": "locked"}]})
        assert client._parse_validate_response(resp) is False

    def test_login_data_not_list_returns_false(self):
        client = _make_client()
        resp = self._resp({"some": "dict"})
        assert client._parse_validate_response(resp) is False

    def test_login_data_empty_list_returns_false(self):
        client = _make_client()
        resp = self._resp([])
        assert client._parse_validate_response(resp) is False

    def test_missing_status_key_returns_false(self):
        client = _make_client()
        resp = self._resp([{"Name": "x"}])
        assert client._parse_validate_response(resp) is False

    def test_status_0_returns_false(self):
        client = _make_client()
        resp = self._resp([{"STATUS": "0"}])
        assert client._parse_validate_response(resp) is False

    def test_status_unexpected_returns_false(self):
        client = _make_client()
        resp = self._resp([{"STATUS": "99"}])
        assert client._parse_validate_response(resp) is False

    def test_status_1_sets_user_info_and_returns_true(self):
        client = _make_client()
        main_table = {"STATUS": "1", "DashboardOption": "1", "Name": "Test"}
        resp = self._resp([main_table])
        dash_resp = MagicMock(status_code=200)

        with patch.object(client.session, "get", return_value=dash_resp):
            result = client._parse_validate_response(resp)

        assert result is True
        assert client.user_info == main_table

    def test_status_1_calls_navigate_to_dashboard_with_main_table(self):
        client = _make_client()
        main_table = {"STATUS": "1", "DashboardOption": "2"}
        resp = self._resp([main_table])

        with patch.object(client, "_navigate_to_dashboard") as mock_nav:
            result = client._parse_validate_response(resp)

        assert result is True
        mock_nav.assert_called_once_with(main_table)

    def test_status_int_1_is_coerced_to_string(self):
        client = _make_client()
        main_table = {"STATUS": 1, "DashboardOption": "1"}
        resp = self._resp([main_table])

        with patch.object(client, "_navigate_to_dashboard"):
            result = client._parse_validate_response(resp)

        assert result is True

    def test_value_error_returns_false(self):
        client = _make_client()
        resp = MagicMock()
        resp.json.side_effect = ValueError("bad json")
        assert client._parse_validate_response(resp) is False

    def test_index_error_during_dt_response_parse_returns_false(self):
        client = _make_client()
        resp = self._resp({"dtResponse": []})  # error_info = login_data["dtResponse"][0] -> IndexError
        assert client._parse_validate_response(resp) is False


class TestLoginRequestPayloads:
    """Assert exact URLs, headers, and payloads login() sends to the portal."""

    def test_full_login_request_sequence(self):
        client = ACWDClient("myuser", "mypass")
        get_resp = _login_page_response(csrf_value="csrf_abc")
        update_resp = _update_state_response()
        inner = [{"STATUS": "1", "DashboardOption": "1", "Name": "Test User"}]
        validate_resp = _validate_login_response(inner)
        dashboard_resp = _dashboard_response()

        captured_posts = []

        def _post_capture(url, **kwargs):
            captured_posts.append((url, kwargs))
            return update_resp if len(captured_posts) == 1 else validate_resp

        with (
            patch.object(client.session, "get", side_effect=_make_get_ordered(get_resp, dashboard_resp)),
            patch.object(client.session, "post", side_effect=_post_capture),
        ):
            result = client.login()

        assert result is True
        assert client.csrf_token == "csrf_abc"

        update_url, update_kwargs = captured_posts[0]
        assert update_url == f"{client.base_url}default.aspx/updateState"
        assert update_kwargs["json"] == {}
        assert update_kwargs["timeout"] == HTTP_TIMEOUT
        assert update_kwargs["headers"] == EXPECTED_LOGIN_HEADERS

        validate_url, validate_kwargs = captured_posts[1]
        assert validate_url == f"{client.base_url}default.aspx/validateLogin"
        assert validate_kwargs["timeout"] == HTTP_TIMEOUT
        assert validate_kwargs["headers"] == EXPECTED_LOGIN_HEADERS
        assert validate_kwargs["json"] == {
            "username": "myuser",
            "password": "mypass",
            "rememberme": False,
            "calledFrom": "LN",
            "ExternalLoginId": "",
            "LoginMode": "1",
            "utilityAcountNumber": "",
            "isEdgeBrowser": False,
        }

    def test_initial_get_uses_base_url_and_timeout(self):
        client = _make_client()
        no_csrf_resp = MagicMock(status_code=200, text="<html></html>")

        with patch.object(client.session, "get", return_value=no_csrf_resp) as mock_get:
            client.login()

        mock_get.assert_called_once_with(client.base_url, timeout=HTTP_TIMEOUT)


def _make_get_ordered(*responses):
    calls = {"n": 0}

    def _side_effect(*_args, **_kwargs):
        idx = calls["n"]
        calls["n"] += 1
        return responses[min(idx, len(responses) - 1)]

    return _side_effect


class TestSelectMeterDirect:
    """Direct assertions on ACWDClient._select_meter selection logic."""

    def test_finds_ami_water_meter_among_multiple(self):
        meters = [
            {"IsAMI": False, "MeterType": "W", "MeterNumber": "NOT_AMI"},
            {"IsAMI": True, "MeterType": "E", "MeterNumber": "AMI_BUT_ELECTRIC"},
            {"IsAMI": True, "MeterType": "W", "MeterNumber": "AMI_WATER"},
        ]
        assert ACWDClient._select_meter(meters) == "AMI_WATER"

    def test_falls_back_to_first_when_no_ami_water_meter(self):
        meters = [
            {"IsAMI": False, "MeterType": "W", "MeterNumber": "FIRST"},
            {"IsAMI": True, "MeterType": "E", "MeterNumber": "SECOND"},
        ]
        assert ACWDClient._select_meter(meters) == "FIRST"

    def test_ami_missing_meter_number_defaults_to_empty_string(self):
        meters = [{"IsAMI": True, "MeterType": "W"}]
        assert ACWDClient._select_meter(meters) == ""

    def test_fallback_missing_meter_number_defaults_to_empty_string(self):
        meters = [{"IsAMI": False, "MeterType": "W"}]
        assert ACWDClient._select_meter(meters) == ""

    def test_requires_both_ami_and_water_type(self):
        meters = [{"IsAMI": True, "MeterType": "E", "MeterNumber": "E1"}]
        assert ACWDClient._select_meter(meters) == "E1"


class TestParseMeterResponseDirect:
    """Direct assertions on ACWDClient._parse_meter_response success paths."""

    def test_returns_meter_details_list_when_valid(self):
        result = ACWDClient._parse_meter_response({"d": json.dumps({"MeterDetails": [{"MeterNumber": "X", "IsAMI": True}]})})
        assert result == [{"MeterNumber": "X", "IsAMI": True}]

    def test_returns_empty_list_when_meter_details_empty(self):
        result = ACWDClient._parse_meter_response({"d": json.dumps({"MeterDetails": []})})
        assert result == []


class TestDiscoverMeterRequestPayload:
    """Assert exact URL, payload, headers, and timeout for BindMultiMeter."""

    def test_posts_correct_url_payload_and_headers(self):
        client = _make_client()
        bind_resp = _bind_meter_response([{"IsAMI": True, "MeterType": "W", "MeterNumber": "M1"}])
        headers = {"csrftoken": "abc"}

        with patch.object(client.session, "post", return_value=bind_resp) as mock_post:
            client._discover_meter(headers)

        mock_post.assert_called_once_with(
            f"{client.base_url}Usages.aspx/BindMultiMeter",
            json={"MeterType": "W"},
            headers=headers,
            timeout=HTTP_TIMEOUT,
        )
        assert client._water_meter_number == "M1"


class TestRefreshCsrfTokenRequestPayload:
    """Assert exact URL/timeout and id-selector for the CSRF refresh GET."""

    def test_requests_correct_url_and_timeout(self):
        client = _make_logged_in_client()
        usage_page = MagicMock(status_code=200, text="<html></html>")

        with patch.object(client.session, "get", return_value=usage_page) as mock_get:
            client._refresh_csrf_token()

        mock_get.assert_called_once_with(f"{client.base_url}usages.aspx?type=WU", timeout=HTTP_TIMEOUT)

    def test_ignores_input_with_different_id(self):
        client = _make_logged_in_client()
        client.csrf_token = "old"
        usage_page = MagicMock(status_code=200, text='<html><input id="wrongId" value="new"/></html>')

        with patch.object(client.session, "get", return_value=usage_page):
            client._refresh_csrf_token()

        assert client.csrf_token == "old"

    def test_ignores_non_input_tag_with_matching_id(self):
        """Only <input id="hdnCSRFToken"> counts, even if another tag shares the id."""
        client = _make_logged_in_client()
        client.csrf_token = "old"
        usage_page = MagicMock(status_code=200, text='<html><div id="hdnCSRFToken" value="sneaky"/></html>')

        with patch.object(client.session, "get", return_value=usage_page):
            client._refresh_csrf_token()

        assert client.csrf_token == "old"

    def test_matching_input_without_value_attribute_leaves_token_unchanged(self):
        """Input has the right id but no value attribute at all: value defaults to "" (falsy)."""
        client = _make_logged_in_client()
        client.csrf_token = "old"
        usage_page = MagicMock(status_code=200, text='<html><input id="hdnCSRFToken"/></html>')

        with patch.object(client.session, "get", return_value=usage_page):
            client._refresh_csrf_token()

        assert client.csrf_token == "old"


class TestGetUsageDataRequestPayloads:
    """Assert exact URL, headers, and payload get_usage_data() sends for LoadWaterUsage."""

    def test_billing_mode_full_payload_and_headers(self):
        client = _make_logged_in_client(meter_cached=True)
        client.csrf_token = "csrf_xyz"
        usage_page = _usage_page_response()
        load_resp = _load_water_usage_response()

        captured = []

        def _post_capture(url, **kwargs):
            captured.append((url, kwargs))
            return load_resp

        with (
            patch.object(client.session, "get", return_value=usage_page),
            patch.object(client.session, "post", side_effect=_post_capture),
        ):
            client.get_usage_data(mode="B")

        url, kwargs = captured[0]
        assert url == f"{client.base_url}Usages.aspx/LoadWaterUsage"
        assert kwargs["timeout"] == HTTP_TIMEOUT
        assert kwargs["headers"] == {
            "Content-Type": "application/json; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{client.base_url}usages.aspx?type=WU",
            "isajax": "1",
            "csrftoken": "csrf_xyz",
        }
        assert kwargs["json"] == {
            "Type": "G",
            "Mode": "B",
            "strDate": "",
            "hourlyType": "H",
            "seasonId": "",
            "weatherOverlay": 0,
            "usageyear": "",
            "MeterNumber": "230057301",
            "DateFromDaily": "",
            "DateToDaily": "",
            "isNoDashboard": True,
        }

    def test_daily_mode_full_payload_with_dates_and_no_csrf_header(self):
        client = _make_logged_in_client(meter_cached=True)
        client.csrf_token = None
        usage_page = _usage_page_response()
        load_resp = _load_water_usage_response()

        captured = []

        def _post_capture(url, **kwargs):
            captured.append((url, kwargs))
            return load_resp

        with (
            patch.object(client.session, "get", return_value=usage_page),
            patch.object(client.session, "post", side_effect=_post_capture),
        ):
            client.get_usage_data(mode="D", date_from="12/01/2025", date_to="12/05/2025", hourly_type="Q")

        _url, kwargs = captured[0]
        assert "csrftoken" not in kwargs["headers"]
        assert kwargs["json"] == {
            "Type": "G",
            "Mode": "D",
            "strDate": "",
            "hourlyType": "Q",
            "seasonId": 0,
            "weatherOverlay": 0,
            "usageyear": "",
            "MeterNumber": "230057301",
            "DateFromDaily": "12/01/2025",
            "DateToDaily": "12/05/2025",
            "isNoDashboard": True,
        }

    def test_meter_number_empty_string_when_discovery_fails(self):
        client = _make_logged_in_client(meter_cached=False)
        usage_page = _usage_page_response()
        bad_bind = MagicMock(status_code=500)
        load_resp = _load_water_usage_response()

        captured = []

        def _post_capture(url, **kwargs):
            captured.append((url, kwargs))
            if "BindMultiMeter" in url:
                return bad_bind
            return load_resp

        with (
            patch.object(client.session, "get", return_value=usage_page),
            patch.object(client.session, "post", side_effect=_post_capture),
        ):
            client.get_usage_data(mode="B")

        load_call = next(kwargs for url, kwargs in captured if "LoadWaterUsage" in url)
        assert load_call["json"]["MeterNumber"] == ""

    def test_skips_discovery_when_meter_already_cached(self):
        client = _make_logged_in_client(meter_cached=True)
        usage_page = _usage_page_response()
        load_resp = _load_water_usage_response()

        with (
            patch.object(client.session, "get", return_value=usage_page),
            patch.object(client.session, "post", return_value=load_resp) as mock_post,
        ):
            client.get_usage_data(mode="B")

        mock_post.assert_called_once()

    def test_default_mode_is_billing(self):
        """Calling without mode= defaults to "B", which drives the seasonId branch."""
        client = _make_logged_in_client(meter_cached=True)
        usage_page = _usage_page_response()
        load_resp = _load_water_usage_response()

        captured = []

        def _post_capture(url, **kwargs):
            captured.append((url, kwargs))
            return load_resp

        with (
            patch.object(client.session, "get", return_value=usage_page),
            patch.object(client.session, "post", side_effect=_post_capture),
        ):
            client.get_usage_data()

        _url, kwargs = captured[0]
        assert kwargs["json"]["Mode"] == "B"
        assert kwargs["json"]["seasonId"] == ""

    def test_discover_meter_receives_the_request_headers(self):
        """get_usage_data() passes its built headers (with csrftoken) through to discovery."""
        client = _make_logged_in_client(meter_cached=False)
        client.csrf_token = "csrf_disc"
        usage_page = _usage_page_response()
        bind_resp = _bind_meter_response([{"IsAMI": True, "MeterType": "W", "MeterNumber": "M1"}])
        load_resp = _load_water_usage_response()

        captured = []

        def _post_capture(url, **kwargs):
            captured.append((url, kwargs))
            if "BindMultiMeter" in url:
                return bind_resp
            return load_resp

        with (
            patch.object(client.session, "get", return_value=usage_page),
            patch.object(client.session, "post", side_effect=_post_capture),
        ):
            client.get_usage_data(mode="B")

        _bind_url, bind_kwargs = next((u, k) for u, k in captured if "BindMultiMeter" in u)
        assert bind_kwargs["headers"] == {
            "Content-Type": "application/json; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{client.base_url}usages.aspx?type=WU",
            "isajax": "1",
            "csrftoken": "csrf_disc",
        }
