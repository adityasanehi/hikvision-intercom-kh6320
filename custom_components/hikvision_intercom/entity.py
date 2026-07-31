"""Shared base entity for Hikvision Intercom."""

from __future__ import annotations

from homeassistant.helpers.device_info import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import CONF_HOST, DOMAIN, SIGNAL_CONNECTION
from .coordinator import IntercomCoordinator


class HikvisionIntercomEntity(Entity):
    """Base entity tying every platform to one intercom device."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: IntercomCoordinator) -> None:
        self.coordinator = coordinator
        self._entry = coordinator.entry
        host = self._entry.data[CONF_HOST]
        device = coordinator.data.get("device", {})
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, host)},
            name=self._entry.title,
            manufacturer="Hikvision",
            model=device.get("model", "2-Wire Video Intercom"),
            sw_version=device.get("firmware"),
            serial_number=device.get("serial"),
            configuration_url=None,
        )

    async def async_added_to_hass(self) -> None:
        """Track bridge connection state for availability."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_CONNECTION.format(entry_id=self._entry.entry_id),
                self._handle_connection,
            )
        )

    def _handle_connection(self, connected: bool) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return self.coordinator.connected
