# Changelog

## 0.9.24

- Fixed touch binary sensors not subscribing to their MQTT event topic after
  entity setup.
- Renamed the single-touch entity key from the misspelled `touch_sigle` to
  `touch_single`; Home Assistant will expose it as
  `binary_sensor.silla_prism_touch_single`.
- Made Prism touch event parsing tolerant of numeric, sequence-like, JSON-like
  and textual MQTT payloads so single, double and long press binary sensors can
  detect events across firmware/protocol variants.
- Double touch now accepts both the historical `1,1` sequence and the compact
  `2` event code.
- Refreshes the touch pulse timer when repeated events arrive close together.

## 0.9.23

- Force solar balancing restarts to begin from 6A after a low-surplus block.
  Stale Prism `pilot` values or manual `Current limit` changes such as 32A are
  no longer used as the ramp base after the controller has held/blocked charging
  for insufficient surplus.
- Residual export tracking still updates diagnostics, but low-surplus recovery
  no longer jumps directly above the Type 2 minimum.
- Added a decision summary for the protected 6A restart path.

## 0.9.22

- Changed solar balancing ownership: when Prism is in solar mode and the solar
  balancer is enabled, the balancer always owns `Current limit`.
- Removed the dedicated solar balance manual current override number. Manual
  changes to Prism `Current limit` are now treated as direct Prism commands, and
  the next balancer cycle republishes the calculated target.
- Kept normal and hybrid modes manual: the solar balancer waits when Prism is
  not in solar mode or Prism autolimit, so it no longer switches normal/hybrid
  back to solar.
- Updated troubleshooting notes, the Lovelace diagnostics example and the
  solar balancer overview diagram to describe the new ownership model.

## 0.9.17

- Added solar balance dry-run mode. When enabled, the integration calculates the
  target current and updates diagnostics without sending MQTT current or mode
  commands to Prism.
- Expanded the decision summary with the dominant constraint or next release
  condition for common balancing decisions.
- Added a ready-to-copy Lovelace diagnostic dashboard for the solar balancer.

## 0.9.16

- Added upstream Prism `hybrid` mode support to the mode select, current port
  mode sensor, translations and documentation.

## 0.9.15

- Treat home-battery reserve as a soft priority before EV surplus: when battery
  charge power is below the configured reserve, the shortfall is subtracted from
  available EV power.
- Added a battery reserve shortfall diagnostic sensor.

## 0.9.14

- Keep solar balance diagnostics populated while Prism is paused, including the
  theoretical current the balancer would request if commanding were allowed.
- Added a theoretical target current diagnostic sensor.
- Treat negative external solar production values as zero production instead of
  converting them to positive surplus.
- Require stable residual export before autolimit recovery attempts.
- Report missing battery power data as a specific waiting state.
- Added a dedicated solar balance manual current number. `Current limit` now
  remains a direct Prism command and no longer enables the balancer override.
- The solar balancer now tracks the live Prism `pilot` current and republishes
  the calculated target if Prism reports a different limit than the last
  controller command.
- Decision summaries now call out when the controller is requesting one current
  but Prism is still reporting a different `pilot` value.

## 0.9.13

- Translated the solar balance decision summary sensor value when Home Assistant
  is configured in Italian.

## 0.9.12

- Added a human-readable solar balance decision summary sensor.
- Moved core solar balancing math into pure helper functions so it can be unit
  tested independently from Home Assistant and MQTT.
- Added unit tests for external solar/home-load calculation, EV-included home
  load correction, battery reserve thresholds, battery sign handling and
  decision summaries.
- Documented troubleshooting steps for 6A hold, autolimit, wallbox pause,
  unexpected surplus, export recovery and HACS version visibility.

## 0.9.11

- Fixed false manual current overrides in solar balancing. The live Prism
  `pilot` value is no longer treated as a manual override because it also
  follows the current requested by the car.
- Manual override is now explicit: it is stored only when the Home Assistant
  `Current limit` number is changed.

## 0.9.10

- Moved away from four-part version tags so HACS can order releases correctly.
