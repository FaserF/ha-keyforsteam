import pytest
from unittest.mock import MagicMock


class MockCoordinator:

    def __init__(self):
        self.data = {"low_price": 50.0}
        self.product_id = "123"
        self.product_name = "Test Game"
        self.last_update_success = True
        self._listeners = []

    def async_add_listener(self, listener):
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)


def test_event_entity_price_drop():
    """Test the Price Drop EventEntity logic."""
    coordinator = MockCoordinator()

    from custom_components.keyforsteam.event import KeyforSteamPriceDropEvent

    # Mock superclass methods to isolate logic testing
    KeyforSteamPriceDropEvent._trigger_event = MagicMock()
    KeyforSteamPriceDropEvent.async_write_ha_state = MagicMock()

    entry = MagicMock()
    event_entity = KeyforSteamPriceDropEvent(coordinator, entry)

    # Initial price set
    event_entity._handle_coordinator_update()
    assert event_entity._last_price == 50.0
    assert not KeyforSteamPriceDropEvent._trigger_event.called

    # Price stays same
    event_entity._handle_coordinator_update()
    assert event_entity._last_price == 50.0
    assert not KeyforSteamPriceDropEvent._trigger_event.called

    # Price drops!
    coordinator.data["low_price"] = 40.0
    event_entity._handle_coordinator_update()
    assert event_entity._last_price == 40.0
    assert KeyforSteamPriceDropEvent._trigger_event.called

    # Inspect event data
    args, kwargs = KeyforSteamPriceDropEvent._trigger_event.call_args
    assert args[0] == "price_drop"
    assert args[1]["previous_price"] == 50.0
    assert args[1]["current_price"] == 40.0
    assert args[1]["difference"] == 10.0
