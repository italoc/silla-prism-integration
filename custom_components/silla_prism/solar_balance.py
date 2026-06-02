"""Shared state for Prism solar battery balancing."""

from __future__ import annotations

from dataclasses import dataclass

from .const import DOMAIN

SOLAR_BALANCE_DISABLED = "disabled"
SOLAR_BALANCE_WAITING_DATA = "waiting_data"
SOLAR_BALANCE_WAITING_STABLE_SURPLUS = "waiting_stable_surplus"
SOLAR_BALANCE_PAUSED_LOW_SURPLUS = "paused_low_surplus"
SOLAR_BALANCE_EXTERNAL_PAUSED = "external_paused"
SOLAR_BALANCE_CHARGING_SURPLUS = "charging_surplus"
SOLAR_BALANCE_LOW_SURPLUS_KEEP_CHARGING = "low_surplus_keep_charging"

SURPLUS_SOURCE_SOLAR_HOME_LOAD = "solar_home_load"
SURPLUS_SOURCE_PRISM_GRID_BATTERY = "prism_grid_battery"


@dataclass(slots=True)
class SolarBalanceState:
    """Store one complete balancing decision for diagnostics.

    The switch entity owns the control loop; sensor entities only render this
    snapshot so users can see why the controller changed, held or skipped
    current.
    """

    status: str = SOLAR_BALANCE_WAITING_DATA
    surplus_current: float | None = None
    available_power: float | None = None
    target_power: float | None = None
    start_delay_remaining: int | None = None
    grid_power: float | None = None
    ev_power: float | None = None
    solar_power: float | None = None
    home_load_power: float | None = None
    battery_power: float | None = None
    battery_charge_power: float | None = None
    battery_discharge_power: float | None = None
    battery_power_used: float | None = None
    battery_max_charge_power: float | None = None
    battery_soc: float | None = None
    battery_reserve_power: float | None = None
    surplus_source: str | None = None
    target_export_power: float | None = None
    deadband_power: float | None = None
    raw_target_current: float | None = None
    target_current: float | None = None
    unused_export_power: float | None = None
    excess_import_power: float | None = None
    residual_export_remaining: int | None = None
    deadband_active: bool | None = None
    ramp_limited: bool | None = None
    ramp_direction: str | None = None
    current_limit_reason: str | None = None
    decision_reason: str | None = None
    decision_summary: str | None = None


@dataclass(slots=True, frozen=True)
class BatteryPowerBreakdown:
    """Normalized battery power values used by the balancer.

    Positive normalized power means discharge, negative means charge.
    """

    normalized_power: float
    charge_power: float
    discharge_power: float
    charge_available_above_reserve: float
    power_to_exclude: float


@dataclass(slots=True, frozen=True)
class AvailablePowerResult:
    """Calculated EV surplus and the source used for the calculation."""

    available_power: float
    source: str
    effective_home_load_power: float | None


def normalize_battery_power(
    battery_power: float,
    battery_discharge_positive: bool,
    battery_reserve_power: float,
    use_battery_charge: bool,
) -> BatteryPowerBreakdown:
    """Normalize battery power and return the pieces used by the algorithm."""
    normalized_power = (
        battery_power if battery_discharge_positive else -battery_power
    )
    charge_power = max(-normalized_power, 0)
    discharge_power = max(normalized_power, 0)
    charge_available = max(charge_power - battery_reserve_power, 0)
    power_to_exclude = discharge_power - (
        charge_available if use_battery_charge else 0
    )
    return BatteryPowerBreakdown(
        normalized_power=normalized_power,
        charge_power=charge_power,
        discharge_power=discharge_power,
        charge_available_above_reserve=charge_available,
        power_to_exclude=power_to_exclude,
    )


