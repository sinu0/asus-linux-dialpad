// Painting of the on-screen dial. Shared by the Shell extension and the
// preview renderer in tools/, so it imports nothing from GNOME Shell.
import Cairo from 'cairo';

// Logical geometry; everything is multiplied by the configured scale.
export const DIAL_D = 360;
export const DIAL_R = DIAL_D / 2;
export const HINT_H = 46;
// Room around the disc for its symmetric shadow.
const OUTER_R = 162;
const ICON_R = 113;
const BUBBLE_R = 27;
const HIGHLIGHT_R = 152;
const GAUGE_R = 136;
const GAUGE_W = 11;
const CENTER_R = 70;
// Half the size of the square around the centre disc and its halo.
const CENTER_EXTENT = CENTER_R + 12;
const POINTER_GLOW_R = 15;
// Side of the square the finger dot is painted in.
export const POINTER_SIZE = 2 * POINTER_GLOW_R;
const ICON_SIZE = 20;
const CENTER_ICON_SIZE = 26;
// Level gauges open at the bottom like a knob scale.
const GAUGE_START = 0.75 * Math.PI;
const GAUGE_SWEEP = 1.5 * Math.PI;
const FONT = 'Adwaita Sans';

export const DEFAULT_SKIN = 'glass';

// Used when skins.json cannot be read: the dark glass look.
export const FALLBACK_SKIN = {
    name: 'Dark glass',
    menu: 'bubbles',
    palette: {
        surfaceTop: [0.17, 0.175, 0.205, 0.97],
        surfaceBottom: [0.085, 0.09, 0.105, 0.97],
        rim: [1, 1, 1, 0.09],
        bubble: [1, 1, 1, 0.07],
        segment: [1, 1, 1, 0.06],
        track: [1, 1, 1, 0.08],
        detent: [1, 1, 1, 0.16],
        freeSlot: [1, 1, 1, 0.14],
        centerTop: [0.205, 0.21, 0.245, 1],
        centerBottom: [0.125, 0.13, 0.15, 1],
        text: [0.96, 0.95, 0.93, 1],
        muted: [0.70, 0.69, 0.67, 1],
        icon: [0.86, 0.85, 0.83, 0.85],
        iconOnColor: [0.08, 0.08, 0.09, 1],
        pointer: [1, 1, 1, 0.95],
        shadow: 0.45,
    },
};

// Function names map to GNOME (Adwaita) symbolic icons, the same set the
// settings app uses. First match wins, so specific words come first.
const ICON_RULES = [
    [['record'], 'media-record'],
    [['stream'], 'network-transmit'],
    [['pause'], 'media-playback-pause'],
    [['mic'], 'audio-input-microphone'],
    [['replay', 'save'], 'document-save'],
    [['point', 'cut', 'split', 'clip', 'snap'], 'edit-cut'],
    [['layer'], 'view-list'],
    [['keyframe'], 'starred'],
    [['arrange', 'order'], 'view-sort-ascending'],
    [['cursor'], 'go-next'],
    [['mirror'], 'object-flip-horizontal'],
    [['mute'], 'audio-volume-muted'],
    [['volume', 'audio', 'sound'], 'audio-volume-high'],
    [['keyboard'], 'keyboard-brightness'],
    [['bright', 'exposure', 'light'], 'display-brightness'],
    [['horizontal'], 'object-flip-horizontal'],
    [['scroll'], 'object-flip-vertical'],
    [['timeline'], 'zoom-fit-best'],
    [['zoom'], 'system-search'],
    [['undo', 'history', 'edit'], 'edit-undo'],
    [['redo'], 'edit-redo'],
    [['seek', 'shuttle'], 'media-seek-forward'],
    [['frame'], 'media-skip-forward'],
    [['media', 'track', 'play', 'music'], 'media-playback-start'],
    [['workspace'], 'view-grid'],
    [['tab'], 'view-paged'],
    [['back', 'forward', 'arrow'], 'go-next'],
    [['brush', 'opacity', 'paint', 'draw'], 'document-edit'],
    [['rotate'], 'object-rotate-right'],
    [['scale'], 'zoom-fit-best'],
    [['photo', 'image'], 'image-x-generic'],
    [['rating', 'star'], 'starred'],
    [['label', 'colour', 'color'], 'color-select'],
    [['font', 'text'], 'font-x-generic'],
    [['notif'], 'preferences-system-notifications'],
];

