# Delta VoiceIQ API Reference

## ToggleWater (v3)

Turns the faucet on or off. Handle must be in the "on" position.

```
POST /api/device/v3/ToggleWater?macAddress=MAC&toggle=on|off
```

Response: `{"retCode": 0, "retMessage": "Success"}`

## Dispense (v2)

Dispenses specific amount in milliliters. Auto-shutoff at 4 minutes (~7.2 gal max). Accuracy drops below 118ml (4 oz).

```
POST /api/device/v2/Dispense?macAddress=MAC&milliliters=946
```

## UsageReport (v2)

Returns water usage data in gallons.

```
GET /api/device/v2/UsageReport?macAddress=MAC&interval=N
```

Intervals: 0=today (1 point), 1=week (7 points), 2=month (~30), 3=year (12)

```json
{
  "retObject": {
    "labels": ["Thu","Fri","Sat","Sun","Mon","Tue","Wed"],
    "datasets": [{"label": "Gallons Used", "data": [23.91, 17.97, 19.41, 24.12, 17.26, 17.71, 0.72]}]
  }
}
```

## HandWashMode (v4)

CDC hand wash cycle: 5s rinse, 20s pause, 10s rinse at 95F.

```
POST /api/voice/v4/handWashMode?macAddress=MAC
Content-Type: application/json

{}
```

Requires `Content-Type: application/json` (even with an empty body) — omitting it returns 415.

## UserInfo (v2)

Returns user profile, device list, MAC addresses, custom containers, and modes.

```
GET /api/user/v2/UserInfo
```
