import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import layout_detect  # noqa: E402

ROWS = [
    {"Vendor ID": "2808", "Product ID": "0220", "Base layout": "proartp16", "Laptop": "ProArt PX13 HN7306WV_HN7306WV", "Event count": "31"},
    {"Vendor ID": "04F3", "Product ID": "3101", "Base layout": "asusvivobook16x", "Laptop": "Vivobook A", "Event count": "2"},
    {"Vendor ID": "04F3", "Product ID": "3101", "Base layout": "zenbookpro14", "Laptop": "Zenbook B", "Event count": "9"},
    {"Vendor ID": "04F3", "Product ID": "3101", "Base layout": "removedlayout", "Laptop": "Old C", "Event count": "99"},
]
AVAILABLE = {"proartp16", "asusvivobook16x", "zenbookpro14"}

DEVICES = """I: Bus=0011 Vendor=0001 Product=0001 Version=ab83
N: Name="AT Translated Set 2 keyboard"

I: Bus=0018 Vendor=04f3 Product=3101 Version=0100
N: Name="ELAN1406:00 04F3:3101 Touchpad"
P: Phys=i2c-ELAN1406:00
"""


class LayoutDetectTest(unittest.TestCase):
    def test_product_name_wins(self):
        self.assertEqual(
            layout_detect.choose_layout(ROWS, "ProArt PX13 HN7306WV_HN7306WV\n", [("04f3", "3101")], AVAILABLE),
            "proartp16",
        )

    def test_touchpad_id_picks_the_most_reported_existing_layout(self):
        self.assertEqual(
            layout_detect.choose_layout(ROWS, "Unknown laptop", [("04f3", "3101")], AVAILABLE),
            "zenbookpro14",
        )

    def test_unknown_laptop(self):
        self.assertIsNone(layout_detect.choose_layout(ROWS, "Unknown", [("1234", "5678")], AVAILABLE))
        self.assertIsNone(layout_detect.choose_layout(ROWS, "", [], AVAILABLE))

    def test_touchpads_from_proc(self):
        self.assertEqual(layout_detect.touchpad_ids(DEVICES), [("04f3", "3101")])

    def test_shipped_table_names_only_shipped_layouts_or_none(self):
        import csv
        layouts = {name[:-3] for name in os.listdir(os.path.join(os.path.dirname(layout_detect.TABLE), "layouts")) if name.endswith(".py")}
        with open(layout_detect.TABLE, newline="") as table:
            rows = list(csv.DictReader(table))
        self.assertTrue(rows)
        self.assertIn(layout_detect.FALLBACK, layouts)
        known = [row for row in rows if row.get("Base layout") in layouts]
        self.assertGreater(len(known), len(rows) // 2)


if __name__ == "__main__":
    unittest.main()
