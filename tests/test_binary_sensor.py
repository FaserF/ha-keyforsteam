import pytest
from unittest.mock import MagicMock, AsyncMock
from custom_components.keyforsteam.binary_sensor import (
    async_setup_entry,
    KeyforSteamPriceAlertSensor,
    KeyforSteamStockBinarySensor,
)
from custom_components.keyforsteam.const import DOMAIN

@pytest.mark.asyncio
async def test_async_setup_entry(mock_hass, mock_config_entry):
    """Test binary sensor setup entry."""
    coordinator = MagicMock()
    mock_hass.data[DOMAIN] = {mock_config_entry.entry_id: {"coordinator": coordinator}}
    
    # Test with threshold enabled
    mock_config_entry.options = {"price_alert_threshold": 20.0}
    mock_add_entities = MagicMock()
    
    await async_setup_entry(mock_hass, mock_config_entry, mock_add_entities)
    mock_add_entities.assert_called_once()
    # Should have added two entities: alert & stock
    assert len(mock_add_entities.call_args[0][0]) == 2

def test_price_alert_sensor():
    """Test price alert sensor."""
    coordinator = MagicMock()
    coordinator.product_name = "Test Game"
    coordinator.data = {"low_price": 15.0}
    
    sensor = KeyforSteamPriceAlertSensor(coordinator, MagicMock(), threshold=20.0)
    assert sensor.is_on is True
    assert sensor.extra_state_attributes["current_price"] == 15.0
    
    coordinator.data["low_price"] = 25.0
    assert sensor.is_on is False

def test_stock_binary_sensor():
    """Test stock binary sensor."""
    coordinator = MagicMock()
    coordinator.product_name = "Test Game"
    coordinator.data = {"offer_count": 5}
    
    sensor = KeyforSteamStockBinarySensor(coordinator, MagicMock())
    assert sensor.is_on is True
    
    coordinator.data["offer_count"] = 0
    assert sensor.is_on is False
