"""API client for the Delta VoiceIQ cloud service."""
from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass

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
