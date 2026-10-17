# Installing Turnpad

The short version is in the [README](README.md#install). This page has the details of both ways to install.

| | Arch package | `install.sh` |
| --- | --- | --- |
| Distributions | Arch Linux and derivatives (CachyOS, EndeavourOS, Manjaro) | Any distribution with systemd: Fedora, Ubuntu, Debian, openSUSE, Void, Gentoo, Solus, immutable Fedora |
| Program | `/usr/share/asus-turnpad`, managed by pacman | `/opt/asus-turnpad` with its own Python environment |
| Python libraries | Distribution packages | Downloaded by pip into `/opt/asus-turnpad/.env` |
| Layout of your laptop | Picked when the driver starts (`auto`) | Picked during installation |
| Update | `git pull`, then `bash packaging/arch/build.sh` | `git pull`, then `bash install.sh` again |
| Remove | `sudo pacman -R asus-turnpad-git` | `bash uninstall.sh` |

Use one of them, not both: `install.sh` refuses to run while the package is installed, and `asus-turnpad-setup` refuses while an `install.sh` install is present. Your settings in `~/.config/asus-turnpad` are kept by both and work with both.

| Distribution | Tested | Result |
| --- | --- | --- |
| CachyOS (Arch), GNOME 51 | On a ProArt PX13 | Everything |
| Arch Linux (package) | CI, every push | Package builds, installs, imports, removes |
| Fedora 44 (`install.sh`) | CI, every push | Installs, imports, uninstalls |
| Ubuntu 26.04 LTS (`install.sh`) | CI, every push | Installs, imports, uninstalls |
| Ubuntu 24.04 LTS (`install.sh`) | Once, by hand | Driver works; the settings app does not start (Libadwaita 1.5) |
| Debian, openSUSE, Void, Gentoo, Solus, immutable Fedora | No | The installer has their package names from the original project |

The CI tests run in containers without a DialPad, so they cover packages, the Python environment, files and the uninstaller, not the touchpad itself. The settings app needs Libadwaita 1.9 (GNOME 50 or newer); the installer warns when it is older.

## Arch package

```bash
git clone https://github.com/sinu0/asus-turnpad.git
cd asus-turnpad
bash packaging/arch/build.sh   # builds the latest commit on GitHub and installs it with pacman
asus-turnpad-setup             # once, as your user
```

`build.sh` runs `makepkg -si` in `~/.cache/asus-turnpad/makepkg` rather than in the clone (makepkg writes the version into the PKGBUILD it builds from, which would get in the way of `git pull`); arguments are passed on to makepkg. Running `makepkg -si` in `packaging/arch` yourself works too.

Log out and back in. `asus-turnpad-setup` adds you to the groups `input`, `i2c` and `uinput` (asks for sudo) and enables the driver's user service and the GNOME extension. It changes nothing for other users; each user who wants the dial runs it once.

What the package installs:

| Path | Content |
| --- | --- |
| `/usr/share/asus-turnpad` | Driver and settings app |
| `/usr/share/gnome-shell/extensions/asus-turnpad@sinu0.github.io` | The on-screen dial for GNOME |
| `/usr/lib/systemd/user/asus-turnpad.service` | The driver as a user service (enabled per user by `asus-turnpad-setup`) |
| `/usr/lib/udev/rules.d/70-asus-turnpad.rules` | Access to uinput, the I2C buses and the DialPad touchpad's hidraw node for the logged-in user |
| `/usr/lib/modules-load.d/asus-turnpad.conf`, `/usr/lib/sysusers.d/asus-turnpad.conf` | Kernel modules `uinput` and `i2c-dev`; groups `i2c` and `uinput` |
| `/usr/bin/asus-turnpad-setup` | The per-user setup above |

**Update:** `git pull`, then `bash packaging/arch/build.sh` (it always builds the latest commit on GitHub and restarts the driver). A changed GNOME extension loads at the next login.

**Remove:**

```bash
systemctl --user disable --now asus-turnpad
sudo pacman -R asus-turnpad-git
```

**Coming from `install.sh`:** run `bash uninstall.sh` in the old clone first (it keeps your settings), then install the package.

## install.sh (all distributions)

```bash
git clone https://github.com/sinu0/asus-turnpad.git
cd asus-turnpad
bash install.sh
```

The installer needs `sudo`. It installs the required system packages with your package manager (apt, dnf, pacman, zypper, xbps, emerge, eopkg, rpm-ostree), creates a Python environment in `/opt/asus-turnpad`, adds you to the groups `input`, `i2c` and `uinput`, picks the layout of your laptop, and sets up the user service and the GNOME extension. It asks no questions; `bash install.sh --interactive` lets you choose the layout, a co-activator key and the services yourself. Log out and back in afterwards.

When your laptop is not in `laptop_touchpad_dialpad_layouts.csv`, the installer looks up the touchpad's vendor and product id on linux-hardware.org to find laptops with the same touchpad; if that also fails it uses `proartp16`, and you measure the dial with *Calibration → Guided calibration* in the app.

**Update:** `git pull`, then `bash install.sh` again.

### Uninstall

```bash
bash uninstall.sh                  # keeps your settings in ~/.config/asus-turnpad
bash uninstall.sh --interactive    # asks whether to remove them too
```

It removes the services, the GNOME extension, `/opt/asus-turnpad`, the udev rules and module list, and anything left from a version before the rename. It uses the same paths as the installer (`install_paths.sh`), so pass the same environment variables if you changed them. Group memberships (`input`, `uinput`, `i2c`) stay.

### Custom paths

The installer and the uninstaller read these environment variables (defaults in `install_paths.sh`):

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

### Running parts of the installer

Check that a touchpad with a DialPad is found:

```bash
$ bash install_device_check.sh
```

Add your user to the groups `i2c`, `input` and `uinput`:

```bash
$ bash install_user_groups.sh
```

Start the driver now and at every login (run as your user, not with `sudo`; it uses `systemctl --user`):

```bash
# with user interface
$ bash install_user_interface.sh
$ bash install_service.sh

# with no user interface
$ USER_INTERFACE=0 \
 bash install_service.sh
```

### Immutable systems (BazziteOS, Fedora Silverblue, Kinoite)

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

### Without systemd

Install with `bash install.sh --interactive` and answer no to the question about `systemd`, then start the driver yourself. The first argument is the layout (`auto` picks the one of this laptop), the second the directory for the driver state `dialpad_dev`:

```
/opt/asus-turnpad/.env/bin/python3 /opt/asus-turnpad/dialpad.py <auto|asusvivobook16x|proartp16|..> ~/.config/asus-turnpad/
```

### Python version managers

**conda**

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

**pyenv** (Python 3.10 or newer)

```
$ git clone https://github.com/sinu0/asus-turnpad.git
$ cd asus-turnpad

$ # pyenv install Ubuntu 22.04
$ apt install -y make build-essential libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev wget curl llvm libncurses5-dev libncursesw5-dev xz-utils tk-dev libffi-dev liblzma-dev python3-openssl git
$ curl https://pyenv.run | bash

# install & change to the Python version for which one do you want to install the driver
$ CC=clang pyenv install 3.12
$ pyenv global 3.12 # change as global
$ # pyenv local 3.12 # will create file .python-version inside source dir so next (re)install will be used automatically saved Python version in this file

# install the driver
$ bash install.sh

# change to the standardly (previously) used Python version
$ pyenv global system
```
