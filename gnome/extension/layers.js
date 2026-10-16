// Layered painting of the on-screen dial, kept out of extension.js.
//
// Why: painting the whole dial with Cairo takes about 6 ms per frame at
// 2x pixel density (GNOME renders fractional scaling such as 150 % at 2x),
// nearly all of it in the shadow and gradients, which never change while
// the dial is shown. The driver sends a signal every few degrees the finger
// moves, so repainting everything made the dial stutter, most on battery.
//
// How: three actors that the compositor (GPU) puts together, each painted
// only when its own look changes:
//
// 1. background: shadow, disc and rim. Painted when the skin, the scale or
//    the size changes.
// 2. content: menu or gauge, centre and hints. Painted when contentKey()
//    of the view changes (another value, function or menu); about 0.6 ms,
//    because the centre disc is copied from an image cached in dial.js.
// 3. pointer: the finger dot, painted once per colour. A moving finger only
//    moves this actor, which paints nothing.
//
// The look is the same as paintDial() in dial.js, which the README
// pictures still use.
import St from 'gi://St';
import Cairo from 'cairo';

import {
    POINTER_SIZE,
    contentKey,
    paintBackground,
    paintContent,
    paintPointer,
    pointerPlacement,
} from './dial.js';

export class DialLayers {
    // parent: the actor to add the layers to, at its top left corner.
    // getView: returns the current view (see dial.js).
    constructor(parent, getView) {
        this._getView = getView;
        this._cache = {};
        this._contentKey = null;
        this._pointerKey = null;
        this._pointerColor = null;

        this._background = this._addLayer(parent, cr => paintBackground(cr, this._getView()));
        this._content = this._addLayer(parent, cr => {
            const view = this._getView();
            if (view.state.enabled)
                paintContent(cr, view, this._cache);
        });
        this._pointer = this._addLayer(parent, cr => {
            if (this._pointerColor)
                paintPointer(cr, this._getView(), this._pointerColor);
        });
        this._pointer.visible = false;
    }

    _addLayer(parent, paint) {
        const area = new St.DrawingArea();
        area.connect('repaint', () => {
            const cr = area.get_context();
            cr.save();
            cr.setOperator(Cairo.Operator.CLEAR);
            cr.paint();
            cr.restore();
            paint(cr);
            // GJS does not free Cairo contexts promptly without this.
            cr.$dispose();
        });
        parent.add_child(area);
        return area;
    }

    setSize(width, height, scale) {
        this._background.set_size(width, height);
        this._content.set_size(width, height);
        const pointerSize = Math.ceil(POINTER_SIZE * scale);
        this._pointer.set_size(pointerSize, pointerSize);
        this.invalidate();
    }

    // After a skin, scale or size change: paint every layer again.
    invalidate() {
        this._contentKey = null;
        this._pointerKey = null;
        this._background.queue_repaint();
        this.update();
    }

    // Called for every signal of the driver, so it only compares and moves.
    update() {
        const view = this._getView();
        const key = contentKey(view);
        if (key !== this._contentKey) {
            this._contentKey = key;
            this._content.queue_repaint();
        }
        this._background.visible = view.state.enabled;
        this._updatePointer(view);
    }

    _updatePointer(view) {
        const placement = view.state.enabled ? pointerPlacement(view) : null;
        this._pointer.visible = Boolean(placement);
        if (!placement)
            return;
        const scale = view.appearance.scale;
        const half = POINTER_SIZE * scale / 2;
        this._pointer.set_position(placement.x * scale - half, placement.y * scale - half);
        const key = JSON.stringify([placement.color, view.skin.palette.pointer]);
        if (key !== this._pointerKey) {
            this._pointerKey = key;
            this._pointerColor = placement.color;
            this._pointer.queue_repaint();
        }
    }

    // The actors go with their parent; this frees the cached image.
    destroy() {
        this._cache.centerImage?.finish();
        this._cache = {};
    }
}
