// Paints dials with the GNOME extension's own code (gnome/extension/dial.js)
// as the Shell shows them: paintDial() plus the icon actors from
// iconLayout(). Tests compare overlay/painter.py and the layer-shell dial
// with these pictures.
//
//   gjs -m tests/render_dial_reference.js cases.json output-directory
//
// cases.json: [{name, skin, accent, appearance, state, details,
// pixelScale?, monitor?}], state and details as in extension.js. Writes
// <name>.png, transparent around the dial, overlayPlacement() size at the
// given pixel scale, and with a group's list open <name>-list.png, its
// submenuPlacement() beside the dial on monitor ({width, height}, logical).
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Rsvg from 'gi://Rsvg?version=2.0';
import Cairo from 'cairo';
import System from 'system';

import {
    DIAL_D,
    HINT_H,
    effectiveLook,
    iconLayout,
    iconNameFor,
    openSubmenu,
    overlayPlacement,
    paintDial,
    paintSubmenu,
    parseColor,
    resolveSkin,
    submenuLayout,
    submenuPlacement,
    submenuSize,
} from '../gnome/extension/dial.js';

const ROOT = GLib.path_get_dirname(GLib.path_get_dirname(System.programPath));
const ICON_THEMES = ['/usr/share/icons/Adwaita', '/usr/share/icons/AdwaitaLegacy', '/usr/share/icons/hicolor'];

function readJson(path) {
    const [, bytes] = Gio.File.new_for_path(path).load_contents(null);
    return JSON.parse(new TextDecoder().decode(bytes));
}

const iconCache = new Map();

function searchDirectory(directory, fileName, depth) {
    const direct = directory.get_child(fileName);
    if (direct.query_exists(null))
        return direct.get_path();
    if (depth === 0)
        return null;
    const enumerator = directory.enumerate_children('standard::name,standard::type', Gio.FileQueryInfoFlags.NONE, null);
    const names = [];
    for (let info = enumerator.next_file(null); info; info = enumerator.next_file(null)) {
        if (info.get_file_type() === Gio.FileType.DIRECTORY)
            names.push(info.get_name());
    }
    // Sorted, so every run and the Python twin find the same file.
    for (const name of names.sort()) {
        const found = searchDirectory(directory.get_child(name), fileName, depth - 1);
        if (found)
            return found;
    }
    return null;
}

function findIcon(name) {
    if (!iconCache.has(name)) {
        let found = null;
        for (const theme of ICON_THEMES) {
            const directory = Gio.File.new_for_path(theme);
            if (directory.query_exists(null) && (found = searchDirectory(directory, `${name}.svg`, 3)))
                break;
        }
        iconCache.set(name, found);
    }
    return iconCache.get(name);
}

function drawIcon(cr, title, configured, x, y, size, color) {
    const path = configured?.startsWith('/') ? configured : findIcon(configured || iconNameFor(title));
    if (!path)
        return;
    const handle = Rsvg.Handle.new_from_file(path);
    cr.pushGroup();
    handle.render_document(cr, new Rsvg.Rectangle({ x, y, width: size, height: size }));
    const mask = cr.popGroup();
    cr.setSourceRGBA(...color);
    cr.mask(mask);
}

const [casesPath, output] = ARGV;
const skins = readJson(GLib.build_filenamev([ROOT, 'gnome', 'extension', 'skins.json']));
for (const [id, skin] of Object.entries(skins))
    skin.__dir = GLib.build_filenamev([ROOT, 'gnome', 'extension']);
GLib.mkdir_with_parents(output, 0o755);
for (const entry of readJson(casesPath)) {
    const view = {
        skin: resolveSkin(skins, entry.skin),
        accent: parseColor(entry.accent, [0.906, 0.725, 0.553, 1]),
        appearance: entry.appearance,
        state: entry.state,
        details: entry.details,
    };
    const scale = view.appearance.scale;
    const pixels = entry.pixelScale ?? 1;
    const width = Math.round(DIAL_D * scale);
    const height = Math.round((DIAL_D + HINT_H) * scale);
    const surface = new Cairo.ImageSurface(Cairo.Format.ARGB32, Math.ceil(width * pixels), Math.ceil(height * pixels));
    const cr = new Cairo.Context(surface);
    cr.scale(pixels, pixels);
    if (view.state.enabled) {
        paintDial(cr, view);
        // The icon actors sit on top of the painted layers.
        const { menu, menuVisible, center } = iconLayout(view);
        for (const icon of menuVisible ? menu : [])
            drawIcon(cr, icon.title, icon.configured, icon.x, icon.y, icon.size, icon.color);
        if (center)
            drawIcon(cr, center.title, center.configured, center.x, center.y, center.size, center.color);
    }
    surface.writeToPNG(GLib.build_filenamev([output, `${entry.name}.png`]));
    cr.$dispose();
    if (view.state.enabled)
        paintList(view, entry, pixels);
}

// An open group's list as _updateSubmenu() in extension.js places and
// paints it beside the dial on entry.monitor: <name>-list.png.
function paintList(view, entry, pixels) {
    const submenu = openSubmenu(view);
    if (!submenu)
        return;
    const monitor = entry.monitor ?? { width: 1920, height: 1080 };
    const look = effectiveLook(view.appearance, view.details.look);
    const scale = view.appearance.scale;
    const dial = overlayPlacement(monitor, scale, look.position, look.custom);
    const size = submenuSize(submenu.items.length, view.appearance.show_hints);
    const placed = submenuPlacement(monitor, dial, scale, size, submenu.preferRight);
    const surface = new Cairo.ImageSurface(Cairo.Format.ARGB32,
        Math.ceil(placed.width * pixels), Math.ceil(placed.height * pixels));
    const cr = new Cairo.Context(surface);
    cr.scale(pixels, pixels);
    paintSubmenu(cr, view, placed.side, placed.scale);
    for (const row of submenuLayout(view, placed.scale).rows)
        drawIcon(cr, row.title, row.configured, row.x, row.y, row.size, row.color);
    surface.writeToPNG(GLib.build_filenamev([output, `${entry.name}-list.png`]));
    cr.$dispose();
}
