import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dialpad_dbus import DialPadDBusService
except ImportError:  # dbus-python or PyGObject missing
    DialPadDBusService = None


@unittest.skipIf(DialPadDBusService is None, "dbus-python is not installed")
class OverlayStateTest(unittest.TestCase):
    def setUp(self):
        # Never started, so updates only touch the in-memory state.
        self.service = DialPadDBusService(
            on_active_application=lambda app: None,
            on_reload_config=lambda: True,
            on_start_calibration=lambda: False,
            status_provider=dict,
        )

    def state(self):
        return self.service._overlay_state

    def test_signal_matches_declared_signature(self):
        import dbus
        from dialpad_dbus import _DialPadObject

        signature = _DialPadObject.OverlayState._dbus_signature
        self.assertEqual(signature, "bsasasidsbbb")
        values = DialPadDBusService._normalize_overlay_payload(self.state())
        self.assertEqual(len(values), len(list(dbus.Signature(signature))))

    def test_progress_mode_is_not_sticky(self):
        self.service.emit_overlay_state({"enabled": True})
        self.service.emit_overlay_state({"title": "Edit", "value": 40, "value_show_only_progress": True})
        self.assertTrue(self.state()["value_show_only_progress"])
        self.service.emit_overlay_state({"titles": [], "icons": [], "title": "Volume", "value": 0, "unit": ""})
        self.assertFalse(self.state()["value_show_only_progress"])

    def test_partial_update_keeps_progress_mode(self):
        self.service.emit_overlay_state({"title": "Edit", "value": 40, "value_show_only_progress": True})
        self.service.emit_overlay_state({"touching": True})
        self.assertTrue(self.state()["value_show_only_progress"])
        self.assertTrue(self.state()["touching"])

    def test_disable_resets_transient_state(self):
        self.service.emit_overlay_state({"enabled": True, "title": "Volume", "value": 5, "touching": True})
        self.service.emit_overlay_state({"input": "center", "value": 1})
        self.service.emit_overlay_state({"enabled": False})
        state = self.state()
        self.assertEqual(state["title"], "")
        self.assertFalse(state["center_pressed"])
        self.assertFalse(state["touching"])

    def test_values_are_coerced(self):
        values = DialPadDBusService._normalize_overlay_payload({
            "value": "42",
            "title": None,
            "titles": ["A", None],
            "touching": 1,
        })
        self.assertEqual(int(values[4]), 42)
        self.assertEqual(str(values[1]), "")
        self.assertEqual([str(item) for item in values[2]], ["A", ""])
        self.assertTrue(bool(values[9]))

    def test_details_merge_and_stay_out_of_state(self):
        self.service.emit_overlay_state({"details": {"profile": "Krita", "colors": ["#fff"]}})
        self.service.emit_overlay_state({"details": {"pointer": 42.5}})
        details = self.service._details
        self.assertEqual(details["profile"], "Krita")
        self.assertEqual(details["colors"], ["#fff"])
        self.assertEqual(details["pointer"], 42.5)
        self.assertEqual(self.state()["title"], "")

    def test_details_json_round_trip(self):
        import json

        self.service.emit_overlay_state({"details": {"hints": {"cw": "Zoom in"}}})
        self.assertEqual(json.loads(self.service._details_json())["hints"], {"cw": "Zoom in"})


if __name__ == "__main__":
    unittest.main()
