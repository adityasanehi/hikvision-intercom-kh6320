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
- `0x1132` `COMM_UPLOAD_VIDEO_INTERCOM_EVENT` and `0x1133`
  `COMM_ALARM_VIDEO_INTERCOM` use different fixed structs. Their event type is
  not the first byte after `dwSize`; decode the documented layout.

`NET_DVR_ALARM_ISAPI_INFO` starts with `pAlarmData`, followed by
`dwAlarmDataLen`; it has no `dwSize` member. See the
[SDK structure definition](https://open.hikvision.com/hardware/structures/NET_DVR_ALARM_ISAPI_INFO.html).

### DS-KH6320-WTDE1 / V2.2.92 observation (2026-10-28)

- During a user-confirmed indoor-screen ring from the analog doorphone, the
  existing bridge alarm stream produced no callback. A separate SDK session
  polling `/ISAPI/VideoIntercom/callStatus?format=json` did not detect that first
  ring; its timing relative to the ring was not tightly controlled.
- A second ring was confirmed by two independent polling sessions at 16:30:48
  local time (`CallStatus.status = "ring"`). The SDK returned to `idle` at
  16:32:33. The user reports the indoor unit was answered/rejected and the door
  opened after 10-15 seconds: the SDK state therefore overstayed actual ringing
  by roughly 90 seconds. Do not treat that 105-second SDK interval as physical
  ring duration or proof of when the call ended.
- Native `NET_DVR_GetDeviceStatus` command 16034 returned error 23 (unsupported).
- `/ISAPI/AccessControl/AcsWorkStatus?format=json` returned network, SIP and SD
  card status, with no magnetic-contact or door-position fields. The tested
  `/ISAPI/VideoIntercom/doorStatus?format=json` and
  `/ISAPI/AccessControl/doorStatus?format=json` paths returned error 23.
- A fresh isolated login accepted callback registration and alarm arming but
  delivered no callbacks during the second ring or the reported door opening.
  A receive-only call-signalling subscription (command 16032) was also accepted
  and delivered no callbacks during that test.
- `/ISAPI/VideoIntercom/WorkStatus` is unsupported (23); the two-way audio
  channel status query returned invalid operation (29). `GET callSignal`
  returned method-not-allowed (23). Adding `channelNo=2` to `callStatus` was
  accepted while idle, but has not been tested during a ring.
- During a separate user-confirmed manual Talk session on the indoor screen,
  base and channel-2 `callStatus` remained `idle`; `callerInfo` stayed at error
  29. Fresh alarm subscriptions received no callbacks before, during or after
  that manual conversation (observed 16:42-16:44 local time). This is distinct
  from explicitly answering a ringing call, which still needs a controlled
  test with Answer held active before hanging up.
- Native `IP_VIEW_DEV_ABILITY` returned a `VideoCall` capability with
  Request/Cancel/Answer/Decline/Timeout/Bye/DeviceIsBusy/ClientIsBusy commands.
  This advertises control, not evidence of pickup notifications. Native
  `NET_DVR_GetDVRWorkState_V30` returned unsupported (23).
- Controlled incoming call: on 2026-10-28, base `callStatus` changed to `ring`
  at 17:20:16.963 and `idle` at 17:20:53.607 local time. The user reported
  answering on the indoor screen and later ending the call. During the answered
  interval the base and channel-2 statuses and `callerInfo.status` remained
  `ring`; no `onCall` or alarm callback was observed. `callerInfo` succeeded
  during the call and returned error 29 after the SDK returned to idle.

The ringing sensor follows the SDK call session through to `idle`, as requested
after the controlled test. It cannot distinguish ringing from a locally answered
call, and the SDK may continue reporting `ring` after the indoor screen stops.

Reference: [pergolafabio's polling implementation](https://github.com/pergolafabio/Hikvision-Addons/blob/main/hikvision-doorbell/src/mqtt.py)
uses `CallStatus.status` from `/ISAPI/VideoIntercom/callStatus?format=json`.
Polling detected the second analog ring here, but its reset did not track the
indoor unit. The `callSignal` endpoint is for control, not status.

Exact numeric types vary by firmware; the bridge logs raw callbacks at
`debug` so the map can be tightened per device.
