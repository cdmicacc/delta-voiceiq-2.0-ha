"""API client for the Delta VoiceIQ cloud service."""
from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass

import aiohttp

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://device.deltafaucet.com"
USER_AGENT = "DFCatHome/2.6.0 CFNetwork/3860.400.51 Darwin/25.3.0"
DFC_SOURCE = "mobile"

LOGIN_PROVIDERS = ("apple", "google", "amazon")

_CODE_RE = re.compile(r"(delta\.code\.[A-Za-z0-9._-]+)")


class DeltaVoiceIQError(Exception):
    """Base error for all Delta VoiceIQ API failures."""


class InvalidCode(DeltaVoiceIQError):
    """The auth code was missing, malformed, expired, or already used."""


class CannotConnect(DeltaVoiceIQError):
    """Could not reach Delta, or its response could not be parsed."""


class NoDevicesFound(DeltaVoiceIQError):
    """UserInfo returned no usable devices for this account."""


class AuthExpired(DeltaVoiceIQError):
    """An authenticated call got a 401. Callers decide how to surface reauth."""


@dataclass
class DeltaDevice:
    """A single VoiceIQ device as returned by UserInfo."""

    mac_address: str
    name: str
    product_id: str | None = None


@dataclass
class ExchangeResult:
    """Result of exchanging a delta auth code for a usable session."""

    access_token: str
    user_id: str
    exp_timestamp: int | None
    devices: list[DeltaDevice]


def build_login_url(provider: str) -> str:
    """Build the Delta Auth/Login URL for the given sign-in provider."""
    if provider not in LOGIN_PROVIDERS:
        raise ValueError(f"Unknown provider: {provider!r}")
    return (
        f"{BASE_URL}/Auth/Login?provider={provider}"
        "&response_type=code&scope=profile_email&state=ha"
        "&redirect_uri=justaddwater://"
    )


def extract_code(raw: str) -> str:
    """Extract a delta.code.* value from a bare code or a justaddwater:// redirect."""
    match = _CODE_RE.search(raw.strip())
    if not match:
        raise InvalidCode(f"Could not find a delta.code.* value in: {raw!r}")
    return match.group(1)


def _b64_pad(value: str) -> str:
    """Restore URL-safe base64 padding so base64.b64decode doesn't choke."""
    value = value.replace("-", "+").replace("_", "/")
    return value + "=" * (-len(value) % 4)


def _decode_exp(access_token: str) -> int | None:
    """Decode the exp claim from a base64-encoded JWT access token.

    Returns None (does not raise) on any decode failure — an unparseable
    exp is a degraded-but-survivable state per the design spec, not a
    fatal one; the caller logs and surfaces it via the Token Expiry sensor.
    """
    try:
        jwt = base64.b64decode(_b64_pad(access_token)).decode("utf-8")
        payload_b64 = jwt.split(".")[1]
        payload = json.loads(base64.b64decode(_b64_pad(payload_b64)))
        return int(payload["exp"])
    except Exception:  # noqa: BLE001 - any decode failure is the same "unparseable" case
        _LOGGER.warning("Could not parse JWT exp claim from access token", exc_info=True)
        return None


