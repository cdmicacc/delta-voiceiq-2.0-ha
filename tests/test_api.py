"""Tests for pure helpers in api.py."""
import base64
import json

import aiohttp
import pytest
from aioresponses import aioresponses

from custom_components.delta_voiceiq.api import (
    AuthExpired,
    CannotConnect,
    DeltaVoiceIQClient,
    InvalidCode,
    NoDevicesFound,
    build_login_url,
    convert_to_ml,
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


FAKE_USER_INFO_RESPONSE = {
    "user": {"id": "00000000000000000000000000000001"},
    "devices": [
        {
            "id": "00000000000000000000000000000002",
            "name": "Kitchen Faucet",
            "macAddress": "AABBCCDDEEFF",
            "isDefault": True,
            "productId": "DELTA2-VOICE",
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
            payload=FAKE_USER_INFO_RESPONSE,
        )
        async with aiohttp.ClientSession() as session:
            client = DeltaVoiceIQClient(session)
            result = await client.exchange_code("delta.code.ABC123")

    assert result.access_token == access_token
    assert result.user_id == "00000000000000000000000000000001"
    assert result.exp_timestamp == 9999999999
    assert len(result.devices) == 1
    assert result.devices[0].mac_address == "AABBCCDDEEFF"
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
async def test_hand_wash_sends_json_content_type():
    """hand_wash must send Content-Type: application/json or Delta returns 415."""
    with aioresponses() as mocked:
        mocked.post(
            "https://device.deltafaucet.com/api/voice/v4/handWashMode?macAddress=AABBCCDDEEFF",
            status=200,
        )
        async with aiohttp.ClientSession() as session:
            client = DeltaVoiceIQClient(session, access_token="tok")
            await client.hand_wash("AABBCCDDEEFF")


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


@pytest.mark.asyncio
async def test_get_usage_malformed_response_raises_cannot_connect():
    with aioresponses() as mocked:
        mocked.get(
            "https://device.deltafaucet.com/api/device/v2/UsageReport?macAddress=AABBCCDDEEFF&interval=1",
            payload={"unexpected": "shape"},
        )
        async with aiohttp.ClientSession() as session:
            client = DeltaVoiceIQClient(session, access_token="tok")
            with pytest.raises(CannotConnect):
                await client.get_usage("AABBCCDDEEFF", 1)
