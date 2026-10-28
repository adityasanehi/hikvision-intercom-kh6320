"""Entity regression checks without requiring a Home Assistant installation."""
import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = 'custom_components.hikvision_intercom'


def load_sensors():
    modules = {}
    def module(name, **attrs):
        obj = ModuleType(name)
        obj.__dict__.update(attrs)
        modules[name] = obj
        return obj

    module('homeassistant')
    module('homeassistant.components')
    module('homeassistant.components.binary_sensor',
           BinarySensorDeviceClass=SimpleNamespace(MOTION='motion', TAMPER='tamper', DOOR='door'),
           BinarySensorEntity=type('BinarySensorEntity', (), {}))
    module('homeassistant.core', HomeAssistant=object, callback=lambda fn: fn)
    module('homeassistant.helpers')
    module('homeassistant.helpers.dispatcher', async_dispatcher_connect=Mock())
    module('homeassistant.helpers.event', async_call_later=Mock())
    module('homeassistant.helpers.entity_platform', AddEntitiesCallback=object)
    module('custom_components')
    module(PACKAGE, HikvisionConfigEntry=object)
    module(PACKAGE + '.coordinator', IntercomCoordinator=object)

    class Entity:
        def __init__(self, coordinator):
            self._entry = coordinator.entry
            self.coordinator = coordinator
            self.hass = object()
            self.async_write_ha_state = Mock()
        async def async_added_to_hass(self):
            pass
        async def async_will_remove_from_hass(self):
            pass
        def async_on_remove(self, fn):
            pass

    module(PACKAGE + '.entity', HikvisionIntercomEntity=Entity)
    with patch.dict(sys.modules, modules):
        for name in ('const', 'binary_sensor'):
            spec = importlib.util.spec_from_file_location(
                PACKAGE + '.' + name,
                ROOT / 'custom_components/hikvision_intercom' / (name + '.py'))
            loaded = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = loaded
            spec.loader.exec_module(loaded)
    return loaded


sensors = load_sensors()


class SensorTests(unittest.TestCase):
    def setUp(self):
        entry = SimpleNamespace(entry_id='intercom', data={'host': '192.0.2.1'})
        self.coordinator = SimpleNamespace(entry=entry, data={'call_status': 'ringing'})

    def test_door_unknown_and_unlock_does_not_change_contact(self):
        sensor = sensors.DoorBinarySensor(self.coordinator)
        self.assertIsNone(sensor._attr_is_on)
        sensor._on_event({'event': 'unlock'})
        self.assertIsNone(sensor._attr_is_on)
        sensor._on_event({'event': 'door', 'open': True})
        self.assertTrue(sensor._attr_is_on)
        sensor._on_event({'event': 'unlock'})
        self.assertTrue(sensor._attr_is_on)
        sensor._on_event({'event': 'door', 'open': False})
        self.assertFalse(sensor._attr_is_on)

    def test_invalid_contact_readings_are_ignored(self):
        sensor = sensors.DoorBinarySensor(self.coordinator)
        for value in (None, 'false', 'true', 0, 1):
            sensor._on_event({'event': 'door', 'open': value})
            self.assertIsNone(sensor._attr_is_on)

    def test_ring_status_reconnect_and_end(self):
        sensor = sensors.RingingBinarySensor(self.coordinator)
        sensor._on_event({'event': 'ring'})
        cancel = sensor._cancel_off
        asyncio.run(sensor.async_added_to_hass())
        self.assertTrue(sensor._attr_is_on)
        cancel.assert_called()
        self.assertIsNone(sensor._cancel_off)
        sensor._on_event({'event': 'status', 'call_status': 'idle'})
        self.assertFalse(sensor._attr_is_on)
        sensor._on_event({'event': 'call_status', 'status': 'unknown'})
        self.assertIsNone(sensor._attr_is_on)

    def test_ring_timeout_cancelled_on_unload(self):
        sensor = sensors.RingingBinarySensor(self.coordinator)
        sensor._on_event({'event': 'ring'})
        cancel = sensor._cancel_off
        asyncio.run(sensor.async_will_remove_from_hass())
        cancel.assert_called()
        self.assertIsNone(sensor._cancel_off)


if __name__ == '__main__':
    unittest.main()