export function iconNameFor(title) {
    const name = (title || '').toLowerCase();
    for (const [words, icon] of ICON_RULES) {
        if (words.some(word => name.includes(word)))
            return `${icon}-symbolic`;
    }
    return 'input-dialpad-symbolic';
}

export function parseColor(text, fallback) {
    const match = /^#?([0-9a-f]{6})$/i.exec(String(text || '').trim());
    if (!match)
        return fallback;
    const value = parseInt(match[1], 16);
    return [(value >> 16 & 255) / 255, (value >> 8 & 255) / 255, (value & 255) / 255, 1];
}

// Skin colours are [r, g, b, a] with channels from 0 to 1, or "#rrggbb" /
// "#rrggbbaa" strings; anything else falls back.
function skinColor(value, fallback) {
    if (Array.isArray(value) && value.length >= 3 && value.every(channel => Number.isFinite(Number(channel)))) {
        const [r, g, b, a = 1] = value.map(channel => Math.max(0, Math.min(1, Number(channel))));
        return [r, g, b, a];
    }
    const match = /^#?([0-9a-f]{6})([0-9a-f]{2})?$/i.exec(String(value ?? '').trim());
    if (!match)
        return fallback;
    const rgb = parseColor(match[1], fallback);
    return [rgb[0], rgb[1], rgb[2], match[2] ? parseInt(match[2], 16) / 255 : 1];
}

// Picks a skin by id from { id: skin }. A skin may name a "base" skin and
// override only some colours; missing colours come from the base, then from
// the fallback, so a partial or broken skin never breaks painting.
export function resolveSkin(skins, id) {
    const chain = [];
    let current = skins?.[id] ?? skins?.[DEFAULT_SKIN];
    while (current && typeof current === 'object' && !chain.includes(current) && chain.length < 8) {
        chain.unshift(current);
        current = skins?.[current.base];
    }
    let menu = FALLBACK_SKIN.menu;
    const palette = { ...FALLBACK_SKIN.palette };
    for (const skin of chain) {
        if (skin.menu === 'segments' || skin.menu === 'bubbles')
            menu = skin.menu;
        for (const [key, fallback] of Object.entries(FALLBACK_SKIN.palette)) {
            const value = skin.palette?.[key];
            if (value === undefined)
                continue;
            if (key === 'shadow') {
                const number = Number(value);
                palette.shadow = Number.isFinite(number) ? Math.max(0, Math.min(1, number)) : palette.shadow;
            } else {
                palette[key] = skinColor(value, palette[key] ?? fallback);
            }
        }
    }
    return { menu, palette };
}

function truncate(text, length) {
    text = String(text || '');
    return text.length > length ? `${text.slice(0, length - 1)}…` : text;
}

// --- state helpers ------------------------------------------------------
//
// A view is { state, details, appearance, accent, skin }: the driver's
// overlay state and details, the overlay section of config.json, the parsed
// accent colour and a resolved skin.

export function segmentState(state) {
    const menu = state.titles.some(label => Boolean(label));
    const titles = menu ? state.titles : state.menuTitles;
    const icons = menu ? state.icons : state.menuIcons;
    return { titles, icons, count: Math.max(titles.length, 4) };
}

export function isSelectedMode(state) {
    return Boolean(state.title) && state.title !== 'Menu' && !state.titles.some(label => Boolean(label));
}

function segmentColor(view, index) {
    return parseColor(view.details.colors?.[index], view.accent);
}

function functionColor(view) {
    return parseColor(view.details.color, view.accent);
}

function activeColor(view) {
    const { titles } = segmentState(view.state);
    const index = titles.indexOf(view.state.title);
    return index >= 0 ? segmentColor(view, index) : view.accent;
}

