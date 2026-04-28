"""Number entity for KeyforSteam price budget alerts."""

import logging
from homeassistant.components.number import RestoreNumber, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up KeyforSteam number entities from a config entry."""
    _LOGGER.debug(
        "Setting up KeyforSteam number entities for entry: %s", entry.entry_id
    )
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    async_add_entities([KeyforSteamBudgetNumber(coordinator, entry)])


class KeyforSteamBudgetNumber(RestoreNumber):
    """Representation of a KeyforSteam budget target number."""

    _attr_translation_key = "budget_limit"
    _attr_has_entity_name = True
    _attr_native_min_value = 0.0
    _attr_native_max_value = 500.0
    _attr_native_step = 1.0
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, entry: ConfigEntry):
        """Initialize the budget number entity."""
        super().__init__()
        self.coordinator = coordinator
        self._entry = entry
        self._attr_unique_id = f"keyforsteam_{coordinator.product_id}_budget_limit"
        self._attr_native_value = 0.0

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        if self.coordinator.data:
            currency = self.coordinator.data.get("currency", "EUR")
            return {"EUR": "€", "USD": "$", "GBP": "£"}.get(currency, currency)
        return "€"

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

    async def async_added_to_hass(self) -> None:
        """Restore last state."""
        await super().async_added_to_hass()
        last_number_data = await self.async_get_last_number_data()
        if last_number_data is not None:
            self._attr_native_value = last_number_data.native_value

    async def async_set_native_value(self, value: float) -> None:
        """Update the budget limit."""
        self._attr_native_value = value
        self.async_write_ha_state()
