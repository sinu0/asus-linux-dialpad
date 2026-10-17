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

## Touchpads without a DialPad

Any other touchpad (Synaptics, ELAN, Apple and others, also on laptops of
other makes) can emulate the DialPad: open *Turnpad → Driver* and switch on
**Emulate the DialPad**; the app restarts the driver. Then:

- **Switching on and off:** hold the top-right corner of the touchpad (about
  1.5 cm, the hold time and co-activator keys of the *Behaviour* page apply),
  or use a keyboard shortcut: *Keyboard shortcut → copy* puts the command in
  the clipboard; add it as a custom shortcut in GNOME Settings (*Keyboard →
  View and Customise Shortcuts → Custom Shortcuts*). The corner can be
  switched off so that only the shortcut switches. After the inactivity time
  of the *Behaviour* page the dial switches off by itself.
- **While the dial is on** the whole touchpad is the dial: the pointer stands
  still, a touch near the middle is the centre button (its size is set on the
  *Driver* page), anywhere else is the ring. The on-screen dial shows where
  you are, so keep its visibility at *Always visible* or *Fade*.
- Nothing is sent to the touchpad (there is no light and nothing to unlock),
  and calibration is not needed.

`install.sh` continues on a touchpad without a DialPad. The driver starts
with the emulated dial switched off, and gives the pointer back when it
stops.

## Sharing a working model

Please open an issue with:

- the touchpad line from `/proc/bus/input/devices` and the laptop model,
- the `geometry` section of your `config.json` after calibration,
- whether the corner LED and activation work.

That is enough to add a row to `laptop_touchpad_dialpad_layouts.csv` and,
if needed, a layout file in `layouts/`.
