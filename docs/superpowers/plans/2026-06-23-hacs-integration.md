# Delta VoiceIQ HACS Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the manual HA package/shell-script/HTML-page setup with a proper `custom_components/delta_voiceiq` HACS integration: config-flow onboarding, one device per faucet, native reauth, and a `valve` + `sensor` + service-based entity model.

**Architecture:** A single `DeltaVoiceIQClient` (aiohttp-based) wraps Delta's API. A config flow exchanges a pasted auth code for a token and auto-discovers devices via `UserInfo`. Four `DataUpdateCoordinator` instances per entry poll `UsageReport` at independent cadences. A `valve` entity and two services (`dispense`, `hand_wash`) drive faucet actions; sensors expose usage, token expiry, and diagnostics. 401s trigger HA's native reauth flow (coordinator path automatic, service/valve path via `entry.async_start_reauth()`).

**Tech Stack:** Python 3, Home Assistant custom integration APIs (`config_entries`, `DataUpdateCoordinator`, `valve`/`sensor` platforms, `issue_registry`), `aiohttp`, `voluptuous`, `pytest` + `pytest-homeassistant-custom-component` for tests.

## Global Constraints

- Domain: `delta_voiceiq`. Package root: `custom_components/delta_voiceiq/`.
- No `secrets.yaml`, no shell scripts, no on-disk file mutation by the integration — all state lives in the config entry.
- `manifest.json`: `config_flow: true`, `iot_class: cloud_polling`, `integration_type: device`.
- Delta API base URL: `https://device.deltafaucet.com`. Required headers on every call: `dfc-source: mobile`, `User-Agent: DFCatHome/2.6.0 CFNetwork/3860.400.51 Darwin/25.3.0`, plus `Authorization: Bearer <token>` on authenticated calls.
- Usage sensors: `device_class: water`, native unit liters, no mL/fl_oz (not supported by HA's water device class). `delta_voiceiq.dispense`'s `unit` field supports `ml`/`l`/`gal`/`fl_oz` via custom conversion code (not device-class-derived).
- Poll cadences: today=10min, week=1hr, month=5hr, year=24hr, each its own `DataUpdateCoordinator`.
- 401 from the `UsageReport` coordinator → raise `ConfigEntryAuthFailed`. 401 from `ToggleWater`/`Dispense`/`handWashMode` → catch and call `entry.async_start_reauth(hass)`.
- Config-flow auth errors: `invalid_code` (PostAuth returned no redirect) vs `cannot_connect` (any other parse/decode/extract failure) — always log the specific underlying cause at `WARNING`.
- `delta_voiceiq.dispense`/`delta_voiceiq.hand_wash` target the valve `entity_id`, not the device.
- Token Expiry sensor: no `entity_category`. MAC Address and User ID sensors: `entity_category: diagnostic`.
- GitHub repo: `cdmicacc/delta-voiceiq-2.0-ha`. Codeowner handle: `@cdmicacc`.

---

## File Structure

```
custom_components/delta_voiceiq/
├── __init__.py        # async_setup_entry/async_unload_entry, runtime data, services, expiry Repair checks
├── const.py            # DOMAIN, config keys, intervals, provider list
├── manifest.json
├── api.py              # DeltaVoiceIQClient, exceptions, pure helpers (build_login_url, extract_code)
├── config_flow.py      # user + reauth steps, device picker
├── coordinator.py      # DeltaUsageCoordinator
├── valve.py            # DeltaFaucetValve entity
├── sensor.py            # usage sensors, token expiry sensor, MAC/user-id diagnostic sensors
├── services.yaml        # dispense / hand_wash schemas
├── strings.json
└── translations/
    └── en.json
hacs.json                # repo metadata for HACS custom-repository install
tests/
├── conftest.py
├── test_api.py
├── test_config_flow.py
├── test_coordinator.py
├── test_valve.py
└── test_sensor.py
```

---

## Task 1: Project scaffolding and test harness

**Files:**
- Create: `custom_components/delta_voiceiq/__init__.py` (empty placeholder, filled in Task 7)
- Create: `custom_components/delta_voiceiq/const.py`
- Create: `custom_components/delta_voiceiq/manifest.json`
- Create: `hacs.json`
- Create: `requirements_test.txt`
- Create: `pytest.ini`
- Create: `tests/conftest.py`
- Create: `tests/__init__.py`
- Create: `custom_components/__init__.py` (empty, makes the dir a package for test discovery)
- Create: `custom_components/delta_voiceiq/translations/.gitkeep`

**Interfaces:**
- Produces: `DOMAIN = "delta_voiceiq"`, `LOGIN_PROVIDERS = ("apple", "google", "amazon")`, `CONF_ACCESS_TOKEN`, `CONF_MAC_ADDRESS`, `CONF_USER_ID`, `CONF_EXP_TIMESTAMP`, `CONF_DEVICE_NAME` (all `str` constants), `USAGE_INTERVALS: dict[str, int]` mapping `"today"/"week"/"month"/"year"` → `0/1/2/3`, `SCAN_INTERVALS: dict[str, timedelta]` matching cadences, `TOKEN_EXPIRY_WARNING_DAYS = 7`.

- [ ] **Step 1: Create `const.py`**

```python
"""Constants for the Delta VoiceIQ integration."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "delta_voiceiq"

LOGIN_PROVIDERS = ("apple", "google", "amazon")

CONF_ACCESS_TOKEN = "access_token"
CONF_MAC_ADDRESS = "mac_address"
CONF_USER_ID = "user_id"
CONF_EXP_TIMESTAMP = "exp_timestamp"
CONF_DEVICE_NAME = "device_name"

USAGE_INTERVALS: dict[str, int] = {
    "today": 0,
    "week": 1,
    "month": 2,
    "year": 3,
}

SCAN_INTERVALS: dict[str, timedelta] = {
    "today": timedelta(minutes=10),
    "week": timedelta(hours=1),
    "month": timedelta(hours=5),
    "year": timedelta(hours=24),
}

TOKEN_EXPIRY_WARNING_DAYS = 7

GALLONS_PER_LITER = 0.264172
```

- [ ] **Step 2: Create `manifest.json`**

```json
{
  "domain": "delta_voiceiq",
  "name": "Delta VoiceIQ",
  "config_flow": true,
  "iot_class": "cloud_polling",
  "integration_type": "device",
  "codeowners": ["@cdmicacc"],
  "documentation": "https://github.com/cdmicacc/delta-voiceiq-2.0-ha",
  "issue_tracker": "https://github.com/cdmicacc/delta-voiceiq-2.0-ha/issues",
  "requirements": [],
  "version": "1.0.0"
}
```

- [ ] **Step 3: Create `hacs.json`**

```json
{
  "name": "Delta VoiceIQ",
  "render_readme": true,
  "homeassistant": "2024.1.0"
}
```

- [ ] **Step 4: Create empty package markers**

```bash
mkdir -p custom_components/delta_voiceiq/translations
touch custom_components/__init__.py
touch custom_components/delta_voiceiq/translations/.gitkeep
touch tests/__init__.py
echo '"""Delta VoiceIQ integration (placeholder, filled in by Task 7)."""' > custom_components/delta_voiceiq/__init__.py
```

- [ ] **Step 5: Create `requirements_test.txt`**

```
pytest-homeassistant-custom-component==0.13.340
aioresponses==0.7.9
```

(Verified against PyPI on 2026-06-23: 0.13.340 is the real latest `pytest-homeassistant-custom-component`. Don't separately pin `pytest`/`pytest-asyncio`/`pytest-aiohttp` — that package's own `requires_dist` strictly pins exact compatible versions of all three internally, e.g. `pytest==9.0.3`, `pytest-asyncio==1.3.0`. Hand-pinning a different version of any of them, as an earlier draft of this plan did, creates an unsatisfiable dependency conflict at install time.)

- [ ] **Step 6: Create `pytest.ini`**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- [ ] **Step 7: Create `tests/conftest.py`**

```python
"""Shared test fixtures."""
import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Make custom_components/ visible to Home Assistant during tests."""
    yield
```

- [ ] **Step 8: Install test dependencies and verify the harness loads**

Run: `pip install -r requirements_test.txt`
Run: `pytest tests/ -v`
Expected: `no tests ran` (collected 0 items) with no import/collection errors — confirms `pytest-homeassistant-custom-component` and the `custom_components` package layout are wired up correctly before any real test exists.

- [ ] **Step 9: Commit**

```bash
git add custom_components hacs.json requirements_test.txt pytest.ini tests
git commit -m "chore: scaffold delta_voiceiq custom integration and test harness"
```

---

## Task 2: `api.py` — exceptions, models, and pure helpers

**Files:**
- Create: `custom_components/delta_voiceiq/api.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Produces: exceptions `DeltaVoiceIQError`, `InvalidCode`, `CannotConnect`, `NoDevicesFound`, `AuthExpired` (all subclass `DeltaVoiceIQError`); dataclasses `DeltaDevice(mac_address: str, name: str, product_id: str | None)` and `ExchangeResult(access_token: str, user_id: str, exp_timestamp: int | None, devices: list[DeltaDevice])`; functions `build_login_url(provider: str) -> str` and `extract_code(raw: str) -> str`.

- [ ] **Step 1: Write failing tests for `build_login_url` and `extract_code`**

```python
"""Tests for pure helpers in api.py."""
import pytest

from custom_components.delta_voiceiq.api import InvalidCode, build_login_url, extract_code


def test_build_login_url_apple():
    url = build_login_url("apple")
    assert url.startswith("https://device.deltafaucet.com/Auth/Login?provider=apple")
    assert "redirect_uri=justaddwater://" in url


def test_build_login_url_rejects_unknown_provider():
    with pytest.raises(ValueError):
        build_login_url("facebook")


def test_extract_code_from_bare_code():
    assert extract_code("delta.code.ABC123") == "delta.code.ABC123"


def test_extract_code_from_full_redirect_url():
    raw = "justaddwater://?code=delta.code.ABC123&state=xyz"
    assert extract_code(raw) == "delta.code.ABC123"


def test_extract_code_strips_whitespace():
    assert extract_code("  delta.code.ABC123  \n") == "delta.code.ABC123"


def test_extract_code_raises_on_garbage_input():
    with pytest.raises(InvalidCode):
        extract_code("not a code at all")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.delta_voiceiq.api'` (the module doesn't exist yet).

