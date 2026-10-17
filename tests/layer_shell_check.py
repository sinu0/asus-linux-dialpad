#!/usr/bin/env python3
"""The layer-shell dial on a real compositor, headless.

Run by tests/layer_shell_in_container.sh inside its own D-Bus session
(dbus-run-session), with HOME and XDG_RUNTIME_DIR in a scratch directory:

    python3 tests/layer_shell_check.py sway OUTPUT_DIR [OUTPUT_SCALE]

It starts the compositor without a screen, a window below the dial that
records clicks, keys and focus, a fake driver on the session bus and the
dial (overlay/layer_shell.py). For every case of tests/dial_cases.py it
writes the overlay section of config.json (the dial reloads it), sends the
driver's OverlayDetails and OverlayState signals, takes a screenshot and
compares the dial with dial.js's picture of the same state
(tests/render_dial_reference.js) over the window's colour. Then the pill,
clicks and keys through the dial, focus, hiding after release and the
fade. Screenshots and differences stay in OUTPUT_DIR.
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import gi  # noqa: E402

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402
from PIL import Image, ImageChops  # noqa: E402

from config import identity  # noqa: E402
from dial_cases import CASES, MIN_PIXELS, case_view, changed_pixels, reference_cases  # noqa: E402
from overlay import look  # noqa: E402

# Screen pixels; WIDTH and HEIGHT are logical, set from the output scale.
PIXELS = (1920, 1080)
SCALE = 1
WIDTH, HEIGHT = PIXELS
BACKGROUND = (58, 69, 96)
# Largest channel difference on the finger dot (resampled, see main()).
DOT_TOLERANCE = 48
BACKGROUND_HEX ="#%02x%02x%02x" % BACKGROUND
INTERFACE_XML = f"""
<node>
  <interface name="{identity.DBUS_INTERFACE}">
    <method name="GetOverlayDetails"><arg type="s" direction="out"/></method>
    <signal name="OverlayState"><arg type="b"/><arg type="s"/><arg type="as"/><arg type="as"/><arg type="i"/>
      <arg type="d"/><arg type="s"/><arg type="b"/><arg type="b"/><arg type="b"/></signal>
    <signal name="OverlayDetails"><arg type="s"/></signal>
  </interface>
</node>
"""

TARGET = f"""
import sys
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib
log = open(sys.argv[1], "a", buffering=1)
Gtk.init()
css = Gtk.CssProvider()
css.load_from_string("window {{ background: {BACKGROUND_HEX}; }}")
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, 800)
window = Gtk.Window(title="target")
click = Gtk.GestureClick()
click.connect("pressed", lambda _g, _n, x, y: log.write(f"click {{x:.0f}} {{y:.0f}}\\n"))
window.add_controller(click)
keys = Gtk.EventControllerKey()
keys.connect("key-pressed", lambda _c, keyval, _code, _state: log.write(f"key {{Gdk.keyval_name(keyval)}}\\n") or False)
window.add_controller(keys)
window.connect("notify::is-active", lambda w, _p: log.write(f"active {{w.is_active()}}\\n"))
window.fullscreen()
window.present()
GLib.MainLoop().run()
"""

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    print(("ok    " if condition else "FAIL  ") + message, flush=True)
    if not condition:
        failures.append(message)


def pump(seconds: float) -> None:
    """Wait while answering D-Bus calls."""
    context = GLib.MainContext.default()
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        while context.pending():
            context.iteration(False)
        time.sleep(0.01)


def wait_for(predicate, seconds: float, what: str) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate():
            return True
        pump(0.05)
    print(f"timed out waiting for {what}", flush=True)
    return False


class FakeDriver:
    """The driver's D-Bus service as far as the dial uses it."""

    def __init__(self):
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.details = {}
        info = Gio.DBusNodeInfo.new_for_xml(INTERFACE_XML).interfaces[0]
        self.bus.register_object(identity.DBUS_PATH, info, self._call, None, None)
        self.owned = False
        Gio.bus_own_name_on_connection(self.bus, identity.DBUS_NAME, Gio.BusNameOwnerFlags.NONE,
                                       lambda *_: setattr(self, "owned", True), None)
        wait_for(lambda: self.owned, 5, "the bus name")

    def _call(self, _bus, _sender, _path, _interface, method, _parameters, invocation):
        if method == "GetOverlayDetails":
            invocation.return_value(GLib.Variant("(s)", (json.dumps(self.details),)))

    def send(self, details, state):
        """Details first, then the state, in one go like the driver."""
        self.details = details
        self.bus.emit_signal(None, identity.DBUS_PATH, identity.DBUS_INTERFACE, "OverlayDetails",
                             GLib.Variant("(s)", (json.dumps(details),)))
        self.bus.emit_signal(None, identity.DBUS_PATH, identity.DBUS_INTERFACE, "OverlayState",
                             GLib.Variant("(bsasasidsbbb)", tuple(state)))
        self.bus.flush_sync(None)


