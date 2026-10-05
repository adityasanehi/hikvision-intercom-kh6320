"""Camera platform: RTSP streams from the door station."""

from __future__ import annotations

from urllib.parse import quote

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.components.ffmpeg import async_get_image
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HikvisionConfigEntry
from .const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_RTSP_PORT,
    CONF_USERNAME,
    DOMAIN,
    SIGNAL_EVENT,
)
from .coordinator import IntercomCoordinator

# (channel, name suffix, is_main)
STREAMS = [
    (101, "Live", True),
    (102, "Live SD", False),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HikvisionConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the intercom cameras."""
    coordinator = entry.runtime_data
    async_add_entities(
        IntercomCamera(coordinator, channel, suffix, is_main)
        for channel, suffix, is_main in STREAMS
    )


class IntercomCamera(Camera):
    """An RTSP camera channel of the door station."""

    _attr_has_entity_name = True
    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(
        self,
        coordinator: IntercomCoordinator,
        channel: int,
        suffix: str,
        is_main: bool,
    ) -> None:
        super().__init__()
        self.coordinator = coordinator
        self._entry = coordinator.entry
        self._channel = channel
        host = self._entry.data[CONF_HOST]
        self._attr_unique_id = f"{host}_camera_{channel}"
        self._attr_name = suffix
        self._attr_entity_registry_enabled_default = is_main
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, host)},
            name=self._entry.title,
            manufacturer="Hikvision",
            model="Video Intercom",
        )
        self._apply_device_info()
        self._rtsp_url = self._build_rtsp_url(self._entry, channel)

    def _apply_device_info(self) -> bool:
        """Fill model/firmware/serial once the bridge reports them."""
        device = self.coordinator.data.get("device", {})
        info = self._attr_device_info
        changed = False
        for key, value in (
            ("model", device.get("model")),
            ("sw_version", device.get("firmware")),
            ("serial_number", device.get("serial")),
        ):
            if value and info.get(key) != value:
                info[key] = value
                changed = True
        return changed

    async def async_added_to_hass(self) -> None:
        """Track device-info updates from the bridge."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_EVENT.format(entry_id=self._entry.entry_id),
                self._on_status,
            )
        )

    @callback
    def _on_status(self, data: dict) -> None:
        if data.get("event") == "status" and self._apply_device_info():
            self.async_write_ha_state()

    @staticmethod
    def _build_rtsp_url(entry, channel: int) -> str:
        host = entry.data[CONF_HOST]
        port = entry.data.get(CONF_RTSP_PORT, 554)
        user = quote(entry.data[CONF_USERNAME], safe="")
        pwd = quote(entry.data[CONF_PASSWORD], safe="")
        return f"rtsp://{user}:{pwd}@{host}:{port}/Streaming/Channels/{channel}"

    async def stream_source(self) -> str:
        return self._rtsp_url

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        return await async_get_image(
            self.hass, self._rtsp_url, width=width, height=height
        )
