# Copyright (C) 2026 tis24dev
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Plain electric water heater (type WH): the app's start-program control model.

A WH has no `onOffStatus` of its own inside `settings` the way the heat-pump water
heater does. Its schema exposes four `startProgram` programmes -- `normal`, `eco`,
`max` and `bps` on the ES100V-FE3W(EU) this was built from -- each pinning its own
fixed `machMode` (0/1/2/3), plus a `stopProgram` carrying a fixed `onOffStatus:"0"`.
So a mode change and a power-on are both a sparse `startProgram {machMode}` on the
chosen programme, power-off is a sparse `stopProgram`, and only the setpoint goes
through `settings` (wire `setParameters`, as on the heat-pump). Every builder reads
its values from the schema, never from a parameter's live value: a start or a
history recovery can write into a category in memory.

Provenance: one live WH dump (ES100V-FE3W(EU), series fe3, 100 L). Its accepted
`commandHistory` carries `startProgram {machMode}` with the programme's own
`remoteActionable`/`remoteVisible` ancillaries and no `programName`, which is what
`mode_patch` reproduces. No dump yet shows an app-sent `stopProgram` or a setpoint
write, so those two bodies follow the same sparse shape and are checked on delivery
by the `WH` send profile.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from .command_dispatch import CommandPatch
from .hon_commands import SYNTHETIC_CATEGORY, param_range

WH_SETTINGS_COMMAND = "settings"
WH_START_COMMAND = "startProgram"
WH_STOP_COMMAND = "stopProgram"
# The schema parameter each write names.
WH_MODE_PARAM = "machMode"
WH_ONOFF_PARAM = "onOffStatus"
WH_TEMP_PARAM = "tempSel"
# The category selector a real `startProgram` carries: the loader adds it from the raw
# programme name (commands.py), and setting it moves the command onto that programme.
WH_PROGRAM_PARAM = "program"
# Fallback setpoint range when the schema declares none: the WH dump's tempSel.
WH_TEMP_FALLBACK = (30.0, 85.0, 1.0)


def code(raw: object) -> str | None:
    """A shadow value as the app sees it: the string of `parNewVal`.

    An integral float is folded to its integer spelling so `1.0` compares like `'1'`.
    """
    if raw is None:
        return None
    if isinstance(raw, float) and raw.is_integer():
        return str(int(raw))
    return str(raw).strip()


def _start(appliance):
    commands = getattr(appliance, "commands", None)
    return commands.get(WH_START_COMMAND) if isinstance(commands, Mapping) else None


def _settings(appliance):
    commands = getattr(appliance, "commands", None)
    return commands.get(WH_SETTINGS_COMMAND) if isinstance(commands, Mapping) else None


def mode_categories(appliance) -> dict[str, str] | None:
    """{programme key: fixed machMode} of `startProgram`, or None without programmes.

    The key is the programme slug the loader reduced the cloud category to (`normal`,
    `eco`, `max`, `bps`) and the value is the schema's fixed `machMode`. A command with
    no categories reports itself under the synthetic `_` key, which is not a programme
    and is skipped; a programme that pins no `machMode` leaves the whole table unknown,
    because a mode change could then not name the value to write.
    """
    command = _start(appliance)
    categories = getattr(command, "categories", None)
    if not isinstance(categories, Mapping):
        return None
    result: dict[str, str] = {}
    for key, category in categories.items():
        if str(key) == SYNTHETIC_CATEGORY:
            continue
        parameters = getattr(category, "parameters", None)
        parameter = parameters.get(WH_MODE_PARAM) if isinstance(parameters, Mapping) else None
        value = code(getattr(parameter, "schema_value", None))
        if not value:
            return None
        result[str(key)] = value
    return result or None


def operations(appliance) -> list[str]:
    """The programme keys a mode can be set to, in schema order; empty without any.

    Every `startProgram` programme is offered, including the resting `normal` one:
    the app reaches it with the same sparse `startProgram {machMode:"0"}` it uses for
    the others, so it is a real mode to select (only the older `hon` integration hid
    it and reported its state through the other programmes instead).
    """
    return list(mode_categories(appliance) or {})


def operation_for(appliance, mach_mode: object) -> str | None:
    """The programme whose fixed `machMode` equals the shadow's, or None.

    The lookup is by schema value, so the shadow's live `machMode` names the running
    programme without trusting any one category's in-memory value.
    """
    wanted = code(mach_mode)
    if wanted is None:
        return None
    for key, value in (mode_categories(appliance) or {}).items():
        if value == wanted:
            return key
    return None


def temperature_range(appliance) -> tuple[float, float, float]:
    """(min, max, step) of `settings.tempSel`, or the WH dump's fallback."""
    settings = _settings(appliance)
    parameters = getattr(settings, "parameters", None)
    parameter = parameters.get(WH_TEMP_PARAM) if isinstance(parameters, Mapping) else None
    return param_range(parameter) or WH_TEMP_FALLBACK


def mode_patch(operation: str, mach_mode: str, *, action: str = "set_mode") -> CommandPatch:
    """A sparse `startProgram {machMode}` on `operation`'s programme.

    The programme is selected in `prepare` so that `machMode` lands on the category it
    belongs to: writing it on whichever category happened to be active would overwrite
    that category's own fixed value in memory. `program_name=""` suppresses the
    top-level `programName`, which is what the app's own mode-change body carries
    (a programme start names its programme, a mode change does not).
    """

    def _select(parameters: dict) -> None:
        parameters[WH_PROGRAM_PARAM].value = operation

    return CommandPatch(
        WH_START_COMMAND,
        {WH_MODE_PARAM: str(mach_mode)},
        action=f"{action}_{operation}",
        prepare=_select,
        program_name="",
    )


def power_on_patch(operation: str, mach_mode: str) -> CommandPatch:
    """Power on by starting `operation`'s programme (its `onOffStatus` is fixed "1")."""
    return mode_patch(operation, mach_mode, action="power_on")


def power_off_patch() -> CommandPatch:
    """Power off with a sparse `stopProgram {onOffStatus:"0"}`."""
    return CommandPatch(
        WH_STOP_COMMAND, {WH_ONOFF_PARAM: "0"}, action="power_off"
    )


def temperature_patch(value: int) -> CommandPatch:
    """A sparse `settings {tempSel}` (wire `setParameters` through the `WH` profile)."""
    return CommandPatch(
        WH_SETTINGS_COMMAND, {WH_TEMP_PARAM: str(int(value))}, action="set_temperature"
    )


def validate_setpoint(value: object, allowed: Sequence[float]) -> bool:
    """Whether `value` is a whole number on the schema's grid within `allowed`."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    if not math.isfinite(value) or float(value) != int(value):
        return False
    low, high, step = allowed
    return low <= value <= high and (value - low) % step == 0
