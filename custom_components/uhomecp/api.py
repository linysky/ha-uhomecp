"""API client for uhomecp."""

import asyncio
import base64
import logging
from typing import Any

import requests
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives import serialization

from .const import (
    BASE_URL,
    CAPTCHA_URL,
    COMMUNITY_LIST_URL,
    DEFAULT_HEADERS,
    DOOR_LIST_URL,
    LOGIN_URL,
    OPEN_DOOR_URL,
    RSA_PUBLIC_KEY,
)

_LOGGER = logging.getLogger(__name__)

# Code indicating captcha is required
CODE_NEED_CAPTCHA = "20010"
CODE_SUCCESS = "0"
CODE_SESSION_EXPIRED = "0000002"


# RSA public key - cached once at module level
_public_key = serialization.load_pem_public_key(RSA_PUBLIC_KEY.encode())  # type: ignore[union-attr]


def encrypt_password(password: str) -> str:
    """Encrypt password: Base64 encode -> RSA encrypt -> base64 output.

    Replicates the sg-rsa.js encryptLong flow from the H5 frontend.
    """
    pwd_b64 = base64.b64encode(password.encode()).decode()
    encrypted = _public_key.encrypt(pwd_b64.encode(), asym_padding.PKCS1v15())
    return base64.b64encode(encrypted).decode()


class UHomeCPApiError(Exception):
    """Base exception for uhomecp API errors."""


class LoginError(UHomeCPApiError):
    """Login failed."""


class AccountLocked(UHomeCPApiError):
    """Account is locked due to too many failed attempts."""


class CaptchaRequired(UHomeCPApiError):
    """Captcha is required to complete login."""

    def __init__(self, img_code: str, random_token: str) -> None:
        self.img_code = img_code
        self.random_token = random_token


