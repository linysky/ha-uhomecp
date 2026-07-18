"""Switch platform for uhomecp - each door is a switch entity."""

import asyncio
import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import UHomeCPClient
from .const import DOMAIN
from .sensor import get_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up uhomecp switch entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    client: UHomeCPClient = data["client"]
    coordinator = data["coordinator"]

    entities = []
    for door in coordinator.data:
        entities.append(
            UHomeCPDoorSwitch(
                coordinator=coordinator,
                client=client,
                door=door,
                entry=entry,
            )
        )

    async_add_entities(entities)


class UHomeCPDoorSwitch(CoordinatorEntity, SwitchEntity):
    """Representation of a door as a switch entity.

    Turn on = open the door, auto-resets to off after 1 second.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        client: UHomeCPClient,
        door: dict[str, Any],
        entry: ConfigEntry,
    ) -> None:
        """Initialize the door switch."""
        super().__init__(coordinator)
        self._client = client
        self._door = door
        self._door_id = str(door.get("doorId", ""))
        self._door_id_str = door.get("doorIdStr", "")
        self._door_name = door.get("name", "Unknown Door")
        self._is_on = False

        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{self._door_id}"
        self._attr_name = self._door_name
        self._attr_device_info = get_device_info(entry)

    @property
    def is_on(self) -> bool:
        """Return True if the switch is on (door was just opened)."""
        return self._is_on

    @property
    def icon(self) -> str:
        """Return the icon for the entity."""
        return "mdi:door"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Open the door and auto-reset after 1 second."""
        try:
            await self._client.async_open_door(self._door_id, self._door_id_str)
            self._is_on = True
            self.async_write_ha_state()

            # Auto-reset to off after 1 second
            await asyncio.sleep(1)
            self._is_on = False
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Failed to open door %s: %s", self._door_name, err)
            raise

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off is a no-op for doors (they auto-reset)."""
        self._is_on = False
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data:
            for door in self.coordinator.data:
                if str(door.get("doorId")) == self._door_id:
                    self._door = door
                    self._door_name = door.get("name", self._door_name)
                    self._attr_name = self._door_name
                    break
        super()._handle_coordinator_update()
