# Changelog

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
