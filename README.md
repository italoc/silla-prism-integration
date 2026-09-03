# Silla Prism Solar custom integration

![Silla Prism Solar](image.png)

Custom Home Assistant integration for Silla Prism EVSE devices over MQTT.

This fork keeps the original Silla Prism MQTT entities and adds solar charging
logic that balances EV charging with photovoltaic production, house load and
home-battery priority.

> **Beta notice:** the solar balancing features actively change Prism current
> limit and operating mode through MQTT. Test with conservative limits before
> relying on it unattended.

## Documentation

The full documentation is available in the project wiki:

**[Open the Silla Prism Solar Integration Wiki](https://github.com/italoc/silla-prism-integration/wiki)**

Start from these pages:

- [Installation](https://github.com/italoc/silla-prism-integration/wiki/Installation)
- [Basic Setup](https://github.com/italoc/silla-prism-integration/wiki/Basic-Setup)
- [Solar Balancing Setup](https://github.com/italoc/silla-prism-integration/wiki/Solar-Balancing-Setup)
- [How Solar Balancing Works](https://github.com/italoc/silla-prism-integration/wiki/How-Solar-Balancing-Works)
- [Troubleshooting](https://github.com/italoc/silla-prism-integration/wiki/Troubleshooting)
- [Release Notes](https://github.com/italoc/silla-prism-integration/wiki/Release-Notes)
- [Home Assistant Core Submission](docs/home-assistant-core-submission.md)

## Main Features

- Silla Prism MQTT entities for state, power, current, energy, mode and touch
  gestures. Touch gestures expose `binary_sensor.silla_prism_touch_single`,
  `binary_sensor.silla_prism_touch_double` and
  `binary_sensor.silla_prism_touch_long`.
- Prism `hybrid` mode support in the mode select and current port mode sensor.
- Optional solar battery balancing switch for each charging port.
- Direct surplus calculation from external solar production and house load
  sensors.
- Home-battery priority based on battery power and optional SOC.
- Configurable export buffer, deadband, start delay, ramp-up, ramp-down and
  residual export recovery.
- Autolimit-aware recovery and explicit pause handling.
- Diagnostic sensors that explain the latest balancing decision.
- Dry-run mode to test the balancing algorithm without sending MQTT commands to
  Prism.

## Touch Gesture Sensors

The Prism touch input is exposed as short-lived binary sensor pulses:

- `binary_sensor.silla_prism_touch_single` for one touch.
- `binary_sensor.silla_prism_touch_double` for two touches.
- `binary_sensor.silla_prism_touch_long` for a long press.

Each event turns the matching sensor on for about two seconds, then restores it
to off. Use a state trigger from `off` to `on` in Home Assistant automations.

Since `0.9.24`, the integration subscribes the touch sensors directly to the
Prism MQTT touch topic and accepts numeric, repeated-sequence, JSON-like and
textual payload variants. The old misspelled
`binary_sensor.silla_prism_touch_sigle` entity was replaced by
`binary_sensor.silla_prism_touch_single`; update any manual references if you
created them before `0.9.24`.

## Quick Install

Prerequisites:

- A working MQTT broker.
- Home Assistant MQTT integration configured and connected to the same broker.
- Prism MQTT enabled on the wallbox.

Installation:

1. Add this repository to HACS as a custom integration repository.
2. Install **Silla Prism EVSE** from HACS.
3. Restart Home Assistant.
4. Add the Silla Prism integration from the Home Assistant dashboard.

[![Open your Home Assistant instance and start setting up a new integration of a specific brand.](https://my.home-assistant.io/badges/brand.svg)](https://my.home-assistant.io/redirect/brand/?brand=silla_prism)

Manual installation is also possible by copying
`custom_components/silla_prism` into your Home Assistant `custom_components`
directory.

## Important HACS Note

Do not keep this fork and the original `persuader72/silla-prism-integration`
installed at the same time. Both integrations use the same Home Assistant domain:

```text
silla_prism
```

Keeping both repositories installed can make HACS or Home Assistant show the
wrong update source.

## Testing

Pure solar balancing helpers are covered by unit tests that do not require a
running Home Assistant instance:

```bash
python3 -m unittest discover
```

## Links

- [Wiki](https://github.com/italoc/silla-prism-integration/wiki)
- [Solar balance diagnostic dashboard](docs/lovelace-solar-balance-diagnostics.yaml)
- [Changelog](CHANGELOG.md)
- [Prism MQTT manual](https://support.silla.industries/wp-content/uploads/2023/09/DOC-Prism_MQTT_Manual-rel.2.0_rev.-20220105-EN.pdf)
