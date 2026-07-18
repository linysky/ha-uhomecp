"""API client for U管家门禁."""

import asyncio
import base64
import logging
from typing import Any

import requests
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives import serialization

from .const import (
    BASE_URL,
    DEFAULT_HEADERS,
    DOOR_LIST_URL,
    LOGIN_URL,
    OPEN_DOOR_URL,
    RSA_PUBLIC_KEY,
)

_LOGGER = logging.getLogger(__name__)


def encrypt_password(password: str) -> str:
    """Encrypt password: Base64 encode -> RSA encrypt -> base64 output.

    Replicates the sg-rsa.js encryptLong flow from the H5 frontend.
    """
    # 1. Base64 encode the password
    pwd_b64 = base64.b64encode(password.encode()).decode()

    # 2. Load RSA public key
    public_key = serialization.load_pem_public_key(RSA_PUBLIC_KEY.encode())

    # 3. RSA encrypt with PKCS1v15
    encrypted = public_key.encrypt(pwd_b64.encode(), asym_padding.PKCS1v15())

    # 4. Return base64 encoded ciphertext
    return base64.b64encode(encrypted).decode()


class UHomeCPApiError(Exception):
    """Base exception for U管家 API errors."""


class LoginError(UHomeCPApiError):
    """Login failed."""


class DoorNotFoundError(UHomeCPApiError):
    """Door not found."""


class UHomeCPClient:
    """U管家 API client."""

    def __init__(self, phone: str, password: str) -> None:
        self.phone = phone
        self.password = password
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.logged_in = False
        self.user_info: dict[str, Any] = {}
        self.doors: list[dict[str, Any]] = []

    def login(self) -> bool:
        """Login with phone + password (RSA encrypted).

        Returns True on success, raises LoginError on failure.
        """
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

        if result.get("code") == "0":
            self.logged_in = True
            self.user_info = result.get("data", {})
            _LOGGER.info("Login successful for %s", self.phone)
            return True

        msg = result.get("msg") or result.get("message", "Unknown error")
        _LOGGER.error("Login failed: %s", msg)
        raise LoginError(msg)

    def get_doors(self) -> list[dict[str, Any]]:
        """Get list of doors for the user's community.

        Returns list of door dicts with keys: doorId, doorIdStr, name, doorType.
        """
        if not self.logged_in:
            self.login()

        community_id = self.user_info.get("communityId", "")
        cust_id = self.user_info.get("custId", "")

        resp = self.session.get(
            f"{BASE_URL}{DOOR_LIST_URL}",
            params={"communityId": community_id, "custId": cust_id},
        )
        result = resp.json()

        if result.get("code") == "0":
            self.doors = result.get("data", [])
            _LOGGER.info("Found %d doors", len(self.doors))
            return self.doors

        # Session might have expired, try re-login
        if result.get("code") in ("0000002", "-1"):
            _LOGGER.warning("Session expired, re-logging in")
            self.login()
            return self.get_doors()

        msg = result.get("msg") or result.get("message", "Unknown error")
        raise UHomeCPApiError(f"Failed to get doors: {msg}")

    def open_door(self, door_id: str, door_id_str: str) -> bool:
        """Open a specific door.

        Args:
            door_id: The door ID (numeric).
            door_id_str: The door string ID.

        Returns True on success.
        """
        if not self.logged_in:
            self.login()

        data = {
            "custId": str(self.user_info.get("custId", "")),
            "userId": str(self.user_info.get("userId", "")),
            "doorId": str(door_id),
            "communityId": str(self.user_info.get("communityId", "")),
            "doorIdStr": str(door_id_str),
            "appVersion": "2.3",
            "appType": "2",
        }

        resp = self.session.post(
            f"{BASE_URL}{OPEN_DOOR_URL}",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        result = resp.json()

        if result.get("code") == "0":
            _LOGGER.info("Door %s opened successfully", door_id)
            return True

        # Session might have expired, try re-login
        if result.get("code") in ("0000002",):
            _LOGGER.warning("Session expired during open_door, re-logging in")
            self.login()
            return self.open_door(door_id, door_id_str)

        msg = result.get("msg") or result.get("message", "Unknown error")
        _LOGGER.error("Failed to open door %s: %s", door_id, msg)
        raise UHomeCPApiError(f"Failed to open door: {msg}")

    async def async_login(self) -> bool:
        """Async wrapper for login."""
        return await asyncio.to_thread(self.login)

    async def async_get_doors(self) -> list[dict[str, Any]]:
        """Async wrapper for get_doors."""
        return await asyncio.to_thread(self.get_doors)

    async def async_open_door(self, door_id: str, door_id_str: str) -> bool:
        """Async wrapper for open_door."""
        return await asyncio.to_thread(self.open_door, door_id, door_id_str)
