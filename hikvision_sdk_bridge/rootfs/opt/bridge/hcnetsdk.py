"""Minimal ctypes binding for the Hikvision HCNetSDK (Linux x86_64).

Only the pieces this bridge needs:
  * init / cleanup / SDK log + component paths
  * NET_DVR_Login_V40         (device login on port 8000)
  * NET_DVR_STDXMLConfig      (ISAPI passthrough: unlock, callSignal, reboot)
  * NET_DVR_SetupAlarmChan_V41 + message callback  (ring / motion / door events)

Struct layouts follow the official HCNetSDK C header (natural alignment),
NOT the app's JNA wrappers (which inline buffers). Verified field-by-field
against the SDK documentation; event-type semantics are calibrated live.
"""

from __future__ import annotations

import ctypes
import logging
import os
from ctypes import (
    CFUNCTYPE,
    POINTER,
    Structure,
    c_byte,
    c_char,
    c_char_p,
    c_int,
    c_long,
    c_uint,
    c_ushort,
    c_void_p,
)

_LOGGER = logging.getLogger("bridge.sdk")

BOOL = c_int
DWORD = c_uint
WORD = c_ushort
LONG = c_long
BYTE = c_byte


# --- structs --------------------------------------------------------------


class NET_DVR_USER_LOGIN_INFO(Structure):
    _fields_ = [
        ("sDeviceAddress", c_char * 129),
        ("byUseTransport", BYTE),
        ("wPort", WORD),
        ("sUserName", c_char * 64),
        ("sPassword", c_char * 64),
        ("cbLoginResult", c_void_p),
        ("pUser", c_void_p),
        ("bUseAsynLogin", c_int),
        ("byProxyType", BYTE),
        ("byUseUTCTime", BYTE),
        ("byLoginMode", BYTE),
        ("byHttps", BYTE),
        ("iProxyID", c_int),
        ("byVerifyMode", BYTE),
        ("byRes2", BYTE * 119),
    ]


class NET_DVR_DEVICEINFO_V30(Structure):
    _fields_ = [
        ("sSerialNumber", ctypes.c_ubyte * 48),
        ("byAlarmInPortNum", BYTE),
        ("byAlarmOutPortNum", BYTE),
        ("byDiskNum", BYTE),
        ("byDVRType", BYTE),
        ("byChanNum", BYTE),
        ("byStartChan", BYTE),
        ("byAudioChanNum", BYTE),
        ("byIPChanNum", BYTE),
        ("byZeroChanNum", BYTE),
        ("byMainProto", BYTE),
        ("bySubProto", BYTE),
        ("bySupport", BYTE),
        ("bySupport1", BYTE),
        ("bySupport2", BYTE),
        ("wDevType", WORD),
        ("bySupport3", BYTE),
        ("byMultiStreamProto", BYTE),
        ("byStartDChan", BYTE),
        ("byStartDTalkChan", BYTE),
        ("byHighDChanNum", BYTE),
        ("bySupport4", BYTE),
        ("byLanguageType", BYTE),
        ("byVoiceInChanNum", BYTE),
        ("byStartVoiceInChanNo", BYTE),
        ("byRes3", BYTE * 2),
        ("byMirrorChanNum", BYTE),
        ("wStartMirrorChanNo", WORD),
        ("byRes2", BYTE * 2),
    ]


class NET_DVR_DEVICEINFO_V40(Structure):
    _fields_ = [
        ("struDeviceV30", NET_DVR_DEVICEINFO_V30),
        ("bySupportLock", BYTE),
        ("byRetryLoginTime", BYTE),
        ("byPasswordLevel", BYTE),
        ("byProxyType", BYTE),
        ("dwSurplusLockTime", DWORD),
        ("byCharEncodeType", BYTE),
        ("bySupportDev5", BYTE),
        ("bySupport", BYTE),
        ("byLoginMode", BYTE),
        ("dwOEMCode", DWORD),
        ("iResidualValidity", c_int),
        ("byResidualValidity", BYTE),
        ("bySingleStartDTalkChan", BYTE),
        ("bySingleDTalkChanNums", BYTE),
        ("byPassWordResetLevel", BYTE),
        ("bySupportStreamEncrypt", BYTE),
        ("byMarketType", BYTE),
        ("byRes2", BYTE * 238),
    ]


