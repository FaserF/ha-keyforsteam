import pytest
from unittest.mock import MagicMock
from custom_components.keyforsteam.image import (
    async_setup_entry,
    KeyforSteamGameImage,
)
from custom_components.keyforsteam.const import DOMAIN


@pytest.mark.asyncio
async def test_async_setup_entry(mock_hass, mock_config_entry):
    """Test image setup entry."""
    coordinator = MagicMock()
    mock_hass.data[DOMAIN] = {mock_config_entry.entry_id: {"coordinator": coordinator}}

    mock_add_entities = MagicMock()
    await async_setup_entry(mock_hass, mock_config_entry, mock_add_entities)
    mock_add_entities.assert_called_once()


def test_game_image():
    """Test game image entity."""
    hass = MagicMock()
    coordinator = MagicMock()
    coordinator.product_id = "123"
    coordinator.product_name = "Test Game"
    coordinator.last_update_success = True
    coordinator.data = {"image": "http://img-url"}

    image_entity = KeyforSteamGameImage(hass, coordinator, MagicMock())

    assert image_entity.available is True
    assert image_entity.image_url == "http://img-url"
    assert image_entity.device_info["identifiers"] == {(DOMAIN, "123")}

    coordinator.last_update_success = False
    assert image_entity.available is False
