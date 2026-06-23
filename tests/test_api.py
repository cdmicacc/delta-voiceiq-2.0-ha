"""Tests for pure helpers in api.py."""
import base64
import json

import aiohttp
import pytest
from aioresponses import aioresponses

from custom_components.delta_voiceiq.api import (
    CannotConnect,
    DeltaVoiceIQClient,
    InvalidCode,
    NoDevicesFound,
    build_login_url,
    extract_code,
)


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


def _b64(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


def _fake_access_token(exp: int = 9999999999) -> str:
    """Build a fake 'access token' shaped like Delta's: base64(jwt-string)."""
    # Header with extra dummy fields to naturally exceed 100 chars after encoding
    header = _b64(json.dumps({"alg": "none", "dummy": "x" * 50}))
    payload = _b64(json.dumps({"exp": exp}))
    jwt = f"{header}.{payload}.sig"
    # Delta's accessToken field is itself base64-encoded JWT text.
    # The longer header above ensures the result is naturally >= 100 chars.
    return _b64(jwt)


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
