// Renders the README pictures of the on-screen dial with the extension's own
// painting code (gnome/extension/dial.js), outside GNOME Shell.
//
//   gjs -m tools/render_overlay_preview.js [output directory]
//
// Writes overlay-states.png (the dial in its main states),
// overlay-skins.png (the menu in every built-in skin), overlay-shapes.png and
// overlay-example.png (the skins in examples/skins). Icons come from the
// Adwaita symbolic theme, as in the Shell.
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Rsvg from 'gi://Rsvg?version=2.0';
import Cairo from 'cairo';
import System from 'system';

import {
    DIAL_D,
    HINT_H,
    iconLayout,
    iconNameFor,
    paintDial,
    parseColor,
    resolveSkin,
} from '../gnome/extension/dial.js';

const ROOT = GLib.path_get_dirname(GLib.path_get_dirname(System.programPath));
const OUTPUT = ARGV[0] || GLib.build_filenamev([ROOT, 'preview']);
const ACCENT = '#e7b98d';
const ICON_THEMES = ['/usr/share/icons/Adwaita', '/usr/share/icons/AdwaitaLegacy', '/usr/share/icons/hicolor'];

const DEFAULT_MENU = ['Volume', 'Brightness', 'Scroll', 'Zoom', 'Undo / Redo', 'Media'];
const DEFAULT_COLORS = ['#6cb6ff', '#f4c95d', '#9ad17b', '#e7b98d', '#c99bff', '#ff8f8f'];

function readJson(path) {
    const [, bytes] = Gio.File.new_for_path(path).load_contents(null);
    return JSON.parse(new TextDecoder().decode(bytes));
}

function view(skin, state, details) {
    return {
        skin,
        accent: parseColor(ACCENT, [1, 1, 1, 1]),
        appearance: { scale: 1, show_hints: true, show_pointer: true },
        state: {
            enabled: true,
            title: '',
            titles: [],
            icons: [],
            menuTitles: DEFAULT_MENU,
            menuIcons: DEFAULT_MENU.map(() => ''),
            value: 0,
            valueAngleStart: 0,
            unit: '',
            centerPressed: false,
            valueShowOnlyProgress: false,
            touching: true,
            ...state,
        },
        details: { profile: '', mode: 'multi', colors: DEFAULT_COLORS, color: '', hints: {}, pointer: -1, ...details },
    };
}

// The four states shown at the top of the README.
function scenes(skin) {
    const selected = { titles: DEFAULT_MENU.map(() => ''), icons: DEFAULT_MENU.map(() => '') };
    return [
        view(skin,
            { title: 'Zoom', titles: DEFAULT_MENU, icons: DEFAULT_MENU.map(() => '') },
            { profile: 'Default', pointer: 228 }),
        view(skin,
            { ...selected, title: 'Volume', value: 64, unit: '%' },
            { profile: 'Default', color: '#6cb6ff', pointer: 118, hints: { ccw: 'Quieter', cw: 'Louder', center: 'Mute' } }),
        view(skin,
            { ...selected, title: 'Zoom' },
            { profile: 'darktable', color: '#e7b98d', pointer: 292, hints: { ccw: 'Zoom out', cw: 'Zoom in', center: 'Fit image' } }),
        view(skin,
            { ...selected, title: 'Brush size' },
            { profile: 'Krita', mode: 'single', color: '#ffad66', pointer: 32, hints: { ccw: 'Smaller brush', cw: 'Larger brush' } }),
    ];
}

const iconCache = new Map();

function findIcon(name) {
    if (iconCache.has(name))
        return iconCache.get(name);
    let found = null;
    for (const theme of ICON_THEMES) {
        const directory = Gio.File.new_for_path(theme);
        if (!directory.query_exists(null))
            continue;
        found = searchDirectory(directory, `${name}.svg`, 3);
        if (found)
            break;
    }
    iconCache.set(name, found);
    return found;
}

function searchDirectory(directory, fileName, depth) {
    const direct = directory.get_child(fileName);
    if (direct.query_exists(null))
        return direct.get_path();
    if (depth === 0)
        return null;
    const enumerator = directory.enumerate_children('standard::name,standard::type', Gio.FileQueryInfoFlags.NONE, null);
    for (let info = enumerator.next_file(null); info; info = enumerator.next_file(null)) {
        if (info.get_file_type() !== Gio.FileType.DIRECTORY)
            continue;
        const found = searchDirectory(directory.get_child(info.get_name()), fileName, depth - 1);
        if (found)
            return found;
    }
    return null;
}

function drawIcon(cr, title, configured, x, y, size, color) {
    const path = configured?.startsWith('/') ? configured : findIcon(configured || iconNameFor(title));
    if (!path)
        return;
    const handle = Rsvg.Handle.new_from_file(path);
    // Symbolic icons are masks recoloured with the requested colour.
    cr.pushGroup();
    handle.render_document(cr, new Rsvg.Rectangle({ x, y, width: size, height: size }));
    const mask = cr.popGroup();
    cr.setSourceRGBA(...color);
    cr.mask(mask);
}

