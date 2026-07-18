"""Button platform for uhomecp - each door is a button entity."""

import asyncio
import logging
import time
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import UHomeCPClient
from .const import DOMAIN
from .sensor import get_device_info

_LOGGER = logging.getLogger(__name__)

# Debounce interval per door (seconds)
OPEN_COOLDOWN = 1.5


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up uhomecp button entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    client: UHomeCPClient = data["client"]
    coordinator = data["coordinator"]

    entities = []
    for door in coordinator.data:
        entities.append(
            UHomeCPDoorButton(
                coordinator=coordinator,
                client=client,
                door=door,
                entry=entry,
            )
        )

    async_add_entities(entities)


class UHomeCPDoorButton(CoordinatorEntity, ButtonEntity):
    """Representation of a door as a button entity.

    Press = open the door, with 1.5s cooldown to prevent accidental double-taps.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        client: UHomeCPClient,
        door: dict[str, Any],
        entry: ConfigEntry,
    ) -> None:
        """Initialize the door button."""
        super().__init__(coordinator)
        self._client = client
        self._door = door
        self._door_id = str(door.get("doorId", ""))
        self._door_id_str = door.get("doorIdStr", "")
        self._door_name = door.get("name", "Unknown Door")
        self._last_press: float = 0

        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{self._door_id}"
        self._attr_name = self._door_name
        self._attr_device_info = get_device_info(entry)

    @property
    def icon(self) -> str:
        """Return the icon for the entity."""
        return "mdi:door"

    async def async_press(self) -> None:
        """Open the door with cooldown protection."""
        now = time.monotonic()
        elapsed = now - self._last_press
        if elapsed < OPEN_COOLDOWN:
            _LOGGER.debug(
                "Door %s pressed too soon (%.1fs < %.1fs), skipping",
                self._door_name, elapsed, OPEN_COOLDOWN
            )
            return

        self._last_press = now
        try:
            await self._client.async_open_door(self._door_id, self._door_id_str)
            _LOGGER.info("Door %s opened", self._door_name)
        except Exception as err:
            _LOGGER.error("Failed to open door %s: %s", self._door_name, err)
            raise

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
