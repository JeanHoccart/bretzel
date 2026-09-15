"""Pomodoro timer feature.

The countdown lives in ``SessionState`` (server-authoritative). A
``ui.interval`` fires :func:`tick` once a second, but only while the
``Play`` client signal is on — Pause flips the signal and the interval
clears with zero round-trip. Each focus block auto-rolls into a break and
back, the classic 4-focus → long-break cadence.

This is the canonical pattern for a pausable client timer : the gate is a
``ClientState`` (instant), the work is a server handler (authoritative).
"""

from __future__ import annotations

from functools import partial

from bretzel import page, refreshable, ui
from bretzel.state import ClientState, SessionState, field
from examples.pomodoro.features.shell import shell

# ── Routing ──────────────────────────────────────────────────────────
PATH = "/"


# mode key → (label, seconds, color, icon)
MODES: dict[str, tuple[str, int, str, str]] = {
    "focus": ("Focus",       25 * 60, "primary", "target"),
    "short": ("Short break",  5 * 60, "success", "coffee"),
    "long":  ("Long break",  15 * 60, "info",    "moon"),
}


# ── State ────────────────────────────────────────────────────────────


class TimerState(SessionState):
    """Server-authoritative countdown : the ticker decrements ``remaining``."""

    mode: str = field(default='focus')
    remaining: int = field(default=25 * 60)
    completed: int = field(default=0)   # focus blocks finished this session


class Play(ClientState):
    """The run/pause gate — a CLIENT signal so flipping it stops the
    ``ui.interval`` instantly. Drives both the interval ``active=`` and the
    Start/Pause button visibility toggle."""

    active: bool = field(default=False)


# ── Logic (handlers) ─────────────────────────────────────────────────


def advance(s: TimerState) -> None:
    """Roll into the next block : focus → short (or long every 4th) → focus."""
    if s.mode == "focus":
        s.completed += 1
        nxt = "long" if s.completed % 4 == 0 else "short"
    else:
        nxt = "focus"
    s.mode = nxt
    s.remaining = MODES[nxt][1]
    ui.notification(
        f"{MODES[nxt][0]} time!",
        variant="success",
        title="Pomodoro",
        duration_ms=4000,
    )


def tick() -> None:
    """One second elapsed — fired by ``ui.interval`` while playing."""
    s = TimerState()
    if s.remaining > 0:
        s.remaining -= 1
    if s.remaining <= 0:
        advance(s)


def set_mode(mode: str) -> None:
    """Jump to a preset block and reset its countdown."""
    if mode not in MODES:
        return
    s = TimerState()
    s.mode = mode
    s.remaining = MODES[mode][1]


def reset_timer() -> None:
    s = TimerState()
    s.remaining = MODES[s.mode][1]


def skip() -> None:
    advance(TimerState())


# ── UI ───────────────────────────────────────────────────────────────


@refreshable(deps=[TimerState])
def timer_zone() -> None:
    """The clock face : mode badge, mm:ss, elapsed progress, session count.
    Refreshed by every tick so the countdown animates without a reload."""
    s = TimerState()
    label, duration, color, icon = MODES[s.mode]
    elapsed = duration - max(s.remaining, 0)
    minutes, seconds = divmod(max(s.remaining, 0), 60)

    with ui.vstack(gap="md", align="center", classes="w-full"):
        with ui.hstack(gap="xs", align="center"):
            ui.icon(icon, color=color)
            ui.badge(label, color=color, variant="soft")
        ui.text(
            f"{minutes:02d}:{seconds:02d}",
            size="6xl",
            weight="bold",
            classes="font-mono tabular-nums",
        )
        ui.progress(value=elapsed, max=duration, color=color, size="sm",
                    show_label=False, classes="w-full")
        plural = "" if s.completed == 1 else "s"
        ui.text(
            f"{s.completed} focus session{plural} completed",
            color="muted",
            size="sm",
        )


@page(PATH, layout=shell, title="Pomodoro")
def timer_page() -> None:
    play = Play()
    with ui.vstack(gap="lg", align="center", classes="w-full max-w-sm mx-auto"):
        ui.heading("Pomodoro", level=1, size="lg")

        # Client timer : ``tick`` fires every second WHILE ``play.active`` ;
        # flip the signal false (Pause) and it clears instantly.
        ui.interval(on_tick=tick, seconds=1, active=play.active)

        with ui.card(padding="lg", classes="w-full"):
            with ui.vstack(gap="lg", align="center"):
                # Mode presets — picking one resets the block and pauses.
                with ui.hstack(gap="sm", justify="center", wrap=True):
                    for key, (mlabel, _secs, mcolor, _icon) in MODES.items():
                        ui.button(
                            mlabel, variant="ghost", size="sm", color=mcolor,
                            on_click=[partial(set_mode, key), play.active.set(False)],
                        )

                timer_zone()

                # Transport controls. Start / Pause swap on the ``play``
                # signal via the universal ``visible=`` modifier (``~`` is
                # the client-side negation of a binding).
                with ui.hstack(gap="sm", align="center", justify="center"):
                    ui.icon_button(
                        "rotate-ccw", variant="ghost",
                        on_click=[reset_timer, play.active.set(False)],
                        tooltip="Reset block",
                    )
                    ui.button(
                        "Start", icon_left="play", color="success",
                        on_click=play.active.set(True), visible=~play.active,
                    )
                    ui.button(
                        "Pause", icon_left="pause", color="warning",
                        on_click=play.active.set(False), visible=play.active,
                    )
                    ui.icon_button(
                        "skip-forward", variant="ghost",
                        on_click=skip, tooltip="Skip to next block",
                    )
