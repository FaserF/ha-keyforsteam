"""KeyForSteam sensor using AllKeyShop JSON-LD structured data."""
import logging
import re
import json
from datetime import datetime, timedelta
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
import async_timeout
import aiohttp

from .const import (
    DOMAIN,
    KEYFORSTEAM_PRODUCT_URL,
    ALLKEYSHOP_PRODUCT_URL,
    CONF_PRODUCT_ID,
    CONF_PRODUCT_NAME,
    CONF_PRODUCT_SLUG,
    CONF_CURRENCY,
    UPDATE_INTERVAL_HOURS,
    REPAIR_THRESHOLD_HOURS,
    REPAIR_API_FAILURE,
    REPAIR_PRODUCT_NOT_FOUND,
    ISSUE_TRACKER_URL,
)

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(hours=UPDATE_INTERVAL_HOURS)


class KeyforSteamDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching KeyforSteam data from JSON-LD."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        """Initialize the data update coordinator."""
        self.entry = entry
        self.product_id = entry.data.get(CONF_PRODUCT_ID, "")
        self.product_name = entry.data.get(CONF_PRODUCT_NAME, "")
        self.product_slug = entry.data.get(CONF_PRODUCT_SLUG, "")
        self.currency = entry.data.get(CONF_CURRENCY, "eur").lower()

        # Failure tracking for HA Repairs
        self.consecutive_failures = 0
        self.last_successful_fetch = None
        self.api_repair_created = False
        self.not_found_repair_created = False

        super().__init__(
            hass,
            _LOGGER,
            name=f"KeyforSteam_{self.product_id}",
            update_interval=UPDATE_INTERVAL
        )

    def _build_product_url(self):
        """Build product page URL from product slug or name."""
        if self.product_slug:
            slug = self.product_slug
        elif self.product_name:
            slug = self.product_name.lower()
            slug = re.sub(r'[^a-z0-9]+', '-', slug)
            slug = slug.strip('-')
        else:
            if not str(self.product_id).isdigit():
                slug = self.product_id.lower()
                slug = re.sub(r'[^a-z0-9]+', '-', slug)
                slug = slug.strip('-')
            else:
                _LOGGER.error("Cannot build URL: no slug or name available")
                return None

        if self.currency == "eur":
            return KEYFORSTEAM_PRODUCT_URL.format(slug=slug)
        else:
            return ALLKEYSHOP_PRODUCT_URL.format(slug=slug)

    def _extract_json_ld(self, html):
        """Extract JSON-LD Product schema from HTML."""
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
                            if isinstance(item, dict) and item.get("@type") == "Product":
                                return item
            except json.JSONDecodeError:
                continue

        return None

    def _parse_offers(self, product_data, url):
        """Parse offers from Product JSON-LD schema."""
        offers_data = product_data.get("offers", {})

        result = {
            "product_id": product_data.get("@id") or self.product_id,
            "name": product_data.get("name") or self.product_name,
            "image": product_data.get("image"),
            "product_url": url,
            "low_price": None,
            "high_price": None,
            "currency": "EUR",
            "offer_count": 0,
            "offers": [],
            "rating": None,
            "last_updated": datetime.now().isoformat(),
        }

        rating_data = product_data.get("aggregateRating", {})
        if rating_data:
            result["rating"] = {
                "value": rating_data.get("ratingValue"),
                "count": rating_data.get("ratingCount"),
            }

        if offers_data.get("@type") == "AggregateOffer":
            result["low_price"] = offers_data.get("lowPrice")
            result["high_price"] = offers_data.get("highPrice")
            result["currency"] = offers_data.get("priceCurrency", "EUR")
            result["offer_count"] = offers_data.get("offerCount", 0)

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

        result["offers"].sort(key=lambda x: x.get("price", float('inf')))

        return result

    async def _handle_api_repair(self, failed: bool):
        """Handle calculation and creation/resolution of API failure repair."""
        from homeassistant.helpers import issue_registry as ir
        issue_id = f"{REPAIR_API_FAILURE}_{self.product_id}"

        if not failed:
            if self.api_repair_created:
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)
                self.api_repair_created = False
            return

        if self.api_repair_created:
            return

        if self.last_successful_fetch is None:
            hours_since_success = REPAIR_THRESHOLD_HOURS + 1
        else:
            hours_since_success = (datetime.now() - self.last_successful_fetch).total_seconds() / 3600

        if hours_since_success >= REPAIR_THRESHOLD_HOURS:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                is_persistent=True,
                severity=ir.IssueSeverity.WARNING,
                translation_key=REPAIR_API_FAILURE,
                translation_placeholders={"issue_url": ISSUE_TRACKER_URL},
            )
            self.api_repair_created = True

    async def _handle_not_found_repair(self, is_404: bool):
        """Handle calculation and creation/resolution of 404 repair."""
        from homeassistant.helpers import issue_registry as ir
        issue_id = f"{REPAIR_PRODUCT_NOT_FOUND}_{self.product_id}"

        if not is_404:
            if self.not_found_repair_created:
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)
                self.not_found_repair_created = False
            return

        if self.not_found_repair_created:
            return

        ir.async_create_issue(
            self.hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            is_persistent=True,
            severity=ir.IssueSeverity.ERROR,
            translation_key=REPAIR_PRODUCT_NOT_FOUND,
            translation_placeholders={
                "product_name": self.product_name or self.product_id,
                "issue_url": ISSUE_TRACKER_URL
            },
        )
        self.not_found_repair_created = True

    async def _async_update_data(self):
        """Fetch data from product page JSON-LD."""
        url = self._build_product_url()
        if not url:
            self.consecutive_failures += 1
            await self._handle_api_repair(True)
            raise UpdateFailed("Could not build product URL")

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
                            self.consecutive_failures += 1
                            await self._handle_not_found_repair(True)
                            raise UpdateFailed(f"Product page not found: {url}")

                        response.raise_for_status()
                        html = await response.text()

                        product_data = self._extract_json_ld(html)
                        if not product_data:
                            self.consecutive_failures += 1
                            await self._handle_api_repair(True)
                            raise UpdateFailed("No Product data found on page")

                        offers = self._parse_offers(product_data, url)

                        # Success - reset failure tracking
                        self.consecutive_failures = 0
                        self.last_successful_fetch = datetime.now()
                        await self._handle_api_repair(False)
                        await self._handle_not_found_repair(False)

                        return offers

                except aiohttp.ClientResponseError as e:
                    self.consecutive_failures += 1
                    if e.status == 404:
                        await self._handle_not_found_repair(True)
                    else:
                        await self._handle_api_repair(True)
                    raise UpdateFailed(f"HTTP error: {e}")
                except Exception as e:
                    self.consecutive_failures += 1
                    await self._handle_api_repair(True)
                    raise UpdateFailed(f"Error: {e}")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up the KeyforSteam sensors from a config entry."""
    _LOGGER.debug("Setting up KeyforSteam sensors for entry: %s", entry.entry_id)

    coordinator = KeyforSteamDataUpdateCoordinator(hass, entry)

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"coordinator": coordinator}

    entities = [
        KeyforSteamPriceSensor(coordinator, entry),
        KeyforSteamRatingSensor(coordinator, entry),
        KeyforSteamOfferCountSensor(coordinator, entry),
    ]
    async_add_entities(entities, update_before_add=True)


