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
