# AGENTS.md – ASUS DialPad Driver

## Workflow / architecture

- **Name:** the project is shown as **Turnpad** (`config/identity.py`). Technical identifiers (D-Bus `io.github.asuslinuxdrivers.DialPad`, `/usr/share/asus-dialpad-driver`, `~/.config/asus-dialpad`, extension UUID) are unchanged for compatibility; "DialPad" in docs names the ASUS hardware feature.
- **Root:** Single-repo, single-app. No monorepo, no build steps, no CI; unit tests in `tests/`.
- **Entrypoints:**
  - `dialpad.py` – main driver daemon, ~3000 lines, monolithic. Runs from systemd `asus_dialpad_driver@.service` via a Python venv at `/usr/share/asus-dialpad-driver/.env`.
  - `dialpad_ui.py` – legacy PySide6 overlay, separate `asus_dialpad_driver_ui@.service`. On GNOME replaced by `gnome/extension/`.
  - `install.sh` – interactive bash installer, sources sub-scripts from repo root.
- **Install target:** `/usr/share/asus-dialpad-driver/`. Source and installed versions can diverge; diff before debugging.
- **Fork additions:**
  - `dialpad_dbus.py` – session D-Bus service (`io.github.asuslinuxdrivers.DialPad`), signal `OverlayState(bsasasidsbbb)`.
  - `dial_gesture.py` – pure gesture maths (angle, slices, `RotationTracker`), no hardware imports; unit tested.
  - `tests/` – `unittest` suite for gesture maths, legacy adapter and D-Bus overlay state.
  - `config/` – JSON config model, macro runtime, legacy adapter, migration from old `dialpad_dev` INI + `layouts/*.py`.
  - `config/presets.py` – ASUS Dial-style function library and pre-programmed app packs (browser, GIMP, Krita, Inkscape, Blender, Kdenlive, Resolve, LibreOffice, code editors, Spotify, video players); `suggested_color()` colours functions without one.
  - `config/labels.py` – key/macro labels shared by the GUI and the overlay hints (includes the evdev code table for old numeric keys).
  - `config_app/` – GTK4/Libadwaita settings GUI (`io.github.asuslinuxdrivers.DialPadControl`).
  - `gnome/extension/` – GNOME Shell 50 extension (`dialpad@asus-linux-drivers`), renders radial dial natively. `dial.js` holds all painting and imports only `cairo` (shared with `tools/`); `extension.js` owns actors, D-Bus and config watching; `layers.js` paints in three layers (background, content, finger dot) that repaint only when their look changes, see "Rendering cost" in `ARCHITECTURE.md`. Every extension file must be listed in `install.sh` and `install_gnome_extension.sh` (`tests/test_install.py`).
  - `gnome/extension/skins.json` – built-in skins (`glass`, `midnight`, `frost`, `proart`, `classic`); user skins are `~/.config/asus-dialpad/skins/<id>.json`. Format and AI workflow in `SKINS.md`.
  - `config/skins.py` – loads/resolves skins in Python (mirrors `resolveSkin()` in `dial.js`, keep both in sync); `PALETTE_KEYS` drives the editor, `SKINS.md` and the AI prompt.
  - `overlay/painter.py` – toolkit-free Cairo port of `dial.js` (settings app previews now, overlays on other desktops later); icons come through a callback, `overlay/gtk_icons.py` for GTK. Keep geometry in sync with `dial.js`.
  - `desktop/` – everything that differs per desktop on the Python side: `active_window.py` (focused-window backends registered with `@backend`, tried in order) and `color_scheme.py` (light/dark via the XDG portal, gsettings fallback).
  - `config/identity.py` – display name (`Turnpad`) and all technical identifiers; `tests/test_identity.py` checks their twins in JS, JSON, `.desktop` and shell files.
  - `install_overlay.sh` – picks the on-screen dial frontend per desktop (GNOME → `install_gnome_extension.sh`).
  - `ARCHITECTURE.md` – component map and how to add a desktop environment.
  - `tools/` – `render_overlay_preview.js` (gjs, paints `preview/overlay-*.png` with `dial.js`) and `screenshot_settings.py` (opens the app on a demo config, saves `preview/settings-*.png`; never writes the user's config).
  - `install_gnome_extension.sh` – sourced by `install.sh`.

## Developer commands

- **Unit tests:** `python3 -m unittest discover -s tests -v`
- **Syntax check driver:** `python3 -c "import ast; ast.parse(open('dialpad.py').read())"`
- **Check all Python:** `python3 -m compileall -q config config_app desktop overlay tools dialpad_dbus.py`
- **Verify bash scripts:** `bash -n install.sh install_gnome_extension.sh`
- **Smoke test config:** `python3 -m config.runtime && python3 -m config.legacy_adapter`
- **Validate GNOME extension (outside Shell):** `gjs -m gnome/extension/extension.js` – will fail with resource import errors because `resource:///org/gnome/shell/ui/main.js` only exists inside the shell process; that is expected and confirms ESM syntax is valid.
- **Desktop file validate:** `desktop-file-validate config_app/io.github.asuslinuxdrivers.DialPadControl.desktop`
- **Regenerate README pictures:** `gjs -m tools/render_overlay_preview.js && python3 tools/screenshot_settings.py` (the second one briefly opens a window).
- **Test D-Bus service standalone:** `python3 dialpad_dbus.py` – starts, emits one invisible state, exits.

## Key environment facts

- **System:** CachyOS (Arch-based), GNOME Shell 51 (extension metadata lists 50 and 51), Wayland, Python 3.14, GTK 4.22, Libadwaita 1.9.
- **Laptop:** ASUS ProArt PX13 HN7306WV. Touchpad `ASCF1A00:00 2808:0220` (min-max x 0-4010, y 0-2443).
- **Layout:** `proartp16` used as fallback. Geometry in legacy layout may not match PX13 — needs calibration.
- **Venv packages:** `dbus-python` must be in the driver venv for D-Bus to work. It is declared in `requirements.txt`; the current installed venv has version 1.4.0.

## GNOME Shell extension lifecycle

- GNOME Shell **does not reload extension code** on disable/enable; a full Shell restart (logout/login) is required after code changes.
- `gnome-extensions enable` will report ERROR until Shell has loaded the extension once.
- Use `gdbus call --session --dest org.gnome.Shell --object-path /org/gnome/Shell --method org.gnome.Shell.Extensions.GetExtensionErrors 'dialpad@asus-linux-drivers'` to read errors.
- `import * as Main` (named), not `import Main from` (default) for `resource:///org/gnome/shell/ui/main.js`.
- Extension replaces `asus_dialpad_driver_ui@.service` on GNOME; the config app calls `ReloadConfig` via D-Bus after saving.

## D-Bus contract

| Item | Value |
|---|---|
| Bus name / Interface | `io.github.asuslinuxdrivers.DialPad` |
| Object path | `/io/github/asuslinuxdrivers/DialPad` |
| Signal | `OverlayState` – signature `bsasasidsbbb` (enabled, title, titles, icons, value, value_angle_start, unit, center_pressed, value_show_only_progress, touching) – keep it fixed for older extensions |
| Signal | `OverlayDetails(s)` – JSON: profile, mode (`multi`/`single`), colors[] (menu order), color, hints {cw, ccw, center}, hold_returns, pointer (degrees, -1 = none). Emitted before `OverlayState` in the same idle callback. Driver sends it via `send_to_socket({"details": {...}})`; details-only payloads emit no `OverlayState`. |
| Signal | `CalibrationProgress(s)` – JSON from `CalibrationSession.state()` plus layout, touchpad_max_x/y and the latest `point` |
| Methods | `SetActiveApplication(s)`, `GetStatus()`, `GetOverlayDetails() -> s`, `ReloadConfig()`, `StartCalibration() -> b`, `CancelCalibration() -> b` |

## Config migration behavior

- First launch of `DialPad Control` app migrates old `dialpad_dev` INI + `layouts/proartp16.py` into `~/.config/asus-dialpad/config.json`.
- If JSON exists, migration is skipped. To re-migrate: delete the JSON file first.
- The driver loads JSON config at startup if it exists; otherwise falls back to legacy layout Python.
- Macros (`MacroStep` list) appear as `{"macro": [...]}` inside legacy `app_shortcuts` dict entries. `emulate_shortcuts()` handles them before legacy key/command logic.

## Profiles and dial behaviour (ASUS Dial parity)

- Profile fields: `mode` (`multi` radial menu / `single` bound function + `single_function`), `sensitivity` (divides rotation thresholds), `scroll_speed` (multiplies scroll units), `remember_last`.
- Segment fields: `enabled`, `color`. MacroStep scroll fields: `axis` (`horizontal`), `modifiers` (keys held while scrolling, e.g. Ctrl = zoom). Never reuse a scroll step's legacy `keys` (old configs contain junk like `["8","11"]`).
- The legacy adapter puts profile settings under the reserved `_meta` key; `is_multifunction()` skips keys starting with `_`. Single mode uses the flat `clockwise/counterclockwise/center` layout with `_meta.single` holding title/treshold/value/unit/color/hints.
- In a selected function: tap centre = the function's `macro_center` if any, otherwise back to menu; holding the centre for `gesture.center_hold_time` returns to the menu (fires while still touching).
- `last_function_by_app` restores the last function on activation and focus change; returning to the menu forgets it. A focus change to another app never keeps the previous app's function.
- `overlay` section of config.json (scale, position, hide_delay_ms, show_hints, show_pointer, accent, skin, skin_light, follow_system_style) is read directly by the Shell extension through a directory monitor (also on the skins directory); the driver does not use it except `show_pointer`. With `follow_system_style` the extension uses `skin_light` unless `org.gnome.desktop.interface color-scheme` is `prefer-dark`.
- `tests/test_driver_state.py` extracts the state functions from `dialpad.py` via AST; keep their names in `STATE_FUNCTIONS` in sync when renaming.

## Guided calibration and other models

- `dial_gesture.CalibrationSession` (pure, tested) fits the outer ring and the centre button from finger traces (`fit_circle`, `angular_coverage`). The driver routes whole touch frames to it while `calibration` is set and skips activation and dial actions; send-events are disabled meanwhile.
- The settings app applies the result and stores `device_name` = layout; `apply_gui_settings()` ignores JSON geometry whose `device_name` differs from the running layout.
- First-run migration detects the layout via `GetStatus()` or the `dialpad.py` process arguments — never hard-code `proartp16`.
- `details` payloads never go to the Unix socket (the PySide overlay `dialpad_ui.py` reads newline-delimited JSON and applies only the keys present).
- See `PORTING.md` for the user-facing steps.

## Touch input pipeline

- Frame-based processing in `listen_touchpad_events()`: events buffered per slot, gesture logic runs once per `SYN_REPORT`.
- Global state mutation is serialised through `driver_state_lock` and `process_pending_driver_updates()` called at start of each frame.
- Per-frame recalculations of `circle_radius` and bounds allow live calibration changes.
- Constants: `DEBOUNCE_MS=30`, `SETTLE_FRAMES=3`; hysteresis comes from `gesture.hysteresis` in JSON (default 3 without JSON).
- `RotationTracker.reset()` must run on touch down, lift, centre and leaving the ring, or the next touch jumps.
- `finger_down` follows the one finger the dial tracks (`dial_touch_id`, chosen by `dial_gesture.select_dial_touch`): the touch already followed, else the newest touch inside the ring or on the corner icon. Other fingers, a resting palm and touches reported as `MT_TOOL_PALM` are ignored, and lifting the tracked finger counts as release even while others stay down. Never clear `slots` on release; `update_touch_slots()` keeps them in sync (also from `d_t.sync()` after `SYN_DROPPED`).
- Actions, shell macros and value queries run on the `dialpad-actions` worker thread via `enqueue_action()`; never call subprocesses from the touch loop.
- The GNOME overlay shows while `touching`, and fades out 1.5 s after release.

## Formatting

- `dialpad.py` uses CRLF line endings (DOS format). Adding code with LF endings triggers `git diff --check` whitespace warnings. Use `unix2dos dialpad.py` after editing if needed.
- Other files use standard LF.
