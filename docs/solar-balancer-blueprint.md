# Solar balancer blueprint

The standalone automation blueprint moves photovoltaic and home-battery control
out of the Silla Prism device integration. The integration exposes Prism
measurements and controls; Home Assistant owns the automation logic.

## Installation

1. Copy
   `blueprints/automation/silla_prism/solar_battery_balancer.yaml` into the same
   path below the Home Assistant configuration directory.
2. Create two input boolean helpers: one enables the balancer and one is a
   private pause marker used only by the blueprint.
3. Reload automations, create an automation from the blueprint, and select the
   Prism mode, current limit, power, and battery entities.
4. Begin with **Dry run** enabled and check the automation traces.
5. Disable dry run only after confirming signs, phases, power values, and port.

Create a separate automation instance and pause marker for each Prism DUO port.

## Control rules

- Commands are sent only in `solar` mode or during recovery from a pause made
  by the blueprint.
- Selecting `normal` or `hybrid` stops balancing without forcing another mode.
- A manual `paused` mode is respected and is never resumed automatically.
- Insufficient surplus writes 6 A before selecting `paused`.
- Recovery waits for stable surplus, writes 6 A, then selects `solar`.
- In solar mode, manual current-limit changes are corrected on the next cycle.
- Battery charging is reserved according to SOC. Charge above the reserve can
  optionally be made available to the EV.

The blueprint evaluates every ten seconds and whenever a required entity
changes. It uses `mode: single`, so updates cannot overlap during restart delay.

The pause marker is controller state, not a user control. Do not reuse it in
another automation or edit it manually.

Automation delays reset when Home Assistant restarts or automations reload.
After startup, the next evaluation begins a new stable-surplus delay.

## Example configuration

The following entity IDs are examples. Replace them with the entities available
in your Home Assistant instance. This example describes a 230 V single-phase
installation limited to 16 A:

```yaml
automation:
  - alias: Prism solar balancer
    use_blueprint:
      path: silla_prism/solar_battery_balancer.yaml
      input:
        enabled_entity: input_boolean.prism_solar_balance
        pause_marker_entity: input_boolean.prism_balancer_paused
        mode_entity: select.silla_prism_set_port_mode
        current_limit_entity: number.silla_prism_set_current_limit
        solar_power_entity: sensor.pv_production_power
        home_load_entity: sensor.home_load_power
        ev_power_entity: sensor.silla_prism_charging_power
        battery_power_entity: sensor.home_battery_power
        battery_soc_entity: sensor.home_battery_soc
        home_load_includes_ev: false
        battery_discharge_positive: true
        nominal_voltage: 230
        charging_phases: 1
        maximum_current: 16
        use_excess_battery_charge: true
        battery_max_charge_power: 2700
        battery_soc_mid: 40
        battery_soc_high: 80
        battery_mid_reserve_power: 1500
        battery_high_reserve_power: 1000
        target_export_power: 100
        deadband_power: 150
        increase_step: 1
        decrease_step: 3
        restart_delay: 60
        dry_run: true
```

For three-phase charging, set `charging_phases: 3`. For Prism DUO, create one
automation per port and select that port's mode, current-limit and charging-power
entities. Each automation must use its own pause-marker helper.
