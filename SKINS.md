# Skins of the on-screen dial

The GNOME Shell dial comes in five built-in skins:

| Id | Name | Look |
|---|---|---|
| `glass` | Dark glass | Dark glass disc with icon bubbles (default) |
| `midnight` | Midnight | Pure black for OLED screens, thin outlines |
| `frost` | Frost | Light frosted disc that suits light themes |
| `proart` | ProArt bronze | Warm dark bronze with a champagne rim |
| `classic` | Classic segments | Ring of coloured sectors like the original ASUS Dial |

![Built-in skins](./preview/overlay-skins.png)

Pick one in **Turnpad → Behaviour → Skin**. With **Match system style** on, the dial uses one skin while GNOME is dark and another while it is light (Frost by default), switching together with the quick-settings style toggle.

## Making your own

### In the skin editor

Click the pencil on a built-in skin (or **+**) to start a copy. The editor shows the menu and a level gauge live while you change:

- **Based on**: the skin your copy starts from. Colours you do not change keep following it.
- **Menu style**: icon bubbles or a ring of sectors.
- **Colours**: every part of the dial, with opacity. A reset button appears next to a changed colour.

**Save** writes the skin to `~/.config/asus-turnpad/skins/<id>.json` and selects it.

### With an AI assistant

1. In the editor, click **Copy prompt for AI**. The clipboard now holds the format below and your current skin.
2. Paste it into any assistant and describe the idea, e.g. *“deep navy with cyan outlines”* or *“matching the Catppuccin Latte palette”*.
3. Copy the JSON it answers with, then click **Paste JSON** in the editor. The dialog reopens with the result, so you can check it and **Save**.

### By hand

Drop a JSON file into `~/.config/asus-turnpad/skins/`. The file name without `.json` is the skin's id; a file named like a built-in skin replaces it. The dial reloads when a file changes, with no restart needed.

```json
{
    "name": "Night owl",
    "description": "Navy with cyan outlines",
    "base": "midnight",
    "menu": "bubbles",
    "palette": {
        "surfaceTop": "#16213ef7",
        "surfaceBottom": "#0b1020f7",
        "rim": "#5ee7ff55",
        "pointer": "#5ee7ff"
    }
}
```

## Format

A skin is one JSON object:

- `name`: shown in the settings app.
- `description`: optional, one line.
- `base`: optional id of another skin; colours left out are taken from it (and from Dark glass in the end).
- `menu`: `"bubbles"` (round icon buttons) or `"segments"` (a ring of sectors).
- `palette`: colours as `"#rrggbb"`, `"#rrggbbaa"` (`aa` = opacity, `00`–`ff`) or `[r, g, b, a]` with channels from 0 to 1.

| Key | Paints |
|---|---|
| `surfaceTop` | Top of the disc gradient |
| `surfaceBottom` | Bottom of the disc gradient and the hint bar |
| `rim` | Thin outline of the disc, the centre and the hint bar |
| `bubble` | Background of a function in the bubble menu |
| `segment` | Background of a function in the sector menu |
| `freeSlot` | Dot or sector where no function is assigned |
| `track` | Unfilled part of the level gauge and the wheel |
| `detent` | Notches of endless functions such as Zoom |
| `centerTop` | Top of the centre button gradient |
| `centerBottom` | Bottom of the centre button gradient |
| `text` | Function and profile names |
| `muted` | Hints such as “Release to select” |
| `icon` | Function icons in the menu |
| `iconOnColor` | Icon of the highlighted function, drawn on its colour |
| `pointer` | Dot that follows the finger around the ring |
| `shadow` | Opacity of the shadow under the disc, a number from 0 to 1 |

Function colours (Volume blue, Zoom champagne…) and the accent colour are set per function and in Behaviour, not by the skin. A broken or partial skin never breaks the dial: unknown values fall back to the base skin.

The built-in skins are in [`gnome/extension/skins.json`](gnome/extension/skins.json). The painting code is shared by the extension and the README pictures (`gjs -m tools/render_overlay_preview.js`). The legacy PySide overlay used on other desktops does not support skins.
