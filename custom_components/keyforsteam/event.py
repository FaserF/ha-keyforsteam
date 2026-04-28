"""Event entity for KeyforSteam price alerts."""

import logging
from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up KeyforSteam event entities from a config entry."""
    _LOGGER.debug("Setting up KeyforSteam event entities for entry: %s", entry.entry_id)
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    async_add_entities([KeyforSteamPriceDropEvent(coordinator, entry)])


class KeyforSteamPriceDropEvent(CoordinatorEntity, EventEntity):
    """Representation of a KeyforSteam price drop event."""

    _attr_event_types = ["price_drop"]
    _attr_translation_key = "price_drop_event"
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry: ConfigEntry):
        """Initialize the event entity."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"keyforsteam_{coordinator.product_id}_price_drop_event"
        self._last_price = None
        self._event_data = {
            "previous_price": 0.0,
            "current_price": 0.0,
            "difference": 0.0,
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for grouping entities."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.product_id)},
            name=self.coordinator.product_name or f"Game {self.coordinator.product_id}",
            manufacturer="AllKeyShop",
            model="Game Price Tracker",
            entry_type="service",
            configuration_url=self.coordinator.data.get("product_url")
            if self.coordinator.data
            else None,
        )

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {
            "previous_price": self._event_data.get("previous_price"),
            "current_price": self._event_data.get("current_price"),
            "difference": self._event_data.get("difference"),
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if not self.coordinator.data:
            return

        current_price = self.coordinator.data.get("low_price")
        if current_price is None:
            return

        # Trigger event only if price actually dropped
        if self._last_price is not None and current_price < self._last_price:
            self._event_data = {
                "previous_price": self._last_price,
                "current_price": current_price,
                "difference": round(self._last_price - current_price, 2),
            }
            self._trigger_event("price_drop", self._event_data)
            _LOGGER.debug(
                "Price drop event triggered for %s: %s -> %s",
                self.coordinator.product_id,
                self._last_price,
                current_price,
            )

        self._last_price = current_price
        self.async_write_ha_state()
