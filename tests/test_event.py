import pytest
from unittest.mock import MagicMock
from custom_components.keyforsteam.event import (
    async_setup_entry,
    KeyforSteamPriceDropEvent,
)
from custom_components.keyforsteam.const import DOMAIN


@pytest.mark.asyncio
async def test_async_setup_entry(mock_hass, mock_config_entry):
    """Test event platform setup entry."""
    coordinator = MagicMock()
    mock_hass.data[DOMAIN] = {mock_config_entry.entry_id: {"coordinator": coordinator}}

    mock_add_entities = MagicMock()
    await async_setup_entry(mock_hass, mock_config_entry, mock_add_entities)
    mock_add_entities.assert_called_once()


def test_price_drop_event():
    """Test price drop event entity."""
    coordinator = MagicMock()
    coordinator.product_id = "123"
    coordinator.product_name = "Test Game"
    coordinator.data = {"low_price": 20.0}

    event_entity = KeyforSteamPriceDropEvent(coordinator, MagicMock())
    event_entity.hass = MagicMock()
    event_entity.async_write_ha_state = MagicMock()
    event_entity._trigger_event = MagicMock()

    # First update establishes the baseline price
    event_entity._handle_coordinator_update()
    event_entity._trigger_event.assert_not_called()

    # Second update with higher price does not trigger
    coordinator.data["low_price"] = 25.0
    event_entity._handle_coordinator_update()
    event_entity._trigger_event.assert_not_called()

    # Third update with lower price triggers event
    coordinator.data["low_price"] = 15.0
    event_entity._handle_coordinator_update()
    event_entity._trigger_event.assert_called_once_with(
        "price_drop",
        {
            "previous_price": 25.0,
            "current_price": 15.0,
            "difference": 10.0,
        },
    )
