"""Binary sensors: ringing, motion, tamper, door state."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HikvisionConfigEntry
from .const import (
    CALL_ENDED,
    CALL_IDLE,
    CALL_ONCALL,
    CALL_RINGING,
    CONF_HOST,
    RING_TIMEOUT,
    SIGNAL_EVENT,
)
from .coordinator import IntercomCoordinator
from .entity import HikvisionIntercomEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HikvisionConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            RingingBinarySensor(coordinator),
            MotionBinarySensor(coordinator),
            TamperBinarySensor(coordinator),
            DoorBinarySensor(coordinator),
        ]
    )


class _EventBinarySensor(HikvisionIntercomEntity, BinarySensorEntity):
    """Base for event-driven binary sensors."""

    _key = "generic"

    def __init__(self, coordinator: IntercomCoordinator) -> None:
        super().__init__(coordinator)
        host = coordinator.entry.data[CONF_HOST]
        self._attr_unique_id = f"{host}_{self._key}"
        self._attr_is_on = False
        self._cancel_off = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_EVENT.format(entry_id=self._entry.entry_id),
                self._on_event,
            )
        )

    @callback
    def _on_event(self, data: dict) -> None:
        """Override in subclasses."""

    @callback
    def _pulse_off(self, delay: float) -> None:
        if self._cancel_off:
            self._cancel_off()

        @callback
        def _off(_now) -> None:
            self._attr_is_on = False
            self._cancel_off = None
            self.async_write_ha_state()

        self._cancel_off = async_call_later(self.hass, delay, _off)


class RingingBinarySensor(_EventBinarySensor):
    """On while the doorbell is ringing / a call is incoming."""

    _key = "ringing"
    _attr_translation_key = "ringing"
    _attr_icon = "mdi:bell-ring"

    @callback
    def _on_event(self, data: dict) -> None:
        event = data.get("event")
        if event == "ring":
            self._attr_is_on = True
            self._pulse_off(RING_TIMEOUT)
        elif event == "call_status":
            status = data.get("status")
            self._attr_is_on = status == CALL_RINGING
            if status in (CALL_ENDED, CALL_IDLE, CALL_ONCALL) and self._cancel_off:
                self._cancel_off()
                self._cancel_off = None
        elif event in ("dismiss",):
            self._attr_is_on = False
        else:
            return
        self.async_write_ha_state()


class MotionBinarySensor(_EventBinarySensor):
    """Motion in front of the door station."""

    _key = "motion"
    _attr_device_class = BinarySensorDeviceClass.MOTION

    @callback
    def _on_event(self, data: dict) -> None:
        if data.get("event") != "motion":
            return
        self._attr_is_on = True
        self._pulse_off(10)
        self.async_write_ha_state()


class TamperBinarySensor(_EventBinarySensor):
    """Tamper / anti-removal alarm."""

    _key = "tamper"
    _attr_device_class = BinarySensorDeviceClass.TAMPER

    @callback
    def _on_event(self, data: dict) -> None:
        if data.get("event") != "tamper":
            return
        self._attr_is_on = True
        self._pulse_off(30)
        self.async_write_ha_state()


class DoorBinarySensor(_EventBinarySensor):
    """Door open/closed contact reported by the station."""

    _key = "door"
    _attr_device_class = BinarySensorDeviceClass.DOOR

    @callback
    def _on_event(self, data: dict) -> None:
        event = data.get("event")
        if event == "door":
            self._attr_is_on = bool(data.get("open"))
        elif event == "unlock":
            # Unlock pulse: show open briefly.
            self._attr_is_on = True
            self._pulse_off(8)
        else:
            return
        self.async_write_ha_state()