def get_battery_reserve_power(
    battery_soc: float | None,
    battery_max_charge_power: float,
    soc_mid: float,
    soc_high: float,
    mid_reserve_power: float,
    high_reserve_power: float,
) -> float:
    """Return how much battery charge power should be reserved."""
    if battery_soc is None:
        return battery_max_charge_power
    if battery_soc >= 95:
        return 0
    if battery_soc >= soc_high:
        return high_reserve_power
    if battery_soc >= soc_mid:
        return mid_reserve_power
    return battery_max_charge_power


def calculate_available_power(
    *,
    ev_power: float,
    grid_power: float,
    battery_charge_available: float,
    battery_power_to_exclude: float,
    use_battery_charge: bool,
    solar_power: float | None = None,
    home_load_power: float | None = None,
    home_load_includes_ev: bool = False,
) -> AvailablePowerResult:
    """Return EV surplus power from direct sensors or Prism fallback data."""
    if solar_power is not None and home_load_power is not None:
        solar_production = abs(solar_power)
        effective_home_load = max(home_load_power, 0)
        if home_load_includes_ev:
            effective_home_load = max(effective_home_load - ev_power, 0)
        available_power = solar_production - effective_home_load
        if use_battery_charge and available_power > 0:
            available_power += battery_charge_available
        return AvailablePowerResult(
            available_power=available_power,
            source=SURPLUS_SOURCE_SOLAR_HOME_LOAD,
            effective_home_load_power=effective_home_load,
        )

    return AvailablePowerResult(
        available_power=ev_power - grid_power - battery_power_to_exclude,
        source=SURPLUS_SOURCE_PRISM_GRID_BATTERY,
        effective_home_load_power=None,
    )


def describe_solar_balance_state(state: SolarBalanceState) -> str:
    """Return a concise human-readable explanation for the latest decision."""
    reason = state.current_limit_reason or state.decision_reason or state.status
    target = (
        f"{state.target_current:g}A"
        if isinstance(state.target_current, (int, float))
        else "no current"
    )
    available = (
        f"{state.available_power:.0f}W"
        if isinstance(state.available_power, (int, float))
        else "unknown surplus"
    )

    if reason == "manual_current_override":
        return f"Holding {target}: explicit Home Assistant current override is active."
    if reason == "low_surplus_hold_6a":
        return f"Holding 6A: calculated surplus is low ({available})."
    if reason == "residual_export_recovery":
        return f"Raising to {target}: residual export stayed available long enough."
    if reason == "battery_charge_target":
        return f"Raising to {target}: battery is charging above the configured reserve."
    if reason == "deadband_hold":
        return f"Holding {target}: grid import/export is inside the deadband."
    if reason == "waiting_stable_surplus":
        remaining = state.start_delay_remaining or 0
        return f"Waiting {remaining}s: surplus must stay stable before increasing."
    if reason == "autolimit_low_surplus":
        return "Waiting: Prism autolimit is active and grid import is still too high."
    if reason == "autolimit_recovery_6a":
        return "Trying 6A recovery: Prism autolimit cleared inside the deadband."
    if reason == "external_pause":
        return "Paused by Prism or app: the integration will not resume automatically."
    if reason == "ramp_up_wait":
        return f"Holding {target}: waiting for the next allowed ramp-up interval."
    if reason in ("ramp_up_limited", "ramp_down_limited"):
        return f"Moving to {target}: ramp limit is smoothing the current change."
    if state.status == SOLAR_BALANCE_CHARGING_SURPLUS:
        return f"Charging at {target}: surplus is available ({available})."
    if state.status == SOLAR_BALANCE_DISABLED:
        return "Solar balancing is disabled."
    if state.status == SOLAR_BALANCE_WAITING_DATA:
        return "Waiting for required sensor data."
    return f"Decision: {reason or state.status}."


def get_solar_balance_signal(serial: str, port: int) -> str:
    """Return the dispatcher signal for one Prism solar balance port."""
    return f"{DOMAIN}_solar_balance_{serial}_{port}"
