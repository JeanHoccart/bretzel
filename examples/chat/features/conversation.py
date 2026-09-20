"""chat/conversation — the page, and the boundary it makes visible.

Three blocks, and each one illustrates a DIFFERENT mechanism. That is the
point of the example, not a layout effect:

1. **The log** (:func:`message_log`) — a ``@refreshable`` zone, because
   one more message is a change of **structure**: a node appears. Only a
   server re-render can do that. ``broadcast=[Log]`` because the
   conversation is a property of the session, not of a tab — opening the
   page twice shows both in the same place.

2. **The bubble in progress** — not a zone at all. A ``<span>`` bound to a
   ``ClientState`` field: when the server reassigns ``Draft().answer``,
   the value comes back down in a JSON patch and the browser writes into
   a text node. No HTML parsed, no morphing. It is a change of **value**,
   not of structure.

3. **The measurement panel** — bound values as well, so free: were it a
   refreshable zone, it would add HTML to every one of the responses it
   claims to be counting.

⚠️ The bubble in progress shows **raw text**, whereas committed messages
go through ``ui.markdown``. That is not an oversight: ``ui.markdown``
refuses a ``ClientBinding`` in its constructor, because a binding path
would flatten the whole structure (headings, lists, code blocks) to plain
text and lie about it in silence. During generation we therefore show the
raw text; on commit, the markdown is rendered by the server. It is also
what most chat UIs do, for a neighbouring reason: half-written markdown is
not valid markdown.
"""

from __future__ import annotations

from bretzel import Screen, page, refreshable, ui
from examples.chat.features.logic import pull_chunk, reset, send, stop
from examples.chat.features.shell import shell
from examples.chat.features.state import Draft, Log, Prompt

#: A bubble's box. Without ``w-fit``, "test" takes up the 42 rem of the
#: ``max-w`` and the conversation looks like a wall: ``max-w`` BOUNDS, it
#: does not size.
#:
#: This ``w-fit`` needed a ``!w-fit`` for a few hours — ``ui.card``'s theme
#: bakes ``w-full``, and the order inside the ``class`` attribute decides
#: nothing against Tailwind. It is fixed in the base layer: a width passed
#: in ``classes=`` now removes the theme's own (``_append_attr``,
#: ``components/base/component.py``). The ``!`` is no longer needed, and
#: its disappearance here is the witness of that fix.
BUBBLE = "w-fit max-w-[85%] md:max-w-[42rem]"


@refreshable(deps=[Log], broadcast=[Log])
def message_log() -> None:
    """The committed messages — a STRUCTURE, so a zone."""
    messages = Log().messages
    with ui.vstack(gap="md"):
        if not messages:
            ui.empty_state(
                "Ask a question to watch the text arrive in slices.",
                icon="message-circle",
            )
        for message in messages:
            user = message["role"] == "user"
            with ui.flex(justify="end" if user else "start"):
                with ui.card(
                    color="primary" if user else "surface",
                    padding="md",
                    classes=BUBBLE,
                ):
                    ui.markdown(message["text"])


def streaming_bubble() -> None:
    """The answer in progress — a VALUE, so not a zone.

    ``visible=`` takes a ``ClientBinding``: the bubble shows and hides on
    the client side, with no round trip. And a bound ``ui.text`` emits a
    ``bz-text``, so each slice is a plain ``textContent`` write.
    """
    with ui.flex(justify="start", visible=Draft().streaming):
        with ui.card(color="surface", padding="md", classes=BUBBLE):
            with ui.hstack(gap="sm", align="start"):
                # ``shrink-0``: a flex child is compressible by
                # default, so the spinner squashed into an ellipse as the
                # text grew — it visibly thinned out during generation.
                ui.spinner(size="sm", color="primary", classes="shrink-0")
                ui.text(
                    Draft().answer,
                    id="bz-stream-answer",
                    classes="whitespace-pre-wrap",
                )