class UHomeCPClient:
    """uhomecp API client."""

    def __init__(self, phone: str, password: str) -> None:
        self.phone = phone
        self.password = password
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.logged_in = False
        self.user_info: dict[str, Any] = {}
        self.community_id: str = ""
        self.community_name: str = ""
        self.doors: list[dict[str, Any]] = []
        self._warmed_up = False

    def get_session_cookies(self) -> dict[str, str]:
        """Export session cookies for persistence."""
        return dict(self.session.cookies)

    def set_session_cookies(self, cookies: dict[str, str]) -> None:
        """Restore session cookies from saved state."""
        for name, value in cookies.items():
            self.session.cookies.set(name, value, domain="www.uhomecp.com")
        self._warmed_up = True

    def set_user_info(self, user_info: dict[str, Any]) -> None:
        """Restore user info from saved state."""
        self.user_info = user_info
        self.logged_in = True

    def _warmup(self) -> None:
        """Warm up the session by getting r_ua cookie from server.

        The server requires a r_ua cookie for login validation.
        This cookie is set in the response of the first request.
        """
        if self._warmed_up:
            return
        self.session.post(
            f"{BASE_URL}{LOGIN_URL}",
            data="loginType=1&password=warmup&tel=00000000000",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        self._warmed_up = True
        _LOGGER.debug("Warmup complete, cookies: %s", dict(self.session.cookies))

    def login(self) -> dict[str, Any]:
        """Login with phone + password (RSA encrypted).

        Returns:
            {"success": True, "userId": "..."} on success

        Raises:
            CaptchaRequired: if captcha is needed (contains img_code + random_token)
            LoginError: on other failures
        """
        self._warmup()
        encrypted_pwd = encrypt_password(self.password)

        data = {
            "loginType": "1",
            "password": encrypted_pwd,
            "tel": self.phone,
            "clientId": "wx",
            "md5Flag": "true",
        }

        resp = self.session.post(
            f"{BASE_URL}{LOGIN_URL}",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        result = resp.json()
        code = result.get("code", "")

        if code == CODE_SUCCESS:
            self.logged_in = True
            self.user_info = result.get("data", {})
            _LOGGER.info("Login successful for %s", self.phone)
            return {"success": True, "data": self.user_info}

        if code == CODE_NEED_CAPTCHA:
            _LOGGER.info("Captcha required for %s", self.phone)
            img_code, random_token = self.get_captcha()
            raise CaptchaRequired(img_code, random_token)

        msg = result.get("msg") or result.get("message", "Unknown error")
        if "锁定" in msg or "locked" in msg.lower():
            _LOGGER.error("Account locked: %s", msg)
            raise AccountLocked(msg)
        _LOGGER.error("Login failed: %s", msg)
        raise LoginError(msg)

    def login_with_captcha(self, captcha: str, random_token: str) -> dict[str, Any]:
        """Login with captcha.

        Args:
            captcha: The captcha text entered by the user.
            random_token: The random token from get_captcha().

        Returns:
            {"success": True, "userId": "..."} on success
        """
        self._warmup()
        encrypted_pwd = encrypt_password(self.password)

        data = {
            "loginType": "1",
            "password": encrypted_pwd,
            "tel": self.phone,
            "clientId": "wx",
            "md5Flag": "true",
            "imgCode": captcha,
            "randomToken": random_token,
        }

        resp = self.session.post(
            f"{BASE_URL}{LOGIN_URL}",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        result = resp.json()

        if result.get("code") == CODE_SUCCESS:
            self.logged_in = True
            self.user_info = result.get("data", {})
            _LOGGER.info("Login with captcha successful for %s", self.phone)
            return {"success": True, "data": self.user_info}

        msg = result.get("msg") or result.get("message", "Unknown error")
        if "锁定" in msg or "locked" in msg.lower():
            _LOGGER.error("Account locked during captcha login: %s", msg)
            raise AccountLocked(msg)
        _LOGGER.error("Login with captcha failed: %s", msg)
        raise LoginError(msg)

    def get_captcha(self) -> tuple[str, str]:
        """Get captcha image from server.

        Returns:
            (img_code_base64, random_token)
        """
        self._warmup()
        resp = self.session.get(f"{BASE_URL}{CAPTCHA_URL}")
        result = resp.json()
        data = result.get("data", {})
        img_code = data.get("imgCode", "")
        random_token = data.get("randomToken", "")
        _LOGGER.debug("Got captcha: imgCode=%d bytes, randomToken=%s", len(img_code), random_token[:20] if random_token else "empty")
        return img_code, random_token

    def get_communities(self) -> list[dict[str, Any]]:
        """Get list of communities for the logged-in user.

        Returns list of community dicts with keys:
            communityId, communityName, cityName, provinceName, status
        """
        if not self.logged_in:
            raise UHomeCPApiError("Not logged in")

        resp = self.session.get(f"{BASE_URL}{COMMUNITY_LIST_URL}")
        result = resp.json()

        if result.get("code") == CODE_SUCCESS:
            communities = result.get("data", [])
            _LOGGER.info("Found %d communities", len(communities))
            return communities

        msg = result.get("msg") or result.get("message", "Unknown error")
        raise UHomeCPApiError(f"Failed to get communities: {msg}")

    def set_community(self, community_id: str, community_name: str) -> None:
        """Set the active community for subsequent API calls."""
        self.community_id = community_id
        self.community_name = community_name
        _LOGGER.info("Community set to %s (%s)", community_name, community_id)

    def _ensure_login(self) -> None:
        """Ensure we have a valid session, re-login if needed."""
        if not self.logged_in:
            raise UHomeCPApiError("Not logged in")

    def _request_with_relogin(self, method: str, url: str, **kwargs) -> dict:
        """Make an API request with automatic re-login on session expiry."""
        resp = self.session.request(method, url, **kwargs)
        result = resp.json()

        if result.get("code") == CODE_SESSION_EXPIRED:
            _LOGGER.warning("Session expired, re-logging in")
            self.login()  # may raise CaptchaRequired or LoginError
            resp = self.session.request(method, url, **kwargs)
            result = resp.json()

        return result

    def get_doors(self) -> list[dict[str, Any]]:
        """Get list of doors for the user's community.

        Returns list of door dicts with keys: doorId, doorIdStr, name, doorType.
        """
        self._ensure_login()

        result = self._request_with_relogin(
            "GET",
            f"{BASE_URL}{DOOR_LIST_URL}",
            params={
                "communityId": self.community_id,
                "custId": str(self.user_info.get("userId", "")),
            },
        )

        if result.get("code") == CODE_SUCCESS:
            self.doors = result.get("data", [])
            if self.doors and not self.community_id:
                self.community_id = str(self.doors[0].get("communityId", ""))
            _LOGGER.info("Found %d doors", len(self.doors))
            return self.doors

        msg = result.get("msg") or result.get("message", "Unknown error")
        raise UHomeCPApiError(f"Failed to get doors: {msg}")

    def open_door(self, door_id: str, door_id_str: str) -> bool:
        """Open a specific door.

        Uses application/json content type (not form-urlencoded).

        Args:
            door_id: The door ID (numeric).
            door_id_str: The door string ID.

        Returns True on success.
        """
        self._ensure_login()

        data = {
            "custId": str(self.user_info.get("userId", "")),
            "userId": str(self.user_info.get("userId", "")),
            "doorId": str(door_id),
            "communityId": self.community_id,
            "doorIdStr": str(door_id_str),
            "appVersion": "2.3",
            "appType": "2",
        }

        result = self._request_with_relogin(
            "POST",
            f"{BASE_URL}{OPEN_DOOR_URL}",
            json=data,
        )

        if result.get("code") == CODE_SUCCESS:
            _LOGGER.info("Door %s opened successfully", door_id)
            return True

        msg = result.get("msg") or result.get("message", "Unknown error")
        _LOGGER.error("Failed to open door %s: %s", door_id, msg)
        raise UHomeCPApiError(f"Failed to open door: {msg}")

    async def async_login(self) -> dict[str, Any]:
        """Async wrapper for login."""
        return await asyncio.to_thread(self.login)

    async def async_login_with_captcha(
        self, captcha: str, random_token: str
    ) -> dict[str, Any]:
        """Async wrapper for login_with_captcha."""
        return await asyncio.to_thread(
            self.login_with_captcha, captcha, random_token
        )

    async def async_get_captcha(self) -> tuple[str, str]:
        """Async wrapper for get_captcha."""
        return await asyncio.to_thread(self.get_captcha)

    async def async_get_communities(self) -> list[dict[str, Any]]:
        """Async wrapper for get_communities."""
        return await asyncio.to_thread(self.get_communities)

    async def async_set_community(
        self, community_id: str, community_name: str
    ) -> None:
        """Async wrapper for set_community."""
        await asyncio.to_thread(self.set_community, community_id, community_name)

    async def async_get_doors(self) -> list[dict[str, Any]]:
        """Async wrapper for get_doors."""
        return await asyncio.to_thread(self.get_doors)

    async def async_open_door(self, door_id: str, door_id_str: str) -> bool:
        """Async wrapper for open_door."""
        return await asyncio.to_thread(self.open_door, door_id, door_id_str)
