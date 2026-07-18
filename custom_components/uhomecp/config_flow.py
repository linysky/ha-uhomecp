"""Config flow for U管家门禁 integration."""

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import AccountLocked, CaptchaRequired, LoginError, UHomeCPClient
from .const import (
    CONF_COMMUNITY_ID,
    CONF_COMMUNITY_NAME,
    CONF_PASSWORD,
    CONF_PHONE,
    DOMAIN,
)

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
                await self._client.async_login()
            except CaptchaRequired as err:
                self._img_code = err.img_code
                self._random_token = err.random_token
                # Some servers return 20010 but no captcha payload; fetch explicitly
                if not self._img_code:
                    try:
                        self._img_code, self._random_token = (
                            await self._client.async_get_captcha()
                        )
                    except Exception:
                        _LOGGER.exception("Failed to fetch captcha image")
                        errors["base"] = "unknown"
                        return self.async_show_form(
                            step_id="user",
                            data_schema=STEP_USER_DATA_SCHEMA,
                            errors=errors,
                        )
                return await self.async_step_captcha()
            except AccountLocked as err:
                _LOGGER.error("Account locked: %s", err)
                errors["base"] = "account_locked"
            except LoginError as err:
                _LOGGER.error("Login failed: %s", err)
                errors["base"] = "invalid_auth"
            except Exception as err:
                _LOGGER.exception("Unexpected error during login: %s", err)
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
        """Handle the captcha step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            captcha = user_input["captcha"]
            try:
                await self._client.async_login_with_captcha(
                    captcha, self._random_token
                )
            except LoginError as err:
                _LOGGER.error("Login with captcha failed: %s", err)
                errors["base"] = "invalid_captcha"
                # Get a fresh captcha
                try:
                    self._img_code, self._random_token = (
                        await self._client.async_get_captcha()
                    )
                except Exception:
                    _LOGGER.exception("Failed to refresh captcha")
                    errors["base"] = "unknown"
            except Exception as err:
                _LOGGER.exception("Unexpected error during captcha login: %s", err)
                errors["base"] = "unknown"
            else:
                return await self._after_login()

        # Build captcha image as HTML img tag (HA config flow supports HTML, not markdown)
        captcha_html = f'<img src="data:image/jpeg;base64,{self._img_code}" style="width:200px;">'

        return self.async_show_form(
            step_id="captcha",
            data_schema=STEP_CAPTCHA_DATA_SCHEMA,
            errors=errors,
            description_placeholders={"tip": captcha_html},
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
