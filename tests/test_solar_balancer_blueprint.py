"""Tests for the standalone solar balancer blueprint."""

from collections.abc import Iterator
import contextlib
import os
from pathlib import Path
import unittest
from unittest.mock import patch

try:
    import pytest

    from homeassistant.components import automation
    from homeassistant.components.blueprint import models
    from homeassistant.core import HomeAssistant, ServiceCall, callback
    from homeassistant.setup import async_setup_component
    from homeassistant.util import yaml as yaml_util
except ModuleNotFoundError as err:
    raise unittest.SkipTest("Home Assistant test environment is not installed") from err


REPOSITORY_PATH = Path(
    os.environ.get("SILLA_PRISM_REPOSITORY", Path(__file__).parents[1])
)
BLUEPRINT_PATH = (
    REPOSITORY_PATH / "blueprints/automation/silla_prism/solar_battery_balancer.yaml"
)

ENTITIES = {
    "enabled_entity": "input_boolean.solar_balance",
    "pause_marker_entity": "input_boolean.solar_balance_paused",
    "mode_entity": "select.prism_mode",
    "current_limit_entity": "number.prism_current_limit",
    "solar_power_entity": "sensor.solar_power",
    "home_load_entity": "sensor.home_load",
    "ev_power_entity": "sensor.ev_power",
    "battery_power_entity": "sensor.battery_power",
    "battery_soc_entity": "sensor.battery_soc",
    "restart_delay": 0,
}


def async_mock_service(
    hass: HomeAssistant, domain: str, service: str
) -> list[ServiceCall]:
    """Capture service calls without depending on Home Assistant test helpers."""
    calls: list[ServiceCall] = []

    async def handle_service(call: ServiceCall) -> None:
        calls.append(call)

    hass.services.async_register(domain, service, handle_service)
    return calls


@pytest.fixture
def ignore_missing_translations() -> list[str]:
    """Ignore generated translations absent from the lightweight checkout."""
    return [
        "component.automation.services.turn_off.name",
        "component.automation.services.turn_on.name",
    ]


@contextlib.contextmanager
def patch_blueprint() -> Iterator[None]:
    """Load the repository blueprint from its source file."""
    original_load = models.DomainBlueprints._load_blueprint  # noqa: SLF001

    @callback
    def mock_load_blueprint(self, path):
        if path != "silla_prism/solar_battery_balancer.yaml":
            return original_load(self, path)
        blueprint_data = yaml_util.load_yaml(BLUEPRINT_PATH)
        blueprint_data["triggers"] = [
            trigger
            for trigger in blueprint_data["triggers"]
            if trigger.get("trigger") != "time_pattern"
        ]
        return models.Blueprint(
            blueprint_data,
            expected_domain=self.domain,
            path=path,
            schema=automation.config.AUTOMATION_BLUEPRINT_SCHEMA,
        )

    with patch(
        "homeassistant.components.blueprint.models.DomainBlueprints._load_blueprint",
        mock_load_blueprint,
    ):
        yield


def test_all_blueprint_fields_have_descriptions() -> None:
    """Every UI field explains its value and expected units or behavior."""
    blueprint_data = yaml_util.load_yaml(BLUEPRINT_PATH)
    sections = blueprint_data["blueprint"]["input"]
    missing = [
        field_name
        for section in sections.values()
        for field_name, field in section["input"].items()
        if not field.get("description")
    ]

    assert not missing


def set_inputs(
    hass: HomeAssistant,
    *,
    mode: str,
    marker: str = "off",
    solar_power: float = 5000,
) -> None:
    """Set the entities consumed by the blueprint."""
    hass.states.async_set("input_boolean.solar_balance", "on")
    hass.states.async_set("input_boolean.solar_balance_paused", marker)
    hass.states.async_set("select.prism_mode", mode)
    hass.states.async_set("number.prism_current_limit", "32")
    hass.states.async_set("sensor.solar_power", solar_power)
    hass.states.async_set("sensor.home_load", "500")
    hass.states.async_set("sensor.ev_power", "0")
    hass.states.async_set("sensor.battery_power", "0")
    hass.states.async_set("sensor.battery_soc", "96")


