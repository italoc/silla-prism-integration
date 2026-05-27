"""Switches for Prism wallbox integration."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from math import floor
import logging

from homeassistant.components import mqtt
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity

from .domain_data import DomainData
from .entity import _get_unique_id
from .entry_data import RuntimeEntryData
from .solar_balance import (
    SOLAR_BALANCE_CHARGING_SURPLUS,
    SOLAR_BALANCE_DISABLED,
    SOLAR_BALANCE_LOW_SURPLUS_KEEP_CHARGING,
    SOLAR_BALANCE_PAUSED_LOW_SURPLUS,
    SOLAR_BALANCE_WAITING_STABLE_SURPLUS,
    SOLAR_BALANCE_WAITING_DATA,
    SolarBalanceState,
    get_solar_balance_signal,
)

_LOGGER = logging.getLogger(__name__)

MIN_CHARGE_CURRENT = 6
DEFAULT_GRID_VOLTAGE = 230.0
MODE_SOLAR = "1"
MODE_NORMAL = "2"
MODE_PAUSED = "3"
MODE_AUTOLIMIT = "7"
AUTOLIMIT_RECOVERY_COOLDOWN = 300


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add switch entities for passed config_entry in HA."""
    entry_data: RuntimeEntryData = DomainData.get(hass).get_entry_data(entry)

    if not entry_data.solar_battery_balance:
        return

    switches = [
        PrismSolarBatteryBalance(entry_data, description, port)
        for port in range(1, entry_data.ports + 1)
        for description in SWITCHES
    ]
    async_add_entities(switches)


class PrismSwitchEntityDescription(SwitchEntityDescription, frozen_or_thawed=True):
    """A class that describes Prism switch entities."""


