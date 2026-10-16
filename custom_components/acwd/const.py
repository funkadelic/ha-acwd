"""Constants for the ACWD Water Usage integration."""

# -- Domain ---------------------------------------------------------------
DOMAIN = "acwd"

# -- Configuration ---------------------------------------------------------
CONF_ACCOUNT_NUMBER = "account_number"
CONF_RATE_PER_UNIT = "rate_per_unit"

# -- Default Values --------------------------------------------------------
DEFAULT_NAME = "ACWD Water"
DEFAULT_RATE_PER_UNIT = 5.38  # USD per 748-gallon unit, effective March 1, 2026

# -- Units -----------------------------------------------------------------
UNIT_HCF = "HCF"  # Hundred Cubic Feet
UNIT_GALLONS = "gal"

# -- Conversions -----------------------------------------------------------
HCF_TO_GALLONS = 748  # 1 HCF = 748 gallons
GALLONS_TO_LITERS = 3.78541  # 1 gallon = 3.78541 liters

# -- Date/Time Formats -----------------------------------------------------
DATE_FORMAT_SLASH_MDY = "%m/%d/%Y"
DATE_FORMAT_LONG = "%B %d, %Y"
TIME_FORMAT_12HR = "%I:%M %p"

# -- API Response Keys -----------------------------------------------------
KEY_D = "d"
KEY_STATUS = "STATUS"
KEY_MESSAGE = "Message"

# -- Logging Messages ------------------------------------------------------
LOG_NETWORK_ERROR = "Network error reaching %s: %s"

# -- HTTP Timeouts ---------------------------------------------------------
HTTP_CONNECT_TIMEOUT = 10  # seconds to establish connection
HTTP_READ_TIMEOUT = 30  # seconds to receive response
HTTP_TIMEOUT = (HTTP_CONNECT_TIMEOUT, HTTP_READ_TIMEOUT)
