"""High-level intercom device: login, event stream, and control commands.

Events arrive on the HCNetSDK alarm channel in a native SDK thread; we normalise
and hand them to the asyncio side through a threadsafe queue. Commands go out as
ISAPI requests tunnelled through NET_DVR_STDXMLConfig (port 8000), since the
device exposes no HTTP/ISAPI server of its own.
"""

from __future__ import annotations

import asyncio
import ctypes
import json
import logging
import re
from ctypes import Structure, c_void_p
from typing import Any

from hcnetsdk import (
    BYTE,
    DWORD,
    MSG_CALLBACK,
    NET_DVR_ALARMER,
    HCNetSDK,
)

_LOGGER = logging.getLogger("bridge.intercom")

# HCNetSDK alarm command ids we care about
COMM_ALARM_V30 = 0x4000
COMM_ALARM_VIDEO_INTERCOM = 0x1132
COMM_UPLOAD_VIDEO_INTERCOM_EVENT = 0x1133
COMM_ISAPI_ALARM = 0x6009

# Device type codes (NET_DVR_DEVICEINFO_V30.wDevType)
DEV_TYPE_INDOOR = 602

# Unlock strategies
UNLOCK_STRATEGY_AUTO = "auto"
UNLOCK_STRATEGY_GENERIC_ISAPI = "generic_isapi"
UNLOCK_STRATEGY_KH6320_INDOOR = "kh6320_indoor"


class NET_DVR_ALARM_ISAPI_INFO(Structure):
    _fields_ = [
        ("dwSize", DWORD),
        ("dwAlarmDataLen", DWORD),
        ("pAlarmData", c_void_p),
        ("byDataType", BYTE),
        ("byPicturesNumber", BYTE),
        ("byRes", BYTE * 2),
        ("pPicPackData", c_void_p),
        ("byRes1", BYTE * 32),
    ]


