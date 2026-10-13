# Running the DialPad on another laptop model

The driver detects ASUS touchpads by name (`ASUE`, `ELAN`, `ASUP`, `ASUF`,
`ASCE`, `ASCF`, `ASCP` + `Touchpad` in `/proc/bus/input/devices`). What
differs between models is the dial geometry and, rarely, the I2C address of
the corner LED. Both can be handled without code changes:

1. **Install** with `bash install.sh` and pick the closest layout when asked
   (`proartp16`, `asusvivobook16x` or `zenbookpro14`). Known touchpads are
   listed in `laptop_touchpad_dialpad_layouts.csv`.
2. **Calibrate.** Open *ProArt DialPad Control → Calibration → Guided calibration*,
   press *Start*, trace the printed outer ring once with one finger, lift it,
   then trace the edge of the centre button. The measured geometry is saved
   to `~/.config/asus-dialpad/config.json` together with the layout name.
3. **Corner icon.** If holding the illuminated corner does not toggle the
   DialPad, adjust the activation area (width / height, top-right corner) on
   the same page.
4. **Overlay.** On GNOME 45–51 the Shell extension draws the dial (tested on
   GNOME 51 only). Other desktops use the original PySide overlay service
   `asus_dialpad_driver_ui@.service`.

If the corner LED does not light up, the touchpad probably needs the other
I2C address: the driver uses `0x38` for `ASUF1416`, `ASUF1205` and
`ASUF1204` and `0x15` otherwise (see `device_addr` in `dialpad.py`).

## Sharing a working model

Please open an issue with:

- the touchpad line from `/proc/bus/input/devices` and the laptop model,
- the `geometry` section of your `config.json` after calibration,
- whether the corner LED and activation work.

That is enough to add a row to `laptop_touchpad_dialpad_layouts.csv` and,
if needed, a layout file in `layouts/`.