class DeltaVoiceIQClient:
    """Thin async wrapper around Delta's VoiceIQ device API."""

    def __init__(self, session: aiohttp.ClientSession, access_token: str | None = None) -> None:
        self._session = session
        self.access_token = access_token

    def _headers(self, authenticated: bool = True) -> dict[str, str]:
        headers = {"dfc-source": DFC_SOURCE, "User-Agent": USER_AGENT}
        if authenticated:
            if not self.access_token:
                raise RuntimeError("No access token set on DeltaVoiceIQClient")
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    async def exchange_code(self, code: str) -> ExchangeResult:
        """Exchange a delta.code.* for an access token, then fetch UserInfo."""
        try:
            async with self._session.get(
                f"{BASE_URL}/Auth/PostAuth",
                params={"code": code, "state": "none"},
                headers=self._headers(authenticated=False),
                allow_redirects=False,
            ) as resp:
                location = resp.headers.get("Location")
        except aiohttp.ClientError as err:
            _LOGGER.warning("Network error calling PostAuth: %s", err)
            raise CannotConnect("Network error calling PostAuth") from err

        if not location:
            raise InvalidCode("PostAuth returned no redirect (bad/expired/used code)")

        if "#/auth/" not in location:
            _LOGGER.warning("PostAuth redirect missing #/auth/ payload: %s", location)
            raise CannotConnect("PostAuth redirect did not contain an auth payload")

        b64_payload = location.split("#/auth/", 1)[1]
        try:
            decoded = json.loads(base64.b64decode(_b64_pad(b64_payload)))
            access_token = decoded["Value"]["accessToken"]
        except Exception as err:  # noqa: BLE001 - any of decode/parse/key-lookup can fail here
            _LOGGER.warning("Failed to decode/extract accessToken from PostAuth payload: %s", err)
            raise CannotConnect("Could not parse PostAuth response") from err

        if len(access_token) < 100:
            _LOGGER.warning("Extracted accessToken suspiciously short (%d chars)", len(access_token))
            raise CannotConnect("Extracted access token looked invalid")

        self.access_token = access_token
        exp = _decode_exp(access_token)
        user_id, devices = await self.get_user_info()
        return ExchangeResult(access_token=access_token, user_id=user_id, exp_timestamp=exp, devices=devices)

    async def get_user_info(self) -> tuple[str, list[DeltaDevice]]:
        """Fetch UserInfo and return (user_id, usable_devices)."""
        try:
            async with self._session.get(
                f"{BASE_URL}/api/user/v2/UserInfo", headers=self._headers()
            ) as resp:
                if resp.status == 401:
                    raise AuthExpired("UserInfo rejected the access token")
                resp.raise_for_status()
                data = await resp.json()
        except aiohttp.ClientError as err:
            _LOGGER.warning("Network error calling UserInfo: %s", err)
            raise CannotConnect("Network error calling UserInfo") from err

        user_id = data.get("user", {}).get("id", "")
        devices = [
            DeltaDevice(mac_address=d["macAddress"], name=d["name"], product_id=d.get("productId"))
            for d in data.get("devices", [])
            if d.get("macAddress") and d.get("name")
        ]
        if not devices:
            raise NoDevicesFound("UserInfo returned no usable devices")
        return user_id, devices

    async def toggle_water(self, mac_address: str, on: bool) -> None:
        await self._post(
            "/api/device/v3/ToggleWater",
            params={"macAddress": mac_address, "toggle": "on" if on else "off"},
        )

    async def dispense(self, mac_address: str, milliliters: float) -> None:
        await self._post(
            "/api/device/v2/Dispense",
            params={"macAddress": mac_address, "milliliters": str(round(milliliters))},
        )

    async def hand_wash(self) -> None:
        await self._post("/api/voice/v4/handWashMode")

    async def get_usage(self, mac_address: str, interval: int) -> float:
        """Return summed usage in gallons for the given interval (0=today,1=week,2=month,3=year)."""
        try:
            async with self._session.get(
                f"{BASE_URL}/api/device/v2/UsageReport",
                params={"macAddress": mac_address, "interval": str(interval)},
                headers=self._headers(),
            ) as resp:
                if resp.status == 401:
                    raise AuthExpired("UsageReport rejected the access token")
                resp.raise_for_status()
                data = await resp.json()
        except aiohttp.ClientError as err:
            raise CannotConnect("Network error calling UsageReport") from err
        return sum(data["retObject"]["datasets"][0]["data"])

    async def _post(self, path: str, params: dict[str, str] | None = None) -> None:
        try:
            async with self._session.post(
                f"{BASE_URL}{path}", params=params or {}, headers=self._headers()
            ) as resp:
                if resp.status == 401:
                    raise AuthExpired(f"{path} rejected the access token")
                resp.raise_for_status()
        except aiohttp.ClientError as err:
            raise CannotConnect(f"Network error calling {path}") from err


_ML_PER_UNIT = {
    "ml": 1.0,
    "l": 1000.0,
    "gal": 3785.411784,
    "fl_oz": 29.5735295625,
}


def convert_to_ml(amount: float, unit: str) -> float:
    """Convert an amount in the given unit to milliliters for the Dispense API."""
    if unit not in _ML_PER_UNIT:
        raise ValueError(f"Unsupported dispense unit: {unit!r}")
    return amount * _ML_PER_UNIT[unit]
