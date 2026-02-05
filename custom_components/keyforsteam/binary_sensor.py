"""Binary sensor for KeyforSteam price alerts."""
import logging
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    DOMAIN,
    CONF_PRODUCT_ID,
    CONF_PRODUCT_NAME,
    CONF_PRICE_ALERT_THRESHOLD,
    DEFAULT_PRICE_ALERT_THRESHOLD,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up KeyforSteam binary sensor from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    threshold = entry.options.get(CONF_PRICE_ALERT_THRESHOLD, DEFAULT_PRICE_ALERT_THRESHOLD)

    # Only create price alert sensor if threshold is configured
    if threshold and threshold > 0:
        async_add_entities([KeyforSteamPriceAlertSensor(coordinator, entry, threshold)])


class KeyforSteamPriceAlertSensor(BinarySensorEntity):
    """Binary sensor for price alerts."""

    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY
    _attr_icon = "mdi:tag-alert"

    def __init__(self, coordinator, entry: ConfigEntry, threshold: float):
        """Initialize the binary sensor."""
        self._coordinator = coordinator
        self._entry = entry
        self._threshold = threshold
        self._attr_unique_id = f"keyforsteam_{coordinator.product_id}_price_alert"
        self._attr_has_entity_name = True
        self._attr_translation_key = "price_alert"

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{self._coordinator.product_name or self._coordinator.product_id} Price Alert"

    @property
    def is_on(self):
        """Return True if price is below threshold."""
        if not self._coordinator.data:
            return False

        low_price = self._coordinator.data.get("low_price")
        if low_price is None:
            return False

        return float(low_price) <= self._threshold

    @property
    def available(self):
        """Return if entity is available."""
        return self._coordinator.last_update_success

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = {
            "threshold": self._threshold,
        }

        if self._coordinator.data:
            low_price = self._coordinator.data.get("low_price")
            attributes["current_price"] = low_price
            if low_price is not None:
                attributes["price_difference"] = round(low_price - self._threshold, 2)

        return attributes

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
