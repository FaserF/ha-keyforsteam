"""KeyForSteam sensor using AllKeyShop JSON-LD structured data."""
import logging
import re
import json
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant
import async_timeout
import aiohttp
from datetime import timedelta

_LOGGER = logging.getLogger(__name__)

DOMAIN = "keyforsteam"
UPDATE_INTERVAL = timedelta(hours=1)

# Base URLs for product pages
KEYFORSTEAM_URL = "https://www.keyforsteam.de/{slug}-key-kaufen-preisvergleich/"
ALLKEYSHOP_URL = "https://www.allkeyshop.com/blog/buy-{slug}-cd-key-compare-prices/"


class KeyforSteamDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching KeyforSteam data from JSON-LD."""

    def __init__(self, hass: HomeAssistant, product_id: str, currency: str):
        """Initialize the data update coordinator."""
        self.product_id = product_id
        self.currency = currency.lower()
        super().__init__(
            hass,
            _LOGGER,
            name="KeyforSteamDataUpdateCoordinator",
            update_interval=UPDATE_INTERVAL
        )

    def _build_product_url(self):
        """Build product page URL from product_id (slug or URL)."""
        product_id = self.product_id.strip()

        # If already a URL, use it directly
        if product_id.startswith("http"):
            return product_id

        # Create slug from product name
        slug = product_id.lower()
        slug = re.sub(r'[^a-z0-9]+', '-', slug)
        slug = slug.strip('-')

        # Use KeyForSteam for EUR, AllKeyShop for USD
        if self.currency == "eur":
            return KEYFORSTEAM_URL.format(slug=slug)
        else:
            return ALLKEYSHOP_URL.format(slug=slug)

    def _extract_json_ld(self, html):
        """Extract JSON-LD Product schema from HTML."""
        # Find all JSON-LD script blocks
        pattern = r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>'
        matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)

        for match in matches:
            try:
                data = json.loads(match)
                # Check if this is a Product schema
                if isinstance(data, dict):
                    if data.get("@type") == "Product":
                        return data
                    # Check in @graph array
                    if "@graph" in data:
                        for item in data["@graph"]:
                            if isinstance(item, dict) and item.get("@type") == "Product":
                                return item
            except json.JSONDecodeError:
                continue

        return None

    def _parse_offers(self, product_data):
        """Parse offers from Product JSON-LD schema."""
        offers_data = product_data.get("offers", {})

        result = {
            "product_id": product_data.get("@id"),
            "name": product_data.get("name"),
            "image": product_data.get("image"),
            "low_price": None,
            "high_price": None,
            "currency": "EUR",
            "offer_count": 0,
            "offers": [],
            "rating": None,
        }

        # Parse aggregate rating
        rating_data = product_data.get("aggregateRating", {})
        if rating_data:
            result["rating"] = {
                "value": rating_data.get("ratingValue"),
                "count": rating_data.get("ratingCount"),
            }

        # Handle AggregateOffer
        if offers_data.get("@type") == "AggregateOffer":
            result["low_price"] = offers_data.get("lowPrice")
            result["high_price"] = offers_data.get("highPrice")
            result["currency"] = offers_data.get("priceCurrency", "EUR")
            result["offer_count"] = offers_data.get("offerCount", 0)

            # Parse individual offers
            individual_offers = offers_data.get("offers", [])
            for offer in individual_offers:
                if isinstance(offer, dict):
                    seller = offer.get("seller", {})
                    result["offers"].append({
                        "price": float(offer.get("price", 0)),
                        "currency": offer.get("priceCurrency", "EUR"),
                        "seller": seller.get("name") if isinstance(seller, dict) else str(seller),
                        "availability": "InStock" if "InStock" in str(offer.get("availability", "")) else "Unknown",
                    })

        # Sort offers by price
        result["offers"].sort(key=lambda x: x.get("price", float('inf')))

        return result

    async def _async_update_data(self):
        """Fetch data from product page JSON-LD."""
        url = self._build_product_url()
        _LOGGER.debug("Fetching product data from: %s", url)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
        }

        async with aiohttp.ClientSession() as session:
            async with async_timeout.timeout(30):
                try:
                    async with session.get(url, headers=headers) as response:
                        if response.status == 404:
                            _LOGGER.error("Product page not found: %s", url)
                            raise Exception(f"Product page not found: {url}")
                        response.raise_for_status()
                        html = await response.text()

                        # Extract JSON-LD Product data
                        product_data = self._extract_json_ld(html)
                        if not product_data:
                            _LOGGER.error("No Product JSON-LD found on page: %s", url)
                            raise Exception("No Product data found on page")

                        # Parse offers
                        offers = self._parse_offers(product_data)
                        _LOGGER.debug("Found %d offers, lowest price: %s %s",
                                     len(offers["offers"]),
                                     offers.get("low_price"),
                                     offers.get("currency"))

                        return offers

                except aiohttp.ClientResponseError as e:
                    _LOGGER.error("HTTP error fetching product page: %s", e)
                    raise
                except Exception as e:
                    _LOGGER.error("Error fetching KeyforSteam data: %s", e)
                    raise


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up the KeyforSteam sensor from a config entry."""
    _LOGGER.debug("Setting up KeyforSteam sensor for entry: %s", entry.entry_id)

    product_id = entry.data.get("product_id")
    currency = entry.data.get("currency", "eur").lower()

    coordinator = KeyforSteamDataUpdateCoordinator(hass, product_id, currency)

    try:
        await coordinator.async_refresh()
        _LOGGER.debug("Data fetched successfully for sensor.")
    except Exception as e:
        _LOGGER.error("Error during coordinator refresh: %s", e)
        return False

    sensor = KeyforSteamSensor(coordinator, entry.title)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    async_add_entities([sensor], update_before_add=True)


