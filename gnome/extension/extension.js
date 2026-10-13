import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import St from 'gi://St';
import Clutter from 'gi://Clutter';
import Cairo from 'cairo';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';

const BUS_NAME = 'io.github.asuslinuxdrivers.DialPad';
const BUS_PATH = '/io/github/asuslinuxdrivers/DialPad';
const BUS_IFACE = BUS_NAME;
const CONFIG_DIR = GLib.build_filenamev([GLib.get_user_config_dir(), 'asus-dialpad']);
const CONFIG_NAME = 'config.json';

// The warm graphite and champagne accents follow the ProArt Creator Hub
// visual language while retaining enough contrast for GNOME's dark shell.
const PALETTE = {
    ink: [0.075, 0.078, 0.09, 0.96],
    ringEdge: [0.42, 0.42, 0.46, 0.56],
    track: [0.21, 0.215, 0.25, 0.98],
    segment: [0.255, 0.26, 0.3, 0.98],
    segmentDim: [0.18, 0.185, 0.215, 0.98],
    champagne: [0.96, 0.82, 0.67, 1],
    paper: [0.985, 0.91, 0.81, 1],
    muted: [0.73, 0.70, 0.67, 0.92],
    shadow: [0, 0, 0, 0.5],
};

// Logical geometry; everything is multiplied by the configured scale.
const DIAL_D = 360;
const DIAL_R = DIAL_D / 2;
const HINT_H = 46;
const OUTER_R = 169;
const RING_OUTER = 154;
const RING_INNER = 104;
const CENTER_R = 88;
// Segment icons occupy the optical centre of the ring.  Keeping their
// complete bounding box inside this radius avoids the bottom sectors looking
// as if their icons spill over the dial edge.
const ICON_R = 127;
const TICK_COUNT = 56;
const ICON_SIZE = 22;
const CENTER_ICON_SIZE = 30;

// Function names map to GNOME (Adwaita) symbolic icons, the same set the
// settings app uses. First match wins, so specific words come first.
const ICON_RULES = [
    [['mute'], 'audio-volume-muted'],
    [['volume', 'audio', 'sound'], 'audio-volume-high'],
    [['keyboard'], 'keyboard-brightness'],
    [['bright', 'exposure', 'light'], 'display-brightness'],
    [['horizontal'], 'object-flip-horizontal'],
    [['scroll'], 'view-continuous'],
    [['timeline'], 'zoom-fit-best'],
    [['zoom'], 'zoom-in'],
    [['redo'], 'edit-redo'],
    [['undo', 'history', 'edit'], 'edit-undo'],
    [['seek', 'shuttle'], 'media-seek-forward'],
    [['frame'], 'media-skip-forward'],
    [['media', 'track', 'play', 'music'], 'media-playback-start'],
    [['workspace'], 'view-grid'],
    [['tab'], 'tab-new'],
    [['back', 'forward', 'arrow'], 'go-next'],
    [['brush', 'opacity', 'paint', 'draw'], 'document-edit'],
    [['rotate'], 'object-rotate-right'],
    [['scale'], 'object-select'],
    [['photo', 'image'], 'image-x-generic'],
    [['rating', 'star'], 'starred'],
    [['label', 'colour', 'color'], 'bookmark-new'],
    [['font', 'text'], 'font-x-generic'],
    [['notif'], 'preferences-system-notifications'],
];
const FADE_IN_MS = 120;
const FADE_OUT_MS = 260;

const DEFAULT_APPEARANCE = {
    scale: 1.0,
    position: 'lower',
    hide_delay_ms: 1500,
    show_hints: true,
    show_pointer: true,
    accent: '#e7b98d',
};

function parseColor(text, fallback) {
    const match = /^#?([0-9a-f]{6})$/i.exec(String(text || '').trim());
    if (!match)
        return fallback;
    const value = parseInt(match[1], 16);
    return [(value >> 16 & 255) / 255, (value >> 8 & 255) / 255, (value & 255) / 255, 1];
}

function truncate(text, length) {
    text = String(text || '');
    return text.length > length ? `${text.slice(0, length - 1)}…` : text;
}

function mix(color, other, amount) {
    return color.map((channel, index) => channel * (1 - amount) + other[index] * amount);
}

