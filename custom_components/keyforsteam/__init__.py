"""Init file for the KeyforSteam integration."""
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
import logging

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the KeyforSteam integration."""
    _LOGGER.debug("Keyforsteam integration setup called.")
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up KeyforSteam from a config entry."""
    _LOGGER.debug("Setting up KeyforSteam entry with entry_id: %s", entry.entry_id)
    hass.data.setdefault(DOMAIN, {})

    try:
        await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
        _LOGGER.debug("Successfully set up sensor for KeyforSteam entry.")
    except Exception as e:
        _LOGGER.error("Error setting up KeyforSteam entry: %s", e)
        return False

    _LOGGER.debug("KeyforSteam entry setup completed successfully.")
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading KeyforSteam entry with entry_id: %s", entry.entry_id)
    await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    hass.data[DOMAIN].pop(entry.entry_id, None)
    return True
