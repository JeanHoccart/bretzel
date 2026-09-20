"""chat/state — three states, and the boundary between them is the point.

The split is not cosmetic: it is what decides what travels on the wire,
and in which direction.

- :class:`Log` — ``SessionState``. The CONVERSATION: the committed
  messages. It is the source of truth, it lives on the server, and it
  changes **structure** (one more line). Only a re-render can show that,
  so it is a ``@refreshable`` zone.

- :class:`Gen` — ``SessionState``. The generation CURSOR. The server alone
  knows how far it is through the text to stream; the client has no reason
  to know it, and above all no authority over it.

- :class:`Draft` — ``ClientState``, **``send_to_server=False``**. What the
  user SEES during generation. The server writes it, the client displays
  it, and it never travels up: that is exactly the definition of a
  downward state. Without that setting, the text being written would go
  back to the server at every tick — that is, on a 2 000-token answer
  streamed in 100 pieces, hundreds of kilobytes of upload for data the
  client has only just received.

⚠️ The corollary, which surprises: ``Draft().answer`` read in a handler is
always ``""``. That is intended — the field does not travel up. So we
NEVER accumulate on the server with ``+=``: we **reassign** the whole
slice the cursor designates (``logic.pull_chunk``). The server stays the
author, the client stays a display.
"""

from __future__ import annotations

from bretzel.state import ClientState, SessionState, field


class Log(SessionState):
    """The committed messages. ``role`` is ``"user"`` or ``"bot"``."""

    messages: list[dict] = field(default_factory=list)


class Gen(SessionState):
    """How far the current generation is, server side only."""

    #: The full text the generator streams. Empty = nothing in flight.
    full: str = field(default='')
    #: How many characters of ``full`` have already been published.
    cursor: int = field(default=0)

    # ── Instrumentation ────────────────────────────────────────────────
    # This example's stated goal: produce the FIGURE that says whether the
    # current transport is enough, rather than a guess off the top of the
    # head.
    ticks: int = field(default=0)
    #: Sum of the sizes of the ``answer`` values published. Every tick
    #: resends the WHOLE slice, not the delta — hence a quadratic growth
    #: the page shows without dressing it up.
    bytes_down: int = field(default=0)


class Draft(ClientState, send_to_server=False):
    """Downward only: the server writes, the client displays.

    ``streaming`` gates the page's ``ui.interval``. It is a
    ``ClientBinding``, so flipping it from the server **stops the timer
    instantly**, without waiting for the next tick — that is what makes
    the *Stop* button honest. A ``@background`` loop could not do it: it
    has no context, hence cannot re-read the state that says "stop" (cf.
    ``handlers.md`` § *background*).
    """

    answer: str = field(default='')
    streaming: bool = field(default=False)

    # ── Display mirrors of Gen's counters ──────────────────────────────
    # Duplication on purpose, and the pattern is what matters: ``Gen``
    # carries the TRUTH (the server increments it), ``Draft`` carries the
    # DISPLAY. Without these mirrors, the measurement panel would be a
    # ``@refreshable`` zone re-rendering at every tick — so the instrument
    # would skew its own measurement by adding HTML to every one of the
    # answers it counts. Here it is only bound text: zero extra bytes.
    ticks: int = field(default=0)
    bytes_down: int = field(default=0)


class Prompt(ClientState):
    """What the user types. **Without** ``send_to_server=False``.

    It is :class:`Draft`'s counter-example, and it is worth reading beside
    it: this value is born in the browser, so it MUST travel up —
    otherwise the handler would not know what to answer. Declaring it
    downward-only would lose it in silence, and the base layer refuses
    anyway to bind a two-way prop (``ui.input(value=…)``) to a state that
    does not travel up.

    Two directions, two states: simpler than a compromise, and it reads.
    """

    text: str = field(default='')
