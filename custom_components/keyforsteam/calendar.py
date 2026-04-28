"""Calendar entity for KeyforSteam game release dates."""

import logging
from datetime import datetime, timedelta
from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
import homeassistant.util.dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up KeyforSteam calendar entities from a config entry."""
    _LOGGER.debug(
        "Setting up KeyforSteam calendar entities for entry: %s", entry.entry_id
    )
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    async_add_entities([KeyforSteamReleaseCalendar(coordinator, entry)])


class KeyforSteamReleaseCalendar(CoordinatorEntity, CalendarEntity):
    """Representation of a KeyforSteam release date calendar."""

    _attr_translation_key = "release_calendar"
    _attr_entity_registry_enabled_default = False
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry: ConfigEntry):
        """Initialize the calendar entity."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"keyforsteam_{coordinator.product_id}_calendar"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for grouping entities."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.product_id)},
            name=self.coordinator.product_name or f"Game {self.coordinator.product_id}",
            manufacturer="AllKeyShop",
            model="Game Price Tracker",
            entry_type="service",
        )

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event."""
        if not self.coordinator.data:
            return None

        release_date = self.coordinator.data.get("release_date")
        if not release_date:
            return None

        try:
            date_obj = dt_util.parse_datetime(release_date)
            if not date_obj:
                date_obj = datetime.strptime(release_date[:10], "%Y-%m-%d")

            start_dt = dt_util.as_local(date_obj)
            end_dt = start_dt + timedelta(days=1)

            return CalendarEvent(
                summary=f"Release: {self.coordinator.product_name}",
                start=start_dt,
                end=end_dt,
                description=f"Release of {self.coordinator.product_name}",
            )
        except Exception as e:
            _LOGGER.debug("Error parsing release date: %s", e)
            return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        event = self.event
        if not event:
            return []

        if event.start >= start_date and event.start <= end_date:
            return [event]

        return []
