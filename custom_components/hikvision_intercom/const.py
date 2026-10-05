"""Constants for the Hikvision Intercom integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "hikvision_intercom"

# Config entry keys
CONF_HOST: Final = "host"
CONF_SDK_PORT: Final = "sdk_port"
CONF_RTSP_PORT: Final = "rtsp_port"
CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_BRIDGE_URL: Final = "bridge_url"
CONF_DOOR_COUNT: Final = "door_count"
CONF_NAME: Final = "name"
CONF_UNLOCK_STRATEGY: Final = "unlock_strategy"
CONF_DOOR_CHANNEL: Final = "door_channel"

# Defaults (from reverse engineering of the DS-KIS/2-wire kit)
DEFAULT_SDK_PORT: Final = 8000
DEFAULT_RTSP_PORT: Final = 554
DEFAULT_USERNAME: Final = "admin"
DEFAULT_BRIDGE_URL: Final = "http://homeassistant.local:8199"
DEFAULT_DOOR_COUNT: Final = 1
DEFAULT_NAME: Final = "Türklingel"
DEFAULT_UNLOCK_STRATEGY: Final = "auto"
DEFAULT_DOOR_CHANNEL: Final = 2

# Unlock strategies (handed to the SDK bridge)
UNLOCK_STRATEGY_AUTO: Final = "auto"
UNLOCK_STRATEGY_GENERIC_ISAPI: Final = "generic_isapi"
UNLOCK_STRATEGY_KH6320_INDOOR: Final = "kh6320_indoor"

# Dispatcher signal templates
SIGNAL_EVENT: Final = "hikvision_intercom_event_{entry_id}"
SIGNAL_CONNECTION: Final = "hikvision_intercom_conn_{entry_id}"

# Event types pushed by the bridge (mapped from SDK alarm callbacks)
EVENT_RING: Final = "ring"           # incoming call / doorbell pressed
EVENT_MOTION: Final = "motion"       # motion detection
EVENT_TAMPER: Final = "tamper"       # tamper alarm
EVENT_DOOR: Final = "door"           # door open/unlocked status
EVENT_CALL_STATUS: Final = "call_status"  # idle/ringing/onCall/ended
EVENT_UNLOCK: Final = "unlock"       # door unlocked (by anyone)
EVENT_DISMISS: Final = "dismiss"     # call dismissed/hung up

# Call status values (from /ISAPI/VideoIntercom/callSignal)
CALL_IDLE: Final = "idle"
CALL_RINGING: Final = "ringing"
CALL_ONCALL: Final = "onCall"
CALL_ENDED: Final = "ended"

# Commands sent to the bridge
CMD_UNLOCK: Final = "unlock"
CMD_ANSWER: Final = "answer"
CMD_REJECT: Final = "reject"
CMD_HANGUP: Final = "hangup"
CMD_REBOOT: Final = "reboot"
CMD_STATUS: Final = "status"

# How long the "ringing" binary sensor stays on without a follow-up event (s)
RING_TIMEOUT: Final = 30
