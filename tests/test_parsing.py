import json
import re

# Payment Methods constants
PAYMENT_METHOD_BASE = "base"
PAYMENT_METHOD_CARD = "card"
PAYMENT_METHOD_PAYPAL = "paypal"
PAYMENT_METHOD_LOWEST_FEES = "lowest_fees"


class MockConfigEntry:
    def __init__(self, data, options={}):
        self.data = data
        self.options = options


def safe_float(value, default=0.0) -> float:
    """Safely convert a value to float, handling None, string, etc."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class KeyforSteamDataUpdateCoordinator:
    def __init__(self, data, options={}):
        self.entry = MockConfigEntry(data, options)
        self.product_id = "190548"
        self.product_name = "Test Game"
        self.allow_accounts = self.entry.options.get(
            "allow_accounts", self.entry.data.get("allow_accounts", False)
        )
        self.payment_method = self.entry.options.get(
            "payment_method",
            self.entry.data.get("payment_method", PAYMENT_METHOD_LOWEST_FEES),
        )

    def _extract_json_ld(self, html):
        pattern = r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>'
        matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
        for match in matches:
            try:
                data = json.loads(match)
                if isinstance(data, dict):
                    if data.get("@type") == "Product":
                        return data
                    if "@graph" in data:
                        for item in data["@graph"]:
                            if (
                                isinstance(item, dict)
                                and item.get("@type") == "Product"
                            ):
                                return item
            except json.JSONDecodeError:
                continue
        return None

    def _parse_offers(self, product_data, url):
        return {
            "image": product_data.get("image"),
            "low_price": safe_float(product_data.get("offers", {}).get("lowPrice"), None),
        }

    def _extract_game_page_trans(self, html):
        match = re.search(r"var gamePageTrans\s*=\s*(\{.*?\});", html, re.DOTALL)
        return json.loads(match.group(1)) if match else None

    def _parse_game_page_trans(self, game_data, url):
        prices = game_data.get("prices", [])
        filtered_prices = []
        for p in prices:
            if not self.allow_accounts and p.get("account"):
                continue

            price_val = safe_float(p.get("price"))
            if self.payment_method == PAYMENT_METHOD_CARD:
                price_val = safe_float(p.get("priceCard")) or safe_float(p.get("price"))
            elif self.payment_method == PAYMENT_METHOD_PAYPAL:
                price_val = safe_float(p.get("pricePaypal")) or safe_float(p.get("price"))
            elif self.payment_method == PAYMENT_METHOD_LOWEST_FEES:
                price_fields = []
                if p.get("priceCard") is not None:
                    card_price = safe_float(p.get("priceCard"))
                    if card_price > 0:
                        price_fields.append(card_price)
                if p.get("pricePaypal") is not None:
                    paypal_price = safe_float(p.get("pricePaypal"))
                    if paypal_price > 0:
                        price_fields.append(paypal_price)
                price_val = min(price_fields) if price_fields else safe_float(p.get("price"))

            if price_val <= 0:
                continue
            entry = dict(p)
            entry["effective_price"] = price_val
            filtered_prices.append(entry)

        if not filtered_prices:
            return None
        low_price = min(p.get("effective_price", float("inf")) for p in filtered_prices)
        return {"low_price": low_price}


def test_parsing():
    html = """
    <html>
    <head>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org/",
            "@type": "Product",
            "name": "Test Game",
            "image": "https://example.com/test_game.jpg",
            "offers": {
                "@type": "AggregateOffer",
                "lowPrice": 52.94,
                "priceCurrency": "EUR"
            }
        }
        </script>
    </head>
    <body>
        <script type="text/javascript">
            var gamePageTrans = {
                "prices": [
                    {"price": 55.00, "priceCard": 53.00, "pricePaypal": 52.94, "account": false},
                    {"price": 50.00, "priceCard": 48.00, "pricePaypal": 47.00, "account": true}
                ]
            };
        </script>
    </body>
    </html>
    """

    coordinator = KeyforSteamDataUpdateCoordinator(
        {"allow_accounts": False, "payment_method": PAYMENT_METHOD_LOWEST_FEES}
    )

    # Test gamePageTrans parsing
    game_data = coordinator._extract_game_page_trans(html)
    offers_js = coordinator._parse_game_page_trans(game_data, "http://example.com")

    assert abs(offers_js["low_price"] - 52.94) < 0.01

    # Test JSON-LD parsing (for image)
    product_data = coordinator._extract_json_ld(html)
    offers_ld = coordinator._parse_offers(product_data, "http://example.com")

    assert offers_ld["image"] == "https://example.com/test_game.jpg"


def test_parsing_with_none_values():
    html = """
    <html>
    <head>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org/",
            "@type": "Product",
            "name": "Test Game",
            "image": "https://example.com/test_game.jpg",
            "offers": {
                "@type": "AggregateOffer",
                "lowPrice": null,
                "priceCurrency": "EUR"
            }
        }
        </script>
    </head>
    <body>
        <script type="text/javascript">
            var gamePageTrans = {
                "prices": [
                    {"price": null, "priceCard": null, "pricePaypal": null, "account": false},
                    {"price": 50.00, "priceCard": 48.00, "pricePaypal": 47.00, "account": false}
                ]
            };
        </script>
    </body>
    </html>
    """

    coordinator = KeyforSteamDataUpdateCoordinator(
        {"allow_accounts": False, "payment_method": PAYMENT_METHOD_LOWEST_FEES}
    )

    # Test gamePageTrans parsing with None values (which caused the float() TypeError)
    game_data = coordinator._extract_game_page_trans(html)
    offers_js = coordinator._parse_game_page_trans(game_data, "http://example.com")

    # Should successfully parse 47.00 since the first offer's prices are None
    assert abs(offers_js["low_price"] - 47.00) < 0.01

    # Test JSON-LD parsing with null lowPrice
    product_data = coordinator._extract_json_ld(html)
    offers_ld = coordinator._parse_offers(product_data, "http://example.com")

    assert offers_ld["low_price"] is None
