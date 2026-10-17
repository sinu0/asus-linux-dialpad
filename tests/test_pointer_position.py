"""desktop/pointer.py asks the compositor where the pointer is."""

import os
import shutil
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from desktop import pointer


class FakeHyprland:
    """A Hyprland IPC socket that answers one request per connection."""

    def __init__(self, runtime: Path, reply: bytes, delay: float = 0):
        self.path = runtime / "hypr" / "abc_123" / ".socket.sock"
        self.path.parent.mkdir(parents=True)
        self.requests = []
        self._reply = reply
        self._delay = delay
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(str(self.path))
        self._server.listen()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
        while True:
            try:
                connection, _ = self._server.accept()
            except OSError:
                return
            with connection:
                self.requests.append(connection.recv(1024))
                time.sleep(self._delay)
                try:
                    connection.sendall(self._reply)
                except OSError:
                    pass

    def close(self):
        self._server.close()


class PointerPositionTest(unittest.TestCase):
    def setUp(self):
        self.runtime = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.runtime, True)

    def hyprland(self, reply, delay=0):
        server = FakeHyprland(self.runtime, reply, delay)
        self.addCleanup(server.close)
        env = mock.patch.dict(os.environ, {"HYPRLAND_INSTANCE_SIGNATURE": "abc_123",
                                           "XDG_RUNTIME_DIR": str(self.runtime)})
        env.start()
        self.addCleanup(env.stop)
        return server

    def test_hyprland_cursor_position(self):
        server = self.hyprland(b'{"x": 2700, "y": 412}')
        self.assertEqual(pointer.position(), (2700.0, 412.0))
        self.assertEqual(server.requests, [b"j/cursorpos"])

    def test_other_compositors_do_not_tell(self):
        with mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(self.runtime)}):
            os.environ.pop("HYPRLAND_INSTANCE_SIGNATURE", None)
            self.assertIsNone(pointer.position())

    def test_garbage_and_silence_give_none_quickly(self):
        self.hyprland(b"unknown request")
        self.assertIsNone(pointer.position())
        self.setUp()
        self.hyprland(b'{"x": 1, "y": 2}', delay=1)
        start = time.monotonic()
        self.assertIsNone(pointer.position())
        self.assertLess(time.monotonic() - start, 0.5)

    def test_missing_socket(self):
        with mock.patch.dict(os.environ, {"HYPRLAND_INSTANCE_SIGNATURE": "gone",
                                          "XDG_RUNTIME_DIR": str(self.runtime)}):
            self.assertIsNone(pointer.position())


if __name__ == "__main__":
    unittest.main()
