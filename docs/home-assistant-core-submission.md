# Home Assistant Core Submission

This integration is currently distributed as a custom HACS integration. To make
it an official Home Assistant integration, the practical route is a pull request
to `home-assistant/core`, not a separate notification email.

## Current Status

- Domain: `silla_prism`
- Setup: config flow through the Home Assistant UI
- Transport: MQTT
- Branding assets: present in `custom_components/silla_prism/brand`
- Local custom integration validation: HACS and hassfest workflows are present
- Latest release documented here: `0.9.24`

## Minimum Upstream Requirements

Home Assistant requires new integrations to meet at least the Bronze tier of the
Integration Quality Scale. Before opening a PR, prepare the integration for the
Core repository shape and verify the Bronze checklist, especially:

- UI config flow coverage and setup tests.
- Unique config entry handling and config-entry unload/reload behavior.
- Entity unique IDs and `has_entity_name` usage.
- Runtime data stored on the config entry.
- Documentation for setup, removal, entities, actions, triggers and conditions,
  with exemptions where the integration does not provide them.
- A `quality_scale.yaml` file for `homeassistant/components/silla_prism`.
- Core-compatible manifest metadata. Official integrations use
  `https://www.home-assistant.io/integrations/silla_prism` as documentation and
  omit a custom `issue_tracker`.

## Suggested Contact / Submission Path

1. Port the integration into a Home Assistant Core development branch under
   `homeassistant/components/silla_prism`.
2. Add full tests expected by Core, starting from config flow setup/unload and
   entity behavior.
3. Add official documentation in the Home Assistant documentation repository
   once the Core PR is ready or requested by maintainers.
4. Open a pull request against `home-assistant/core` with context about Silla
   Prism, MQTT requirements and the communication protocol used by this
   integration.
5. Be ready to answer maintainer review comments and adjust the implementation
   to Core architecture conventions.

## Draft PR Context

```markdown
## Proposed integration

This PR proposes a new `silla_prism` integration for Silla Prism EVSE wallboxes.
The integration communicates locally over MQTT and exposes Prism charging state,
power/current/energy sensors, operating mode controls and touch gesture event
binary sensors.

The custom integration has been used through HACS and includes a UI config flow,
MQTT-based entities, translations, branding assets and diagnostics around solar
charging behavior.

## Product / service

Silla Prism is an EVSE / wallbox for electric vehicle charging. The integration
uses the device MQTT interface and requires a configured Home Assistant MQTT
integration.

## Notes for reviewers

- Local-only communication through MQTT.
- One or more charging ports are supported.
- Touch input events are exposed as short-lived binary sensor pulses.
- Solar balancing behavior is currently implemented in the custom integration;
  confirm whether all of it should be included in the initial Core PR or split
  into a smaller first submission.
```
