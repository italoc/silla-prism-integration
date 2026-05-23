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
        self._margin = entry_data.solar_balance_margin
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
        self._last_current_command: int | None = None
        self._last_current_increase: datetime | None = None
        self._last_mode_command: str | None = None
        self._charging_from_surplus = False
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
                    f"{self._base_topic}{self._port}/volt",
                    self._mqtt_grid_voltage_received,
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
    def _mqtt_grid_voltage_received(self, msg) -> None:
        self._grid_voltage = self._parse_state(msg.payload)
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
        target_power = available_power - self._margin - self._target_export_power
        min_power = MIN_CHARGE_CURRENT * voltage * self._phases
        already_charging = self._is_charging_from_surplus(min_power)

        if target_power < min_power:
            self._reset_start_delay()
            self._reset_residual_export()
            if already_charging:
                self._charging_from_surplus = True
                self._update_solar_balance_state(
                    SOLAR_BALANCE_CHARGING_SURPLUS,
                    MIN_CHARGE_CURRENT,
                    available_power,
                    target_power,
                    0,
                    battery_power,
                    battery_charge_power,
                    battery_discharge_power,
                    battery_power_to_exclude,
                    battery_reserve_power,
                    target_current=MIN_CHARGE_CURRENT,
                    decision_reason=SOLAR_BALANCE_CHARGING_SURPLUS,
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
                target_current=0,
                decision_reason="paused_low_surplus",
            )
            await self._async_publish_current(MIN_CHARGE_CURRENT)
            await self._async_publish_mode(MODE_PAUSED)
            return

        target_current = floor(target_power / (voltage * self._phases))
        target_current = max(MIN_CHARGE_CURRENT, min(target_current, self._max_current))
        target_current = self._apply_current_optimizations(target_current)
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
                target_current=preview_current,
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
            target_current=target_current,
            decision_reason="charging_surplus",
        )
        await self._async_publish_current(target_current)
        await self._async_publish_mode(MODE_SOLAR)
        self._charging_from_surplus = True

    def _is_charging_from_surplus(self, min_power: float) -> bool:
        """Return True when Prism appears to be actively charging already."""
        return self._charging_from_surplus or self._ev_power >= min_power * 0.5

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

    def _apply_current_optimizations(self, target_current: int) -> int:
        """Apply hysteresis, ramp limits and residual export recovery."""
        last_current = self._last_current_command
        if last_current is None:
            self._track_residual_export()
            return target_current

        grid_error = self._grid_power + self._target_export_power
        if abs(grid_error) <= self._deadband_power:
            self._reset_residual_export()
            return last_current

        target_current = self._apply_residual_export_recovery(target_current)

        if target_current > last_current:
            return self._limit_current_increase(target_current, last_current)
        if target_current < last_current:
            self._reset_residual_export()
            return max(target_current, last_current - self._decrease_step)
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
            return recovered_current
        return target_current

    def _track_residual_export(self) -> bool:
        if self._residual_export_power <= 0:
            return False

        grid_error = self._grid_power + self._target_export_power
        excess_export = max(-grid_error - self._deadband_power, 0)
        if excess_export < self._residual_export_power:
            self._reset_residual_export()
            return False

        if self._residual_export_delay <= 0:
            return True

        now = datetime.now(timezone.utc)
        if self._residual_export_since is None:
            self._residual_export_since = now
            return False

        elapsed = (now - self._residual_export_since).total_seconds()
        return elapsed >= self._residual_export_delay

    def _limit_current_increase(self, target_current: int, last_current: int) -> int:
        if self._increase_interval <= 0:
            self._last_current_increase = datetime.now(timezone.utc)
            return min(target_current, last_current + self._increase_step)

        now = datetime.now(timezone.utc)
        if self._last_current_increase is not None:
            elapsed = (now - self._last_current_increase).total_seconds()
            if elapsed < self._increase_interval:
                return last_current

        self._last_current_increase = now
        return min(target_current, last_current + self._increase_step)

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
        target_current: float | None = None,
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
            target_current=target_current,
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
        if self._last_mode_command == mode:
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
