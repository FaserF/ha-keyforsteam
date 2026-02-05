"""Init file for the KeyforSteam integration."""
import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN, CONF_PRICE_ALERT_THRESHOLD, DEFAULT_PRICE_ALERT_THRESHOLD

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor", "button"]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the KeyforSteam integration."""
    _LOGGER.debug("KeyforSteam integration setup called.")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up KeyforSteam from a config entry."""
    _LOGGER.debug("Setting up KeyforSteam entry with entry_id: %s", entry.entry_id)
    hass.data.setdefault(DOMAIN, {})

    # Determine which platforms to load
    platforms_to_load = ["sensor"]

    # Only load binary_sensor if price alert threshold is configured
    threshold = entry.options.get(CONF_PRICE_ALERT_THRESHOLD, DEFAULT_PRICE_ALERT_THRESHOLD)
    if threshold and threshold > 0:
        platforms_to_load.append("binary_sensor")

    try:
        await hass.config_entries.async_forward_entry_setups(entry, platforms_to_load)
        _LOGGER.debug("Successfully set up platforms for KeyforSteam entry: %s", platforms_to_load)
    except Exception as e:
        _LOGGER.error("Error setting up KeyforSteam entry: %s", e)
        return False

    # Register update listener for options changes
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    _LOGGER.debug("KeyforSteam entry setup completed successfully.")
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    _LOGGER.debug("Options updated for KeyforSteam entry: %s", entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading KeyforSteam entry with entry_id: %s", entry.entry_id)

    # Determine which platforms were loaded
    platforms_to_unload = ["sensor"]
    threshold = entry.options.get(CONF_PRICE_ALERT_THRESHOLD, DEFAULT_PRICE_ALERT_THRESHOLD)
    if threshold and threshold > 0:
        platforms_to_unload.append("binary_sensor")

    unloaded = await hass.config_entries.async_unload_platforms(entry, platforms_to_unload)

    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        _LOGGER.debug("KeyforSteam entry unloaded successfully.")
    else:
        _LOGGER.warning("Failed to unload KeyforSteam entry with entry_id: %s", entry.entry_id)

    return unloaded