// Where the extension places its icon actors, relative to the dial's top
// left corner and already scaled: menu icons (hidden while a function is
// selected, its gauge takes their place) and the centre icon.
export function iconLayout(view) {
    const { state, appearance, skin } = view;
    const { titles, icons, count } = segmentState(state);
    const activeTitle = state.title === 'Menu' ? '' : state.title;
    const scale = appearance.scale;
    const selected = isSelectedMode(state);
    const slice = (2 * Math.PI) / count;
    const size = Math.round(ICON_SIZE * scale);
    const menu = [];
    for (let index = 0; index < count; index++) {
        if (!titles[index])
            continue;
        const angle = (index + 0.5) * slice - Math.PI / 2;
        const active = titles[index] === activeTitle;
        menu.push({
            title: titles[index],
            configured: icons[index] || '',
            x: Math.round((DIAL_R + Math.cos(angle) * ICON_R) * scale - size / 2),
            y: Math.round((DIAL_R + Math.sin(angle) * ICON_R) * scale - size / 2),
            size,
            color: active ? skin.palette.iconOnColor : skin.palette.icon,
        });
    }

    let center = null;
    const hovered = Boolean(state.title) && state.title !== 'Menu' && !selected;
    if (selected || hovered) {
        const index = titles.indexOf(state.title);
        const centerSize = Math.round(CENTER_ICON_SIZE * scale);
        const offset = selected ? 34 : 26;
        center = {
            title: state.title,
            configured: index >= 0 ? icons[index] || '' : '',
            x: Math.round(DIAL_R * scale - centerSize / 2),
            y: Math.round((DIAL_R - offset) * scale - centerSize / 2),
            size: centerSize,
            color: selected ? functionColor(view) : activeColor(view),
        };
    }
    return { menu, menuVisible: !selected, center };
}

// --- painting -----------------------------------------------------------

// The dial in one go (previews). The Shell extension paints the three
// layers separately so a moving finger repaints nothing: the background
// only changes with the skin or scale, the content with the state, and the
// finger dot is an actor that moves.
export function paintDial(cr, view) {
    paintBackground(cr, view);
    paintContent(cr, view);
    const pointer = pointerPlacement(view);
    if (pointer) {
        cr.save();
        cr.scale(view.appearance.scale, view.appearance.scale);
        drawPointer(cr, view, pointer.x, pointer.y, pointer.color);
        cr.restore();
    }
}

export function paintBackground(cr, view) {
    cr.save();
    cr.scale(view.appearance.scale, view.appearance.scale);
    drawSurface(cr, view, DIAL_R, DIAL_R);
    cr.restore();
}

// cache: optional object the caller keeps between calls; it holds the
// centre disc, the most expensive part, as a ready-made image.
export function paintContent(cr, view, cache = null) {
    cr.save();
    cr.scale(view.appearance.scale, view.appearance.scale);
    if (isSelectedMode(view.state))
        drawGauge(cr, view, DIAL_R, DIAL_R);
    else if (view.skin.menu === 'segments')
        drawSegmentMenu(cr, view, DIAL_R, DIAL_R);
    else
        drawBubbleMenu(cr, view, DIAL_R, DIAL_R);
    drawCenter(cr, view, DIAL_R, DIAL_R, cache);
    drawHints(cr, view, DIAL_R, DIAL_D + HINT_H / 2);
    cr.restore();
}

// Everything paintContent() depends on besides the skin and the overlay
// settings; equal keys paint equal content.
export function contentKey(view) {
    const { state, details } = view;
    return JSON.stringify([
        state.enabled, state.title, state.titles, state.menuTitles, state.value,
        state.valueAngleStart, state.unit, state.centerPressed, state.valueShowOnlyProgress,
        details.profile, details.mode, details.colors, details.color, details.hints,
    ]);
}

// Centre of the finger dot in unscaled dial units and its glow colour, or
// null when no dot is shown.
export function pointerPlacement(view) {
    const pointer = Number(view.details.pointer);
    if (!view.appearance.show_pointer || !view.state.touching || !(pointer >= 0))
        return null;
    const selected = isSelectedMode(view.state);
    const radius = selected ? GAUGE_R : HIGHLIGHT_R;
    const angle = pointer * Math.PI / 180 - Math.PI / 2;
    return {
        x: DIAL_R + Math.cos(angle) * radius,
        y: DIAL_R + Math.sin(angle) * radius,
        color: selected ? functionColor(view) : view.skin.palette.pointer,
    };
}

