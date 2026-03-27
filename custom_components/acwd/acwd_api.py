"""
ACWD Water Usage Scraper
Logs into the ACWD portal and retrieves water usage data

Exception handling patterns:
- login(): returns False on auth/parse failures (ValueError, KeyError, TypeError,
  IndexError); raises on network errors (Timeout, ConnectionError) and HTTP errors
  (HTTPError via raise_for_status). Callers use the bool return for auth flow;
  network/HTTP exceptions propagate for infrastructure-level failure handling.
- get_usage_data(): returns None on parse or data failures; raises RuntimeError if
  called before login(); raises on network errors from LoadWaterUsage. Callers check
  None for graceful degradation.
- logout(): closes the session and clears all sensitive state. ACWD uses session
  cookies so session.close() is sufficient; no server-side logout endpoint is needed.
"""

import requests
from bs4 import BeautifulSoup
import logging

from .const import (
    DATE_FORMAT_LONG,
    HTTP_TIMEOUT,
    KEY_D,
    KEY_MESSAGE,
    KEY_STATUS,
    LOG_NETWORK_ERROR,
)
from .helpers import parse_api_response, parse_date_mdy

_LOGGER = logging.getLogger(__name__)

# User agent string for HTTP requests
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"

# HTTP header constants
CONTENT_TYPE_JSON = "application/json; charset=UTF-8"
HEADER_X_REQUESTED_WITH = "X-Requested-With"
HEADER_REFERER = "Referer"
HEADER_CONTENT_TYPE = "Content-Type"
VALUE_XML_HTTP_REQUEST = "XMLHttpRequest"

# Parser constants
PARSER_HTML = "html.parser"
FIELD_CSRF_TOKEN = "hdnCSRFToken"  # noqa: S105  # form field name, not a secret


