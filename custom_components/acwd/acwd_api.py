"""
ACWD Water Usage Scraper
Logs into the ACWD portal and retrieves water usage data
"""

import json
import logging
import time
from contextlib import contextmanager
from typing import Any, Callable, Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# User agent string for HTTP requests
# Updated to a more maintainable format that can be easily updated
# Using a modern Chrome user agent that's less likely to be blocked
USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/143.0.0.0 Safari/537.36'
)


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
        """Extract all hidden form fields from the login page"""
        hidden_fields = {}

        # Get all hidden input fields
        for field in soup.find_all('input', {'type': 'hidden'}):
            name = field.get('name')
            value = field.get('value', '')
            if name:  # Only include fields with a name attribute
                hidden_fields[name] = value

        return hidden_fields

    def login(self) -> bool:
        """Login to the ACWD portal.
        
        Returns:
            True if login successful, False otherwise
        """
        logger.info("Fetching login page...")

        # Step 1: Get the login page to establish session and extract tokens
        # Use retry logic for network requests
        try:
            response = self._retry_request(
                self.session.get,
                self.base_url,
                max_retries=3,
                retry_delay=2.0,
                timeout=30,
                headers={'User-Agent': USER_AGENT}
            )
        except Exception as e:
            logger.error(f"Failed to load login page after retries: {e}")
            return False

        if response.status_code != 200:
            logger.error(f"Failed to load login page: {response.status_code}")
            return False

        soup = BeautifulSoup(response.text, 'html.parser')

        # Step 2: Extract hidden fields (CSRF token, etc.)
        hidden_fields = self._get_hidden_fields(soup)
        logger.info(f"Extracted {len(hidden_fields)} hidden fields")

        # Get the CSRF token
        csrf_token = hidden_fields.get('hdnCSRFToken', '')
        if not csrf_token:
            logger.error("No CSRF token found!")
            return False

        # Store CSRF token for future requests
        self.csrf_token = csrf_token
        logger.debug("CSRF token obtained")

        # Step 3: Call updateState endpoint
        logger.info("Calling updateState endpoint...")
        update_state_url = f"{self.base_url}default.aspx/updateState"

        try:
            update_state_response = self._retry_request(
                self.session.post,
                update_state_url,
                max_retries=2,
                retry_delay=1.0,
                json={},
                timeout=30,
                headers={
                    'Content-Type': 'application/json; charset=UTF-8',
                    'Referer': self.base_url,
                    'X-Requested-With': 'XMLHttpRequest',
                    'User-Agent': USER_AGENT,
                    'CSRFToken': csrf_token
                }
            )
        except Exception as e:
            logger.warning(f"updateState failed (non-critical): {e}")

        # Step 4: Call validateLogin endpoint (actual login validation)
        logger.info("Calling validateLogin endpoint...")
        validate_login_url = f"{self.base_url}default.aspx/validateLogin"

        login_payload = {
            'username': self.username,
            'password': self.password,
            'rememberme': False,
            'calledFrom': 'LN',
            'ExternalLoginId': '',
            'LoginMode': '1',
            'utilityAcountNumber': '',
            'isEdgeBrowser': False
        }

        try:
            validate_response = self._retry_request(
                self.session.post,
                validate_login_url,
                max_retries=3,
                retry_delay=2.0,
                json=login_payload,
                timeout=30,
                headers={
                    'Content-Type': 'application/json; charset=UTF-8',
                    'Referer': self.base_url,
                    'X-Requested-With': 'XMLHttpRequest',
                    'User-Agent': USER_AGENT,
                    'CSRFToken': csrf_token
                }
            )
        except Exception as e:
            logger.error(f"validateLogin failed after retries: {e}")
            return False

        if validate_response.status_code != 200:
            logger.error(f"validateLogin failed with status code: {validate_response.status_code}")
            return False

        # Step 5: Check the response from validateLogin
        try:
            result = validate_response.json()
            logger.debug("validateLogin response received")

            # ASP.NET WebMethods wrap response in 'd' property
            if 'd' not in result:
                logger.error("Unexpected response format - missing 'd' property")
                return False

            # Parse the inner JSON (it's a JSON string inside 'd')
            login_data = json.loads(result['d'])
            logger.debug("Login response parsed successfully")

            # Check for special cases
            if result['d'] == "Migrated User Found":
                logger.error("Account requires migration")
                return False

            # Handle error response format (dtResponse)
            if isinstance(login_data, dict) and 'dtResponse' in login_data:
                error_info = login_data['dtResponse'][0]
                logger.error(f"Login failed: {error_info.get('Message', 'Unknown error')}")
                return False

            # Handle success response format (array with STATUS)
            if isinstance(login_data, list) and len(login_data) > 0:
                main_table = login_data[0]

                # Check STATUS field
                if 'STATUS' in main_table:
                    status = str(main_table['STATUS'])  # Convert to string for comparison
                    if status == '0':
                        logger.error(f"Login failed: {main_table.get('Message', 'Unknown error')}")
                        return False
                    elif status == '1':
                        logger.info("Login successful!")

                        # Store user info
                        self.user_info = main_table
                        logger.debug("User information stored")

                        # Determine which dashboard to use
                        dashboard_option = main_table.get('DashboardOption', '1')
                        if dashboard_option == '2':
                            dashboard_url = f"{self.base_url}DashboardCustom.aspx"
                        elif dashboard_option == '3':
                            dashboard_url = f"{self.base_url}DashboardCustom3_3.aspx"
                        else:
                            dashboard_url = f"{self.base_url}Dashboard.aspx"

                        # Navigate to the appropriate dashboard
                        logger.info(f"Navigating to {dashboard_url}...")
                        dashboard_response = self.session.get(dashboard_url)

                        if dashboard_response.status_code == 200:
                            logger.info("Successfully accessed Dashboard!")
                            self.logged_in = True
                            return True
                        else:
                            logger.warning(f"Dashboard returned {dashboard_response.status_code}")
                            self.logged_in = True  # Still logged in even if dashboard fails
                            return True
                else:
                    logger.error(f"Unexpected response structure: {main_table}")
                    return False
            else:
                logger.error(f"Unexpected login response: {login_data}")
                return False

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse login response JSON: {e}")
            logger.error(f"Response: {result.get('d', '')[:200]}")
            return False
        except Exception as e:
            logger.error(f"Error processing validateLogin response: {e}")
            logger.error(f"Response text: {validate_response.text[:200]}")
            return False

    def get_usage_data(self, mode='B', date_from=None, date_to=None, str_date=None, hourly_type='H'):
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
            raise Exception("Not logged in. Call login() first.")

        logger.info(f"Fetching usage data (mode={mode}, hourly_type={hourly_type})...")

        # First, navigate to the usage page to get a fresh CSRF token
        usage_page_url = f"{self.base_url}usages.aspx?type=WU"
        try:
            page_response = self._retry_request(
                self.session.get,
                usage_page_url,
                max_retries=2,
                retry_delay=1.0,
                timeout=30,
                headers={'User-Agent': USER_AGENT}
            )
            
            if page_response.status_code == 200:
                soup = BeautifulSoup(page_response.text, 'html.parser')
                csrf_input = soup.find('input', {'id': 'hdnCSRFToken'})
                if csrf_input:
                    fresh_csrf = csrf_input.get('value', '')
                    if fresh_csrf:
                        self.csrf_token = fresh_csrf
                        logger.debug("Got fresh CSRF token from usage page")
        except Exception as e:
            logger.warning(f"Failed to get fresh CSRF token (using existing): {e}")

        usage_url = f"{self.base_url}Usages.aspx/LoadWaterUsage"

        # Convert MM/DD/YYYY date to "Month D, YYYY" format if provided
        formatted_date = ''
        if str_date:
            try:
                from datetime import datetime
                date_obj = datetime.strptime(str_date, '%m/%d/%Y')
                # Format as "December 4, 2025" (no leading zero on day)
                formatted_date = date_obj.strftime('%B %d, %Y').replace(' 0', ' ')
            except:
                formatted_date = str_date  # Fallback to original if parsing fails

        # Set up headers for API requests
        headers = {
            'Content-Type': 'application/json; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': f"{self.base_url}usages.aspx?type=WU",
            'isajax': '1'
        }

        # Add CSRF token to header (lowercase as per browser)
        if self.csrf_token:
            headers['csrftoken'] = self.csrf_token

        # Get water meter number
        # The water meter number is not in the login response - it's loaded dynamically
        # Call BindMultiMeter API to discover available meters and select AMI meter

        # Try to discover the correct meter number if not cached
        if self._water_meter_number is None:
            # Call BindMultiMeter endpoint to get list of available meters
            bind_meter_url = f"{self.base_url}Usages.aspx/BindMultiMeter"
            bind_payload = {"MeterType": "W"}  # W for water

            try:
                bind_response = self._retry_request(
                    self.session.post,
                    bind_meter_url,
                    max_retries=2,
                    retry_delay=1.0,
                    json=bind_payload,
                    timeout=30,
                    headers=headers
                )

                if bind_response.status_code == 200:
                    bind_result = bind_response.json()
                    if 'd' in bind_result:
                        bind_data = json.loads(bind_result['d'])
                        meter_details = bind_data.get('MeterDetails', [])

                        # Find AMI-enabled meter (smart meter with hourly data)
                        ami_meter = None
                        for meter in meter_details:
                            if meter.get('IsAMI') and meter.get('MeterType') == 'W':
                                ami_meter = meter.get('MeterNumber', '')
                                logger.info(f"Found AMI water meter: {ami_meter}")
                                break

                        if ami_meter:
                            self._water_meter_number = ami_meter
                        else:
                            # No AMI meter found, try first water meter or empty
                            if meter_details:
                                self._water_meter_number = meter_details[0].get('MeterNumber', '')
                                logger.info(f"No AMI meter found, using first meter: {self._water_meter_number}")
                            else:
                                self._water_meter_number = ''
                                logger.warning("No water meters found, using empty meter number")
            except Exception as e:
                logger.error(f"Error fetching meter list: {e}")
                self._water_meter_number = ''

        # Use cached meter number
        meter_number = self._water_meter_number if self._water_meter_number is not None else ''

        # Build final payload with discovered meter number
        payload = {
            'Type': 'G',  # Graph type (as per browser)
            'Mode': mode,
            'strDate': formatted_date,  # Format: "December 4, 2025"
            'hourlyType': hourly_type,  # 'H' for hourly, 'Q' for 15-minute intervals
            'seasonId': '' if mode == 'B' else 0,  # Empty string for billing cycle
            'weatherOverlay': 0,
            'usageyear': '',
            'MeterNumber': meter_number,
            'DateFromDaily': date_from or '',
            'DateToDaily': date_to or '',
            'isNoDashboard': True
        }

        try:
            response = self._retry_request(
                self.session.post,
                usage_url,
                max_retries=3,
                retry_delay=2.0,
                json=payload,
                timeout=30,
                headers=headers
            )
        except Exception as e:
            logger.error(f"Failed to fetch usage data after retries: {e}")
            return None

        if response.status_code != 200:
            logger.error(f"Failed to fetch usage data: {response.status_code}")
            return None

        try:
            result = response.json()
            if 'd' in result:
                usage_data = json.loads(result['d'])
                logger.info(f"Retrieved usage data successfully")
                return usage_data
            else:
                logger.error("Unexpected response format")
                return None
        except Exception as e:
            logger.error(f"Error parsing usage data: {e}")
            return None

    def logout(self):
        """Logout from the portal"""
        if self.logged_in:
            logger.info("Logging out...")
            # TODO: Find and implement logout URL if needed
            self.session.close()
            self.logged_in = False

    @property
    def meter_number(self):
        """Get the water meter number.

        Returns the AMI-enabled water meter number discovered from the
        BindMultiMeter API call. This is populated during the first call
        to get_usage_data().
        """
        return self._water_meter_number


def main():
    """Example usage"""
    import os
    from getpass import getpass

    # Get credentials from environment variables or prompt
    username = os.getenv('ACWD_USERNAME') or input("ACWD Username: ")
    password = os.getenv('ACWD_PASSWORD') or getpass("ACWD Password: ")

    scraper = ACWDClient(username, password)

    try:
        if scraper.login():
            print("\nSuccessfully logged in!")
            print(f"User: {scraper.user_info.get('Name')}")
            print(f"Account: {scraper.user_info.get('AccountNumber')}")

            # Get daily usage data
            print("\nFetching daily water usage...")
            daily_usage = scraper.get_usage_data(mode='D')

            if daily_usage:
                import json
                print("\nDaily usage data:")
                print(json.dumps(daily_usage, indent=2)[:1000])  # First 1000 chars
            else:
                print("No usage data available")
        else:
            print("Login failed!")

    finally:
        scraper.logout()


if __name__ == "__main__":
    main()
