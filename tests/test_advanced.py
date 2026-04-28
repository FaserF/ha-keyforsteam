import pytest
from unittest.mock import MagicMock, AsyncMock


class MockCoordinator:
    def __init__(self):
        self.data = {"low_price": 50.0, "currency": "EUR", "release_date": "2026-12-25"}
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

    KeyforSteamPriceDropEvent._trigger_event = MagicMock()
    KeyforSteamPriceDropEvent.async_write_ha_state = MagicMock()

    entry = MagicMock()
    event_entity = KeyforSteamPriceDropEvent(coordinator, entry)

    event_entity._handle_coordinator_update()
    assert event_entity._last_price == 50.0

    coordinator.data["low_price"] = 40.0
    event_entity._handle_coordinator_update()
    assert event_entity._last_price == 40.0
    assert KeyforSteamPriceDropEvent._trigger_event.called


def test_calendar_entity():
    """Test the Release Calendar Entity."""
    coordinator = MockCoordinator()

    from custom_components.keyforsteam.calendar import KeyforSteamReleaseCalendar

    entry = MagicMock()
    calendar = KeyforSteamReleaseCalendar(coordinator, entry)

    # Test event property
    event = calendar.event
    assert event is not None
    assert "Test Game" in event.summary
    assert event.start.strftime("%Y-%m-%d") == "2026-12-25"


@pytest.mark.asyncio
async def test_number_entity():
    """Test the Target Budget NumberEntity."""
    coordinator = MockCoordinator()

    from custom_components.keyforsteam.number import KeyforSteamBudgetNumber

    KeyforSteamBudgetNumber.async_write_ha_state = MagicMock()
    # Mock RestoreNumber's internal state persistence method
    KeyforSteamBudgetNumber.async_get_last_number_data = AsyncMock(
        return_value=MagicMock(native_value=35.0)
    )

    entry = MagicMock()
    entry.options = {"price_alert_threshold": 35.0}
    entry.data = {}
    number_entity = KeyforSteamBudgetNumber(coordinator, entry)
    number_entity.hass = MagicMock()

    # Test restore
    await number_entity.async_added_to_hass()
    assert number_entity.native_value == 35.0

    # Test set value
    await number_entity.async_set_native_value(25.0)
    # Manually update mock to simulate async_update_entry
    number_entity._entry.options["price_alert_threshold"] = 25.0
    assert number_entity.native_value == 25.0
    assert number_entity.async_write_ha_state.called