class ACWDClient:
    """Scraper for ACWD water usage data"""

    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.base_url = "https://portal.acwd.org/portal/"
        self.logged_in = False
        self.user_info = {}
        self.csrf_token = None
        self._water_meter_number = None

    def _get_hidden_fields(self, soup):
        """Extract all hidden form fields from the login page.

        Args:
            soup: BeautifulSoup object containing the login page HTML

        Returns:
            dict: Dictionary mapping field names to their values
        """
        hidden_fields = {}

        # Get all hidden input fields
        for field in soup.find_all("input", {"type": "hidden"}):
            name = field.get("name")
            value = field.get("value", "")
            if name:  # Only include fields with a name attribute
                hidden_fields[name] = value

        return hidden_fields

    def _navigate_to_dashboard(self, main_table):
        """Navigate to the appropriate dashboard URL after a successful login.

        Reads DashboardOption from main_table to determine which dashboard
        URL to request. Non-fatal: logs a warning on network error and returns
        normally so login() can proceed.

        Args:
            main_table: The first element of the validateLogin response list,
                        expected to contain a DashboardOption key.
        """
        dashboard_option = main_table.get("DashboardOption", "1")
        if dashboard_option == "2":
            dashboard_url = f"{self.base_url}DashboardCustom.aspx"
        elif dashboard_option == "3":
            dashboard_url = f"{self.base_url}DashboardCustom3_3.aspx"
        else:
            dashboard_url = f"{self.base_url}Dashboard.aspx"

        _LOGGER.info("Navigating to %s...", dashboard_url)
        try:
            dashboard_response = self.session.get(dashboard_url, timeout=HTTP_TIMEOUT)

            if dashboard_response.status_code == 200:
                _LOGGER.info("Successfully accessed Dashboard!")
            else:
                _LOGGER.warning("Dashboard returned %s", dashboard_response.status_code)
        except (requests.Timeout, requests.ConnectionError) as e:
            _LOGGER.warning(LOG_NETWORK_ERROR, dashboard_url, e)

    def _parse_validate_response(self, validate_response):
        """Parse the validateLogin HTTP response and apply login logic.

        Calls validate_response.json() — non-ValueError exceptions (e.g.
        RuntimeError) propagate to the caller. On success, stores user_info
        and calls _navigate_to_dashboard; returns True. Returns False for any
        auth or parse failure.

        Args:
            validate_response: The requests.Response from the validateLogin POST.

        Returns:
            True on successful login, False on any auth/parse failure.
        """
        try:
            result = validate_response.json()
            _LOGGER.debug("validateLogin response received")

            # Check for special cases before JSON parsing (not valid JSON)
            if not isinstance(result, dict):
                _LOGGER.error(
                    "validateLogin returned non-dict JSON: %s", type(result).__name__
                )
                return False

            if result.get(KEY_D) == "Migrated User Found":
                _LOGGER.error("Account requires migration")
                return False

            # Parse the inner JSON (it's a JSON string inside 'd')
            login_data = parse_api_response(result, endpoint="validateLogin")
            _LOGGER.debug("Login response parsed successfully")

            # Handle error response format (dtResponse)
            if isinstance(login_data, dict) and "dtResponse" in login_data:
                error_info = login_data["dtResponse"][0]
                _LOGGER.error(
                    "Login failed: %s", error_info.get(KEY_MESSAGE, "Unknown error")
                )
                return False

            # Handle success response format (array with STATUS)
            if not (isinstance(login_data, list) and len(login_data) > 0):
                _LOGGER.error("Unexpected login response: %s", login_data)
                return False

            main_table = login_data[0]

            if KEY_STATUS not in main_table:
                _LOGGER.error("Unexpected response structure: %s", main_table)
                return False

            status = str(main_table[KEY_STATUS])  # Convert to string for comparison
            if status == "0":
                _LOGGER.error(
                    "Login failed: %s", main_table.get(KEY_MESSAGE, "Unknown error")
                )
                return False

            if status == "1":
                _LOGGER.info("Login successful!")
                self.user_info = main_table
                _LOGGER.debug("User information stored")
                self._navigate_to_dashboard(main_table)
                return True

            _LOGGER.error("Unexpected response structure: %s", main_table)
            return False

        except ValueError:
            _LOGGER.exception("Failed to parse login response JSON")
            return False
        except (KeyError, TypeError, IndexError):
            _LOGGER.exception("Error processing validateLogin response")
            _LOGGER.debug("Response text: %s", validate_response.text[:200])
            return False

    def login(self):
        """Login to the ACWD portal"""
        _LOGGER.info("Fetching login page...")

        # Step 1: Get the login page to establish session and extract tokens
        try:
            response = self.session.get(self.base_url, timeout=HTTP_TIMEOUT)
        except (requests.Timeout, requests.ConnectionError) as e:
            _LOGGER.warning(LOG_NETWORK_ERROR, self.base_url, e)
            raise

        response.raise_for_status()

        soup = BeautifulSoup(response.text, PARSER_HTML)

        # Step 2: Extract hidden fields (CSRF token, etc.)
        hidden_fields = self._get_hidden_fields(soup)
        _LOGGER.info("Extracted %s hidden fields", len(hidden_fields))

        # Get the CSRF token
        csrf_token = hidden_fields.get(FIELD_CSRF_TOKEN, "")
        if not csrf_token:
            _LOGGER.error("No CSRF token found!")
            return False

        # Store CSRF token for future requests
        self.csrf_token = csrf_token
        _LOGGER.debug("CSRF token obtained")

        # Step 3: Call updateState endpoint
        _LOGGER.info("Calling updateState endpoint...")
        update_state_url = f"{self.base_url}default.aspx/updateState"

        update_state_response = self.session.post(
            update_state_url,
            json={},
            headers={
                "Content-Type": CONTENT_TYPE_JSON,
                "Referer": self.base_url,
                HEADER_X_REQUESTED_WITH: VALUE_XML_HTTP_REQUEST,
                "User-Agent": USER_AGENT,
                "CSRFToken": csrf_token,
            },
            timeout=HTTP_TIMEOUT,
        )

        if update_state_response.status_code != 200:
            _LOGGER.warning(
                "updateState returned %s", update_state_response.status_code
            )

        # Step 4: Call validateLogin endpoint (actual login validation)
        _LOGGER.info("Calling validateLogin endpoint...")
        validate_login_url = f"{self.base_url}default.aspx/validateLogin"

        login_payload = {
            "username": self.username,
            "password": self.password,
            "rememberme": False,
            "calledFrom": "LN",
            "ExternalLoginId": "",
            "LoginMode": "1",
            "utilityAcountNumber": "",
            "isEdgeBrowser": False,
        }

        try:
            validate_response = self.session.post(
                validate_login_url,
                json=login_payload,
                headers={
                    "Content-Type": CONTENT_TYPE_JSON,
                    "Referer": self.base_url,
                    HEADER_X_REQUESTED_WITH: VALUE_XML_HTTP_REQUEST,
                    "User-Agent": USER_AGENT,
                    "CSRFToken": csrf_token,
                },
                timeout=HTTP_TIMEOUT,
            )
        except (requests.Timeout, requests.ConnectionError) as e:
            _LOGGER.warning(LOG_NETWORK_ERROR, validate_login_url, e)
            raise

        if validate_response.status_code != 200:
            _LOGGER.error(
                "validateLogin failed with status code: %s",
                validate_response.status_code,
            )
            return False

        # Step 5: Parse validateLogin response and complete login
        login_ok = self._parse_validate_response(validate_response)
        if not login_ok:
            return False
        self.logged_in = True
        return True

    @staticmethod
    def _parse_meter_response(bind_result):
        """Parse and validate the BindMultiMeter API response.

        Args:
            bind_result: Raw JSON response from BindMultiMeter endpoint.

        Returns:
            list[dict] | None: List of meter dicts on success (may be empty),
                or None on parse/validation error.
        """
        try:
            bind_data = parse_api_response(bind_result, endpoint="BindMultiMeter")
        except ValueError as e:
            _LOGGER.warning("Failed to parse BindMultiMeter response: %s", e)
            return None

        if not isinstance(bind_data, dict):
            _LOGGER.warning(
                "Unexpected BindMultiMeter response type: %s",
                type(bind_data).__name__,
            )
            return None

        if "MeterDetails" not in bind_data:
            _LOGGER.warning("BindMultiMeter response missing MeterDetails key")
            return None

        meter_details = bind_data["MeterDetails"]

        if not isinstance(meter_details, list) or any(
            not isinstance(m, dict) for m in meter_details
        ):
            if isinstance(meter_details, list):
                bad_types = {
                    type(m).__name__ for m in meter_details if not isinstance(m, dict)
                }
                _LOGGER.warning(
                    "Invalid MeterDetails format: expected list of dicts, "
                    "got list containing %s",
                    ", ".join(sorted(bad_types)),
                )
            else:
                _LOGGER.warning(
                    "Invalid MeterDetails format: expected list of dicts, got %s",
                    type(meter_details).__name__,
                )
            return None

        return meter_details

    @staticmethod
    def _select_meter(meter_details):
        """Select the best meter from a list of meter dicts.

        Prefers an AMI-enabled water meter; falls back to the first meter.

        Args:
            meter_details: Non-empty list of meter dicts.

        Returns:
            str: The chosen MeterNumber.
        """
        for meter in meter_details:
            if meter.get("IsAMI") and meter.get("MeterType") == "W":
                meter_number = meter.get("MeterNumber", "")
                _LOGGER.info("Found AMI water meter: %s", meter_number)
                return meter_number

        meter_number = meter_details[0].get("MeterNumber", "")
        _LOGGER.info("No AMI meter found, using first meter: %s", meter_number)
        return meter_number

    def _discover_meter(self, headers):
        """Discover the water meter number via the BindMultiMeter API.

        Calls the BindMultiMeter endpoint to get available meters, preferring
        an AMI-enabled water meter. Sets self._water_meter_number on success;
        leaves it unchanged on failure.

        Args:
            headers: HTTP headers dict (must include CSRF token if available)
        """
        bind_meter_url = f"{self.base_url}Usages.aspx/BindMultiMeter"
        bind_payload = {"MeterType": "W"}  # W for water

        try:
            bind_response = self.session.post(
                bind_meter_url,
                json=bind_payload,
                headers=headers,
                timeout=HTTP_TIMEOUT,
            )
        except (requests.Timeout, requests.ConnectionError) as e:
            _LOGGER.warning(LOG_NETWORK_ERROR, bind_meter_url, e)
            return

        if bind_response.status_code != 200:
            _LOGGER.debug(
                "BindMultiMeter returned status %d",
                bind_response.status_code,
            )
            return

        try:
            bind_result = bind_response.json()
        except ValueError as e:
            _LOGGER.warning("Failed to decode BindMultiMeter response JSON: %s", e)
            return

        meter_details = self._parse_meter_response(bind_result)

        if meter_details is None:
            # Parse/validation failed — leave existing meter number unchanged
            return

        if not meter_details:
            self._water_meter_number = ""
            _LOGGER.warning("No water meters found, using empty meter number")
            return

        self._water_meter_number = self._select_meter(meter_details)

    def _refresh_csrf_token(self):
        """Fetch the usage page and update self.csrf_token if a fresh token is found.

        Non-fatal: logs warnings on network errors and continues silently
        if no token is found.
        """
        usage_page_url = f"{self.base_url}usages.aspx?type=WU"
        try:
            page_response = self.session.get(usage_page_url, timeout=HTTP_TIMEOUT)
        except (requests.Timeout, requests.ConnectionError) as e:
            _LOGGER.warning(LOG_NETWORK_ERROR, usage_page_url, e)
            return

        if page_response.status_code != 200:
            return

        soup = BeautifulSoup(page_response.text, PARSER_HTML)
        csrf_input = soup.find("input", {"id": FIELD_CSRF_TOKEN})
        if csrf_input:
            fresh_csrf = csrf_input.get("value", "")
            if fresh_csrf:
                self.csrf_token = fresh_csrf
                _LOGGER.info("Got fresh CSRF token from usage page")

    @staticmethod
    def _format_api_date(str_date):
        """Convert MM/DD/YYYY date string to "Month D, YYYY" format for the API.

        Args:
            str_date: Date string in MM/DD/YYYY format, or None.

        Returns:
            str: Formatted date string, or empty string if str_date is falsy.
        """
        if not str_date:
            return ""

        date_obj = parse_date_mdy(str_date)
        if date_obj is not None:
            # Format as "December 4, 2025" (no leading zero on day)
            return date_obj.strftime(DATE_FORMAT_LONG).replace(" 0", " ")

        _LOGGER.warning("Failed to parse date %r, using raw value", str_date)
        return str(str_date)

    def get_usage_data(
        self, mode="B", date_from=None, date_to=None, str_date=None, hourly_type="H"
    ):
        """
        Retrieve water usage data

        Args:
            mode: Data granularity mode
                  'B' - Billing cycle (default - recommended for summary)
                  'D' - Daily usage
                  'H' - Hourly usage (requires str_date parameter)
                  'M' - Monthly usage
                  'Y' - Yearly usage
            date_from: Start date for daily mode (MM/DD/YYYY format)
            date_to: End date for daily mode (MM/DD/YYYY format)
            str_date: Specific date for hourly mode (MM/DD/YYYY format)
            hourly_type: For hourly mode - 'H' for hourly, 'Q' for 15-minute intervals

        Returns:
            dict: Usage data from the API, or None if request fails

        Note:
            - Billing cycle mode ('B') provides complete historical summary data
            - Hourly mode ('H') requires str_date parameter for specific date
            - 15-minute mode uses hourly_type='Q' with mode='H'
            - ACWD has 24-hour data delay - current day data is not available
        """
        if not self.logged_in:
            raise RuntimeError("Not logged in. Call login() first.")

        _LOGGER.info(
            "Fetching usage data (mode=%s, hourly_type=%s)...", mode, hourly_type
        )

        self._refresh_csrf_token()

        formatted_date = self._format_api_date(str_date)

        usage_url = f"{self.base_url}Usages.aspx/LoadWaterUsage"

        # Set up headers for API requests
        headers = {
            "Content-Type": CONTENT_TYPE_JSON,
            HEADER_X_REQUESTED_WITH: VALUE_XML_HTTP_REQUEST,
            "Referer": f"{self.base_url}usages.aspx?type=WU",
            "isajax": "1",
        }

        # Add CSRF token to header (lowercase as per browser)
        if self.csrf_token:
            headers["csrftoken"] = self.csrf_token

        # Discover meter number if not cached
        if self._water_meter_number is None:
            self._discover_meter(headers)

        # Use cached meter number
        meter_number = (
            self._water_meter_number if self._water_meter_number is not None else ""
        )

        # Build final payload with discovered meter number
        payload = {
            "Type": "G",  # Graph type (as per browser)
            "Mode": mode,
            "strDate": formatted_date,  # Format: "December 4, 2025"
            "hourlyType": hourly_type,  # 'H' for hourly, 'Q' for 15-minute intervals
            "seasonId": "" if mode == "B" else 0,  # Empty string for billing cycle
            "weatherOverlay": 0,
            "usageyear": "",
            "MeterNumber": meter_number,
            "DateFromDaily": date_from or "",
            "DateToDaily": date_to or "",
            "isNoDashboard": True,
        }

        response = self.session.post(
            usage_url, json=payload, headers=headers, timeout=HTTP_TIMEOUT
        )

        if response.status_code != 200:
            _LOGGER.error("Failed to fetch usage data: %s", response.status_code)
            return None

        try:
            result = response.json()
        except ValueError as e:
            _LOGGER.exception("Error decoding usage response: %s", e)
            return None

        try:
            usage_data = parse_api_response(result, endpoint="LoadWaterUsage")
            _LOGGER.info("Retrieved usage data successfully")
            return usage_data
        except ValueError as e:
            _LOGGER.error("Error parsing usage data: %s", e)
            return None

    def logout(self):
        """Logout from the portal"""
        if self.logged_in:
            _LOGGER.info("Logging out...")
            # ACWD portal uses session cookies; closing the session is sufficient for logout.
            self.session.close()
        self.logged_in = False
        self.csrf_token = None
        self.user_info = {}
        self._water_meter_number = None

    @property
    def meter_number(self):
        """Get the water meter number.

        Returns the AMI-enabled water meter number discovered from the
        BindMultiMeter API call. This is populated during the first call
        to get_usage_data().
        """
        return self._water_meter_number
