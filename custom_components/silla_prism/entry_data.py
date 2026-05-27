"""Runtime entry data for Silla Prism stored in hass.data."""

from dataclasses import dataclass, field

from homeassistant.helpers.device_registry import DeviceInfo

from .solar_balance import SolarBalanceState


@dataclass(slots=True)
class RuntimeEntryData:
    """Store runtime data for esphome config entries."""

    topic: str
    ports: int
    vsensors: bool
    powerwall: bool
    serial: str
    maxcurr: int
    solar_battery_balance: bool
    battery_power_sensor: str
    solar_production_power_sensor: str
    home_load_power_sensor: str
    battery_soc_sensor: str
    battery_discharge_positive: bool
    battery_max_charge_power: int
    solar_balance_phases: int
    solar_balance_start_delay: int
    solar_balance_use_battery_charge: bool
    solar_balance_soc_mid: int
    solar_balance_soc_high: int
    solar_balance_mid_reserve_power: int
    solar_balance_high_reserve_power: int
    solar_balance_target_export_power: int
    solar_balance_deadband_power: int
    solar_balance_increase_interval: int
    solar_balance_increase_step: int
    solar_balance_decrease_step: int
    solar_balance_residual_export_power: int
    solar_balance_residual_export_delay: int
    devices: list[DeviceInfo]
    solar_balance_states: dict[int, SolarBalanceState] = field(default_factory=dict)
