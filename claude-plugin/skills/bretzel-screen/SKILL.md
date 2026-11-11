---
name: bretzel-screen
description: Use when the user asks for a new screen, page, view, form, dashboard or feature UI in a Bretzel app, or wants to see what an app or screen would look like before it is built ("make me a mockup", "show me the screen first", "design the page for X"). Builds a real Bretzel mockup on invented data, gets it validated from screenshots, then turns that same code into the working screen.
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


def nothing() -> None:
    ui.notification("Mockup: nothing is saved.")


@page("/", title="Tickets — mockup")
def tickets() -> None:
    with ui.container(width="lg", classes="py-8"):
        with ui.vstack(gap="md"):
            ui.heading("Tickets", level=1)
            for ticket in TICKETS:
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
- Handlers are module-level no-ops (a notification at most). The layout,
  the hierarchy and the words are what is being decided.

## 3. Show it

```bash
bretzel check mockups/<screen>.py
bretzel probe mockups.<screen>:app --out mockups/shots/<screen>
```

The probe drives a real browser and writes `f1-light.png` and
`f1-dark.png`. Open both yourself first; fix what is obviously wrong. Then
give the user the two screenshot paths, three lines on the choices made, and
ask for their validation or changes. Iterate in rounds until they say yes.
`bretzel dev mockups.<screen>:app` lets them click through it themselves.

## 4. Wire it

Once validated, move the page into the app (`features/<screen>.py`,
included in `main.py`): the same component tree, the invented constants
replaced by typed state and real queries, the no-op handlers by real ones.
Do not redesign while wiring; a change of design goes back to step 2.

## 5. Check it against the mockup

```bash
bretzel check <package>
bretzel probe <module>:app --route /<screen> --out shots/<screen>
```

Compare the new screenshots with the validated ones and report the
differences, if any. Then the mockup file can go (or stay in `mockups/` as
the record of what was agreed).
