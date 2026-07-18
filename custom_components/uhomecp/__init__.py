"""The U管家门禁 integration."""

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CaptchaRequired, UHomeCPApiError, UHomeCPClient
from .const import (
    CONF_COMMUNITY_ID,
    CONF_COMMUNITY_NAME,
    CONF_PASSWORD,
    CONF_PHONE,
    DOMAIN,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up U管家门禁 from a config entry."""
    phone = entry.data[CONF_PHONE]
    password = entry.data[CONF_PASSWORD]
    community_id = entry.data.get(CONF_COMMUNITY_ID, "")
    community_name = entry.data.get(CONF_COMMUNITY_NAME, "")

    client = UHomeCPClient(phone, password)

    # Login
    try:
        await client.async_login()
    except CaptchaRequired:
        _LOGGER.error(
            "Captcha required during setup - please reconfigure the integration"
        )
        return False
    except UHomeCPApiError as err:
        _LOGGER.error("Failed to login: %s", err)
        return False

    # Set community
    if community_id:
        await client.async_set_community(community_id, community_name)

    # Get initial door list
    try:
        await client.async_get_doors()
    except UHomeCPApiError as err:
        _LOGGER.error("Failed to get doors: %s", err)
        return False

    async def _async_update_data():
        """Fetch door data from the API."""
        try:
            return await client.async_get_doors()
        except CaptchaRequired as err:
            raise UpdateFailed(
                "Session expired and re-login requires captcha. "
                "Please reconfigure the integration."
            ) from err
        except UHomeCPApiError as err:
            raise UpdateFailed(f"Failed to fetch door data: {err}") from err

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=_async_update_data,
        update_interval=timedelta(seconds=UPDATE_INTERVAL),
    )

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
