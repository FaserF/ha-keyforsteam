import inspect
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest
from homeassistant.core import HomeAssistant

# Patch aiohttp ClientResponse to handle the stream_writer parameter, which was made
# required in aiohttp 3.14+ but is not passed by the current version of aioresponses.
_original_client_response_init = aiohttp.ClientResponse.__init__


def _patched_client_response_init(self, *args, **kwargs):
    sig = inspect.signature(_original_client_response_init)
    if "stream_writer" in sig.parameters and "stream_writer" not in kwargs:
        kwargs["stream_writer"] = MagicMock()
    return _original_client_response_init(self, *args, **kwargs)


aiohttp.ClientResponse.__init__ = _patched_client_response_init


@pytest.fixture
def mock_hass():
    hass = MagicMock(spec=HomeAssistant)
    hass.data = {"network": MagicMock()}
    hass.services = MagicMock()
    hass.services.async_register = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_listen_once = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.config_entries.async_reload = AsyncMock(return_value=True)
    return hass


@pytest.fixture
def mock_config_entry():
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {
        "product_id": "12345",
        "product_name": "Test Game",
        "product_slug": "test-game",
        "currency": "eur",
        "allow_accounts": False,
        "payment_method": "lowest_fees",
    }
    entry.options = {}
    entry.async_on_unload = MagicMock()
    entry.add_update_listener = MagicMock()
    return entry
