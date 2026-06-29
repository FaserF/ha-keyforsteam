"""KeyForSteam sensor using AllKeyShop JSON-LD structured data."""

import logging
import re
import json
import random
import asyncio
from datetime import datetime, timedelta

import aiohttp

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.device_registry import DeviceEntryType

from .const import (
    DOMAIN,
    KEYFORSTEAM_PRODUCT_URL,
    ALLKEYSHOP_PRODUCT_URL,
    CONF_PRODUCT_ID,
    CONF_PRODUCT_NAME,
    CONF_PRODUCT_SLUG,
    CONF_CURRENCY,
    CONF_ALLOW_ACCOUNTS,
    CONF_IGNORE_UNREALISTIC_PRICES,
    CONF_PAYMENT_METHOD,
    CONF_UPDATE_INTERVAL,
    PAYMENT_METHOD_CARD,
    PAYMENT_METHOD_PAYPAL,
    PAYMENT_METHOD_LOWEST_FEES,
    UPDATE_INTERVAL_HOURS,
    REPAIR_THRESHOLD_HOURS,
    REPAIR_API_FAILURE,
    REPAIR_PRODUCT_NOT_FOUND,
    ISSUE_TRACKER_URL,
    CLOUDFLARE_BACKOFF_HOURS,
    MAX_RETRIES,
)

# Markers that indicate a Cloudflare/bot-detection page (applies to both
# non-200 responses AND to 200 responses that are challenge pages).
CLOUDFLARE_MARKERS = [
    "ray id",
    "captcha-bypass",
    "ddos guard",
    "sucuri",
    "just a moment",
    "checking your browser",
    "please wait",
    "enable javascript and cookies",
    "challenge-form",
    "cf-browser-verification",
    "cf-challenge",
    "cloudflare-challenge",
]

USER_AGENTS = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    # Safari on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
]

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(hours=UPDATE_INTERVAL_HOURS)


