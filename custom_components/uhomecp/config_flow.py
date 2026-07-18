"""Config flow for U管家门禁 integration."""

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .api import CaptchaRequired, LoginError, UHomeCPClient
from .const import CONF_PASSWORD, CONF_PHONE, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PHONE): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

STEP_CAPTCHA_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("captcha"): str,
    }
)


class UHomeCPConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for U管家门禁."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._client: UHomeCPClient | None = None
        self._phone: str = ""
        self._password: str = ""
        self._random_token: str = ""
        self._img_code: str = ""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - user inputs phone and password."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._phone = user_input[CONF_PHONE]
            self._password = user_input[CONF_PASSWORD]
            self._client = UHomeCPClient(self._phone, self._password)

            try:
                result = await self._client.async_login()
            except CaptchaRequired as err:
                # Need captcha, save the captcha info and show captcha step
                self._img_code = err.img_code
                self._random_token = err.random_token
                return await self.async_step_captcha()
            except LoginError as err:
                _LOGGER.error("Login failed: %s", err)
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception during login")
                errors["base"] = "unknown"
            else:
                # Login successful without captcha
                await self.async_set_unique_id(self._phone)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"U管家 ({self._phone})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_captcha(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the captcha step - user inputs the captcha text."""
        errors: dict[str, str] = {}

        if user_input is not None:
            captcha = user_input["captcha"]
            try:
                result = await self._client.async_login_with_captcha(
                    captcha, self._random_token
                )
            except LoginError as err:
                _LOGGER.error("Login with captcha failed: %s", err)
                errors["base"] = "invalid_captcha"
                # Get a new captcha for retry
                try:
                    self._img_code, self._random_token = (
                        await self._client.async_get_captcha()
                    )
                except Exception:
                    errors["base"] = "unknown"
            except Exception:
                _LOGGER.exception("Unexpected exception during captcha login")
                errors["base"] = "unknown"
            else:
                # Login successful
                await self.async_set_unique_id(self._phone)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"U管家 ({self._phone})",
                    data={
                        CONF_PHONE: self._phone,
                        CONF_PASSWORD: self._password,
                    },
                )

        return self.async_show_form(
            step_id="captcha",
            data_schema=STEP_CAPTCHA_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "captcha_image": f"![captcha](data:image/jpeg;base64,{self._img_code})",
            },
        )
