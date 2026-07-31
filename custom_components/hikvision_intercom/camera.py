"""Camera platform: RTSP streams from the door station."""

from __future__ import annotations

from urllib.parse import quote

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.components.ffmpeg import async_get_image
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_info import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HikvisionConfigEntry
from .const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_RTSP_PORT,
    CONF_USERNAME,
    DOMAIN,
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
        entry = coordinator.entry
        self._channel = channel
        host = entry.data[CONF_HOST]
        self._attr_unique_id = f"{host}_camera_{channel}"
        self._attr_name = suffix
        self._attr_entity_registry_enabled_default = is_main
        device = coordinator.data.get("device", {})
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, host)},
            name=entry.title,
            manufacturer="Hikvision",
            model=device.get("model", "2-Wire Video Intercom"),
        )
        self._rtsp_url = self._build_rtsp_url(entry, channel)

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