class Sway:
    name = "sway"

    def __init__(self, runtime: Path, output: Path):
        config = runtime / "sway.conf"
        config.write_text(
            f"output HEADLESS-1 mode {PIXELS[0]}x{PIXELS[1]} position 0 0 scale {SCALE}\n"
            "xwayland disable\ndefault_border none\nfocus_follows_mouse no\n")
        environment = {**os.environ, "WLR_BACKENDS": "headless", "WLR_LIBINPUT_NO_DEVICES": "1",
                       "WLR_RENDERER": "pixman", "WLR_HEADLESS_OUTPUTS": "1"}
        environment.pop("WAYLAND_DISPLAY", None)
        self.log = open(output / "sway.log", "w")
        # Distributions give sway the cap_sys_nice file capability, which
        # containers refuse to exec; a copy has none.
        binary = runtime / "sway"
        shutil.copyfile(shutil.which("sway"), binary)
        binary.chmod(0o755)
        self.process = subprocess.Popen([str(binary), "-c", str(config), "-d"], env=environment,
                                        stdout=self.log, stderr=subprocess.STDOUT)
        self.runtime = runtime
        if not wait_for(lambda: self.socket(), 20, "sway"):
            raise SystemExit("sway did not start, see sway.log")
        self.display = sorted(p for p in os.listdir(runtime) if p.startswith("wayland-") and not p.endswith(".lock"))[0]

    def socket(self):
        found = glob.glob(str(self.runtime / "sway-ipc.*.sock"))
        return found[0] if found and glob.glob(str(self.runtime / "wayland-*")) else None

    def command(self, *args: str) -> str:
        return subprocess.run(["swaymsg", "-s", self.socket(), *args], capture_output=True, text=True).stdout

    def click(self, x: int, y: int) -> None:
        # The seat has no mouse; a virtual pointer clicks like one.
        environment = {**os.environ, "WAYLAND_DISPLAY": self.display}
        subprocess.run([sys.executable, str(ROOT / "tests" / "virtual_pointer.py"), str(x), str(y),
                        str(WIDTH), str(HEIGHT)], env=environment, check=True, timeout=30)

    def type(self, text: str) -> None:
        # A virtual keyboard (wtype) gives the seat a keyboard and focus.
        environment = {**os.environ, "WAYLAND_DISPLAY": self.display}
        subprocess.run(["wtype", "-s", "500", text, "-s", "300"], env=environment, check=True, timeout=30)

    def has_window(self, title: str) -> bool:
        return f'"name": "{title}"' in self.command("-t", "get_tree")

    def screenshot(self, path: Path) -> Image.Image:
        environment = {**os.environ, "WAYLAND_DISPLAY": self.display}
        subprocess.run(["grim", str(path)], env=environment, check=True)
        return Image.open(path).convert("RGB")

    def stop(self) -> None:
        self.process.terminate()
        self.process.wait(10)


COMPOSITORS = {"sway": Sway}


class FakeHyprland:
    """Hyprland's IPC socket answering "j/cursorpos" with self.cursor
    (global logical pixels), so the dial's position "pointer" can be
    tested on sway (desktop/pointer.py)."""

    SIGNATURE = "turnpad_test"

    def __init__(self, runtime: Path, cursor):
        import socket
        import threading

        self.cursor = cursor
        self.requests = 0
        path = runtime / "hypr" / self.SIGNATURE / ".socket.sock"
        path.parent.mkdir(parents=True, exist_ok=True)
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(str(path))
        self._server.listen()
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try:
                connection, _ = self._server.accept()
            except OSError:
                return
            with connection:
                if connection.recv(64) == b"j/cursorpos":
                    self.requests += 1
                    connection.sendall(json.dumps({"x": self.cursor[0], "y": self.cursor[1]}).encode())

    def close(self):
        self._server.close()


def write_overlay(overlay: dict) -> None:
    config = Path.home() / ".config" / identity.CONFIG_DIR_NAME
    config.mkdir(parents=True, exist_ok=True)
    (config / "config.json").write_text(json.dumps({"overlay": overlay}))