class NET_DVR_XML_CONFIG_INPUT(Structure):
    _fields_ = [
        ("dwSize", DWORD),
        ("lpRequestUrl", c_void_p),
        ("dwRequestUrlLen", DWORD),
        ("lpInBuffer", c_void_p),
        ("dwInBufferSize", DWORD),
        ("dwRecvTimeOut", DWORD),
        ("byForceEncrpt", BYTE),
        ("byNumOfMultiPart", BYTE),
        ("byMultiPartNO", BYTE),
        ("byRes", BYTE * 125),
    ]


class NET_DVR_XML_CONFIG_OUTPUT(Structure):
    _fields_ = [
        ("dwSize", DWORD),
        ("lpOutBuffer", c_void_p),
        ("dwOutBufferSize", DWORD),
        ("dwReturnedXMLLen", DWORD),
        ("lpStatusBuffer", c_void_p),
        ("dwStatusSize", DWORD),
        ("byRes", BYTE * 128),
    ]


class NET_DVR_SETUPALARM_PARAM(Structure):
    _fields_ = [
        ("dwSize", DWORD),
        ("byLevel", BYTE),
        ("byAlarmInfoType", BYTE),
        ("byRetAlarmTypeV40", BYTE),
        ("byRetDevInfoVersion", BYTE),
        ("byRetVQDAlarmType", BYTE),
        ("byFaceAlarmDetection", BYTE),
        ("bySupport", BYTE),
        ("byBrokenNetHttp", BYTE),
        ("wTaskNo", WORD),
        ("byDeployType", BYTE),
        ("byRes1", BYTE * 3),
        ("byAlarmTypeURL", BYTE),
        ("byCustomCtrl", BYTE),
    ]


class NET_DVR_ALARMER(Structure):
    _fields_ = [
        ("byUserIDValid", BYTE),
        ("bySerialValid", BYTE),
        ("byVersionValid", BYTE),
        ("byDeviceNameValid", BYTE),
        ("byMacAddrValid", BYTE),
        ("byLinkPortValid", BYTE),
        ("byDeviceIPValid", BYTE),
        ("bySocketIPValid", BYTE),
        ("lUserID", LONG),
        ("sSerialNumber", ctypes.c_ubyte * 48),
        ("dwDeviceVersion", DWORD),
        ("sDeviceName", c_char * 32),
        ("byMacAddr", ctypes.c_ubyte * 6),
        ("wLinkPort", WORD),
        ("sDeviceIP", c_char * 128),
        ("sSocketIP", c_char * 128),
        ("byIpProtocol", BYTE),
        ("byRes2", BYTE * 11),
    ]


# void CALLBACK(LONG lCommand, NET_DVR_ALARMER*, char* pAlarmInfo, DWORD, void*)
MSG_CALLBACK = CFUNCTYPE(
    None, LONG, POINTER(NET_DVR_ALARMER), c_char_p, DWORD, c_void_p
)

# SetSDKInitCfg types
NET_SDK_INIT_CFG_LIBEAY_PATH = 3
NET_SDK_INIT_CFG_SSLEAY_PATH = 4
NET_SDK_INIT_CFG_SDK_PATH = 2


class NET_DVR_LOCAL_SDK_PATH(Structure):
    _fields_ = [("sPath", c_char * 256), ("byRes", BYTE * 128)]