def measurement_panel() -> None:
    """What the transport really cost — bound values.

    The figure that matters is ``bytes down``: every tick resends the
    WHOLE slice, not the delta, so the total grows as the square of the
    answer's length. That is the property we want in plain sight, because
    it is the one that will decide whether the SSE channel must one day
    carry an append patch.
    """
    with ui.card(color="surface", padding="sm"):
        with ui.hstack(gap="lg", align="center", wrap=True):
            ui.text("Transport measured", size="xs", weight="medium",
                    color="muted")
            with ui.hstack(gap="xs"):
                ui.text("requests:", size="xs", color="muted")
                ui.text(Draft().ticks, size="xs", weight="medium")
            with ui.hstack(gap="xs"):
                ui.text("bytes down:", size="xs", color="muted")
                ui.text(Draft().bytes_down, size="xs", weight="medium")
            # The explanation is dropped on mobile: at 375 px it wraps
            # and pushes the figures out of view, so it costs exactly what
            # it exists to show.
            if not Screen().is_mobile:
                ui.text(
                    "every tick resends the whole slice — the total grows in "
                    "O(n²)",
                    size="xs",
                    color="muted",
                    italic=True,
                )


def composer() -> None:
    """The input. ``Prompt`` travels up, unlike ``Draft``.

    ``Screen().is_mobile`` is a plain ``bool`` resolved at render time
    from a viewport cookie — so an ordinary Python ``if``, not a reactive
    zone nor a media query. On a narrow screen the labels give way to
    icons: two text buttons plus a field do not fit on a 375 px row.
    """
    mobile = Screen().is_mobile
    with ui.hstack(gap="sm", align="center"):
        ui.input(
            value=Prompt().text,
            placeholder=("Try “bretzel”…" if mobile
                         else "Try “bretzel” or “stream”…"),
            clearable=True,
            disabled=Draft().streaming,
            classes="flex-1 min-w-0",
        )
        if mobile:
            ui.icon_button(
                "send",
                color="primary",
                on_click=send,
                visible=~Draft().streaming,
                tooltip="Envoyer",
                id="bz-send",
            )
            ui.icon_button(
                "square",
                color="error",
                variant="soft",
                on_click=stop,
                visible=Draft().streaming,
                tooltip="Stop",
            )
        else:
            ui.button(
                "Envoyer",
                color="primary",
                icon_left="send",
                on_click=send,
                visible=~Draft().streaming,
                id="bz-send",
            )
            ui.button(
                "Stop",
                color="error",
                variant="soft",
                icon_left="square",
                on_click=stop,
                visible=Draft().streaming,
            )


@page("/", layout=shell)
def conversation() -> None:
    with ui.vstack(gap="lg", classes="flex-1 min-h-0"):
        # Header and composer: ``shrink-0``, otherwise flexbox squeezes
        # them to make room for the log instead of scrolling it.
        with ui.hstack(justify="between", align="center", classes="shrink-0"):
            ui.heading("Conversation", level=2, size="xl")
            ui.button(
                "Effacer",
                variant="ghost",
                color="muted",
                icon_left="trash-2",
                on_click=reset,
            )

        # ``ui.pane`` carries the ``min-h-0`` that makes the bar appear:
        # without it, a flex child's ``min-height:auto`` floor stops the
        # zone going below the height of its content, it grows with the
        # conversation, and ``overflow-y-auto`` never has anything to do.
        # Reproduced while writing this example, before the component
        # existed.
        with ui.pane(gap="md"):
            message_log()
            streaming_bubble()

        with ui.vstack(gap="sm", classes="shrink-0"):
            composer()
            measurement_panel()

    # The metronome. ``active=`` is a ``ClientBinding``: the server flips
    # it to False and the timer stops at the same instant, without waiting
    # for the next tick. That is what makes the Stop button honest — and
    # what a ``@background`` loop could not do, being context-free hence
    # unable to re-read the state that stops it.
    ui.interval(on_tick=pull_chunk, seconds=0.12, active=Draft().streaming)