def dial_box(view, scale=None) -> tuple[int, int, int, int]:
    """Where the dial is, in screen pixels (or scaled by scale)."""
    scale = SCALE if scale is None else scale
    rule = look.effective_look(view["appearance"], view["details"].get("look"))
    placed = look.overlay_placement({"width": WIDTH, "height": HEIGHT}, view["appearance"]["scale"],
                                    rule["position"], rule["custom"])
    box = placed["x"], placed["y"], placed["x"] + placed["width"], placed["y"] + placed["height"]
    return tuple(round(value * scale) for value in box)


def pointer_box(view):
    """The finger dot's square inside the dial's picture, in screen pixels."""
    placement = look.pointer_placement(view)
    if not placement:
        return None
    scale = view["appearance"]["scale"] * SCALE
    half = look.POINTER_SIZE / 2 + 1
    return tuple(round(value) for value in ((placement["x"] - half) * scale, (placement["y"] - half) * scale,
                                            (placement["x"] + half) * scale, (placement["y"] + half) * scale))


def background_pixels(image: Image.Image, box=None) -> int:
    """Pixels in box (default: all) that are not the target window's colour."""
    box = box or (0, 0, *image.size)
    plain = Image.new("RGB", (box[2] - box[0], box[3] - box[1]), BACKGROUND)
    return changed_pixels(image.crop(box), plain)


