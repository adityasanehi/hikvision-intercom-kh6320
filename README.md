# Hikvision Intercom for Home Assistant

[![Add to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?repository=adityasanehi%2Fhikvision-intercom-kh6320&category=integration)
[![Add add-on repository](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fadityasanehi%2Fhikvision-intercom-kh6320)

> **Attribution / base:** This project is **derived from
> [TimLuist1/hikvision-intercom](https://github.com/TimLuist1/hikvision-intercom)**
> (used as the base and upstream). This repo adds support for Hikvision
> **4-wire hybrid indoor stations** — specifically the **DS-KH6320-WTDE1** with an
> analog doorphone (DS-KB2421T-IM) — whose door unlock uses a different ISAPI body
> than the 2-wire door stations the base targets. See
> [docs/KH6320-WTDE1.md](docs/KH6320-WTDE1.md).

A native Home Assistant integration for **Hikvision video intercom / door
stations** (DS-KIS / DS-KV / DS-KH kits, including 2-wire door stations and
4-wire hybrid indoor stations) that expose **no HTTP/ISAPI web server** — where
control is only reachable through Hikvision's binary SDK on port `8000`.

It gives you, on a wall tablet or anywhere in HA:

- 📹 **Live video** of the door camera (RTSP, no SDK needed)
- 🔔 **Ring / call events** — trigger a full-screen popup, TTS, tablet wake-up…
- 🚪 **Door unlock** (one entity per relay)
- ☎️ **Answer / reject / hang up** the call
- 🎙️ **Two-way talk** *(in progress — see roadmap)*

## Why two parts?

The door station speaks a proprietary binary protocol on port `8000`
(`HCNetSDK`). That SDK is a **glibc** shared library and cannot run inside the
Alpine/musl Home Assistant Core container. So the project is split:

```
Home Assistant
├─ custom_component  hikvision_intercom   (HACS)   ── the entities & UI
│      camera · binary_sensor · lock · button · config_flow
│                         │  WebSocket / HTTP (local)
└─ add-on  Hikvision SDK Bridge  (glibc + HCNetSDK) ── the "motor"
       login · alarm/event stream · callSignal · door unlock · (voice)
                                 │  port 8000 (SDK) + 554 (RTSP)
                          ┌──────┴───────┐
                          │  Door station │  192.168.x.x
                          └───────────────┘
```

The integration talks to the bridge over a small **local WebSocket API** — no
cloud, no MQTT broker required.

## Install

### 1. The SDK Bridge add-on
1. Home Assistant → **Settings → Add-ons → Add-on Store → ⋮ → Repositories**
   and add `https://github.com/TimLuist1/hikvision-intercom`.
2. Provide the Hikvision **Device Network SDK (Linux)** libraries (they are not
   redistributable, so you fetch them once):
   ```bash
   cd hikvision_sdk_bridge
   ./get-sdk.sh ~/Downloads/CH-HCNetSDK*Linux64*.zip   # amd64 HA host
   ```
   Download the SDK from
   <https://www.hikvision.com/en/support/download/sdk/> → *Device Network SDK*.
3. Install & start the **Hikvision SDK Bridge** add-on. It listens on
   `:8199` on the HA host.

### 2. The integration (HACS)
1. HACS → **Custom repositories** → add the same URL, category *Integration*.
2. Install **Hikvision Intercom (2-Wire)**, restart HA.
3. **Settings → Devices → Add Integration → Hikvision Intercom** and enter:
   - Door station IP (e.g. `192.168.0.38`), username, password
   - SDK port `8000`, RTSP port `554`
   - Bridge URL (default `http://homeassistant.local:8199`)
   - Number of door relays

## Entities

| Entity | Type | Notes |
|---|---|---|
| `camera.*_live` | camera | RTSP main stream (1080p) |
| `camera.*_live_sd` | camera | RTSP sub stream (disabled by default) |
| `binary_sensor.*_ringing` | binary_sensor | on while the doorbell rings |
| `binary_sensor.*_motion` / `_tamper` / `_door` | binary_sensor | station events |
| `lock.*_door_1` | lock | door opener relay (momentary) |
| `button.*_answer` / `_reject` / `_hangup` | button | call control |
| `button.*_reboot` | button | reboot station (disabled by default) |

### Example: ring → wake the hallway tablet
```yaml
automation:
  - alias: Doorbell popup
    trigger:
      - trigger: state
        entity_id: binary_sensor.turklingel_ringing
        to: "on"
    action:
      - action: media_player.turn_on
        target: { entity_id: media_player.hallway_tablet }
      - action: notify.mobile_app
        data:
          message: "Es klingelt an der Tür"
          data: { channel: doorbell, priority: high }
```

## How it was built

Full port-scan + protocol reverse engineering of the device and the Hik-Connect
APK. Key findings that shaped the design:

- Open ports: `554` RTSP · `5060/udp` SIP(YATE) · `8000` SDK · `8102` · `8200/9010/9020` private · `6666`. **No HTTP/ISAPI (80/443 closed).**
- Video: RTSP `Streaming/Channels/101` = H.264 1080p + G.711µ.
- Unlock (2-wire door stations): `PUT /ISAPI/AccessControl/RemoteControl/door/<id>`
  with `<RemoteControlDoor><cmd>open</cmd></RemoteControlDoor>` — tunnelled via
  `NET_DVR_STDXMLConfig`.
- Unlock (4-wire hybrid indoor stations, e.g. DS-KH6320-WTDE1): the same endpoint
  but with `<RemoteControlDoor><doorNo>1</doorNo><cmd>open</cmd><channelNo>2</channelNo><controlType>monitor</controlType></RemoteControlDoor>`
  — the `channelNo` points at the analog doorphone's lock relay. The integration
  auto-detects the indoor station type (`wDevType = 602`) and picks this path.
- Call control: `/ISAPI/VideoIntercom/callSignal` + `callerInfo`.
- Ring/motion/door events: `NET_DVR_SetupAlarmChan` + message callback.
- The app uses `HCNetSDK` via JNA — confirming the SDK path.

See [`docs/PROTOCOL.md`](docs/PROTOCOL.md) for the detailed notes.

## Roadmap

- [ ] Two-way audio (SDK `NET_DVR_StartVoiceCom`) exposed via WebRTC/go2rtc
- [ ] `callerInfo` → who is calling (which door/unit)
- [ ] Prebuilt add-on images (no local SDK download)
- [ ] Calibrated event-type map per firmware

## Disclaimer

For use with your own devices. The bundled Hikvision SDK is proprietary to
Hikvision. Not affiliated with Hikvision.
