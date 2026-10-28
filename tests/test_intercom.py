"""SDK parser checks using real ctypes buffers without loading the SDK."""
import asyncio
import ctypes
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'hikvision_sdk_bridge/rootfs/opt/bridge'))
from intercom import COMM_ISAPI_ALARM, IntercomDevice, NET_DVR_ALARM_ISAPI_INFO
from hcnetsdk import NET_DVR_DEVICEINFO_V40


class IntercomTests(unittest.TestCase):
    def setUp(self):
        self.sdk = Mock()
        self.device = IntercomDevice(self.sdk, Mock(), asyncio.Queue())

    def test_actual_isapi_abi_and_ring_payload(self):
        # HCNetSDK starts this structure with the payload pointer, not dwSize.
        self.assertEqual(NET_DVR_ALARM_ISAPI_INFO.pAlarmData.offset, 0)
        self.assertEqual(NET_DVR_ALARM_ISAPI_INFO.dwAlarmDataLen.offset, ctypes.sizeof(ctypes.c_void_p))
        payload = b'{"eventType":"call","status":"ringing"}'
        buf = ctypes.create_string_buffer(payload)
        info = NET_DVR_ALARM_ISAPI_INFO()
        info.pAlarmData = ctypes.addressof(buf)
        info.dwAlarmDataLen = len(payload)
        info.byDataType = 2
        events = self.device._parse(COMM_ISAPI_ALARM, ctypes.addressof(info), ctypes.sizeof(info))
        self.assertEqual(events, [{'event': 'ring'}, {'event': 'call_status', 'status': 'ringing'}])

    def test_rejects_truncated_null_and_oversized_alarm(self):
        info = NET_DVR_ALARM_ISAPI_INFO()
        address = ctypes.addressof(info)
        for pointer, size in ((0, 0), (address, 4), (address, ctypes.sizeof(info))):
            self.assertEqual(self.device._parse(COMM_ISAPI_ALARM, pointer, size), [])
        info.pAlarmData = 1  # Must reject the length before dereferencing.
        info.dwAlarmDataLen = (1 << 20) + 1
        self.assertEqual(self.device._parse(COMM_ISAPI_ALARM, address, ctypes.sizeof(info)), [])

    def test_call_status_endpoint_and_normalization(self):
        for raw, expected in [('idle', 'idle'), ('ring', 'ringing'), ('onCall', 'onCall'), ('error', 'unknown')]:
            self.sdk.isapi.return_value = (True, '{"CallStatus":{"status":"'+raw+'"}}', '')
            self.assertEqual(self.device.call_status(), expected)
        self.sdk.isapi.assert_called_with(None, 'GET', '/ISAPI/VideoIntercom/callStatus?format=json', '')

    def test_invalid_call_status_is_unknown(self):
        for payload in ('', '[]', '{}', 'null', '{"CallStatus":null}', '{"CallStatus":{"status":[]}}'):
            self.sdk.isapi.return_value = (True, payload, '')
            self.assertEqual(self.device.call_status(), 'unknown')
        self.sdk.isapi.return_value = (False, '', '')
        self.assertEqual(self.device.call_status(), 'unknown')

    def test_failed_callback_registration_aborts_connection(self):
        self.sdk.login.return_value = (1, NET_DVR_DEVICEINFO_V40())
        self.device._read_device_info = Mock()
        self.sdk.set_message_callback.return_value = False
        with self.assertRaisesRegex(RuntimeError, 'alarm callback'):
            self.device.connect('192.0.2.1', 8000, 'user', 'password')
        self.sdk.logout.assert_called_once_with(1)
        self.sdk.setup_alarm_chan.assert_not_called()


if __name__ == '__main__':
    unittest.main()
