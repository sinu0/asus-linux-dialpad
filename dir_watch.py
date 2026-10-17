"""Watches the driver's config directory with Gio.FileMonitor.

Replaces pyinotify (no Fedora package, and its AsyncNotifier needs asyncore,
gone since Python 3.12). Reports what the old inotify mask
IN_CLOSE_WRITE | IN_MOVED_TO | IN_IGNORED did: a file written and closed,
a file moved or renamed into the directory, and the directory itself gone.
The monitor runs in its own thread with its own GLib main context, so it
needs no main loop elsewhere in the process.
"""

import logging
import threading

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

log = logging.getLogger(__name__)

# Gio event → the inotify event it stands for.
_FINISHED_WRITE = Gio.FileMonitorEvent.CHANGES_DONE_HINT  # IN_CLOSE_WRITE
_MOVED_TO = (Gio.FileMonitorEvent.MOVED_IN, Gio.FileMonitorEvent.RENAMED)  # IN_MOVED_TO
_DELETED = Gio.FileMonitorEvent.DELETED  # IN_IGNORED, only for the directory itself


class DirectoryWatcher:
    """Calls on_event(name) in the watcher thread for each such event and,
    when it returns True, on_change() once delay_ms after the first one: one
    save (a temporary file written, then renamed over the real one) is
    several events but one change, and the delay gives the writer time to
    finish. name is the file's name in the directory ("" for the directory
    itself)."""

    def __init__(self, path, on_change, on_event=lambda name: True, delay_ms=100):
        self._directory = Gio.File.new_for_path(path)
        self._on_change = on_change
        self._on_event = on_event
        self._delay_ms = delay_ms
        self._context = GLib.MainContext.new()
        self._loop = GLib.MainLoop.new(self._context, False)
        self._monitor = None
        self._pending = None
        self._ready = threading.Event()
        self._error = None
        self._thread = threading.Thread(target=self._run, name="config-watch", daemon=True)

    def start(self):
        """Starts watching; raises GLib.Error when the directory cannot be
        watched."""
        self._thread.start()
        self._ready.wait()
        if self._error is not None:
            raise self._error

    def close(self):
        # Quit from inside the loop: a quit() before run() would be lost.
        stop = GLib.idle_source_new()
        stop.set_callback(self._quit)
        stop.attach(self._context)
        if self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join(timeout=1)

    def _run(self):
        self._context.push_thread_default()
        try:
            try:
                self._monitor = self._directory.monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, None)
                self._monitor.connect("changed", self._changed)
            except GLib.Error as error:
                self._error = error
                return
            finally:
                self._ready.set()
            self._loop.run()
            self._monitor.cancel()
        finally:
            self._context.pop_thread_default()

    def _changed(self, _monitor, file, other_file, event):
        if event == _FINISHED_WRITE:
            changed = file
        elif event in _MOVED_TO:
            changed = other_file if event == Gio.FileMonitorEvent.RENAMED else file
        elif event == _DELETED and file.equal(self._directory):
            changed = file
        else:
            return
        name = self._directory.get_relative_path(changed) or ""
        try:
            if not self._on_event(name):
                return
        except Exception:
            log.exception("Config directory event handler failed")
            return
        if self._pending is None:
            self._pending = GLib.timeout_source_new(self._delay_ms)
            self._pending.set_callback(self._fire)
            self._pending.attach(self._context)

    def _quit(self, *_args):
        self._loop.quit()
        return GLib.SOURCE_REMOVE

    def _fire(self, *_args):
        self._pending = None
        try:
            self._on_change()
        except Exception:
            log.exception("Config directory change handler failed")
        return GLib.SOURCE_REMOVE
