"""DirectoryWatcher reports what the driver's old inotify watch did."""

import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dir_watch import DirectoryWatcher


class DirectoryWatcherTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.directory = os.path.join(self.root, "watched")
        os.mkdir(self.directory)
        self.events = []
        self.changes = 0
        self.changed = threading.Event()
        self.accept = True
        self.watcher = DirectoryWatcher(self.directory, self._on_change, self._on_event, delay_ms=50)
        self.watcher.start()

    def tearDown(self):
        self.watcher.close()
        shutil.rmtree(self.root, ignore_errors=True)

    def _on_event(self, name):
        self.events.append(name)
        return self.accept

    def _on_change(self):
        self.changes += 1
        self.changed.set()

    def settle(self):
        time.sleep(0.3)

    def write(self, name, text="x"):
        with open(os.path.join(self.directory, name), "w") as f:
            f.write(text)

    def test_written_file(self):
        self.write("dialpad_dev")
        self.assertTrue(self.changed.wait(2))
        self.settle()
        self.assertIn("dialpad_dev", self.events)
        self.assertEqual(self.changes, 1)

    def test_atomic_save_is_one_change(self):
        # config.schema.save_config(): write a temporary file, rename it over.
        self.write("config.json.tmp")
        os.replace(os.path.join(self.directory, "config.json.tmp"), os.path.join(self.directory, "config.json"))
        self.assertTrue(self.changed.wait(2))
        self.settle()
        self.assertIn("config.json", self.events)
        self.assertEqual(self.changes, 1)

    def test_file_moved_in(self):
        outside = os.path.join(self.root, "outside")
        with open(outside, "w") as f:
            f.write("x")
        os.rename(outside, os.path.join(self.directory, "dialpad_dev"))
        self.assertTrue(self.changed.wait(2))
        self.assertEqual(self.events, ["dialpad_dev"])

    def test_deleting_a_file_is_ignored(self):
        self.write("dialpad_dev")
        self.assertTrue(self.changed.wait(2))
        self.settle()
        self.events.clear()
        os.unlink(os.path.join(self.directory, "dialpad_dev"))
        self.settle()
        self.assertEqual(self.events, [])
        self.assertEqual(self.changes, 1)

    def test_directory_removed(self):
        os.rmdir(self.directory)
        self.assertTrue(self.changed.wait(2))
        self.assertIn("", self.events)

    def test_rejected_events_change_nothing(self):
        # The driver rejects its own saves (config_lock held).
        self.accept = False
        self.write("dialpad_dev")
        self.settle()
        self.assertIn("dialpad_dev", self.events)
        self.assertEqual(self.changes, 0)

    def test_close_stops_the_thread(self):
        self.watcher.close()
        self.assertFalse(self.watcher._thread.is_alive())
        self.write("dialpad_dev")
        self.settle()
        self.assertEqual(self.changes, 0)


class DirectoryWatcherErrorTest(unittest.TestCase):
    def test_missing_directory_does_not_hang(self):
        # inotify cannot watch a missing path; Gio may fall back to polling.
        watcher = DirectoryWatcher(os.path.join(tempfile.gettempdir(), "no-such-dir-turnpad"), lambda: None)
        try:
            watcher.start()
        except Exception:
            pass
        finally:
            watcher.close()


if __name__ == "__main__":
    unittest.main()
