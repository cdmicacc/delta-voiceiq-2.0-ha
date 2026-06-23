# Delta VoiceIQ: Convert to a Native HACS Integration

## Problem

The current implementation is an HA "package" (`packages/delta_voiceiq.yaml`) plus a standalone web page (`www/delta-refresh.html`) and a POSIX shell script (`scripts/delta_token_exchange.sh`) that mutates `secrets.yaml`/`automations.yaml`/`configuration.yaml` on disk. This requires manual file copying into `/config`, produces a pile of ungrouped helper entities (`input_boolean`, `input_text`, `input_number`) instead of a single device, can't be configured through the UI, and the token-refresh page is a separate flaky HTML tool. mitmproxy is required once for initial token capture.

## Goals

- Convert to a proper `custom_components/delta_voiceiq` integration, installable via HACS (custom repository).
- One HA **device** per faucet, with entities and services tied to it — no loose helpers.
- Fully UI-configurable: config flow for setup, native reauth flow for token refresh. No `secrets.yaml`, no shell scripts, no on-disk file mutation, no Long-Lived Access Token needed.
- Eliminate mitmproxy entirely, including for first-time setup, by reusing the already-documented `Auth/Login` → delta-code → `PostAuth` → `UserInfo` flow to auto-discover MAC address, user ID, and device name.
- Support multiple faucets (multiple config entries).
- Usage sensors default to metric (liters) but remain user-adjustable, via the standard per-entity unit override, to any unit HA's `water` sensor device class actually supports (gal, m³, ft³, CCF, MCF — no custom code for this). Milliliters are not an option here: HA's `water` device class does not support mL conversion.
- Refresh stays manual (Delta's API has no refresh token), but the manual step is now a guided in-UI HA flow instead of a separate web page + shell script + chmod + Supervisor token dance.

## Non-goals

- No automatic/headless token refresh (Delta's auth flow requires a human to sign in and copy a code out of DevTools console — this is unavoidable).
- No new dashboard card. HA's built-in `valve` domain ships standard Tile/entity cards and an auto-generated dashboard; custom dashboard styling (water-fill animation, etc.) is deferred to a separate future effort. `dashboard/card.yaml` is deleted.
- No submission to the default HACS store (custom repository only).

## Architecture

```
custom_components/delta_voiceiq/
├── __init__.py          # entry setup/unload, owns DeltaVoiceIQClient + coordinators
├── manifest.json
├── config_flow.py       # setup + reauth, sharing the sign-in steps
├── api.py               # DeltaVoiceIQClient: build login URL, exchange code, UserInfo,
│                         # ToggleWater, Dispense, UsageReport, handWashMode
├── coordinator.py        # one DataUpdateCoordinator per usage interval
├── valve.py               # faucet open/close entity
├── sensor.py              # usage sensors + token-expiry diagnostic sensor
├── services.yaml          # dispense / hand_wash service schemas
├── strings.json
└── translations/en.json
hacs.json                  # repo metadata for HACS custom-repository install
```

`manifest.json` required/expected fields: `domain: delta_voiceiq`, `name`, `config_flow: true` (the headline feature this whole redesign is built around — named explicitly here, not left implicit), `iot_class: cloud_polling` (the coordinators poll Delta's cloud API on a schedule), `integration_type: device`, plus the standard `codeowners`, `documentation`, `requirements` fields.

`strings.json`/`translations/en.json` must cover, under the `config` key's `step`/`error`/`abort` sections, every step and error/abort condition defined in this spec: the provider-picker, instructions, code-paste, and device-picker steps; the `invalid_code`/`cannot_connect` config-flow errors; the `no_devices_found` abort. This is a real scope item (the flow can't render without it), not a thin pass-through file — but the actual UI copy is implementation work, not a design decision, so it's deferred to that phase rather than drafted here.

`packages/`, `www/`, `scripts/`, `secrets.yaml.example`, and `dashboard/` are deleted once the integration covers their functionality. `docs/MITMPROXY.md` is removed (or reduced to a "how this was originally reverse-engineered" historical note, not a setup step); `docs/API.md` and `docs/AUTH.md` are kept and lightly updated to describe the new component instead of raw `secrets.yaml`/shell usage.

## Onboarding & reauth flow

Setup and reauth share the same steps (a `source == reauth` check skips the "select device" step on reauth):

1. **Pick sign-in provider** (Apple / Google / Amazon). The flow builds the documented `Auth/Login?provider=...&redirect_uri=justaddwater://...` URL and presents it as a link to open in the browser.
2. **Instructions step**: reminder to open DevTools → Console on the *new tab* that opens, before signing in, since the `justaddwater://` redirect only appears there.
3. **Paste delta code**: text field accepting either the bare `delta.code.XXXXX` or the full `justaddwater://...` redirect string; the flow extracts the code from either.
4. The integration calls `Auth/PostAuth` with the code (no prior token/MAC/user-ID needed — verified against the existing shell script, which sends no `Authorization` header to this call), decodes the double-encoded `accessToken` and JWT `exp` claim, then calls `UserInfo` with the new token. **Confirmed live** (2026-06-23, against a real account): `UserInfo` needs only `Authorization: Bearer <token>` + `dfc-source`/`User-Agent` — no MAC address or user ID in the request — and returns `devices: [{ id, name, macAddress, isDefault, productId, currentUsage, ... }]` plus `user.id`.
5. **Select device** (setup only): the flow first filters `UserInfo`'s `devices` array to entries that have both `macAddress` and `name` present, discarding any malformed entry rather than crashing the picker. If that leaves zero devices, abort the flow with `no_devices_found` ("No VoiceIQ devices found on this account."). If exactly one remains, skip straight through. If more than one, show a picker labeled by each device's `name` field (confirmed present in the live response, e.g. `"name": "Kitchen Faucet"`). Each chosen device becomes its own config entry, keyed by `macAddress` as the unique ID.
6. Token, MAC address, user ID, and expiry timestamp are stored in the config entry (`hass.config_entries`), never written to a file.

**Reauth trigger:** a 401 from `UsageReport` (coordinator-driven) raises `ConfigEntryAuthFailed` from inside the coordinator's update method — this is HA's documented automatic-reauth path. A 401 from `ToggleWater`/`Dispense` (valve open/close) or `handWashMode` (services) is not coordinator-driven, so those call sites instead catch the 401 and call `entry.async_start_reauth(hass)` directly — HA's documented escape hatch for triggering the same reauth flow from outside `async_setup_entry`/coordinator contexts. Both paths end with the user re-entering this same flow at step 1.

**Open question to verify during implementation:** HA's developer docs confirm the backend mechanics (a config flow starting at `async_step_reauth`) for both paths, but do not specify the exact frontend surface — whether the user is prompted via a "Reauthenticate" affordance directly on the integration's card in Settings → Devices & Services, a Settings → Repairs issue, or both. Confirm the actual UI presentation against a real HA instance (or more authoritative docs/source) before/during implementation; this does not change the backend design above, only what instructions to give the user in the README.

**Expiry warning:** the integration creates an HA **Repair issue** ("Delta Faucet token expires in N days") once fewer than 7 days remain, shown in Settings → Repairs. This replaces today's 9am automation + `persistent_notification`.

**Unparseable `exp` claim:** the original shell script treats this as a non-fatal, silent fallback (`EXP=0`/`DAYS_LEFT="unknown"`, exchange continues). This design treats it as a signal something is wrong instead — an unparseable `exp` on a token that otherwise decoded and authenticated successfully likely means Delta changed the token format, which the rest of this design's assumptions (decode logic, expiry tracking) depend on. On decode failure: log the failure (including enough of the raw decoded JWT payload to debug, at `WARNING` level) during the auth/reauth exchange; the Token Expiry sensor reports `unknown`; and the integration raises a *separate* Repair issue ("Delta Faucet token expiry could not be determined — check the Home Assistant logs"), distinct from the 7-day low-expiry Repair issue, so the condition isn't silently swallowed.

## Entities and services (per device/config entry)

| Item | Type | Notes |
|---|---|---|
| Faucet | `valve` | `device_class: water`, open = on, closed = off. No state feedback from Delta's API, so `assumed_state = True` (same limitation as today's `input_boolean`). |
| Usage Today | `sensor` | native unit liters (converted from the API's gallons), `device_class: water`, `state_class: total_increasing`. User can override the displayed unit per-entity via Settings → Entities, limited to what `SensorDeviceClass.WATER` actually supports for conversion: L, gal, m³, ft³, CCF, MCF — no mL, no fl_oz. Built into HA, no custom code. |
| Usage Week / Month / Year | `sensor` | same as above, one per `UsageReport` interval. |
| Token Expiry | `sensor` | days remaining. No `entity_category` — this is an actionable user-facing value (the user may want to chart it or build their own automation ahead of the 7-day Repair threshold below), not hardware/connection telemetry, so it doesn't fit HA's diagnostic-category examples (RSSI, MAC address, identify button). |
| MAC Address | `sensor` | `entity_category: diagnostic`. Matches HA's own canonical diagnostic example directly. |
| User ID | `sensor` | `entity_category: diagnostic`. |
| `delta_voiceiq.dispense` | service | `target: entity_id` on the valve entity (not the device) — the action conceptually acts on the faucet's water-flow capability, which is the valve entity itself; there's a 1:1 device→valve mapping anyway. data: `amount` (number), `unit` (`ml` default, also accepts `l`/`gal`/`fl_oz`). Unlike the sensors above, this unit list is not constrained by any HA device class — it's the integration's own conversion logic (custom code) feeding directly into the API's `milliliters` parameter, so mL/fl_oz are fine here. |
| `delta_voiceiq.hand_wash` | service | `target: entity_id` on the valve entity, same reasoning as above. No data params. Calls `handWashMode`. |

Container presets (Glass, Coffee Pot, Sink, etc.) are no longer integration code — users write their own HA scripts/scenes that call `delta_voiceiq.dispense` with whatever `amount`/`unit` they want, fully customizable without touching Python.

## Polling

One `DeltaVoiceIQClient` (single aiohttp session + token) is owned by the config entry's runtime data. Four `DataUpdateCoordinator` instances per entry, one per `UsageReport` interval, preserving today's cadence:

| Coordinator | Interval | Poll cadence |
|---|---|---|
| Today | 0 | 10 min |
| Week | 1 | 1 hour |
| Month | 2 | 5 hours |
| Year | 3 | 24 hours |

Any coordinator's refresh that hits a 401 raises `ConfigEntryAuthFailed` (via the shared client), triggering reauth as described above.

**Deliberate departure from HA's single-coordinator-per-source default:** HA's coordinator guidance generally frames one `DataUpdateCoordinator` around one logical data source, not one per derived cadence — and all four "sources" here are really the same `UsageReport` endpoint called with a different `interval` param. Four coordinators is a real choice, not the unremarkable default, made because the four intervals have independent legitimate cadences (10min/1hr/5hr/24hr) and independent failure/availability domains: if the year sensor's 24-hour poll fails, today's usage sensor shouldn't go `unavailable` along with it. A single coordinator juggling four internal timers would avoid the minor duplication of four coordinator objects but couples their failure states together, which is the wrong tradeoff here.

## Error handling

- 401 from `UsageReport` (coordinator) → `ConfigEntryAuthFailed` → native HA reauth flow. 401 from `ToggleWater`/`Dispense`/`handWashMode` (valve actions, services) → caught explicitly and resolved via `entry.async_start_reauth(hass)` (see Onboarding & reauth flow above; exact frontend presentation TBD/verify-during-implementation for both paths).
- Other HTTP errors / timeouts during a coordinator refresh → `UpdateFailed`, entity goes `unavailable` until the next successful poll (standard HA coordinator behavior).
- Service calls (`dispense`, `hand_wash`) that fail raise `HomeAssistantError` with the underlying reason, surfaced in the UI/automation trace.
- Config flow validates the pasted code (calls `PostAuth` synchronously) and shows one of two inline errors, mapped from the shell script's five distinct failure points:
  - `invalid_code` — `PostAuth` returns no redirect (the case Delta uses for a bad, expired, or already-consumed code).
  - `cannot_connect` — anything else: no base64 payload in the redirect, failed base64 decode, failed `accessToken` extraction, or an extracted token that's suspiciously short. These indicate Delta's response shape changed or something broke in transit/parsing, not a bad code, so they're bucketed separately from `invalid_code` even though both surface as `cannot_connect` to the user.
  - The specific underlying failure (which of the five cases) is logged at `WARNING` level either way, so it's debuggable without needing more user-facing error keys.

## Testing

- Unit tests for `api.py`: token/JWT decoding, double-base64 handling, code extraction from both bare-code and full-URL input, ml↔unit conversion in the dispense service.
- Config flow tests: happy path (single device), multi-device picker, invalid code, reauth path re-using a previous entry.
- Coordinator tests: 401 → `ConfigEntryAuthFailed`, other errors → `UpdateFailed`.
- These follow standard `pytest-homeassistant-custom-component` patterns for custom integrations.

## Migration notes (for README)

- Existing users: remove `packages/delta_voiceiq.yaml`, `www/delta-refresh.html`, `scripts/delta_token_exchange.sh`, and the `secrets.yaml` entries; install the integration via HACS custom repository; run the config flow once (same delta-code-paste motion they already know from today's refresh page, but now eliminates the MAC/user-ID copy step too).
- Any automations/scripts referencing the old `input_boolean.delta_faucet_state` / `sensor.delta_faucet_usage_*` / `script.delta_faucet_*` entities need updating to the new `valve.*` / `sensor.*` entity IDs and the new services.
