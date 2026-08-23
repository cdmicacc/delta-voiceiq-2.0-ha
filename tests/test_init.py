"""Tests for delta_voiceiq/__init__.py entry setup."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from homeassistant.helpers import issue_registry as ir

from custom_components.delta_voiceiq import _async_check_token_expiry
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


@pytest.mark.asyncio
async def test_scheduled_recheck_creates_issue_as_token_ages(hass, freezer):
    """The 24h interval check must run on the event loop and create the Repair.

    Regression test: the interval callback used to be a plain lambda, which
    async_track_time_interval runs in an executor thread. Every scheduled run
    died with a thread-safety RuntimeError inside issue_registry, so the Repair
    was only ever evaluated at setup and never appeared as the token aged.
    """
    now = datetime(2026, 6, 23, tzinfo=timezone.utc)
    freezer.move_to(now)
    # 8.5 days out -> 8 whole days left, above the threshold, so setup is silent.
    exp = int(now.timestamp()) + int(8.5 * 86400)

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="AABBCCDDEEFF",
        data={
            CONF_ACCESS_TOKEN: "tok123",
            CONF_MAC_ADDRESS: "AABBCCDDEEFF",
            CONF_USER_ID: "u1",
            CONF_EXP_TIMESTAMP: exp,
            "device_name": "Kitchen Faucet",
        },
    )
    entry.add_to_hass(hass)

    with patch.object(DeltaVoiceIQClient, "get_usage", AsyncMock(return_value=1.0)):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        issue_id = f"{entry.entry_id}_expiring_soon"
        assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None

        # 25h later the token has ~7.46 days left -> 7 whole days, at threshold.
        freezer.move_to(now + timedelta(hours=25))
        async_fire_time_changed(hass, now + timedelta(hours=25))
        await hass.async_block_till_done()

    issue = ir.async_get(hass).async_get_issue(DOMAIN, issue_id)
    assert issue is not None, "scheduled re-check did not create the expiring_soon Repair"
    assert issue.translation_placeholders == {"days": "7"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("days_out", "expect_issue"),
    [
        (8.01, False),  # just over 8 days -> 8 whole days left, still quiet
        (7.99, True),   # under 8 days -> the 7th day before expiry, warn
        (7.01, True),   # still 7 whole days left
        (6.99, True),   # 6 whole days, well inside the window
    ],
)
async def test_expiring_soon_fires_on_the_seventh_day_before_expiry(
    hass, days_out, expect_issue
):
    """The warning must give a full 7 days' notice, not 6-and-change.

    Thresholding on `days_left < 7` fired only once fewer than 7 days remained.
    The boundary is `days_left < 8` -- i.e. 7 days plus some hours, the seventh
    day before expiry -- expressed as floor(days_left) <= 7.
    """
    now = datetime(2026, 6, 23, tzinfo=timezone.utc)
    entry = _entry_with_exp(hass, int(now.timestamp() + days_out * 86400))

    with patch("custom_components.delta_voiceiq.dt_util.utcnow", return_value=now):
        _async_check_token_expiry(hass, entry)

    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"{entry.entry_id}_expiring_soon")
    assert (issue is not None) is expect_issue
