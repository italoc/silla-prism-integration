# Changelog

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
