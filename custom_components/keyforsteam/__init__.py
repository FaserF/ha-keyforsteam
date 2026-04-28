"""Init file for the KeyforSteam integration."""

import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

import homeassistant.helpers.config_validation as cv
from .const import DOMAIN, CONF_PRICE_ALERT_THRESHOLD, DEFAULT_PRICE_ALERT_THRESHOLD

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS = ["sensor", "binary_sensor", "button", "image", "event"]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the KeyforSteam integration."""
    _LOGGER.debug("KeyforSteam integration setup called.")

    from homeassistant.core import ServiceResponse, SupportsResponse
    from homeassistant.helpers.aiohttp_client import async_get_clientsession
    from .const import GAMES_CATALOG_URL
    import voluptuous as vol
    import aiohttp
    import async_timeout
    import re
    import json

    async def async_get_prices(call) -> ServiceResponse:
        game_name = call.data.get("game_name")
        if not game_name:
            raise vol.Invalid("game_name is required")

        session = async_get_clientsession(hass)

        try:
            async with async_timeout.timeout(10):
                async with session.get(GAMES_CATALOG_URL) as response:
                    if response.status != 200:
                        return {"error": "Failed to fetch catalog"}
                    cat_data = await response.json()
                    games = cat_data.get("games", [])
        except Exception as e:
            return {"error": f"Catalog fetch error: {e}"}

        best_game = None
        query_lower = game_name.lower().strip()
        scored_results = []
        for game in games:
            name = game.get("name", "")
            name_lower = name.lower()
            score = 0
            if name_lower == query_lower:
                score = 1000
            elif name_lower.startswith(query_lower):
                score = 500
            elif query_lower in name_lower:
                score = 100

            if score > 0:
                if any(word in name_lower for word in ["account", "dlc", "pack", "map", "expansion"]):
                    score -= 300
                score += (200 - min(len(name), 150)) / 10
                scored_results.append((score, game))

        scored_results.sort(key=lambda x: x[0], reverse=True)
        if not scored_results:
            return {"error": "Game not found"}
        
        best_game = scored_results[0][1]
        slug = best_game.get("name", "").lower()
        slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
        
        url = f"https://www.keyforsteam.de/{slug}-key-kaufen"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        try:
            async with async_timeout.timeout(15):
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        return {"error": f"Failed to fetch game page: status {response.status}"}
                    html = await response.text()
        except Exception as e:
            return {"error": f"Fetch game page error: {e}"}

        match = re.search(r"var gamePageTrans\s*=\s*(\{.*?\});", html, re.DOTALL)
        if not match:
            return {"error": "No price data found on page"}

        try:
            game_data = json.loads(match.group(1))
            prices = game_data.get("prices", [])
            merchants = game_data.get("merchants", {})
            
            offers = []
            for p in prices:
                price_val = p.get("price", 0)
                if p.get("priceCard"):
                    price_val = p.get("priceCard")
                merchant_name = p.get("merchantName") or merchants.get(str(p.get("merchant")), {}).get("name", "Unknown")
                offers.append({
                    "seller": merchant_name,
                    "price": float(price_val),
                    "currency": "EUR",
                    "is_account": p.get("account", False)
                })
            
            offers.sort(key=lambda x: x["price"])
            return {
                "game_name": best_game.get("name"),
                "url": url,
                "best_price": offers[0]["price"] if offers else None,
                "offers": offers[:5]
            }
        except Exception as e:
            return {"error": f"Parsing error: {e}"}

    hass.services.async_register(
        DOMAIN,
        "get_prices",
        async_get_prices,
        schema=vol.Schema({vol.Required("game_name"): cv.string}),
        supports_response=SupportsResponse.ONLY,
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up KeyforSteam from a config entry."""
    _LOGGER.debug("Setting up KeyforSteam entry with entry_id: %s", entry.entry_id)
    hass.data.setdefault(DOMAIN, {})

    # Create and initialize the coordinator here to prevent race conditions across platforms
    from .sensor import KeyforSteamDataUpdateCoordinator
    coordinator = KeyforSteamDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator}

    # Determine which platforms to load
    platforms_to_load = ["sensor", "image", "button", "event"]

    # Only load binary_sensor if price alert threshold is configured
    threshold = entry.options.get(
        CONF_PRICE_ALERT_THRESHOLD, DEFAULT_PRICE_ALERT_THRESHOLD
    )
    if threshold and threshold > 0:
        platforms_to_load.append("binary_sensor")

    try:
        await hass.config_entries.async_forward_entry_setups(entry, platforms_to_load)
        _LOGGER.debug(
            "Successfully set up platforms for KeyforSteam entry: %s", platforms_to_load
        )
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
    platforms_to_unload = ["sensor", "image", "button", "event"]
    threshold = entry.options.get(
        CONF_PRICE_ALERT_THRESHOLD, DEFAULT_PRICE_ALERT_THRESHOLD
    )
    if threshold and threshold > 0:
        platforms_to_unload.append("binary_sensor")

    unloaded = await hass.config_entries.async_unload_platforms(
        entry, platforms_to_unload
    )

    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        _LOGGER.debug("KeyforSteam entry unloaded successfully.")
    else:
        _LOGGER.warning(
            "Failed to unload KeyforSteam entry with entry_id: %s", entry.entry_id
        )

    return unloaded