class PrismSolarBatteryBalance(SwitchEntity, RestoreEntity):
    """Balance EV charging against PV surplus and battery power."""

    entity_description: PrismSwitchEntityDescription
    _attr_should_poll = False

    def __init__(
        self,
        entry_data: RuntimeEntryData,
        description: PrismSwitchEntityDescription,
        port: int,
    ) -> None:
        """Initialize the solar battery balance switch."""
        self._port = port
        self._entry_data = entry_data
        self._base_topic = entry_data.topic
        self._battery_sensor = entry_data.battery_power_sensor
        self._battery_soc_sensor = entry_data.battery_soc_sensor
        self._battery_discharge_positive = entry_data.battery_discharge_positive
        self._battery_max_charge_power = entry_data.battery_max_charge_power
        self._phases = entry_data.solar_balance_phases
        self._start_delay_seconds = entry_data.solar_balance_start_delay * 60
        self._use_battery_charge = entry_data.solar_balance_use_battery_charge
        self._soc_mid = entry_data.solar_balance_soc_mid
        self._soc_high = entry_data.solar_balance_soc_high
        self._mid_reserve_power = entry_data.solar_balance_mid_reserve_power
        self._high_reserve_power = entry_data.solar_balance_high_reserve_power
        self._target_export_power = entry_data.solar_balance_target_export_power
        self._deadband_power = entry_data.solar_balance_deadband_power
        self._increase_interval = entry_data.solar_balance_increase_interval
        self._increase_step = entry_data.solar_balance_increase_step
        self._decrease_step = entry_data.solar_balance_decrease_step
        self._residual_export_power = entry_data.solar_balance_residual_export_power
        self._residual_export_delay = entry_data.solar_balance_residual_export_delay
        self._max_current = entry_data.maxcurr
        self._attr_device_info = self._get_device(entry_data, port)
        self.entity_description = self._get_description(
            port, entry_data.ports > 1, description
        )
        self._attr_unique_id = _get_unique_id(
            entry_data.serial, self.entity_description.key
        )
        self._attr_is_on = True

        self._grid_power: float | None = None
        self._ev_power: float | None = None
        self._grid_voltage: float | None = None
        self._battery_power: float | None = None
        self._battery_soc: float | None = None
        self._reported_current_limit: int | None = None
        self._last_current_command: int | None = None
        self._last_current_increase: datetime | None = None
        self._last_mode_command: str | None = None
        self._reported_mode: str | None = None
        self._raw_target_current: int | None = None
        self._unused_export_power: float = 0
        self._excess_import_power: float = 0
        self._residual_export_remaining: int = 0
        self._deadband_active = False
        self._ramp_limited = False
        self._ramp_direction = "none"
        self._current_limit_reason = "waiting_data"
        self._charging_from_surplus = False
        self._last_autolimit_recovery: datetime | None = None
        self._surplus_since: datetime | None = None
        self._residual_export_since: datetime | None = None
        self._start_delay_trigger: CALLBACK_TYPE | None = None
        self._unsubs: list[Callable[[], None]] = []

    def _get_description(
        self,
        port: int,
        multiport: bool,
        description: PrismSwitchEntityDescription,
    ) -> PrismSwitchEntityDescription:
        if multiport:
            key = description.key.format(port)
        else:
            key = description.key[:-3]
        return PrismSwitchEntityDescription(
            key=key,
            entity_category=description.entity_category,
            has_entity_name=description.has_entity_name,
            translation_key=description.translation_key,
        )

    def _get_device(self, entry_data: RuntimeEntryData, port: int) -> DeviceInfo:
        if entry_data.ports > 1:
            return entry_data.devices[port]
        return entry_data.devices[0]

    async def async_added_to_hass(self) -> None:
        """Restore state, subscribe to MQTT, and track the battery sensor."""
        if state := await self.async_get_last_state():
            self._attr_is_on = state.state == "on"

        self._unsubs.extend(
            [
                await mqtt.async_subscribe(
                    self.hass,
                    f"{self._base_topic}energy_data/power_grid",
                    self._mqtt_grid_power_received,
                ),
                await mqtt.async_subscribe(
                    self.hass,
                    f"{self._base_topic}{self._port}/w",
                    self._mqtt_ev_power_received,
                ),
                await mqtt.async_subscribe(
                    self.hass,
                    f"{self._base_topic}{self._port}/pilot",
                    self._mqtt_current_limit_received,
                ),
                await mqtt.async_subscribe(
                    self.hass,
                    f"{self._base_topic}{self._port}/volt",
                    self._mqtt_grid_voltage_received,
                ),
                await mqtt.async_subscribe(
                    self.hass,
                    f"{self._base_topic}{self._port}/mode",
                    self._mqtt_mode_received,
                ),
            ]
        )
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._battery_sensor, self._battery_power_received
            )
        )
        if self._battery_soc_sensor:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, self._battery_soc_sensor, self._battery_soc_received
                )
            )

        if battery_state := self.hass.states.get(self._battery_sensor):
            self._battery_power = self._parse_state(battery_state.state)
        if self._battery_soc_sensor and (
            battery_soc_state := self.hass.states.get(self._battery_soc_sensor)
        ):
            self._battery_soc = self._parse_state(battery_soc_state.state)
        await self._async_update_balance()

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe from MQTT topics."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        self._cancel_start_delay()
        await super().async_will_remove_from_hass()

    async def async_turn_on(self, **kwargs) -> None:
        """Enable solar battery balancing."""
        self._attr_is_on = True
        self.async_write_ha_state()
        await self._async_update_balance()

    async def async_turn_off(self, **kwargs) -> None:
        """Disable solar battery balancing."""
        self._attr_is_on = False
        self.async_write_ha_state()
        self._reset_start_delay()
        self._reset_residual_export()
        self._charging_from_surplus = False
        self._update_solar_balance_state(
            SOLAR_BALANCE_DISABLED,
            0,
            None,
            None,
            None,
            decision_reason="disabled",
        )
        await self._async_publish_mode(MODE_NORMAL)

    @callback
    def _mqtt_grid_power_received(self, msg) -> None:
        self._grid_power = self._parse_state(msg.payload)
        self.hass.async_create_task(self._async_update_balance())

    @callback
    def _battery_soc_received(self, event: Event[EventStateChangedData]) -> None:
        new_state = event.data["new_state"]
        if new_state is None or new_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            self._battery_soc = None
        else:
            self._battery_soc = self._parse_state(new_state.state)
        self.hass.async_create_task(self._async_update_balance())

    @callback
    def _mqtt_ev_power_received(self, msg) -> None:
        self._ev_power = self._parse_state(msg.payload)
        self.hass.async_create_task(self._async_update_balance())

    @callback
    def _mqtt_current_limit_received(self, msg) -> None:
        current_limit = self._parse_state(msg.payload)
        self._reported_current_limit = (
            None if current_limit is None else int(current_limit)
        )
        self.hass.async_create_task(self._async_update_balance())

    @callback
    def _mqtt_grid_voltage_received(self, msg) -> None:
        self._grid_voltage = self._parse_state(msg.payload)
        self.hass.async_create_task(self._async_update_balance())

    @callback
    def _mqtt_mode_received(self, msg) -> None:
        self._reported_mode = str(msg.payload)
        self.hass.async_create_task(self._async_update_balance())

    @callback
    def _battery_power_received(self, event: Event[EventStateChangedData]) -> None:
        new_state = event.data["new_state"]
        if new_state is None or new_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            self._battery_power = None
        else:
            self._battery_power = self._parse_state(new_state.state)
        self.hass.async_create_task(self._async_update_balance())

    def _parse_state(self, value: str) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            _LOGGER.debug(
                "Invalid solar balance value for %s: %s",
                self.entity_description.key,
                value,
            )
            return None

    async def _async_update_balance(self) -> None:
        if not self.is_on:
            self._reset_start_delay()
            self._reset_residual_export()
            self._charging_from_surplus = False
            self._update_solar_balance_state(
                SOLAR_BALANCE_DISABLED,
                0,
                None,
                None,
                None,
                decision_reason="disabled",
            )
            return

        if not self._has_required_values:
            self._reset_start_delay()
            self._reset_residual_export()
            self._charging_from_surplus = False
            self._update_solar_balance_state(
                SOLAR_BALANCE_WAITING_DATA,
                None,
                None,
                None,
                None,
                decision_reason="waiting_data",
            )
            return

        battery_power = self._battery_power
        if not self._battery_discharge_positive:
            battery_power = -battery_power

        voltage = self._grid_voltage or DEFAULT_GRID_VOLTAGE
        battery_charge_power = max(-battery_power, 0)
        battery_discharge_power = max(battery_power, 0)
        battery_reserve_power = self._get_battery_reserve_power()
        battery_charge_available = max(
            battery_charge_power - battery_reserve_power, 0
        )
        battery_power_to_exclude = battery_discharge_power - (
            battery_charge_available if self._use_battery_charge else 0
        )
        available_power = self._ev_power - self._grid_power - battery_power_to_exclude
        target_power = available_power - self._target_export_power
        min_power = MIN_CHARGE_CURRENT * voltage * self._phases
        watts_per_amp = voltage * self._phases
        already_charging = self._is_charging_from_surplus(min_power)
        self._reset_current_diagnostics()

        if target_power < min_power:
            self._reset_start_delay()
            self._reset_residual_export()
            if self._reported_mode == MODE_AUTOLIMIT:
                if self._can_recover_from_autolimit():
                    self._charging_from_surplus = True
                    self._last_autolimit_recovery = datetime.now(timezone.utc)
                    self._update_solar_balance_state(
                        SOLAR_BALANCE_LOW_SURPLUS_KEEP_CHARGING,
                        MIN_CHARGE_CURRENT,
                        available_power,
                        target_power,
                        0,
                        battery_power,
                        battery_charge_power,
                        battery_discharge_power,
                        battery_power_to_exclude,
                        battery_reserve_power,
                        raw_target_current=MIN_CHARGE_CURRENT,
                        target_current=MIN_CHARGE_CURRENT,
                        current_limit_reason="autolimit_recovery_6a",
                        decision_reason=SOLAR_BALANCE_LOW_SURPLUS_KEEP_CHARGING,
                    )
                    await self._async_publish_current(MIN_CHARGE_CURRENT)
                    await self._async_publish_mode(MODE_SOLAR)
                    return

                self._charging_from_surplus = False
                self._update_solar_balance_state(
                    SOLAR_BALANCE_PAUSED_LOW_SURPLUS,
                    0,
                    available_power,
                    target_power,
                    None,
                    battery_power,
                    battery_charge_power,
                    battery_discharge_power,
                    battery_power_to_exclude,
                    battery_reserve_power,
                    raw_target_current=0,
                    target_current=0,
                    current_limit_reason="autolimit_low_surplus",
                    decision_reason=SOLAR_BALANCE_PAUSED_LOW_SURPLUS,
                )
                return

            self._charging_from_surplus = True
            manual_current = self._get_manual_current_override()
            target_current = manual_current or MIN_CHARGE_CURRENT
            current_limit_reason = (
                "manual_current_override"
                if manual_current is not None
                else "low_surplus_hold_6a"
            )
            self._update_solar_balance_state(
                SOLAR_BALANCE_LOW_SURPLUS_KEEP_CHARGING,
                target_current,
                available_power,
                target_power,
                0,
                battery_power,
                battery_charge_power,
                battery_discharge_power,
                battery_power_to_exclude,
                battery_reserve_power,
                raw_target_current=MIN_CHARGE_CURRENT,
                target_current=target_current,
                current_limit_reason=current_limit_reason,
                decision_reason=SOLAR_BALANCE_LOW_SURPLUS_KEEP_CHARGING,
            )
            if manual_current is None:
                await self._async_publish_current(MIN_CHARGE_CURRENT)
            await self._async_publish_mode(MODE_SOLAR)
            return

        target_current = floor(target_power / (voltage * self._phases))
        target_current = max(MIN_CHARGE_CURRENT, min(target_current, self._max_current))
        self._raw_target_current = target_current
        target_current = self._apply_current_optimizations(
            target_current, watts_per_amp
        )
        delay_remaining = self._get_start_delay_remaining()
        if delay_remaining > 0 and not already_charging:
            preview_current = (
                MIN_CHARGE_CURRENT if self._use_battery_charge else target_current
            )
            self._update_solar_balance_state(
                SOLAR_BALANCE_WAITING_STABLE_SURPLUS,
                preview_current,
                available_power,
                min_power if self._use_battery_charge else target_power,
                delay_remaining,
                battery_power,
                battery_charge_power,
                battery_discharge_power,
                battery_power_to_exclude,
                battery_reserve_power,
                raw_target_current=self._raw_target_current,
                target_current=preview_current,
                current_limit_reason="waiting_stable_surplus",
                decision_reason="waiting_stable_surplus",
            )
            await self._async_publish_current(MIN_CHARGE_CURRENT)
            self._schedule_start_delay(delay_remaining)
            return

        self._cancel_start_delay()
        self._update_solar_balance_state(
            SOLAR_BALANCE_CHARGING_SURPLUS,
            target_current,
            available_power,
            target_power,
            0,
            battery_power,
            battery_charge_power,
            battery_discharge_power,
            battery_power_to_exclude,
            battery_reserve_power,
            raw_target_current=self._raw_target_current,
            target_current=target_current,
            current_limit_reason=self._current_limit_reason,
            decision_reason="charging_surplus",
        )
        await self._async_publish_current(target_current)
        await self._async_publish_mode(MODE_SOLAR)
        self._charging_from_surplus = True

    def _is_charging_from_surplus(self, min_power: float) -> bool:
        """Return True when Prism appears to be actively charging already."""
        return self._charging_from_surplus or self._ev_power >= min_power * 0.5

    def _can_recover_from_autolimit(self) -> bool:
        """Return True when autolimit can be probed without command loops."""
        if self._grid_power is None:
            return False

        if self._grid_power > self._deadband_power:
            return False

        if self._last_autolimit_recovery is None:
            return True

        elapsed = (
            datetime.now(timezone.utc) - self._last_autolimit_recovery
        ).total_seconds()
        return elapsed >= AUTOLIMIT_RECOVERY_COOLDOWN

    def _get_manual_current_override(self) -> int | None:
        """Return the reported current if it appears to be a manual override."""
        if (
            self._reported_current_limit is None
            or self._last_current_command is None
            or self._reported_current_limit == self._last_current_command
            or self._reported_current_limit < MIN_CHARGE_CURRENT
        ):
            return None
        return min(self._reported_current_limit, self._max_current)

    def _get_battery_reserve_power(self) -> float:
        """Return how much battery charge power should be reserved for home storage."""
        if self._battery_soc is None:
            return self._battery_max_charge_power
        if self._battery_soc >= 95:
            return 0
        if self._battery_soc >= self._soc_high:
            return self._high_reserve_power
        if self._battery_soc >= self._soc_mid:
            return self._mid_reserve_power
        return self._battery_max_charge_power

    def _apply_current_optimizations(
        self, target_current: int, watts_per_amp: float
    ) -> int:
        """Apply hysteresis, proportional correction and ramp limits."""
        last_current = self._last_current_command
        if last_current is None:
            self._track_grid_error()
            self._track_residual_export()
            self._current_limit_reason = "initial_target"
            return target_current

        self._track_grid_error()
        if self._deadband_active:
            self._reset_residual_export()
            self._current_limit_reason = "deadband_hold"
            return last_current

        target_current = self._apply_residual_export_recovery(target_current)

        if target_current > last_current:
            return self._limit_current_increase(
                target_current, last_current, watts_per_amp
            )
        if target_current < last_current:
            self._reset_residual_export()
            self._ramp_direction = "down"
            step = self._get_proportional_decrease_step(watts_per_amp)
            limited_current = max(target_current, last_current - step)
            self._ramp_limited = limited_current != target_current
            self._current_limit_reason = (
                "ramp_down_limited" if self._ramp_limited else "target_current"
            )
            return limited_current
        self._current_limit_reason = "target_current"
        return target_current

    def _apply_residual_export_recovery(self, target_current: int) -> int:
        if self._last_current_command is None:
            return target_current
        if not self._track_residual_export():
            return target_current

        recovered_current = min(
            self._max_current,
            self._last_current_command + self._increase_step,
        )
        if recovered_current > target_current:
            self._reset_residual_export()
            self._current_limit_reason = "residual_export_recovery"
            return recovered_current
        return target_current

    def _track_grid_error(self) -> None:
        grid_error = self._grid_power + self._target_export_power
        self._deadband_active = abs(grid_error) <= self._deadband_power
        self._unused_export_power = max(-grid_error - self._deadband_power, 0)
        self._excess_import_power = max(grid_error - self._deadband_power, 0)

    def _track_residual_export(self) -> bool:
        if self._residual_export_power <= 0:
            self._residual_export_remaining = 0
            return False

        if self._unused_export_power < self._residual_export_power:
            self._reset_residual_export()
            return False

        if self._residual_export_delay <= 0:
            self._residual_export_remaining = 0
            return True

        now = datetime.now(timezone.utc)
        if self._residual_export_since is None:
            self._residual_export_since = now
            self._residual_export_remaining = self._residual_export_delay
            return False

        elapsed = (now - self._residual_export_since).total_seconds()
        self._residual_export_remaining = max(
            self._residual_export_delay - int(elapsed), 0
        )
        return elapsed >= self._residual_export_delay

    def _limit_current_increase(
        self, target_current: int, last_current: int, watts_per_amp: float
    ) -> int:
        self._ramp_direction = "up"
        step = self._get_proportional_increase_step(watts_per_amp)
        if self._increase_interval <= 0:
            self._last_current_increase = datetime.now(timezone.utc)
            limited_current = min(target_current, last_current + step)
            self._ramp_limited = limited_current != target_current
            self._current_limit_reason = (
                "ramp_up_limited" if self._ramp_limited else "target_current"
            )
            return limited_current

        now = datetime.now(timezone.utc)
        if self._last_current_increase is not None:
            elapsed = (now - self._last_current_increase).total_seconds()
            if elapsed < self._increase_interval:
                self._ramp_limited = True
                self._current_limit_reason = "ramp_up_wait"
                return last_current

        self._last_current_increase = now
        limited_current = min(target_current, last_current + step)
        self._ramp_limited = limited_current != target_current
        self._current_limit_reason = (
            "ramp_up_limited" if self._ramp_limited else "target_current"
        )
        return limited_current

    def _get_proportional_increase_step(self, watts_per_amp: float) -> int:
        if watts_per_amp <= 0:
            return self._increase_step
        proportional_step = int(self._unused_export_power // watts_per_amp)
        return max(self._increase_step, min(proportional_step, self._decrease_step))

    def _get_proportional_decrease_step(self, watts_per_amp: float) -> int:
        if watts_per_amp <= 0:
            return self._decrease_step
        proportional_step = int(self._excess_import_power // watts_per_amp) + 1
        return max(self._decrease_step, proportional_step)

    def _get_start_delay_remaining(self) -> int:
        if self._start_delay_seconds <= 0:
            return 0

        now = datetime.now(timezone.utc)
        if self._surplus_since is None:
            self._surplus_since = now
            return self._start_delay_seconds

        elapsed = int((now - self._surplus_since).total_seconds())
        return max(self._start_delay_seconds - elapsed, 0)

    def _schedule_start_delay(self, delay_remaining: int) -> None:
        if self._start_delay_trigger is not None:
            return
        self._start_delay_trigger = async_call_later(
            self.hass, min(delay_remaining, 1), self._start_delay_elapsed
        )

    @callback
    def _start_delay_elapsed(self, *_: datetime) -> None:
        self._start_delay_trigger = None
        self.hass.async_create_task(self._async_update_balance())

    def _reset_start_delay(self) -> None:
        self._surplus_since = None
        self._cancel_start_delay()

    def _reset_residual_export(self) -> None:
        self._residual_export_since = None
        self._residual_export_remaining = 0

    def _reset_current_diagnostics(self) -> None:
        self._raw_target_current = None
        self._unused_export_power = 0
        self._excess_import_power = 0
        self._residual_export_remaining = 0
        self._deadband_active = False
        self._ramp_limited = False
        self._ramp_direction = "none"
        self._current_limit_reason = "target_current"

    def _cancel_start_delay(self) -> None:
        if self._start_delay_trigger is not None:
            self._start_delay_trigger()
            self._start_delay_trigger = None

    def _update_solar_balance_state(
        self,
        status: str,
        surplus_current: float | None,
        available_power: float | None,
        target_power: float | None,
        start_delay_remaining: int | None,
        battery_power: float | None = None,
        battery_charge_power: float | None = None,
        battery_discharge_power: float | None = None,
        battery_power_used: float | None = None,
        battery_reserve_power: float | None = None,
        raw_target_current: float | None = None,
        target_current: float | None = None,
        current_limit_reason: str | None = None,
        decision_reason: str | None = None,
    ) -> None:
        state = SolarBalanceState(
            status=status,
            surplus_current=surplus_current,
            available_power=available_power,
            target_power=target_power,
            start_delay_remaining=start_delay_remaining,
            grid_power=self._grid_power,
            ev_power=self._ev_power,
            battery_power=battery_power,
            battery_charge_power=battery_charge_power,
            battery_discharge_power=battery_discharge_power,
            battery_power_used=battery_power_used,
            battery_max_charge_power=self._battery_max_charge_power,
            battery_soc=self._battery_soc,
            battery_reserve_power=battery_reserve_power,
            target_export_power=self._target_export_power,
            deadband_power=self._deadband_power,
            raw_target_current=raw_target_current,
            target_current=target_current,
            unused_export_power=self._unused_export_power,
            excess_import_power=self._excess_import_power,
            residual_export_remaining=self._residual_export_remaining,
            deadband_active=self._deadband_active,
            ramp_limited=self._ramp_limited,
            ramp_direction=self._ramp_direction,
            current_limit_reason=current_limit_reason,
            decision_reason=decision_reason,
        )
        self._entry_data.solar_balance_states[self._port] = state
        async_dispatcher_send(
            self.hass,
            get_solar_balance_signal(self._entry_data.serial, self._port),
            state,
        )

    @property
    def _has_required_values(self) -> bool:
        return (
            self._grid_power is not None
            and self._ev_power is not None
            and self._battery_power is not None
        )

    async def _async_publish_current(self, current: int) -> None:
        if self._last_current_command == current:
            return
        self._last_current_command = current
        await mqtt.async_publish(
            self.hass,
            f"{self._base_topic}{self._port}/command/set_current_limit",
            current,
        )

    async def _async_publish_mode(self, mode: str) -> None:
        if self._last_mode_command == mode and self._reported_mode in (None, mode):
            return
        self._last_mode_command = mode
        await mqtt.async_publish(
            self.hass,
            f"{self._base_topic}{self._port}/command/set_mode",
            mode,
        )


SWITCHES: tuple[PrismSwitchEntityDescription, ...] = (
    PrismSwitchEntityDescription(
        key="solar_battery_balance_{}",
        entity_category=EntityCategory.CONFIG,
        has_entity_name=True,
        translation_key="solar_battery_balance",
    ),
)
