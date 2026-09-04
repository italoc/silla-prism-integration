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
