import logging
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

class KeyforSteamDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching KeyforSteam data."""

    def __init__(self, hass: HomeAssistant, product_id: str, currency: str):
        """Initialize the data update coordinator."""
        self.product_id = product_id
        self.currency = currency
        super().__init__(
            hass,
            _LOGGER,
            name="KeyforSteamDataUpdateCoordinator",
            update_interval=UPDATE_INTERVAL
        )

    async def _async_update_data(self):
        """Fetch data from KeyforSteam."""
        url = f"https://www.keyforsteam.de/wp-admin/admin-ajax.php?action=get_offers&product={self.product_id}&currency={self.currency}&use_beta_offers_display=1"

        async with aiohttp.ClientSession() as session:
            async with async_timeout.timeout(10):
                try:
                    async with session.get(url) as response:
                        response.raise_for_status()
                        data = await response.json()
                        if data.get("success"):
                            editions = list(data.get("editions", {}).values())
                            merchants = list(data.get("merchants", {}).values())
                            offers = data.get("offers", [])
                            _LOGGER.debug("Data fetched successfully from: %s", url)
                            return offers, merchants, editions
                        else:
                            _LOGGER.error("Error fetching data: %s", data.get("message", "Unknown error"))
                            raise Exception("Failed to fetch data from KeyforSteam")
                except Exception as e:
                    _LOGGER.error("Exception occurred while fetching KeyforSteam data: %s", e)
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
        currency = self._coordinator.currency.lower()
        return "€" if currency == "eur" else "$"

    @property
    def icon(self):
        """Return the icon for the sensor."""
        return "mdi:gamepad-variant"

    @property
    def state(self):
        """Return the price of the cheapest offer."""
        if self._coordinator.data:
            offers, merchants, editions = self._coordinator.data
            cheapest_offer = self._find_cheapest_offer(offers)
            if cheapest_offer:
                _LOGGER.debug("Handling lowest price: %s", cheapest_offer)
                return cheapest_offer['price']
        _LOGGER.warning("No data available for state.")
        return None

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = {}
        if self._coordinator.data:
            offers, merchants, editions = self._coordinator.data

            cheapest_offer = self._find_cheapest_offer(offers)
            if cheapest_offer:
                merchant_id = cheapest_offer.get('merchant')
                edition_id = cheapest_offer.get('edition')

                attributes['priceBase'] = cheapest_offer['price']
                attributes['priceCard'] = cheapest_offer['priceCard']
                attributes['pricePaypal'] = cheapest_offer['pricePaypal']
                attributes['coupon'] = cheapest_offer['coupon']

                merchant_info = next(
                    (merchant for merchant in merchants if isinstance(merchant, dict) and merchant.get('id') == merchant_id),
                    None
                )
                if merchant_info:
                    attributes['merchant'] = merchant_info.get("name")
                    attributes['merchant_payment_methods'] = merchant_info.get("paymentMethods", [])
                else:
                    attributes['merchant'] = merchant_id
                    attributes['merchant_payment_methods'] = "unknown"

                edition_info = next(
                    (edition for edition in editions if isinstance(edition, dict) and edition.get('id') == edition_id),
                    None
                )
                if edition_info:
                    attributes['edition'] = edition_info.get("name")
                else:
                    attributes['edition'] = edition_id

        return attributes

    @property
    def device_info(self):
        """Return device information for grouping sensors."""
        return {
            "identifiers": {(DOMAIN, "keyforsteam_group")},
            "name": "KeyforSteam",
            "manufacturer": "KeyforSteam API",
            "model": "Game Price Tracker",
            "entry_type": "service",
        }

    async def async_update(self):
        """Fetch new state data for the sensor."""
        await self._coordinator.async_refresh()

    def _find_cheapest_offer(self, offers):
        """Find the cheapest offer from the list of offers."""
        _LOGGER.debug("Offers data received")
        lowest_offer = None
        lowest_price = float('inf')

        for offer in offers:
            price = offer.get('price', {}).get('eur', {}).get('price')
            if price is not None and price < lowest_price:
                lowest_price = price
                lowest_offer = offer

        if lowest_offer:
            return {
                'price': lowest_price,
                'priceCard': lowest_offer.get('price', {}).get('eur', {}).get('priceCard'),
                'pricePaypal': lowest_offer.get('price', {}).get('eur', {}).get('pricePaypal'),
                'merchant': lowest_offer.get('merchant'),
                'edition': lowest_offer.get('edition'),
                'coupon': (
                    lowest_offer.get('price', {})
                    .get('eur', {})
                    .get('bestCoupon', {})
                    .get('code') if lowest_offer and 
                                lowest_offer.get('price') and 
                                lowest_offer.get('price').get('eur') and 
                                lowest_offer.get('price').get('eur').get('bestCoupon') 
                    else None
                ),
            }
        return None
