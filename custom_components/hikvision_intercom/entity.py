"""Shared base entity for Hikvision Intercom."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import CONF_HOST, DOMAIN, SIGNAL_CONNECTION, SIGNAL_EVENT
from .coordinator import IntercomCoordinator


class HikvisionIntercomEntity(Entity):
    """Base entity tying every platform to one intercom device."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: IntercomCoordinator) -> None:
        self.coordinator = coordinator
        self._entry = coordinator.entry
        self._host = self._entry.data[CONF_HOST]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._host)},
            name=self._entry.title,
            manufacturer="Hikvision",
            model="Video Intercom",
        )
        self._apply_device_info()

    def _apply_device_info(self) -> bool:
        """Fill model/firmware/serial once the bridge reports them.

        Returns True if the device info changed (so callers can re-write state).
        """
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
        """Track device-info updates and bridge connection state."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_EVENT.format(entry_id=self._entry.entry_id),
                self._on_status,
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_CONNECTION.format(entry_id=self._entry.entry_id),
                self._handle_connection,
            )
        )

    @callback
    def _on_status(self, data: dict) -> None:
        if data.get("event") == "status" and self._apply_device_info():
            self.async_write_ha_state()

    @callback
    def _handle_connection(self, connected: bool) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return self.coordinator.connected
