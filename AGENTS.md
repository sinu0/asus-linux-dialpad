# AGENTS.md – ASUS DialPad Driver

## Workflow / architecture

- **Name:** the project is shown as **Turnpad**; the technical name is `asus-turnpad`. All identifiers live in `config/identity.py` (Python) and `install_paths.sh` (shell); `tests/test_identity.py` keeps them and their JS/JSON/.desktop twins in sync. "DialPad" in docs names the ASUS hardware feature.
- **Supported desktops:** GNOME only for now. Other desktops start with an issue (`.github/ISSUE_TEMPLATE/desktop-support.yml`); do not add one unasked.
- **Before the rename** the project was installed as `asus-dialpad-driver` (`/usr/share/asus-dialpad-driver`, `~/.config/asus-dialpad`, D-Bus `io.github.asuslinuxdrivers.DialPad`, extension `dialpad@asus-linux-drivers`, services `asus_dialpad_driver@$USER`). `install_migrate.sh` moves settings and removes those leftovers on every install and uninstall.
- **Root:** Single-repo, single-app. No monorepo, no build steps; unit tests in `tests/`.
- **CI:** `.github/workflows/tests.yml` on GitHub Actions (every push and pull request) runs in an `archlinux:latest` container (Ubuntu's GTK/Libadwaita are too old): unit tests including the headless-mutter layout test, syntax checks, and `update_previews.py --check --only overlay`; job `arch-package` runs `packaging/arch/test-package.sh` (builds the Arch package from the commit, installs, checks files and imports, removes). Settings pictures are only rendered and attached to the run (artifact `rendered-pictures`): they show the apps installed on the desktop that renders them (Krita, Firefox, darktable icons), so they are updated locally.
- **Entrypoints:**
  - `dialpad.py` – main driver daemon, ~3000 lines, monolithic. Runs as the user service `asus-turnpad.service` via a Python venv at `/opt/asus-turnpad/.env`.
  - `dialpad_ui.py` – legacy PySide6 overlay, separate `asus-turnpad-ui.service`. On GNOME replaced by `gnome/extension/`.
  - `install.sh` – bash installer for every distribution (unattended; `--interactive` asks), sources sub-scripts from repo root. Refuses to run while the Arch package is installed.
  - `packaging/` – distribution packages: `arch/PKGBUILD` (`asus-turnpad-git`, builds the latest GitHub commit; deps from the Arch repos, no venv), static user unit `asus-turnpad.service` (layout `auto`), udev rules (uaccess + groups), modules-load, sysusers, and `asus-turnpad-setup` (per-user: groups, enable service and extension; refuses while an `install.sh` install exists). `arch/build.sh` runs `makepkg -si` in `~/.cache/asus-turnpad/makepkg` (makepkg rewrites `pkgver` in the PKGBUILD it uses, which would dirty the clone); `arch/test-package.sh` tests it in a clean container. Users read `INSTALL.md`.
- **Install target:** `install.sh` → `/opt/asus-turnpad/` with a venv, owned by root (FHS layout in `install_paths.sh`); Arch package → `/usr/share/asus-turnpad` (`identity.PACKAGE_DIR`), system Python. Code must not assume either path (it finds files next to itself). User data: `~/.config/asus-turnpad/` (`config.json`, `skins/`, driver state `dialpad_dev`). Source and installed versions can diverge; diff before debugging.
- **Fork additions:**
  - `layout_detect.py` – layout for this laptop from `laptop_touchpad_dialpad_layouts.csv` (product name, then touchpad vendor/product id; fallback `proartp16`). `dialpad.py auto` uses it; `install_layout_auto_suggestion.sh` runs it as a script. Nix packaging was removed (stale, old names).
  - `dialpad_dbus.py` – session D-Bus service (`io.github.sinu0.AsusTurnpad.Driver`), signal `OverlayState(bsasasidsbbb)`.
  - `dial_gesture.py` – pure gesture maths (angle, slices, `RotationTracker`), no hardware imports; unit tested.
  - **Security:** services keep `NoNewPrivileges=yes` (dial commands must never reach root, the user may have passwordless sudo); the driver needs no privileges (I2C via group, hidraw via uaccess). `config.schema.shell_commands()` lists commands of imported profiles and the app asks before importing them. Skins must stay data only.
  - `launch.py` – runs Command/Shell steps: in their own `systemd-run --user --scope` (they survive driver restarts), waiting at most 2 s so a program with a window never blocks the action thread. Functions with no turning actions are launchers: `select_multifunction_segment()` runs their tap action straight from the menu (library category "Launch").
  - `backlight.py` – DialPad light brightness: `commands_for_level()` (0 = light off while the dial works, 1–8 = values `0x41`–`0x48` after `0x01`) and `KeyboardBacklight` (UPower `KbdBacklight` on the system bus, keyboard off = light off; change signals arrive in the D-Bus service's GLib loop). Config section `backlight` (`follow_keyboard`, `level`); the driver applies it through `apply_backlight()` on the action thread, never on the touch thread.
  - `tests/` – `unittest` suite for gesture maths, legacy adapter and D-Bus overlay state.
  - `config/` – JSON config model, macro runtime, legacy adapter, migration from old `dialpad_dev` INI + `layouts/*.py`.
  - `config/presets.py` – ASUS Dial-style function library and pre-programmed app packs (browser, GIMP, Krita, Inkscape, Blender, Kdenlive, Resolve, LibreOffice, code editors, Spotify, video players); `suggested_color()` colours functions without one.
  - `config/profile_share.py` – profiles as text: `PROFILE_FORMAT` + `ai_prompt()` for assistants, `profiles_from_text()` reads an answer, a profile or an export file (normalises key names via `labels.parse_keys`, raises `ProfileTextError` with a readable reason); used by Dial Controls › Build with AI and by file import. Keep `PROFILE_FORMAT` in sync with the schema.
  - `config/labels.py` – key/macro labels shared by the GUI and the overlay hints (includes the evdev code table for old numeric keys); `parse_keys()`/`keys_to_text()` read and write typed shortcuts ("Ctrl+F12"); `ICON_RULES` must match `dial.js` (`tests/test_labels.py`), `ICON_CHOICES` feeds the icon picker.
  - `config_app/` – GTK4/Libadwaita settings GUI (`io.github.sinu0.AsusTurnpad`).
  - `gnome/extension/` – GNOME Shell 45–51 extension (`asus-turnpad@sinu0.github.io`), renders radial dial natively. `dial.js` holds all painting and imports only `cairo` (shared with `tools/`); `extension.js` owns actors, D-Bus and config watching; `layers.js` paints in three layers (background, content, finger dot) that repaint only when their look changes, see "Rendering cost" in `ARCHITECTURE.md`. Every extension file must be listed in `install.sh` and `install_gnome_extension.sh` (`tests/test_install.py`).
  - `gnome/extension/skins.json` – built-in skins (`glass`, `midnight`, `frost`, `proart`, `classic`); user skins are `~/.config/asus-turnpad/skins/<id>.json`. Format and AI workflow in `SKINS.md`.
  - `config/skins.py` – loads/resolves skins in Python (mirrors `resolveSkin()` in `dial.js`, keep both in sync); `PALETTE_KEYS` drives the editor, `SKINS.md` and the AI prompt. Skins also carry `shape` (`DIAL_SHAPES`), `outline` (custom polar outline, points clamped by `outline_limit()` to the dial square), `tile`, `tileSize` and `background` (PNG next to the skin file; loaders add the private `__dir` key, `without_private_keys()` strips it before saving). Shape paths exist twice: `shapePath`/`tilePath` in `dial.js` and `shape_path`/`_tile_path` in `overlay/painter.py`; `tests/test_skins.py` checks the shared lists and limits.
  - `config_app/outline_editor.py` – the drag-the-points outline editor (polar grid, snapping, mirror, presets).
  - `overlay/painter.py` – toolkit-free Cairo port of `dial.js` (settings app previews now, overlays on other desktops later); icons come through a callback, `overlay/gtk_icons.py` for GTK. Keep geometry in sync with `dial.js`.
  - `desktop/` – everything that differs per desktop on the Python side: `active_window.py` (focused-window backends registered with `@backend`, tried in order) and `color_scheme.py` (light/dark via the XDG portal, gsettings fallback).
  - `config/identity.py` – display name (`Turnpad`) and all technical identifiers; `tests/test_identity.py` checks their twins in JS, JSON, `.desktop` and shell files.
  - `install_overlay.sh` – picks the on-screen dial frontend per desktop (GNOME → `install_gnome_extension.sh`).
  - `install_paths.sh` – every installed path and name for the shell scripts (FHS: `/opt`, `~/.config`, `/etc/udev/rules.d`, `/etc/modules-load.d`, `/var/log`); scripts source it and never set their own defaults (`tests/test_identity.py`). The program directory is root-owned: install Python packages with `venv_pip`, never write to it at runtime.
  - `install_migrate.sh` – moves installs from before the rename (see Name above).
  - `uninstall.sh` – removes everything installed plus pre-rename leftovers; keeps `~/.config/asus-turnpad` unless confirmed with `--interactive`.
  - `ARCHITECTURE.md` – component map and how to add a desktop environment.
  - `examples/skins/` – example user skin (`gertie.json` + public-domain `gertie.png`); `tools/render_overlay_preview.js` paints it into `preview/overlay-example.png`, `tests/test_skins.py` loads it.
  - `README.md` shows only the main pictures and the example skin; all others are in `GALLERY.md`.
  - `tools/` – `render_overlay_preview.js` (gjs, paints `preview/overlay-*.png` with `dial.js`), `screenshot_settings.py` (opens the app on a demo config, saves `preview/settings-*.png`; never writes the user's config), `update_previews.py` (runs both, keeps unchanged pictures) and `git-hooks/pre-push`.
  - `install_gnome_extension.sh` – sourced by `install.sh`.

## Developer commands

- **Unit tests:** `python3 -m unittest discover -s tests -v`
- **Syntax check driver:** `python3 -c "import ast; ast.parse(open('dialpad.py').read())"`
- **Check all Python:** `python3 -m compileall -q config config_app desktop overlay tools dialpad_dbus.py`
- **Verify bash scripts:** `bash -n install*.sh uninstall.sh`
- **Smoke test config:** `python3 -m config.runtime && python3 -m config.legacy_adapter`
- **Validate GNOME extension (outside Shell):** `gjs -m gnome/extension/extension.js` – will fail with resource import errors because `resource:///org/gnome/shell/ui/main.js` only exists inside the shell process; that is expected and confirms ESM syntax is valid.
- **Desktop file validate:** `desktop-file-validate config_app/io.github.sinu0.AsusTurnpad.desktop`
- **README pictures:** `python3 tools/update_previews.py` renders everything in `preview/` and replaces only pictures that really changed (rendering noise stays below a tolerance, so unchanged pictures are not re-committed); `--check` only reports. Run it before every push that touches the extension, settings app, painters or skins and commit the changed pictures. The settings app renders in a headless mutter (own D-Bus session, virtual 2560×1600 monitor), so no window appears and focus cannot spoil the pictures; `--visible` opens it on the desktop instead. `tools/git-hooks/pre-push` enforces it once enabled with `git config core.hooksPath tools/git-hooks` (skip once: `SKIP_PREVIEWS=1 git push`). Pictures never read the desktop's settings (`GSETTINGS_BACKEND=memory`, `ScreenshotApp` pretends a dark desktop); `--only overlay` compares only those pictures, `--output DIR` keeps everything rendered.
- **Overlay on monitors 1080p–4K:** `tests/test_overlay_placement.py` runs `overlayPlacement()` from `dial.js` in gjs for common monitors and GNOME scale factors (logical pixels; the PX13 at 200 % is 1440×900); the dial must stay on screen and top ≤ center ≤ lower ≤ bottom.
- **Settings app layout 1080p–4K:** `tests/test_settings_layout.py` runs `tests/layout_probe.py` in one headless mutter per window size, in parallel (~9 s); it visits every page and the main dialogs and fails on widgets past the window edge, a window that cannot shrink to the size, or GTK warnings. Add new pages to `PAGES` and new dialogs to `dialogs()` there.
- **Test D-Bus service standalone:** `python3 dialpad_dbus.py` – starts, emits one invisible state, exits.

## Key environment facts

- **System:** CachyOS (Arch-based), GNOME Shell 51 (extension metadata lists 50 and 51), Wayland, Python 3.14, GTK 4.22, Libadwaita 1.9.
- **Laptop:** ASUS ProArt PX13 HN7306WV. Touchpad `ASCF1A00:00 2808:0220` (min-max x 0-4010, y 0-2443).
- **Layout:** `proartp16` used as fallback. Geometry in legacy layout may not match PX13 — needs calibration.
- **Venv packages:** `dbus-python` must be in the driver venv for D-Bus to work. It is declared in `requirements.txt`; the current installed venv has version 1.4.0.

## GNOME Shell extension lifecycle

- GNOME Shell **does not reload extension code** on disable/enable; a full Shell restart (logout/login) is required after code changes.
- `gnome-extensions enable` will report ERROR until Shell has loaded the extension once.
- Use `gdbus call --session --dest org.gnome.Shell --object-path /org/gnome/Shell --method org.gnome.Shell.Extensions.GetExtensionErrors 'asus-turnpad@sinu0.github.io'` to read errors.
- `import * as Main` (named), not `import Main from` (default) for `resource:///org/gnome/shell/ui/main.js`.
- Extension replaces `asus-turnpad-ui.service` on GNOME; the config app calls `ReloadConfig` via D-Bus after saving.

## D-Bus contract

| Item | Value |
|---|---|
| Bus name / Interface | `io.github.sinu0.AsusTurnpad.Driver` |
| Object path | `/io/github/sinu0/AsusTurnpad/Driver` |
| Signal | `OverlayState` – signature `bsasasidsbbb` (enabled, title, titles, icons, value, value_angle_start, unit, center_pressed, value_show_only_progress, touching) – keep it fixed for older extensions |
| Signal | `OverlayDetails(s)` – JSON: profile, mode (`multi`/`single`), colors[] (menu order), color, hints {cw, ccw, center}, hold_returns, pointer (degrees, -1 = none), look (profile then function overrides of `config.schema.OVERLAY_RULE_KEYS`; `{}` = config defaults). Emitted before `OverlayState` in the same idle callback. Driver sends it via `send_to_socket({"details": {...}})`; details-only payloads emit no `OverlayState`. |
| Signal | `CalibrationProgress(s)` – JSON from `CalibrationSession.state()` plus layout, touchpad_max_x/y and the latest `point` |
| Methods | `SetActiveApplication(s)`, `GetStatus()`, `GetOverlayDetails() -> s`, `ReloadConfig()`, `StartCalibration() -> b`, `CancelCalibration() -> b` |

## Config migration behavior

- First launch of the Turnpad app migrates old `dialpad_dev` INI + `layouts/proartp16.py` into `~/.config/asus-turnpad/config.json`.
- If JSON exists, migration is skipped. To re-migrate: delete the JSON file first.
- The driver loads JSON config at startup if it exists; otherwise falls back to legacy layout Python.
- Macros (`MacroStep` list) appear as `{"macro": [...]}` inside legacy `app_shortcuts` dict entries. `emulate_shortcuts()` handles them before legacy key/command logic.

## Profiles and dial behaviour (ASUS Dial parity)

- Profile fields: `mode` (`multi` radial menu / `single` bound function + `single_function`), `sensitivity` (divides rotation thresholds), `scroll_speed` (multiplies scroll units), `remember_last`.
- Segment fields: `enabled`, `color`. MacroStep scroll fields: `axis` (`horizontal`), `modifiers` (keys held while scrolling, e.g. Ctrl = zoom). Never reuse a scroll step's legacy `keys` (old configs contain junk like `["8","11"]`).
- The legacy adapter puts profile settings under the reserved `_meta` key; `is_multifunction()` skips keys starting with `_`. Single mode uses the flat `clockwise/counterclockwise/center` layout with `_meta.single` holding title/treshold/value/unit/color/hints.
- In a selected function: tap centre = the function's `macro_center` if any, otherwise back to menu; holding the centre for `gesture.center_hold_time` returns to the menu (fires while still touching).
- Dial look per level: `overlay` defaults (`position` incl. `custom` + `custom_x`/`custom_y` = dial centre as screen fractions, `visibility` `full`/`fade`/`pill`, `fade_opacity` %) ← `Profile.overlay` ← `Segment.overlay` (dicts of overrides, validated by `overlay_rule()`). The driver merges profile + function (`overlay_look()`, also in single mode via `_meta.single.overlay`) into `details.look`; the menu uses the profile's. The extension resolves the rest with `effectiveLook()` in `dial.js`; `fade` = full on touch, fades after `FADE_AFTER_MS`; `pill` = a small St label (`pillContent()`/`pillPlacement()`) instead of the dial. Settings app: `_dial_look_rows()` (plain on the Skins page, folded "On-screen dial" row in profile and function editors, screen picker for custom).
- `last_function_by_app` restores the last function on activation and focus change; returning to the menu forgets it. A focus change to another app never keeps the previous app's function.
- `overlay` section of config.json (scale, position, hide_delay_ms, show_hints, show_pointer, accent, skin, skin_light, follow_system_style) is read directly by the Shell extension through a directory monitor (also on the skins directory); the driver does not use it except `show_pointer`. With `follow_system_style` the extension uses `skin_light` unless `org.gnome.desktop.interface color-scheme` is `prefer-dark`.
- `tests/test_driver_state.py` extracts the state functions from `dialpad.py` via AST; keep their names in `STATE_FUNCTIONS` in sync when renaming.

## Guided calibration and other models

- `dial_gesture.CalibrationSession` (pure, tested) fits the outer ring and the centre button from finger traces (`fit_circle`, `angular_coverage`). The driver routes whole touch frames to it while `calibration` is set and skips activation and dial actions; send-events are disabled meanwhile.
- The settings app applies the result live and asks *Keep* / *Revert* (`_calibration_backup` holds the geometry before; closing the app without choosing reverts in `do_shutdown`). It stores `device_name` = layout; `apply_gui_settings()` ignores JSON geometry whose `device_name` differs from the running layout.
- *Reset geometry* restores the running layout's values via `config.migrate.layout_geometry()`, which parses the layout file with `ast` (layouts import `libevdev`); the toast offers Undo.
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
