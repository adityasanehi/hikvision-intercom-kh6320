"""Binary sensors: ringing, motion, tamper, and door contact."""

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

    async def async_will_remove_from_hass(self) -> None:
        if self._cancel_off:
            self._cancel_off()
            self._cancel_off = None
        await super().async_will_remove_from_hass()

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

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._on_event(
            {"event": "call_status", "status": self.coordinator.data["call_status"]}
        )

    @callback
    def _on_event(self, data: dict) -> None:
        event = data.get("event")
        if event == "ring":
            self._attr_is_on = True
            self._pulse_off(RING_TIMEOUT)
        elif event in ("call_status", "status"):
            status = data.get("status" if event == "call_status" else "call_status")
            if status is None:
                return
            self._attr_is_on = None if status == "unknown" else status == CALL_RINGING
            if self._cancel_off:
                self._cancel_off()
                self._cancel_off = None
        elif event == "dismiss":
            self._attr_is_on = False
            if self._cancel_off:
                self._cancel_off()
                self._cancel_off = None
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
    """Physical door contact; unknown until the station reports a reading."""

    _key = "door"
    _attr_device_class = BinarySensorDeviceClass.DOOR

    def __init__(self, coordinator: IntercomCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_is_on = None

    @callback
    def _on_event(self, data: dict) -> None:
        if data.get("event") != "door" or not isinstance(data.get("open"), bool):
            return
        self._attr_is_on = data["open"]
        self.async_write_ha_state()
