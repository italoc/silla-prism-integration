"""Unit tests for pure solar balancing helpers."""

import importlib.util
from pathlib import Path
import sys
import types
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "custom_components.silla_prism"
package = types.ModuleType(PACKAGE_NAME)
package.__path__ = [str(ROOT / "custom_components" / "silla_prism")]
sys.modules.setdefault("custom_components", types.ModuleType("custom_components"))
sys.modules[PACKAGE_NAME] = package


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


load_module(
    f"{PACKAGE_NAME}.const", ROOT / "custom_components" / "silla_prism" / "const.py"
)
solar_balance = load_module(
    f"{PACKAGE_NAME}.solar_balance",
    ROOT / "custom_components" / "silla_prism" / "solar_balance.py",
)

SOLAR_BALANCE_CHARGING_SURPLUS = solar_balance.SOLAR_BALANCE_CHARGING_SURPLUS
SOLAR_BALANCE_DISABLED = solar_balance.SOLAR_BALANCE_DISABLED
SOLAR_BALANCE_EXTERNAL_PAUSED = solar_balance.SOLAR_BALANCE_EXTERNAL_PAUSED
SOLAR_BALANCE_WAITING_BATTERY_DATA = solar_balance.SOLAR_BALANCE_WAITING_BATTERY_DATA
SOLAR_BALANCE_WAITING_DATA = solar_balance.SOLAR_BALANCE_WAITING_DATA
SOLAR_BALANCE_WAITING_SOLAR_MODE = solar_balance.SOLAR_BALANCE_WAITING_SOLAR_MODE
SURPLUS_SOURCE_PRISM_GRID_BATTERY = solar_balance.SURPLUS_SOURCE_PRISM_GRID_BATTERY
SURPLUS_SOURCE_SOLAR_HOME_LOAD = solar_balance.SURPLUS_SOURCE_SOLAR_HOME_LOAD
SolarBalanceState = solar_balance.SolarBalanceState
calculate_available_power = solar_balance.calculate_available_power
describe_solar_balance_state = solar_balance.describe_solar_balance_state
get_battery_reserve_power = solar_balance.get_battery_reserve_power
normalize_battery_power = solar_balance.normalize_battery_power


