"""Buttons: answer / reject / hang up a call, reboot the station."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from collections.abc import Callable, Coroutine
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HikvisionConfigEntry
from .const import CMD_ANSWER, CMD_HANGUP, CMD_REBOOT, CMD_REJECT, CONF_HOST
from .coordinator import IntercomCoordinator
from .entity import HikvisionIntercomEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class IntercomButtonDescription(ButtonEntityDescription):
    """Describes an intercom button."""

    command: str


BUTTONS: tuple[IntercomButtonDescription, ...] = (
    IntercomButtonDescription(
        key="answer",
        translation_key="answer",
        icon="mdi:phone",
        command=CMD_ANSWER,
    ),
    IntercomButtonDescription(
        key="reject",
        translation_key="reject",
        icon="mdi:phone-hangup",
        command=CMD_REJECT,
    ),
    IntercomButtonDescription(
        key="hangup",
        translation_key="hangup",
        icon="mdi:phone-off",
        command=CMD_HANGUP,
    ),
    IntercomButtonDescription(
        key="reboot",
        translation_key="reboot",
        icon="mdi:restart",
        command=CMD_REBOOT,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HikvisionConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up call-control buttons."""
    coordinator = entry.runtime_data
    async_add_entities(IntercomButton(coordinator, desc) for desc in BUTTONS)


class IntercomButton(HikvisionIntercomEntity, ButtonEntity):
    """A call-control action."""

    entity_description: IntercomButtonDescription

    def __init__(
        self,
        coordinator: IntercomCoordinator,
        description: IntercomButtonDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        host = coordinator.entry.data[CONF_HOST]
        self._attr_unique_id = f"{host}_button_{description.key}"

    async def async_press(self) -> None:
        try:
            result = await self.coordinator.async_command(
                self.entity_description.command
            )
        except (ConnectionError, TimeoutError) as err:
            raise HomeAssistantError(
                f"SDK bridge not reachable: {err}"
            ) from err
        if not result.get("ok", False):
            raise HomeAssistantError(
                result.get("error", "command failed on the intercom")
            )
