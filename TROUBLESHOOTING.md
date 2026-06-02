# Troubleshooting

This page lists the most useful checks when solar balancing behaves differently
from expected.

## The car does not stay at 6A

Check `Decision summary` and `Decision reason`.

- If the reason is `manual_current_override`, the current was explicitly changed
  through the Home Assistant `Current limit` number. Toggle the solar balancing
  switch or let the balancer publish a new current to clear the override.
- The Prism `pilot` value is not treated as a manual override. It follows the
  current requested by the car and should not keep the balancer above 6A.
- If `Unused export power` is above the configured residual export threshold for
  long enough, residual export recovery can raise current above 6A.

## The wallbox is in autolimit and does not restart

Autolimit is treated as Prism protection. The integration waits while grid
import is above the deadband. When import returns inside the deadband, it makes
one 6A recovery attempt, then waits 5 minutes before another attempt.

Useful sensors:

- `Solar balance status`
- `Grid power used in calculation`
- `Decision summary`
- `Decision reason`

## The wallbox was paused by the app or charge limit

Paused mode is considered deliberate. The integration does not resume charging
automatically when Prism reports paused mode or pause state. Change the Prism
mode back to solar/normal or toggle the balancing switch when you want the
balancer to take over again.

## The EV receives more power than direct solar production

Check whether `Use battery charge as surplus` is enabled. When enabled, battery
charge power above the configured reserve can be redirected to the EV. The
reserve is an approximate target because Prism current changes in whole amps.

Also verify:

- `Battery reserve power`
- `Battery power used in calculation`
- `Solar production used in calculation`
- `Home load used in calculation`

## The calculated surplus looks wrong

Prefer external Home Assistant sensors for real PV production and house load.
Prism `energy_data/power_solar` and `energy_data/power_house` can stay at `0`
on some installations and are not used for the direct calculation.

If the house load sensor includes the EV charger, enable `Home load sensor
includes EV charger`. The balancer then subtracts live Prism EV output power
from the house load before calculating surplus.

## Energy is still being exported

The balancer intentionally keeps the configured `Target grid export` as a safety
buffer. It also applies a deadband and ramp limits, so current may not rise
immediately. If export remains available beyond the residual export threshold,
`Residual export countdown` shows when recovery can add more current.

## HACS does not show the latest version

Make sure the manifest version and tag match, for example manifest `0.9.11` and
tag `v0.9.11`. Use normal three-part versions. Avoid four-part versions such as
`0.9.9.10`, because HACS can order them unexpectedly.
