# Delta VoiceIQ 2.0 - Home Assistant Integration

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1+-blue?logo=home-assistant)](https://www.home-assistant.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![HACS](https://img.shields.io/badge/HACS-Required-orange)](https://hacs.xyz)
[![VoiceIQ](https://img.shields.io/badge/VoiceIQ-Gen%202-green)](https://www.deltafaucet.com/voiceiq)

> A complete reverse-engineered integration of **Delta VoiceIQ Version 2** smart faucets with Home Assistant. Control your faucet, dispense precise amounts, track water usage, and manage auth tokens -- all without the official app.

## What This Does

- **On/Off control** via dashboard card, automations, or voice assistants
- **Metered dispensing** with preset containers (Glass, Coffee Pot, Sink) or custom ml amounts
- **Water usage tracking** with daily, weekly, monthly, and yearly sensors
- **Animated dashboard card** with water-fill icon, flow animations, and usage badge
- **Rich popup** (browser_mod) with dispense buttons, usage stats, and history graph
- **Guided token refresh flow** integrated into Home Assistant, no mitmproxy required
- **Token expiry warnings** via persistent notifications

## Screenshots

| Dashboard Card | Long-Press Popup | Card Flowing |
|:-:|:-:|:-:|
| ![Card](docs/images/card-off.png) | ![Popup](docs/images/popup.png) | ![Flowing](docs/images/card-flowing.png) |
| Animated water-fill icon with usage badge | Dispense buttons, usage stats, history | Bubble animation when faucet is on |

## Compatibility

| Component | Tested Version |
|-----------|---------------|
| VoiceIQ Module | Gen 2 (product ID: `DELTA2-VOICE`) |
| Module Firmware | 2.0.2.0 |
| DFC@Home App | 2.6.0 (iOS) |
| VoiceIQ API | v2/v3 on `device.deltafaucet.com` |
| Home Assistant | 2024.1+ (tested through 2026.4) |

**Gen 1 vs Gen 2:** This integration targets the **Generation 2 VoiceIQ module** and its API. The DFC@Home app now supports both Gen 1 and Gen 2 modules. The API endpoints should be the same, but Gen 1 has not been tested with this integration. If you have a Gen 1 module and try this, please open an issue with your results.

---

## Quick Start

1. Install [HACS](https://hacs.xyz) if you don't have it already.
2. In HACS, add this repository as a **custom repository**: `https://github.com/cdmicacc/delta-voiceiq-2.0-ha`.
3. Install **Delta VoiceIQ** from HACS, then restart Home Assistant.
4. Go to **Settings → Devices & Services → Add Integration**, search for **Delta VoiceIQ**, and follow the setup wizard.
5. During setup you'll pick a sign-in provider (Apple/Google/Amazon), sign in to Delta in a new browser tab, and copy a one-time code from that tab's redirect response back into the wizard. No mitmproxy, no `secrets.yaml`, no MAC address or user ID to look up by hand — the integration discovers your device automatically.

---

## Migrating From the Old Package-Based Setup

If you previously installed this via `packages/delta_voiceiq.yaml`:

1. Remove `packages/delta_voiceiq.yaml`, `www/delta-refresh.html`, and `scripts/delta_token_exchange.sh` from your `/config` directory, and delete the `delta_token`/`delta_mac_address`/`delta_user_id` entries from `secrets.yaml`.
2. Install the integration via HACS (Quick Start above) and run through setup once — same sign-in-and-paste-code motion you already know from the old refresh page, but you won't need to look up your MAC address or user ID this time.
3. Update any automations, scripts, or dashboards that reference the old entities (`input_boolean.delta_faucet_state`, `sensor.delta_faucet_usage_*`, `script.delta_faucet_*`) to the new ones (`valve.<device>_*`, `sensor.<device>_usage_*`, the `delta_voiceiq.dispense`/`delta_voiceiq.hand_wash` services). There is no automatic migration path — the old entities are unstructured helpers with no natural 1:1 mapping to the new device-scoped entities, so this is a one-time manual cleanup.

---

## Repository Structure

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

---

## Prerequisites

**Hardware:**
- Delta VoiceIQ-enabled faucet (Touch2O manufactured after Jan 2018)
- VoiceIQ module connected to WiFi and registered at `device.deltafaucet.com`

**Home Assistant:**
- Home Assistant OS or Supervised (2024.1+)
- File Editor or Studio Code Server add-on

**Optional (for enhanced dashboard experience):**
- [Mushroom Cards](https://github.com/piitaya/lovelace-mushroom) — for animated water-fill effects
- [card-mod](https://github.com/thomasloven/lovelace-card-mod) — for dynamic styling and animations
- [browser_mod](https://github.com/thomasloven/hass-browser_mod) — for long-press popups with dispense buttons and usage stats

---

## API Reference

Base URL: `https://device.deltafaucet.com`

### Required Headers

```
Authorization: Bearer <VoiceIQ JWT>
dfc-source: mobile
User-Agent: DFCatHome/2.6.0 CFNetwork/3860.400.51 Darwin/25.3.0
```

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/device/v3/ToggleWater?macAddress=MAC&toggle=on\|off` | POST | Turn faucet on/off |
| `/api/device/v2/Dispense?macAddress=MAC&milliliters=N` | POST | Dispense specific amount (ml) |
| `/api/device/v2/UsageReport?macAddress=MAC&interval=N` | GET | Usage (0=today, 1=week, 2=month, 3=year) |
| `/api/voice/v4/handWashMode?macAddress=MAC` | POST | Hand wash mode (requires `Content-Type: application/json`) |
| `/api/user/v2/UserInfo` | GET | User info, devices, containers |

See [docs/API.md](docs/API.md) for full details.

---

## Authentication

Delta uses **two completely separate** auth systems. Only VoiceIQ is needed.

| Property | VoiceIQ (for faucet) | DFC@Home (NOT for faucet) |
|----------|---------------------|--------------------------|
| Server | `device.deltafaucet.com` | `api.deltafaucet-cw.com` |
| Token lifetime | ~60 days | 15 min (with refresh) |
| Refresh token | No | Yes |
| Login | Apple/Google/Amazon | Azure AD B2C |

The VoiceIQ system has no refresh token. You must re-authenticate every ~60 days. The in-HA reauthentication flow makes this straightforward.

See [docs/AUTH.md](docs/AUTH.md) for the full deep dive.

---

## Refreshing Your Token

Delta's VoiceIQ token has no refresh token and lasts about 60 days, so refreshing is still a manual, occasional step — but it's now a guided flow inside Home Assistant instead of a separate web page and shell script.

- **Proactive warning:** once your token has fewer than 7 days left, a Repair issue appears in **Settings → Repairs** telling you to reauthenticate.
- **Reactive trigger:** if the token has already expired and an API call fails, Home Assistant automatically starts a reauthentication flow for the integration (look for a "Reauthenticate" prompt on the Delta VoiceIQ entry in **Settings → Devices & Services**, and/or an entry in **Settings → Repairs** — confirm which surface(s) you actually see and update this note accordingly once you've gone through it once).
- **To refresh:** follow the same sign-in-and-paste-a-code steps as initial setup (step 5 above) — the wizard reuses the exact same flow for both setup and reauthentication.

---

## Dashboard

The integration provides device entities for your faucet that you can control and monitor via the default Entities card or any custom card.

For an enhanced experience with animated water-fill effects, Mushroom + card-mod can be used. The integration's device entities are compatible with any Lovelace card that can display valves, sensors, and services.

**Basic setup:**
1. Install [Mushroom Cards](https://github.com/piitaya/lovelace-mushroom) and [card-mod](https://github.com/thomasloven/lovelace-card-mod) via HACS (optional, for animated effects)
2. Add a card to your dashboard pointing to your Delta VoiceIQ device
3. Tap/click to toggle, long-press for more options (if using browser_mod)

**For a rich popup with dispense buttons and usage stats (optional):**
- Install [browser_mod](https://github.com/thomasloven/hass-browser_mod) via HACS AND add it as an integration (Settings > Devices & Services > Add Integration > Browser Mod)

### Usage Sensor Polling Schedule

The usage sensors automatically poll the Delta API on a regular schedule. No manual refresh needed.

| Sensor | Poll Interval |
|--------|--------------|
| Today's usage | Every 10 minutes |
| Weekly usage | Every 1 hour |
| Monthly usage | Every 5 hours |
| Yearly usage | Every 24 hours |

After an HA restart, sensors will show "unknown" briefly until their first poll cycle completes (up to 10 minutes for the daily sensor). This is normal and resolves automatically.

---

## Example Automations

### Morning Coffee Fill
```yaml
automation:
  - alias: "Morning Coffee"
    trigger:
      - platform: time
        at: "06:30:00"
    action:
      - service: delta_voiceiq.dispense
        target:
          entity_id: valve.kitchen_faucet   # replace with your device's valve entity ID
        data:
          amount: 946
          unit: ml
```

### Faucet Auto-Off Safety
```yaml
automation:
  - alias: "Faucet Auto-Off"
    trigger:
      - platform: state
        entity_id: valve.kitchen_faucet   # replace with your device's valve entity ID
        to: "open"
        for:
          minutes: 5
    action:
      - service: valve.close_valve
        target:
          entity_id: valve.kitchen_faucet   # replace with your device's valve entity ID
```

---

## FAQ and Troubleshooting

### General

**Q: 401 Unauthorized / authentication errors?**
Token expired. Go to **Settings → Devices & Services**, find the Delta VoiceIQ integration, and click the ⋮ menu to select "Reauthenticate".

**Q: Can I use the DFC@Home / Azure B2C token?**
No. Different systems, different tokens. Only VoiceIQ tokens work.

**Q: Gen 1 module?**
Untested but likely works. The API endpoints should be the same. Please open an issue with your results.

**Q: Dispense amount inaccurate?**
Accuracy drops below 4oz (118ml). The faucet also has a 4-minute auto-shutoff, capping max dispense at roughly 7.2 gallons.

**Q: Usage sensors show "unknown" after restart?**
Sensors need their first poll cycle after a restart. They will populate automatically within 10 minutes, or you can force refresh in Developer Tools > Services > `homeassistant.update_entity`.

### Dashboard

**Q: Popup not showing on long-press?**
browser_mod must be added as an **integration** in HA (Settings > Devices & Services > Add Integration > Browser Mod), not just installed via HACS. After adding, hard-refresh your browser.

**Q: Faucet icon not visible on the card?**
This can happen on Android tablets running Fully Kiosk Browser. Force-close the browser and reopen. If the issue persists, restart HA.

**Q: Card animations not updating when faucet state changes? (custom dashboards only)**
If you build a custom dashboard card using Mushroom + card-mod, add `entities` to your card_mod config to explicitly tell card-mod which entities to watch. Example:
```yaml
card_mod:
  entities:
    - valve.kitchen_faucet          # replace with your device's valve entity ID
    - sensor.kitchen_faucet_usage_today   # replace with your device's sensor entity ID
```
(This is not needed if using the default Entities card.)

### Token Refresh

**Q: How do I refresh my token?**
See the "Refreshing Your Token" section above. When your token nears expiry (< 7 days), a Repair issue will appear in **Settings → Repairs**. Follow the same sign-in-and-paste-code steps as initial setup.

**Q: Where do I find the delta code after signing in?**
After signing in, Delta redirects to a `justaddwater://` URL your browser can't open — the code is embedded in that URL. How to extract it depends on your browser:
- **Firefox:** Open the Network tab before clicking sign in. Find the failed redirect request and look at its `Location` response header.
- **Chrome:** Open DevTools Console (right-click > Inspect > Console) before signing in. After sign in, the `justaddwater://` line appears in the Console output.
- **Safari:** Not recommended — does not work reliably on Mac, iOS, or iPad.

**Q: Apple Sign-In shows "Your request could not be completed"?**
Apple rate-limits authentication attempts. Wait 10-15 minutes and try again.

**Q: I used "Hide My Email" with Apple and can't sign in on Chrome?**
In Chrome, when the Apple sign-in page loads, look for "Sign in with passkey from nearby device" or a passkey icon. This lets you authenticate via your iPhone's Face ID/Touch ID even though you're in Chrome.

---

## Disclaimer

Not affiliated with Delta Faucet or Masco Corporation. Use at your own risk. Automated water control could cause flooding if misused.

## Credits and Acknowledgments

**Dashboard Card Styling:**
- [@Anashost](https://github.com/Anashost) - Badge theme and water-fill animations inspired by [HA Animated Cards](https://github.com/Anashost/HA-Animated-cards/blob/main/appliances.md)

**Optional Custom Components (for enhanced dashboard experience):**
- [@piitaya](https://github.com/piitaya) - [Mushroom Cards](https://github.com/piitaya/lovelace-mushroom)
- [@thomasloven](https://github.com/thomasloven) - [card-mod](https://github.com/thomasloven/lovelace-card-mod) and [browser_mod](https://github.com/thomasloven/hass-browser_mod)
- [HACS](https://hacs.xyz) - Home Assistant Community Store

**Tools Used:**
- [mitmproxy](https://mitmproxy.org/) - API reverse-engineering and token capture
- [jwt.io](https://jwt.io) - JWT token inspection

**Prior Art:**
- [@evantobin](https://github.com/evantobin) - [homebridge-voiceiq](https://github.com/evantobin/homebridge-voiceiq) demonstrating VoiceIQ API control
- [@pvmac2194](https://gist.github.com/pvmac2194) - [Delta VoiceIQ API gist](https://gist.github.com/pvmac2194/d1f8d6fcdecd7cef2843ad7ce138f1ce)

**Built With:**
- [Home Assistant](https://www.home-assistant.io/)
- [Delta VoiceIQ](https://www.deltafaucet.com/voiceiq) by Delta Faucet Company

MIT License.