class KeyforSteamSensor(SensorEntity):
    """Representation of a KeyforSteam sensor."""

    def __init__(self, coordinator, name):
        """Initialize the sensor."""
        self._coordinator = coordinator
        self._name = f"KeyforSteam {coordinator.product_id}"
        self._state = None
        self._attributes = {}
        _LOGGER.debug("Initializing sensor: %s", name)

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def unique_id(self):
        """Return a unique ID for the sensor."""
        return f"keyforsteam_{self._coordinator.product_id}"

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement based on the currency."""
        if self._coordinator.data:
            currency = self._coordinator.data.get("currency", "EUR")
            return "€" if currency == "EUR" else "$"
        return "€"

    @property
    def icon(self):
        """Return the icon for the sensor."""
        return "mdi:gamepad-variant"

    @property
    def state(self):
        """Return the lowest price."""
        if self._coordinator.data:
            low_price = self._coordinator.data.get("low_price")
            if low_price is not None:
                return low_price
        _LOGGER.warning("No data available for state.")
        return None

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = {}
        if self._coordinator.data:
            data = self._coordinator.data

            attributes["product_name"] = data.get("name")
            attributes["product_id"] = data.get("product_id")
            attributes["low_price"] = data.get("low_price")
            attributes["high_price"] = data.get("high_price")
            attributes["currency"] = data.get("currency")
            attributes["offer_count"] = data.get("offer_count")

            # Rating info
            rating = data.get("rating")
            if rating:
                attributes["rating"] = rating.get("value")
                attributes["rating_count"] = rating.get("count")

            # Best offer details
            offers = data.get("offers", [])
            if offers:
                best_offer = offers[0]  # Already sorted by price
                attributes["best_seller"] = best_offer.get("seller")
                attributes["best_price"] = best_offer.get("price")

                # Top 5 offers summary
                top_offers = []
                for offer in offers[:5]:
                    top_offers.append(f"{offer.get('seller')}: {offer.get('price')}€")
                attributes["top_offers"] = top_offers

        return attributes

    @property
    def device_info(self):
        """Return device information for grouping sensors."""
        return {
            "identifiers": {(DOMAIN, "keyforsteam_group")},
            "name": "KeyforSteam",
            "manufacturer": "AllKeyShop",
            "model": "Game Price Tracker",
            "entry_type": "service",
        }

    async def async_update(self):
        """Fetch new state data for the sensor."""
        await self._coordinator.async_refresh()