// The finger dot centred in a POINTER_SIZE square (scaled).
export function paintPointer(cr, view, color) {
    cr.save();
    cr.scale(view.appearance.scale, view.appearance.scale);
    drawPointer(cr, view, POINTER_GLOW_R, POINTER_GLOW_R, color);
    cr.restore();
}

function drawSurface(cr, view, cx, cy) {
    const palette = view.skin.palette;
    cr.save();
    // Soft shadow centred under the disc, slightly lower like a light
    // from above; concentric so the dial never looks off-centre.
    const shadow = new Cairo.RadialGradient(cx, cy + 4, OUTER_R - 6, cx, cy + 4, OUTER_R + 16);
    shadow.addColorStopRGBA(0, 0, 0, 0, palette.shadow);
    shadow.addColorStopRGBA(1, 0, 0, 0, 0);
    cr.arc(cx, cy + 4, OUTER_R + 16, 0, 2 * Math.PI);
    cr.setSource(shadow);
    cr.fill();

    const surface = new Cairo.LinearGradient(cx, cy - OUTER_R, cx, cy + OUTER_R);
    surface.addColorStopRGBA(0, ...palette.surfaceTop);
    surface.addColorStopRGBA(1, ...palette.surfaceBottom);
    cr.arc(cx, cy, OUTER_R, 0, 2 * Math.PI);
    cr.setSource(surface);
    cr.fill();

    cr.arc(cx, cy, OUTER_R - 0.5, 0, 2 * Math.PI);
    cr.setLineWidth(1);
    cr.setSourceRGBA(...palette.rim);
    cr.stroke();
    cr.restore();
}

function menuSlices(view) {
    const { titles, count } = segmentState(view.state);
    const slice = (2 * Math.PI) / count;
    const activeTitle = view.state.title === 'Menu' ? '' : view.state.title;
    return Array.from({ length: count }, (_, index) => {
        const label = titles[index] || '';
        return {
            index,
            label,
            active: Boolean(label) && label === activeTitle,
            start: index * slice - Math.PI / 2,
            end: (index + 1) * slice - Math.PI / 2,
            mid: (index + 0.5) * slice - Math.PI / 2,
        };
    });
}

function wedge(cr, cx, cy, inner, outer, start, end) {
    cr.newPath();
    cr.moveTo(cx + Math.cos(start) * inner, cy + Math.sin(start) * inner);
    cr.arc(cx, cy, outer, start, end);
    cr.arcNegative(cx, cy, inner, end, start);
    cr.closePath();
}

function drawBubbleMenu(cr, view, cx, cy) {
    const palette = view.skin.palette;
    cr.save();
    cr.setLineCap(Cairo.LineCap.ROUND);

    for (const { index, label, active, start, end, mid } of menuSlices(view)) {
        const x = cx + Math.cos(mid) * ICON_R;
        const y = cy + Math.sin(mid) * ICON_R;

        if (!label) {
            // A free slot is a quiet dot, not a dark hole in the ring.
            cr.arc(x, y, 3, 0, 2 * Math.PI);
            cr.setSourceRGBA(...palette.freeSlot);
            cr.fill();
            continue;
        }

        const color = segmentColor(view, index);
        if (active) {
            // Glow of the chosen slice and an arc on the rim.
            wedge(cr, cx, cy, CENTER_R + 8, OUTER_R - 3, start + 0.06, end - 0.06);
            cr.setSourceRGBA(color[0], color[1], color[2], 0.07);
            cr.fill();

            cr.setLineWidth(4);
            cr.setSourceRGBA(...color);
            cr.arc(cx, cy, HIGHLIGHT_R, start + 0.1, end - 0.1);
            cr.stroke();
        }

        cr.newPath();
        cr.arc(x, y, BUBBLE_R, 0, 2 * Math.PI);
        if (active) {
            cr.setSourceRGBA(...color);
            cr.fill();
        } else {
            cr.setSourceRGBA(...palette.bubble);
            cr.fill();
            // A small colour key keeps functions recognisable.
            cr.arc(x, y, BUBBLE_R - 0.75, mid + Math.PI - 0.55, mid + Math.PI + 0.55);
            cr.setLineWidth(1.5);
            cr.setSourceRGBA(color[0], color[1], color[2], 0.75);
            cr.stroke();
        }
    }
    cr.restore();
}

