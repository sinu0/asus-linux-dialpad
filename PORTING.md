# Running the DialPad on another laptop model

The driver detects ASUS touchpads by name (`ASUE`, `ELAN`, `ASUP`, `ASUF`,
`ASCE`, `ASCF`, `ASCP` + `Touchpad` in `/proc/bus/input/devices`). What
differs between models is the dial geometry and, rarely, the I2C address of
the corner LED. Both can be handled without code changes:

1. **Install** as described in the [README](README.md#install). The layout
   (`proartp16`, `asusvivobook16x` or `zenbookpro14`) is picked from
   `laptop_touchpad_dialpad_layouts.csv` by laptop name or touchpad id; an
   unknown laptop gets `proartp16` (`bash install.sh --interactive` lets you
   choose).
2. **Calibrate.** Open *Turnpad → Calibration → Guided calibration*,
   press *Start*, trace the printed outer ring once with one finger, lift it,
   then trace the edge of the centre button. The measured geometry is used
   right away so you can try the dial; press *Keep* to save it to
   `~/.config/asus-turnpad/config.json` together with the layout name, or
   *Revert* to go back (closing the app without choosing also reverts).
   *Reset geometry* at the bottom of the page restores the values of the
   layout file.
3. **Corner icon.** If holding the illuminated corner does not toggle the
   DialPad, adjust the activation area (width / height, top-right corner) on
   the same page.
4. **Overlay.** On GNOME 45–51 the Shell extension draws the dial (tested on
   GNOME 51 only). Other desktops use the original PySide overlay service
   `asus-turnpad-ui.service`.

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
