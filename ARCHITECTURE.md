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
          · layer-shell compositors: overlay/layer_shell.py (painter.py)
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
| On-screen dial | **Yes**, one frontend each | `gnome/extension/`, `overlay/layer_shell.py`, `dialpad_ui.py` |
| What the dial shows, where and when | No (pure Python twins of the JavaScript) | `overlay/look.py`, `overlay/visibility.py` |
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

On wlroots compositors, KDE Plasma and COSMIC, `gtk4-layer-shell` gives such a surface without stealing focus or appearing in Alt-Tab; `overlay/layer_shell.py` is that frontend (below). GNOME needs the Shell extension, because Mutter has no layer-shell.

Show the dial while `touching` is true and fade it out `hide_delay_ms` after release. With `follow_system_style`, pick `skin_light` when `desktop.color_scheme.ColorScheme().prefers_dark()` is false.

#### The layer-shell frontend

`overlay/layer_shell.py` (run with the system `python3`, as a script or `python3 -m overlay.layer_shell`) is the dial for every compositor with layer-shell: KDE Plasma 6, Hyprland, sway, niri, COSMIC. It restarts itself once with `gtk4-layer-shell` in `LD_PRELOAD` (the library must load before `libwayland-client`) and exits with status 3 where there is no layer-shell (GNOME, X11). `overlay/frontend.py` holds its GTK 4 windows: two surfaces on the overlay layer (the dial and the pill), no keyboard interactivity, an empty input region so clicks reach the window below, placed against the whole output with `overlayPlacement()`'s margins. Wayland does not say where the pointer is, so the compositor chooses the output (the focused one); the dial is unmapped between touches, so each touch chooses again, and `--output NAME` pins it.

It reproduces the extension piece by piece, so both desktops show the same dial:

| Extension (JavaScript) | Layer-shell frontend (Python) |
|---|---|
| `overlayPlacement()`, `effectiveLook()`, `pillContent()`, `pillPlacement()`, `iconLayout()`, `pointerPlacement()`, `contentKey()` in `dial.js` | `overlay/look.py` |
| appearance, `OverlayState` and `OverlayDetails` handling in `extension.js` | `overlay/look.py` (`load_appearance()`, `apply_overlay_state()`, `merge_details()`) |
| `_updateVisibility()`, `_show()`, `_hide()`, fade timers in `extension.js` | `overlay/visibility.py` |
| `paintBackground()`, `paintContent()`, `paintPointer()` and the icon actors | `paint_background()`, `paint_content()`, `paint_pointer()` in `overlay/painter.py` |
| `layers.js` | `DialLayers` in `overlay/frontend.py`: each layer keeps its picture as a Cairo image until its key changes |

`tests/test_overlay_look.py` runs the `dial.js` functions in gjs and compares them with `look.py`; `tests/test_live_painter.py` compares the painting with `dial.js` pixel by pixel. `tests/layer_shell_in_container.sh` runs the frontend on headless sway in a container with a fake driver on a private bus and compares screenshots with `dial.js` (also at output scale 2), clicks and types through the dial and checks hiding, the pill and the fade.

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

The layer-shell frontend has the same three layers (`DialLayers` in `overlay/frontend.py`). The overlay actor (or layer surface) is only as large as the dial, so its fade does not composite the whole screen. The driver sends the finger angle in `POINTER_STEP_DEGREES` steps (at most once per touch frame). `paintDial()` remains the one-call version for the README pictures and produces the same pixels.