def safe_float(value, default=0.0) -> float:
    """Safely convert a value to float, handling None, string, etc."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class KeyforSteamDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching KeyforSteam data from JSON-LD."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        """Initialize the data update coordinator."""
        self.entry = entry
        self.product_id = entry.data.get(CONF_PRODUCT_ID, "")
        self.product_name = entry.data.get(CONF_PRODUCT_NAME, "")
        self.product_slug = entry.data.get(CONF_PRODUCT_SLUG, "")
        self.currency = entry.data.get(CONF_CURRENCY, "eur").lower()

        # Merge options and data for settings
        self.allow_accounts = entry.options.get(
            CONF_ALLOW_ACCOUNTS, entry.data.get(CONF_ALLOW_ACCOUNTS, False)
        )
        self.ignore_unrealistic_prices = entry.options.get(
            CONF_IGNORE_UNREALISTIC_PRICES,
            entry.data.get(CONF_IGNORE_UNREALISTIC_PRICES, True),
        )
        self.payment_method = entry.options.get(
            CONF_PAYMENT_METHOD,
            entry.data.get(CONF_PAYMENT_METHOD, PAYMENT_METHOD_LOWEST_FEES),
        )
        self.update_interval_hours = entry.options.get(
            CONF_UPDATE_INTERVAL,
            entry.data.get(CONF_UPDATE_INTERVAL, UPDATE_INTERVAL_HOURS),
        )

        # Failure tracking for HA Repairs
        self.consecutive_failures = 0
        self.last_successful_fetch: datetime | None = None
        self.api_repair_created = False
        self.not_found_repair_created = False

        # Backoff tracking: when a Cloudflare block is detected, we set this
        # to a future datetime and skip all requests until it has elapsed.
        # This persists as long as the coordinator object is alive (i.e. until
        # the next full HA restart), which is intentional – the ban typically
        # lasts hours, not seconds.
        self._backoff_until: datetime | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=f"KeyforSteam_{self.product_id}",
            update_interval=timedelta(hours=self.update_interval_hours),
        )

    def _build_product_url(self):
        """Build product page URL from product slug or name."""
        if self.product_slug:
            slug = self.product_slug
        elif self.product_name:
            slug = self.product_name.lower()
            slug = re.sub(r"[^a-z0-9]+", "-", slug)
            slug = slug.strip("-")
        else:
            if not str(self.product_id).isdigit():
                slug = self.product_id.lower()
                slug = re.sub(r"[^a-z0-9]+", "-", slug)
                slug = slug.strip("-")
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
                # Clean up the match (sometimes has leading/trailing garbage)
                match = match.strip()
                if not match:
                    continue
                data = json.loads(match)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get("@type") == "Product":
                            return item
                elif isinstance(data, dict):
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
        """Parse offers from Product JSON-LD schema."""
        offers_data = product_data.get("offers")
        if not isinstance(offers_data, dict):
            offers_data = {}

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

        rating_data = product_data.get("aggregateRating")
        if isinstance(rating_data, dict):
            result["rating"] = {
                "value": rating_data.get("ratingValue"),
                "count": rating_data.get("count") or rating_data.get("ratingCount"),
            }

        if offers_data.get("@type") == "AggregateOffer":
            result["low_price"] = safe_float(offers_data.get("lowPrice"), None)
            result["high_price"] = safe_float(offers_data.get("highPrice"), None)
            result["currency"] = offers_data.get("priceCurrency", "EUR")
            result["offer_count"] = offers_data.get("offerCount", 0)

            individual_offers = offers_data.get("offers", [])
            for offer in individual_offers:
                if isinstance(offer, dict):
                    seller = offer.get("seller", {})
                    result["offers"].append(
                        {
                            "price": safe_float(offer.get("price")),
                            "currency": offer.get("priceCurrency", "EUR"),
                            "seller": (
                                seller.get("name")
                                if isinstance(seller, dict)
                                else str(seller)
                            ),
                            "availability": (
                                "InStock"
                                if "InStock" in str(offer.get("availability", ""))
                                else "Unknown"
                            ),
                        }
                    )

        result["offers"].sort(key=lambda x: x.get("price", float("inf")))

        return result

    def _extract_game_page_trans(self, html):
        """Extract gamePageTrans JSON from the page source."""
        try:
            match = re.search(r"var gamePageTrans\s*=\s*(\{.*?\});", html, re.DOTALL)
            if match:
                return json.loads(match.group(1))
        except Exception as e:
            _LOGGER.error("Error parsing gamePageTrans: %s", e)
        return None

    def _parse_game_page_trans(self, game_data, url):
        """Parse offers from gamePageTrans JS object."""
        if not isinstance(game_data, dict):
            return None
        prices = game_data.get("prices")
        if not isinstance(prices, list):
            prices = []

        # Filter and map based on settings
        filtered_prices = []
        for p in prices:
            is_account = p.get("account", False)
            if not self.allow_accounts and is_account:
                continue

            # Select price based on payment method safely
            price_val = safe_float(p.get("price"))
            if self.payment_method == PAYMENT_METHOD_CARD:
                price_val = safe_float(p.get("priceCard")) or safe_float(p.get("price"))
            elif self.payment_method == PAYMENT_METHOD_PAYPAL:
                price_val = safe_float(p.get("pricePaypal")) or safe_float(
                    p.get("price")
                )
            elif self.payment_method == PAYMENT_METHOD_LOWEST_FEES:
                # Find the absolute minimum across fee-inclusive fields safely.
                price_fields = []
                if p.get("priceCard") is not None:
                    card_price = safe_float(p.get("priceCard"))
                    if card_price > 0:
                        price_fields.append(card_price)
                if p.get("pricePaypal") is not None:
                    paypal_price = safe_float(p.get("pricePaypal"))
                    if paypal_price > 0:
                        price_fields.append(paypal_price)

                if price_fields:
                    price_val = min(price_fields)
                else:
                    price_val = safe_float(p.get("price"))

            # Create a copy with the selected price as 'effective_price'
            if price_val <= 0:
                continue
            entry = dict(p)
            entry["effective_price"] = price_val
            filtered_prices.append(entry)

        if not filtered_prices:
            return None

        # Sort filtered_prices by effective_price ascending
        filtered_prices.sort(key=lambda x: x["effective_price"])

        # Filter out unrealistic prices if option is active
        if self.ignore_unrealistic_prices:
            # 1. Filter out prices below 0.80
            filtered_prices = [
                p for p in filtered_prices if p["effective_price"] >= 0.80
            ]

            # 2. Filter out lowest price if difference is 70% or more compared to the second cheapest
            if len(filtered_prices) >= 2:
                p1 = filtered_prices[0]["effective_price"]
                p2 = filtered_prices[1]["effective_price"]
                if (p2 - p1) / p2 >= 0.70:
                    filtered_prices.pop(0)

        if not filtered_prices:
            return None

        # Find lowest and highest based on effective price
        low_price = filtered_prices[0]["effective_price"]
        high_price = max(p.get("effective_price", 0.0) for p in filtered_prices)

        result = {
            "product_id": self.product_id,
            "name": game_data.get("name") or self.product_name,
            "image": None,  # gamePageTrans doesn't have a clean image
            "product_url": url,
            "low_price": low_price,
            "high_price": high_price,
            "currency": self.currency.upper(),
            "offer_count": len(filtered_prices),
            "offers": [],
            "rating": None,
            "last_updated": datetime.now().isoformat(),
        }

        # Handle rating if available in merchants
        merchants = game_data.get("merchants")
        if not isinstance(merchants, dict):
            merchants = {}

        for p in filtered_prices:
            merchant_id = str(p.get("merchant"))
            merchant_info = merchants.get(merchant_id, {})
            result["offers"].append(
                {
                    "price": safe_float(p.get("effective_price")),
                    "currency": self.currency.upper(),
                    "seller": p.get("merchantName") or merchant_info.get("name"),
                    "availability": "InStock" if p.get("dispo") == 1 else "Unknown",
                    "is_account": p.get("account", False),
                }
            )

        result["offers"].sort(key=lambda x: x.get("price", float("inf")))
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
            hours_since_success: float = float(REPAIR_THRESHOLD_HOURS + 1)
        else:
            hours_since_success = (
                datetime.now() - self.last_successful_fetch
            ).total_seconds() / 3600

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
                "issue_url": ISSUE_TRACKER_URL,
            },
        )
        self.not_found_repair_created = True

    async def _async_update_data(self):
        """Fetch data from product page with retries, jitter, and anti-ban logic.

        Key design decisions to avoid Cloudflare bans:
        - Use the shared HA aiohttp session (has persistent cookies, not a fresh
          connection every time).
        - On a Cloudflare block: immediately abort retries and set a backoff
          timer. Return cached data so entities stay available.
        - On HA restart: _backoff_until is checked first, so no request is made
          while a backoff is active.
        - Max retries is deliberately low (MAX_RETRIES=2) to avoid hitting the
          server in a tight loop.
        """
        from homeassistant.helpers import aiohttp_client

        url = self._build_product_url()
        if not url:
            self.consecutive_failures += 1
            await self._handle_api_repair(True)
            raise UpdateFailed("Could not build product URL")

        # --- Backoff guard ---
        # If a Cloudflare block was detected previously, skip the request
        # entirely and return whatever data we already have.
        now = datetime.now()
        if self._backoff_until is not None and now < self._backoff_until:
            remaining = (self._backoff_until - now).total_seconds() / 3600
            _LOGGER.warning(
                "Skipping fetch for '%s': Cloudflare backoff active for another %.1f hour(s). "
                "Existing data will be preserved.",
                self.product_name or self.product_id,
                remaining,
            )
            # Return cached data to keep entities available
            if self.data is not None:
                return self.data
            raise UpdateFailed(
                f"Cloudflare backoff active for another {remaining:.1f} hour(s). "
                "Will retry automatically once the backoff expires."
            )

        # Use the shared HA session – it reuses cookies and looks more like a
        # real browser session than a freshly created ClientSession.
        session = aiohttp_client.async_get_clientsession(self.hass)

        last_error = None

        for attempt in range(1, MAX_RETRIES + 1):
            if attempt > 1:
                # Exponential backoff with jitter between retries
                backoff_delay = (2**attempt) + random.uniform(1.0, 3.0)
                _LOGGER.info(
                    "Retrying request to %s in %.2f seconds (attempt %d/%d)",
                    url,
                    backoff_delay,
                    attempt,
                    MAX_RETRIES,
                )
                await asyncio.sleep(backoff_delay)
            else:
                # Initial random delay to desynchronise from other integrations
                # and prevent request storms after HA restarts.
                initial_delay = random.uniform(2.0, 8.0)
                _LOGGER.debug(
                    "Waiting %.2f seconds before fetching '%s' to reduce bot fingerprint",
                    initial_delay,
                    self.product_name or self.product_id,
                )
                await asyncio.sleep(initial_delay)

            user_agent = random.choice(USER_AGENTS)

            headers = {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0",
            }

            _LOGGER.debug(
                "Attempt %d/%d: Fetching product data from: %s",
                attempt,
                MAX_RETRIES,
                url,
            )

            try:
                async with asyncio.timeout(15):
                    async with session.get(url, headers=headers) as response:
                        _LOGGER.debug("Response status: %d", response.status)

                        if response.status == 404:
                            _LOGGER.error(
                                "Product page not found (404) for URL: %s", url
                            )
                            self.consecutive_failures += 1
                            await self._handle_not_found_repair(True)
                            raise UpdateFailed(f"Product page not found: {url}")

                        # Non-200 status (e.g. 403, 429) – check for Cloudflare
                        if response.status != 200:
                            html_text = await response.text()
                            html_lower = html_text.lower()
                            is_cloudflare = any(
                                marker in html_lower for marker in CLOUDFLARE_MARKERS
                            )
                            error_msg = (
                                f"Access blocked (HTTP {response.status}) on attempt "
                                f"{attempt}/{MAX_RETRIES}."
                            )
                            if is_cloudflare:
                                error_msg += " Cloudflare/bot-protection page detected."
                                self._set_cloudflare_backoff()
                                _LOGGER.error(error_msg)
                                # Break out immediately – more retries will only make the ban worse
                                last_error = Exception(error_msg)
                                break

                            preview = html_text[:400].replace("\n", " ").strip()
                            error_msg += f" Response preview: {preview}"
                            _LOGGER.error(error_msg)
                            last_error = Exception(error_msg)
                            continue

                        response.raise_for_status()
                        html = await response.text()

                        # Even on HTTP 200, Cloudflare sometimes serves a
                        # challenge page. Detect and handle it like a block.
                        html_lower = html.lower()
                        if any(marker in html_lower for marker in CLOUDFLARE_MARKERS):
                            preview = html[:400].replace("\n", " ").strip()
                            error_msg = (
                                f"Cloudflare/bot-protection page detected (HTTP 200) on attempt "
                                f"{attempt}/{MAX_RETRIES}. Response preview: {preview}"
                            )
                            _LOGGER.error(error_msg)
                            self._set_cloudflare_backoff()
                            last_error = Exception(error_msg)
                            # Break immediately – retrying will not help and increases ban risk
                            break

                        # --- Parse the page ---
                        # 1. Always try JSON-LD for metadata
                        product_data = self._extract_json_ld(html)
                        offers = None
                        if product_data:
                            offers = self._parse_offers(product_data, url)

                        # 2. Try the richer gamePageTrans JS object for price data
                        game_data = self._extract_game_page_trans(html)
                        if game_data:
                            js_offers = self._parse_game_page_trans(game_data, url)
                            if js_offers:
                                if offers:
                                    # Merge: metadata from LD + prices from JS
                                    offers.update(
                                        {
                                            "low_price": js_offers["low_price"],
                                            "high_price": js_offers["high_price"],
                                            "offer_count": js_offers["offer_count"],
                                            "offers": js_offers["offers"],
                                        }
                                    )
                                else:
                                    offers = js_offers

                        if not offers:
                            _LOGGER.warning(
                                "Page loaded successfully but no game data found on attempt %d. "
                                "Page structure may have changed. HTML sample: %s",
                                attempt,
                                html[:300].replace("\n", " "),
                            )
                            last_error = Exception(
                                "Could not find any product data on page"
                            )
                            continue

                        # --- Success ---
                        self.consecutive_failures = 0
                        self.last_successful_fetch = datetime.now()
                        self._backoff_until = None  # Clear any previous backoff
                        await self._handle_api_repair(False)
                        await self._handle_not_found_repair(False)
                        return offers

            except aiohttp.ClientResponseError as e:
                _LOGGER.error(
                    "HTTP client response error on attempt %d: %s", attempt, e
                )
                last_error = e
                if e.status == 404:
                    self.consecutive_failures += 1
                    await self._handle_not_found_repair(True)
                    raise UpdateFailed(f"Product page not found: {e}")
            except asyncio.TimeoutError as e:
                _LOGGER.error("Timeout fetching URL on attempt %d: %s", attempt, e)
                last_error = e
            except UpdateFailed:
                raise  # propagate 404-triggered UpdateFailed immediately
            except Exception as e:
                _LOGGER.exception(
                    "Unexpected error fetching URL on attempt %d: %s", attempt, e
                )
                last_error = e

        # All attempts failed (or aborted due to Cloudflare block)
        self.consecutive_failures += 1
        await self._handle_api_repair(True)

        # If we have stale data, return it so entities stay available rather
        # than flipping to 'unavailable' on every blocked refresh.
        if self.data is not None:
            _LOGGER.warning(
                "All fetch attempts failed for '%s'. Preserving last known data. Last error: %s",
                self.product_name or self.product_id,
                last_error,
            )
            return self.data

        raise UpdateFailed(
            f"Failed to update data after {MAX_RETRIES} attempts. Last error: {last_error}"
        )

    def _set_cloudflare_backoff(self):
        """Set a backoff timestamp to avoid hammering a site that is blocking us."""
        self._backoff_until = datetime.now() + timedelta(hours=CLOUDFLARE_BACKOFF_HOURS)
        _LOGGER.warning(
            "Cloudflare/bot-protection block detected for '%s'. "
            "Backing off for %d hours until %s to prevent a ban. "
            "Existing sensor data will be preserved during this period.",
            self.product_name or self.product_id,
            CLOUDFLARE_BACKOFF_HOURS,
            self._backoff_until.strftime("%H:%M"),
        )


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up the KeyforSteam sensors from a config entry."""
    _LOGGER.debug("Setting up KeyforSteam sensors for entry: %s", entry.entry_id)

    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities = [
        KeyforSteamPriceSensor(coordinator, entry),
        KeyforSteamRatingSensor(coordinator, entry),
        KeyforSteamOfferCountSensor(coordinator, entry),
    ]
    async_add_entities(entities)