export default class DialPadExtension extends Extension {
    enable() {
        this._signalId = 0;
        this._detailsSignalId = 0;
        this._focusHandlerId = 0;
        this._monitorsId = 0;
        this._configMonitor = null;
        this._configMonitorId = 0;
        this._configReloadId = 0;
        this._overlay = null;
        this._drawingArea = null;
        this._iconLayer = null;
        this._iconKey = '';
        this._hideTimeoutId = 0;
        this._shown = false;
        this._appearance = { ...DEFAULT_APPEARANCE };
        this._state = {
            enabled: false,
            title: '',
            titles: [],
            icons: [],
            menuTitles: [],
            menuIcons: [],
            value: 0,
            valueAngleStart: 0.0,
            unit: '',
            centerPressed: false,
            valueShowOnlyProgress: false,
            touching: false,
        };
        this._details = {
            profile: '',
            mode: 'multi',
            colors: [],
            color: '',
            hints: {},
            hold_returns: true,
            pointer: -1,
        };

        try {
            this._loadAppearance();
            this._watchConfig();
            this._connectDBus();
            this._connectFocus();
            this._createOverlay();
            this._fetchDetails();
        } catch (error) {
            log(`dialpad: unable to start overlay: ${error}`);
        }
    }

    disable() {
        this._cancelHide();
        try { this._unwatchConfig(); } catch (_) {}
        try { this._disconnectFocus(); } catch (_) {}
        try { this._disconnectDBus(); } catch (_) {}
        try { this._destroyOverlay(); } catch (_) {}
    }

    // --- appearance from config.json -----------------------------------

    _loadAppearance() {
        const appearance = { ...DEFAULT_APPEARANCE };
        try {
            const file = Gio.File.new_for_path(GLib.build_filenamev([CONFIG_DIR, CONFIG_NAME]));
            const [ok, bytes] = file.load_contents(null);
            if (ok) {
                const overlay = JSON.parse(new TextDecoder().decode(bytes)).overlay || {};
                for (const key of Object.keys(DEFAULT_APPEARANCE)) {
                    if (overlay[key] !== undefined && overlay[key] !== null)
                        appearance[key] = overlay[key];
                }
            }
        } catch (_) {
            // A missing or half-written file keeps the defaults.
        }
        appearance.scale = Math.max(0.6, Math.min(1.6, Number(appearance.scale) || 1));
        appearance.hide_delay_ms = Math.max(0, Math.min(10000, Number(appearance.hide_delay_ms) || 0));
        this._appearance = appearance;
        this._accent = parseColor(appearance.accent, [0.906, 0.725, 0.553, 1]);
    }

