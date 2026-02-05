"""Config flow for KeyforSteam integration."""
import logging
import re
import aiohttp
import async_timeout
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    DOMAIN,
    GAMES_CATALOG_URL,
    CONF_PRODUCT_ID,
    CONF_PRODUCT_NAME,
    CONF_PRODUCT_SLUG,
    CONF_CURRENCY,
    CONF_PRICE_ALERT_THRESHOLD,
    DEFAULT_CURRENCY,
    DEFAULT_PRICE_ALERT_THRESHOLD,
)

_LOGGER = logging.getLogger(__name__)


class KeyforSteamConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for KeyforSteam."""

    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self._games_cache = None
        self._selected_game = None

    async def _fetch_games_catalog(self):
        """Fetch games catalog from AllKeyShop API."""
        if self._games_cache is not None:
            return self._games_cache

        try:
            async with aiohttp.ClientSession() as session:
                async with async_timeout.timeout(30):
                    async with session.get(GAMES_CATALOG_URL) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data.get("status") == "success":
                                self._games_cache = data.get("games", [])
                                _LOGGER.debug("Fetched %d games from catalog", len(self._games_cache))
                                return self._games_cache
        except Exception as e:
            _LOGGER.error("Error fetching games catalog: %s", e)

        return []

    def _search_games(self, query: str, limit: int = 100) -> list:
        """Search games by name with prioritization."""
        if not self._games_cache or not query:
            return []

        query_lower = query.lower().strip()
        if len(query_lower) < 2:
            return []

        # Scoring:
        # - Exact match: 1000
        # - Starts with: 500
        # - Contains: 100
        # - Penalty for DLC/Account/Pack: -300

        scored_results = []
        for game in self._games_cache:
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
                # Apply penalties to keep base games at top
                if any(word in name_lower for word in ["account", "dlc", "pack", "map", "expansion"]):
                    score -= 300

                # Bonus for shorter names (more likely to be base game)
                score += (200 - min(len(name), 150)) / 10

                scored_results.append((score, game))

        # Sort by score descending
        scored_results.sort(key=lambda x: x[0], reverse=True)

        return [item[1] for item in scored_results[:limit]]

    def _create_slug(self, game_name: str) -> str:
        """Create URL slug from game name."""
        slug = game_name.lower()
        slug = re.sub(r'[^a-z0-9]+', '-', slug)
        slug = slug.strip('-')
        return slug

    async def async_step_user(self, user_input=None):
        """Handle the initial step - game search."""
        errors = {}

        # Fetch games catalog in background
        if self._games_cache is None:
            await self._fetch_games_catalog()

        if user_input is not None:
            game_query = user_input.get("game_query", "").strip()

            if game_query:
                # Search for games
                results = self._search_games(game_query)

                if results:
                    # Store results and move to selection step
                    self._search_results = results
                    return await self.async_step_select()
                else:
                    errors["game_query"] = "no_games_found"
            else:
                errors["game_query"] = "required"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("game_query"): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT)
                ),
            }),
            errors=errors,
            description_placeholders={
                "games_count": str(len(self._games_cache)) if self._games_cache else "0"
            }
        )

    async def async_step_select(self, user_input=None):
        """Handle game selection step."""
        errors = {}

        if user_input is not None:
            selected_id = user_input.get("game_selection")
            currency = user_input.get(CONF_CURRENCY, DEFAULT_CURRENCY)

            # Find selected game
            selected_game = None
            for game in self._search_results:
                if str(game.get("id")) == str(selected_id):
                    selected_game = game
                    break

            if selected_game:
                game_name = selected_game.get("name", "Unknown Game")
                game_id = selected_game.get("id")
                game_slug = self._create_slug(game_name)

                # Check if already configured
                await self.async_set_unique_id(f"keyforsteam_{game_id}")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=game_name,
                    data={
                        CONF_PRODUCT_ID: str(game_id),
                        CONF_PRODUCT_NAME: game_name,
                        CONF_PRODUCT_SLUG: game_slug,
                        CONF_CURRENCY: currency,
                    }
                )
            else:
                errors["game_selection"] = "invalid_selection"

        # Build selection options
        options = [
            {"value": str(game.get("id")), "label": game.get("name", "Unknown")}
            for game in self._search_results
        ]

        return self.async_show_form(
            step_id="select",
            data_schema=vol.Schema({
                vol.Required("game_selection"): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(CONF_CURRENCY, default=DEFAULT_CURRENCY): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": "eur", "label": "EUR (€)"},
                            {"value": "usd", "label": "USD ($)"},
                            {"value": "gbp", "label": "GBP (£)"},
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return KeyforSteamOptionsFlow(config_entry)


class KeyforSteamOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for KeyforSteam."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Handle options flow."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Get current values from options or data
        options = self.config_entry.options
        data = self.config_entry.data

        current_threshold = options.get(
            CONF_PRICE_ALERT_THRESHOLD, DEFAULT_PRICE_ALERT_THRESHOLD
        )
        current_currency = options.get(
            CONF_CURRENCY, data.get(CONF_CURRENCY, DEFAULT_CURRENCY)
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_PRICE_ALERT_THRESHOLD,
                    default=float(current_threshold)
                ): vol.Coerce(float),
                vol.Optional(
                    CONF_CURRENCY,
                    default=current_currency
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": "eur", "label": "EUR (€)"},
                            {"value": "usd", "label": "USD ($)"},
                            {"value": "gbp", "label": "GBP (£)"},
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }),
        )
