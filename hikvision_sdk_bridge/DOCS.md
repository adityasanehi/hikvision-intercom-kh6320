# Hikvision SDK Bridge

The "motor" for the **Hikvision Intercom (2-Wire)** integration. It runs the
Hikvision `HCNetSDK` (which needs glibc and therefore cannot live inside HA
Core) and exposes a tiny local WebSocket/HTTP API on port `8199`.

The HA integration connects to it, receives ring/motion/door events, and sends
unlock / answer / reject / hang-up commands.

## Before you start: provide the SDK libraries

The Hikvision Device Network SDK is **not redistributable**, so it is not
shipped in this repo. Fetch it once and lay it out into `hcnetsdk/`:

```bash
cd hikvision_sdk_bridge
./get-sdk.sh /path/to/CH-HCNetSDK_STD_V*_Linux64.zip
```

Download the SDK from
<https://www.hikvision.com/en/support/download/sdk/> → *Device Network SDK*.
Choose **Linux64** for a normal (amd64) Home Assistant host, or the **arm64**
build for a Raspberry Pi / aarch64 host.

The add-on will not build until `hcnetsdk/libhcnetsdk.so` is present.

## Options

| Option | Default | Description |
|---|---|---|
| `log_level` | `info` | `debug` prints raw alarm-callback data — useful for calibrating event types on your firmware. |

## How it works

- `host_network: true` so the bridge can reach the door station directly on
  port `8000` and be reachable by the integration.
- Device credentials are **not** stored in the add-on. The integration sends
  them over the WebSocket (`bind`) — one source of truth.
- On `bind` the bridge logs in (`NET_DVR_Login_V40`), arms the alarm channel
  (`NET_DVR_SetupAlarmChan_V41`) and reads `deviceInfo`.
- Events from the SDK callback are normalised to
  `ring / motion / tamper / door / unlock / call_status` and pushed to clients.

## Calibrating events

Different firmwares label intercom events differently. With `log_level: debug`,
ring your doorbell / unlock the door once and watch the add-on log. You'll see
lines like:

```
INFO bridge.intercom: ISAPI alarm (1): <EventNotificationAlert>...<eventType>...
INFO bridge.intercom: Video-intercom cmd 0x1132 type=5 raw=...
```

Open an issue with those lines and the exact mapping can be tightened.
