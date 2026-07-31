"""Lock platform: the door opener relay(s)."""

from __future__ import annotations

import logging

from homeassistant.components.lock import LockEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HikvisionConfigEntry
from .const import (
    CMD_UNLOCK,
    CONF_DOOR_COUNT,
    CONF_HOST,
    DEFAULT_DOOR_COUNT,
    SIGNAL_EVENT,
)
from .coordinator import IntercomCoordinator
from .entity import HikvisionIntercomEntity

_LOGGER = logging.getLogger(__name__)

# Door relays are momentary: show "unlocked" for this long, then relock.
RELOCK_AFTER = 5


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HikvisionConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one lock per configured door."""
    coordinator = entry.runtime_data
    count = entry.data.get(CONF_DOOR_COUNT, DEFAULT_DOOR_COUNT)
    async_add_entities(
        DoorLock(coordinator, door_id) for door_id in range(1, count + 1)
    )


class DoorLock(HikvisionIntercomEntity, LockEntity):
    """A door opener relay exposed as a lock."""

    _attr_translation_key = "door"

    def __init__(self, coordinator: IntercomCoordinator, door_id: int) -> None:
        super().__init__(coordinator)
        self._door_id = door_id
        host = coordinator.entry.data[CONF_HOST]
        self._attr_unique_id = f"{host}_lock_{door_id}"
        self._attr_translation_placeholders = {"door": str(door_id)}
        # Momentary relay -> resting state is locked.
        self._attr_is_locked = True
        self._cancel_relock = None

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
        # Reflect unlocks triggered outside HA (keypad, card, app).
        if data.get("event") == "unlock" and data.get("door") in (None, self._door_id):
            self._show_unlocked()

    async def async_unlock(self, **kwargs) -> None:
        """Trigger the door opener."""
        try:
            result = await self.coordinator.async_command(
                CMD_UNLOCK, door=self._door_id
            )
        except (ConnectionError, TimeoutError) as err:
            raise HomeAssistantError(f"SDK bridge not reachable: {err}") from err
        if not result.get("ok", False):
            raise HomeAssistantError(
                result.get("error", "door unlock failed on the intercom")
            )
        self._show_unlocked()

    async def async_lock(self, **kwargs) -> None:
        """Momentary relay: nothing to actively lock; just reset the display."""
        if self._cancel_relock:
            self._cancel_relock()
            self._cancel_relock = None
        self._attr_is_locked = True
        self.async_write_ha_state()

    @callback
    def _show_unlocked(self) -> None:
        self._attr_is_locked = False
        self.async_write_ha_state()
        if self._cancel_relock:
            self._cancel_relock()

        @callback
        def _relock(_now) -> None:
            self._attr_is_locked = True
            self._cancel_relock = None
            self.async_write_ha_state()

        self._cancel_relock = async_call_later(self.hass, RELOCK_AFTER, _relock)
