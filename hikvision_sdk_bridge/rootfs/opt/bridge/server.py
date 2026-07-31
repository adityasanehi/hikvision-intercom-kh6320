"""WebSocket/HTTP API between the SDK bridge and the HA integration.

Protocol (JSON over ws://<addon>:8199/ws):
  client -> bridge:
    {"type":"bind","host","sdk_port","username","password"}
    {"type":"command","id":N,"command":"unlock","door":1}
  bridge -> client:
    {"type":"event","event":"ring",...}
    {"type":"status","device":{...},"call_status":"idle"}
    {"type":"result","id":N,"ok":true,"data":...}
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiohttp import WSMsgType, web

from hcnetsdk import HCNetSDK
from intercom import IntercomDevice

_LOGGER = logging.getLogger("bridge.server")


class BridgeServer:
    def __init__(self, sdk_dir: str, port: int) -> None:
        self._sdk_dir = sdk_dir
        self._port = port
        self._loop: asyncio.AbstractEventLoop | None = None
        self._sdk: HCNetSDK | None = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._device: IntercomDevice | None = None
        self._bind_key: tuple | None = None
        self._bind_lock = asyncio.Lock()
        self._clients: set[web.WebSocketResponse] = set()

    # -- lifecycle ---------------------------------------------------------

    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._sdk = HCNetSDK(self._sdk_dir)
        await self._loop.run_in_executor(None, self._sdk.init)
        _LOGGER.info("HCNetSDK initialised")

        app = web.Application()
        app.router.add_get("/health", self._health)
        app.router.add_get("/ws", self._ws_handler)
        app.router.add_post("/command", self._http_command)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", self._port)
        await site.start()
        _LOGGER.info("Bridge listening on :%s", self._port)

        asyncio.create_task(self._broadcaster())
        # run forever
        await asyncio.Event().wait()

    # -- http --------------------------------------------------------------

    async def _health(self, request: web.Request) -> web.Response:
        return web.json_response(
            {"ok": True, "bound": self._device is not None,
             "device": self._device.device_info if self._device else {}}
        )

    async def _http_command(self, request: web.Request) -> web.Response:
        data = await request.json()
        result = await self._run_command(data)
        return web.json_response(result)

    # -- websocket ---------------------------------------------------------

    async def _ws_handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)
        self._clients.add(ws)
        _LOGGER.info("Client connected (%d total)", len(self._clients))
        # Send current snapshot immediately.
        if self._device is not None:
            await self._safe_send(ws, self._status_message())
        try:
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue
                try:
                    data = msg.json()
                except ValueError:
                    continue
                await self._handle(ws, data)
        finally:
            self._clients.discard(ws)
            _LOGGER.info("Client disconnected (%d left)", len(self._clients))
        return ws

    async def _handle(self, ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
        mtype = data.get("type")
        if mtype == "bind":
            await self._ensure_bound(data)
            await self._safe_send(ws, self._status_message())
        elif mtype == "command":
            result = await self._run_command(data)
            result["type"] = "result"
            result["id"] = data.get("id")
            await self._safe_send(ws, result)

    # -- device binding ----------------------------------------------------

    async def _ensure_bound(self, data: dict[str, Any]) -> None:
        key = (
            data.get("host"),
            int(data.get("sdk_port", 8000)),
            data.get("username"),
            data.get("password"),
        )
        async with self._bind_lock:
            if self._device is not None and self._bind_key == key:
                return
            if self._device is not None:
                await self._loop.run_in_executor(None, self._device.disconnect)
                self._device = None
            device = IntercomDevice(self._sdk, self._loop, self._queue)
            try:
                await self._loop.run_in_executor(
                    None, device.connect, key[0], key[1], key[2], key[3]
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("Login to %s failed: %s", key[0], err)
                raise
            self._device = device
            self._bind_key = key

    def _status_message(self) -> dict[str, Any]:
        dev = self._device
        return {
            "type": "status",
            "device": dev.device_info if dev else {},
            "call_status": "idle",
        }

    # -- commands ----------------------------------------------------------

    async def _run_command(self, data: dict[str, Any]) -> dict[str, Any]:
        if self._device is None:
            return {"ok": False, "error": "device not bound"}
        cmd = data.get("command")
        dev = self._device
        try:
            if cmd == "unlock":
                ok, msg = await self._loop.run_in_executor(
                    None, dev.unlock, int(data.get("door", 1))
                )
            elif cmd == "answer":
                ok, msg = await self._loop.run_in_executor(None, dev.answer)
            elif cmd == "reject":
                ok, msg = await self._loop.run_in_executor(None, dev.reject)
            elif cmd == "hangup":
                ok, msg = await self._loop.run_in_executor(None, dev.hangup)
            elif cmd == "reboot":
                ok, msg = await self._loop.run_in_executor(None, dev.reboot)
            elif cmd == "status":
                status = await self._loop.run_in_executor(None, dev.call_status)
                return {"ok": True, "data": {"call_status": status}}
            else:
                return {"ok": False, "error": f"unknown command {cmd}"}
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Command %s failed", cmd)
            return {"ok": False, "error": str(err)}
        return {"ok": bool(ok), "data": msg}

    # -- event fan-out -----------------------------------------------------

    async def _broadcaster(self) -> None:
        while True:
            ev = await self._queue.get()
            message = {"type": "event", **ev}
            for ws in list(self._clients):
                await self._safe_send(ws, message)

    async def _safe_send(self, ws: web.WebSocketResponse, payload: dict) -> None:
        try:
            await ws.send_json(payload)
        except (ConnectionResetError, RuntimeError):
            self._clients.discard(ws)
