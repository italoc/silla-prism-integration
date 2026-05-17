"""Shared state for Prism solar battery balancing."""

from __future__ import annotations

from dataclasses import dataclass

from .const import DOMAIN

SOLAR_BALANCE_DISABLED = "disabled"
SOLAR_BALANCE_WAITING_DATA = "waiting_data"
SOLAR_BALANCE_WAITING_STABLE_SURPLUS = "waiting_stable_surplus"
SOLAR_BALANCE_PAUSED_LOW_SURPLUS = "paused_low_surplus"
SOLAR_BALANCE_CHARGING_SURPLUS = "charging_surplus"


@dataclass(slots=True)
class SolarBalanceState:
    """Store the latest solar balance calculation for one port."""

    status: str = SOLAR_BALANCE_WAITING_DATA
    surplus_current: float | None = None
    available_power: float | None = None
    target_power: float | None = None
    start_delay_remaining: int | None = None
    grid_power: float | None = None
    ev_power: float | None = None
    battery_power: float | None = None
    battery_charge_power: float | None = None
    battery_discharge_power: float | None = None
    battery_power_used: float | None = None
    battery_max_charge_power: float | None = None
    battery_soc: float | None = None
    battery_reserve_power: float | None = None
    target_current: float | None = None
    decision_reason: str | None = None


def get_solar_balance_signal(serial: str, port: int) -> str:
    """Return the dispatcher signal for one Prism solar balance port."""
    return f"{DOMAIN}_solar_balance_{serial}_{port}"
