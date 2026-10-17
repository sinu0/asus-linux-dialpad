# Architecture

Turnpad is a set of separately running parts that talk over the session D-Bus and share one JSON file. Only the outer layer depends on the desktop.

```
 touchpad (evdev) ─► dialpad.py ──────────► uinput keys, scroll, media keys
                      │   ▲   ▲
     focused window ──┘   │   └── config.json  ◄── config_app/ (settings, GTK4)
     desktop/active_window│                         │
                          │                         │ ReloadConfig
                 dialpad_dbus.py  ◄─────────────────┘
                          │  OverlayState / OverlayDetails signals
                          ▼
          on-screen dial frontend (per desktop)
          · GNOME: gnome/extension/ (dial.js)
          · others: dialpad_ui.py (legacy window)
```

| Part | Desktop-specific? | Where |
|---|---|---|
| Touch input, gestures, actions | No | `dialpad.py`, `dial_gesture.py` |
| Configuration model, presets, skins | No | `config/` |
| D-Bus service | No (session bus) | `dialpad_dbus.py` |
| Settings app | No (GTK4 runs everywhere) | `config_app/` |
| Focused application | **Yes**, one backend each | `desktop/active_window.py` |
| Light/dark preference | No (XDG portal, gsettings fallback) | `desktop/color_scheme.py` |
| On-screen dial | **Yes**, one frontend each | `gnome/extension/`, `dialpad_ui.py` |
| Dial painting | No (Cairo) | `gnome/extension/dial.js`, `overlay/painter.py` |
| Installing the frontend | **Yes**, one case each | `install_overlay.sh` |

## Names and identifiers

`config/identity.py` holds the display name and every technical identifier (D-Bus name and path, settings app id, config directory, extension UUID, install directory); `install_paths.sh` is its shell twin and also holds every installed path. Each identifier has twins in JavaScript, JSON and `.desktop` files; `tests/test_identity.py` fails when they drift apart. Changing a technical identifier breaks existing installs (their config directory and running extension), so it also needs a step in `install_migrate.sh`, like the one from the old `asus-dialpad-driver` names.

## Adding a desktop environment

Turnpad supports GNOME only for now. A new desktop starts with a [desktop support request](https://github.com/sinu0/asus-turnpad/issues/new?template=desktop-support.yml), ideally from someone who can test on it.

Three integration points, all optional. The driver already works everywhere evdev and uinput do.

### 1. Focused application

Add a function to `desktop/active_window.py`:

```python
# "example-ctl" stands for the compositor's own command-line tool.
@backend("example", ("wayland",))
def example(context: Context) -> WindowInfo:
    window = json.loads(_output(["example-ctl", "focused-window", "--json"]))
    return binary_from_pid(window["pid"]), window["title"]
```

It returns `(binary path, title)` or raises. Backends are tried in registration order and dropped after `max_failures` errors. A frontend that knows the focused app itself can push it instead, like the GNOME extension: call `SetActiveApplication(desktop_id)` on the D-Bus service.

### 2. On-screen dial

A frontend is a transparent, click-through window or layer above all others that does three things:

1. Subscribes to `OverlayState` and `OverlayDetails` on `io.github.sinu0.AsusTurnpad.Driver`. Call `GetOverlayDetails()` once at start. The signal contract is in `AGENTS.md`.
2. Reads the `overlay` section of `~/.config/asus-turnpad/config.json` (scale, position, hide delay, hints, pointer, accent, skin, skin_light, follow_system_style) and reloads it when the file changes.
3. Paints with `overlay.painter.paint_dial()` (Python and Cairo; icons through `overlay.gtk_icons.draw_icon` in GTK) or with `gnome/extension/dial.js` (GJS). Skins then work without extra code.

On wlroots compositors, KDE Plasma and COSMIC, `gtk4-layer-shell` gives such a surface without stealing focus or appearing in Alt-Tab. GNOME needs the Shell extension, because Mutter has no layer-shell.

Show the dial while `touching` is true and fade it out `hide_delay_ms` after release. With `follow_system_style`, pick `skin_light` when `desktop.color_scheme.ColorScheme().prefers_dark()` is false.

### 3. Installer

Add a case to `install_overlay.sh` that sources an `install_<desktop>_overlay.sh`, and the matching removal to `uninstall.sh`. Distribution packages (`packaging/`) install the frontend's files system-wide, and `packaging/asus-turnpad-setup` enables it per user.

## Keeping the two painters in sync

`gnome/extension/dial.js` (GJS, inside GNOME Shell) and `overlay/painter.py` (Python, everywhere else and in the settings app) draw the same dial. Change both together, then compare the results:

```
python3 tools/update_previews.py   # preview/overlay-*.png from dial.js, settings pages (dial from painter.py)
```

Skin resolution has the same pairing: `resolveSkin()` in `dial.js` and `resolve_skin()` in `config/skins.py`.

## Rendering cost

The dial has to stay smooth on battery without measurable CPU or GPU use. The arithmetic per driver signal (a sine and cosine for the finger dot, comparing the shown state) takes microseconds; what costs is rasterising with Cairo. A full `paintDial()` takes about 6 ms per frame at 2x pixel density (GNOME renders 150 % scaling at 2x), mostly the shadow and gradients that never change while the dial is shown.

The GNOME extension therefore paints in three layers that the compositor puts together (`gnome/extension/layers.js`, described at the top of the file):

| Layer | Painted when | Cost |
|---|---|---|
| Background: shadow, disc, rim | skin, scale or size changes | once |
| Content: menu or gauge, centre, hints | `contentKey()` changes (value, function, menu) | about 0.6 ms; the centre disc is a cached image |
| Finger dot | its colour changes | moving it paints nothing |

The overlay actor is only as large as the dial, so its fade does not composite the whole screen. The driver sends the finger angle in `POINTER_STEP_DEGREES` steps (at most once per touch frame). `paintDial()` remains the one-call version for the README pictures and produces the same pixels.
