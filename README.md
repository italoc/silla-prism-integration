# Silla Prism Solar custom integration

![Silla Prism Solar](image.png)

Custom Home Assistant integration for Silla Prism EVSE devices, based on MQTT.
This fork keeps the original Prism MQTT integration and adds solar charging
logic that can balance EV charging with photovoltaic production, house load and
home-battery priority.

> **Beta notice:** the solar balancing features actively change Prism current
> limit and operating mode through MQTT. Test with conservative limits before
> relying on it unattended.

## Table Of Contents

- [Main Features](#main-features)
- [Installation](#installation)
- [Basic Setup](#basic-setup)
- [Solar Balancing Setup](#solar-balancing-setup)
- [Recommended Sensor Setup](#recommended-sensor-setup)
- [Balancer Overview](#balancer-overview)
- [How Solar Balancing Works](#how-solar-balancing-works)
- [Battery Priority](#battery-priority)
- [Stabilization And Safety](#stabilization-and-safety)
- [Solar Balancing Options](#solar-balancing-options)
- [Diagnostic Sensors](#diagnostic-sensors)
- [Prism Entities](#prism-entities)
- [Testing](#testing)
- [Troubleshooting And Releases](#troubleshooting-and-releases)

## Main Features

- Silla Prism MQTT entities for state, power, current, energy, mode and touch
  gestures.
- Optional `Solar battery balancing` switch for each charging port.
- EV current control from Prism data, configured Home Assistant sensors and
  user-defined safety limits.
- Direct surplus calculation from external solar production and house load
  sensors.
- Optional correction for house-load sensors that include the EV charger.
- Home-battery priority based on battery power and optional SOC.
- Configurable export buffer, deadband, start delay, ramp-up, ramp-down and
  residual export recovery.
- Autolimit-aware recovery and explicit pause handling, so the integration does
  not fight wallbox protection states or user/app pauses.
- Pause diagnostics continue to calculate the theoretical target current without
  sending commands to the wallbox.
- Diagnostic sensors that explain the latest balancing decision.

## Installation

Prerequisites:

- A working MQTT broker.
- Home Assistant MQTT integration configured and connected to the same broker.
- Prism MQTT enabled on the wallbox.

Steps:

1. Configure the Prism EVSE to use your MQTT broker. See the
   [Prism MQTT manual](https://support.silla.industries/wp-content/uploads/2023/09/DOC-Prism_MQTT_Manual-rel.2.0_rev.-20220105-EN.pdf).
2. Install this repository with HACS as a custom repository, or copy
   `custom_components/silla_prism` into your Home Assistant
   `custom_components` directory.
3. Restart Home Assistant.
4. Add the Silla Prism integration from the Home Assistant dashboard.

[![Open your Home Assistant instance and start setting up a new integration of a specific brand.](https://my.home-assistant.io/badges/brand.svg)](https://my.home-assistant.io/redirect/brand/?brand=silla_prism)

## Basic Setup

First configure Prism MQTT in the Silla app and keep the same base topic in
Home Assistant.

<img alt="Prism custom MQTT setup" src="images/setup-mqtt-custom.png" width="420">

During integration setup:

| Field | What to enter |
| ----- | ------------- |
| Topic | Prism MQTT base topic. It must match the Prism app value and keep the trailing `/`. |
| Number of ports | Use `1` for a single-port Prism, or the actual number for multi-port models. |
| Serial number / unique code | Optional for a single Prism; useful when more than one Prism is connected. |
| Enable virtual sensor | Adds derived entities, such as total grid energy. |
| Max current | Upper current limit the integration is allowed to request. |

## Solar Balancing Setup

The setup/reconfigure form includes the solar balancing options. The most
important rule is simple: if possible, configure real external sensors for solar
production and house load. The integration intentionally does not rely on Prism
`energy_data/power_solar` and `energy_data/power_house` for balancing because
they can remain at `0` on some installations.

<img alt="Silla Prism configuration connection and battery sensors" src="images/config-solar-battery-1-connection.png" width="480">

Select:

- `Battery power sensor`: home battery charge/discharge power in W.
- `Solar production power sensor`: real PV production in W.
- `Home load power sensor`: house load in W.
- `Home load sensor includes EV charger`: enable it when the house load sensor
  is a total-load sensor that also includes the wallbox/EV charger.
- `Home battery SOC sensor`: optional battery state of charge in %.

<img alt="Silla Prism configuration battery priority and charging phases" src="images/config-solar-battery-2-battery-priority.png" width="480">

Set the low-SOC battery reserve, charging phases, stable surplus delay, and
whether battery charge power above the reserve can be used as EV surplus.

<img alt="Silla Prism configuration SOC reserves and ramp settings" src="images/config-solar-battery-3-reserves-ramp.png" width="480">

Set the SOC thresholds, medium/high battery reserves, target grid export,
deadband and current increase interval.

<img alt="Silla Prism configuration current steps and residual export recovery" src="images/config-solar-battery-4-export-recovery.png" width="480">

Set how quickly current can rise or fall, and when persistent unused export
should recover one more amp.

## Recommended Sensor Setup

| Sensor | Required | Notes |
| ------ | -------- | ----- |
| Solar production | Recommended | Real PV production in W. Required for the direct solar-minus-house formula. |
| Home load | Recommended | House load in W. Configure whether it includes the EV charger. |
| Battery power | Required for balancing | Positive/negative sign can be configured. Internally, positive means discharge and negative means charge. |
| Battery SOC | Optional | Enables dynamic battery reserve based on SOC thresholds. |

If the home load sensor includes the EV charger, enable the matching option.
The controller will subtract live Prism EV output power before calculating
surplus. Without this correction, increasing EV current also increases the house
load used by the formula, making the available surplus look too low.

## Balancer Overview

The following overview is exported from draw.io and summarizes the main energy
signals, controller steps and wallbox protection states.

<img alt="Silla Prism solar balancer overview" src="images/solar-balancer-overview.png" width="760">

The editable draw.io source is available at
[`images/solar-balancer-overview.drawio`](images/solar-balancer-overview.drawio).

## How Solar Balancing Works

The controller tries to send only usable solar surplus to the EV while keeping a
configurable safety buffer for the home battery and avoiding unwanted grid
import. It writes Prism MQTT commands for current limit and solar mode, but it
does not override wallbox pauses or active autolimit protection.

With solar production and home load sensors configured, the preferred formula
is:

```text
effective_home_load = home_load
if home_load_includes_ev:
    effective_home_load = max(home_load - ev_power, 0)

available_power = solar_production - effective_home_load

if use_battery_charge and available_power > 0:
    available_power += max(battery_charge_power - battery_reserve_power, 0)

target_power = available_power - target_grid_export
```

The external solar production sensor must be positive when PV is producing.
Negative production values are treated as `0 W` so an inverted sensor cannot
create false surplus.

Without both external solar production and external home load sensors, the
fallback estimator is:

```text
available_power = ev_power - grid_power - battery_power_to_exclude
target_power = available_power - target_grid_export
```

The controller then converts power into current:

```text
watts_per_amp = grid_voltage * phases
target_current = floor(target_power / watts_per_amp)
```

The final current is clamped between the Type 2 minimum of `6A` and the
configured maximum current.

## Battery Priority

The battery reserve is the amount of charge power the controller tries to leave
for the home battery before giving the rest to the EV.

With a SOC sensor:

| Battery SOC | Reserve used |
| ----------- | ------------ |
| Below medium SOC | Maximum battery charge power |
| At or above medium SOC | Medium SOC battery reserve |
| At or above high SOC | High SOC battery reserve |
| At or above 95% | `0 W` |

When `Use battery charge as surplus` is enabled, the reserve is also treated as
an approximate maximum battery charge target. If the battery is still charging
above that target and grid import is not excessive, EV current can rise
gradually to bring battery charging back toward the configured reserve. The
result is approximate because Prism current changes in whole amps.

## Stabilization And Safety

To avoid loops and oscillation, the controller applies several guards:

| Mechanism | Purpose |
| --------- | ------- |
| Target export | Keeps a small export buffer before giving power to the EV. |
| Deadband | Leaves current unchanged near the target export. |
| Stable surplus delay | Waits before starting or raising from idle/low-surplus conditions. |
| Increase interval and step | Raises current gradually. |
| Decrease step | Drops current faster when house loads appear. |
| Residual export recovery | Adds current when export remains unused long enough. |

Low surplus is handled without stopping solar charging: if target power is below
the Type 2 minimum, Prism is kept in solar mode at `6A`. To force a manual value
inside the balancer, set `Solar balance manual current` to `6A` or higher. Set it
back to `0` to return to automatic control. `Current limit` remains a direct
Prism command and is not treated as a solar-balancer override. The live Prism
`pilot` value is also not treated as a manual override because it follows the
current requested by the car. If there is persistent real grid export, residual
export recovery can raise current above `6A` after the configured delay.

Autolimit and pause are intentionally different:

- `autolimit`: treated as wallbox protection. The integration does not force
  solar mode while grid import is above the deadband. When import returns inside
  the deadband, residual export must stay stable before one `6A` recovery
  attempt is made. Another attempt is blocked for 5 minutes.
- `paused`: treated as a deliberate wallbox/app pause, for example a charge
  limit reached. The integration keeps diagnostics updated, including the
  theoretical current it would request, but does not resume charging
  automatically.

## Solar Balancing Options

| Option | Description |
| ------ | ----------- |
| Enable solar battery balancing | Creates the balancing switch. |
| Battery power sensor | Home Assistant entity that reports battery charge/discharge power in W. |
| Solar production power sensor | Home Assistant entity that reports real PV production in W. |
| Home load power sensor | Home Assistant entity that reports house load in W. |
| Home load sensor includes EV charger | Subtracts live Prism EV output power from the house load before calculating surplus. |
| Home battery SOC sensor | Optional entity that reports home battery state of charge in %. |
| Battery discharge is a positive value | Enable if the battery sensor is positive while discharging and negative while charging. |
| Maximum battery charge power | Battery charge power reserved while SOC is low. Default is `2700 W`. |
| Number of charging phases | Use `1` for single phase or `3` for three phase charging. |
| Stable surplus delay | Minutes of continuous surplus required before current can rise from idle/low surplus. Default is `5`. |
| Use battery charge as surplus | Lets battery charge power above the reserve become available EV surplus. |
| Medium home battery SOC | SOC threshold where the reserve drops to the medium value. Default is `40%`. |
| High home battery SOC | SOC threshold where the reserve drops to the high value. Default is `80%`. |
| Medium SOC battery reserve | Approximate maximum battery charge power kept at medium SOC. Default is `1500 W`. |
| High SOC battery reserve | Approximate maximum battery charge power kept at high SOC. Default is `1000 W`. |
| Target grid export | Watts intentionally kept exported as a safety buffer. Default is `150 W`. |
| Import/export deadband | Watts around the target export where current is left unchanged. Default is `150 W`. |
| Minimum current increase interval | Minimum seconds between upward current steps. Default is `15`. |
| Maximum current increase step | Maximum amp increase per ramp step. Default is `1A`. |
| Maximum current decrease step | Maximum amp decrease per correction. Default is `3A`. |
| Residual export for current recovery | Extra export required before adding current beyond the rounded calculation. Default is `400 W`. |
| Residual export time before recovery | Seconds residual export must stay above threshold before recovery. Default is `60`. |

## Manual Current Override

`Solar balance manual current` is a dedicated number for the balancing algorithm:

- `0`: automatic balancing; the controller decides current.
- `6A` or higher: the balancer keeps that current during low-surplus solar
  charging instead of publishing its own calculated low-surplus value.

Use `Current limit` only when you want to send a direct current command to Prism.
Changing `Current limit` or receiving a new Prism `pilot` value does not enable
the solar balance manual override.

When the controller requests one current but Prism still reports a different
`pilot` value, `Decision summary` reports the mismatch explicitly. This separates
the current requested by the balancer from the limit currently reported by Prism
and from the real delivered current.

## Diagnostic Sensors

When solar balancing is enabled, the integration exposes diagnostic entities for
each port. For a single-port Prism the entity IDs normally use the names below;
on multi-port devices Home Assistant adds the port number.

| Entity ID | Entity | Description |
| --------- | ------ | ----------- |
| `silla_prism_solar_balance_status` | Solar balance status | Current balancing state: disabled, waiting for data, wallbox paused, waiting for stable surplus, low-surplus hold or charging from surplus. |
| `silla_prism_solar_balance_surplus_current` | Solar surplus current | Current in amps available from the calculated surplus. |
| `silla_prism_solar_balance_start_countdown` | Stable surplus countdown | Seconds remaining before the integration can start or raise current from a waiting/low-surplus state. |
| `silla_prism_solar_balance_available_power` | Calculated total surplus | Total power available to the balancing algorithm. |
| `silla_prism_solar_balance_battery_power_used` | Battery power used in calculation | Battery contribution used by the algorithm. |
| `silla_prism_solar_balance_grid_power` | Grid power used in calculation | Latest Prism grid power used by the algorithm. |
| `silla_prism_solar_balance_solar_power` | Solar production used in calculation | Latest configured solar production sensor value used by the algorithm. |
| `silla_prism_solar_balance_home_load_power` | Home load used in calculation | Latest house load value used by the algorithm, corrected for EV power when configured. |
| `silla_prism_solar_balance_target_current` | Calculated target current | Final current after deadband, ramp and recovery limits. |
| `silla_prism_solar_balance_raw_target_current` | Raw target current | Current calculated directly from surplus before stabilization. |
| `silla_prism_solar_balance_theoretical_target_current` | Theoretical target current | Current the balancer would request if it were allowed to command the wallbox, useful while paused. |
| `silla_prism_solar_balance_battery_reserve_power` | Battery reserve power | Home-battery charge power currently protected by SOC logic. |
| `silla_prism_solar_balance_target_export_power` | Target export power | Configured export buffer. |
| `silla_prism_solar_balance_unused_export_power` | Unused export power | Export still available beyond target export and deadband. |
| `silla_prism_solar_balance_residual_export_countdown` | Residual export countdown | Seconds remaining before unused export can trigger current recovery. |
| `silla_prism_solar_balance_decision_reason` | Decision reason | Current reason for the controller decision. |
| `silla_prism_solar_balance_decision_summary` | Decision summary | Human-readable explanation of the latest balancing decision, including Prism `pilot` mismatch when present. |

These sensors are the best place to understand why the controller is holding,
raising or lowering current.

## Prism Entities

For a single-port Prism the entity IDs normally use the names below. On
multi-port devices Home Assistant adds the port number to the port-specific
entities.

| Entity ID | Type | Description | Unit / values |
| --------- | ---- | ----------- | ------------- |
| `silla_prism_online` | Binary sensor | Prism connection state | online/offline |
| `silla_prism_current_state` | Sensor | Current Prism state | `idle`, `waiting`, `charging`, `pause` |
| `silla_prism_power_grid_voltage` | Sensor | Measured grid voltage | V |
| `silla_prism_output_power` | Sensor | Power delivered to the charging port | W |
| `silla_prism_output_current` | Sensor | Current delivered to the charging port | mA |
| `silla_prism_output_car_current` | Sensor | Current requested by the car | A |
| `silla_prism_current_set_by_user` | Sensor | Current limit set by the user | A |
| `silla_prism_session_time` | Sensor | Current session duration | s |
| `silla_prism_session_output_energy` | Sensor | Energy delivered during the current session | Wh |
| `silla_prism_total_output_energy` | Sensor | Total delivered energy | Wh |
| `silla_prism_error` | Binary sensor | Error status | on/off |
| `silla_prism_current_port_mode` | Sensor | Current port mode reported by Prism | `solar`, `normal`, `paused`, `suspended`, `unknown`, `autolimit` |
| `silla_prism_input_grid_power` | Sensor | Input power from grid | W |
| `silla_prism_core_temperature` | Sensor | Prism CPU temperature | °C |
| `silla_prism_set_max_current` | Number | Set user current limit | A |
| `silla_prism_set_current_limit` | Number | Set active current limit | A |
| `silla_prism_solar_balance_manual_current_override` | Number | Manual current used only by the solar balancer; `0` means automatic | A |
| `silla_prism_set_mode` | Select | Set current port mode | `solar`, `normal`, `paused` |
| `silla_prism_set_mode_traps_auth` | Button | Authorize charging | command |
| `silla_prism_set_mode_traps_noauth` | Button | Revoke charging authorization | command |
| `silla_prism_touch_sigle` | Binary sensor | Single touch gesture pulse | on/off |
| `silla_prism_touch_double` | Binary sensor | Double touch gesture pulse | on/off |
| `silla_prism_touch_long` | Binary sensor | Long touch gesture pulse | on/off |
| `silla_prism_input_grid_energy` | Sensor | Derived total energy taken from grid, when virtual sensors are enabled | kWh |
| `silla_prism_powerwall_solar` | Sensor | Legacy Powerwall-compatible PV power sensor, when Powerwall sensors are enabled | W |
| `silla_prism_powerwall_house` | Sensor | Legacy Powerwall-compatible house power sensor, when Powerwall sensors are enabled | W |
| `silla_prism_solar_battery_balance` | Switch | Enable or disable automatic solar battery balancing, when configured | on/off |

## Testing

Pure solar balancing helpers are covered by unit tests that do not require a
running Home Assistant instance:

```bash
python3 -m unittest discover
```

## Troubleshooting And Releases

For common balancing cases, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

For release notes, see [CHANGELOG.md](CHANGELOG.md). Tags and manifest versions
use normal three-part semantic versions such as `0.9.11`; avoid four-part
versions because HACS may not order them as expected.
