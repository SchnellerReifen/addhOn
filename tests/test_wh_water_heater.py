# Copyright (C) 2026 tis24dev
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The plain electric water heater platform (type WH).

Its control model is the app's start-program one (see `wh.py`): a mode change and a
power-on are both a sparse `startProgram {machMode}` on the chosen programme, power-off
is a sparse `stopProgram`, and the setpoint goes through `settings`. The schema the
fixtures below mirror is a live WH dump (ES100V-FE3W(EU), series fe3): `settings.tempSel`
30-85 and four `startProgram` programmes normal/eco/max/bps with fixed machMode 0/1/2/3.
"""
import asyncio
import enum
import json
import math
import types
import unittest
from pathlib import Path
from unittest import mock

from tests.test_hpwh import _install_package_stubs, _mod  # same stubs, one place

_install_package_stubs()

water_heater = _mod("homeassistant.components.water_heater")


class _Feature(enum.IntFlag):
    TARGET_TEMPERATURE = 1
    OPERATION_MODE = 2
    AWAY_MODE = 4
    ON_OFF = 8


water_heater.WaterHeaterEntityFeature = getattr(water_heater, "WaterHeaterEntityFeature", _Feature)
water_heater.WaterHeaterEntity = getattr(water_heater, "WaterHeaterEntity", type("WaterHeaterEntity", (), {}))
for _name, _value in (("STATE_ECO", "eco"), ("STATE_ELECTRIC", "electric"),
                      ("STATE_HEAT_PUMP", "heat_pump"), ("STATE_OFF", "off")):
    setattr(water_heater, _name, getattr(water_heater, _name, _value))
_mod("homeassistant.components").water_heater = water_heater
_const = _mod("homeassistant.const")
_const.ATTR_TEMPERATURE = getattr(_const, "ATTR_TEMPERATURE", "temperature")
_const.UnitOfTemperature.FAHRENHEIT = getattr(_const.UnitOfTemperature, "FAHRENHEIT", "°F")

from homeassistant.exceptions import HomeAssistantError  # noqa: E402
from custom_components.addhon import water_heater as platform  # noqa: E402
from custom_components.addhon.const import CONF_ENABLE_EXPERIMENTAL, DOMAIN  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "wh_es100v" / "attributes.json"
SENT: list = []


def _range(value, low, high, step=1):
    return types.SimpleNamespace(value=value, min=low, max=high, step=step)


def _fixed(value):
    return types.SimpleNamespace(value=value, schema_value=value)


def _appliance(with_programmes: bool = True):
    settings = types.SimpleNamespace(parameters={"tempSel": _range(41, 30, 85)})
    commands: dict = {"settings": settings, "stopProgram": types.SimpleNamespace(parameters={})}
    if with_programmes:
        categories = {
            name: types.SimpleNamespace(parameters={"machMode": _fixed(mode)})
            for name, mode in (("normal", "0"), ("eco", "1"), ("max", "2"), ("bps", "3"))
        }
        commands["startProgram"] = types.SimpleNamespace(categories=categories, parameters={})
    return types.SimpleNamespace(commands=commands, model_attributes={})


class _Coordinator:
    """The pieces of HA's DataUpdateCoordinator the platform and its listener use."""

    def __init__(self, data) -> None:
        self.data = data
        self.hass = None
        self.last_update_success = True
        self.listeners: list = []

    def async_add_listener(self, update_callback):
        self.listeners.append(update_callback)

        def _remove() -> None:
            self.listeners.remove(update_callback)

        return _remove


class _Entry:
    entry_id = "entry-1"

    def __init__(self, experimental: bool) -> None:
        self.options = {CONF_ENABLE_EXPERIMENTAL: experimental}
        self.on_unload: list = []

    def async_on_unload(self, func) -> None:
        self.on_unload.append(func)