    _watchConfig() {
        const directory = Gio.File.new_for_path(CONFIG_DIR);
        try {
            this._configMonitor = directory.monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, null);
        } catch (_) {
            return;
        }
        this._configMonitorId = this._configMonitor.connect('changed', (_monitor, file, other) => {
            const names = [file?.get_basename(), other?.get_basename()];
            if (!names.includes(CONFIG_NAME))
                return;
            if (this._configReloadId)
                GLib.source_remove(this._configReloadId);
            this._configReloadId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 200, () => {
                this._configReloadId = 0;
                this._loadAppearance();
                this._applyGeometry();
                this._iconKey = '';
                this._updateIcons();
                this._drawingArea?.queue_repaint();
                return GLib.SOURCE_REMOVE;
            });
        });
    }

    _unwatchConfig() {
        if (this._configReloadId) {
            GLib.source_remove(this._configReloadId);
            this._configReloadId = 0;
        }
        if (this._configMonitor) {
            if (this._configMonitorId)
                this._configMonitor.disconnect(this._configMonitorId);
            this._configMonitor.cancel();
            this._configMonitor = null;
            this._configMonitorId = 0;
        }
    }

    // --- overlay actors -------------------------------------------------

    _createOverlay() {
        if (!Main.layoutManager?.uiGroup)
            return;

        this._overlay = new St.Widget({ visible: false, reactive: false, opacity: 0 });
        this._drawingArea = new St.DrawingArea();
        this._drawingArea.connect('repaint', this._onRepaint.bind(this));
        this._overlay.add_child(this._drawingArea);
        this._iconLayer = new St.Widget({ reactive: false });
        this._overlay.add_child(this._iconLayer);
        this._centerIcon = new St.Icon({ style_class: 'dialpad-center-icon', visible: false });
        this._overlay.add_child(this._centerIcon);
        Main.layoutManager.uiGroup.add_child(this._overlay);
        this._monitorsId = Main.layoutManager.connect('monitors-changed', () => this._applyGeometry());
        GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
            this._applyGeometry();
            return GLib.SOURCE_REMOVE;
        });
    }

    _destroyOverlay() {
        if (this._monitorsId) {
            Main.layoutManager.disconnect(this._monitorsId);
            this._monitorsId = 0;
        }
        if (!this._overlay)
            return;
        if (this._overlay.get_parent())
            Main.layoutManager.uiGroup.remove_child(this._overlay);
        this._overlay.remove_all_transitions();
        this._overlay.destroy();
        this._overlay = null;
        this._drawingArea = null;
        this._iconLayer = null;
        this._centerIcon = null;
        this._iconKey = '';
        this._shown = false;
    }

    _applyGeometry() {
        if (!this._overlay || !this._drawingArea)
            return;
        const monitor = Main.layoutManager.primaryMonitor;
        if (!monitor)
            return;
        const scale = this._appearance.scale;
        const width = Math.round(DIAL_D * scale);
        const height = Math.round((DIAL_D + HINT_H) * scale);
        this._overlay.set_position(monitor.x, monitor.y);
        this._overlay.set_size(monitor.width, monitor.height);
        this._drawingArea.set_size(width, height);
        this._iconLayer.set_size(width, width);

        const x = Math.round((monitor.width - width) / 2);
        const centred = (monitor.height - width) / 2;
        const positions = {
            center: centred,
            // A slightly lower placement mirrors the unobtrusive Windows ASUS
            // Dial overlay without obscuring the focused application's toolbar.
            lower: centred + Math.min(84, monitor.height * 0.08),
            bottom: monitor.height - height - Math.round(monitor.height * 0.06),
            top: Math.round(monitor.height * 0.08),
        };
        const y = Math.round(positions[this._appearance.position] ?? positions.lower);
        this._drawingArea.set_position(x, y);
        this._iconLayer.set_position(x, y);
        this._dialOrigin = [x, y];
        this._updateIcons();
        this._drawingArea.queue_repaint();
    }

    // --- D-Bus ----------------------------------------------------------

    _connectDBus() {
        this._signalId = Gio.DBus.session.signal_subscribe(
            BUS_NAME, BUS_IFACE, 'OverlayState', BUS_PATH, null,
            Gio.DBusSignalFlags.NONE, this._onOverlayState.bind(this));
        this._detailsSignalId = Gio.DBus.session.signal_subscribe(
            BUS_NAME, BUS_IFACE, 'OverlayDetails', BUS_PATH, null,
            Gio.DBusSignalFlags.NONE, this._onOverlayDetails.bind(this));
    }

    _disconnectDBus() {
        for (const key of ['_signalId', '_detailsSignalId']) {
            if (this[key]) {
                Gio.DBus.session.signal_unsubscribe(this[key]);
                this[key] = 0;
            }
        }
    }

    _fetchDetails() {
        Gio.DBus.session.call(
            BUS_NAME, BUS_PATH, BUS_IFACE, 'GetOverlayDetails', null,
            new GLib.VariantType('(s)'), Gio.DBusCallFlags.NONE, 1000, null,
            (connection, result) => {
                try {
                    const [json] = connection.call_finish(result).deepUnpack();
                    this._mergeDetails(json);
                } catch (_) {
                    // Older drivers have no details; the dial still works.
                }
            });
    }

    _connectFocus() {
        if (!global.display)
            return;
        this._focusHandlerId = global.display.connect('notify::focus-window', this._onFocusWindow.bind(this));
    }

    _disconnectFocus() {
        if (this._focusHandlerId) {
            global.display.disconnect(this._focusHandlerId);
            this._focusHandlerId = 0;
        }
    }

    _mergeDetails(json) {
        try {
            const details = JSON.parse(json);
            if (details && typeof details === 'object')
                Object.assign(this._details, details);
        } catch (_) {}
    }

    _onOverlayDetails(_conn, _sender, _path, _iface, _signal, params) {
        const [json] = params.deepUnpack();
        this._mergeDetails(json);
        this._drawingArea?.queue_repaint();
    }

    _onOverlayState(_conn, _sender, _path, _iface, _signal, params) {
        const [enabled, title, titles, icons, value, valueAngleStart, unit, centerPressed, valueShowOnlyProgress, touching] = params.deepUnpack();
        // Drivers without the touching field keep the dial up while enabled.
        const legacyDriver = params.n_children() < 10;
        const wasEnabled = this._state.enabled;
        this._state.enabled = enabled;
        this._state.title = title || '';
        this._state.titles = titles || [];
        this._state.icons = icons || [];
        if (this._state.titles.some(label => Boolean(label))) {
            this._state.menuTitles = [...this._state.titles];
            this._state.menuIcons = [...this._state.icons];
        }
        this._state.value = value || 0;
        this._state.valueAngleStart = valueAngleStart || 0.0;
        this._state.unit = unit || '';
        this._state.centerPressed = centerPressed || false;
        this._state.valueShowOnlyProgress = valueShowOnlyProgress || false;
        this._state.touching = legacyDriver ? enabled : Boolean(touching);

        this._updateIcons();
        this._updateVisibility(wasEnabled);
        this._drawingArea?.queue_repaint();
    }

    _onFocusWindow() {
        const focusWindow = global.display?.focus_window;
        const tracker = Shell.WindowTracker?.get_default();
        const app = focusWindow && tracker ? tracker.get_window_app(focusWindow) : null;
        const appId = app?.get_id() || '';
        Gio.DBus.session.call(
            BUS_NAME, BUS_PATH, BUS_IFACE, 'SetActiveApplication',
            new GLib.Variant('(s)', [appId]), null,
            Gio.DBusCallFlags.NONE, -1, null, null);
    }

    // --- visibility -----------------------------------------------------

    _updateVisibility(wasEnabled) {
        if (!this._overlay)
            return;
        if (!this._state.enabled) {
            this._hide();
            return;
        }
        if (this._state.touching) {
            this._cancelHide();
            this._show();
            return;
        }
        // Not touching: flash the dial after activation, and let an
        // already visible dial linger so the final value can be read.
        if (!wasEnabled || this._shown) {
            this._show();
            this._scheduleHide();
        }
    }

    _show() {
        if (this._shown)
            return;
        this._shown = true;
        this._overlay.remove_all_transitions();
        this._overlay.visible = true;
        this._overlay.ease({
            opacity: 255,
            duration: FADE_IN_MS,
            mode: Clutter.AnimationMode.EASE_OUT_QUAD,
        });
    }

    _hide() {
        this._cancelHide();
        if (!this._shown || !this._overlay)
            return;
        this._shown = false;
        this._overlay.remove_all_transitions();
        this._overlay.ease({
            opacity: 0,
            duration: FADE_OUT_MS,
            mode: Clutter.AnimationMode.EASE_IN_QUAD,
            onComplete: () => {
                if (this._overlay && !this._shown)
                    this._overlay.visible = false;
            },
        });
    }

    _scheduleHide() {
        this._cancelHide();
        this._hideTimeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, this._appearance.hide_delay_ms, () => {
            this._hideTimeoutId = 0;
            this._hide();
            return GLib.SOURCE_REMOVE;
        });
    }

    _cancelHide() {
        if (this._hideTimeoutId) {
            GLib.source_remove(this._hideTimeoutId);
            this._hideTimeoutId = 0;
        }
    }

    // --- state helpers --------------------------------------------------

    _segmentState() {
        const menu = this._state.titles.some(label => Boolean(label));
        const titles = menu ? this._state.titles : this._state.menuTitles;
        const icons = menu ? this._state.icons : this._state.menuIcons;
        return { titles, icons, count: Math.max(titles.length, 4) };
    }

    _isSelectedMode() {
        return Boolean(this._state.title) && this._state.title !== 'Menu' && !this._state.titles.some(label => Boolean(label));
    }

    _segmentColor(index) {
        return parseColor(this._details.colors?.[index], this._accent);
    }

    _functionColor() {
        return parseColor(this._details.color, this._accent);
    }

    _numericValue() {
        const number = Number(this._state.value);
        return Number.isFinite(number) ? number : null;
    }

    _gicon(title, configured) {
        // A configured icon wins when it exists: an absolute file path or an
        // icon name from the theme.
        if (configured) {
            if (configured.startsWith('/')) {
                if (GLib.file_test(configured, GLib.FileTest.EXISTS))
                    return Gio.FileIcon.new(Gio.File.new_for_path(configured));
            } else {
                return Gio.ThemedIcon.new(configured);
            }
        }
        const name = (title || '').toLowerCase();
        for (const [words, icon] of ICON_RULES) {
            if (words.some(word => name.includes(word)))
                return Gio.ThemedIcon.new(`${icon}-symbolic`);
        }
        return Gio.ThemedIcon.new('input-dialpad-symbolic');
    }

    _cssColor(color, alpha = 1) {
        const [r, g, b] = color.map(channel => Math.round(channel * 255));
        return `color: rgba(${r}, ${g}, ${b}, ${alpha});`;
    }

    _updateIcons() {
        if (!this._iconLayer)
            return;
        const { titles, icons, count } = this._segmentState();
        const activeTitle = this._state.title === 'Menu' ? '' : this._state.title;
        const scale = this._appearance.scale;
        const key = JSON.stringify([titles, icons, count, scale]);

        if (key !== this._iconKey) {
            this._iconKey = key;
            this._iconLayer.destroy_all_children();
            const slice = (2 * Math.PI) / count;
            const size = Math.round(ICON_SIZE * scale);
            for (let index = 0; index < count; index++) {
                if (!titles[index])
                    continue;
                const angle = (index + 0.5) * slice - Math.PI / 2;
                const icon = new St.Icon({
                    gicon: this._gicon(titles[index], icons[index] || ''),
                    icon_size: size,
                    style_class: 'dialpad-segment-icon',
                });
                icon.set_position(
                    Math.round((DIAL_R + Math.cos(angle) * ICON_R) * scale - size / 2),
                    Math.round((DIAL_R + Math.sin(angle) * ICON_R) * scale - size / 2));
                icon._dialpadTitle = titles[index];
                this._iconLayer.add_child(icon);
            }
        }

        // Icons belong to the menu ring only; a selected function shows its
        // value gauge in the same place.
        this._iconLayer.visible = !this._isSelectedMode();
        for (const icon of this._iconLayer.get_children()) {
            const active = icon._dialpadTitle === activeTitle;
            icon.opacity = active ? 255 : 190;
            if (active)
                icon.add_style_pseudo_class('active');
            else
                icon.remove_style_pseudo_class('active');
        }
        this._updateCenterIcon();
    }

    _updateCenterIcon() {
        const icon = this._centerIcon;
        if (!icon)
            return;
        const title = this._state.title;
        const selected = this._isSelectedMode();
        const hovered = Boolean(title) && title !== 'Menu' && !selected;
        icon.visible = selected || hovered;
        if (!icon.visible || !this._dialOrigin)
            return;

        const { titles, icons } = this._segmentState();
        const index = titles.indexOf(title);
        const scale = this._appearance.scale;
        const size = Math.round(CENTER_ICON_SIZE * scale);
        icon.gicon = this._gicon(title, index >= 0 ? icons[index] || '' : '');
        icon.icon_size = size;
        icon.set_style(this._cssColor(selected ? this._functionColor() : PALETTE.champagne));
        const [x, y] = this._dialOrigin;
        const offset = selected ? 36 : 28;
        icon.set_position(
            Math.round(x + DIAL_R * scale - size / 2),
            Math.round(y + (DIAL_R - offset) * scale - size / 2));
    }

    // --- painting -------------------------------------------------------

    _onRepaint(area) {
        const cr = area.get_context();
        cr.save();
        cr.setOperator(Cairo.Operator.CLEAR);
        cr.paint();
        cr.restore();
        if (this._state.enabled) {
            cr.save();
            cr.scale(this._appearance.scale, this._appearance.scale);
            this._drawDialBase(cr, DIAL_R, DIAL_R);
            if (this._isSelectedMode()) {
                this._drawFunctionRing(cr, DIAL_R, DIAL_R);
                this._drawProgress(cr, DIAL_R, DIAL_R);
            } else {
                this._drawSegments(cr, DIAL_R, DIAL_R);
            }
            this._drawPointer(cr, DIAL_R, DIAL_R);
            this._drawCenter(cr, DIAL_R, DIAL_R);
            this._drawHints(cr, DIAL_R, DIAL_D + HINT_H / 2);
            cr.restore();
        }
        // GJS does not free Cairo contexts promptly without this.
        cr.$dispose();
    }

    _drawDialBase(cr, cx, cy) {
        cr.save();
        cr.arc(cx + 4, cy + 8, OUTER_R, 0, 2 * Math.PI);
        cr.setSourceRGBA(...PALETTE.shadow);
        cr.fill();

        const baseGradient = new Cairo.RadialGradient(cx - 46, cy - 56, 18, cx, cy, OUTER_R);
        baseGradient.addColorStopRGBA(0, 0.29, 0.3, 0.35, 1);
        baseGradient.addColorStopRGBA(1, ...PALETTE.ink);
        cr.arc(cx, cy, OUTER_R, 0, 2 * Math.PI);
        cr.setSource(baseGradient);
        cr.fill();

        cr.arc(cx, cy, RING_OUTER, 0, 2 * Math.PI);
        cr.setLineWidth(1.2);
        cr.setSourceRGBA(...PALETTE.ringEdge);
        cr.stroke();

        cr.setLineWidth(1.1);
        cr.setLineCap(Cairo.LineCap.ROUND);
        for (let i = 0; i < TICK_COUNT; i++) {
            const angle = i / TICK_COUNT * 2 * Math.PI - Math.PI / 2;
            const longTick = i % 7 === 0;
            const outer = RING_OUTER + (longTick ? 8 : 4);
            const inner = RING_OUTER - (longTick ? 6 : 2);
            cr.moveTo(cx + Math.cos(angle) * inner, cy + Math.sin(angle) * inner);
            cr.lineTo(cx + Math.cos(angle) * outer, cy + Math.sin(angle) * outer);
        }
        cr.setSourceRGBA(...PALETTE.muted);
        cr.stroke();
        cr.restore();
    }

    _drawSegments(cr, cx, cy) {
        const { titles, count } = this._segmentState();
        const slice = (2 * Math.PI) / count;
        const activeTitle = this._state.title === 'Menu' ? '' : this._state.title;

        for (let index = 0; index < count; index++) {
            const label = titles[index] || '';
            const start = index * slice - Math.PI / 2 + 0.025;
            const end = (index + 1) * slice - Math.PI / 2 - 0.025;
            const active = Boolean(label) && label === activeTitle;
            const color = this._segmentColor(index);
            cr.save();
            cr.moveTo(cx + Math.cos(start) * RING_INNER, cy + Math.sin(start) * RING_INNER);
            cr.arc(cx, cy, RING_OUTER - 4, start, end);
            cr.arcNegative(cx, cy, RING_INNER, end, start);
            cr.closePath();
            const fill = active ? mix(color, PALETTE.segment, 0.38) : label ? PALETTE.segment : PALETTE.segmentDim;
            cr.setSourceRGBA(...fill);
            cr.fill();
            cr.restore();

            // A thin colour key on the inner edge identifies each function,
            // like the coloured buttons of the ASUS Control Panel.
            if (label) {
                cr.save();
                cr.setLineWidth(active ? 5 : 3);
                cr.setSourceRGBA(color[0], color[1], color[2], active ? 1 : 0.7);
                cr.arc(cx, cy, RING_INNER + 3, start + 0.04, end - 0.04);
                cr.stroke();
                cr.restore();
            }
        }
    }

    _drawFunctionRing(cr, cx, cy) {
        const radius = (RING_OUTER + RING_INNER) / 2 - 2;
        const width = RING_OUTER - RING_INNER - 18;
        const color = this._functionColor();
        cr.save();
        cr.setLineCap(Cairo.LineCap.ROUND);
        cr.setLineWidth(width);
        cr.setSourceRGBA(...PALETTE.track);
        cr.arc(cx, cy, radius, 0, 2 * Math.PI);
        cr.stroke();

        // Percentage functions (volume, brightness…) show a level gauge.
        const value = this._numericValue();
        if (!this._state.valueShowOnlyProgress && this._state.unit === '%' && value !== null) {
            const fraction = Math.max(0, Math.min(1, value / 100));
            if (fraction > 0.004) {
                const start = -Math.PI / 2;
                cr.setSourceRGBA(color[0], color[1], color[2], 0.92);
                cr.arc(cx, cy, radius, start, start + fraction * 2 * Math.PI);
                cr.stroke();
            }
        } else {
            // Endless functions get a subtle coloured groove instead.
            cr.setLineWidth(2);
            cr.setSourceRGBA(color[0], color[1], color[2], 0.45);
            cr.arc(cx, cy, radius + width / 2 - 1, 0, 2 * Math.PI);
            cr.stroke();
        }
        cr.restore();
    }

    _drawProgress(cr, cx, cy) {
        if (!this._state.valueShowOnlyProgress)
            return;
        const fraction = Math.max(-1, Math.min(1, this._state.value / 100));
        if (Math.abs(fraction) < 0.01)
            return;
        // The driver measures degrees clockwise from the top of the pad.
        const start = this._state.valueAngleStart * Math.PI / 180 - Math.PI / 2;
        const end = start + fraction * 2 * Math.PI;
        const radius = (RING_OUTER + RING_INNER) / 2 - 2;
        cr.save();
        cr.setLineCap(Cairo.LineCap.ROUND);
        cr.setLineWidth(RING_OUTER - RING_INNER - 18);
        cr.setSourceRGBA(...this._functionColor());
        if (fraction > 0)
            cr.arc(cx, cy, radius, start, end);
        else
            cr.arcNegative(cx, cy, radius, start, end);
        cr.stroke();
        cr.restore();
    }

    _drawPointer(cr, cx, cy) {
        const pointer = Number(this._details.pointer);
        if (!this._appearance.show_pointer || !this._state.touching || !(pointer >= 0))
            return;
        const angle = pointer * Math.PI / 180 - Math.PI / 2;
        const radius = RING_OUTER + 2;
        const x = cx + Math.cos(angle) * radius;
        const y = cy + Math.sin(angle) * radius;
        const color = this._isSelectedMode() ? this._functionColor() : PALETTE.paper;
        cr.save();
        cr.arc(x, y, 9, 0, 2 * Math.PI);
        cr.setSourceRGBA(color[0], color[1], color[2], 0.28);
        cr.fill();
        cr.arc(x, y, 5, 0, 2 * Math.PI);
        cr.setSourceRGBA(...color);
        cr.fill();
        cr.restore();
    }

    _drawCenter(cr, cx, cy) {
        const selectedMode = this._isSelectedMode();
        cr.save();
        cr.arc(cx + 3, cy + 5, CENTER_R + 2, 0, 2 * Math.PI);
        cr.setSourceRGBA(...PALETTE.shadow);
        cr.fill();

        const centerGradient = new Cairo.RadialGradient(cx - 26, cy - 34, 8, cx, cy, CENTER_R);
        centerGradient.addColorStopRGBA(0, 0.3, 0.31, 0.36, 1);
        centerGradient.addColorStopRGBA(1, 0.16, 0.165, 0.19, 1);
        cr.arc(cx, cy, CENTER_R, 0, 2 * Math.PI);
        cr.setSource(centerGradient);
        cr.fill();

        const accent = selectedMode ? this._functionColor() : this._accent;
        cr.arc(cx, cy, CENTER_R, 0, 2 * Math.PI);
        cr.setLineWidth(this._state.centerPressed ? 3 : 1.5);
        cr.setSourceRGBA(...(this._state.centerPressed ? accent : PALETTE.ringEdge));
        cr.stroke();

        const title = this._state.title;
        const profile = (this._details.profile || '').toUpperCase();
        if (selectedMode) {
            this._drawCenteredText(cr, title, cx, cy + 4, title.length > 12 ? 15 : 19, PALETTE.paper, true);
            const value = !this._state.valueShowOnlyProgress && this._state.unit
                ? `${this._state.value}${this._state.unit}`
                : '';
            if (value)
                this._drawCenteredText(cr, value, cx, cy + 30, 16, accent, true);
            else if (profile)
                this._drawCenteredText(cr, profile, cx, cy + 30, 9, PALETTE.muted, false);
        } else if (title && title !== 'Menu') {
            this._drawCenteredText(cr, title, cx, cy + 15, title.length > 12 ? 14 : 18, PALETTE.paper, true);
            this._drawCenteredText(cr, 'Release to select', cx, cy + 39, 9, PALETTE.champagne, false);
        } else {
            this._drawCenteredText(cr, profile || 'ASUS DIAL', cx, cy - 9, profile.length > 12 ? 12 : 16, PALETTE.paper, true);
            this._drawCenteredText(cr, 'Choose a function', cx, cy + 17, 10, PALETTE.champagne, false);
            this._drawCenteredText(cr, 'Touch a segment', cx, cy + 38, 9, PALETTE.muted, false);
        }
        cr.restore();
    }

    _drawHints(cr, cx, cy) {
        if (!this._appearance.show_hints || !this._isSelectedMode())
            return;
        const hints = this._details.hints || {};
        const multi = this._details.mode !== 'single';
        const ccw = truncate(hints.ccw, 20);
        const cw = truncate(hints.cw, 20);
        let center = '';
        if (hints.center) {
            const action = truncate(hints.center, 26);
            center = multi ? `Tap: ${action}  ·  Hold: menu` : `Tap: ${action}`;
        }
        else if (multi)
            center = 'Tap centre: menu';
        if (!ccw && !cw && !center)
            return;

        const width = 300;
        const height = center ? 40 : 24;
        const top = cy - HINT_H / 2 + 2;
        cr.save();
        this._roundedRect(cr, cx - width / 2, top, width, height, 11);
        cr.setSourceRGBA(0.1, 0.105, 0.12, 0.88);
        cr.fill();
        const arrowColor = this._functionColor();
        if (ccw) {
            this._drawTurnArrow(cr, cx - width / 2 + 18, top + 12, false, arrowColor);
            this._drawAlignedText(cr, ccw, cx - width / 2 + 30, top + 12, 11, PALETTE.paper, 'left');
        }
        if (cw) {
            this._drawTurnArrow(cr, cx + width / 2 - 18, top + 12, true, arrowColor);
            this._drawAlignedText(cr, cw, cx + width / 2 - 30, top + 12, 11, PALETTE.paper, 'right');
        }
        if (center)
            this._drawCenteredText(cr, center, cx, top + 29, 9, PALETTE.muted, false);
        cr.restore();
    }

    _drawTurnArrow(cr, x, y, clockwise, color) {
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

    _roundedRect(cr, x, y, width, height, radius) {
        cr.newSubPath();
        cr.arc(x + width - radius, y + radius, radius, -Math.PI / 2, 0);
        cr.arc(x + width - radius, y + height - radius, radius, 0, Math.PI / 2);
        cr.arc(x + radius, y + height - radius, radius, Math.PI / 2, Math.PI);
        cr.arc(x + radius, y + radius, radius, Math.PI, 1.5 * Math.PI);
        cr.closePath();
    }

    _setFont(cr, size, bold) {
        cr.setFontSize(size);
        cr.selectFontFace('Sans', Cairo.FontSlant.NORMAL, bold ? Cairo.FontWeight.BOLD : Cairo.FontWeight.NORMAL);
    }

    _drawCenteredText(cr, text, x, y, size, color, bold) {
        cr.save();
        cr.setSourceRGBA(...color);
        this._setFont(cr, size, bold);
        const extents = cr.textExtents(text);
        cr.moveTo(x - extents.width / 2 - extents.xBearing, y + extents.height / 2);
        cr.showText(text);
        cr.restore();
    }

    _drawAlignedText(cr, text, x, y, size, color, align) {
        cr.save();
        cr.setSourceRGBA(...color);
        this._setFont(cr, size, false);
        const extents = cr.textExtents(text);
        const left = align === 'right' ? x - extents.width - extents.xBearing : x - extents.xBearing;
        cr.moveTo(left, y + extents.height / 2);
        cr.showText(text);
        cr.restore();
    }
}