class KeyforSteamBaseEntity(SensorEntity):
    """Base class for KeyforSteam sensors."""

    def __init__(self, coordinator: KeyforSteamDataUpdateCoordinator, entry: ConfigEntry):
        """Initialize the sensor."""
        self._coordinator = coordinator
        self._entry = entry
        self._attr_has_entity_name = True

    @property
    def available(self):
        """Return if entity is available."""
        return self._coordinator.last_update_success

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for grouping sensors."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._coordinator.product_id)},
            name=self._coordinator.product_name or f"Game {self._coordinator.product_id}",
            manufacturer="AllKeyShop",
            model="Game Price Tracker",
            entry_type="service",
        )

    async def async_added_to_hass(self):
        """Subscribe to updates."""
        self.async_on_remove(
            self._coordinator.async_add_listener(self.async_write_ha_state)
        )


class KeyforSteamPriceSensor(KeyforSteamBaseEntity):
    """Representation of a KeyforSteam price sensor."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:gamepad-variant"
    _attr_translation_key = "lowest_price"

    def __init__(self, coordinator: KeyforSteamDataUpdateCoordinator, entry: ConfigEntry):
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"keyforsteam_{coordinator.product_id}_price"

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement based on the currency."""
        if self._coordinator.data:
            currency = self._coordinator.data.get("currency", "EUR")
            return {"EUR": "€", "USD": "$", "GBP": "£"}.get(currency, currency)
        return "€"

    @property
    def native_value(self):
        """Return the lowest price."""
        if self._coordinator.data:
            return self._coordinator.data.get("low_price")
        return None

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if not self._coordinator.data:
            return {}

        data = self._coordinator.data
        attributes = {
            "product_name": data.get("name"),
            "product_id": data.get("product_id"),
            "product_url": data.get("product_url"),
            "low_price": data.get("low_price"),
            "high_price": data.get("high_price"),
            "currency": data.get("currency"),
            "offer_count": data.get("offer_count"),
            "last_updated": data.get("last_updated"),
        }

        rating = data.get("rating")
        if rating:
            attributes["rating"] = rating.get("value")
            attributes["rating_count"] = rating.get("count")

        offers = data.get("offers", [])
        if offers:
            best_offer = offers[0]
            attributes["best_seller"] = best_offer.get("seller")
            attributes["best_price"] = best_offer.get("price")

            top_offers = []
            for offer in offers[:5]:
                top_offers.append(f"{offer.get('seller')}: {offer.get('price')}€")
            attributes["top_offers"] = top_offers
            attributes["all_offers"] = offers[:10]

        return attributes


class KeyforSteamRatingSensor(KeyforSteamBaseEntity):
    """Representation of a KeyforSteam rating sensor."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:star"
    _attr_translation_key = "rating"

    def __init__(self, coordinator: KeyforSteamDataUpdateCoordinator, entry: ConfigEntry):
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"keyforsteam_{coordinator.product_id}_rating"

    @property
    def native_value(self):
        """Return the rating."""
        if self._coordinator.data:
            rating_data = self._coordinator.data.get("rating")
            if rating_data:
                return rating_data.get("value")
        return None

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if not self._coordinator.data:
            return {}

        rating_data = self._coordinator.data.get("rating")
        if rating_data:
            return {"rating_count": rating_data.get("count")}
        return {}


class KeyforSteamOfferCountSensor(KeyforSteamBaseEntity):
    """Representation of a KeyforSteam offer count sensor."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:store"
    _attr_translation_key = "offer_count"

    def __init__(self, coordinator: KeyforSteamDataUpdateCoordinator, entry: ConfigEntry):
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"keyforsteam_{coordinator.product_id}_offer_count"

    @property
    def native_value(self):
        """Return the offer count."""
        if self._coordinator.data:
            return self._coordinator.data.get("offer_count")
        return None
