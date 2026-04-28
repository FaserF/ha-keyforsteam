import pytest
from unittest.mock import MagicMock
from custom_components.keyforsteam.diagnostics import async_get_config_entry_diagnostics
from custom_components.keyforsteam.const import DOMAIN


@pytest.mark.asyncio
async def test_async_get_config_entry_diagnostics(mock_hass, mock_config_entry):
    """Test diagnostics generation."""
    coordinator = MagicMock()
    coordinator.product_id = "123"
    coordinator.product_name = "Test Game"
    coordinator.product_slug = "test-game"
    coordinator.currency = "eur"
    coordinator.consecutive_failures = 0
    coordinator.last_successful_fetch = None
    coordinator.api_repair_created = False
    coordinator.not_found_repair_created = False
    coordinator.last_update_success = True
    coordinator.data = {"name": "Test Game", "low_price": 10.0, "currency": "EUR"}

    mock_hass.data[DOMAIN] = {mock_config_entry.entry_id: {"coordinator": coordinator}}

    diagnostics = await async_get_config_entry_diagnostics(mock_hass, mock_config_entry)

    assert diagnostics["entry"]["entry_id"] == mock_config_entry.entry_id
    assert diagnostics["coordinator"]["product_id"] == "123"
    assert diagnostics["data"]["low_price"] == 10.0
