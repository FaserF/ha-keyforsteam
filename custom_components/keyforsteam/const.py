"""Constants for KeyforSteam integration."""

DOMAIN = "keyforsteam"
DEFAULT_CURRENCY = "eur"

# API Endpoints
GAMES_CATALOG_URL = "https://www.allkeyshop.com/api/v2/vaks.php?action=gameNames&currency=eur"
KEYFORSTEAM_PRODUCT_URL = "https://www.keyforsteam.de/{slug}-key-kaufen-preisvergleich/"
ALLKEYSHOP_PRODUCT_URL = "https://www.allkeyshop.com/blog/buy-{slug}-cd-key-compare-prices/"

# Update Intervals
UPDATE_INTERVAL_HOURS = 1
REPAIR_THRESHOLD_HOURS = 24

# Repair Issue Identifiers
REPAIR_API_FAILURE = "api_failure"
REPAIR_PRODUCT_NOT_FOUND = "product_not_found"
ISSUE_TRACKER_URL = "https://github.com/FaserF/ha-keyforsteam/issues"

# Supported Currencies
SUPPORTED_CURRENCIES = ["eur", "usd", "gbp"]

# Config Keys
CONF_PRODUCT_ID = "product_id"
CONF_PRODUCT_NAME = "product_name"
CONF_PRODUCT_SLUG = "product_slug"
CONF_CURRENCY = "currency"
CONF_PRICE_ALERT_THRESHOLD = "price_alert_threshold"
CONF_ALLOW_ACCOUNTS = "allow_accounts"
CONF_PAYMENT_METHOD = "payment_method"

# Payment Methods
PAYMENT_METHOD_BASE = "base"
PAYMENT_METHOD_CARD = "card"
PAYMENT_METHOD_PAYPAL = "paypal"
PAYMENT_METHOD_LOWEST_FEES = "lowest_fees"

# Defaults
DEFAULT_PRICE_ALERT_THRESHOLD = 0  # 0 = disabled