function drawSegmentMenu(cr, view, cx, cy) {
    // The ASUS Dial look: one sector per function with a colour key on its
    // inner edge; the chosen sector fills with its colour.
    const palette = view.skin.palette;
    const inner = CENTER_R + 8;
    const outer = OUTER_R - 6;
    cr.save();
    for (const { index, label, active, start, end } of menuSlices(view)) {
        const from = start + 0.02;
        const to = end - 0.02;
        wedge(cr, cx, cy, inner, outer, from, to);
        if (!label) {
            cr.setSourceRGBA(...palette.freeSlot);
            cr.fill();
            continue;
        }
        const color = segmentColor(view, index);
        cr.setSourceRGBA(...(active ? color : palette.segment));
        cr.fill();
        if (!active) {
            cr.newPath();
            cr.arc(cx, cy, inner + 3, from + 0.04, to - 0.04);
            cr.setLineWidth(3);
            cr.setSourceRGBA(...color);
            cr.stroke();
        }
    }
    cr.restore();
}

function drawGauge(cr, view, cx, cy) {
    const { state } = view;
    const palette = view.skin.palette;
    const color = functionColor(view);
    const number = Number(state.value);
    const value = Number.isFinite(number) ? number : null;
    const level = !state.valueShowOnlyProgress && state.unit === '%' && value !== null;
    cr.save();
    cr.setLineCap(Cairo.LineCap.ROUND);
    cr.setLineWidth(GAUGE_W);

    if (level) {
        // Level functions (volume, brightness…) get a knob-style scale.
        cr.setSourceRGBA(...palette.track);
        cr.arc(cx, cy, GAUGE_R, GAUGE_START, GAUGE_START + GAUGE_SWEEP);
        cr.stroke();
        const fraction = Math.max(0, Math.min(1, value / 100));
        if (fraction > 0.005) {
            cr.setSourceRGBA(...color);
            cr.arc(cx, cy, GAUGE_R, GAUGE_START, GAUGE_START + fraction * GAUGE_SWEEP);
            cr.stroke();
        }
    } else {
        // Endless functions show detents, like the notches of a wheel.
        cr.setSourceRGBA(...palette.track);
        cr.arc(cx, cy, GAUGE_R, 0, 2 * Math.PI);
        cr.stroke();
        cr.setLineWidth(2);
        for (let index = 0; index < 24; index++) {
            const angle = index / 24 * 2 * Math.PI;
            cr.moveTo(cx + Math.cos(angle) * (GAUGE_R - 3), cy + Math.sin(angle) * (GAUGE_R - 3));
            cr.lineTo(cx + Math.cos(angle) * (GAUGE_R + 3), cy + Math.sin(angle) * (GAUGE_R + 3));
        }
        cr.setSourceRGBA(...palette.detent);
        cr.stroke();
    }

    if (state.valueShowOnlyProgress) {
        // Progress towards the next step of slow functions (Undo…).
        const fraction = Math.max(-1, Math.min(1, state.value / 100));
        if (Math.abs(fraction) >= 0.01) {
            const start = state.valueAngleStart * Math.PI / 180 - Math.PI / 2;
            cr.setLineWidth(GAUGE_W);
            cr.setSourceRGBA(...color);
            if (fraction > 0)
                cr.arc(cx, cy, GAUGE_R, start, start + fraction * 2 * Math.PI);
            else
                cr.arcNegative(cx, cy, GAUGE_R, start, start + fraction * 2 * Math.PI);
            cr.stroke();
        }
    }
    cr.restore();
}

function drawPointer(cr, view, x, y, color) {
    cr.save();
    const glow = new Cairo.RadialGradient(x, y, 2, x, y, POINTER_GLOW_R);
    glow.addColorStopRGBA(0, color[0], color[1], color[2], 0.55);
    glow.addColorStopRGBA(1, color[0], color[1], color[2], 0);
    cr.arc(x, y, POINTER_GLOW_R, 0, 2 * Math.PI);
    cr.setSource(glow);
    cr.fill();
    cr.arc(x, y, 5.5, 0, 2 * Math.PI);
    cr.setSourceRGBA(...view.skin.palette.pointer);
    cr.fill();
    cr.restore();
}