function drawDial(cr, dialView, x, y) {
    cr.save();
    cr.translate(x, y);
    paintDial(cr, dialView);
    const { menu, menuVisible, center } = iconLayout(dialView);
    if (menuVisible) {
        for (const icon of menu)
            drawIcon(cr, icon.title, icon.configured, icon.x, icon.y, icon.size, icon.color);
    }
    if (center)
        drawIcon(cr, center.title, center.configured, center.x, center.y, center.size, center.color);
    cr.restore();
}

function background(cr, width, height) {
    const gradient = new Cairo.LinearGradient(0, 0, width, height);
    gradient.addColorStopRGBA(0, 0.22, 0.25, 0.40, 1);
    gradient.addColorStopRGBA(0.55, 0.30, 0.31, 0.37, 1);
    gradient.addColorStopRGBA(1, 0.36, 0.33, 0.27, 1);
    cr.rectangle(0, 0, width, height);
    cr.setSource(gradient);
    cr.fill();
}

function caption(cr, text, x, y) {
    cr.save();
    cr.selectFontFace('Adwaita Sans', Cairo.FontSlant.NORMAL, Cairo.FontWeight.BOLD);
    cr.setFontSize(15);
    const extents = cr.textExtents(text);
    cr.moveTo(x - extents.width / 2 - extents.xBearing, y);
    cr.setSourceRGBA(1, 1, 1, 0.9);
    cr.showText(text);
    cr.restore();
}

function renderRow(path, dials, captions) {
    const cell = 420;
    const pad = 40;
    const top = captions ? 44 : 30;
    const width = pad * 2 + dials.length * cell - (cell - DIAL_D);
    // Menus have no hint bar below the disc.
    const height = top + DIAL_D + (captions ? 16 : HINT_H + 24);
    const surface = new Cairo.ImageSurface(Cairo.Format.ARGB32, width, height);
    const cr = new Cairo.Context(surface);
    background(cr, width, height);
    dials.forEach((dialView, index) => {
        const x = pad + index * cell;
        if (captions)
            caption(cr, captions[index], x + DIAL_D / 2, 30);
        drawDial(cr, dialView, x, top);
    });
    surface.writeToPNG(path);
    cr.$dispose();
    print(`wrote ${path}`);
}

const skins = readJson(GLib.build_filenamev([ROOT, 'gnome', 'extension', 'skins.json']));
GLib.mkdir_with_parents(OUTPUT, 0o755);
renderRow(GLib.build_filenamev([OUTPUT, 'overlay-states.png']), scenes(resolveSkin(skins, 'glass')));
const ids = Object.keys(skins);
renderRow(
    GLib.build_filenamev([OUTPUT, 'overlay-skins.png']),
    ids.map(id => scenes(resolveSkin(skins, id))[0]),
    ids.map(id => skins[id].name || id));

// Shapes a skin can take, on top of built-in looks.
const shapes = {
    'Square': { base: 'glass', shape: 'square', tile: 'square' },
    'Octagon': { base: 'midnight', shape: 'octagon', tile: 'hexagon' },
    'Knurled': { base: 'proart', shape: 'knurled', tile: 'diamond' },
    'Drawn: star': { base: 'glass', shape: 'custom', tileSize: 0.85, outline: { points: [1, 0.72, 1, 0.72, 1, 0.72, 1, 0.72, 1, 0.72], smooth: false } },
    'Drawn: flower': { base: 'frost', shape: 'custom', outline: { points: [1, 0.86, 1, 0.86, 1, 0.86, 1, 0.86, 1, 0.86, 1, 0.86], smooth: true } },
};
const withShapes = { ...skins };
for (const [name, skin] of Object.entries(shapes))
    withShapes[name] = skin;
renderRow(
    GLib.build_filenamev([OUTPUT, 'overlay-shapes.png']),
    Object.keys(shapes).map(name => scenes(resolveSkin(withShapes, name))[0]),
    Object.keys(shapes));

// Example skins with their background pictures, as user skins are loaded.
const examples = GLib.build_filenamev([ROOT, 'examples', 'skins']);
const withExamples = { ...skins };
const exampleIds = [];
const enumerator = Gio.File.new_for_path(examples).enumerate_children('standard::name', Gio.FileQueryInfoFlags.NONE, null);
for (let info = enumerator.next_file(null); info; info = enumerator.next_file(null)) {
    const name = info.get_name();
    if (!name.endsWith('.json'))
        continue;
    const id = name.slice(0, -5);
    withExamples[id] = { ...readJson(GLib.build_filenamev([examples, name])), __dir: examples };
    exampleIds.push(id);
}
exampleIds.sort();
renderRow(
    GLib.build_filenamev([OUTPUT, 'overlay-example.png']),
    exampleIds.flatMap(id => scenes(resolveSkin(withExamples, id)).slice(0, 2)));
