"""Image entity for KeyforSteam game coverage."""

import logging
from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.device_registry import DeviceEntryType

from .const import DOMAIN
from .sensor import KeyforSteamDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up the KeyforSteam image entity from a config entry."""
    _LOGGER.debug("Setting up KeyforSteam image entity for entry: %s", entry.entry_id)
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    async_add_entities([KeyforSteamGameImage(hass, coordinator, entry)])


class KeyforSteamGameImage(ImageEntity):
    """Representation of a KeyforSteam game cover image."""

    _attr_translation_key = "game_image"
    _attr_entity_registry_enabled_default = False
    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: KeyforSteamDataUpdateCoordinator,
        entry: ConfigEntry,
    ):
        """Initialize the image entity."""
        super().__init__(hass)
        self.coordinator = coordinator
        self._entry = entry
        self._attr_unique_id = f"keyforsteam_{coordinator.product_id}_image"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success

    @property
    def image_url(self) -> str | None:
        """Return URL of image."""
        if self.coordinator.data:
            return self.coordinator.data.get("image")
        return None

    @property
    def image_last_updated(self):
        """Return timestamp of when the image was last updated."""
        if self.coordinator.data:
            last_updated = self.coordinator.data.get("last_updated")
            if last_updated:
                import homeassistant.util.dt as dt_util

                return dt_util.parse_datetime(last_updated)
        return None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for grouping entities."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.product_id)},
            name=self.coordinator.product_name or f"Game {self.coordinator.product_id}",
            manufacturer="AllKeyShop",
            model="Game Price Tracker",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=(
                self.coordinator.data.get("product_url")
                if self.coordinator.data
                else None
            ),
        )

    async def async_added_to_hass(self):
        """Subscribe to updates."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )
