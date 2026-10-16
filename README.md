# Turnpad — touchpad dial for ASUS laptops

Turnpad turns the DialPad printed on the touchpad of ASUS laptops into an ASUS Dial-style controller on Linux: a radial menu of functions, per-application profiles, an on-screen dial with skins and a settings app.

> **This is a personal fork** of [asus-linux-drivers/asus-dialpad-driver](https://github.com/asus-linux-drivers/asus-dialpad-driver)
> by Lukáš Drahník (GPL-2.0). It adds features modelled on the Windows
> [ASUS Dial & Control Panel](https://www.asus.com/proart/software-solutions/asus-dial-and-control-panel/).
> It was written with substantial help from an AI assistant and has been tested
> only on a ProArt PX13 (HN7306WV) with GNOME 51 on Wayland. Expect rough edges.
> Not affiliated with ASUS or Dialpad, Inc.; "ASUS", "ASUS Dial" and "ProArt" are trademarks of ASUSTeK and "Dialpad" of Dialpad, Inc. They are used here only to say which hardware Turnpad works with.

What the fork adds:

- **Settings app** (GTK4/libadwaita): per-application profiles, a function library, pre-programmed packs (browsers, GIMP, Krita, Inkscape, Blender, Kdenlive, DaVinci Resolve, LibreOffice, code editors, Spotify, video players), function colours and order, import/export.
- **ASUS Dial behaviour**: radial menu or single-function mode, per-app sensitivity and scroll speed, remembered last function, tap centre for the function's action, hold centre for the menu, horizontal scroll and Ctrl+wheel zoom.
- **GNOME Shell overlay**: native radial dial with value gauge, rotation hints and finger position; size and position configurable.
- **Guided calibration** that measures the dial on any DialPad touchpad — see [PORTING.md](PORTING.md).

### Install

```bash
git clone https://github.com/sinu0/asus-linux-dialpad.git
cd asus-linux-dialpad
bash install.sh
```

The installer needs `sudo`, asks no questions (use `bash install.sh --interactive` to choose layout, co-activator key and services yourself), keeps your existing configuration, and collects no data. Afterwards log out and back in, hold the illuminated corner icon to switch the DialPad on, and open **Turnpad** from the applications menu. To update, `git pull` and run `bash install.sh` again; to remove, run `bash uninstall.sh`.

Configuration lives in `~/.config/asus-turnpad/config.json`; the original `dialpad_dev` + `layouts/*.py` setup keeps working as a fallback. Updating from a version before the rename (`asus-dialpad-driver`) moves your settings over and removes the old files and services.

### Supported desktops

Turnpad currently supports **GNOME** (Shell 45–51). The driver itself also runs on other desktops, but without the native on-screen dial and skins. Support for another desktop (KDE Plasma, Hyprland, sway, COSMIC…) starts with an issue: [request your desktop](https://github.com/sinu0/asus-linux-dialpad/issues/new?template=desktop-support.yml). [ARCHITECTURE.md](ARCHITECTURE.md#adding-a-desktop-environment) describes what a port involves.

---

[![License: GPL v2](https://img.shields.io/badge/License-GPLv2-blue.svg)](https://www.gnu.org/licenses/old-licenses/gpl-2.0.en.html)

## Screenshots

**On-screen dial** (GNOME Shell): radial menu with colour-coded functions, a level gauge for volume and brightness, rotation hints and the finger position.

![On-screen dial](./preview/overlay-states.png)

**Skins** — five built-in looks, plus your own made in the skin editor or written as JSON by hand or by an AI assistant ([SKINS.md](SKINS.md)):

![Built-in skins](./preview/overlay-skins.png)

**Settings app** — functions of a profile, application profiles, the function library, the per-function editor, calibration, behaviour and skins:

| | |
|---|---|
| ![Dial controls](./preview/settings-dial-controls.png) | ![Profiles](./preview/settings-profiles.png) |
| ![Function library](./preview/settings-library.png) | ![Function editor](./preview/settings-function-editor.png) |
| ![Guided calibration](./preview/settings-calibration.png) | ![Behaviour](./preview/settings-behaviour.png) |
| ![Skin gallery](./preview/settings-skins.png) | ![Skin editor](./preview/settings-skin-editor.png) |

How the parts fit together and how to support another desktop: [ARCHITECTURE.md](ARCHITECTURE.md).

The pictures are generated from the code: `gjs -m tools/render_overlay_preview.js` paints the dial with the extension's own drawing code, and `python3 tools/screenshot_settings.py` opens the settings app on a demo configuration and saves each page.

The sections below come from the original project and describe the base driver.

## Changelog

[CHANGELOG.md](CHANGELOG.md)

## Frequently Asked Questions

[FAQ](#faq)

## Features

Everything is set up in the **Turnpad** app (applications menu); changes apply immediately, no restart or file editing needed.

**Profiles**

- A default profile plus profiles per application, switched automatically with the focused window (desktop ID on GNOME, window title or binary elsewhere)
- Radial-menu mode with several functions, or single-function mode where the dial always controls one function
- Per-profile sensitivity, scroll speed and "remember last function"
- Pre-programmed packs for browsers, GIMP, Krita, Inkscape, Blender, Kdenlive, DaVinci Resolve, LibreOffice, code editors, Spotify, video players and darktable; import/export of profiles

**Functions**

- Library of ready functions: volume, brightness, keyboard light, mute, workspaces, vertical/horizontal scroll, zoom, tabs, back/forward, arrow keys, media tracks, seek, undo/redo, font size, brush size, frame stepping, timeline zoom
- Own colour, order on the dial, show/hide, rotation step and an optional live value (e.g. volume in % with a level gauge)
- Separate actions for turning clockwise, counter-clockwise and tapping; each action can be a captured keyboard shortcut, media key, volume, brightness, vertical or horizontal scroll (optionally with Ctrl/Shift/Alt held, e.g. Ctrl + wheel zoom), a shell command or a wait — several steps run in order

**Using the dial**

- Hold the illuminated corner icon to switch the DialPad on or off (optionally only together with a co-activator key)
- In the menu, touch a sector and release to choose a function; a function that only has a tap action runs straight away
- In a function, turn around the ring; tap the centre for the function's tap action (or to go back when it has none), hold the centre to return to the menu
- Fast spins accelerate scrolling; the DialPad switches itself off after a period of inactivity

**On-screen dial**

- GNOME Shell 45–51: native overlay with colours, level gauge, rotation hints and finger position; size, position and accent colour are configurable
- Skins: Dark glass, Midnight (OLED black), Frost (light), ProArt bronze and Classic segments, optionally following the system light/dark style; the skin editor creates your own with a live preview, and its "Copy prompt for AI" / "Paste JSON" pair lets any AI assistant design one ([SKINS.md](SKINS.md))
- Other desktops: the original PySide overlay (own `.svg` icons; double-click to unlock its position and move it)

**Base driver** (from the original project)

- Runs as a user service in its own Python virtual environment, on Wayland and X11
- Automatic layout detection for known laptops, plus guided calibration for others ([PORTING.md](PORTING.md))
- The original project collects anonymous installation data; **this fork removed it** and sends nothing

## Installation

Get the latest stable or dev version using `git`:

```bash
$ git clone https://github.com/sinu0/asus-linux-dialpad.git
$ cd asus-linux-dialpad
```

or customized install:

```
# ENV VARS (with the defaults, see install_paths.sh)
INSTALL_DIR_PATH="/opt/asus-turnpad"                 # program and its Python environment, owned by root
CONFIG_FILE_DIR_PATH="$HOME/.config/asus-turnpad"    # settings, skins and driver state
LOGS_DIR_PATH="/var/log/asus-turnpad"                # only for install and uninstall logs
INSTALL_UDEV_DIR_PATH="/etc/udev"
```

Where things go follows the Filesystem Hierarchy Standard for software installed outside the package manager:

| Path | Content |
| --- | --- |
| `/opt/asus-turnpad` | Driver, settings app, GNOME extension source and the Python environment (read-only for users) |
| `~/.config/asus-turnpad` | `config.json`, `skins/`, driver state `dialpad_dev` |
| `~/.config/systemd/user/asus-turnpad.service` | The driver as a user service, started with the graphical session |
| `~/.local/share/gnome-shell/extensions/asus-turnpad@sinu0.github.io` | The on-screen dial for GNOME |
| `/etc/udev/rules.d/70-asus-turnpad-*.rules`, `/etc/modules-load.d/asus-turnpad.conf` | Access to the touchpad's I2C and hidraw nodes and to uinput; kernel modules loaded at boot |
| `/var/log/asus-turnpad` | Logs of the installer and uninstaller |

### Installation on Immutable Systems (BazziteOS, Fedora Silverblue, Kinoite)

The default paths are writable on immutable distributions (`/opt` and `/etc`); expect two reboots:

```bash
# First run - installs system packages
$ bash install.sh

# Reboot when prompted (required for package layering)
$ systemctl reboot

# Second run - completes driver installation
$ bash install.sh

# Final reboot (required for group membership)
$ systemctl reboot
```

**Why two reboots?** Immutable systems require a reboot after layering packages and another after group membership changes.

---

or run separately parts of the install script.

Try found Touchpad with DialPad:

```bash
$ bash install_device_check.sh
```

Add a user to the groups `i2c,input,uinput`:

```bash
$ bash install_user_groups.sh
```

Run driver now and every time that user logs in (do NOT run as `$ sudo`, works via `systemctl --user`):

```bash
# with user interface
$ bash install_user_interface.sh
$ bash install_service.sh

# with no user interface
$ USER_INTERFACE=0 \
 bash install_service.sh
```

#### NixOS

> **Fork note:** the Nix packaging is inherited from the original project and has not been updated for this fork's additions (settings app, GNOME extension, JSON configuration). The flake URLs below still point to the original driver.

Nix code is provided for this driver.
Please read the `nix/module.nix` for default behavior.

<details>
<summary>The driver installation (NixOS)</summary>
<br>

##### All Nix versions

First, you will want to pin this repository using your input pinner of choice (some [listed on the Wiki](https://wiki.nixos.org/wiki/Applications#Dependencies)).
After, we need to add the overlay & module to the system.
While there are many ways to organize a NixOS system, for a simple `configuration.nix`-only example:

```nix
# configuration.nix
{ config, lib, pkgs, ... }:

let
  inputs = import ./my/pinned/inputs { };
in
{
  system = "x86_64-linux";

  nixpkgs.overlays = [
    (import "${inputs.asus-dialpad-driver}/nix/overlay")
  ];

  modules = [
    (import "${inputs.asus-dialpad-driver}/nix/module.nix")
  ];

  # Users *must* be enrolled in these groups
  users.users.alice = {
    extraGroups = [ "i2c" "input" "uinput" ];
  };

  # Enable Asus DialPad Service
  hardware.asus-dialpad-driver = {
    enable = true;
    sessionTypes = [ "wayland" "x11" ]; # default
    # Enable user-level systemd service
    daemon.enable = true; # default
    layout = "proartp16"; # default
    defaultConfig = { /* … */ };
  };
}
```

> The key for the caclulator toggling script should be associated with XF86Calculator, allowing it to toggle any calculator application, not just the one specified in the configuration. This means that the key binding can be used to manage various calculator applications across different key binding configurations. For e.g.:

```nix
"XF86Calculator".action = sh -c "if pidof gnome-calculator > /dev/null; then kill $(pidof gnome-calculator); else gnome-calculator; fi";
```

##### Nix flakes only

[Flakes](https://nix.dev/concepts/flakes.html) are another, experimental way to add asus-dialpad-driver to your system.
To add it to your system’s flake.

```nix
# flake.nix

{

    inputs = {
        # ---Snip---
        asus-dialpad-driver = {
          url = "github:asus-linux-drivers/asus-dialpad-driver/v2.3.0"; # use this line for the latest release of stable version
          # url = "github:asus-linux-drivers/asus-dialpad-driver"; # or this line for using master branch with the latest changes which may be not stable
          inputs.nixpkgs.follows = "nixpkgs";
        };
        # ---Snip---
    }

    outputs = {nixpkgs, asus-dialpad-driver, ...} @ inputs: {
        nixosConfigurations.HOSTNAME = nixpkgs.lib.nixosSystem {

            modules = [
                ({ ... }: {
                  nixpkgs.overlays = [
                    asus-dialpad-driver.overlays.default
                  ];
                })
                asus-dialpad-driver.nixosModules.default
                ./configuration.nix
            ];
        };
    }
}
```
Then you can enable the service, `services.asus-dialpad-driver`, in your `configuration.nix` file in the same way as the prior section for stable Nix.

</details>

## Uninstallation

To uninstall run

```bash
$ bash uninstall.sh                  # keeps your settings in ~/.config/asus-turnpad
$ bash uninstall.sh --interactive    # asks whether to remove them too
```

It removes the services, the GNOME extension, `/opt/asus-turnpad`, the udev rules and module list, and anything left from a version before the rename. It uses the same paths as the installer (`install_paths.sh`), so pass the same environment variables if you changed them. Group memberships (`input`, `uinput`, `i2c`) stay.

## Layouts

Layouts below are named by laptop models, but the name is not important. What is important is their visual appearance because they are repeated on multiple laptop models across series. The install script should recognize the correct one automatically for your laptop. If yours was not recognized, please create issue.

| Name | Description                                                                                                  | Image                                                                                               |
| ------------ | ------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------- |
| <a id="asusvivobook16x"></a><br><br><br><br><br>asusvivobook16x<br><br><br><br><br><br><br> | not nested                                                                | ![](images/Asus-Vivobook-16-x.png)                                             |
| <a id="proartp16"></a><br><br><br><br><br>proartp16<br><br><br><br><br><br><br> | nested                                                               | ![](images/Asus-ProArt-P16.png)   |
| <a id="zenbookpro14"></a><br><br><br><br><br>zenbookpro14<br><br><br><br><br><br><br> | nested                                                               | ![](images/Asus-Zenbook-Pro-14.jpg)   |


### FAQ ###

**How to start DialPad without systemd service?**

- install with `bash install.sh --interactive` and answer no to the question about using `systemd`
- layout name is required as first argument and as second argument can be optionally passed path to directory where will be autocreated config `dialpad_dev` (default is current working directory):

```
/opt/asus-turnpad/.env/bin/python3 /opt/asus-turnpad/dialpad.py <asusvivobook16x|proartp16|..> ~/.config/asus-turnpad/
```

**How to install the driver when is used conda for managing multiple Python versions?**

```
$ # install conda and then
$ conda create -n conda_env -c conda-forge python=3.11
$ conda activate conda_env
(conda_env) $ which python3
/home/ldrahnik/miniconda3/envs/conda_env/bin/python3
(conda_env) $ python3 --version
Python 3.11.13
(conda_env) $ bash install.sh
...
$ (conda_env) $ /opt/asus-turnpad/.env/bin/python3 --version
Python 3.11.13
(conda_env) $ conda deactivate
$
```

**How to install the driver when is used pyenv for managing multiple Python versions?**

```
$ git clone https://github.com/sinu0/asus-linux-dialpad.git
$ cd asus-linux-dialpad

$ # pyenv install Ubuntu 22.04
$ apt install -y make build-essential libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev wget curl llvm libncurses5-dev libncursesw5-dev xz-utils tk-dev libffi-dev liblzma-dev python3-openssl git
$ curl https://pyenv.run | bash

# install & change to the Python version for which one do you want to install the driver
$ CC=clang pyenv install 3.9.4
$ pyenv global 3.9.4 # change as global
$ # pyenv local 3.9.4 # will create file .python-version inside source dir so next (re)install will be used automatically saved Python version in this file

# install the driver
$ bash install.sh

# change to the standardly (previously) used Python version
$ pyenv global system
```

**How can DialPad be activated via CLI?**

Normally you hold the illuminated corner icon. From a terminal, change `enabled` in the driver's state file; the running driver picks it up:

```
# enabling DialPad via command line
sed -i "s/^enabled = 0/enabled = 1/" ~/.config/asus-turnpad/dialpad_dev
# disabling
sed -i "s/^enabled = 1/enabled = 0/" ~/.config/asus-turnpad/dialpad_dev
```

## Configuration

Use the **Turnpad** app for every setting:

| App page | What it configures |
| --- | --- |
| **Dial Controls** | Functions of the selected profile (add from the library, order, colour, show/hide, actions for turning and tapping, live value), dial mode, sensitivity, scroll speed, remembering the last function |
| **Apps & Profiles** | Default and application profiles, pre-programmed packs, duplicate/rename/remove, import and export |
| **Behaviour** | Corner icon hold time, co-activator keys, switching off after inactivity, default rotation step, jitter filter, centre hold time, minimum menu sectors, on-screen dial size, position, visibility time, hints, finger position, progress arc and accent colour |
| **Calibration** | Guided calibration (trace the ring and the centre button) or manual dial geometry and corner icon area |
| **Driver** | Driver status, active profile and function, reload, configuration folder |

The layout (touchpad family) is chosen automatically during installation; to force one, run `LAYOUT_NAME=proartp16 bash install.sh` (or `bash install.sh --interactive`). Known layouts are listed in [Layouts](#layouts).

### Where the settings are stored

You do not need to edit these files; they are described for backups and troubleshooting.

| File | Content |
| --- | --- |
| `~/.config/asus-turnpad/config.json` | Everything set in the app: profiles, functions, behaviour, on-screen dial and dial geometry. Written atomically; the driver and the GNOME extension reload it after every change. Use *Import/Export* to move profiles between computers. |
| `~/.config/asus-turnpad/dialpad_dev` | Runtime state of the driver: `enabled` (DialPad on/off) and `socket_enabled` (messages for the PySide overlay on other desktops; the GNOME overlay does not need it). Its other keys come from the original driver and are ignored while `config.json` exists. |
| `/opt/asus-turnpad/layouts/*.py` | Default geometry of each touchpad family and the original Python format of shortcuts. Used only until `config.json` exists — the first start of the app converts them. |

If `config.json` is deleted, the app recreates it from the layout on its next start.

## Debugging

- The driver can be installed like `LOG=DEBUG bash install.sh` to extend the logs to a debug level (**recommended only for short-term debugging purpose**)

The **Driver** page of the app shows whether the driver is reachable, the focused application, the active profile and function.

Then check the service logs:

```
$ journalctl --user -u asus-turnpad.service
$ systemctl --user restart asus-turnpad.service
```

The driver state and the messages for the on-screen dial are available on the session D-Bus:

```
$ gdbus call --session --dest io.github.sinu0.AsusTurnpad.Driver --object-path /io/github/sinu0/AsusTurnpad/Driver --method io.github.sinu0.AsusTurnpad.Driver.GetStatus
$ gdbus monitor --session --dest io.github.sinu0.AsusTurnpad.Driver
```

GNOME extension errors (the extension reloads only after logging out and back in):

```
$ gdbus call --session --dest org.gnome.Shell --object-path /org/gnome/Shell --method org.gnome.Shell.Extensions.GetExtensionErrors asus-turnpad@sinu0.github.io
```

For further debugging stop the installed services:

```
systemctl --user stop asus-turnpad.service
systemctl --user stop asus-turnpad-ui.service
```

And listen on socket using `socat` (e.g. `$ sudo apt install socat`):

**Is necessary to have enabled in config `socket_enabled`.**

```
$ socat - UNIX-RECV:$XDG_RUNTIME_DIR/asus-turnpad.sock
{"ts": 1767791846.2734825, "enabled": true}
{"ts": 1767791846.3734825, "input": "center", "value": 1}
{"ts": 1767791846.3737416, "input": "center", "value": 0}
{"ts": 1767791846.461517, "input": "counterclockwise", "value": "62", "title": "Volume"}
{"ts": 1767791846.6073422, "input": "counterclockwise", "value": "58", "title": "Volume"}
{"ts": 1767791846.698195, "input": "counterclockwise", "value": "56", "title": "Volume"}
{"ts": 1767791846.814567, "input": "center", "value": 1}
{"ts": 1767791846.8146207, "input": "center", "value": 0}
{"ts": 1767791846.8976963, "input": "counterclockwise", "value": "54", "title": "Volume"}
{"ts": 1767791846.9604836, "input": "counterclockwise", "value": "52", "title": "Volume"}
{"ts": 1767791847.161212, "input": "counterclockwise", "value": "50", "title": "Volume"}
{"ts": 1767791847.3800304, "input": "clockwise", "value": "52", "title": "Volume"}
{"ts": 1767791847.5570402, "input": "clockwise", "value": "54", "title": "Volume"}
{"ts": 1767791847.6351395, "input": "center", "value": 1}
{"ts": 1767791847.6357095, "input": "center", "value": 0}
{"ts": 1767791847.7126362, "input": "clockwise", "value": "56", "title": "Volume"}
{"ts": 1767791847.789433, "input": "clockwise", "value": "58", "title": "Volume"}
{"ts": 1767791846.2734825, "enabled": false}
```

or use log level `DEBUG`:

```
$ cd /opt/asus-turnpad && source .env/bin/activate
(.env) $ LOG=DEBUG python3 dialpad_ui.py
Listening on /run/user/1000/asus-turnpad.sock
2026-01-15 12:34:23,980 DEBUG {'ts': 1768476870.9540725, 'enabled': True}
2026-01-15 12:34:26,281 DEBUG {'ts': 1768476866.2752297, 'titles': ['Volume', 'Scroll', 'Brightness'], 'icons': ['/usr/share/icons/elementary/status/symbolic/audio-volume-medium-symbolic.svg', '/usr/share/icons/elementary/status/symbolic/rotation-allowed-symbolic.svg', '/usr/share/icons/elementary/status/symbolic/display-brightness-symbolic.svg'], 'title': None}
2026-01-15 12:34:27,481 DEBUG {'ts': 1768476867.4463465, 'enabled': False}
```

## Similar existing

- I do not know any

## Existing related projects

- [c++] Set of tools for handling ASUS Dial and similar designware hardware under Linux (https://github.com/fredaime/openwheel)
- [c++] Continuing development of the project above for the ASUS Dial (https://github.com/FrancisChung/asus-dial-driver)

**Why was this project created?** Because linux does not support integration of DialPad into a Touchpad

## Credits

The driver this fork builds on — touchpad handling, layouts, installer and the original DialPad support — is the work of [Lukáš Drahník](https://github.com/ldrahnik) and the contributors of [asus-linux-drivers/asus-dialpad-driver](https://github.com/asus-linux-drivers/asus-dialpad-driver).
