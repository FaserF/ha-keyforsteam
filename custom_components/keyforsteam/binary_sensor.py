"""Binary sensor for KeyforSteam price alerts."""
import logging
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    DOMAIN,
    CONF_PRICE_ALERT_THRESHOLD,
    DEFAULT_PRICE_ALERT_THRESHOLD,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up KeyforSteam binary sensors from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities = [KeyforSteamStockBinarySensor(coordinator, entry)]

    threshold = entry.options.get(CONF_PRICE_ALERT_THRESHOLD, DEFAULT_PRICE_ALERT_THRESHOLD)
    if threshold and threshold > 0:
        entities.append(KeyforSteamPriceAlertSensor(coordinator, entry, threshold))

    async_add_entities(entities)


class KeyforSteamBaseBinarySensor(BinarySensorEntity):
    """Base class for KeyforSteam binary sensors."""

    def __init__(self, coordinator, entry: ConfigEntry):
        """Initialize the binary sensor."""
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


class KeyforSteamPriceAlertSensor(KeyforSteamBaseBinarySensor):
    """Binary sensor for price alerts."""

    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY
    _attr_icon = "mdi:tag-alert"
    _attr_translation_key = "price_alert"

    def __init__(self, coordinator, entry: ConfigEntry, threshold: float):
        """Initialize the binary sensor."""
        super().__init__(coordinator, entry)
        self._threshold = threshold
        self._attr_unique_id = f"keyforsteam_{coordinator.product_id}_price_alert"

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
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = {"threshold": self._threshold}

        if self._coordinator.data:
            low_price = self._coordinator.data.get("low_price")
            attributes["current_price"] = low_price
            if low_price is not None:
                attributes["price_difference"] = round(low_price - self._threshold, 2)

        return attributes


class KeyforSteamStockBinarySensor(KeyforSteamBaseBinarySensor):
    """Binary sensor for stock status."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_icon = "mdi:package-variant"
    _attr_translation_key = "stock"

    def __init__(self, coordinator, entry: ConfigEntry):
        """Initialize the binary sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"keyforsteam_{coordinator.product_id}_stock"

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{self._coordinator.product_name or self._coordinator.product_id} Stock"

    @property
    def is_on(self):
        """Return True if game is in stock."""
        if not self._coordinator.data:
            return False

        offer_count = self._coordinator.data.get("offer_count", 0)
        return offer_count > 0
