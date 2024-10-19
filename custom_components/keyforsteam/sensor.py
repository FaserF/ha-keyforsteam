import logging
import requests
import async_timeout
from datetime import timedelta
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.const import CONF_NAME
from .const import DOMAIN, DEFAULT_CURRENCY, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry):
    """Set up the sensor from a config entry."""
    product_id = entry.data.get("product_id")
    currency = entry.data.get("currency", DEFAULT_CURRENCY)

    _LOGGER.debug("Setting up sensor for product_id: %s, currency: %s", product_id, currency)

    # Create the data update coordinator
    coordinator = KeyforSteamDataUpdateCoordinator(hass, product_id, currency)

    # Refresh coordinator data
    try:
        await coordinator.async_refresh()
    except Exception as e:
        _LOGGER.error("Error during coordinator refresh: %s", e)
        return False

    if coordinator.data is None:
        _LOGGER.error("Coordinator returned no data after refresh.")
        return False

    # Log the coordinator data after refreshing
    _LOGGER.debug("Coordinator data after refresh: %s", coordinator.data)

    # Create and register the sensor
    sensor = KeyforSteamSensor(coordinator, entry.title)
    if sensor is None:
        _LOGGER.error("Failed to create sensor for KeyforSteam entry.")
        return False

    # Store the sensor in the data structure
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    hass.data[DOMAIN]["sensor"] = sensor

    # Load the sensor platform
    await hass.helpers.discovery.async_load_platform("sensor", DOMAIN, {}, hass.data[DOMAIN])
    _LOGGER.debug("Sensor platform loaded for KeyforSteam.")
    return True

class KeyforSteamDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching KeyforSteam data from the API."""

    def __init__(self, hass, product_id, currency):
        super().__init__(
            hass,
            _LOGGER,
            name="KeyforSteam",
            update_interval=timedelta(seconds=SCAN_INTERVAL),
        )
        self.product_id = product_id
        self.currency = currency

    async def _async_update_data(self):
        """Fetch data from KeyforSteam API."""
        base_url = "https://www.keyforsteam.de/wp-admin/admin-ajax.php?action=get_offers&product={}&currency={}&use_beta_offers_display=1"
        if self.currency == "USD":
            base_url = base_url.replace("www.keyforsteam.de", "www.keyforsteam.com")

        url = base_url.format(self.product_id, self.currency)
        _LOGGER.debug("Fetching data from URL: %s", url)

        try:
            with async_timeout.timeout(30):
                response = await self.hass.async_add_executor_job(requests.get, url)
                response.raise_for_status()
        except requests.exceptions.HTTPError as http_err:
            _LOGGER.error("HTTP error occurred while fetching data: %s", http_err)
            return None
        except Exception as e:
            _LOGGER.error("Error fetching data: %s", e)
            return None

        try:
            data = response.json()
            _LOGGER.debug("Response data: %s", data)
        except ValueError as json_err:
            _LOGGER.error("Failed to parse JSON response: %s", json_err)
            return None

        if not data.get("success"):
            _LOGGER.error("API response was not successful: %s", data)
            raise Exception("Failed to fetch data from KeyforSteam")

        offers = data.get("offers", [])
        if not offers:
            _LOGGER.warning("No offers found in the response.")
            return None

        lowest_price = min(
            (offer["price"]["eur"]["price"] for offer in offers if offer.get("price", {}).get("eur", {}).get("price") is not None),
            default=None
        )
        _LOGGER.debug("Lowest price fetched: %s", lowest_price)
        return lowest_price

class KeyforSteamSensor(SensorEntity):
    """Representation of a KeyforSteam sensor."""

    def __init__(self, coordinator, name):
        self.coordinator = coordinator
        self._attr_name = f"{name} lowest price"
        self._attr_unique_id = f"keyforsteam_{self.coordinator.product_id}"
        self._attr_state = None
        self._attr_attributes = {}

    @property
    def state(self):
        """Return the state of the sensor."""
        return self.coordinator.data

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attr_attributes

    async def async_update(self):
        """Update the sensor state."""
        _LOGGER.debug("Updating sensor state for: %s", self._attr_name)
        await self.coordinator.async_refresh()
        self._attr_state = self.coordinator.data
        _LOGGER.debug("Updated sensor state: %s", self._attr_state)

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        self.async_on_remove(
            async_track_time_interval(
                self.hass,
                self.async_update,
                timedelta(seconds=SCAN_INTERVAL)
            )
        )
