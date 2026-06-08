import pytest
from unittest.mock import patch, AsyncMock, MagicMock
with patch("homeassistant.helpers.frame.report_usage"):
    from custom_components.keyforsteam import (
        async_setup,
        async_setup_entry,
        async_update_options,
        async_unload_entry,
    )
from custom_components.keyforsteam.const import DOMAIN

from aioresponses import aioresponses
from custom_components.keyforsteam.const import GAMES_CATALOG_URL
import aiohttp


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

        # Since the module is dynamically imported inside the target function, we patch the target function's
        # module globals or simply patch the import target module before running
        import homeassistant.helpers.aiohttp_client as aiohttp_client
        with patch.object(aiohttp_client, "async_get_clientsession") as mock_get_session:
            session = aiohttp.ClientSession()
            mock_get_session.return_value = session
            try:
                response = await service_func(call_mock)
                assert response["game_name"] == "Test Game"
                assert response["best_price"] == 10.0
            finally:
                await session.close()


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
    coordinator = MagicMock()
    coordinator.currency = "eur"
    coordinator.allow_accounts = False
    coordinator.payment_method = "lowest_fees"
    coordinator.ignore_unrealistic_prices = True
    coordinator.update_interval_hours = 1
    mock_hass.data[DOMAIN] = {mock_config_entry.entry_id: {"coordinator": coordinator}}

    # Set default options so we don't trigger reload when we only change threshold
    mock_config_entry.options = {
        "price_alert_threshold": 50.0,
        "currency": "eur",
        "allow_accounts": False,
        "payment_method": "lowest_fees",
        "ignore_unrealistic_prices": True,
    }
    await async_update_options(mock_hass, mock_config_entry)
    assert mock_hass.config_entries.async_reload.call_count == 0

    # Test core setting change (reload)
    mock_config_entry.options = {
        "price_alert_threshold": 50.0,
        "currency": "usd",
        "allow_accounts": False,
        "payment_method": "lowest_fees",
        "ignore_unrealistic_prices": True,
    }
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
