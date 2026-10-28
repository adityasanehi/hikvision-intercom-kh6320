"""Call-status polling and reconnect snapshot regression checks."""
import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'hikvision_sdk_bridge/rootfs/opt/bridge'))
from server import BridgeServer


class PollTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = BridgeServer('/unused', 8199)
        self.server._loop = asyncio.get_running_loop()
        self.device = SimpleNamespace(wdev_type=602, call_state='idle',
                                      call_status=Mock(return_value='ringing'), device_info={})
        self.server._device = self.device

    async def poll_once(self):
        with patch('server.asyncio.sleep', new=AsyncMock(side_effect=asyncio.CancelledError)):
            with self.assertRaises(asyncio.CancelledError):
                await self.server._poll_call_status()

    async def test_ring_then_idle_with_no_duplicate_events(self):
        await self.poll_once()
        self.assertEqual(self.server._queue.get_nowait(), {'event': 'call_status', 'status': 'ringing'})
        self.assertEqual(self.server._status_message()['call_status'], 'ringing')
        await self.poll_once()
        self.assertTrue(self.server._queue.empty())
        self.device.call_status.return_value = 'idle'
        await self.poll_once()
        self.assertEqual(self.server._queue.get_nowait(), {'event': 'call_status', 'status': 'idle'})

    async def test_failed_poll_reports_unknown_and_recovers(self):
        self.device.call_status.side_effect = RuntimeError('disconnected')
        await self.poll_once()
        self.assertEqual(self.server._queue.get_nowait()['status'], 'unknown')
        self.device.call_status.side_effect = None
        await self.poll_once()
        self.assertEqual(self.server._queue.get_nowait()['status'], 'ringing')

    async def test_non_indoor_and_unbound_devices_are_not_polled(self):
        self.device.wdev_type = 1
        await self.poll_once()
        self.device.call_status.assert_not_called()
        self.server._device = None
        await self.poll_once()
        self.assertEqual(self.server._status_message()['call_status'], 'unknown')


if __name__ == '__main__':
    unittest.main()
