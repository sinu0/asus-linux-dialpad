"""Rendering noise must not count as a changed README picture; real changes must."""

import sys
import tempfile
import unittest
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover - Pillow is a development dependency
    Image = None

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))


@unittest.skipIf(Image is None, "Pillow is not installed")
class ChangedPixelsTest(unittest.TestCase):
    def setUp(self):
        from update_previews import MIN_PIXELS, changed_pixels

        self.changed_pixels = changed_pixels
        self.min_pixels = MIN_PIXELS
        self.directory = tempfile.TemporaryDirectory()
        self.base = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def save(self, name, image):
        path = self.base / name
        image.save(path)
        return path

    def test_noise_is_ignored_and_changes_are_counted(self):
        old = self.save("old.png", Image.new("RGB", (40, 40), (60, 60, 60)))
        noisy = self.save("noisy.png", Image.new("RGB", (40, 40), (66, 54, 60)))
        self.assertEqual(self.changed_pixels(old, noisy), 0)

        changed = Image.new("RGB", (40, 40), (60, 60, 60))
        changed.paste((200, 60, 60), (0, 0, 10, 10))
        self.assertEqual(self.changed_pixels(old, self.save("changed.png", changed)), 100)
        self.assertGreaterEqual(100, self.min_pixels)

    def test_other_size_is_a_change(self):
        old = self.save("old.png", Image.new("RGB", (40, 40)))
        self.assertIsNone(self.changed_pixels(old, self.save("big.png", Image.new("RGB", (41, 40)))))


if __name__ == "__main__":
    unittest.main()
