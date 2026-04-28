import pytest
from unittest.mock import MagicMock, AsyncMock
from custom_components.keyforsteam.button import (
    async_setup_entry,
    KeyforSteamUpdateButton,
)
from custom_components.keyforsteam.const import DOMAIN

@pytest.mark.asyncio
async def test_async_setup_entry(mock_hass, mock_config_entry):
    """Test button setup entry."""
    coordinator = MagicMock()
    mock_hass.data[DOMAIN] = {mock_config_entry.entry_id: {"coordinator": coordinator}}
    
    mock_add_entities = MagicMock()
    await async_setup_entry(mock_hass, mock_config_entry, mock_add_entities)
    mock_add_entities.assert_called_once()

@pytest.mark.asyncio
async def test_update_button():
    """Test the update button press."""
    coordinator = MagicMock()
    coordinator.async_request_refresh = AsyncMock()
    coordinator.product_id = "123"
    coordinator.product_name = "Test Game"
    
    button = KeyforSteamUpdateButton(coordinator, MagicMock())
    await button.async_press()
    coordinator.async_request_refresh.assert_called_once()
    
    assert button.device_info["identifiers"] == {(DOMAIN, "123")}
