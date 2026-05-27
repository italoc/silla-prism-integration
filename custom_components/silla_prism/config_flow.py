"""Silla Prism for Home Assistant."""

import asyncio
import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant.components import mqtt
from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.helpers import config_validation as cv, selector

from .const import (
    CONF_BATTERY_DISCHARGE_POSITIVE,
    CONF_BATTERY_MAX_CHARGE_POWER,
    CONF_BATTERY_POWER_SENSOR,
    CONF_BATTERY_SOC_SENSOR,
    CONF_HOME_LOAD_POWER_SENSOR,
    CONF_SOLAR_PRODUCTION_POWER_SENSOR,
    CONF_MAX_CURRENT,
    CONF_PORTS,
    CONF_POWERWALL,
    CONF_SERIAL,
    CONF_SOLAR_BALANCE_PHASES,
    CONF_SOLAR_BALANCE_START_DELAY,
    CONF_SOLAR_BALANCE_USE_BATTERY_CHARGE,
    CONF_SOLAR_BALANCE_SOC_MID,
    CONF_SOLAR_BALANCE_SOC_HIGH,
    CONF_SOLAR_BALANCE_MID_RESERVE_POWER,
    CONF_SOLAR_BALANCE_HIGH_RESERVE_POWER,
    CONF_SOLAR_BALANCE_TARGET_EXPORT_POWER,
    CONF_SOLAR_BALANCE_DEADBAND_POWER,
    CONF_SOLAR_BALANCE_INCREASE_INTERVAL,
    CONF_SOLAR_BALANCE_INCREASE_STEP,
    CONF_SOLAR_BALANCE_DECREASE_STEP,
    CONF_SOLAR_BALANCE_RESIDUAL_EXPORT_POWER,
    CONF_SOLAR_BALANCE_RESIDUAL_EXPORT_DELAY,
    CONF_SOLAR_BATTERY_BALANCE,
    CONF_TOPIC,
    CONF_VSENSORS,
    DEFAULT_BATTERY_DISCHARGE_POSITIVE,
    DEFAULT_BATTERY_MAX_CHARGE_POWER,
    DEFAULT_BATTERY_POWER_SENSOR,
    DEFAULT_BATTERY_SOC_SENSOR,
    DEFAULT_HOME_LOAD_POWER_SENSOR,
    DEFAULT_SOLAR_PRODUCTION_POWER_SENSOR,
    DEFAULT_MAX_CURRENT,
    DEFAULT_PORTS,
    DEFAULT_POWERWALL,
    DEFAULT_SERIAL,
    DEFAULT_SOLAR_BALANCE_PHASES,
    DEFAULT_SOLAR_BALANCE_START_DELAY,
    DEFAULT_SOLAR_BALANCE_USE_BATTERY_CHARGE,
    DEFAULT_SOLAR_BALANCE_SOC_MID,
    DEFAULT_SOLAR_BALANCE_SOC_HIGH,
    DEFAULT_SOLAR_BALANCE_MID_RESERVE_POWER,
    DEFAULT_SOLAR_BALANCE_HIGH_RESERVE_POWER,
    DEFAULT_SOLAR_BALANCE_TARGET_EXPORT_POWER,
    DEFAULT_SOLAR_BALANCE_DEADBAND_POWER,
    DEFAULT_SOLAR_BALANCE_INCREASE_INTERVAL,
    DEFAULT_SOLAR_BALANCE_INCREASE_STEP,
    DEFAULT_SOLAR_BALANCE_DECREASE_STEP,
    DEFAULT_SOLAR_BALANCE_RESIDUAL_EXPORT_POWER,
    DEFAULT_SOLAR_BALANCE_RESIDUAL_EXPORT_DELAY,
    DEFAULT_SOLAR_BATTERY_BALANCE,
    DEFAULT_TOPIC,
    DEFAULT_VSENSORS,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

BATTERY_SENSOR_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor")
)

