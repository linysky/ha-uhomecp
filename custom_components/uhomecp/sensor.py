"""Sensor platform for U管家门禁 - exposes community and door count info."""

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import UHomeCPClient
from .const import CONF_COMMUNITY_ID, CONF_COMMUNITY_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up U管家门禁 sensor entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    client: UHomeCPClient = data["client"]
    coordinator = data["coordinator"]

    entities = [
        UHomeCPCommunitySensor(
            coordinator=coordinator,
            client=client,
            entry=entry,
        ),
        UHomeCPDoorCountSensor(
            coordinator=coordinator,
            client=client,
            entry=entry,
        ),
    ]

    async_add_entities(entities)


class UHomeCPCommunitySensor(CoordinatorEntity, SensorEntity):
    """Sensor showing the current community name."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:home-city"

    def __init__(
        self,
        coordinator,
        client: UHomeCPClient,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the community sensor."""
        super().__init__(coordinator)
        self._client = client
        self._community_name = entry.data.get(CONF_COMMUNITY_NAME, "Unknown")
        self._community_id = entry.data.get(CONF_COMMUNITY_ID, "")

        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_community"
        self._attr_name = "小区"

    @property
    def native_value(self) -> str:
        """Return the community name."""
        return self._client.community_name or self._community_name

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        return {
            "community_id": self._client.community_id or self._community_id,
        }


class UHomeCPDoorCountSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing the number of available doors."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:door"
    _attr_native_unit_of_measurement = "个"

    def __init__(
        self,
        coordinator,
        client: UHomeCPClient,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the door count sensor."""
        super().__init__(coordinator)
        self._client = client

        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_door_count"
        self._attr_name = "门禁数量"

    @property
    def native_value(self) -> int:
        """Return the number of doors."""
        if self.coordinator.data:
            return len(self.coordinator.data)
        return len(self._client.doors)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return door names as attributes."""
        doors = self.coordinator.data or self._client.doors
        return {
            "doors": [d.get("name", "Unknown") for d in doors],
        }
