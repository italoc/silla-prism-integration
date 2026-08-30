"""Unit tests for Prism touch event parsing."""

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


touch_events = load_module(
    f"{PACKAGE_NAME}.touch_events",
    ROOT / "custom_components" / "silla_prism" / "touch_events.py",
)

normalize_touch_payload = touch_events.normalize_touch_payload
touch_payload_matches = touch_events.touch_payload_matches


class TouchEventParserTest(TestCase):
    """Cover Prism touch payload variants seen across MQTT firmware versions."""

    def test_parses_comma_and_json_like_sequences(self) -> None:
        self.assertEqual(normalize_touch_payload("1"), (1,))
        self.assertEqual(normalize_touch_payload("1,1"), (1, 1))
        self.assertEqual(normalize_touch_payload("[1, 1]"), (1, 1))

    def test_parses_textual_events(self) -> None:
        self.assertEqual(normalize_touch_payload("single"), (1,))
        self.assertEqual(normalize_touch_payload("double_touch"), (2,))
        self.assertEqual(normalize_touch_payload("pressione lunga"), (3,))

    def test_double_accepts_repeated_touch_and_numeric_code(self) -> None:
        accepted = ((1, 1), (2,))

        self.assertTrue(touch_payload_matches("1,1", accepted))
        self.assertTrue(touch_payload_matches("2", accepted))
        self.assertTrue(touch_payload_matches("double", accepted))
        self.assertFalse(touch_payload_matches("1", accepted))

    def test_ignores_empty_or_unknown_payloads(self) -> None:
        self.assertIsNone(normalize_touch_payload(""))
        self.assertIsNone(normalize_touch_payload(None))
        self.assertFalse(touch_payload_matches("knock", ((1,),)))
