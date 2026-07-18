"""The U管家门禁 integration."""

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CaptchaRequired, UHomeCPApiError, UHomeCPClient
from .const import CONF_PASSWORD, CONF_PHONE, DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up U管家门禁 from a config entry."""
    phone = entry.data[CONF_PHONE]
    password = entry.data[CONF_PASSWORD]

    client = UHomeCPClient(phone, password)

    # Login (should succeed without captcha since it was solved during config)
    try:
        await client.async_login()
    except CaptchaRequired:
        _LOGGER.error("Captcha required during setup - this should not happen")
        return False
    except UHomeCPApiError as err:
        _LOGGER.error("Failed to login: %s", err)
        return False

    # Get initial door list
    try:
        await client.async_get_doors()
    except UHomeCPApiError as err:
        _LOGGER.error("Failed to get doors: %s", err)
        return False

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=client.async_get_doors,
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