SILLA_PRISM_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TOPIC, default=DEFAULT_TOPIC): cv.string,
        vol.Required(CONF_PORTS, default=DEFAULT_PORTS): cv.positive_int,
        vol.Optional(CONF_SERIAL, default=DEFAULT_SERIAL): cv.string,
        vol.Optional(CONF_VSENSORS, default=DEFAULT_VSENSORS): cv.boolean,
        vol.Optional(CONF_POWERWALL, default=DEFAULT_POWERWALL): cv.boolean,
        vol.Optional(CONF_MAX_CURRENT, default=DEFAULT_MAX_CURRENT): cv.positive_int,
        vol.Optional(
            CONF_SOLAR_BATTERY_BALANCE, default=DEFAULT_SOLAR_BATTERY_BALANCE
        ): cv.boolean,
        vol.Optional(
            CONF_BATTERY_POWER_SENSOR, default=DEFAULT_BATTERY_POWER_SENSOR
        ): BATTERY_SENSOR_SELECTOR,
        vol.Optional(
            CONF_SOLAR_PRODUCTION_POWER_SENSOR,
            default=DEFAULT_SOLAR_PRODUCTION_POWER_SENSOR,
        ): BATTERY_SENSOR_SELECTOR,
        vol.Optional(
            CONF_HOME_LOAD_POWER_SENSOR, default=DEFAULT_HOME_LOAD_POWER_SENSOR
        ): BATTERY_SENSOR_SELECTOR,
        vol.Optional(
            CONF_BATTERY_SOC_SENSOR, default=DEFAULT_BATTERY_SOC_SENSOR
        ): BATTERY_SENSOR_SELECTOR,
        vol.Optional(
            CONF_BATTERY_DISCHARGE_POSITIVE,
            default=DEFAULT_BATTERY_DISCHARGE_POSITIVE,
        ): cv.boolean,
        vol.Optional(
            CONF_BATTERY_MAX_CHARGE_POWER, default=DEFAULT_BATTERY_MAX_CHARGE_POWER
        ): cv.positive_int,
        vol.Optional(
            CONF_SOLAR_BALANCE_PHASES, default=DEFAULT_SOLAR_BALANCE_PHASES
        ): vol.In([1, 3]),
        vol.Optional(
            CONF_SOLAR_BALANCE_START_DELAY,
            default=DEFAULT_SOLAR_BALANCE_START_DELAY,
        ): vol.All(vol.Coerce(int), vol.Range(min=0, max=60)),
        vol.Optional(
            CONF_SOLAR_BALANCE_USE_BATTERY_CHARGE,
            default=DEFAULT_SOLAR_BALANCE_USE_BATTERY_CHARGE,
        ): cv.boolean,
        vol.Optional(
            CONF_SOLAR_BALANCE_SOC_MID, default=DEFAULT_SOLAR_BALANCE_SOC_MID
        ): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
        vol.Optional(
            CONF_SOLAR_BALANCE_SOC_HIGH, default=DEFAULT_SOLAR_BALANCE_SOC_HIGH
        ): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
        vol.Optional(
            CONF_SOLAR_BALANCE_MID_RESERVE_POWER,
            default=DEFAULT_SOLAR_BALANCE_MID_RESERVE_POWER,
        ): vol.All(vol.Coerce(int), vol.Range(min=0)),
        vol.Optional(
            CONF_SOLAR_BALANCE_HIGH_RESERVE_POWER,
            default=DEFAULT_SOLAR_BALANCE_HIGH_RESERVE_POWER,
        ): vol.All(vol.Coerce(int), vol.Range(min=0)),
        vol.Optional(
            CONF_SOLAR_BALANCE_TARGET_EXPORT_POWER,
            default=DEFAULT_SOLAR_BALANCE_TARGET_EXPORT_POWER,
        ): vol.All(vol.Coerce(int), vol.Range(min=0)),
        vol.Optional(
            CONF_SOLAR_BALANCE_DEADBAND_POWER,
            default=DEFAULT_SOLAR_BALANCE_DEADBAND_POWER,
        ): vol.All(vol.Coerce(int), vol.Range(min=0)),
        vol.Optional(
            CONF_SOLAR_BALANCE_INCREASE_INTERVAL,
            default=DEFAULT_SOLAR_BALANCE_INCREASE_INTERVAL,
        ): vol.All(vol.Coerce(int), vol.Range(min=0, max=300)),
        vol.Optional(
            CONF_SOLAR_BALANCE_INCREASE_STEP,
            default=DEFAULT_SOLAR_BALANCE_INCREASE_STEP,
        ): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
        vol.Optional(
            CONF_SOLAR_BALANCE_DECREASE_STEP,
            default=DEFAULT_SOLAR_BALANCE_DECREASE_STEP,
        ): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
        vol.Optional(
            CONF_SOLAR_BALANCE_RESIDUAL_EXPORT_POWER,
            default=DEFAULT_SOLAR_BALANCE_RESIDUAL_EXPORT_POWER,
        ): vol.All(vol.Coerce(int), vol.Range(min=0)),
        vol.Optional(
            CONF_SOLAR_BALANCE_RESIDUAL_EXPORT_DELAY,
            default=DEFAULT_SOLAR_BALANCE_RESIDUAL_EXPORT_DELAY,
        ): vol.All(vol.Coerce(int), vol.Range(min=0, max=600)),
    }
)


class SillaPrismConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a Silla Prism config flow."""

    VERSION = 1
    MINOR_VERSION = 9

    def __init__(self) -> None:
        """Initialize flow."""
        self._topic: str | None = DEFAULT_TOPIC
        self._ports: int = DEFAULT_PORTS
        self._vsensors: bool = DEFAULT_VSENSORS
        self._powerwall: bool = DEFAULT_POWERWALL
        self._serial: str = DEFAULT_SERIAL
        self._max_current: int = DEFAULT_MAX_CURRENT
        self._solar_battery_balance: bool = DEFAULT_SOLAR_BATTERY_BALANCE
        self._battery_power_sensor: str = DEFAULT_BATTERY_POWER_SENSOR
        self._solar_production_power_sensor: str = (
            DEFAULT_SOLAR_PRODUCTION_POWER_SENSOR
        )
        self._home_load_power_sensor: str = DEFAULT_HOME_LOAD_POWER_SENSOR
        self._battery_discharge_positive: bool = DEFAULT_BATTERY_DISCHARGE_POSITIVE
        self._battery_max_charge_power: int = DEFAULT_BATTERY_MAX_CHARGE_POWER
        self._solar_balance_phases: int = DEFAULT_SOLAR_BALANCE_PHASES
        self._solar_balance_start_delay: int = DEFAULT_SOLAR_BALANCE_START_DELAY
        self._solar_balance_use_battery_charge: bool = (
            DEFAULT_SOLAR_BALANCE_USE_BATTERY_CHARGE
        )
        self._battery_soc_sensor: str = DEFAULT_BATTERY_SOC_SENSOR
        self._solar_balance_soc_mid: int = DEFAULT_SOLAR_BALANCE_SOC_MID
        self._solar_balance_soc_high: int = DEFAULT_SOLAR_BALANCE_SOC_HIGH
        self._solar_balance_mid_reserve_power: int = (
            DEFAULT_SOLAR_BALANCE_MID_RESERVE_POWER
        )
        self._solar_balance_high_reserve_power: int = (
            DEFAULT_SOLAR_BALANCE_HIGH_RESERVE_POWER
        )
        self._solar_balance_target_export_power: int = (
            DEFAULT_SOLAR_BALANCE_TARGET_EXPORT_POWER
        )
        self._solar_balance_deadband_power: int = DEFAULT_SOLAR_BALANCE_DEADBAND_POWER
        self._solar_balance_increase_interval: int = (
            DEFAULT_SOLAR_BALANCE_INCREASE_INTERVAL
        )
        self._solar_balance_increase_step: int = DEFAULT_SOLAR_BALANCE_INCREASE_STEP
        self._solar_balance_decrease_step: int = DEFAULT_SOLAR_BALANCE_DECREASE_STEP
        self._solar_balance_residual_export_power: int = (
            DEFAULT_SOLAR_BALANCE_RESIDUAL_EXPORT_POWER
        )
        self._solar_balance_residual_export_delay: int = (
            DEFAULT_SOLAR_BALANCE_RESIDUAL_EXPORT_DELAY
        )

    async def fetch_device_info(self) -> str | None:
        """Fetech information from MQTT."""
        assert self._topic is not None
        error = None
        event = asyncio.Event()

        async def message_received(msg):
            """Handle new messages on MQTT."""
            _LOGGER.debug("New intent: %s", msg.payload)
            event.set()

        topic1 = self._topic + "0/info/temperature/core"
        _LOGGER.debug("Subscribing test topic1: %s", topic1)
        unsub_topic1 = await mqtt.async_subscribe(self.hass, topic1, message_received)

        topic2 = self._topic + "energy_data/power_grid"
        _LOGGER.debug("Subscribing test topic2: %s", topic2)
        unsub_topic2 = await mqtt.async_subscribe(self.hass, topic2, message_received)

        topic3 = self._topic + "hello"
        _LOGGER.debug("Subscribing test topic3: %s", topic3)
        unsub_topic3 = await mqtt.async_subscribe(self.hass, topic3, message_received)

        try:
            await asyncio.wait_for(event.wait(), 5)
        except TimeoutError:
            error = "Timeout expired"

        unsub_topic1()
        unsub_topic2()
        unsub_topic3()
        return error

    async def _async_validate_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        _LOGGER.debug("Called with user input: %s source: %s", user_input, self.source)

        if self.source == SOURCE_RECONFIGURE:
            entry = self._get_reconfigure_entry()
            self._ports = entry.data.get(CONF_PORTS, DEFAULT_PORTS)
            self._serial = entry.data.get(CONF_SERIAL, DEFAULT_SERIAL)
            self._vsensors = entry.data.get(CONF_VSENSORS, DEFAULT_VSENSORS)
            self._powerwall = entry.data.get(CONF_POWERWALL, DEFAULT_POWERWALL)
        else:
            self._ports = user_input[CONF_PORTS]
            self._serial = re.sub(r"[^a-zA-Z0-9]", "", user_input[CONF_SERIAL])
            self._vsensors = user_input[CONF_VSENSORS]
            self._powerwall = user_input[CONF_POWERWALL]

        self._topic = user_input[CONF_TOPIC]
        self._max_current = max(
            min(user_input[CONF_MAX_CURRENT], 32), 6
        )  # clamp between 6 and 32
        self._solar_battery_balance = user_input.get(
            CONF_SOLAR_BATTERY_BALANCE, DEFAULT_SOLAR_BATTERY_BALANCE
        )
        self._battery_power_sensor = user_input.get(
            CONF_BATTERY_POWER_SENSOR, DEFAULT_BATTERY_POWER_SENSOR
        ).strip()
        self._solar_production_power_sensor = user_input.get(
            CONF_SOLAR_PRODUCTION_POWER_SENSOR,
            DEFAULT_SOLAR_PRODUCTION_POWER_SENSOR,
        ).strip()
        self._home_load_power_sensor = user_input.get(
            CONF_HOME_LOAD_POWER_SENSOR, DEFAULT_HOME_LOAD_POWER_SENSOR
        ).strip()
        self._battery_soc_sensor = user_input.get(
            CONF_BATTERY_SOC_SENSOR, DEFAULT_BATTERY_SOC_SENSOR
        ).strip()
        self._battery_discharge_positive = user_input.get(
            CONF_BATTERY_DISCHARGE_POSITIVE, DEFAULT_BATTERY_DISCHARGE_POSITIVE
        )
        self._battery_max_charge_power = user_input.get(
            CONF_BATTERY_MAX_CHARGE_POWER, DEFAULT_BATTERY_MAX_CHARGE_POWER
        )
        self._solar_balance_phases = user_input.get(
            CONF_SOLAR_BALANCE_PHASES, DEFAULT_SOLAR_BALANCE_PHASES
        )
        self._solar_balance_start_delay = user_input.get(
            CONF_SOLAR_BALANCE_START_DELAY, DEFAULT_SOLAR_BALANCE_START_DELAY
        )
        self._solar_balance_use_battery_charge = user_input.get(
            CONF_SOLAR_BALANCE_USE_BATTERY_CHARGE,
            DEFAULT_SOLAR_BALANCE_USE_BATTERY_CHARGE,
        )
        self._solar_balance_soc_mid = user_input.get(
            CONF_SOLAR_BALANCE_SOC_MID, DEFAULT_SOLAR_BALANCE_SOC_MID
        )
        self._solar_balance_soc_high = user_input.get(
            CONF_SOLAR_BALANCE_SOC_HIGH, DEFAULT_SOLAR_BALANCE_SOC_HIGH
        )
        self._solar_balance_mid_reserve_power = user_input.get(
            CONF_SOLAR_BALANCE_MID_RESERVE_POWER,
            DEFAULT_SOLAR_BALANCE_MID_RESERVE_POWER,
        )
        self._solar_balance_high_reserve_power = user_input.get(
            CONF_SOLAR_BALANCE_HIGH_RESERVE_POWER,
            DEFAULT_SOLAR_BALANCE_HIGH_RESERVE_POWER,
        )
        self._solar_balance_target_export_power = user_input.get(
            CONF_SOLAR_BALANCE_TARGET_EXPORT_POWER,
            DEFAULT_SOLAR_BALANCE_TARGET_EXPORT_POWER,
        )
        self._solar_balance_deadband_power = user_input.get(
            CONF_SOLAR_BALANCE_DEADBAND_POWER,
            DEFAULT_SOLAR_BALANCE_DEADBAND_POWER,
        )
        self._solar_balance_increase_interval = user_input.get(
            CONF_SOLAR_BALANCE_INCREASE_INTERVAL,
            DEFAULT_SOLAR_BALANCE_INCREASE_INTERVAL,
        )
        self._solar_balance_increase_step = user_input.get(
            CONF_SOLAR_BALANCE_INCREASE_STEP,
            DEFAULT_SOLAR_BALANCE_INCREASE_STEP,
        )
        self._solar_balance_decrease_step = user_input.get(
            CONF_SOLAR_BALANCE_DECREASE_STEP,
            DEFAULT_SOLAR_BALANCE_DECREASE_STEP,
        )
        self._solar_balance_residual_export_power = user_input.get(
            CONF_SOLAR_BALANCE_RESIDUAL_EXPORT_POWER,
            DEFAULT_SOLAR_BALANCE_RESIDUAL_EXPORT_POWER,
        )
        self._solar_balance_residual_export_delay = user_input.get(
            CONF_SOLAR_BALANCE_RESIDUAL_EXPORT_DELAY,
            DEFAULT_SOLAR_BALANCE_RESIDUAL_EXPORT_DELAY,
        )
        if self._solar_balance_soc_mid > self._solar_balance_soc_high:
            (
                self._solar_balance_soc_mid,
                self._solar_balance_soc_high,
            ) = (
                self._solar_balance_soc_high,
                self._solar_balance_soc_mid,
            )

        if self._solar_battery_balance and self._battery_power_sensor == "":
            return await self._async_step_user_base(error="battery_sensor_required")
        if (
            self._solar_battery_balance
            and self._home_load_power_sensor != ""
            and self._solar_production_power_sensor == ""
        ):
            return await self._async_step_user_base(error="solar_sensor_required")

        return await self._async_try_fetch_device_info()

    async def _async_step_user_base(
        self, user_input: dict[str, Any] | None = None, error: str | None = None
    ) -> ConfigFlowResult:
        _LOGGER.info("Async_step_user %s", DOMAIN)
        if user_input is not None:
            return await self._async_validate_device(user_input)

        errors = {}
        if error is not None:
            errors["base"] = error

        if self.source == SOURCE_RECONFIGURE:
            # We are reconfiguring an existing device
            entry = self._get_reconfigure_entry()
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(
                            CONF_TOPIC, default=entry.data[CONF_TOPIC]
                        ): cv.string,
                        vol.Optional(
                            CONF_MAX_CURRENT,
                            default=entry.data.get(
                                CONF_MAX_CURRENT, DEFAULT_MAX_CURRENT
                            ),
                        ): cv.positive_int,
                        vol.Optional(
                            CONF_SOLAR_BATTERY_BALANCE,
                            default=entry.data.get(
                                CONF_SOLAR_BATTERY_BALANCE,
                                DEFAULT_SOLAR_BATTERY_BALANCE,
                            ),
                        ): cv.boolean,
                        vol.Optional(
                            CONF_BATTERY_POWER_SENSOR,
                            default=entry.data.get(
                                CONF_BATTERY_POWER_SENSOR,
                                DEFAULT_BATTERY_POWER_SENSOR,
                            ),
                        ): BATTERY_SENSOR_SELECTOR,
                        vol.Optional(
                            CONF_SOLAR_PRODUCTION_POWER_SENSOR,
                            default=entry.data.get(
                                CONF_SOLAR_PRODUCTION_POWER_SENSOR,
                                DEFAULT_SOLAR_PRODUCTION_POWER_SENSOR,
                            ),
                        ): BATTERY_SENSOR_SELECTOR,
                        vol.Optional(
                            CONF_HOME_LOAD_POWER_SENSOR,
                            default=entry.data.get(
                                CONF_HOME_LOAD_POWER_SENSOR,
                                DEFAULT_HOME_LOAD_POWER_SENSOR,
                            ),
                        ): BATTERY_SENSOR_SELECTOR,
                        vol.Optional(
                            CONF_BATTERY_SOC_SENSOR,
                            default=entry.data.get(
                                CONF_BATTERY_SOC_SENSOR,
                                DEFAULT_BATTERY_SOC_SENSOR,
                            ),
                        ): BATTERY_SENSOR_SELECTOR,
                        vol.Optional(
                            CONF_BATTERY_DISCHARGE_POSITIVE,
                            default=entry.data.get(
                                CONF_BATTERY_DISCHARGE_POSITIVE,
                                DEFAULT_BATTERY_DISCHARGE_POSITIVE,
                            ),
                        ): cv.boolean,
                        vol.Optional(
                            CONF_BATTERY_MAX_CHARGE_POWER,
                            default=entry.data.get(
                                CONF_BATTERY_MAX_CHARGE_POWER,
                                DEFAULT_BATTERY_MAX_CHARGE_POWER,
                            ),
                        ): cv.positive_int,
                        vol.Optional(
                            CONF_SOLAR_BALANCE_PHASES,
                            default=entry.data.get(
                                CONF_SOLAR_BALANCE_PHASES,
                                DEFAULT_SOLAR_BALANCE_PHASES,
                            ),
                        ): vol.In([1, 3]),
                        vol.Optional(
                            CONF_SOLAR_BALANCE_START_DELAY,
                            default=entry.data.get(
                                CONF_SOLAR_BALANCE_START_DELAY,
                                DEFAULT_SOLAR_BALANCE_START_DELAY,
                            ),
                        ): vol.All(vol.Coerce(int), vol.Range(min=0, max=60)),
                        vol.Optional(
                            CONF_SOLAR_BALANCE_USE_BATTERY_CHARGE,
                            default=entry.data.get(
                                CONF_SOLAR_BALANCE_USE_BATTERY_CHARGE,
                                DEFAULT_SOLAR_BALANCE_USE_BATTERY_CHARGE,
                            ),
                        ): cv.boolean,
                        vol.Optional(
                            CONF_SOLAR_BALANCE_SOC_MID,
                            default=entry.data.get(
                                CONF_SOLAR_BALANCE_SOC_MID,
                                DEFAULT_SOLAR_BALANCE_SOC_MID,
                            ),
                        ): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
                        vol.Optional(
                            CONF_SOLAR_BALANCE_SOC_HIGH,
                            default=entry.data.get(
                                CONF_SOLAR_BALANCE_SOC_HIGH,
                                DEFAULT_SOLAR_BALANCE_SOC_HIGH,
                            ),
                        ): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
                        vol.Optional(
                            CONF_SOLAR_BALANCE_MID_RESERVE_POWER,
                            default=entry.data.get(
                                CONF_SOLAR_BALANCE_MID_RESERVE_POWER,
                                DEFAULT_SOLAR_BALANCE_MID_RESERVE_POWER,
                            ),
                        ): vol.All(vol.Coerce(int), vol.Range(min=0)),
                        vol.Optional(
                            CONF_SOLAR_BALANCE_HIGH_RESERVE_POWER,
                            default=entry.data.get(
                                CONF_SOLAR_BALANCE_HIGH_RESERVE_POWER,
                                DEFAULT_SOLAR_BALANCE_HIGH_RESERVE_POWER,
                            ),
                        ): vol.All(vol.Coerce(int), vol.Range(min=0)),
                        vol.Optional(
                            CONF_SOLAR_BALANCE_TARGET_EXPORT_POWER,
                            default=entry.data.get(
                                CONF_SOLAR_BALANCE_TARGET_EXPORT_POWER,
                                DEFAULT_SOLAR_BALANCE_TARGET_EXPORT_POWER,
                            ),
                        ): vol.All(vol.Coerce(int), vol.Range(min=0)),
                        vol.Optional(
                            CONF_SOLAR_BALANCE_DEADBAND_POWER,
                            default=entry.data.get(
                                CONF_SOLAR_BALANCE_DEADBAND_POWER,
                                DEFAULT_SOLAR_BALANCE_DEADBAND_POWER,
                            ),
                        ): vol.All(vol.Coerce(int), vol.Range(min=0)),
                        vol.Optional(
                            CONF_SOLAR_BALANCE_INCREASE_INTERVAL,
                            default=entry.data.get(
                                CONF_SOLAR_BALANCE_INCREASE_INTERVAL,
                                DEFAULT_SOLAR_BALANCE_INCREASE_INTERVAL,
                            ),
                        ): vol.All(vol.Coerce(int), vol.Range(min=0, max=300)),
                        vol.Optional(
                            CONF_SOLAR_BALANCE_INCREASE_STEP,
                            default=entry.data.get(
                                CONF_SOLAR_BALANCE_INCREASE_STEP,
                                DEFAULT_SOLAR_BALANCE_INCREASE_STEP,
                            ),
                        ): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
                        vol.Optional(
                            CONF_SOLAR_BALANCE_DECREASE_STEP,
                            default=entry.data.get(
                                CONF_SOLAR_BALANCE_DECREASE_STEP,
                                DEFAULT_SOLAR_BALANCE_DECREASE_STEP,
                            ),
                        ): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
                        vol.Optional(
                            CONF_SOLAR_BALANCE_RESIDUAL_EXPORT_POWER,
                            default=entry.data.get(
                                CONF_SOLAR_BALANCE_RESIDUAL_EXPORT_POWER,
                                DEFAULT_SOLAR_BALANCE_RESIDUAL_EXPORT_POWER,
                            ),
                        ): vol.All(vol.Coerce(int), vol.Range(min=0)),
                        vol.Optional(
                            CONF_SOLAR_BALANCE_RESIDUAL_EXPORT_DELAY,
                            default=entry.data.get(
                                CONF_SOLAR_BALANCE_RESIDUAL_EXPORT_DELAY,
                                DEFAULT_SOLAR_BALANCE_RESIDUAL_EXPORT_DELAY,
                            ),
                        ): vol.All(vol.Coerce(int), vol.Range(min=0, max=600)),
                    }
                ),
                errors=errors,
            )
        # We are creating a new device
        return self.async_show_form(
            step_id="user",
            data_schema=SILLA_PRISM_SCHEMA,
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a reconfiguration flow initialized by the user."""
        if user_input is not None:
            return await self._async_validate_device(user_input)

        return await self._async_step_user_base()

    async def _async_try_fetch_device_info(self) -> ConfigFlowResult:
        """Try to fetch device info and return any errors."""
        error = None

        # Make sure MQTT integration is enabled and the client is available
        if not await mqtt.async_wait_for_mqtt_client(self.hass):
            error = "MQTT integration is not available"
            _LOGGER.error(error)

        if error is None:
            error = await self.fetch_device_info()

        if error is None:
            if self.source == SOURCE_RECONFIGURE:
                return await self._async_update_entry()
            return await self._async_create_entry()

        if self.source == SOURCE_RECONFIGURE:
            return await self.async_step_reconfigure()
        return await self._async_step_user_base(error=error)

    async def _async_create_entry(self) -> ConfigFlowResult:
        config_data = {
            CONF_TOPIC: self._topic,
            CONF_PORTS: self._ports,
            CONF_SERIAL: self._serial,
            CONF_VSENSORS: self._vsensors,
            CONF_POWERWALL: self._powerwall,
            CONF_MAX_CURRENT: self._max_current,
            CONF_SOLAR_BATTERY_BALANCE: self._solar_battery_balance,
            CONF_BATTERY_POWER_SENSOR: self._battery_power_sensor,
            CONF_SOLAR_PRODUCTION_POWER_SENSOR: self._solar_production_power_sensor,
            CONF_HOME_LOAD_POWER_SENSOR: self._home_load_power_sensor,
            CONF_BATTERY_SOC_SENSOR: self._battery_soc_sensor,
            CONF_BATTERY_DISCHARGE_POSITIVE: self._battery_discharge_positive,
            CONF_BATTERY_MAX_CHARGE_POWER: self._battery_max_charge_power,
            CONF_SOLAR_BALANCE_PHASES: self._solar_balance_phases,
            CONF_SOLAR_BALANCE_START_DELAY: self._solar_balance_start_delay,
            CONF_SOLAR_BALANCE_USE_BATTERY_CHARGE: (
                self._solar_balance_use_battery_charge
            ),
            CONF_SOLAR_BALANCE_SOC_MID: self._solar_balance_soc_mid,
            CONF_SOLAR_BALANCE_SOC_HIGH: self._solar_balance_soc_high,
            CONF_SOLAR_BALANCE_MID_RESERVE_POWER: (
                self._solar_balance_mid_reserve_power
            ),
            CONF_SOLAR_BALANCE_HIGH_RESERVE_POWER: (
                self._solar_balance_high_reserve_power
            ),
            CONF_SOLAR_BALANCE_TARGET_EXPORT_POWER: (
                self._solar_balance_target_export_power
            ),
            CONF_SOLAR_BALANCE_DEADBAND_POWER: self._solar_balance_deadband_power,
            CONF_SOLAR_BALANCE_INCREASE_INTERVAL: (
                self._solar_balance_increase_interval
            ),
            CONF_SOLAR_BALANCE_INCREASE_STEP: self._solar_balance_increase_step,
            CONF_SOLAR_BALANCE_DECREASE_STEP: self._solar_balance_decrease_step,
            CONF_SOLAR_BALANCE_RESIDUAL_EXPORT_POWER: (
                self._solar_balance_residual_export_power
            ),
            CONF_SOLAR_BALANCE_RESIDUAL_EXPORT_DELAY: (
                self._solar_balance_residual_export_delay
            ),
        }
        return self.async_create_entry(
            title="SillaPrism",
            data=config_data,
        )

    async def _async_update_entry(self) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()

        config_data = {
            CONF_TOPIC: self._topic,
            CONF_PORTS: entry.data.get(CONF_PORTS, DEFAULT_PORTS),
            CONF_SERIAL: entry.data.get(CONF_SERIAL, DEFAULT_SERIAL),
            CONF_VSENSORS: entry.data.get(CONF_VSENSORS, DEFAULT_VSENSORS),
            CONF_POWERWALL: entry.data.get(CONF_POWERWALL, DEFAULT_POWERWALL),
            CONF_MAX_CURRENT: self._max_current,
            CONF_SOLAR_BATTERY_BALANCE: self._solar_battery_balance,
            CONF_BATTERY_POWER_SENSOR: self._battery_power_sensor,
            CONF_SOLAR_PRODUCTION_POWER_SENSOR: self._solar_production_power_sensor,
            CONF_HOME_LOAD_POWER_SENSOR: self._home_load_power_sensor,
            CONF_BATTERY_SOC_SENSOR: self._battery_soc_sensor,
            CONF_BATTERY_DISCHARGE_POSITIVE: self._battery_discharge_positive,
            CONF_BATTERY_MAX_CHARGE_POWER: self._battery_max_charge_power,
            CONF_SOLAR_BALANCE_PHASES: self._solar_balance_phases,
            CONF_SOLAR_BALANCE_START_DELAY: self._solar_balance_start_delay,
            CONF_SOLAR_BALANCE_USE_BATTERY_CHARGE: (
                self._solar_balance_use_battery_charge
            ),
            CONF_SOLAR_BALANCE_SOC_MID: self._solar_balance_soc_mid,
            CONF_SOLAR_BALANCE_SOC_HIGH: self._solar_balance_soc_high,
            CONF_SOLAR_BALANCE_MID_RESERVE_POWER: (
                self._solar_balance_mid_reserve_power
            ),
            CONF_SOLAR_BALANCE_HIGH_RESERVE_POWER: (
                self._solar_balance_high_reserve_power
            ),
            CONF_SOLAR_BALANCE_TARGET_EXPORT_POWER: (
                self._solar_balance_target_export_power
            ),
            CONF_SOLAR_BALANCE_DEADBAND_POWER: self._solar_balance_deadband_power,
            CONF_SOLAR_BALANCE_INCREASE_INTERVAL: (
                self._solar_balance_increase_interval
            ),
            CONF_SOLAR_BALANCE_INCREASE_STEP: self._solar_balance_increase_step,
            CONF_SOLAR_BALANCE_DECREASE_STEP: self._solar_balance_decrease_step,
            CONF_SOLAR_BALANCE_RESIDUAL_EXPORT_POWER: (
                self._solar_balance_residual_export_power
            ),
            CONF_SOLAR_BALANCE_RESIDUAL_EXPORT_DELAY: (
                self._solar_balance_residual_export_delay
            ),
        }
        return self.async_update_reload_and_abort(
            self._get_reconfigure_entry(),
            data_updates=config_data,
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        _LOGGER.info("Async_step_user %s", DOMAIN)
        return await self._async_step_user_base(user_input=user_input)
