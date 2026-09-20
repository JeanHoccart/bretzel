# Chat — server → browser streaming, and what it costs

```bash
py -m examples.chat.main
```

Text that fills in progressively is the case that **forces a choice**
between the two ways Bretzel has of changing the DOM. This example puts
them side by side on a single page.

## The two halves, and why they do not overlap

| what changes | mechanism | in this example |
|---|---|---|
| **Structure** — a node appears | `@refreshable` → re-render + morph | the message log (`message_log`) |
| **Value** — an already-bound node changes | `ClientState` → patch → signal | the bubble in progress (`streaming_bubble`) |

These are not two solutions to the same problem. One message **more** is
structure: only a server re-render can make it appear. The **text** of
that message growing is a value: the server reassigns a field, it comes
back down in a JSON patch, and the browser writes into a text node — no
HTML parsed, no morphing.

## Two states, two directions

This split carries everything else:

```python
class Draft(ClientState, send_to_server=False):   # server → client
    answer: str = ""          # the text shown while generating
    streaming: bool = False   # the ui.interval's gate

class Prompt(ClientState):                        # client → server
    text: str = ""            # what the user types
```

`Draft` **never** travels back up: without that setting, the text being
written would go back to the server on every tick, for data the client
has only just received. The corollary is surprising and reads in
`logic.py`: `Draft().answer` is `""` inside a handler, so we **reassign**
`full[:cursor]` instead of accumulating with `+=`.

`Prompt` does travel up, because its value is born in the browser. The
base layer refuses, incidentally, to bind a two-way prop
(`ui.input(value=…)`) to a downward-only state — the mistake is caught at
construction, not discovered in production.

## The cadence is pulled by the client, and that is the point

```python
ui.interval(on_tick=pull_chunk, seconds=0.12, active=Draft().streaming)
```

`active=` is a `ClientBinding`: the server flips it to `False` and the
timer stops **at the same instant**. That is what makes the *Stop* button
honest.

A server loop (`@app.background`) could not do it: it has no request
context, hence no way to re-read the state that would tell it to stop. It
would carry on producing requests after the click. It is written in
`.claude/bretzel/handlers.md` § *background*, and the playground's
stepper walked that road in reverse for the same reason.

## What it costs — measured, then modelled

Every tick resends the **whole** slice, not the delta. The total sent
down therefore follows:

```
total = n · (k + 1) / 2        n = final size, k = number of slices
```

A model **validated against the browser**: at `n = 337` and `k = 57`, it
predicts 9 773 bytes and `tests/runtime_js/test_chat_example_streams.py`
measures 9 754 — a 0.2 % gap. An out-of-browser simulation of the same
loop lands on the exact figure.

What matters is that **`k` is an application choice**, not a framework
limit. It divides the cost AND the number of requests, linearly.
Extrapolated to a 2 000-token answer (~8 KB):

| words / slice | requests | sent down |
|---:|---:|---:|
| 1 | 400 | 1 566 KB |
| 3 *(the default here)* | 133 | 525 KB |
| 5 | 80 | 316 KB |
| 20 | 20 | **82 KB** |
| 50 | 8 | 35 KB |

**The conclusion, and it is a negative one**: at a reasonable slice size,
the current transport is enough. 20 requests and 82 KB for a complete
answer do not justify making the SSE channel carry an append patch, nor
inventing one more mechanism. The spectacular cost of the first reading
came from a setting of the example, not from the framework.

The work would become justified again under **one precise condition**:
wanting the word-by-word "typewriter" effect AND a long answer — that is,
a large `k` demanded by UX. But even there, the right answer is probably
to decouple the transport cadence from the display cadence (fetch in
blocks, reveal progressively on the client) rather than to add a channel.

The page's measurement panel shows all of this live, without dressing it
up: an example that hides the cost of what it demonstrates teaches
nothing.

## The generator is simulated

No LLM call, no API key. The subject is the **transport**; wiring a real
model would change only `features/generator.py` § `answer_for`, and would
say nothing more about what this example demonstrates.

## A detail that is not one

While generating, the bubble shows **raw text**; on commit, the message
goes through `ui.markdown`. `ui.markdown` refuses a `ClientBinding` at the
constructor — a binding path would flatten the whole structure (headings,
lists, code) into plain text and lie in silence. Most chat UIs do the
same, for a neighbouring reason: half-written markdown is not valid
markdown.
