"""Running programs and shell commands from dial actions.

A dial action may start anything from a quick command (playerctl next) to
a program with a window (a calculator). run() waits up to WAIT_SECONDS, so
quick commands keep their order inside a macro, and then lets a program
that is still running carry on without blocking the next dial action.

With systemd, the command gets its own scope (systemd-run --user --scope):
a program started from the dial is not part of the driver's service and
survives the driver restarting or stopping.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading

from config.identity import SLUG

log = logging.getLogger(SLUG)

WAIT_SECONDS = 2.0


def command_line(argv: list[str]) -> list[str]:
    """argv, wrapped in its own systemd scope when systemd is there."""
    systemd_run = shutil.which("systemd-run")
    if systemd_run is None:
        return list(argv)
    return [systemd_run, "--user", "--scope", "--quiet", "--collect", "--", *argv]


def run(argv: list[str], wait: float = WAIT_SECONDS) -> int | None:
    """Exit status of a command that finished within `wait`, else None."""
    try:
        process = subprocess.Popen(
            command_line(argv),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as error:
        log.error("Could not start %s: %s", argv[0], error)
        return 127
    try:
        status = process.wait(timeout=wait)
    except subprocess.TimeoutExpired:
        # Still running, e.g. a program window: reap it whenever it ends.
        threading.Thread(target=process.wait, name=f"{SLUG}-launched", daemon=True).start()
        return None
    if status != 0:
        log.error("%s exited with status %s", " ".join(argv), status)
    return status


def run_shell(script: str, wait: float = WAIT_SECONDS) -> int | None:
    return run(["/bin/sh", "-c", script], wait)
