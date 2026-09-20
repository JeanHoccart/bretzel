"""chat/generator — the token source, simulated.

**No LLM call.** This example demonstrates a TRANSPORT, not an
integration: wiring a real model would need an API key, would make the
demo depend on a network and a budget, and would not change by one byte
what we are trying to show — how a text growing on the server reaches the
browser. The day a real model is wired in, only :func:`answer_for`
changes; all the rest of the app is already correct.

Throughput **by words** rather than by characters: that is roughly what a
real tokenizer does, and it gives pieces of a realistic size (4-6 bytes),
hence a realistic number of ticks — which is what counts, since the
measurement is the point of this example.
"""

from __future__ import annotations

#: Canned answers, picked by a keyword of the prompt. A ``dict`` rather
#: than a cascade of ``if``: adding a case is one line.
_ANSWERS: dict[str, str] = {
    "bretzel": (
        "Bretzel renders the HTML on the server and leaves a small "
        "client runtime to apply the changes. State is typed, split "
        "across four server scopes and one client scope. Mutating a "
        "piece of state re-renders the subtrees that depend on it, "
        "without anyone having to ask. There is no Node dependency in "
        "production: the CSS is compiled by a binary, and the runtime is "
        "a single JavaScript file served as it is."
    ),
    "stream": (
        "The text you are reading arrives in slices. On every slice "
        "the server reassigns the whole value of a client-state field, "
        "which comes back down in a JSON patch. The browser then writes "
        "straight into a text node: no HTML parsed, no tree morphing, a "
        "single assignment. That is why it does not flicker."
    ),
}

_DEFAULT = (
    "There is no model behind me — I am a simulated generator, and "
    "that is on purpose. This example shows how a text produced bit by "
    "bit on the server reaches your screen, not how one calls an API. "
    "Try the words “bretzel” or “stream” for a "
    "longer answer."
)


def answer_for(prompt: str) -> str:
    """The full answer to stream for ``prompt``.

    The ONLY spot to replace with a real model call.
    """
    lowered = prompt.lower()
    for keyword, answer in _ANSWERS.items():
        if keyword in lowered:
            return answer
    return _DEFAULT


#: Words published per slice. **The most important setting in this
#: example**, and it is an APPLICATION choice, not a framework limit.
#:
#: The total sent down follows ``n · (k+1) / 2`` — ``n`` the final size,
#: ``k`` the number of slices. Model verified: at ``n=337`` and ``k=57`` it
#: predicts 9 773 bytes, the measurement gives 9 754 (0.2 % off).
#:
#: So ``k`` divides the cost AND the number of requests, **linearly**.
#: Extrapolated to a 2 000-token answer (~8 000 bytes):
#:
#: ===============  ==========  ===========
#: words / slice      requests    sent down
#: ===============  ==========  ===========
#: 1                       400     1 566 kB
#: 5                        80       316 kB
#: 20                       20        82 kB
#: 50                        8        35 kB
#: ===============  ==========  ===========
#:
#: **3 and not 1**, although 1 makes the phenomenon more spectacular: an
#: example serves as a pattern as much as a demonstration, and shipping
#: the worst case by default would teach the wrong reflex. 1 stays one
#: character away for whoever wants to watch the curve run away.
#:
#: ⚠️ The trade-off is REAL and it is a matter of taste, not of technique:
#: bigger slices arrive in visible jolts where one word at a time gives
#: the "typewriter" effect. If that effect matters, the way out is not to
#: lower this number — it is to separate the TRANSPORT cadence from the
#: DISPLAY one: fetch 20 words at once and reveal them progressively on
#: the client. Several real chat UIs do exactly that, and it asks nothing
#: of the server.
CHUNK_WORDS = 3


def advance(full: str, cursor: int, words: int = CHUNK_WORDS) -> int:
    """The cursor after ``words`` more word(s), bounded to ``len(full)``.

    A pure function: it knows neither the state nor the request, so it
    tests without mounting anything. The cursor is a position in the
    string (and not a word index) so that the published slice is a plain
    ``full[:cursor]``.
    """
    for _ in range(max(1, words)):
        if cursor >= len(full):
            return len(full)
        # Skip the space if any, then the word, and stop AFTER it: the
        # published slice always ends on a whole word.
        nxt = full.find(" ", cursor + 1)
        if nxt == -1:
            return len(full)
        cursor = nxt
    return cursor
