"""Coordinator: persistent WebSocket link to the SDK bridge add-on.

The bridge (a glibc add-on running the Hikvision HCNetSDK) does the heavy
lifting on port 8000: login, alarm/event stream, callSignal, door unlock and
two-way audio. This coordinator keeps a push connection open, forwards events
to entities via the dispatcher, and sends commands back.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CMD_STATUS,
    DOMAIN,
    SIGNAL_CONNECTION,
    SIGNAL_EVENT,
)

_LOGGER = logging.getLogger(__name__)

RECONNECT_MIN = 2
RECONNECT_MAX = 30


class IntercomCoordinator:
    """Owns the WebSocket connection to the bridge for one intercom device."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, bridge_url: str) -> None:
        self.hass = hass
        self.entry = entry
        self._bridge_url = bridge_url.rstrip("/")
        self._session: aiohttp.ClientSession = async_get_clientsession(hass)
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._task: asyncio.Task | None = None
        self._closing = False
        self._req_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self.connected = False
        # Last known state, refreshed from bridge "status" and live events.
        self.data: dict[str, Any] = {
            "call_status": "idle",
            "device": {},
        }

    # ---- lifecycle -------------------------------------------------------

    async def async_start(self) -> None:
        """Start the background connection loop."""
        self._closing = False
        self._task = self.entry.async_create_background_task(
            self.hass, self._run(), name=f"{DOMAIN}_ws_{self.entry.entry_id}"
        )

    async def async_stop(self) -> None:
        """Tear down the connection."""
        self._closing = True
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    @property
    def ws_url(self) -> str:
        base = self._bridge_url.replace("http://", "ws://").replace("https://", "wss://")
        return f"{base}/ws"

    # ---- connection loop -------------------------------------------------

    async def _run(self) -> None:
        delay = RECONNECT_MIN
        while not self._closing:
            try:
                _LOGGER.debug("Connecting to bridge %s", self.ws_url)
                async with self._session.ws_connect(
                    self.ws_url,
                    heartbeat=20,
                    timeout=aiohttp.ClientTimeout(connect=10),
                ) as ws:
                    self._ws = ws
                    self._set_connected(True)
                    delay = RECONNECT_MIN
                    # Ask the bridge to bind/login to our device and send status.
                    await self._send_raw(
                        {
                            "type": "bind",
                            "host": self.entry.data.get("host"),
                            "sdk_port": self.entry.data.get("sdk_port"),
                            "username": self.entry.data.get("username"),
                            "password": self.entry.data.get("password"),
                            "unlock_strategy": self.entry.data.get(
                                "unlock_strategy", "auto"
                            ),
                            "door_channel": self.entry.data.get(
                                "door_channel", 2
                            ),
                        }
                    )
                    await self.async_command(CMD_STATUS)
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            self._handle_message(msg.json())
                        elif msg.type in (
                            aiohttp.WSMsgType.CLOSED,
                            aiohttp.WSMsgType.ERROR,
                        ):
                            break
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as err:
                _LOGGER.debug("Bridge connection error: %s", err)
            finally:
                self._ws = None
                self._set_connected(False)
                self._fail_pending(ConnectionError("bridge disconnected"))

            if self._closing:
                break
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX)

    @callback
    def _set_connected(self, state: bool) -> None:
        if state == self.connected:
            return
        self.connected = state
        async_dispatcher_send(
            self.hass, SIGNAL_CONNECTION.format(entry_id=self.entry.entry_id), state
        )

    # ---- message handling ------------------------------------------------

    @callback
    def _handle_message(self, data: dict[str, Any]) -> None:
        mtype = data.get("type")
        if mtype == "event":
            event = data.get("event")
            _LOGGER.debug("Intercom event: %s", data)
            if event == "call_status":
                self.data["call_status"] = data.get("status", "idle")
            async_dispatcher_send(
                self.hass, SIGNAL_EVENT.format(entry_id=self.entry.entry_id), data
            )
        elif mtype == "status":
            self.data["device"] = data.get("device", {})
            if "call_status" in data:
                self.data["call_status"] = data["call_status"]
            async_dispatcher_send(
                self.hass,
                SIGNAL_EVENT.format(entry_id=self.entry.entry_id),
                {"event": "status", **data},
            )
        elif mtype == "result":
            rid = data.get("id")
            fut = self._pending.pop(rid, None)
            if fut and not fut.done():
                fut.set_result(data)

    def _fail_pending(self, err: Exception) -> None:
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(err)
        self._pending.clear()

    # ---- outbound --------------------------------------------------------

    async def _send_raw(self, payload: dict[str, Any]) -> None:
        if self._ws is None or self._ws.closed:
            raise ConnectionError("bridge not connected")
        await self._ws.send_json(payload)

    async def async_command(
        self, command: str, timeout: float = 10.0, **params: Any
    ) -> dict[str, Any]:
        """Send a command to the bridge and await its result (retry once on drop)."""
        payload = {"type": "command", "command": command, **params}
        last_err: Exception | None = None
        for attempt in range(2):
            self._req_id += 1
            rid = self._req_id
            fut: asyncio.Future = self.hass.loop.create_future()
            self._pending[rid] = fut
            try:
                await self._send_raw({**payload, "id": rid})
                return await asyncio.wait_for(fut, timeout)
            except (ConnectionError, asyncio.TimeoutError) as err:
                self._pending.pop(rid, None)
                last_err = err
                # The socket may have dropped just as we sent the command; wait
                # for the background loop to reconnect and retry once.
                if attempt == 0 and isinstance(err, ConnectionError):
                    await asyncio.sleep(RECONNECT_MIN)
                    continue
                raise err
        raise last_err  # pragma: no cover
