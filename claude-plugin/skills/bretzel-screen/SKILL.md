---
name: bretzel-screen
description: Use when the user asks for a new screen, page, view, form, dashboard or feature UI in a Bretzel app, or wants to see what an app or screen would look like before it is built ("make me a mockup", "show me the screen first", "design the page for X"), and when they approve a mockup ("build it", "wire it"). Builds a real Bretzel mockup on invented data, gets it validated from screenshots, then turns that same code into the working screen.
---

# A new screen: mockup, validation, then the code

In Bretzel a mockup is not a drawing: it is a throwaway Bretzel page on
invented data, made of the very components, theme and layout the app will
ship. What the user validates is what they get — nothing is redrawn when it
is wired. Do ONE screen at a time, and never chain to the next screen without
the user's validation.

## 1. Understand the screen

What it is for, who opens it, what it shows, what can be done from it. Infer
what you can from the app (its features, its data); ask only what you
cannot, in one short message.

- **How the user works today, not what the category offers.** Ask which
  actions they really use in the tool this screen replaces. A mail screen
  for someone who only marks as read and archives has two actions, not the
  twenty of a full mail client.
- **One screen, one job.** If the request bundles several screens (a list,
  an agenda, a to-do, an assistant), say so and start with one. Agree on
  the app's shell first when there is none.
- **Nothing invented.** The first mockup holds what was asked and nothing
  else, as light as it can be. Features you think of go in the message as
  questions, not on the screen: adding later is cheap, removing what the
  user never wanted costs their trust.
- **Look at the references.** For each gesture the screen offers (picking
  recipients, a folder, a long list, a separator, a scrollbar), check how
  two or three established products do it, say which you follow, and
  recommend. A plain select where every real product has a token field is
  the kind of first draft that has to be redone.

## 2. Write the mockup

One file, `mockups/<screen>.py` (with an empty `mockups/__init__.py`), its
own app, no state, no database:

```python
"""Mockup — the ticket list. Invented data, no state, nothing saved."""

import sys

from bretzel import Bretzel, page, ui

TICKETS = [
    {"id": 1042, "title": "Invoice PDF is blank for orders over 100 lines", "status": "Open"},
    {"id": 1041, "title": "Login loops on Safari", "status": "In progress"},
    {"id": 1039, "title": "Export", "status": "Done"},
]
COLORS = {"Open": "warning", "In progress": "info", "Done": "success"}


def open_tickets() -> list[dict]:
    return TICKETS  # invented — wiring changes this line, not the page


def nothing() -> None:
    ui.notification("Mockup: nothing is saved.")


@page("/", title="Tickets — mockup")
def tickets() -> None:
    with ui.container(width="lg", classes="py-8"):
        with ui.vstack(gap="md"):
            ui.heading("Tickets", level=1)
            for ticket in open_tickets():
                with ui.card():
                    with ui.hstack(gap="sm", justify="between"):
                        ui.text(f"#{ticket['id']} {ticket['title']}")
                        ui.badge(ticket["status"], color=COLORS[ticket["status"]])
            ui.button("New ticket", on_click=nothing)


app = Bretzel(title="Mockup", secret_key="mockup-only-not-a-real-secret", mode="dev")
app.include(sys.modules[__name__])
```

- **Data that looks real**: plausible names and volumes, a long label, an
  empty case, a number that does not fit — the cases the real screen meets.
- **The app's real look**: if the app passes a `theme=` or a layout, the
  mockup uses the same. Reuse the app's components and helpers when they
  exist.
- **Data behind one function**: the page reads it through a function
  (`open_tickets()`), never the constant itself — wiring then changes that
  function alone.
- Handlers are module-level no-ops (a notification at most). The layout,
  the hierarchy and the words are what is being decided.
- **Components as they are.** Props (`variant=`, `size=`, `gap=`,
  `align=`) first, no `classes=` in a first draft. When the screen needs a
  component Bretzel does not have, or one that cannot do it without
  forcing classes, say so in the message — do not stand in with the
  nearest one (a select for recipients, a textarea for rich text).

## 3. Show it

```bash
bretzel check mockups/<screen>.py
bretzel probe mockups.<screen>:app --out mockups/shots/<screen>
```

The probe drives a real browser and writes `f1-light.png` and
`f1-dark.png`. Before the user sees anything, check it yourself:

- **Measure, do not eyeball.** In the browser, read the boxes
  (`getBoundingClientRect`): the gaps between repeated rows are equal, the
  space on each side of a separator or a scrollbar matches, edges that
  should line up do, sibling buttons share their radius and height.
- **Narrow it.** Load the page at the smallest width the user has, and
  again in between: nothing passes under another element, nothing comes
  out on the far side, a long label truncates instead of pushing.
- **Play the gestures.** A screenshot shows none of these: click each
  action and look at what remains (an archived item leaves the reading
  pane too), check the focus lands where typing starts (the reply box after
  "Reply"), double-click whatever creates or sends (it happens once), and
  try selecting the text the user will want to copy.

Then give the user the two screenshot paths, three lines on the choices
made, and ask for their validation or changes. When they ask a question
("should the scrollbar show?", "a card or not?"), answer it in that same
round with what the references do and your recommendation. Iterate in
rounds until they say yes. `bretzel dev mockups.<screen>:app` lets them
click through it themselves.

## 4. Wire it

Once validated — the user says "build it" — move the page into the app as
its own feature (see the `bretzel` skill, "Write in this shape"): the same
component tree; the data function now returns typed state or a real query,
and the no-op handlers become real ones — `@idempotent` on every handler
that creates, sends or pays.
Do not redesign while wiring; a change of design goes back to step 2.

## 5. Check it against the mockup

```bash
bretzel check <package>
bretzel probe <module>:app --route /<screen> --out shots/<screen>
```

Compare the new screenshots with the validated ones and report the
differences, if any. Then the mockup file can go (or stay in `mockups/` as
the record of what was agreed).