async def setup_blueprint(hass: HomeAssistant) -> None:
    """Set up one automation using the blueprint."""
    with patch_blueprint():
        assert await async_setup_component(
            hass,
            "automation",
            {
                "automation": {
                    "alias": "Prism solar balance test",
                    "use_blueprint": {
                        "path": "silla_prism/solar_battery_balancer.yaml",
                        "input": ENTITIES,
                    },
                }
            },
        )


@pytest.mark.parametrize("mode", ["normal", "hybrid"])
async def test_blueprint_does_not_control_non_solar_modes(
    hass: HomeAssistant, mode: str
) -> None:
    """Normal and hybrid modes remain under manual control."""
    set_inputs(hass, mode=mode)
    number_calls = async_mock_service(hass, "number", "set_value")
    select_calls = async_mock_service(hass, "select", "select_option")
    await setup_blueprint(hass)

    hass.states.async_set("sensor.solar_power", "5100")
    await hass.async_block_till_done()

    assert not number_calls
    assert not select_calls


async def test_low_surplus_sets_six_amps_before_pause(hass: HomeAssistant) -> None:
    """Low surplus follows the safe current-before-pause sequence."""
    set_inputs(hass, mode="solar", solar_power=900)
    number_calls = async_mock_service(hass, "number", "set_value")
    select_calls = async_mock_service(hass, "select", "select_option")
    marker_calls = async_mock_service(hass, "input_boolean", "turn_on")
    await setup_blueprint(hass)

    hass.states.async_set("sensor.solar_power", "901")
    await hass.async_block_till_done()

    assert number_calls[0].data["value"] == 6
    assert marker_calls
    assert select_calls[0].data["option"] == "paused"


async def test_unavailable_measurement_sends_no_commands(hass: HomeAssistant) -> None:
    """Unavailable startup data leaves Prism untouched."""
    set_inputs(hass, mode="solar")
    hass.states.async_set("sensor.battery_power", "unavailable")
    number_calls = async_mock_service(hass, "number", "set_value")
    select_calls = async_mock_service(hass, "select", "select_option")
    await setup_blueprint(hass)

    hass.states.async_set("sensor.solar_power", "5100")
    await hass.async_block_till_done()

    assert not number_calls
    assert not select_calls


async def test_active_solar_mode_corrects_manual_current(hass: HomeAssistant) -> None:
    """The balancer owns current while solar mode is active."""
    set_inputs(hass, mode="solar")
    hass.states.async_set("number.prism_current_limit", "6")
    number_calls = async_mock_service(hass, "number", "set_value")
    await setup_blueprint(hass)

    hass.states.async_set("sensor.solar_power", "5100")
    await hass.async_block_till_done()

    assert number_calls[0].data["value"] == 7


async def test_current_above_configured_max_is_clamped(hass: HomeAssistant) -> None:
    """A stale or manual high current is immediately brought inside the limit."""
    set_inputs(hass, mode="solar")
    number_calls = async_mock_service(hass, "number", "set_value")
    await setup_blueprint(hass)

    hass.states.async_set("sensor.solar_power", "5100")
    await hass.async_block_till_done()

    assert number_calls[0].data["value"] == 16


async def test_manual_pause_is_not_resumed(hass: HomeAssistant) -> None:
    """Paused mode without the marker belongs to the user or Prism."""
    set_inputs(hass, mode="paused", marker="off")
    number_calls = async_mock_service(hass, "number", "set_value")
    select_calls = async_mock_service(hass, "select", "select_option")
    await setup_blueprint(hass)

    hass.states.async_set("sensor.solar_power", "5100")
    await hass.async_block_till_done()

    assert not number_calls
    assert not select_calls


async def test_balancer_pause_restarts_from_six_amps(hass: HomeAssistant) -> None:
    """A pause owned by the blueprint restarts conservatively at 6 A."""
    set_inputs(hass, mode="paused", marker="on")
    number_calls = async_mock_service(hass, "number", "set_value")
    select_calls = async_mock_service(hass, "select", "select_option")
    marker_calls = async_mock_service(hass, "input_boolean", "turn_off")
    await setup_blueprint(hass)

    hass.states.async_set("sensor.solar_power", "5100")
    await hass.async_block_till_done()

    assert number_calls[0].data["value"] == 6
    assert select_calls[0].data["option"] == "solar"
    assert marker_calls