- [ ] **Step 3: Implement `api.py` (exceptions, models, helpers only — network methods come in Tasks 3-4)**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add custom_components/delta_voiceiq/api.py tests/test_api.py
git commit -m "feat: add Delta VoiceIQ API exceptions, models, and URL/code helpers"
```

---

## Task 3: `api.py` — `DeltaVoiceIQClient.exchange_code` and `get_user_info`

**Files:**
- Modify: `custom_components/delta_voiceiq/api.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- Consumes: `_b64_pad`, `_decode_exp`, `DeltaDevice`, `ExchangeResult`, `InvalidCode`, `CannotConnect`, `NoDevicesFound`, `AuthExpired` from Task 2.
- Produces: `DeltaVoiceIQClient(session: aiohttp.ClientSession, access_token: str | None = None)` with `async def exchange_code(self, code: str) -> ExchangeResult` and `async def get_user_info(self) -> tuple[str, list[DeltaDevice]]`. After a successful `exchange_code`, `self.access_token` is set.

- [ ] **Step 1: Write failing tests using `aioresponses` to mock Delta's HTTP responses**

Append to `tests/test_api.py`:

```python
import base64
import json

import aiohttp
from aioresponses import aioresponses

from custom_components.delta_voiceiq.api import (
    CannotConnect,
    DeltaVoiceIQClient,
    InvalidCode,
    NoDevicesFound,
)


def _b64(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


def _fake_access_token(exp: int = 9999999999) -> str:
    """Build a fake 'access token' shaped like Delta's: base64(jwt-string)."""
    header = _b64(json.dumps({"alg": "none"}))
    payload = _b64(json.dumps({"exp": exp}))
    jwt = f"{header}.{payload}.sig"
    # Delta's accessToken field is itself base64-encoded JWT text, padded out
    # past the 100-char floor api.py checks for.
    return _b64(jwt) + "A" * 60


REAL_USER_INFO_RESPONSE = {
    "user": {"id": "9cdf1a02bde344ca938157c9ab086278"},
    "devices": [
        {
            "id": "825e5c85eb6144f8b3ef76370665344a",
            "name": "Kitchen Faucet",
            "macAddress": "84712732CBBB",
            "isDefault": True,
            "productId": "DELTA1-VOICE",
            "currentUsage": "21.40",
        }
    ],
    "uiDevices": [],
    "containers": [],
    "modes": [],
}


@pytest.mark.asyncio
async def test_exchange_code_success():
    access_token = _fake_access_token()
    post_auth_payload = _b64(json.dumps({"Value": {"accessToken": access_token}}))
    with aioresponses() as mocked:
        mocked.get(
            "https://device.deltafaucet.com/Auth/PostAuth?code=delta.code.ABC123&state=none",
            status=302,
            headers={"Location": f"https://device.deltafaucet.com/#/auth/{post_auth_payload}"},
        )
        mocked.get(
            "https://device.deltafaucet.com/api/user/v2/UserInfo",
            payload=REAL_USER_INFO_RESPONSE,
        )
        async with aiohttp.ClientSession() as session:
            client = DeltaVoiceIQClient(session)
            result = await client.exchange_code("delta.code.ABC123")

    assert result.access_token == access_token
    assert result.user_id == "9cdf1a02bde344ca938157c9ab086278"
    assert result.exp_timestamp == 9999999999
    assert len(result.devices) == 1
    assert result.devices[0].mac_address == "84712732CBBB"
    assert result.devices[0].name == "Kitchen Faucet"
    assert client.access_token == access_token


@pytest.mark.asyncio
async def test_exchange_code_no_redirect_raises_invalid_code():
    with aioresponses() as mocked:
        mocked.get(
            "https://device.deltafaucet.com/Auth/PostAuth?code=delta.code.BAD&state=none",
            status=200,
        )
        async with aiohttp.ClientSession() as session:
            client = DeltaVoiceIQClient(session)
            with pytest.raises(InvalidCode):
                await client.exchange_code("delta.code.BAD")


@pytest.mark.asyncio
async def test_exchange_code_undecodable_payload_raises_cannot_connect():
    with aioresponses() as mocked:
        mocked.get(
            "https://device.deltafaucet.com/Auth/PostAuth?code=delta.code.ABC123&state=none",
            status=302,
            headers={"Location": "https://device.deltafaucet.com/#/auth/not-valid-base64!!!"},
        )
        async with aiohttp.ClientSession() as session:
            client = DeltaVoiceIQClient(session)
            with pytest.raises(CannotConnect):
                await client.exchange_code("delta.code.ABC123")


@pytest.mark.asyncio
async def test_get_user_info_raises_no_devices_found_when_empty():
    with aioresponses() as mocked:
        mocked.get(
            "https://device.deltafaucet.com/api/user/v2/UserInfo",
            payload={"user": {"id": "u1"}, "devices": []},
        )
        async with aiohttp.ClientSession() as session:
            client = DeltaVoiceIQClient(session, access_token="sometoken")
            with pytest.raises(NoDevicesFound):
                await client.get_user_info()


@pytest.mark.asyncio
async def test_get_user_info_filters_malformed_devices():
    with aioresponses() as mocked:
        mocked.get(
            "https://device.deltafaucet.com/api/user/v2/UserInfo",
            payload={
                "user": {"id": "u1"},
                "devices": [
                    {"id": "1", "name": "Kitchen Faucet", "macAddress": "AABBCCDDEEFF"},
                    {"id": "2", "macAddress": "112233445566"},  # missing name
                ],
            },
        )
        async with aiohttp.ClientSession() as session:
            client = DeltaVoiceIQClient(session, access_token="sometoken")
            user_id, devices = await client.get_user_info()

    assert user_id == "u1"
    assert len(devices) == 1
    assert devices[0].mac_address == "AABBCCDDEEFF"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api.py -v`
Expected: FAIL with `AttributeError: module 'custom_components.delta_voiceiq.api' has no attribute 'DeltaVoiceIQClient'`

- [ ] **Step 3: Implement `DeltaVoiceIQClient.__init__`, `_headers`, `exchange_code`, `get_user_info`**

