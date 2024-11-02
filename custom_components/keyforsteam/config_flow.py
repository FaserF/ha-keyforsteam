"""Config flow for KeyforSteam integration."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from .const import DOMAIN

class KeyforSteamConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for KeyforSteam."""

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is not None:
            return self.async_create_entry(title="KeyforSteam", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=self.get_options_schema()
        )

    @staticmethod
    def get_options_schema():
        """Return the options schema for the user input."""
        return vol.Schema({
            vol.Required("product_id"): str,
            vol.Required("currency", default="eur"): vol.In(["eur", "usd"]),
        })
