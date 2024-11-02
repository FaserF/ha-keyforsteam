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
UPDATE_INTERVAL = timedelta(minutes=10)

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
                            # Direkt Zugriff auf die Listen, falls sie bereits Listen sind
                            editions = data.get("editions", [])
                            merchants = data.get("merchants", [])
                            offers = data.get("offers", [])
                            # _LOGGER.debug("Data fetched successfully: %s", data)
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
    currency = entry.data.get("currency", "eur")

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
        self._name = name
        self._state = None
        self._attributes = {}
        _LOGGER.debug("Initializing sensor: %s", name)

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the price of the cheapest offer."""
        if self._coordinator.data:
            offers, merchants, editions = self._coordinator.data
            cheapest_offer = self._find_cheapest_offer(offers)
            if cheapest_offer:
                # Access the price correctly
                _LOGGER.debug("Handling lowest price: %s", cheapest_offer)
                price = cheapest_offer['price']
                return price
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

                if merchant_id:
                    merchant_info = next((merchant for merchant in merchants if merchant.get('id') == merchant_id), None)
                    if merchant_info:
                        attributes['merchant_name'] = merchant_info.get("name")
                        attributes['payment_methods'] = merchant_info.get("paymentMethods", [])

                if edition_id:
                    edition_info = next((edition for edition in editions if edition.get('id') == edition_id), None)
                    if edition_info:
                        attributes['edition_name'] = edition_info.get("name")

                attributes['cheapest_offer'] = cheapest_offer

        return attributes

    async def async_update(self):
        """Fetch new state data for the sensor."""
        await self._coordinator.async_refresh()

    def _find_cheapest_offer(self, offers):
        """Find the cheapest offer from the list of offers."""
        _LOGGER.debug("Offers data received: %s", offers)
        lowest_offer = None
        lowest_price = float('inf')  # Initialize to a very high number

        for offer in offers:
            # Extract the price from the offer
            price = offer['price']['eur']['price']

            # Check if the current offer's price is lower than the lowest found
            if price < lowest_price:
                lowest_price = price
                lowest_offer = offer

        _LOGGER.debug("Handling lowest offer: %s", lowest_offer)

        if lowest_offer:
            # Extract relevant information
            lowest_price_info = {
                'price': lowest_price,
                'priceCard': lowest_offer['price']['eur']['priceCard'],
                'merchant': lowest_offer['merchant'],
                'edition': lowest_offer['edition'],
                'coupon': lowest_offer['price']['eur']['bestCoupon']['code'] if lowest_offer['price']['eur']['bestCoupon'] else None
            }
            return lowest_price_info
        else:
            return None