Append to `custom_components/delta_voiceiq/api.py` (add `import aiohttp` to the top-of-file imports alongside the existing ones):

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api.py -v`
Expected: PASS (11 passed)

- [ ] **Step 5: Commit**

```bash
git add custom_components/delta_voiceiq/api.py tests/test_api.py
git commit -m "feat: implement DeltaVoiceIQClient code exchange and UserInfo lookup"
```

---

## Task 4: `api.py` — `toggle_water`, `dispense`, `hand_wash`, `get_usage`, unit conversion

**Files:**
- Modify: `custom_components/delta_voiceiq/api.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- Consumes: `DeltaVoiceIQClient`, `AuthExpired`, `CannotConnect` from Task 3.
- Produces: `async def toggle_water(self, mac_address: str, on: bool) -> None`, `async def dispense(self, mac_address: str, milliliters: float) -> None`, `async def hand_wash(self) -> None`, `async def get_usage(self, mac_address: str, interval: int) -> float` (returns gallons, matching the API's native unit) on `DeltaVoiceIQClient`; pure function `convert_to_ml(amount: float, unit: str) -> float` accepting `unit` in `{"ml", "l", "gal", "fl_oz"}`.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_api.py`:

```python
from custom_components.delta_voiceiq.api import AuthExpired, convert_to_ml


def test_convert_to_ml_passthrough():
    assert convert_to_ml(500, "ml") == 500


def test_convert_to_ml_liters():
    assert convert_to_ml(1, "l") == 1000


def test_convert_to_ml_gallons():
    assert round(convert_to_ml(1, "gal"), 1) == 3785.4


def test_convert_to_ml_fl_oz():
    assert round(convert_to_ml(1, "fl_oz"), 1) == 29.6


def test_convert_to_ml_rejects_unknown_unit():
    with pytest.raises(ValueError):
        convert_to_ml(1, "cups")


@pytest.mark.asyncio
async def test_toggle_water_on_sends_correct_request():
    with aioresponses() as mocked:
        mocked.post(
            "https://device.deltafaucet.com/api/device/v3/ToggleWater?macAddress=AABBCCDDEEFF&toggle=on",
            status=200,
            payload={"retCode": 0, "retMessage": "Success"},
        )
        async with aiohttp.ClientSession() as session:
            client = DeltaVoiceIQClient(session, access_token="tok")
            await client.toggle_water("AABBCCDDEEFF", on=True)  # no exception = success


@pytest.mark.asyncio
async def test_toggle_water_401_raises_auth_expired():
    with aioresponses() as mocked:
        mocked.post(
            "https://device.deltafaucet.com/api/device/v3/ToggleWater?macAddress=AABBCCDDEEFF&toggle=off",
            status=401,
        )
        async with aiohttp.ClientSession() as session:
            client = DeltaVoiceIQClient(session, access_token="tok")
            with pytest.raises(AuthExpired):
                await client.toggle_water("AABBCCDDEEFF", on=False)


@pytest.mark.asyncio
async def test_dispense_rounds_milliliters_into_request():
    with aioresponses() as mocked:
        mocked.post(
            "https://device.deltafaucet.com/api/device/v2/Dispense?macAddress=AABBCCDDEEFF&milliliters=355",
            status=200,
        )
        async with aiohttp.ClientSession() as session:
            client = DeltaVoiceIQClient(session, access_token="tok")
            await client.dispense("AABBCCDDEEFF", 355.0)


@pytest.mark.asyncio
async def test_hand_wash_success():
    with aioresponses() as mocked:
        mocked.post(
            "https://device.deltafaucet.com/api/voice/v4/handWashMode",
            status=200,
        )
        async with aiohttp.ClientSession() as session:
            client = DeltaVoiceIQClient(session, access_token="tok")
            await client.hand_wash()


@pytest.mark.asyncio
async def test_get_usage_sums_dataset():
    with aioresponses() as mocked:
        mocked.get(
            "https://device.deltafaucet.com/api/device/v2/UsageReport?macAddress=AABBCCDDEEFF&interval=1",
            payload={"retObject": {"datasets": [{"data": [1.5, 2.5, 3.0]}]}},
        )
        async with aiohttp.ClientSession() as session:
            client = DeltaVoiceIQClient(session, access_token="tok")
            result = await client.get_usage("AABBCCDDEEFF", 1)

    assert result == 7.0


@pytest.mark.asyncio
async def test_get_usage_401_raises_auth_expired():
    with aioresponses() as mocked:
        mocked.get(
            "https://device.deltafaucet.com/api/device/v2/UsageReport?macAddress=AABBCCDDEEFF&interval=0",
            status=401,
        )
        async with aiohttp.ClientSession() as session:
            client = DeltaVoiceIQClient(session, access_token="tok")
            with pytest.raises(AuthExpired):
                await client.get_usage("AABBCCDDEEFF", 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api.py -v`
Expected: FAIL with `ImportError: cannot import name 'convert_to_ml'`

- [ ] **Step 3: Implement the remaining client methods and `convert_to_ml`**

Append to `custom_components/delta_voiceiq/api.py`:

```python
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
```

Add these methods to the `DeltaVoiceIQClient` class (after `get_user_info`):

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api.py -v`
Expected: PASS (19 passed)

- [ ] **Step 5: Commit**

```bash
git add custom_components/delta_voiceiq/api.py tests/test_api.py
git commit -m "feat: implement faucet control, dispense, hand-wash, usage, and unit conversion"
```

---

## Task 5: `coordinator.py` — `DeltaUsageCoordinator`

**Files:**
- Create: `custom_components/delta_voiceiq/coordinator.py`
- Test: `tests/test_coordinator.py`

**Interfaces:**
- Consumes: `DeltaVoiceIQClient.get_usage`, `AuthExpired`, `CannotConnect` from Task 4; `USAGE_INTERVALS`, `SCAN_INTERVALS` from Task 1.
- Produces: `DeltaUsageCoordinator(hass, client: DeltaVoiceIQClient, mac_address: str, interval_name: str)` subclassing `homeassistant.helpers.update_coordinator.DataUpdateCoordinator[float]`. `interval_name` must be a key of `USAGE_INTERVALS`/`SCAN_INTERVALS` (`"today"|"week"|"month"|"year"`). Exposes the usual coordinator surface (`.data`, `async_config_entry_first_refresh()`, etc.) consumed by Task 9's sensors.

- [ ] **Step 1: Write failing tests**

```python
"""Tests for DeltaUsageCoordinator."""
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.delta_voiceiq.api import AuthExpired, CannotConnect
from custom_components.delta_voiceiq.coordinator import DeltaUsageCoordinator


@pytest.mark.asyncio
async def test_coordinator_fetches_usage_for_its_interval(hass):
    client = AsyncMock()
    client.get_usage.return_value = 12.5
    coordinator = DeltaUsageCoordinator(hass, client, "AABBCCDDEEFF", "week")

    data = await coordinator._async_update_data()

    assert data == 12.5
    client.get_usage.assert_awaited_once_with("AABBCCDDEEFF", 1)  # 1 == USAGE_INTERVALS["week"]


@pytest.mark.asyncio
async def test_coordinator_raises_config_entry_auth_failed_on_401(hass):
    client = AsyncMock()
    client.get_usage.side_effect = AuthExpired("nope")
    coordinator = DeltaUsageCoordinator(hass, client, "AABBCCDDEEFF", "today")

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_coordinator_raises_update_failed_on_other_errors(hass):
    client = AsyncMock()
    client.get_usage.side_effect = CannotConnect("network down")
    coordinator = DeltaUsageCoordinator(hass, client, "AABBCCDDEEFF", "month")

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_coordinator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.delta_voiceiq.coordinator'`

- [ ] **Step 3: Implement `coordinator.py`**

```python
"""DataUpdateCoordinator for Delta VoiceIQ usage polling."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntryAuthFailed
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AuthExpired, CannotConnect, DeltaVoiceIQClient
from .const import DOMAIN, SCAN_INTERVALS, USAGE_INTERVALS

_LOGGER = logging.getLogger(__name__)


class DeltaUsageCoordinator(DataUpdateCoordinator[float]):
    """Polls UsageReport for a single interval (today/week/month/year)."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: DeltaVoiceIQClient,
        mac_address: str,
        interval_name: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{mac_address}_{interval_name}",
            update_interval=SCAN_INTERVALS[interval_name],
        )
        self._client = client
        self._mac_address = mac_address
        self._interval_value = USAGE_INTERVALS[interval_name]

    async def _async_update_data(self) -> float:
        try:
            return await self._client.get_usage(self._mac_address, self._interval_value)
        except AuthExpired as err:
            raise ConfigEntryAuthFailed("Delta VoiceIQ token rejected") from err
        except CannotConnect as err:
            raise UpdateFailed(str(err)) from err
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_coordinator.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add custom_components/delta_voiceiq/coordinator.py tests/test_coordinator.py
git commit -m "feat: add DeltaUsageCoordinator with auth-failure/update-failure mapping"
```

---

## Task 6: `config_flow.py` — setup, device picker, reauth

**Files:**
- Create: `custom_components/delta_voiceiq/config_flow.py`
- Test: `tests/test_config_flow.py`

**Interfaces:**
- Consumes: `build_login_url`, `extract_code`, `DeltaVoiceIQClient`, `InvalidCode`, `CannotConnect`, `NoDevicesFound`, `AuthExpired`, `ExchangeResult`, `DeltaDevice` from Tasks 2-4; `DOMAIN`, `LOGIN_PROVIDERS`, `CONF_ACCESS_TOKEN`, `CONF_MAC_ADDRESS`, `CONF_USER_ID`, `CONF_EXP_TIMESTAMP`, `CONF_DEVICE_NAME` from Task 1.
- Produces: `DeltaVoiceIQConfigFlow` registered for `domain=DOMAIN`, steps `user` (provider picker), `code` (instructions + paste field), `device` (multi-device picker), `reauth` (HA's entry point). Config entry `data` dict keys: `access_token`, `mac_address`, `user_id`, `exp_timestamp`, `device_name`. Unique ID = the device's `mac_address`.

- [ ] **Step 1: Write failing tests**

```python
"""Tests for the Delta VoiceIQ config flow."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.delta_voiceiq.api import (
    CannotConnect,
    DeltaDevice,
    ExchangeResult,
    InvalidCode,
)
from custom_components.delta_voiceiq.const import (
    CONF_ACCESS_TOKEN,
    CONF_MAC_ADDRESS,
    DOMAIN,
)

ONE_DEVICE = ExchangeResult(
    access_token="tok123",
    user_id="u1",
    exp_timestamp=9999999999,
    devices=[DeltaDevice(mac_address="AABBCCDDEEFF", name="Kitchen Faucet")],
)

TWO_DEVICES = ExchangeResult(
    access_token="tok123",
    user_id="u1",
    exp_timestamp=9999999999,
    devices=[
        DeltaDevice(mac_address="AABBCCDDEEFF", name="Kitchen Faucet"),
        DeltaDevice(mac_address="112233445566", name="Bathroom Faucet"),
    ],
)


@pytest.mark.asyncio
async def test_happy_path_single_device(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"provider": "apple"}
    )
    assert result["step_id"] == "code"

    with patch(
        "custom_components.delta_voiceiq.config_flow.DeltaVoiceIQClient"
    ) as mock_client_cls:
        mock_client_cls.return_value.exchange_code = AsyncMock(return_value=ONE_DEVICE)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"code": "delta.code.ABC123"}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_MAC_ADDRESS] == "AABBCCDDEEFF"
    assert result["data"][CONF_ACCESS_TOKEN] == "tok123"


@pytest.mark.asyncio
async def test_multi_device_shows_picker_then_creates_chosen_entry(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"provider": "apple"}
    )

    with patch(
        "custom_components.delta_voiceiq.config_flow.DeltaVoiceIQClient"
    ) as mock_client_cls:
        mock_client_cls.return_value.exchange_code = AsyncMock(return_value=TWO_DEVICES)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"code": "delta.code.ABC123"}
        )

    assert result["step_id"] == "device"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"mac_address": "112233445566"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_MAC_ADDRESS] == "112233445566"


@pytest.mark.asyncio
async def test_invalid_code_shows_error_and_keeps_user_on_code_step(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"provider": "apple"}
    )

    with patch(
        "custom_components.delta_voiceiq.config_flow.DeltaVoiceIQClient"
    ) as mock_client_cls:
        mock_client_cls.return_value.exchange_code = AsyncMock(side_effect=InvalidCode("bad"))
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"code": "garbage"}
        )

    assert result["step_id"] == "code"
    assert result["errors"] == {"base": "invalid_code"}


@pytest.mark.asyncio
async def test_cannot_connect_shows_error(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"provider": "apple"}
    )

    with patch(
        "custom_components.delta_voiceiq.config_flow.DeltaVoiceIQClient"
    ) as mock_client_cls:
        mock_client_cls.return_value.exchange_code = AsyncMock(side_effect=CannotConnect("down"))
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"code": "delta.code.ABC123"}
        )

    assert result["step_id"] == "code"
    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.asyncio
async def test_reauth_flow_updates_existing_entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="AABBCCDDEEFF",
        data={
            CONF_ACCESS_TOKEN: "old-token",
            CONF_MAC_ADDRESS: "AABBCCDDEEFF",
            "user_id": "u1",
            "exp_timestamp": 1,
            "device_name": "Kitchen Faucet",
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "unique_id": entry.unique_id,
        },
        data=entry.data,
    )
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"provider": "apple"}
    )
    assert result["step_id"] == "code"

    with patch(
        "custom_components.delta_voiceiq.config_flow.DeltaVoiceIQClient"
    ) as mock_client_cls:
        mock_client_cls.return_value.exchange_code = AsyncMock(return_value=ONE_DEVICE)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"code": "delta.code.NEW"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_ACCESS_TOKEN] == "tok123"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config_flow.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.delta_voiceiq.config_flow'`

- [ ] **Step 3: Implement `config_flow.py`**

```python
"""Config flow for Delta VoiceIQ."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    AuthExpired,
    CannotConnect,
    DeltaDevice,
    DeltaVoiceIQClient,
    ExchangeResult,
    InvalidCode,
    NoDevicesFound,
    build_login_url,
    extract_code,
)
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_DEVICE_NAME,
    CONF_EXP_TIMESTAMP,
    CONF_MAC_ADDRESS,
    CONF_USER_ID,
    DOMAIN,
    LOGIN_PROVIDERS,
)

_LOGGER = logging.getLogger(__name__)


class DeltaVoiceIQConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle setup and reauth for Delta VoiceIQ."""

    VERSION = 1

    def __init__(self) -> None:
        self._provider: str | None = None
        self._exchange_result: ExchangeResult | None = None
        self._reauth_entry: config_entries.ConfigEntry | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            self._provider = user_input["provider"]
            return await self.async_step_code()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required("provider"): vol.In(LOGIN_PROVIDERS)}),
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        return await self.async_step_user()

    async def async_step_code(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                code = extract_code(user_input["code"])
                session = async_get_clientsession(self.hass)
                client = DeltaVoiceIQClient(session)
                result = await client.exchange_code(code)
            except InvalidCode:
                errors["base"] = "invalid_code"
            except NoDevicesFound:
                return self.async_abort(reason="no_devices_found")
            except (CannotConnect, AuthExpired):
                errors["base"] = "cannot_connect"
            else:
                self._exchange_result = result
                if self.source == config_entries.SOURCE_REAUTH:
                    return await self._async_finish_reauth()
                if len(result.devices) == 1:
                    return await self._async_finish_setup(result.devices[0])
                return await self.async_step_device()

        login_url = build_login_url(self._provider)
        return self.async_show_form(
            step_id="code",
            data_schema=vol.Schema({vol.Required("code"): str}),
            description_placeholders={"login_url": login_url},
            errors=errors,
        )

    async def async_step_device(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        assert self._exchange_result is not None
        if user_input is not None:
            chosen_mac = user_input["mac_address"]
            device = next(
                d for d in self._exchange_result.devices if d.mac_address == chosen_mac
            )
            return await self._async_finish_setup(device)

        options = {d.mac_address: d.name for d in self._exchange_result.devices}
        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema({vol.Required("mac_address"): vol.In(options)}),
        )

    async def _async_finish_setup(self, device: DeltaDevice) -> FlowResult:
        assert self._exchange_result is not None
        await self.async_set_unique_id(device.mac_address)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=device.name,
            data={
                CONF_ACCESS_TOKEN: self._exchange_result.access_token,
                CONF_MAC_ADDRESS: device.mac_address,
                CONF_USER_ID: self._exchange_result.user_id,
                CONF_EXP_TIMESTAMP: self._exchange_result.exp_timestamp,
                CONF_DEVICE_NAME: device.name,
            },
        )

    async def _async_finish_reauth(self) -> FlowResult:
        assert self._exchange_result is not None
        assert self._reauth_entry is not None
        new_data = {
            **self._reauth_entry.data,
            CONF_ACCESS_TOKEN: self._exchange_result.access_token,
            CONF_EXP_TIMESTAMP: self._exchange_result.exp_timestamp,
        }
        return self.async_update_reload_and_abort(
            self._reauth_entry, data=new_data, reason="reauth_successful"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config_flow.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add custom_components/delta_voiceiq/config_flow.py tests/test_config_flow.py
git commit -m "feat: implement config flow with device auto-discovery and reauth"
```

---

## Task 7: `__init__.py` — entry setup/unload and runtime data (no platforms yet)

**Files:**
- Modify: `custom_components/delta_voiceiq/__init__.py` (replace the Task 1 placeholder)
- Create: `tests/test_init.py`

**Interfaces:**
- Consumes: `DeltaVoiceIQClient` (Tasks 2-4), `DeltaUsageCoordinator` (Task 5), `CONF_ACCESS_TOKEN`/`CONF_MAC_ADDRESS`/`USAGE_INTERVALS`/`DOMAIN` (Task 1).
- Produces: `DeltaVoiceIQRuntimeData(client: DeltaVoiceIQClient, coordinators: dict[str, DeltaUsageCoordinator])` dataclass; `async_setup_entry(hass, entry) -> bool` sets `entry.runtime_data` to an instance of it (keys `"today"`/`"week"`/`"month"`/`"year"`); `async_unload_entry(hass, entry) -> bool`. `PLATFORMS: list[Platform]` starts empty here — Tasks 8 and 9 each append their platform and add the corresponding `async_forward_entry_setups`/`async_unload_platforms` call.

- [ ] **Step 1: Write failing test**

```python
"""Tests for delta_voiceiq/__init__.py entry setup."""
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.delta_voiceiq.api import DeltaVoiceIQClient
from custom_components.delta_voiceiq.const import (
    CONF_ACCESS_TOKEN,
    CONF_EXP_TIMESTAMP,
    CONF_MAC_ADDRESS,
    CONF_USER_ID,
    DOMAIN,
)


@pytest.mark.asyncio
async def test_setup_entry_creates_client_and_four_coordinators(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="AABBCCDDEEFF",
        data={
            CONF_ACCESS_TOKEN: "tok123",
            CONF_MAC_ADDRESS: "AABBCCDDEEFF",
            CONF_USER_ID: "u1",
            CONF_EXP_TIMESTAMP: 9999999999,
            "device_name": "Kitchen Faucet",
        },
    )
    entry.add_to_hass(hass)

    with patch.object(DeltaVoiceIQClient, "get_usage", AsyncMock(return_value=1.0)):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    runtime_data = entry.runtime_data
    assert runtime_data.client.access_token == "tok123"
    assert set(runtime_data.coordinators.keys()) == {"today", "week", "month", "year"}
    for coordinator in runtime_data.coordinators.values():
        assert coordinator.data == 1.0


@pytest.mark.asyncio
async def test_unload_entry_succeeds(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="AABBCCDDEEFF",
        data={
            CONF_ACCESS_TOKEN: "tok123",
            CONF_MAC_ADDRESS: "AABBCCDDEEFF",
            CONF_USER_ID: "u1",
            CONF_EXP_TIMESTAMP: 9999999999,
            "device_name": "Kitchen Faucet",
        },
    )
    entry.add_to_hass(hass)

    with patch.object(DeltaVoiceIQClient, "get_usage", AsyncMock(return_value=1.0)):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_init.py -v`
Expected: FAIL — `async_setup_entry` doesn't exist yet (the Task 1 placeholder file has no setup function), so HA logs a setup error and `hass.config_entries.async_setup(entry.entry_id)` returns `False`/raises.

- [ ] **Step 3: Implement `__init__.py`**

```python
"""The Delta VoiceIQ integration."""
from __future__ import annotations

from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import DeltaVoiceIQClient
from .const import CONF_ACCESS_TOKEN, CONF_MAC_ADDRESS, USAGE_INTERVALS
from .coordinator import DeltaUsageCoordinator

PLATFORMS: list[Platform] = []


@dataclass
class DeltaVoiceIQRuntimeData:
    """Data owned by a single config entry for the lifetime of its setup."""

    client: DeltaVoiceIQClient
    coordinators: dict[str, DeltaUsageCoordinator] = field(default_factory=dict)


type DeltaVoiceIQConfigEntry = ConfigEntry[DeltaVoiceIQRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: DeltaVoiceIQConfigEntry) -> bool:
    """Set up Delta VoiceIQ from a config entry."""
    session = async_get_clientsession(hass)
    client = DeltaVoiceIQClient(session, access_token=entry.data[CONF_ACCESS_TOKEN])
    mac_address = entry.data[CONF_MAC_ADDRESS]

    coordinators: dict[str, DeltaUsageCoordinator] = {}
    for interval_name in USAGE_INTERVALS:
        coordinator = DeltaUsageCoordinator(hass, client, mac_address, interval_name)
        await coordinator.async_config_entry_first_refresh()
        coordinators[interval_name] = coordinator

    entry.runtime_data = DeltaVoiceIQRuntimeData(client=client, coordinators=coordinators)

    if PLATFORMS:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DeltaVoiceIQConfigEntry) -> bool:
    """Unload a Delta VoiceIQ config entry."""
    if not PLATFORMS:
        return True
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_init.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add custom_components/delta_voiceiq/__init__.py tests/test_init.py
git commit -m "feat: implement config entry setup/unload with per-interval coordinators"
```

---

## Task 8: `valve.py` — the faucet entity, wired into `__init__.py`

**Files:**
- Create: `custom_components/delta_voiceiq/valve.py`
- Modify: `custom_components/delta_voiceiq/__init__.py` (add `Platform.VALVE` to `PLATFORMS`)
- Test: `tests/test_valve.py`

**Interfaces:**
- Consumes: `DeltaVoiceIQRuntimeData`, `DeltaVoiceIQConfigEntry` (Task 7); `AuthExpired`, `CannotConnect` (Tasks 2-4); `CONF_MAC_ADDRESS`, `CONF_DEVICE_NAME`, `DOMAIN` (Task 1). Confirmed signature: `ConfigEntry.async_start_reauth(self, hass: HomeAssistant, context=None, data=None)` — verified against `home-assistant/core`'s `config_entries.py` (it takes `hass`, contrary to an earlier inaccurate doc-summary read during the design-review phase).
- Produces: `DeltaFaucetValve(entry: DeltaVoiceIQConfigEntry)` — a `ValveEntity` with `async_open_valve`/`async_close_valve`. `async_setup_entry(hass, entry, async_add_entities)` platform function.

- [ ] **Step 1: Write failing tests**

```python
"""Tests for the DeltaFaucetValve entity."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.delta_voiceiq.api import AuthExpired, CannotConnect
from custom_components.delta_voiceiq.const import CONF_DEVICE_NAME, CONF_MAC_ADDRESS
from custom_components.delta_voiceiq.valve import DeltaFaucetValve


def _make_entry(client):
    entry = MagicMock()
    entry.data = {CONF_MAC_ADDRESS: "AABBCCDDEEFF", CONF_DEVICE_NAME: "Kitchen Faucet"}
    entry.runtime_data.client = client
    entry.async_start_reauth = MagicMock()
    return entry


@pytest.mark.asyncio
async def test_open_valve_calls_toggle_water_and_updates_state():
    client = AsyncMock()
    entry = _make_entry(client)
    valve = DeltaFaucetValve(entry)
    valve.hass = MagicMock()
    valve.async_write_ha_state = MagicMock()

    await valve.async_open_valve()

    client.toggle_water.assert_awaited_once_with("AABBCCDDEEFF", on=True)
    assert valve.is_closed is False


@pytest.mark.asyncio
async def test_close_valve_calls_toggle_water_and_updates_state():
    client = AsyncMock()
    entry = _make_entry(client)
    valve = DeltaFaucetValve(entry)
    valve.hass = MagicMock()
    valve.async_write_ha_state = MagicMock()

    await valve.async_close_valve()

    client.toggle_water.assert_awaited_once_with("AABBCCDDEEFF", on=False)
    assert valve.is_closed is True


@pytest.mark.asyncio
async def test_auth_expired_starts_reauth_and_raises():
    client = AsyncMock()
    client.toggle_water.side_effect = AuthExpired("nope")
    entry = _make_entry(client)
    valve = DeltaFaucetValve(entry)
    valve.hass = MagicMock()

    with pytest.raises(HomeAssistantError):
        await valve.async_open_valve()

    entry.async_start_reauth.assert_called_once_with(valve.hass)


@pytest.mark.asyncio
async def test_cannot_connect_raises_home_assistant_error():
    client = AsyncMock()
    client.toggle_water.side_effect = CannotConnect("down")
    entry = _make_entry(client)
    valve = DeltaFaucetValve(entry)
    valve.hass = MagicMock()

    with pytest.raises(HomeAssistantError):
        await valve.async_close_valve()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_valve.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.delta_voiceiq.valve'`

- [ ] **Step 3: Implement `valve.py`**

```python
"""Valve entity for the Delta faucet."""
from __future__ import annotations

import logging

from homeassistant.components.valve import ValveDeviceClass, ValveEntity, ValveEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DeltaVoiceIQConfigEntry
from .api import AuthExpired, CannotConnect
from .const import CONF_DEVICE_NAME, CONF_MAC_ADDRESS, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeltaVoiceIQConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([DeltaFaucetValve(entry)])


class DeltaFaucetValve(ValveEntity):
    """Represents the faucet's water flow as an open/closed valve."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_device_class = ValveDeviceClass.WATER
    _attr_reports_position = False
    _attr_assumed_state = True
    _attr_supported_features = ValveEntityFeature.OPEN | ValveEntityFeature.CLOSE

    def __init__(self, entry: DeltaVoiceIQConfigEntry) -> None:
        self._entry = entry
        self._client = entry.runtime_data.client
        self._mac_address = entry.data[CONF_MAC_ADDRESS]
        self._attr_unique_id = f"{self._mac_address}_valve"
        self._attr_is_closed = True
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._mac_address)},
            name=entry.data[CONF_DEVICE_NAME],
            manufacturer="Delta",
            model="VoiceIQ Faucet",
        )

    async def async_open_valve(self) -> None:
        await self._set_state(open_=True)

    async def async_close_valve(self) -> None:
        await self._set_state(open_=False)

    async def _set_state(self, open_: bool) -> None:
        try:
            await self._client.toggle_water(self._mac_address, on=open_)
        except AuthExpired as err:
            self._entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                "Delta faucet authentication expired; reauthentication started"
            ) from err
        except CannotConnect as err:
            raise HomeAssistantError(str(err)) from err
        self._attr_is_closed = not open_
        self.async_write_ha_state()
```

Modify `custom_components/delta_voiceiq/__init__.py`: change `PLATFORMS: list[Platform] = []` to:

```python
PLATFORMS: list[Platform] = [Platform.VALVE]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_valve.py tests/test_init.py -v`
Expected: PASS (all green — `test_init.py`'s setup test now also forwards to the real `valve` platform and must still pass with a live valve entity created)

- [ ] **Step 5: Commit**

```bash
git add custom_components/delta_voiceiq/valve.py custom_components/delta_voiceiq/__init__.py tests/test_valve.py
git commit -m "feat: add faucet valve entity with reauth-on-401 handling"
```

---

## Task 9: `sensor.py` — usage sensors, Token Expiry, MAC/User-ID diagnostics

**Files:**
- Create: `custom_components/delta_voiceiq/sensor.py`
- Modify: `custom_components/delta_voiceiq/const.py` (rename the unused `GALLONS_PER_LITER` constant from Task 1 to a clearer, actually-used one)
- Modify: `custom_components/delta_voiceiq/__init__.py` (add `Platform.SENSOR` to `PLATFORMS`)
- Test: `tests/test_sensor.py`

**Interfaces:**
- Consumes: `DeltaUsageCoordinator` (Task 5), `DeltaVoiceIQConfigEntry`/`DeltaVoiceIQRuntimeData` (Task 7), `CONF_MAC_ADDRESS`/`CONF_USER_ID`/`CONF_EXP_TIMESTAMP`/`USAGE_INTERVALS`/`DOMAIN` (Task 1).
- Produces: `UsageSensor(entry, coordinator: DeltaUsageCoordinator, interval_name: str)`, `TokenExpirySensor(entry)`, `StaticInfoSensor(entry, name: str, unique_suffix: str, value: str, *, diagnostic: bool = True)` — all `SensorEntity` subclasses. `async_setup_entry(hass, entry, async_add_entities)` platform function.

- [ ] **Step 1: Rename the unit-conversion constant in `const.py`**

In `custom_components/delta_voiceiq/const.py`, replace:

```python
GALLONS_PER_LITER = 0.264172
```

with:

```python
LITERS_PER_GALLON = 3.785411784
```

(The Task 1 constant was never consumed by anything yet, so this is a same-task rename, not a breaking change to existing code.)

- [ ] **Step 2: Write failing tests**

```python
"""Tests for Delta VoiceIQ sensors."""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from custom_components.delta_voiceiq.const import CONF_EXP_TIMESTAMP, CONF_MAC_ADDRESS, CONF_USER_ID
from custom_components.delta_voiceiq.sensor import StaticInfoSensor, TokenExpirySensor, UsageSensor


def _make_entry(exp_timestamp=None):
    entry = MagicMock()
    entry.data = {
        CONF_MAC_ADDRESS: "AABBCCDDEEFF",
        CONF_USER_ID: "u1",
        CONF_EXP_TIMESTAMP: exp_timestamp,
        "device_name": "Kitchen Faucet",
    }
    return entry


def test_usage_sensor_converts_gallons_to_liters():
    entry = _make_entry()
    coordinator = MagicMock()
    coordinator.data = 5.0  # gallons
    sensor = UsageSensor(entry, coordinator, "week")

    assert sensor.native_value == 18.93  # round(5.0 * 3.785411784, 2)
    assert sensor.unique_id == "AABBCCDDEEFF_usage_week"


def test_usage_sensor_returns_none_when_coordinator_has_no_data():
    entry = _make_entry()
    coordinator = MagicMock()
    coordinator.data = None
    sensor = UsageSensor(entry, coordinator, "today")

    assert sensor.native_value is None


def test_token_expiry_sensor_computes_days_remaining():
    now = datetime(2026, 6, 23, tzinfo=timezone.utc)
    exp = int(now.timestamp()) + 10 * 86400  # 10 days from "now"
    entry = _make_entry(exp_timestamp=exp)

    with patch("homeassistant.util.dt.utcnow", return_value=now):
        sensor = TokenExpirySensor(entry)

    assert sensor.native_value == 10


def test_token_expiry_sensor_unknown_when_exp_missing():
    entry = _make_entry(exp_timestamp=None)
    sensor = TokenExpirySensor(entry)

    assert sensor.native_value is None


def test_static_info_sensor_is_diagnostic_by_default():
    entry = _make_entry()
    sensor = StaticInfoSensor(entry, "MAC Address", "mac_address_info", "AABBCCDDEEFF")

    assert sensor.native_value == "AABBCCDDEEFF"
    assert sensor.entity_category == "diagnostic"
    assert sensor.unique_id == "AABBCCDDEEFF_mac_address_info"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_sensor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.delta_voiceiq.sensor'`

- [ ] **Step 4: Implement `sensor.py`**

```python
"""Sensor entities for Delta VoiceIQ."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfTime, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import CoordinatorEntity
import homeassistant.util.dt as dt_util

from . import DeltaVoiceIQConfigEntry
from .const import CONF_EXP_TIMESTAMP, CONF_MAC_ADDRESS, CONF_USER_ID, DOMAIN, LITERS_PER_GALLON, USAGE_INTERVALS
from .coordinator import DeltaUsageCoordinator

_LOGGER = logging.getLogger(__name__)

_INTERVAL_TITLES = {"today": "Usage Today", "week": "Usage Week", "month": "Usage Month", "year": "Usage Year"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeltaVoiceIQConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinators = entry.runtime_data.coordinators
    entities: list[SensorEntity] = [
        UsageSensor(entry, coordinators[name], name) for name in USAGE_INTERVALS
    ]
    entities.append(TokenExpirySensor(entry))
    entities.append(
        StaticInfoSensor(entry, "MAC Address", "mac_address_info", entry.data[CONF_MAC_ADDRESS])
    )
    entities.append(StaticInfoSensor(entry, "User ID", "user_id_info", entry.data[CONF_USER_ID]))
    async_add_entities(entities)


def _device_info(entry: DeltaVoiceIQConfigEntry) -> DeviceInfo:
    return DeviceInfo(identifiers={(DOMAIN, entry.data[CONF_MAC_ADDRESS])})


class UsageSensor(CoordinatorEntity[DeltaUsageCoordinator], SensorEntity):
    """Reports usage for one UsageReport interval, in liters."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.WATER
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfVolume.LITERS

    def __init__(self, entry: DeltaVoiceIQConfigEntry, coordinator: DeltaUsageCoordinator, interval_name: str) -> None:
        super().__init__(coordinator)
        mac_address = entry.data[CONF_MAC_ADDRESS]
        self._attr_name = _INTERVAL_TITLES[interval_name]
        self._attr_unique_id = f"{mac_address}_usage_{interval_name}"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> float | None:
        gallons = self.coordinator.data
        if gallons is None:
            return None
        return round(gallons * LITERS_PER_GALLON, 2)


class TokenExpirySensor(SensorEntity):
    """Reports days remaining until the stored access token expires."""

    _attr_has_entity_name = True
    _attr_name = "Token Expiry"
    _attr_native_unit_of_measurement = UnitOfTime.DAYS
    _attr_icon = "mdi:key-chain"
    _attr_should_poll = False

    def __init__(self, entry: DeltaVoiceIQConfigEntry) -> None:
        self._entry = entry
        mac_address = entry.data[CONF_MAC_ADDRESS]
        self._attr_unique_id = f"{mac_address}_token_expiry"
        self._attr_device_info = _device_info(entry)
        self._update_value()

    def _update_value(self) -> None:
        exp = self._entry.data.get(CONF_EXP_TIMESTAMP)
        if not exp:
            self._attr_native_value = None
            return
        days_left = (exp - dt_util.utcnow().timestamp()) / 86400
        self._attr_native_value = round(days_left)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_track_time_interval(self.hass, self._handle_update, timedelta(hours=1))
        )

    async def _handle_update(self, now) -> None:
        self._update_value()
        self.async_write_ha_state()


class StaticInfoSensor(SensorEntity):
    """A fixed, non-polling value read once from the config entry."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        entry: DeltaVoiceIQConfigEntry,
        name: str,
        unique_suffix: str,
        value: str,
        *,
        diagnostic: bool = True,
    ) -> None:
        mac_address = entry.data[CONF_MAC_ADDRESS]
        self._attr_name = name
        self._attr_unique_id = f"{mac_address}_{unique_suffix}"
        self._attr_native_value = value
        self._attr_device_info = _device_info(entry)
        if diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
```

Modify `custom_components/delta_voiceiq/__init__.py`: change

```python
PLATFORMS: list[Platform] = [Platform.VALVE]
```

to:

```python
PLATFORMS: list[Platform] = [Platform.VALVE, Platform.SENSOR]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_sensor.py tests/test_init.py -v`
Expected: PASS (all green)

- [ ] **Step 6: Commit**

```bash
git add custom_components/delta_voiceiq/sensor.py custom_components/delta_voiceiq/const.py custom_components/delta_voiceiq/__init__.py tests/test_sensor.py
git commit -m "feat: add usage, token expiry, and diagnostic sensors"
```

---

## Task 10: `services.yaml` and entity-targeted `dispense`/`hand_wash` services

**Files:**
- Modify: `custom_components/delta_voiceiq/valve.py` (add `async_dispense`/`async_hand_wash` methods and service registration)
- Create: `custom_components/delta_voiceiq/services.yaml`
- Modify: `tests/test_valve.py`

**Interfaces:**
- Consumes: `convert_to_ml` (Task 4); `AuthExpired`, `CannotConnect` (Tasks 2-4).
- Produces: `DeltaFaucetValve.async_dispense(self, amount: float, unit: str = "ml") -> None`, `DeltaFaucetValve.async_hand_wash(self) -> None`. Services `delta_voiceiq.dispense` and `delta_voiceiq.hand_wash`, both entity-targeted at the valve domain via `EntityPlatform.async_register_entity_service` (registered inside `valve.async_setup_entry`, so each config entry's platform setup wires the services exactly once per HA run — `async_register_entity_service` is idempotent across multiple entries).

- [ ] **Step 1: Write failing tests**

Append to `tests/test_valve.py`:

```python
@pytest.mark.asyncio
async def test_async_dispense_converts_unit_and_calls_dispense():
    client = AsyncMock()
    entry = _make_entry(client)
    valve = DeltaFaucetValve(entry)
    valve.hass = MagicMock()
    valve.async_write_ha_state = MagicMock()

    await valve.async_dispense(amount=1, unit="l")

    client.dispense.assert_awaited_once_with("AABBCCDDEEFF", 1000.0)


@pytest.mark.asyncio
async def test_async_dispense_defaults_to_ml():
    client = AsyncMock()
    entry = _make_entry(client)
    valve = DeltaFaucetValve(entry)
    valve.hass = MagicMock()

    await valve.async_dispense(amount=355)

    client.dispense.assert_awaited_once_with("AABBCCDDEEFF", 355.0)


@pytest.mark.asyncio
async def test_async_dispense_auth_expired_starts_reauth():
    client = AsyncMock()
    client.dispense.side_effect = AuthExpired("nope")
    entry = _make_entry(client)
    valve = DeltaFaucetValve(entry)
    valve.hass = MagicMock()

    with pytest.raises(HomeAssistantError):
        await valve.async_dispense(amount=355)

    entry.async_start_reauth.assert_called_once_with(valve.hass)


@pytest.mark.asyncio
async def test_async_hand_wash_calls_client():
    client = AsyncMock()
    entry = _make_entry(client)
    valve = DeltaFaucetValve(entry)
    valve.hass = MagicMock()

    await valve.async_hand_wash()

    client.hand_wash.assert_awaited_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_valve.py -v`
Expected: FAIL with `AttributeError: 'DeltaFaucetValve' object has no attribute 'async_dispense'`

- [ ] **Step 3: Implement the service methods and registration in `valve.py`**

Add `convert_to_ml` to the `.api` import line:

```python
from .api import AuthExpired, CannotConnect, convert_to_ml
```

Add these two new import lines (alongside valve.py's existing `from homeassistant.helpers.entity_platform import AddEntitiesCallback` from Task 8 — keep that one too, `entity_platform` the module and `AddEntitiesCallback` the class are both needed):

```python
import voluptuous as vol
from homeassistant.helpers import entity_platform
```

Replace `async_setup_entry` with:

```python
async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeltaVoiceIQConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([DeltaFaucetValve(entry)])

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        "dispense",
        {
            vol.Required("amount"): vol.Coerce(float),
            vol.Optional("unit", default="ml"): vol.In(["ml", "l", "gal", "fl_oz"]),
        },
        "async_dispense",
    )
    platform.async_register_entity_service("hand_wash", {}, "async_hand_wash")
```

Add these methods to `DeltaFaucetValve` (after `_set_state`):

```python
    async def async_dispense(self, amount: float, unit: str = "ml") -> None:
        milliliters = convert_to_ml(amount, unit)
        try:
            await self._client.dispense(self._mac_address, milliliters)
        except AuthExpired as err:
            self._entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                "Delta faucet authentication expired; reauthentication started"
            ) from err
        except CannotConnect as err:
            raise HomeAssistantError(str(err)) from err

    async def async_hand_wash(self) -> None:
        try:
            await self._client.hand_wash()
        except AuthExpired as err:
            self._entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                "Delta faucet authentication expired; reauthentication started"
            ) from err
        except CannotConnect as err:
            raise HomeAssistantError(str(err)) from err
```

- [ ] **Step 4: Create `services.yaml`**

```yaml
dispense:
  target:
    entity:
      domain: valve
  fields:
    amount:
      required: true
      example: 355
      selector:
        number:
          min: 0
          max: 15000
          step: 1
    unit:
      required: false
      default: ml
      selector:
        select:
          options:
            - ml
            - l
            - gal
            - fl_oz

hand_wash:
  target:
    entity:
      domain: valve
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_valve.py -v`
Expected: PASS (all green)

- [ ] **Step 6: Commit**

```bash
git add custom_components/delta_voiceiq/valve.py custom_components/delta_voiceiq/services.yaml tests/test_valve.py
git commit -m "feat: add entity-targeted dispense and hand_wash services"
```

---

## Task 11: Token-expiry and unparseable-`exp` Repair issues

**Files:**
- Modify: `custom_components/delta_voiceiq/__init__.py`
- Modify: `tests/test_init.py`

**Interfaces:**
- Consumes: `CONF_EXP_TIMESTAMP`, `TOKEN_EXPIRY_WARNING_DAYS`, `DOMAIN` (Task 1).
- Produces: `_async_check_token_expiry(hass: HomeAssistant, entry: DeltaVoiceIQConfigEntry) -> None`, called once at setup and every 24h thereafter. Creates/deletes two `issue_registry` issues per entry: `f"{entry.entry_id}_exp_unparseable"` (exp couldn't be decoded) and `f"{entry.entry_id}_expiring_soon"` (fewer than `TOKEN_EXPIRY_WARNING_DAYS` days remain) — both `IssueSeverity.WARNING`, both cleared automatically once the underlying condition resolves (e.g. after a successful reauth refreshes `exp_timestamp`).

- [ ] **Step 1: Write failing tests**

Append to `tests/test_init.py`:

```python
from datetime import datetime, timezone

from homeassistant.helpers import issue_registry as ir

from custom_components.delta_voiceiq import _async_check_token_expiry
from custom_components.delta_voiceiq.const import CONF_EXP_TIMESTAMP, DOMAIN


def _entry_with_exp(hass, exp_timestamp):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="AABBCCDDEEFF",
        data={
            CONF_ACCESS_TOKEN: "tok123",
            CONF_MAC_ADDRESS: "AABBCCDDEEFF",
            CONF_USER_ID: "u1",
            CONF_EXP_TIMESTAMP: exp_timestamp,
            "device_name": "Kitchen Faucet",
        },
    )
    entry.add_to_hass(hass)
    return entry


@pytest.mark.asyncio
async def test_check_token_expiry_creates_unparseable_issue_when_exp_is_none(hass):
    entry = _entry_with_exp(hass, None)

    _async_check_token_expiry(hass, entry)

    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"{entry.entry_id}_exp_unparseable")
    assert issue is not None


@pytest.mark.asyncio
async def test_check_token_expiry_no_issue_when_far_from_expiry(hass):
    now = datetime(2026, 6, 23, tzinfo=timezone.utc)
    exp = int(now.timestamp()) + 30 * 86400
    entry = _entry_with_exp(hass, exp)

    with patch("custom_components.delta_voiceiq.dt_util.utcnow", return_value=now):
        _async_check_token_expiry(hass, entry)

    assert ir.async_get(hass).async_get_issue(DOMAIN, f"{entry.entry_id}_expiring_soon") is None
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"{entry.entry_id}_exp_unparseable") is None


@pytest.mark.asyncio
async def test_check_token_expiry_creates_expiring_soon_issue_under_threshold(hass):
    now = datetime(2026, 6, 23, tzinfo=timezone.utc)
    exp = int(now.timestamp()) + 3 * 86400  # 3 days left, under the 7-day threshold
    entry = _entry_with_exp(hass, exp)

    with patch("custom_components.delta_voiceiq.dt_util.utcnow", return_value=now):
        _async_check_token_expiry(hass, entry)

    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"{entry.entry_id}_expiring_soon")
    assert issue is not None


@pytest.mark.asyncio
async def test_check_token_expiry_clears_issue_once_resolved(hass):
    now = datetime(2026, 6, 23, tzinfo=timezone.utc)
    soon = int(now.timestamp()) + 3 * 86400
    entry = _entry_with_exp(hass, soon)

    with patch("custom_components.delta_voiceiq.dt_util.utcnow", return_value=now):
        _async_check_token_expiry(hass, entry)
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"{entry.entry_id}_expiring_soon") is not None

    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_EXP_TIMESTAMP: int(now.timestamp()) + 30 * 86400}
    )
    with patch("custom_components.delta_voiceiq.dt_util.utcnow", return_value=now):
        _async_check_token_expiry(hass, entry)

    assert ir.async_get(hass).async_get_issue(DOMAIN, f"{entry.entry_id}_expiring_soon") is None
```

Add `from datetime import datetime, timezone` and `from homeassistant.helpers import issue_registry as ir` and `from custom_components.delta_voiceiq import _async_check_token_expiry` to the top of `tests/test_init.py` (alongside the existing imports from Task 7).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_init.py -v`
Expected: FAIL with `ImportError: cannot import name '_async_check_token_expiry'`

- [ ] **Step 3: Implement in `__init__.py`**

Add `from datetime import timedelta`, `from homeassistant.helpers import issue_registry as ir`, `from homeassistant.helpers.event import async_track_time_interval`, and `import homeassistant.util.dt as dt_util` as new import lines. Extend the existing `from .const import ...` line from Task 7 (do not add a second one) so it reads:

```python
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_EXP_TIMESTAMP,
    CONF_MAC_ADDRESS,
    DOMAIN,
    TOKEN_EXPIRY_WARNING_DAYS,
    USAGE_INTERVALS,
)
```

Add this function (module level, after the dataclass/type alias):

```python
def _async_check_token_expiry(hass: HomeAssistant, entry: DeltaVoiceIQConfigEntry) -> None:
    """Create/clear Repair issues for an unparseable exp claim or a soon-to-expire token."""
    unparseable_issue_id = f"{entry.entry_id}_exp_unparseable"
    expiring_issue_id = f"{entry.entry_id}_expiring_soon"
    exp = entry.data.get(CONF_EXP_TIMESTAMP)

    if exp is None:
        ir.async_create_issue(
            hass,
            DOMAIN,
            unparseable_issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="exp_unparseable",
        )
        ir.async_delete_issue(hass, DOMAIN, expiring_issue_id)
        return

    ir.async_delete_issue(hass, DOMAIN, unparseable_issue_id)
    days_left = (exp - dt_util.utcnow().timestamp()) / 86400
    if days_left < TOKEN_EXPIRY_WARNING_DAYS:
        ir.async_create_issue(
            hass,
            DOMAIN,
            expiring_issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="expiring_soon",
            translation_placeholders={"days": str(round(days_left))},
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, expiring_issue_id)
```

In `async_setup_entry`, after `entry.runtime_data = ...` and before the `PLATFORMS` forwarding block, add:

```python
    _async_check_token_expiry(hass, entry)
    entry.async_on_unload(
        async_track_time_interval(
            hass, lambda now: _async_check_token_expiry(hass, entry), timedelta(hours=24)
        )
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_init.py -v`
Expected: PASS (all green)

- [ ] **Step 5: Commit**

```bash
git add custom_components/delta_voiceiq/__init__.py tests/test_init.py
git commit -m "feat: add Repair issues for unparseable exp and soon-to-expire tokens"
```

---

## Task 12: `strings.json` / `translations/en.json`, and service descriptions

**Files:**
- Create: `custom_components/delta_voiceiq/strings.json`
- Create: `custom_components/delta_voiceiq/translations/en.json`
- Modify: `custom_components/delta_voiceiq/services.yaml` (add `name`/`description` fields)

**Interfaces:**
- Produces: UI copy for every config-flow step/error/abort and Repair issue defined in Tasks 6 and 11. No new Python interfaces — this task is config-flow-test-coverage-complete already (Task 6's tests don't depend on string content), but without this file the flow renders raw translation keys instead of text in the real HA UI.

- [ ] **Step 1: Create `strings.json`**

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Sign in to Delta",
        "description": "Pick the provider you use to sign in to the DFC@Home app.",
        "data": {
          "provider": "Sign-in provider"
        }
      },
      "code": {
        "title": "Paste your Delta sign-in code",
        "description": "1. Open this link and sign in: {login_url}\n2. **Before you sign in**, open DevTools (right-click → Inspect → Console tab) on the tab that opens — the redirect only shows up there.\n3. After signing in, find a line in the Console containing `justaddwater://?code=delta.code.XXXXX`. Copy that whole line, or just the `delta.code.XXXXX` part.\n4. Paste it below.",
        "data": {
          "code": "Delta sign-in code or full redirect URL"
        }
      },
      "device": {
        "title": "Select your faucet",
        "description": "Multiple VoiceIQ devices were found on this account. Pick the one to add.",
        "data": {
          "mac_address": "Faucet"
        }
      }
    },
    "error": {
      "invalid_code": "That code was rejected by Delta. It may be expired or already used — sign in again to get a fresh one.",
      "cannot_connect": "Could not complete sign-in with Delta. Check the Home Assistant logs for details and try again."
    },
    "abort": {
      "no_devices_found": "No VoiceIQ devices were found on this Delta account.",
      "already_configured": "This faucet is already configured.",
      "reauth_successful": "Re-authentication was successful."
    }
  },
  "issues": {
    "exp_unparseable": {
      "title": "Delta faucet token expiry could not be determined",
      "description": "Home Assistant could not read the expiration date from your Delta access token. Check the Home Assistant logs for details — this usually means Delta changed its token format."
    },
    "expiring_soon": {
      "title": "Delta faucet token expires soon",
      "description": "Your Delta faucet access token expires in {days} days. Go to Settings → Devices & Services and reauthenticate to refresh it."
    }
  }
}
```

- [ ] **Step 2: Copy it to `translations/en.json`**

```bash
cp custom_components/delta_voiceiq/strings.json custom_components/delta_voiceiq/translations/en.json
```

- [ ] **Step 3: Add `name`/`description` to `services.yaml`**

Replace the contents of `custom_components/delta_voiceiq/services.yaml` with:

```yaml
dispense:
  name: Dispense
  description: Dispense a specific amount of water from the faucet.
  target:
    entity:
      domain: valve
  fields:
    amount:
      name: Amount
      description: How much to dispense, in the chosen unit.
      required: true
      example: 355
      selector:
        number:
          min: 0
          max: 15000
          step: 1
    unit:
      name: Unit
      description: Unit for the amount field.
      required: false
      default: ml
      selector:
        select:
          options:
            - ml
            - l
            - gal
            - fl_oz

hand_wash:
  name: Hand wash mode
  description: Run the faucet's hand-wash cycle (5s rinse, 20s pause, 10s rinse at 95F).
  target:
    entity:
      domain: valve
```

- [ ] **Step 4: Run the full test suite to confirm nothing broke**

Run: `pytest tests/ -v`
Expected: PASS (every test from Tasks 2-11 still green — this task touches no `.py` files)

- [ ] **Step 5: Commit**

```bash
git add custom_components/delta_voiceiq/strings.json custom_components/delta_voiceiq/translations/en.json custom_components/delta_voiceiq/services.yaml
git commit -m "docs: add config flow / Repair issue translations and service descriptions"
```

---

## Task 13: Remove legacy files, update README and docs

**Files:**
- Delete: `packages/delta_voiceiq.yaml`, `www/delta-refresh.html`, `scripts/delta_token_exchange.sh`, `secrets.yaml.example`, `dashboard/card.yaml`
- Modify: `README.md`
- Modify: `docs/MITMPROXY.md`
- Modify: `.gitignore` (the `secrets.yaml` ignore rule is no longer needed — the integration never writes one)

**Interfaces:** None — this task has no code interfaces; it's a deliverable in its own right (the repo no longer contains the manual-setup artifacts the new integration replaces) and is independently verifiable (`git status`/`grep` checks below).

- [ ] **Step 1: Delete the legacy directories/files**

```bash
git rm -r packages/ www/ scripts/ dashboard/ secrets.yaml.example
```

- [ ] **Step 2: Remove the now-unused `secrets.yaml` ignore rule from `.gitignore`**

Remove these two lines from `.gitignore`:

```
# Secrets
secrets.yaml
```

(Leave the rest of `.gitignore` — macOS/Python/editor rules — untouched.)

- [ ] **Step 3: Replace the README's setup-instructions sections**

Replace the README's `## Quick Start` section through the end of `## Initial Token Capture` (i.e. everything from `## Quick Start` up to, but not including, `## Home Assistant Setup`) with:

```markdown
## Quick Start

1. Install [HACS](https://hacs.xyz) if you don't have it already.
2. In HACS, add this repository as a **custom repository**: `https://github.com/cdmicacc/delta-voiceiq-2.0-ha`.
3. Install **Delta VoiceIQ** from HACS, then restart Home Assistant.
4. Go to **Settings → Devices & Services → Add Integration**, search for **Delta VoiceIQ**, and follow the setup wizard.
5. During setup you'll pick a sign-in provider (Apple/Google/Amazon), sign in to Delta in a new browser tab, copy a one-time code out of that tab's DevTools console, and paste it back into the wizard. No mitmproxy, no `secrets.yaml`, no MAC address or user ID to look up by hand — the integration discovers your device automatically.

---
```

Replace `## Home Assistant Setup` through the end of `## Token Lifecycle: Expiry, Notification, and Refresh` with:

```markdown
## Refreshing Your Token

Delta's VoiceIQ token has no refresh token and lasts about 60 days, so refreshing is still a manual, occasional step — but it's now a guided flow inside Home Assistant instead of a separate web page and shell script.

- **Proactive warning:** once your token has fewer than 7 days left, a Repair issue appears in **Settings → Repairs** telling you to reauthenticate.
- **Reactive trigger:** if the token has already expired and an API call fails, Home Assistant automatically starts a reauthentication flow for the integration (look for a "Reauthenticate" prompt on the Delta VoiceIQ entry in **Settings → Devices & Services**, and/or an entry in **Settings → Repairs** — confirm which surface(s) you actually see and update this note accordingly once you've gone through it once).
- **To refresh:** follow the same sign-in-and-paste-a-code steps as initial setup (step 5 above) — the wizard reuses the exact same flow for both setup and reauthentication.

---
```

- [ ] **Step 4: Update the README's Repository Structure block**

Replace the fenced code block under `## Repository Structure` with:

```markdown
```
delta-voiceiq-2.0-ha/
├── README.md
├── LICENSE
├── hacs.json
├── docs/
│   ├── API.md                         # Full API reference
│   └── AUTH.md                        # Authentication deep dive
└── custom_components/
    └── delta_voiceiq/                  # The HACS integration
```
```

- [ ] **Step 5: Add a migration note for existing (pre-HACS) users**

Add this section right after `## Quick Start`:

```markdown
## Migrating From the Old Package-Based Setup

If you previously installed this via `packages/delta_voiceiq.yaml`:

1. Remove `packages/delta_voiceiq.yaml`, `www/delta-refresh.html`, and `scripts/delta_token_exchange.sh` from your `/config` directory, and delete the `delta_token`/`delta_mac_address`/`delta_user_id` entries from `secrets.yaml`.
2. Install the integration via HACS (Quick Start above) and run through setup once — same sign-in-and-paste-code motion you already know from the old refresh page, but you won't need to look up your MAC address or user ID this time.
3. Update any automations, scripts, or dashboards that reference the old entities (`input_boolean.delta_faucet_state`, `sensor.delta_faucet_usage_*`, `script.delta_faucet_*`) to the new ones (`valve.<device>_*`, `sensor.<device>_usage_*`, the `delta_voiceiq.dispense`/`delta_voiceiq.hand_wash` services). There is no automatic migration path — the old entities are unstructured helpers with no natural 1:1 mapping to the new device-scoped entities, so this is a one-time manual cleanup.

---
```

- [ ] **Step 6: Trim `docs/MITMPROXY.md` to a historical note**

Replace the entire contents of `docs/MITMPROXY.md` with:

```markdown
# mitmproxy (Historical / Debugging Only)

This integration's setup flow no longer requires mitmproxy — the config flow's sign-in-and-paste-code steps (see the README's Quick Start) work for both first-time setup and token refresh, using the same `Auth/Login` → `PostAuth` → `UserInfo` flow this project originally reverse-engineered using mitmproxy.

mitmproxy is still useful if you're debugging the Delta API itself (e.g. confirming a header or endpoint behaves as documented in [API.md](API.md)), but it is not part of normal setup or use.
```

- [ ] **Step 7: Verify no remaining references to deleted files**

Run: `grep -rn "secrets.yaml\|delta-refresh.html\|delta_token_exchange" README.md docs/API.md docs/AUTH.md docs/MITMPROXY.md`
Expected: no matches (or only matches inside the new "Migrating From the Old Package-Based Setup" section, which intentionally still names them as things to remove).

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "docs: remove legacy package/script/HTML setup, document HACS install and migration"
```

---

## Task 14: Manual smoke test against the real faucet

**Files:** None created/modified — this task is a verification checkpoint against your real Home Assistant instance and real Delta account, the same live system used to verify the design spec's claims earlier in this project.

**Interfaces:** None.

- [ ] **Step 1: Install the integration on your real HA instance**

Copy `custom_components/delta_voiceiq/` into your real `/config/custom_components/`. (If your dev environment and HA instance are the same machine, symlink instead of copy so future edits don't need re-syncing.) Restart Home Assistant.

- [ ] **Step 2: Run the config flow end-to-end**

Settings → Devices & Services → Add Integration → Delta VoiceIQ. Pick your sign-in provider, sign in, copy the `delta.code.*` value from the new tab's DevTools console, paste it into the wizard. Confirm:
- The flow completes and creates one device named after your real faucet (e.g. "Kitchen Faucet" per the earlier live `UserInfo` capture).
- `valve.<device>_faucet` (or however HA names it) appears, along with the four usage sensors, Token Expiry, MAC Address, and User ID sensors, all grouped under one device in Settings → Devices & Services.

- [ ] **Step 3: Exercise the valve**

Toggle the valve entity open, then closed, from the UI. Confirm the physical faucet responds (it should turn on/off, matching today's `input_boolean`-driven behavior) and the entity's state flips accordingly (it's `assumed_state`, so HA trusts the action succeeded rather than confirming from the device).

- [ ] **Step 4: Exercise the services**

Developer Tools → Actions → call `delta_voiceiq.dispense` targeting your faucet's valve entity with `amount: 100`, `unit: ml`. Confirm ~100ml dispenses. Call `delta_voiceiq.hand_wash` and confirm the hand-wash cycle runs.

- [ ] **Step 5: Confirm usage sensors populate**

Wait for (or force) a coordinator refresh and confirm `sensor.<device>_usage_today` shows a value in liters that's consistent with the `currentUsage` gallons figure from the earlier live `UserInfo` capture (21.40 gal ≈ 81.0 L) — it won't match exactly since usage continues accruing, but it should be in the right ballpark, not wildly off or stuck at zero.

- [ ] **Step 6: Confirm the Token Expiry sensor is sane**

`sensor.<device>_token_expiry` should show a number of days roughly matching ~60 days minus however long it's been since you last captured a token (don't expect an exact match — just confirm it's a plausible positive number, not `unknown` and not negative).

- [ ] **Step 7: Resolve the open reauth-UI-surface question from the design spec**

The spec flagged as unverified whether HA's reauthentication prompt appears as a "Reauthenticate" affordance on the integration card in Settings → Devices & Services, a Settings → Repairs issue, or both. You can't easily force a real 401 without waiting ~60 days, but you can simulate it: temporarily edit the config entry's stored `access_token` to a garbage value via Developer Tools → Template (`{{ states.valve }}` won't help directly — instead, briefly add a debug log line or use `hass.config_entries.async_update_entry` from a one-off Developer Tools → Services call against a test/dev HA instance, not your production faucet) and then trigger a coordinator refresh or a valve toggle. Observe where the reauth prompt actually shows up, and update the "Refreshing Your Token" README section from Task 13 to state the confirmed UI surface instead of "confirm which surface(s) you actually see."

- [ ] **Step 8: Update README and close out**

Edit the README's "Refreshing Your Token" section to replace the placeholder sentence from Task 13 step 3 with the confirmed behavior from Step 7 above. Commit.

```bash
git add README.md
git commit -m "docs: confirm reauthentication UI surface from live testing"
```
