"""When the on-screen dial shows, fades and hides, without any toolkit.

A line-by-line twin of the visibility part of gnome/extension/extension.js
(_updateVisibility, _show, _hide, _scheduleFade, _scheduleHide), so every
frontend times the dial like the Shell does: it shows while the finger
touches, flashes after activation, lingers hide_delay_ms after release and,
with visibility "fade", dims after FADE_AFTER_MS of touching.

The frontend supplies two actors (the dial and the pill) and a timer; the
tests use fake ones.
"""

from __future__ import annotations

from typing import Callable, Protocol

from overlay.look import (
    FADE_AFTER_MS,
    FADE_IN_MS,
    FADE_OUT_MS,
    FADE_SLOW_MS,
    ease_in_out_quad,
    ease_in_quad,
    ease_out_quad,
    js_round,
)


class Actor(Protocol):
    """Something that fades: a Clutter actor in the Shell, a window here."""

    visible: bool
    opacity: int  # 0–255 like Clutter

    def ease(self, opacity: int, duration: int, easing: Callable[[float], float],
             on_complete: Callable[[], None] | None = None) -> None: ...

    def remove_all_transitions(self) -> None: ...


class Timers(Protocol):
    def add(self, milliseconds: int, callback: Callable[[], None]) -> object: ...

    def remove(self, handle: object) -> None: ...


class Visibility:
    """dial and pill: Actors. look(): the effective look (overlay.look),
    state(): the driver state, hide_delay(): hide_delay_ms."""

    def __init__(self, dial: Actor, pill: Actor, timers: Timers,
                 look: Callable[[], dict], state: Callable[[], dict], hide_delay: Callable[[], int]):
        self._dial = dial
        self._pill = pill
        self._timers = timers
        self._look = look
        self._state = state
        self._hide_delay = hide_delay
        self._hide_timeout = None
        self._fade_timeout = None
        self.shown = False
        self.shown_actor: Actor | None = None

    def update(self, was_enabled: bool, was_touching: bool) -> None:
        """After every OverlayState signal (_updateVisibility)."""
        state = self._state()
        if not state["enabled"]:
            self.hide()
            return
        if state["touching"]:
            self._cancel_hide()
            self.show(not was_touching)
            return
        self._cancel_fade()
        # Not touching: flash the dial after activation, and let an already
        # visible dial linger so the final value can be read.
        if not was_enabled or self.shown:
            self.show(False)
            self._schedule_hide()

    def look_changed(self) -> None:
        """Another profile or function may show the pill instead of the
        dial, or the other way round."""
        if self.shown:
            self.show(False)

    def active_actor(self) -> Actor:
        """The dial, or the pill in its place."""
        return self._pill if self._look()["visibility"] == "pill" else self._dial

    def show(self, touch_started: bool) -> None:
        """touch_started: a new touch brings a faded dial back to full."""
        actor = self.active_actor()
        if self.shown_actor is not None and self.shown_actor is not actor:
            self.shown_actor.remove_all_transitions()
            self.shown_actor.opacity = 0
            self.shown_actor.visible = False
        was_shown = self.shown and self.shown_actor is actor
        self.shown = True
        self.shown_actor = actor
        if was_shown and not touch_started:
            return
        actor.remove_all_transitions()
        actor.visible = True
        actor.ease(255, FADE_IN_MS, ease_out_quad)
        self._schedule_fade()

    def hide(self) -> None:
        self._cancel_hide()
        self._cancel_fade()
        actor = self.shown_actor
        if not self.shown or actor is None:
            return
        self.shown = False
        actor.remove_all_transitions()

        def done():
            if not self.shown or self.shown_actor is not actor:
                actor.visible = False

        actor.ease(0, FADE_OUT_MS, ease_in_quad, done)

    def cancel(self) -> None:
        """Stop the timers, when the frontend quits."""
        self._cancel_hide()
        self._cancel_fade()

    # Visibility "fade": after a moment of touching, fade so what lies
    # underneath shows through.
    def _schedule_fade(self) -> None:
        self._cancel_fade()
        look = self._look()
        if look["visibility"] != "fade":
            return

        def fade():
            self._fade_timeout = None
            if self.shown and self._state()["touching"] and self.shown_actor is not None:
                self.shown_actor.ease(js_round(255 * look["fadeOpacity"]), FADE_SLOW_MS, ease_in_out_quad)

        self._fade_timeout = self._timers.add(FADE_AFTER_MS, fade)

    def _cancel_fade(self) -> None:
        if self._fade_timeout is not None:
            self._timers.remove(self._fade_timeout)
            self._fade_timeout = None

    def _schedule_hide(self) -> None:
        self._cancel_hide()

        def hide():
            self._hide_timeout = None
            self.hide()

        self._hide_timeout = self._timers.add(int(self._hide_delay()), hide)

    def _cancel_hide(self) -> None:
        if self._hide_timeout is not None:
            self._timers.remove(self._hide_timeout)
            self._hide_timeout = None