class SolarBalanceHelperTest(TestCase):
    """Cover the balancing math that should stay independent from Home Assistant."""

    def test_home_load_including_ev_is_corrected(self) -> None:
        result = calculate_available_power(
            ev_power=2600,
            grid_power=0,
            battery_charge_available=0,
            battery_reserve_shortfall=0,
            battery_power_to_exclude=0,
            use_battery_charge=False,
            solar_power=1300,
            home_load_power=3400,
            home_load_includes_ev=True,
        )

        self.assertEqual(result.source, SURPLUS_SOURCE_SOLAR_HOME_LOAD)
        self.assertEqual(result.effective_home_load_power, 800)
        self.assertEqual(result.available_power, 500)

    def test_zero_solar_and_battery_discharge_are_not_surplus(self) -> None:
        result = calculate_available_power(
            ev_power=2660,
            grid_power=-3,
            battery_charge_available=0,
            battery_reserve_shortfall=0,
            battery_power_to_exclude=3607,
            use_battery_charge=True,
            solar_power=0,
            home_load_power=755,
            home_load_includes_ev=False,
        )

        self.assertEqual(result.source, SURPLUS_SOURCE_SOLAR_HOME_LOAD)
        self.assertEqual(result.available_power, -755)

    def test_negative_solar_sensor_is_not_treated_as_production(self) -> None:
        result = calculate_available_power(
            ev_power=0,
            grid_power=0,
            battery_charge_available=0,
            battery_reserve_shortfall=0,
            battery_power_to_exclude=0,
            use_battery_charge=False,
            solar_power=-1200,
            home_load_power=400,
        )

        self.assertEqual(result.source, SURPLUS_SOURCE_SOLAR_HOME_LOAD)
        self.assertEqual(result.available_power, -400)

    def test_fallback_subtracts_grid_import_and_battery_discharge(self) -> None:
        result = calculate_available_power(
            ev_power=2000,
            grid_power=300,
            battery_charge_available=0,
            battery_reserve_shortfall=0,
            battery_power_to_exclude=600,
            use_battery_charge=False,
        )

        self.assertEqual(result.source, SURPLUS_SOURCE_PRISM_GRID_BATTERY)
        self.assertEqual(result.available_power, 1100)

    def test_battery_reserve_shortfall_reduces_direct_solar_surplus(self) -> None:
        result = calculate_available_power(
            ev_power=1790,
            grid_power=0,
            battery_charge_available=0,
            battery_reserve_shortfall=837,
            battery_power_to_exclude=0,
            use_battery_charge=False,
            solar_power=2652,
            home_load_power=534,
        )

        self.assertEqual(result.source, SURPLUS_SOURCE_SOLAR_HOME_LOAD)
        self.assertEqual(result.available_power, 1281)

    def test_battery_reserve_tracks_soc_thresholds(self) -> None:
        self.assertEqual(
            get_battery_reserve_power(None, 2700, 40, 80, 1500, 1000), 2700
        )
        self.assertEqual(
            get_battery_reserve_power(60, 2700, 40, 80, 1500, 1000), 1500
        )
        self.assertEqual(
            get_battery_reserve_power(85, 2700, 40, 80, 1500, 1000), 1000
        )
        self.assertEqual(
            get_battery_reserve_power(96, 2700, 40, 80, 1500, 1000), 0
        )

    def test_battery_charge_above_reserve_can_become_surplus(self) -> None:
        breakdown = normalize_battery_power(
            battery_power=-2200,
            battery_discharge_positive=True,
            battery_reserve_power=1500,
            use_battery_charge=True,
        )

        self.assertEqual(breakdown.charge_power, 2200)
        self.assertEqual(breakdown.discharge_power, 0)
        self.assertEqual(breakdown.charge_available_above_reserve, 700)
        self.assertEqual(breakdown.power_to_exclude, -700)

    def test_battery_discharge_positive_setting_is_respected(self) -> None:
        breakdown = normalize_battery_power(
            battery_power=-500,
            battery_discharge_positive=False,
            battery_reserve_power=1500,
            use_battery_charge=True,
        )

        self.assertEqual(breakdown.normalized_power, 500)
        self.assertEqual(breakdown.discharge_power, 500)
        self.assertEqual(breakdown.power_to_exclude, 500)

    def test_decision_summary_explains_low_surplus_hold(self) -> None:
        summary = describe_solar_balance_state(
            SolarBalanceState(
                status=SOLAR_BALANCE_CHARGING_SURPLUS,
                available_power=-755,
                target_current=6,
                current_limit_reason="low_surplus_hold_6a",
            )
        )

        self.assertIn("Holding 6A", summary)
        self.assertIn("-755W", summary)
        self.assertIn("Constraint", summary)

    def test_decision_summary_explains_manual_override(self) -> None:
        summary = describe_solar_balance_state(
            SolarBalanceState(
                target_current=12,
                current_limit_reason="manual_current_override",
            )
        )

        self.assertIn("solar balance manual current override", summary)

    def test_decision_summary_uses_italian_when_requested(self) -> None:
        summary = describe_solar_balance_state(
            SolarBalanceState(
                available_power=-755,
                target_current=6,
                current_limit_reason="low_surplus_hold_6a",
            ),
            "it",
        )

        self.assertIn("Mantengo 6A", summary)
        self.assertIn("surplus calcolato", summary)
        self.assertIn("Vincolo", summary)

    def test_decision_summary_explains_dry_run(self) -> None:
        summary = describe_solar_balance_state(
            SolarBalanceState(
                status=SOLAR_BALANCE_CHARGING_SURPLUS,
                available_power=2800,
                target_current=12,
                current_limit_reason="target_current",
                dry_run=True,
            )
        )

        self.assertIn("Dry run", summary)
        self.assertIn("would request 12A", summary)
        self.assertIn("no MQTT command is sent", summary)

    def test_decision_summary_reports_next_stable_surplus_release(self) -> None:
        summary = describe_solar_balance_state(
            SolarBalanceState(
                target_current=6,
                start_delay_remaining=42,
                current_limit_reason="waiting_stable_surplus",
            )
        )

        self.assertIn("Waiting 42s", summary)
        self.assertIn("Next release in 42s", summary)

    def test_decision_summary_reports_theoretical_pause_target(self) -> None:
        summary = describe_solar_balance_state(
            SolarBalanceState(
                status=SOLAR_BALANCE_EXTERNAL_PAUSED,
                current_limit_reason="external_pause",
                theoretical_target_current=10,
            )
        )

        self.assertIn("Theoretical target 10A", summary)

    def test_decision_summary_reports_waiting_solar_mode(self) -> None:
        summary = describe_solar_balance_state(
            SolarBalanceState(
                status=SOLAR_BALANCE_WAITING_SOLAR_MODE,
                current_limit_reason="waiting_solar_mode",
                theoretical_target_current=10,
            )
        )

        self.assertIn("not in solar mode", summary)

    def test_decision_summary_handles_disabled_and_waiting_data(self) -> None:
        self.assertEqual(
            describe_solar_balance_state(
                SolarBalanceState(status=SOLAR_BALANCE_DISABLED)
            ),
            "Solar balancing is disabled.",
        )
        self.assertEqual(
            describe_solar_balance_state(
                SolarBalanceState(status=SOLAR_BALANCE_WAITING_DATA)
            ),
            "Waiting for required sensor data.",
        )
        self.assertEqual(
            describe_solar_balance_state(
                SolarBalanceState(status=SOLAR_BALANCE_WAITING_BATTERY_DATA)
            ),
            "Waiting for battery power data.",
        )