function drawCenterDisc(cr, palette, cx, cy) {
    const halo = new Cairo.RadialGradient(cx, cy + 2, CENTER_R - 4, cx, cy + 2, CENTER_R + 10);
    halo.addColorStopRGBA(0, 0, 0, 0, palette.shadow * 0.75);
    halo.addColorStopRGBA(1, 0, 0, 0, 0);
    cr.arc(cx, cy + 2, CENTER_R + 10, 0, 2 * Math.PI);
    cr.setSource(halo);
    cr.fill();

    const surface = new Cairo.LinearGradient(cx, cy - CENTER_R, cx, cy + CENTER_R);
    surface.addColorStopRGBA(0, ...palette.centerTop);
    surface.addColorStopRGBA(1, ...palette.centerBottom);
    cr.arc(cx, cy, CENTER_R, 0, 2 * Math.PI);
    cr.setSource(surface);
    cr.fill();
}

// The disc is copied from an image made once per skin and pixel density.
function drawCachedCenterDisc(cr, palette, cx, cy, cache) {
    const pixelScale = cr.userToDeviceDistance(1, 0)[0] * cr.getTarget().getDeviceScale()[0];
    const key = JSON.stringify([pixelScale, palette.shadow, palette.centerTop, palette.centerBottom]);
    if (cache.centerKey !== key) {
        const pixels = Math.ceil(2 * CENTER_EXTENT * pixelScale);
        const image = new Cairo.ImageSurface(Cairo.Format.ARGB32, pixels, pixels);
        image.setDeviceScale(pixelScale, pixelScale);
        const imageCr = new Cairo.Context(image);
        drawCenterDisc(imageCr, palette, CENTER_EXTENT, CENTER_EXTENT);
        imageCr.$dispose();
        cache.centerImage?.finish();
        cache.centerImage = image;
        cache.centerKey = key;
    }
    cr.save();
    cr.setSourceSurface(cache.centerImage, cx - CENTER_EXTENT, cy - CENTER_EXTENT);
    cr.rectangle(cx - CENTER_EXTENT, cy - CENTER_EXTENT, 2 * CENTER_EXTENT, 2 * CENTER_EXTENT);
    cr.fill();
    cr.restore();
}

function drawCenter(cr, view, cx, cy, cache) {
    const { state, details } = view;
    const palette = view.skin.palette;
    const selectedMode = isSelectedMode(state);
    const accent = selectedMode ? functionColor(view) : view.accent;
    cr.save();
    if (cache)
        drawCachedCenterDisc(cr, palette, cx, cy, cache);
    else
        drawCenterDisc(cr, palette, cx, cy);

    cr.arc(cx, cy, CENTER_R - 0.5, 0, 2 * Math.PI);
    cr.setLineWidth(state.centerPressed ? 2.5 : 1);
    cr.setSourceRGBA(...(state.centerPressed ? accent : palette.rim));
    cr.stroke();

    const title = state.title;
    const profile = (details.profile || '').toUpperCase();
    if (selectedMode) {
        const value = !state.valueShowOnlyProgress && state.unit
            ? `${state.value}${state.unit}`
            : '';
        drawCenteredText(cr, truncate(title, 14), cx, cy + 2, title.length > 10 ? 13 : 16, palette.text, true);
        if (value)
            drawCenteredText(cr, value, cx, cy + 27, 18, accent, true);
        else if (profile)
            drawCenteredText(cr, truncate(profile, 16), cx, cy + 26, 8.5, palette.muted, false);
    } else if (title && title !== 'Menu') {
        drawCenteredText(cr, truncate(title, 14), cx, cy + 10, title.length > 10 ? 13 : 16, palette.text, true);
        drawCenteredText(cr, 'Release to select', cx, cy + 32, 8.5, palette.muted, false);
    } else {
        drawCenteredText(cr, truncate(profile || 'DIAL', 14), cx, cy - 8, profile.length > 10 ? 11 : 13, palette.text, true);
        drawCenteredText(cr, 'Choose a function', cx, cy + 14, 9, palette.muted, false);
    }
    cr.restore();
}

