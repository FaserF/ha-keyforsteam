"""Button for KeyforSteam manual updates."""
import logging
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up KeyforSteam button from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([KeyforSteamUpdateButton(coordinator, entry)])


class KeyforSteamUpdateButton(ButtonEntity):
    """Button to trigger a manual update."""

    _attr_icon = "mdi:refresh"
    _attr_has_entity_name = True
    _attr_translation_key = "update_button"

    def __init__(self, coordinator, entry: ConfigEntry):
        """Initialize the button."""
        self._coordinator = coordinator
        self._entry = entry
        self._attr_unique_id = f"keyforsteam_{coordinator.product_id}_update"

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.debug("Manual update triggered via button for %s", self._coordinator.product_id)
        await self._coordinator.async_request_refresh()

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