async def _setup(experimental: bool, appliance=None, **overrides) -> dict:
    SENT.clear()
    attributes = dict(json.loads(FIXTURE.read_text(encoding="utf-8"))["attributes"])
    attributes.update(overrides)
    data = {"wh-1": {"type": "WH", "name": "Boiler", "attributes": attributes,
                     "settings": {}, "appliance": appliance or _appliance()}}
    coordinator = _Coordinator(data)
    hass = types.SimpleNamespace(
        data={DOMAIN: {"entry-1": {"coordinator": coordinator, "client": None}}},
        config=types.SimpleNamespace(
            units=types.SimpleNamespace(temperature_unit=_const.UnitOfTemperature.CELSIUS)
        ),
    )
    entry = _Entry(experimental)
    added: list = []
    await platform.async_setup_entry(hass, entry, added.extend)
    for entity in added:
        entity.hass = hass
    return {"hass": hass, "entry": entry, "coordinator": coordinator, "added": added}


async def _build(experimental: bool, appliance=None, **overrides) -> list:
    return (await _setup(experimental, appliance=appliance, **overrides))["added"]


async def _record(hass, client, appliance, patch) -> None:
    SENT.append(patch)


_PATCHERS: list = []


def setUpModule() -> None:
    # Every write is recorded instead of sent; the refresh after it is a no-op.
    _PATCHERS.append(mock.patch.object(platform, "async_dispatch_patch", _record))
    _PATCHERS.append(mock.patch.object(platform, "_register_eco_schedule_service"))
    _PATCHERS.append(
        mock.patch(
            "custom_components.addhon.base_entity.HonBaseEntity._async_request_command_refresh",
            mock.AsyncMock(),
        )
    )
    for patcher in _PATCHERS:
        patcher.start()


def tearDownModule() -> None:
    while _PATCHERS:
        _PATCHERS.pop().stop()