function drawHints(cr, view, cx, cy) {
    if (!view.appearance.show_hints || !isSelectedMode(view.state))
        return;
    const palette = view.skin.palette;
    const hints = view.details.hints || {};
    const multi = view.details.mode !== 'single';
    const ccw = truncate(hints.ccw, 20);
    const cw = truncate(hints.cw, 20);
    let center = '';
    if (hints.center) {
        const action = truncate(hints.center, 26);
        center = multi ? `Tap: ${action}  ·  Hold: menu` : `Tap: ${action}`;
    } else if (multi) {
        center = 'Tap centre: menu';
    }
    if (!ccw && !cw && !center)
        return;

    const width = 300;
    const height = center ? 40 : 24;
    const top = cy - HINT_H / 2 + 2;
    cr.save();
    roundedRect(cr, cx - width / 2, top, width, height, 12);
    cr.setSourceRGBA(...palette.surfaceBottom);
    cr.fillPreserve();
    cr.setLineWidth(1);
    cr.setSourceRGBA(...palette.rim);
    cr.stroke();
    const arrowColor = functionColor(view);
    if (ccw) {
        drawTurnArrow(cr, cx - width / 2 + 18, top + 12, false, arrowColor);
        drawAlignedText(cr, ccw, cx - width / 2 + 30, top + 12, 11, palette.text, 'left');
    }
    if (cw) {
        drawTurnArrow(cr, cx + width / 2 - 18, top + 12, true, arrowColor);
        drawAlignedText(cr, cw, cx + width / 2 - 30, top + 12, 11, palette.text, 'right');
    }
    if (center)
        drawCenteredText(cr, center, cx, top + 29, 9, palette.muted, false);
    cr.restore();
}

function drawTurnArrow(cr, x, y, clockwise, color) {
    // Drawn instead of ↺/↻, which the Cairo toy font cannot render.
    const radius = 5.5;
    const start = clockwise ? -Math.PI * 0.85 : -Math.PI * 0.15;
    const end = clockwise ? Math.PI * 0.45 : Math.PI * 0.55;
    cr.save();
    // showText() leaves a current point; start a fresh path.
    cr.newPath();
    cr.setLineWidth(1.6);
    cr.setLineCap(Cairo.LineCap.ROUND);
    cr.setSourceRGBA(...color);
    if (clockwise)
        cr.arc(x, y, radius, start, end);
    else
        cr.arcNegative(x, y, radius, start, end);
    cr.stroke();
    const tipX = x + Math.cos(end) * radius;
    const tipY = y + Math.sin(end) * radius;
    const tangent = end + (clockwise ? Math.PI / 2 : -Math.PI / 2);
    for (const spread of [0.5, -0.5]) {
        const angle = tangent + Math.PI + spread;
        cr.moveTo(tipX, tipY);
        cr.lineTo(tipX + Math.cos(angle) * 4, tipY + Math.sin(angle) * 4);
    }
    cr.stroke();
    cr.restore();
}

function roundedRect(cr, x, y, width, height, radius) {
    cr.newSubPath();
    cr.arc(x + width - radius, y + radius, radius, -Math.PI / 2, 0);
    cr.arc(x + width - radius, y + height - radius, radius, 0, Math.PI / 2);
    cr.arc(x + radius, y + height - radius, radius, Math.PI / 2, Math.PI);
    cr.arc(x + radius, y + radius, radius, Math.PI, 1.5 * Math.PI);
    cr.closePath();
}

function setFont(cr, size, bold) {
    cr.setFontSize(size);
    cr.selectFontFace(FONT, Cairo.FontSlant.NORMAL, bold ? Cairo.FontWeight.BOLD : Cairo.FontWeight.NORMAL);
}

function drawCenteredText(cr, text, x, y, size, color, bold) {
    cr.save();
    cr.setSourceRGBA(...color);
    setFont(cr, size, bold);
    const extents = cr.textExtents(text);
    cr.moveTo(x - extents.width / 2 - extents.xBearing, y + extents.height / 2);
    cr.showText(text);
    cr.restore();
}

function drawAlignedText(cr, text, x, y, size, color, align) {
    cr.save();
    cr.setSourceRGBA(...color);
    setFont(cr, size, false);
    const extents = cr.textExtents(text);
    const left = align === 'right' ? x - extents.width - extents.xBearing : x - extents.xBearing;
    cr.moveTo(left, y + extents.height / 2);
    cr.showText(text);
    cr.restore();
}
