import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.migrate import layout_geometry  # noqa: E402
from config.schema import TouchGeometry  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


class LayoutGeometryTest(unittest.TestCase):
    def test_every_shipped_layout_has_geometry(self):
        for path in sorted((ROOT / "layouts").glob("*.py")):
            with self.subTest(layout=path.stem):
                geometry = layout_geometry(path.stem, ROOT / "layouts")
                self.assertIsInstance(geometry, TouchGeometry)
                self.assertGreater(geometry.circle_diameter, geometry.center_button_diameter)

    def test_reads_the_constants_without_importing(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "model.py").write_text(
                "import module_that_does_not_exist\n"
                "top_right_icon_width = 200\ntop_right_icon_height = 210\n"
                "circle_diameter = 1000\ncenter_button_diameter = 300\n"
                "circle_center_x = 700\ncircle_center_y = 650.4\n"
            )
            self.assertEqual(
                layout_geometry("model", directory),
                TouchGeometry(width=200, height=210, circle_diameter=1000,
                              center_button_diameter=300, center_x=700, center_y=650),
            )

    def test_missing_or_incomplete_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "partial.py").write_text("circle_diameter = 900\n")
            self.assertIsNone(layout_geometry("partial", directory))
            self.assertIsNone(layout_geometry("absent", directory))
            self.assertIsNone(layout_geometry("../partial", directory))
            self.assertIsNone(layout_geometry("", directory))


if __name__ == "__main__":
    unittest.main()