def main() -> int:
    global SCALE, WIDTH, HEIGHT
    compositor_name, output = sys.argv[1], Path(sys.argv[2])
    # Output scale: 2 is a HiDPI laptop panel at 200 % (the ProArt PX13).
    SCALE = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    WIDTH, HEIGHT = PIXELS[0] // SCALE, PIXELS[1] // SCALE
    output.mkdir(parents=True, exist_ok=True)
    runtime = Path(os.environ["XDG_RUNTIME_DIR"])
    print(f"== {compositor_name} at scale {SCALE}: reference pictures from dial.js", flush=True)
    cases_file = output / "cases.json"
    cases_file.write_text(json.dumps([{**entry, "pixelScale": SCALE} for entry in reference_cases()]))
    subprocess.run(["gjs", "-m", str(ROOT / "tests" / "render_dial_reference.js"), str(cases_file),
                    str(output / "reference")], check=True)

    compositor = COMPOSITORS[compositor_name](runtime, output)
    # The Hyprland signature only matters for position "pointer"; its socket
    # appears in the "near the pointer" checks.
    environment = {**os.environ, "WAYLAND_DISPLAY": compositor.display, "GSK_RENDERER": "cairo",
                   "GTK_A11Y": "none", "NO_AT_BRIDGE": "1", "HYPRLAND_INSTANCE_SIGNATURE": FakeHyprland.SIGNATURE}
    processes = []
    try:
        print("== target window", flush=True)
        target_log = output / "target.log"
        target_log.write_text("")
        processes.append(subprocess.Popen([sys.executable, "-c", TARGET, str(target_log)], env=environment))
        check(wait_for(lambda: compositor.has_window("target"), 15, "the target window"),
              "a window below the dial")

        print("== dial", flush=True)
        driver = FakeDriver()
        write_overlay(CASES[0]["overlay"])
        dial_log = open(output / "dial.log", "w")
        dial = subprocess.Popen([sys.executable, str(ROOT / "overlay" / "layer_shell.py")], env=environment,
                                stdout=dial_log, stderr=subprocess.STDOUT)
        processes.append(dial)
        wait_for(lambda: "running on" in (output / "dial.log").read_text(), 15, "the dial")
        pump(0.5)
        check(dial.poll() is None, "the dial runs")
        environ = Path(f"/proc/{dial.pid}/environ").read_bytes().split(b"\0")
        check(any(item.startswith(b"LD_PRELOAD=") and b"gtk4-layer-shell" in item for item in environ),
              "the dial restarted itself with gtk4-layer-shell preloaded")

        overlay = None
        for case in CASES:
            name = case["name"]
            if case["overlay"] != overlay:
                overlay = case["overlay"]
                write_overlay(overlay)
                pump(0.8)  # the dial reloads config.json 200 ms after a change
            driver.send(case["details"], case["signal"])
            pump(0.6)
            shot = compositor.screenshot(output / f"screen-{name}.png")
            box = dial_box(case_view(case))
            reference = Image.open(output / "reference" / f"{name}.png").convert("RGBA")
            expected = Image.new("RGBA", reference.size, BACKGROUND + (255,))
            expected.alpha_composite(reference)
            actual = shot.crop(box).convert("RGBA")
            actual.save(output / f"dial-{name}.png")
            # The finger dot is a layer of its own at a fractional position,
            # resampled between pixels like the Shell's actor; dial.js paints
            # it in place. It gets a looser comparison of its own.
            dot = pointer_box(case_view(case))
            if dot:
                actual_dot, expected_dot = actual.crop(dot), expected.crop(dot)
                blank = Image.new("RGBA", (dot[2] - dot[0], dot[3] - dot[1]))
                actual.paste(blank, dot[:2])
                expected.paste(blank, dot[:2])
                worst = max(ImageChops.difference(actual_dot, expected_dot).getextrema(), key=lambda pair: pair[1])[1]
                check(worst <= DOT_TOLERANCE, f"{name}: the finger dot matches (largest difference {worst})")
            pixels = changed_pixels(actual, expected)
            check(pixels is not None and pixels < MIN_PIXELS,
                  f"{name}: the dial on screen matches dial.js ({pixels} pixels differ)")
            outside = shot.copy()
            outside.paste(Image.new("RGB", (box[2] - box[0], box[3] - box[1]), BACKGROUND), box[:2])
            check(background_pixels(outside) == 0, f"{name}: nothing else on screen")

        print("== click-through, keys and focus", flush=True)
        menu = CASES[0]
        write_overlay(menu["overlay"])
        pump(0.8)
        driver.send(menu["details"], menu["signal"])
        pump(0.5)
        x0, y0, x1, y1 = dial_box(case_view(menu))
        left, top, right, _bottom = dial_box(case_view(menu), scale=1)
        centre = ((left + right) // 2, top + (right - left) // 2)  # logical, as windows see it
        before = target_log.read_text()
        compositor.click(*centre)
        pump(0.5)
        clicks = [line for line in target_log.read_text()[len(before):].splitlines() if line.startswith("click")]
        check(clicks == [f"click {centre[0]} {centre[1]}"], f"a click on the dial reaches the window below {clicks}")
        before = target_log.read_text()
        compositor.type("q")
        pump(0.5)
        typed = target_log.read_text()[len(before):]
        check("key q" in typed, "keys typed while the dial shows reach the window below")
        check("active True" in typed and "active False" not in typed.split("key q")[0],
              "the window below keeps the keyboard focus while the dial shows")

        print("== hiding after release", flush=True)
        released = list(menu["signal"])
        released[-1] = False
        driver.send(menu["details"], released)
        pump(0.5)
        shot = compositor.screenshot(output / "screen-released.png")
        check(background_pixels(shot, (x0, y0, x1, y1)) > 1000, "the dial lingers after release")
        pump(look.DEFAULT_APPEARANCE["hide_delay_ms"] / 1000 + look.FADE_OUT_MS / 1000 + 0.5)
        shot = compositor.screenshot(output / "screen-hidden.png")
        check(background_pixels(shot) == 0, "the dial is gone hide_delay_ms after release")

        print("== pill", flush=True)
        details = {**menu["details"], "look": {"visibility": "pill"}}
        volume = CASES[1]
        driver.send({**volume["details"], "look": {"visibility": "pill"}}, volume["signal"])
        pump(0.6)
        shot = compositor.screenshot(output / "screen-pill.png")
        mask = Image.new("RGB", shot.size, BACKGROUND)
        difference = ImageChops.difference(shot, mask).convert("L").point(lambda v: 255 if v > 12 else 0)
        bbox = difference.getbbox()
        check(bbox is not None, "the pill shows")
        if bbox:
            width, height = bbox[2] - bbox[0], bbox[3] - bbox[1]
            dial_centre = ((x0 + x1) / 2, y0 + (x1 - x0) / 2)
            pill_centre = ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
            check(width < 400 * SCALE and height < 80 * SCALE, f"the pill is small ({width}x{height})")
            near = 3 * SCALE
            check(abs(pill_centre[0] - dial_centre[0]) <= near and abs(pill_centre[1] - dial_centre[1]) <= near,
                  f"the pill sits where the dial's centre would be ({pill_centre} vs {dial_centre})")
        driver.send(details, menu["signal"])
        pump(0.6)
        shot = compositor.screenshot(output / "screen-pill-menu.png")
        hovered = ImageChops.difference(shot, mask).convert("L").point(lambda v: 255 if v > 12 else 0).getbbox()
        check(bool(bbox and hovered) and hovered[2] - hovered[0] < bbox[2] - bbox[0],
              f"the pill follows the state (the function under the finger: {hovered})")
        # The driver always sends a look; {} means the config's defaults.
        driver.send({**menu["details"], "look": {}}, menu["signal"])
        pump(0.6)
        shot = compositor.screenshot(output / "screen-back-to-dial.png")
        check(changed_pixels(shot.crop((x0, y0, x1, y1)), Image.open(output / "dial-menu-hover.png")) < MIN_PIXELS,
              "a function without the pill brings the dial back")

        print("== fade", flush=True)
        # Like the extension, fading starts with a new touch.
        fade = {**menu["details"], "look": {"visibility": "fade", "fade_opacity": 35}}
        driver.send(fade, released)
        pump(0.2)
        driver.send(fade, menu["signal"])
        pump((look.FADE_AFTER_MS + look.FADE_SLOW_MS) / 1000 + 0.4)
        shot = compositor.screenshot(output / "screen-faded.png")
        full = Image.open(output / "dial-menu-hover.png").convert("RGB")
        faded = shot.crop((x0, y0, x1, y1))
        plain = Image.new("RGB", full.size, BACKGROUND)
        expected = Image.blend(plain, full, 0.35)
        dimmed = changed_pixels(faded, expected)
        check(dimmed < 400, f"visibility fade dims the dial to fade_opacity while touching ({dimmed} pixels differ)")

        print("== near the pointer", flush=True)
        hide_time = look.DEFAULT_APPEARANCE["hide_delay_ms"] / 1000 + look.FADE_OUT_MS / 1000 + 0.6

        def hide_fully(details):
            driver.send(details, released)
            pump(hide_time)

        def dial_at(name, box, message):
            shot = compositor.screenshot(output / f"screen-{name}.png")
            pixels = changed_pixels(shot.crop(box), full)
            outside = shot.copy()
            outside.paste(Image.new("RGB", (box[2] - box[0], box[3] - box[1]), BACKGROUND), box[:2])
            check(pixels is not None and pixels < MIN_PIXELS and background_pixels(outside) == 0,
                  f"{message} ({pixels} pixels differ, {background_pixels(outside)} outside)")

        near = {**menu["details"], "look": {"position": "pointer"}}
        hide_fully(near)
        # No compositor answer (no Hyprland socket yet): "lower".
        driver.send(near, menu["signal"])
        pump(0.6)
        dial_at("pointer-unknown", (x0, y0, x1, y1), "without a pointer position the dial shows at lower")
        hide_fully(near)
        hyprland = FakeHyprland(runtime, (100, 60))
        try:
            driver.send(near, menu["signal"])
            pump(0.6)
            appearance_scale = look.load_appearance(menu["overlay"])["scale"]

            def beside(pointer, gap):
                placed = look.overlay_placement({"width": WIDTH, "height": HEIGHT}, appearance_scale, "pointer",
                                                None, pointer, "below-right", gap)
                box = placed["x"], placed["y"], placed["x"] + placed["width"], placed["y"] + placed["height"]
                return tuple(round(value * SCALE) for value in box)

            check(hyprland.requests == 1, f"the pointer is asked once when the dial shows ({hyprland.requests})")
            dial_at("pointer", beside((100, 60), 24), "the dial shows below right of the pointer")
            # The pointer moves and the look changes while the dial shows:
            # it keeps the pointer from when it appeared.
            hyprland.cursor = (700, 400)
            driver.send({**near, "look": {"position": "pointer", "pointer_gap": 60}}, menu["signal"])
            pump(0.6)
            check(hyprland.requests == 1, f"a visible dial does not ask again ({hyprland.requests})")
            dial_at("pointer-gap", beside((100, 60), 60), "a look change keeps the pointer from when it appeared")
        finally:
            hyprland.close()

        check(dial.poll() is None, "the dial is still running")
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(5)
            except subprocess.TimeoutExpired:
                process.kill()
        compositor.stop()

    print("== no layer-shell: a clear message and exit status 3", flush=True)
    without = {key: value for key, value in os.environ.items() if key != "WAYLAND_DISPLAY"}
    run = subprocess.run([sys.executable, str(ROOT / "overlay" / "layer_shell.py")], env=without,
                         capture_output=True, text=True, timeout=30)
    check(run.returncode == 3 and "layer-shell" in run.stderr, f"exit {run.returncode}: {run.stderr.strip()}")

    if failures:
        print(f"\n{len(failures)} check(s) failed; pictures in {output}")
        return 1
    print(f"\n== layer-shell dial on {compositor_name}: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