class HCNetSDK:
    """Thin wrapper around libhcnetsdk.so."""

    def __init__(self, sdk_dir: str) -> None:
        self.sdk_dir = sdk_dir
        self._lib = self._load(sdk_dir)
        self._configure_prototypes()

    @staticmethod
    def _load(sdk_dir: str) -> ctypes.CDLL:
        # HCNetSDK dlopen()s its component libs (libHCCore, HCNetSDKCom/*)
        # relative to the process; make sure they're findable.
        os.environ["LD_LIBRARY_PATH"] = (
            f"{sdk_dir}:{sdk_dir}/HCNetSDKCom:"
            + os.environ.get("LD_LIBRARY_PATH", "")
        )
        lib_path = os.path.join(sdk_dir, "libhcnetsdk.so")
        _LOGGER.info("Loading HCNetSDK from %s", lib_path)
        return ctypes.CDLL(lib_path)

    def _configure_prototypes(self) -> None:
        lib = self._lib
        lib.NET_DVR_Init.restype = BOOL
        lib.NET_DVR_Cleanup.restype = BOOL
        lib.NET_DVR_GetLastError.restype = DWORD
        lib.NET_DVR_SetConnectTime.argtypes = [DWORD, DWORD]
        lib.NET_DVR_SetReconnect.argtypes = [DWORD, c_int]
        lib.NET_DVR_SetSDKInitCfg.argtypes = [c_int, c_void_p]
        lib.NET_DVR_SetSDKInitCfg.restype = BOOL

        lib.NET_DVR_Login_V40.argtypes = [
            POINTER(NET_DVR_USER_LOGIN_INFO),
            POINTER(NET_DVR_DEVICEINFO_V40),
        ]
        lib.NET_DVR_Login_V40.restype = LONG
        lib.NET_DVR_Logout.argtypes = [LONG]
        lib.NET_DVR_Logout.restype = BOOL

        lib.NET_DVR_STDXMLConfig.argtypes = [
            LONG,
            POINTER(NET_DVR_XML_CONFIG_INPUT),
            POINTER(NET_DVR_XML_CONFIG_OUTPUT),
        ]
        lib.NET_DVR_STDXMLConfig.restype = BOOL

        lib.NET_DVR_SetupAlarmChan_V41.argtypes = [
            LONG,
            POINTER(NET_DVR_SETUPALARM_PARAM),
        ]
        lib.NET_DVR_SetupAlarmChan_V41.restype = LONG
        lib.NET_DVR_CloseAlarmChan_V30.argtypes = [LONG]
        lib.NET_DVR_CloseAlarmChan_V30.restype = BOOL
        lib.NET_DVR_SetDVRMessageCallBack_V50.argtypes = [
            c_int,
            MSG_CALLBACK,
            c_void_p,
        ]
        lib.NET_DVR_SetDVRMessageCallBack_V50.restype = BOOL

    # -- lifecycle ---------------------------------------------------------

    def init(self) -> None:
        # Point the SDK at its own component directory before init.
        cfg = NET_DVR_LOCAL_SDK_PATH()
        cfg.sPath = self.sdk_dir.encode()
        self._lib.NET_DVR_SetSDKInitCfg(NET_SDK_INIT_CFG_SDK_PATH, ctypes.byref(cfg))
        if not self._lib.NET_DVR_Init():
            raise RuntimeError(f"NET_DVR_Init failed: {self.last_error()}")
        self._lib.NET_DVR_SetConnectTime(5000, 3)
        self._lib.NET_DVR_SetReconnect(10000, 1)

    def cleanup(self) -> None:
        self._lib.NET_DVR_Cleanup()

    def last_error(self) -> int:
        return int(self._lib.NET_DVR_GetLastError())

    # -- login -------------------------------------------------------------

    def login(
        self, host: str, port: int, user: str, password: str
    ) -> tuple[int, NET_DVR_DEVICEINFO_V40]:
        info = NET_DVR_USER_LOGIN_INFO()
        info.sDeviceAddress = host.encode()
        info.wPort = port
        info.sUserName = user.encode()
        info.sPassword = password.encode()
        info.byUseTransport = 0
        info.bUseAsynLogin = 0
        device = NET_DVR_DEVICEINFO_V40()
        uid = self._lib.NET_DVR_Login_V40(ctypes.byref(info), ctypes.byref(device))
        if uid < 0:
            raise RuntimeError(f"login failed: SDK error {self.last_error()}")
        return int(uid), device

    def logout(self, user_id: int) -> None:
        self._lib.NET_DVR_Logout(user_id)

    # -- ISAPI passthrough -------------------------------------------------

    def isapi(
        self,
        user_id: int,
        method: str,
        url: str,
        body: str = "",
        out_size: int = 1 << 18,
        timeout: int = 5000,
    ) -> tuple[bool, str, str]:
        """Send an ISAPI request through the SDK. Returns (ok, out_xml, status)."""
        request = f"{method} {url}"
        req_buf = request.encode()
        in_buf = body.encode()

        cin = NET_DVR_XML_CONFIG_INPUT()
        cin.dwSize = ctypes.sizeof(NET_DVR_XML_CONFIG_INPUT)
        cin.lpRequestUrl = ctypes.cast(
            ctypes.create_string_buffer(req_buf), c_void_p
        )
        # keep a ref so the buffer isn't GC'd during the call
        self._req_ref = ctypes.create_string_buffer(req_buf)
        cin.lpRequestUrl = ctypes.cast(self._req_ref, c_void_p)
        cin.dwRequestUrlLen = len(req_buf)
        if in_buf:
            self._in_ref = ctypes.create_string_buffer(in_buf)
            cin.lpInBuffer = ctypes.cast(self._in_ref, c_void_p)
            cin.dwInBufferSize = len(in_buf)
        cin.dwRecvTimeOut = timeout

        out_buf = ctypes.create_string_buffer(out_size)
        status_buf = ctypes.create_string_buffer(4096)
        cout = NET_DVR_XML_CONFIG_OUTPUT()
        cout.dwSize = ctypes.sizeof(NET_DVR_XML_CONFIG_OUTPUT)
        cout.lpOutBuffer = ctypes.cast(out_buf, c_void_p)
        cout.dwOutBufferSize = out_size
        cout.lpStatusBuffer = ctypes.cast(status_buf, c_void_p)
        cout.dwStatusSize = 4096

        ok = bool(
            self._lib.NET_DVR_STDXMLConfig(
                user_id, ctypes.byref(cin), ctypes.byref(cout)
            )
        )
        out_xml = out_buf.raw[: cout.dwReturnedXMLLen].decode(errors="replace")
        status = status_buf.value.decode(errors="replace")
        if not ok:
            _LOGGER.debug("ISAPI %s -> SDK err %s status=%s",
                          request, self.last_error(), status)
        return ok, out_xml, status

    # -- alarm channel -----------------------------------------------------

    def set_message_callback(self, cb: MSG_CALLBACK) -> bool:
        return bool(self._lib.NET_DVR_SetDVRMessageCallBack_V50(0, cb, None))

    def setup_alarm_chan(self, user_id: int) -> int:
        param = NET_DVR_SETUPALARM_PARAM()
        param.dwSize = ctypes.sizeof(NET_DVR_SETUPALARM_PARAM)
        param.byLevel = 1              # arm at second level
        param.byAlarmInfoType = 1      # prefer richer/ISAPI alarm info
        param.byRetAlarmTypeV40 = 1
        param.byRetDevInfoVersion = 1
        param.byDeployType = 1         # real-time deployment
        handle = self._lib.NET_DVR_SetupAlarmChan_V41(user_id, ctypes.byref(param))
        if handle < 0:
            raise RuntimeError(f"setup alarm chan failed: {self.last_error()}")
        return int(handle)

    def close_alarm_chan(self, handle: int) -> None:
        self._lib.NET_DVR_CloseAlarmChan_V30(handle)
