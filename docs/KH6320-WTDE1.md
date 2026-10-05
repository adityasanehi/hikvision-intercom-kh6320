# DS-KH6320-WTDE1 (4-wire hybrid indoor station) unlock

The base project targets **2-wire door stations** (DS-KIS/DS-KV kits) whose door
unlock is the generic ISAPI `RemoteControlDoor` body:

```
PUT /ISAPI/AccessControl/RemoteControl/door/1
<RemoteControlDoor><cmd>open</cmd></RemoteControlDoor>
```

That path **fails** on the **DS-KH6320-WTDE1** — a *4-wire hybrid* indoor station
that is wired directly to an **analog doorphone** (DS-KB2421T-IM) over a 4-wire
cable. On this device:

- The generic body returns SDK error **23 (`NET_DVR_NOSUPPORT`)**.
- The native `NET_DVR_CONTROL_GATEWAY_LOCK` command (**16009**) also returns
  **23 (not supported)** — the device exposes no `<ControlGateway>` capability.
- `PUT /ISAPI/AccessControl/RemoteControl/door/1` with a `channelNo`/`controlType`
  body returns **29 (`NET_DVR_DVROPRATEFAILED`)** unless the correct `channelNo`
  is supplied.

## Working command (verified live)

```
PUT /ISAPI/AccessControl/RemoteControl/door/1
<RemoteControlDoor xmlns="http://www.isapi.org/ver20/XMLSchema">
  <doorNo>1</doorNo>
  <cmd>open</cmd>
  <channelNo>2</channelNo>
  <controlType>monitor</controlType>
</RemoteControlDoor>
```

The decisive field is **`channelNo`** — the analog doorphone's lock relay sits on
channel **2** (channel 1 is unused on a single-doorphone install), and
`controlType` must be `monitor` (a `calling`-context unlock needs an active call).

Verification matrix on a real DS-KH6320-WTDE1 (firmware V2.2.92):

| `doorNo` | `channelNo` | `controlType` | result |
|---|---|---|---|
| 1 | 1 | monitor | ❌ err 29 |
| 1 | 2 | monitor | ✅ ok |
| 1 | 2 | calling | ❌ err 29 |
| 1 | 3 | monitor | ✅ ok |
| 2 | 2 | monitor | ✅ ok |
| 0 | 2 | monitor | ❌ err 29 |

## How the integration handles it

- On login the bridge reads `NET_DVR_DEVICEINFO_V30.wDevType`.
- `wDevType == 602` (indoor station) → the `kh6320_indoor` unlock strategy, which
  sends the body above with `channelNo` from the config option `door_channel`
  (default `2`).
- Any other device keeps the original generic ISAPI body.

`unlock_strategy` can be forced from the config flow:
`auto` (default) · `generic_isapi` · `kh6320_indoor`.
