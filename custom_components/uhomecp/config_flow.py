"""Config flow for U管家门禁 integration."""

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .api import LoginError, UHomeCPClient
from .const import CONF_PASSWORD, CONF_PHONE, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PHONE): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


async def _validate_login(hass: HomeAssistant, phone: str, password: str) -> dict[str, Any]:
    """Validate the login credentials by attempting to login."""
    client = UHomeCPClient(phone, password)
    await hass.async_add_executor_job(client.login)
    return client.user_info


class UHomeCPConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for U管家门禁."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - user inputs phone and password."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await _validate_login(
                    self.hass,
                    user_input[CONF_PHONE],
                    user_input[CONF_PASSWORD],
                )
            except LoginError as err:
                _LOGGER.error("Login failed: %s", err)
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception during login")
                errors["base"] = "unknown"
            else:
                # Login successful, create entry
                await self.async_set_unique_id(user_input[CONF_PHONE])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"U管家 ({user_input[CONF_PHONE]})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
