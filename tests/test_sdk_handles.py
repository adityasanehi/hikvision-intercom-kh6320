"""Failed native handles must not be mistaken for successful logins."""
import ctypes
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'hikvision_sdk_bridge/rootfs/opt/bridge'))
from hcnetsdk import HCNetSDK


class SdkHandleTests(unittest.TestCase):
    def setUp(self):
        self.sdk = HCNetSDK.__new__(HCNetSDK)
        self.sdk._lib = Mock()
        self.sdk._configure_prototypes()
        self.sdk._lib.NET_DVR_GetLastError.return_value = 7

    def test_failed_login_is_signed_and_rejected(self):
        native = self.sdk._lib.NET_DVR_Login_V40
        self.assertIs(native.restype, ctypes.c_int)
        native.return_value = native.restype(0xffffffff).value
        with self.assertRaisesRegex(RuntimeError, 'login failed: SDK error 7'):
            self.sdk.login('192.0.2.1', 8000, 'user', 'password')

    def test_failed_alarm_handle_is_signed_and_rejected(self):
        native = self.sdk._lib.NET_DVR_SetupAlarmChan_V41
        self.assertIs(native.restype, ctypes.c_int)
        native.return_value = native.restype(0xffffffff).value
        with self.assertRaisesRegex(RuntimeError, 'setup alarm chan failed: 7'):
            self.sdk.setup_alarm_chan(0)


if __name__ == '__main__':
    unittest.main()