class IntercomDevice:
    """One logged-in door station."""

    def __init__(
        self,
        sdk: HCNetSDK,
        loop: asyncio.AbstractEventLoop,
        event_queue: asyncio.Queue,
    ) -> None:
        self._sdk = sdk
        self._loop = loop
        self._queue = event_queue
        self.user_id: int | None = None
        self._alarm_handle: int | None = None
        self._cb = MSG_CALLBACK(self._on_message)  # keep ref alive
        self.device_info: dict[str, Any] = {}
        self.host = ""
        self.wdev_type = 0
        self.unlock_strategy = UNLOCK_STRATEGY_AUTO
        self.door_channel = 2  # channelNo of the indoor doorphone lock relay

    # -- connection --------------------------------------------------------

    def connect(self, host: str, port: int, user: str, password: str) -> None:
        self.host = host
        self.user_id, dev = self._sdk.login(host, port, user, password)
        self.wdev_type = int(dev.struDeviceV30.wDevType)
        _LOGGER.info(
            "Logged in to %s as user id %s (device type %s)",
            host, self.user_id, self.wdev_type,
        )
        self._read_device_info()
        self._sdk.set_message_callback(self._cb)
        self._alarm_handle = self._sdk.setup_alarm_chan(self.user_id)
        _LOGGER.info("Alarm channel armed (handle %s)", self._alarm_handle)

    def disconnect(self) -> None:
        if self._alarm_handle is not None:
            self._sdk.close_alarm_chan(self._alarm_handle)
            self._alarm_handle = None
        if self.user_id is not None:
            self._sdk.logout(self.user_id)
            self.user_id = None

    def _read_device_info(self) -> None:
        ok, xml, _ = self._sdk.isapi(
            self.user_id, "GET", "/ISAPI/System/deviceInfo"
        )
        if ok and xml:
            self.device_info = {
                "model": _xml_tag(xml, "model"),
                "firmware": _xml_tag(xml, "firmwareVersion"),
                "serial": _xml_tag(xml, "serialNumber"),
                "name": _xml_tag(xml, "deviceName"),
            }
            _LOGGER.info("Device: %s", self.device_info)

    # -- event callback (runs in SDK thread) -------------------------------

    def _on_message(self, lCommand, pAlarmer, pAlarmInfo, dwBufLen, pUser):
        try:
            events = self._parse(int(lCommand), pAlarmInfo or 0, int(dwBufLen))
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Failed to parse alarm 0x%04x", lCommand)
            events = [{"event": "raw", "command": f"0x{lCommand:04x}"}]
        for ev in events:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, ev)
        return True  # BOOL return expected by the SDK

    def _parse(self, lCommand, pAlarmInfo, dwBufLen) -> list[dict[str, Any]]:
        _LOGGER.debug("Alarm 0x%04x (%d bytes)", lCommand, dwBufLen)

        if lCommand == COMM_ISAPI_ALARM:
            return self._parse_isapi_alarm(pAlarmInfo)

        # Read the raw buffer once, safely (pointer may be NULL).
        raw = b""
        if pAlarmInfo and dwBufLen:
            raw = ctypes.string_at(pAlarmInfo, min(int(dwBufLen), 256))

        if lCommand in (COMM_ALARM_VIDEO_INTERCOM, COMM_UPLOAD_VIDEO_INTERCOM_EVENT):
            _LOGGER.info(
                "Video-intercom cmd 0x%04x (%d B) raw=%s",
                lCommand, dwBufLen, raw[:48].hex(),
            )
            return [
                {
                    "event": "intercom",
                    "command": f"0x{lCommand:04x}",
                    "raw": raw[:48].hex(),
                }
            ]

        # Unknown: forward raw for live calibration.
        _LOGGER.info("Unhandled alarm 0x%04x raw=%s", lCommand, raw[:48].hex())
        return [{"event": "raw", "command": f"0x{lCommand:04x}", "raw": raw[:48].hex()}]

    def _parse_isapi_alarm(self, pAlarmInfo) -> list[dict[str, Any]]:
        if not pAlarmInfo:
            return []
        info = NET_DVR_ALARM_ISAPI_INFO.from_address(pAlarmInfo)
        if not info.pAlarmData or not info.dwAlarmDataLen:
            return []
        data = ctypes.string_at(info.pAlarmData, info.dwAlarmDataLen)
        text = data.decode(errors="replace")
        _LOGGER.info("ISAPI alarm (%s): %s", info.byDataType, text[:300])
        return self._normalize_isapi(text)

    def _normalize_isapi(self, text: str) -> list[dict[str, Any]]:
        """Map an ISAPI event payload (XML or JSON) to normalized events."""
        event_type = ""
        payload: dict[str, Any] = {}
        if text.lstrip().startswith("{"):
            try:
                payload = json.loads(text)
                event_type = _find_key(payload, "eventType") or ""
            except json.JSONDecodeError:
                pass
        else:
            event_type = _xml_tag(text, "eventType") or ""

        et = event_type.lower()
        out: list[dict[str, Any]] = []
        if any(k in et for k in ("call", "ring", "sip")):
            status = (_xml_tag(text, "status") or _find_key(payload, "status") or "").lower()
            if status in ("ring", "ringing", "request", "bellcall"):
                out.append({"event": "ring"})
                out.append({"event": "call_status", "status": "ringing"})
            elif status in ("oncall", "talking", "answer"):
                out.append({"event": "call_status", "status": "onCall"})
            elif status in ("hangup", "end", "idle", "ended", "dismiss", "cancel"):
                out.append({"event": "call_status", "status": "ended"})
                out.append({"event": "dismiss"})
            else:
                out.append({"event": "ring"})
        elif "motion" in et:
            out.append({"event": "motion"})
        elif "tamper" in et or "dismant" in et:
            out.append({"event": "tamper"})
        elif "unlock" in et or "door" in et:
            out.append({"event": "unlock", "door": _find_key(payload, "doorNo")})
        if not out:
            out.append({"event": "isapi", "eventType": event_type, "raw": text[:200]})
        return out

    # -- commands ----------------------------------------------------------

    def _isapi(self, method: str, url: str, body: str = "") -> tuple[bool, str]:
        ok, xml, status = self._sdk.isapi(self.user_id, method, url, body)
        return ok, xml or status

    def unlock(self, door: int = 1) -> tuple[bool, str]:
        strategy = self._effective_strategy()
        if strategy == UNLOCK_STRATEGY_KH6320_INDOOR:
            return self.unlock_indoor(door)
        return self._unlock_isapi(door)

    def _effective_strategy(self) -> str:
        strategy = self.unlock_strategy or UNLOCK_STRATEGY_AUTO
        if strategy == UNLOCK_STRATEGY_AUTO:
            return (
                UNLOCK_STRATEGY_KH6320_INDOOR
                if self.wdev_type == DEV_TYPE_INDOOR
                else UNLOCK_STRATEGY_GENERIC_ISAPI
            )
        return strategy

    def _unlock_isapi(self, door: int) -> tuple[bool, str]:
        body = (
            '<RemoteControlDoor xmlns="http://www.hikvision.com/ver20/XMLSchema">'
            "<cmd>open</cmd></RemoteControlDoor>"
        )
        return self._isapi("PUT", f"/ISAPI/AccessControl/RemoteControl/door/{door}", body)

    def unlock_indoor(self, door: int = 1) -> tuple[bool, str]:
        """Unlock the door lock wired to an analog doorphone (DS-KH6320-WTDE1).

        The 4-wire hybrid indoor station does not implement the native
        ``NET_DVR_CONTROL_GATEWAY_LOCK`` (16009) command nor the plain
        ``<cmd>open</cmd>`` ISAPI body — both return an error on this model. Its
        ``RemoteControlDoor`` endpoint requires ``channelNo`` and ``controlType``;
        the analog doorphone's lock relay sits on ``channelNo`` (2 by default,
        configurable via ``door_channel``), verified live against a DS-KH6320-WTDE1.
        """
        channel = getattr(self, "door_channel", 2) or 2
        body = (
            '<RemoteControlDoor xmlns="http://www.isapi.org/ver20/XMLSchema">'
            f"<doorNo>{door}</doorNo>"
            "<cmd>open</cmd>"
            f"<channelNo>{channel}</channelNo>"
            "<controlType>monitor</controlType>"
            "</RemoteControlDoor>"
        )
        return self._isapi(
            "PUT", f"/ISAPI/AccessControl/RemoteControl/door/{door}", body
        )

    def call_signal(self, cmd_type: str) -> tuple[bool, str]:
        body = json.dumps({"CallSignal": {"cmdType": cmd_type}})
        return self._isapi("PUT", "/ISAPI/VideoIntercom/callSignal?format=json", body)

    def answer(self) -> tuple[bool, str]:
        return self.call_signal("answer")

    def reject(self) -> tuple[bool, str]:
        return self.call_signal("reject")

    def hangup(self) -> tuple[bool, str]:
        return self.call_signal("hangUp")

    def reboot(self) -> tuple[bool, str]:
        return self._isapi("PUT", "/ISAPI/System/reboot")

    def call_status(self) -> str:
        ok, xml = self._isapi("GET", "/ISAPI/VideoIntercom/callSignal?format=json")
        if not ok:
            return "unknown"
        m = re.search(r'"cmdType"\s*:\s*"([^"]+)"', xml)
        return m.group(1) if m else "idle"


def _xml_tag(xml: str, tag: str) -> str | None:
    m = re.search(rf"<{tag}>(.*?)</{tag}>", xml, re.I | re.S)
    return m.group(1).strip() if m else None


def _find_key(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                return v
            found = _find_key(v, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_key(item, key)
            if found is not None:
                return found
    return None
