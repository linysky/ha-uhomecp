"""The uhomecp integration."""

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CaptchaRequired, UHomeCPApiError, UHomeCPClient
from .captcha import recognize_captcha
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
    """Set up uhomecp from a config entry."""
    phone = entry.data[CONF_PHONE]
    password = entry.data[CONF_PASSWORD]
    community_id = entry.data.get(CONF_COMMUNITY_ID, "")
    community_name = entry.data.get(CONF_COMMUNITY_NAME, "")

    client = UHomeCPClient(phone, password)

    # Restore saved session if available, otherwise fresh login
    saved_cookies = entry.data.get("_cookies")
    saved_user_info = entry.data.get("_user_info")
    if saved_cookies and saved_user_info:
        client.set_session_cookies(saved_cookies)
        client.set_user_info(saved_user_info)
        _LOGGER.info("Restored saved session for %s", phone)
    else:
        try:
            await client.async_login()
        except CaptchaRequired as err:
            auto_result = await hass.async_add_executor_job(
                recognize_captcha, err.img_code
            )
            if auto_result:
                _LOGGER.info("Auto-recognized captcha during setup: %s", auto_result)
                try:
                    await client.async_login_with_captcha(auto_result, err.random_token)
                except Exception:
                    raise ConfigEntryAuthFailed("Auto-login failed")
            else:
                raise ConfigEntryAuthFailed(
                    "Captcha required - please reconfigure the integration"
                )
        except UHomeCPApiError as err:
            _LOGGER.error("Failed to login: %s", err)
            return False

    if community_id:
        await client.async_set_community(community_id, community_name)

    # Verify session by fetching doors
    try:
        await client.async_get_doors()
    except Exception:
        _LOGGER.info("Saved session invalid, re-logging in")
        try:
            await client.async_login()
        except CaptchaRequired as err:
            auto_result = await hass.async_add_executor_job(
                recognize_captcha, err.img_code
            )
            if auto_result:
                _LOGGER.info("Auto-recognized captcha during re-login: %s", auto_result)
                try:
                    await client.async_login_with_captcha(auto_result, err.random_token)
                except Exception:
                    raise ConfigEntryAuthFailed("Auto-login failed")
            else:
                raise ConfigEntryAuthFailed(
                    "Captcha required - please reconfigure the integration"
                )
        except UHomeCPApiError as err:
            _LOGGER.error("Failed to login: %s", err)
            return False

        if community_id:
            await client.async_set_community(community_id, community_name)

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
            raise ConfigEntryAuthFailed(
                "Session expired, re-login requires captcha"
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
