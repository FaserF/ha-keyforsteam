import pytest
from unittest.mock import MagicMock, AsyncMock
from homeassistant.core import HomeAssistant


@pytest.fixture
def mock_hass():
    hass = MagicMock(spec=HomeAssistant)
    hass.data = {}
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
