import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from custom_components.keyforsteam import (
    async_setup,
    async_setup_entry,
    async_update_options,
    async_unload_entry,
)
from custom_components.keyforsteam.const import DOMAIN

from aioresponses import aioresponses
from custom_components.keyforsteam.const import GAMES_CATALOG_URL


@pytest.mark.asyncio
async def test_async_setup(mock_hass):
    """Test the setup of the integration."""
    result = await async_setup(mock_hass, {})
    assert result is True
    mock_hass.services.async_register.assert_called_once()

    # Extract the service callback
    service_call = mock_hass.services.async_register.call_args[0]
    assert service_call[1] == "get_prices"
    service_func = service_call[2]

    # Test calling the service
    with aioresponses() as m:
        m.get(
            GAMES_CATALOG_URL,
            payload={"games": [{"name": "Test Game"}]},
        )
        m.get(
            "https://www.keyforsteam.de/test-game-key-kaufen",
            body='var gamePageTrans = {"prices": [{"price": 10.0, "merchantName": "Seller A"}]};',
        )

        call_mock = MagicMock()
        call_mock.data = {"game_name": "Test Game"}

        response = await service_func(call_mock)
        assert response["game_name"] == "Test Game"
        assert response["best_price"] == 10.0


@pytest.mark.asyncio
async def test_async_setup_entry(mock_hass, mock_config_entry):
    """Test setting up a config entry."""
    with patch(
        "custom_components.keyforsteam.sensor.KeyforSteamDataUpdateCoordinator"
    ) as mock_coord_class:
        mock_coord = MagicMock()
        mock_coord.async_config_entry_first_refresh = AsyncMock()
        mock_coord_class.return_value = mock_coord

        result = await async_setup_entry(mock_hass, mock_config_entry)

        assert result is True
        assert DOMAIN in mock_hass.data
        assert mock_config_entry.entry_id in mock_hass.data[DOMAIN]
        mock_coord.async_config_entry_first_refresh.assert_called_once()
        mock_hass.config_entries.async_forward_entry_setups.assert_called_once()


@pytest.mark.asyncio
async def test_async_update_options(mock_hass, mock_config_entry):
    """Test handling options update."""
    await async_update_options(mock_hass, mock_config_entry)
    mock_hass.config_entries.async_reload.assert_called_once_with(
        mock_config_entry.entry_id
    )


@pytest.mark.asyncio
async def test_async_unload_entry(mock_hass, mock_config_entry):
    """Test unloading a config entry."""
    mock_hass.data[DOMAIN] = {mock_config_entry.entry_id: {}}

    result = await async_unload_entry(mock_hass, mock_config_entry)

    assert result is True
    assert mock_config_entry.entry_id not in mock_hass.data[DOMAIN]
    mock_hass.config_entries.async_unload_platforms.assert_called_once()
