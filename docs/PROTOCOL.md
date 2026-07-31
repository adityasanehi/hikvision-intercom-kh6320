# Protocol notes (reverse engineering)

Target: Hikvision 2-wire video intercom kit (DS-KIS701-class), tested against a
device at `192.168.0.38`.

## Port scan (from the LAN)

| Port | Proto | Service |
|---|---|---|
| 554 | TCP | RTSP (Digest auth; realm = device MAC) |
| 5060 | UDP | SIP — server banner `YATE/2.0.0` |
| 6666 | TCP | Hikvision private |
| 8000 | TCP | HCNetSDK (device network SDK) |
| 8102 | TCP | Hikvision private |
| 8200 / 9010 / 9020 | TCP | Private video-intercom protocol (XML frames, MD5-signed) |

**Ports 80 and 443 are closed** — there is no HTTP/ISAPI web server. Every
control path therefore has to go through the SDK on 8000.

## Video (works without the SDK)

```
rtsp://<user>:<pass>@<ip>:554/Streaming/Channels/101   # main, H.264 1080p@25 + G.711µ
rtsp://<user>:<pass>@<ip>:554/Streaming/Channels/102   # sub,  704x576
```

## SIP (YATE)

The device answers SIP `OPTIONS` and `INVITE` (100 Trying) but `REGISTER`
returns `501 Not Implemented` — it is not a registrar; calls are peer-to-peer by
IP. Blind INVITEs are terminated (`487`) because Hikvision expects a device
specific INVITE body. The official app does **not** use SIP; it uses the SDK.
SIP remains a possible future path but is not used by this integration.

## Private protocol (8200/9010/9020)

Frame = 32-byte header + XML body + 32-hex (MD5) trailer. Example unauthenticated
reply on 9020: `<Response><Result>129</Result></Response>` (129 = not
authorised). Not used — the SDK path is cleaner and fully featured.

## Hik-Connect APK findings

The app (`com.hikvision.hikconnect`, Hik-Connect 6.13.810) drives the device via
`HCNetSDK` through **JNA** (`HCNetSDKByJNA`). Relevant SDK calls:

- `NET_DVR_Login_V40` — login on 8000
- `NET_DVR_STDXMLConfig` — **ISAPI passthrough** over the SDK session
- `NET_DVR_SetupAlarmChan_V41` + `NET_DVR_SetDVRMessageCallBack_V50` — events
- `NET_DVR_StartVoiceCom` / `NET_DVR_VoiceComSendData` — two-way audio

ISAPI endpoints used by the app (tunnelled through STDXMLConfig):

| Purpose | Method + URL | Body |
|---|---|---|
| Unlock door | `PUT /ISAPI/AccessControl/RemoteControl/door/<id>` | `<RemoteControlDoor><cmd>open</cmd></RemoteControlDoor>` |
| Call control | `PUT /ISAPI/VideoIntercom/callSignal?format=json` | `{"CallSignal":{"cmdType":"answer\|reject\|hangUp"}}` |
| Caller info | `GET /ISAPI/VideoIntercom/callerInfo?format=json` | — |
| Device info | `GET /ISAPI/System/deviceInfo` | — |
| Reboot | `PUT /ISAPI/System/reboot` | — |

The door unlock body (`RemoteControlDoor` with `<cmd>open</cmd>`) was taken
verbatim from the app's React-Native bundle `biz.hcdoorguard.android.js`.

## Event mapping (to calibrate live)

Alarm callback commands seen / expected:

- `0x6009` `COMM_ISAPI_ALARM` → ISAPI XML/JSON with `<eventType>` (call, motion,
  unlock…). Preferred, human-readable.
- `0x1132` `COMM_ALARM_VIDEO_INTERCOM` / `0x1133` event → fixed structs; first
  byte after `dwSize` is the type.

Exact numeric types vary by firmware; the bridge logs raw callbacks at
`debug` so the map can be tightened per device.