class WaterHeaterTest(unittest.IsolatedAsyncioTestCase):
    async def test_not_created_without_the_experimental_option(self) -> None:
        self.assertEqual(await _build(experimental=False), [])

    async def test_created_for_a_wh_appliance(self) -> None:
        added = await _build(experimental=True)
        self.assertEqual(len(added), 1)
        self.assertIsInstance(added[0], platform.HonWaterHeater)

    async def test_not_created_without_a_setpoint_or_a_programme(self) -> None:
        appliance = types.SimpleNamespace(commands={"settings": types.SimpleNamespace(parameters={})},
                                          model_attributes={})
        self.assertEqual(await _build(experimental=True, appliance=appliance), [])

    async def test_reads_the_reporters_appliance(self) -> None:
        entity = (await _build(experimental=True))[0]
        self.assertEqual(entity.current_temperature, 28.0)
        self.assertEqual(entity.target_temperature, 41.0)
        self.assertEqual((entity.min_temp, entity.max_temp, entity.target_temperature_step),
                         (30.0, 85.0, 1.0))
        self.assertEqual(entity.current_operation, "normal")
        self.assertEqual(entity.operation_list, ["normal", "eco", "max", "bps", "off"])

    async def test_mode_change_sends_machmode_only(self) -> None:
        entity = (await _build(experimental=True))[0]
        await entity.async_set_operation_mode("eco")
        patch = SENT[0]
        self.assertEqual((patch.command_name, dict(patch.values)), ("startProgram", {"machMode": "1"}))
        self.assertEqual(patch.program_name, "")

    async def test_each_mode_sends_the_machmode_its_schema_fixes(self) -> None:
        entity = (await _build(experimental=True))[0]
        for operation in ("normal", "eco", "max", "bps"):
            await entity.async_set_operation_mode(operation)
        self.assertEqual(
            [dict(p.values) for p in SENT],
            [{"machMode": "0"}, {"machMode": "1"}, {"machMode": "2"}, {"machMode": "3"}],
        )

    async def test_an_unknown_mode_is_refused(self) -> None:
        entity = (await _build(experimental=True))[0]
        with self.assertRaises(HomeAssistantError) as ctx:
            await entity.async_set_operation_mode("turbo")
        self.assertEqual(ctx.exception.translation_key, "program_not_supported")
        self.assertEqual(SENT, [])

    async def test_off_mode_switches_off(self) -> None:
        entity = (await _build(experimental=True))[0]
        await entity.async_set_operation_mode("off")
        self.assertEqual((SENT[0].command_name, dict(SENT[0].values)),
                         ("stopProgram", {"onOffStatus": "0"}))

    async def test_turn_off(self) -> None:
        entity = (await _build(experimental=True))[0]
        await entity.async_turn_off()
        self.assertEqual((SENT[0].command_name, dict(SENT[0].values)),
                         ("stopProgram", {"onOffStatus": "0"}))

    async def test_turn_on_starts_the_current_programme(self) -> None:
        entity = (await _build(experimental=True, onOffStatus=0, machMode=2))[0]
        await entity.async_turn_on()
        self.assertEqual((SENT[0].command_name, dict(SENT[0].values)),
                         ("startProgram", {"machMode": "2"}))
        self.assertEqual(SENT[0].program_name, "")

    async def test_turn_on_without_a_known_mode_starts_the_first_programme(self) -> None:
        entity = (await _build(experimental=True, onOffStatus=0, machMode=9))[0]
        await entity.async_turn_on()
        self.assertEqual(dict(SENT[0].values), {"machMode": "0"})

    async def test_temperature(self) -> None:
        entity = (await _build(experimental=True))[0]
        await entity.async_set_temperature(temperature=45)
        self.assertEqual((SENT[0].command_name, dict(SENT[0].values)),
                         ("settings", {"tempSel": "45"}))

    async def test_temperature_out_of_range_or_fractional_is_refused(self) -> None:
        entity = (await _build(experimental=True))[0]
        for value in (29, 86, 45.5, True):
            with self.assertRaises(HomeAssistantError) as ctx:
                await entity.async_set_temperature(temperature=value)
            self.assertEqual(ctx.exception.translation_key, "invalid_setpoint", value)
        self.assertEqual(SENT, [])

    async def test_non_finite_temperatures_are_refused_not_crashing(self) -> None:
        entity = (await _build(experimental=True))[0]
        for value in (math.nan, math.inf, -math.inf):
            with self.assertRaises(HomeAssistantError) as ctx:
                await entity.async_set_temperature(temperature=value)
            self.assertEqual(ctx.exception.translation_key, "invalid_setpoint", value)
        self.assertEqual(SENT, [])

    async def test_an_unknown_power_state_is_unknown_not_off(self) -> None:
        entity = (await _build(experimental=True))[0]
        attributes = entity.coordinator.data["wh-1"]["attributes"]
        attributes["onOffStatus"] = "0"
        self.assertEqual(entity.current_operation, "off")
        for value in ("2", ""):
            attributes["onOffStatus"] = value
            self.assertIsNone(entity.current_operation, value)
        del attributes["onOffStatus"]
        self.assertIsNone(entity.current_operation)

    async def test_a_bps_programme_reads_as_its_own_operation(self) -> None:
        entity = (await _build(experimental=True, machMode=3))[0]
        self.assertEqual(entity.current_operation, "bps")

    async def test_a_fahrenheit_install_rounds_to_the_whole_degree(self) -> None:
        entity = (await _build(experimental=True))[0]
        entity.hass.config = types.SimpleNamespace(
            units=types.SimpleNamespace(temperature_unit=_const.UnitOfTemperature.FAHRENHEIT)
        )
        await entity.async_set_temperature(temperature=(105 - 32) * 5 / 9)  # 40.56
        self.assertEqual([dict(p.values) for p in SENT], [{"tempSel": "41"}])

    async def test_a_fractional_fahrenheit_is_refused_not_rounded(self) -> None:
        entity = (await _build(experimental=True))[0]
        entity.hass.config = types.SimpleNamespace(
            units=types.SimpleNamespace(temperature_unit=_const.UnitOfTemperature.FAHRENHEIT)
        )
        with self.assertRaises(HomeAssistantError) as ctx:
            await entity.async_set_temperature(temperature=(104.7 - 32) * 5 / 9)
        self.assertEqual(ctx.exception.translation_key, "invalid_setpoint")
        self.assertEqual(SENT, [])


if __name__ == "__main__":
    unittest.main()
