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
                            editions = list(data.get("editions", {}).values())
                            merchants = list(data.get("merchants", {}).values())
                            _LOGGER.debug("Data fetched successfully: %s", data)
                            return editions, merchants
                        else:
                            _LOGGER.error("Error fetching data: %s", data.get("message", "Unknown error"))
                            raise Exception("Failed to fetch data from KeyforSteam")
                except Exception as e:
                    _LOGGER.error("Exception occurred while fetching KeyforSteam data: %s", e)
                    raise

async def async_setup_platform(hass: HomeAssistant, config: dict, async_add_entities: AddEntitiesCallback, discovery_info=None):
    """Set up the KeyforSteam sensor platform."""
    if discovery_info is None:
        _LOGGER.error("No discovery info provided; cannot set up platform.")
        return

    product_id = discovery_info["product_id"]
    currency = discovery_info.get("currency", "eur")
    coordinator = KeyforSteamDataUpdateCoordinator(hass, product_id, currency)

    # Initial data fetch
    try:
        await coordinator.async_refresh()
        _LOGGER.debug("Initial data fetched successfully for product_id: %s", product_id)
    except Exception as e:
        _LOGGER.error("Error during coordinator refresh: %s", e)
        return

    sensor = KeyforSteamSensor(coordinator, discovery_info['name'])
    async_add_entities([sensor], update_before_add=True)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up the KeyforSteam sensor from a config entry."""
    _LOGGER.debug("Setting up KeyforSteam sensor for entry: %s", entry.entry_id)

    product_id = entry.data.get("product_id")
    currency = entry.data.get("currency", "eur")

    coordinator = KeyforSteamDataUpdateCoordinator(hass, product_id, currency)

    # Initial refresh
    try:
        await coordinator.async_refresh()
        _LOGGER.debug("Data fetched successfully for sensor.")
    except Exception as e:
        _LOGGER.error("Error during coordinator refresh: %s", e)
        return False

    if coordinator.data is None:
        _LOGGER.error("Coordinator returned no data after refresh.")
        return False

    # Logging the fetched data
    _LOGGER.debug("Coordinator data: %s", coordinator.data)

    sensor = KeyforSteamSensor(coordinator, entry.title)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    _LOGGER.debug("Adding sensor entity: %s", sensor.name)
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
            cheapest_offer = self._find_cheapest_offer(self._coordinator.data[0])
            if cheapest_offer:
                return cheapest_offer.get("price")  # Ensure "price" exists
        return None  # Return None if no price available

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if self._coordinator.data:
            cheapest_offer = self._find_cheapest_offer(self._coordinator.data[0])
            if cheapest_offer:
                merchant_id = cheapest_offer.get("merchant_id")
                if merchant_id:
                    merchant_info = next((merchant for merchant in self._coordinator.data[1] if merchant['id'] == merchant_id), None)
                    if merchant_info:
                        self._attributes['merchant_name'] = merchant_info.get("name")
                        self._attributes['payment_methods'] = merchant_info.get("paymentMethods", [])

                self._attributes['cheapest_offer'] = cheapest_offer

        return self._attributes

    async def async_update(self):
        """Fetch new state data for the sensor."""
        await self._coordinator.async_refresh()
        _LOGGER.debug("Sensor updated with data: %s", self._coordinator.data)

    def _find_cheapest_offer(self, offers):
        """Find the cheapest offer from the list of offers."""
        _LOGGER.debug("Offers data received: %s", offers)

        if not isinstance(offers, list):
            _LOGGER.error("Expected a list of offers, but got: %s", type(offers))
            return None  # Or return an appropriate default value

        if not offers:
            return None

        # Search for the cheapest offer and ensure "price" exists
        cheapest = min((offer for offer in offers if "price" in offer), key=lambda x: x.get("price", float('inf')), default=None)
        return cheapest
