"""Sensor platform for uhomecp - exposes community name."""

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import UHomeCPClient
from .const import CONF_COMMUNITY_ID, CONF_COMMUNITY_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)


def get_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Return device info for grouping entities by community."""
    community_id = entry.data.get(CONF_COMMUNITY_ID, "")
    community_name = entry.data.get(CONF_COMMUNITY_NAME, "uhomecp")
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_{community_id}")},
        name=community_name,
        manufacturer="SEGI",
        entry_type=DeviceEntryType.SERVICE,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up uhomecp sensor entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    client: UHomeCPClient = data["client"]
    coordinator = data["coordinator"]

    async_add_entities([
        UHomeCPCommunitySensor(
            coordinator=coordinator,
            client=client,
            entry=entry,
        ),
    ])


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
        self._attr_device_info = get_device_info(entry)

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
