"""Diagnostics for KeyforSteam integration."""

from typing import Any
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    diagnostics = {
        "entry": {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "coordinator": {
            "product_id": coordinator.product_id,
            "product_name": coordinator.product_name,
            "product_slug": coordinator.product_slug,
            "currency": coordinator.currency,
            "consecutive_failures": coordinator.consecutive_failures,
            "last_successful_fetch": (
                coordinator.last_successful_fetch.isoformat()
                if coordinator.last_successful_fetch
                else None
            ),
            "api_repair_created": coordinator.api_repair_created,
            "not_found_repair_created": coordinator.not_found_repair_created,
            "last_update_success": coordinator.last_update_success,
        },
    }

    if coordinator.data:
        diagnostics["data"] = coordinator.data

    return diagnostics
