"""Constants for the ACWD Water Usage integration."""

# -- Domain ---------------------------------------------------------------
DOMAIN = "acwd"

# -- Configuration ---------------------------------------------------------
CONF_ACCOUNT_NUMBER = "account_number"

# -- Default Values --------------------------------------------------------
DEFAULT_NAME = "ACWD Water"

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
