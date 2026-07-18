"""Config flow for U管家门禁 integration."""

import logging
import os
import base64
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .api import AccountLocked, CaptchaRequired, LoginError, UHomeCPClient
from .const import CONF_COMMUNITY_ID, CONF_COMMUNITY_NAME, CONF_PASSWORD, CONF_PHONE, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PHONE): str,
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
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
        self._communities: list[dict[str, Any]] = []

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
                self._img_code = err.img_code
                self._random_token = err.random_token
                return await self.async_step_captcha()
            except AccountLocked as err:
                _LOGGER.error("Account locked: %s", err)
                errors["base"] = "account_locked"
            except LoginError as err:
                _LOGGER.error("Login failed: %s", err)
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception during login")
                errors["base"] = "unknown"
            else:
                return await self._after_login()

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
                # Dismiss the notification
                persistent_notification.dismiss(self.hass, f"{DOMAIN}_captcha")
                return await self._after_login()

        # Save captcha image to www folder and show notification
        www_dir = self.hass.config.path("www")
        await self.hass.async_add_executor_job(os.makedirs, www_dir, True)

        img_data = base64.b64decode(self._img_code)
        filepath = os.path.join(www_dir, "uhomecp_captcha.jpg")
        await self.hass.async_add_executor_job(
            lambda: open(filepath, "wb").write(img_data)
        )

        # Show persistent notification with the image
        persistent_notification.create(
            self.hass,
            f'<img src="/local/uhomecp_captcha.jpg" alt="验证码" style="max-width:200px;">'
            f"\n\n请在下方输入验证码：",
            title="U管家验证码",
            notification_id=f"{DOMAIN}_captcha",
        )

        return self.async_show_form(
            step_id="captcha",
            data_schema=STEP_CAPTCHA_DATA_SCHEMA,
            errors=errors,
        )

    async def _after_login(self) -> FlowResult:
        """After successful login, get communities and show selection."""
        try:
            self._communities = await self._client.async_get_communities()
        except Exception:
            _LOGGER.exception("Failed to get communities")
            await self.async_set_unique_id(self._phone)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"U管家 ({self._phone})",
                data={
                    CONF_PHONE: self._phone,
                    CONF_PASSWORD: self._password,
                },
            )

        active = [c for c in self._communities if c.get("status") == 1]

        if len(active) == 0:
            return self.async_abort(reason="no_communities")

        if len(active) == 1:
            community = active[0]
            community_id = str(community["communityId"])
            community_name = community["communityName"]
            await self._client.async_set_community(community_id, community_name)
            await self.async_set_unique_id(f"{self._phone}_{community_id}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"{community_name} ({self._phone})",
                data={
                    CONF_PHONE: self._phone,
                    CONF_PASSWORD: self._password,
                    CONF_COMMUNITY_ID: community_id,
                    CONF_COMMUNITY_NAME: community_name,
                },
            )

        return await self.async_step_community()

    async def async_step_community(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle community selection step."""
        if user_input is not None:
            community_id = user_input[CONF_COMMUNITY_ID]
            community_name = ""
            for c in self._communities:
                if str(c["communityId"]) == community_id:
                    community_name = c["communityName"]
                    break

            await self._client.async_set_community(community_id, community_name)
            await self.async_set_unique_id(f"{self._phone}_{community_id}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"{community_name} ({self._phone})",
                data={
                    CONF_PHONE: self._phone,
                    CONF_PASSWORD: self._password,
                    CONF_COMMUNITY_ID: community_id,
                    CONF_COMMUNITY_NAME: community_name,
                },
            )

        active = [c for c in self._communities if c.get("status") == 1]
        options = {
            str(c["communityId"]): f"{c['communityName']} ({c['cityName']})"
            for c in active
        }

        return self.async_show_form(
            step_id="community",
            data_schema=vol.Schema(
                {vol.Required(CONF_COMMUNITY_ID): vol.In(options)}
            ),
        )
