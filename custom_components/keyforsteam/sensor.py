import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant
import asyncio
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
            name="KeyforSteamDataUpdateCoordinator",  # Name hinzugefügt
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
                        _LOGGER.debug("Fetched data: %s", data)  # Debug log for fetched data
                        if data.get("success"):
                            return data.get("editions"), data.get("merchants")
                        else:
                            _LOGGER.error("Error fetching data: %s", data.get("message", "Unknown error"))
                            raise Exception("Failed to fetch data from KeyforSteam")
                except Exception as e:
                    _LOGGER.error("Exception occurred while fetching KeyforSteam data: %s", e)
                    raise

async def async_setup_platform(hass: HomeAssistant, config: dict, async_add_entities, discovery_info=None):
    """Set up the KeyforSteam sensor platform."""
    _LOGGER.debug("Setting up KeyforSteam sensor platform.")
    if discovery_info is None:
        return

    product_id = discovery_info["product_id"]
    currency = discovery_info.get("currency", "eur")
    coordinator = KeyforSteamDataUpdateCoordinator(hass, product_id, currency)

    # Initial data fetch
    try:
        await coordinator.async_refresh()
        _LOGGER.debug("Coordinator data after refresh: %s", coordinator.data)
    except Exception as e:
        _LOGGER.error("Error during coordinator refresh: %s", e)
        return

    # Create and add the sensor
    sensor = KeyforSteamSensor(coordinator, discovery_info['name'])
    async_add_entities([sensor], update_before_add=True)
    _LOGGER.debug("Added KeyforSteam sensor: %s", sensor.name)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up the KeyforSteam sensor from a config entry."""
    product_id = entry.data.get("product_id")
    currency = entry.data.get("currency", "eur")

    _LOGGER.debug("Setting up KeyforSteam sensor for product_id: %s, currency: %s", product_id, currency)

    # Create the data update coordinator
    coordinator = KeyforSteamDataUpdateCoordinator(hass, product_id, currency)

    # Initial refresh
    try:
        await coordinator.async_refresh()
    except Exception as e:
        _LOGGER.error("Error during coordinator refresh: %s", e)
        return False

    if coordinator.data is None:
        _LOGGER.error("Coordinator returned no data after refresh.")
        return False

    _LOGGER.debug("Coordinator data after refresh: %s", coordinator.data)

    # Create and register the sensor
    sensor = KeyforSteamSensor(coordinator, entry.title)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = sensor

    async_add_entities([sensor], update_before_add=True)
    _LOGGER.debug("Successfully set up KeyforSteam sensor.")
    return True

class KeyforSteamSensor(SensorEntity):
    """Representation of a KeyforSteam sensor."""

    def __init__(self, coordinator, name):
        """Initialize the sensor."""
        self._coordinator = coordinator
        self._name = name
        self._state = None
        _LOGGER.debug("Initializing sensor: %s", name)  # Debug log for sensor initialization

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._coordinator.data

    async def async_update(self):
        """Fetch new state data for the sensor."""
        await self._coordinator.async_refresh()
        _LOGGER.debug("Sensor updated with data: %s", self._coordinator.data)  # Debug log for update data
        self._state = self._coordinator.data
