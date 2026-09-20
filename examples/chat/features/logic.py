"""chat/logic — the three actions: send, pull a piece, stop.

The heart of the demonstrator is :func:`pull_chunk`, and its shape is
worth reading before being copied.

**We reassign, we do not accumulate.** ``Draft`` is declared
``send_to_server=False``: its fields never travel up, so ``Draft().answer``
is ``""`` inside a handler. A ``+=`` would start from nothing at every
tick. The server therefore publishes the slice the cursor designates —
``full[:cursor]`` — and stays the sole author of the value.

**It is the client that keeps time.** ``ui.interval`` pulls a piece every
120 ms as long as ``Draft().streaming`` is true. Flipping that field from
the server cuts the timer instantly, which makes *Stop* honest. A server
loop (``@background``) would not know how to stop: it has no request
context, hence cannot re-read the state that would tell it — written in
so many words in ``handlers.md`` § *background*, and the playground's
stepper moved from that pattern to ``ui.interval`` for exactly this
reason.
"""

from __future__ import annotations

from examples.chat.features.generator import advance, answer_for
from examples.chat.features.state import Draft, Gen, Log, Prompt


def send() -> None:
    """Commit the user's message and arm the generation.

    The text comes from ``Prompt``, an ordinary ``ClientState`` — so it
    travels up with the POST and reads here as a plain Python value. That
    is the opposite direction from ``Draft``, and it is why they are two
    states and not one.
    """
    draft_prompt = Prompt()
    prompt = (draft_prompt.text or "").strip()
    if not prompt:
        return
    draft_prompt.text = ""  # vider le champ de saisie

    log = Log()
    # Reassignment and not ``.append()``: a list mutated in place does
    # not trigger change detection, so the zone would not re-render (cf.
    # traps.md § collection mutation).
    log.messages = [*log.messages, {"role": "user", "text": prompt}]

    gen = Gen()
    gen.full = answer_for(prompt)
    gen.cursor = 0
    gen.ticks = 0
    gen.bytes_down = 0

    draft = Draft()
    draft.answer = ""
    draft.streaming = True
    draft.ticks = 0
    draft.bytes_down = 0


def pull_chunk() -> None:
    """Publish one more word. Called by ``ui.interval``, client side."""
    gen = Gen()
    if not gen.full or gen.cursor >= len(gen.full):
        stop()
        return

    gen.cursor = advance(gen.full, gen.cursor)
    slice_ = gen.full[: gen.cursor]

    gen.ticks += 1
    # The WHOLE slice goes out again at every tick — that is the
    # property we want visible, not hidden. The total grows as O(n²) on
    # the answer's length, and the page shows it.
    gen.bytes_down += len(slice_.encode("utf-8"))

    draft = Draft()
    draft.answer = slice_
    draft.ticks = gen.ticks
    draft.bytes_down = gen.bytes_down

    if gen.cursor >= len(gen.full):
        stop()


def stop() -> None:
    """Stop the generation and pour what was produced into the log.

    Called by the *Stop* button as well as by the natural end of the text:
    in both cases what was written is kept, because an interrupted answer
    is still an answer — throwing it away would punish the user for having
    clicked.
    """
    gen = Gen()
    draft = Draft()

    produced = gen.full[: gen.cursor]
    if produced:
        log = Log()
        log.messages = [*log.messages, {"role": "bot", "text": produced}]

    gen.full = ""
    gen.cursor = 0
    draft.answer = ""
    draft.streaming = False
    # ``ticks`` / ``bytes_down`` are NOT reset here: the measurement only
    # becomes readable once the generation is over. Clearing them on
    # arrival would empty the panel the second it becomes useful.


def reset() -> None:
    """Clear the conversation — and there, yes, reset the counters."""
    Log().messages = []
    gen = Gen()
    gen.full = ""
    gen.cursor = 0
    gen.ticks = 0
    gen.bytes_down = 0
    draft = Draft()
    draft.answer = ""
    draft.streaming = False
    draft.ticks = 0
    draft.bytes_down = 0
    Prompt().text = ""