class KeyforSteamBaseEntity(SensorEntity):
    """Base class for KeyforSteam sensors."""

    _coordinator: KeyforSteamDataUpdateCoordinator

    def __init__(
        self, coordinator: KeyforSteamDataUpdateCoordinator, entry: ConfigEntry
    ):
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
            name=self._coordinator.product_name
            or f"Game {self._coordinator.product_id}",
            manufacturer="AllKeyShop",
            model="Game Price Tracker",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=(
                self._coordinator.data.get("product_url")
                if self._coordinator.data
                else None
            ),
        )

    async def async_added_to_hass(self):
        """Subscribe to updates."""
        self.async_on_remove(
            self._coordinator.async_add_listener(self.async_write_ha_state)
        )


class KeyforSteamPriceSensor(KeyforSteamBaseEntity):
    """Representation of a KeyforSteam price sensor."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:gamepad-variant"
    _attr_translation_key = "lowest_price"

    def __init__(
        self, coordinator: KeyforSteamDataUpdateCoordinator, entry: ConfigEntry
    ):
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

    _coordinator: KeyforSteamDataUpdateCoordinator
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:star"
    _attr_translation_key = "rating"
    _attr_entity_registry_enabled_default = False

    def __init__(
        self, coordinator: KeyforSteamDataUpdateCoordinator, entry: ConfigEntry
    ):
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

    _coordinator: KeyforSteamDataUpdateCoordinator
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:store"
    _attr_translation_key = "offer_count"
    _attr_entity_registry_enabled_default = False

    def __init__(
        self, coordinator: KeyforSteamDataUpdateCoordinator, entry: ConfigEntry
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"keyforsteam_{coordinator.product_id}_offer_count"

    @property
    def native_value(self):
        """Return the offer count."""
        if self._coordinator.data:
            return self._coordinator.data.get("offer_count")
        return None
