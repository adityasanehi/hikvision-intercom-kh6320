"""Config flow for Hikvision Intercom (2-Wire)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_BRIDGE_URL,
    CONF_DOOR_COUNT,
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_RTSP_PORT,
    CONF_SDK_PORT,
    CONF_USERNAME,
    DEFAULT_BRIDGE_URL,
    DEFAULT_DOOR_COUNT,
    DEFAULT_NAME,
    DEFAULT_RTSP_PORT,
    DEFAULT_SDK_PORT,
    DEFAULT_USERNAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def _test_tcp(host: str, port: int, timeout: float = 5.0) -> bool:
    """Return True if a TCP connection to host:port succeeds."""
    try:
        fut = asyncio.open_connection(host, port)
        reader, writer = await asyncio.wait_for(fut, timeout)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001
            pass
        return True
    except (OSError, asyncio.TimeoutError):
        return False


class HikvisionIntercomConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Hikvision Intercom."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()

            # The device must at least answer on its SDK port.
            if not await _test_tcp(host, user_input[CONF_SDK_PORT]):
                errors["base"] = "cannot_connect_device"

            # The bridge is optional at setup time (may be installed later),
            # but warn if the URL is clearly unreachable.
            if not errors:
                bridge_ok = await self._test_bridge(user_input[CONF_BRIDGE_URL])
                if not bridge_ok:
                    _LOGGER.warning(
                        "SDK bridge at %s not reachable yet; entities will "
                        "connect once the add-on is running",
                        user_input[CONF_BRIDGE_URL],
                    )

            if not errors:
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME) or DEFAULT_NAME,
                    data=user_input,
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default="192.168.0.38"): str,
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(CONF_USERNAME, default=DEFAULT_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Required(CONF_SDK_PORT, default=DEFAULT_SDK_PORT): vol.Coerce(int),
                vol.Required(CONF_RTSP_PORT, default=DEFAULT_RTSP_PORT): vol.Coerce(int),
                vol.Required(
                    CONF_BRIDGE_URL, default=DEFAULT_BRIDGE_URL
                ): str,
                vol.Required(
                    CONF_DOOR_COUNT, default=DEFAULT_DOOR_COUNT
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=4)),
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    async def _test_bridge(self, bridge_url: str) -> bool:
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(
                f"{bridge_url.rstrip('/')}/health",
                timeout=aiohttp.ClientTimeout(total=4),
            ) as resp:
                return resp.status == 200
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return False
