---
name: bretzel
description: Use when writing or changing an app built with Bretzel, the server-driven Python web framework (`import bretzel`, `from bretzel import ui`, `@page`, `@refreshable`, `SessionState`, `bretzel dev`), or when the user wants a Python web app, internal tool or dashboard without writing JavaScript. Says where the exact API is read and how the app is checked before saying it works.
---

# Working on a Bretzel app

Bretzel apps are pure Python: the server owns typed state, `ui.*` components
describe the interface, and a region redraws when a state it read changes.
Do not guess the API from other frameworks (Streamlit, NiceGUI, Reflex): the
installed package describes itself, at the version the app runs.

## Read before writing

- `bretzel describe` — the index of every component and helper. Its header
  holds the rules a first draft gets wrong (handlers are module-level
  functions, never lambdas; universal kwargs).
- `bretzel describe ui.datatable refreshable SessionState` — the full cards
  you need, in ONE call.
- A recipe first, when one matches the request (an edit dialog, a list
  shared live, a password login, pages with a navbar, a JSON route,
  screens added to an existing FastAPI app): one complete app each, in
  Markdown, listed first in https://docs.bretzel-py.dev/llms.txt. Every
  component in real use, with its code: https://ui.bretzel-py.dev.

## Write in this shape

- State is a typed class: `PageState` (one tab), `SessionState`,
  `UserState`, `AppState` (everyone), `ClientState` (browser only). Mutate
  it in a handler; the regions that read it redraw, in every tab the scope
  allows. There is no refresh to call and no dependency to declare.
- Ask "does the server need to know to render?". No: a `ClientState`, no
  round trip. But branches hidden with `visible=` are still rendered and
  redrawn: what decides WHICH heavy content to render (the app shown, a
  panel open or closed, a heavy tab) is an addressable `PageState`
  (`field(url=...)`) or a `UserState` preference, and the page renders
  only what is seen. A `ClientState` stays right for light branches (a
  menu, a tooltip, two small cards).
- Server states live in memory and a restart forgets them (`bretzel dev`
  restarts on every save). To keep them, name a file:
  `Bretzel(state_url="sqlite:///state.db")` — derive the path from the
  app's own settings, next to its database, so a test on a copy does not
  write into the real preferences.
- Data that lives elsewhere (a database) is followed through a `Topic`
  (`from bretzel.state import Topic, reads, writes`): the function that
  queries it carries `@reads(topic)`, the ones that change it
  `@writes(topic)`.
- A title is `ui.heading(text, level=…)`, never a big `ui.text`: the
  heading is what a screen reader and `get_by_role("heading")` find.
- Use the components as they are: their props (`color=`, `size=`,
  `variant=`, `align=`, `gap=`) before any `classes=`, and no `classes=` at
  all in a first draft. Keep Bretzel's base style; give the app its colors
  through its theme. A component that only does the job with forced
  classes (`!`) is missing a prop: say so to the user rather than bend it.
- When Bretzel has no component for the job, say so before writing. Do not
  stand in with the nearest one (a select for a list of recipients, a
  textarea for formatted text): the stand-in is what gets redone.
- An app is `main.py` (the `Bretzel(...)` instance and `app.include(...)`)
  plus `features/`, from the first screen on: one package per screen or
  domain, its logic (state, queries, handlers) apart from its UI, and its
  contract — `Feature(name=..., kind=..., provides=..., uses=...)` in
  `feature.py`, where `uses` names the only features it may import
  (`bretzel describe Feature`). A feature file that passes a few hundred
  lines is two features.
- Every handler that creates, sends or pays carries `@idempotent`: a double
  click then acts once.

## Check before saying it works

1. `bretzel check <package>` — a plugin hook already runs it on each file
   you write, with Write or Edit or from the shell, and on what the
   session changed before you hand back; run it on the whole package at
   the end anyway, fix every finding in one pass, then once more.
2. `bretzel probe <module>:app --route /path --out shots` — a real browser:
   JavaScript errors, failed requests, overflow, keyboard, both themes, and
   screenshots. Look at the screenshots before reporting. Once per machine:
   `python -m pip install "bretzel[probe]"` then
   `python -m playwright install chromium`. Not installed is not a reason
   to skip it: install it, or say plainly the screen was not seen.
3. `bretzel features <module>:app` — each feature, what it imports and who
   uses it, and what to fix (`uses` that differ from the real imports). Run
   it after the first wired screen, not only at the end.
   `bretzel impact <module>:app <files>` — what a change touches, and which
   probes to run.

A green test is not a working screen: what is visual is judged on the
screenshot, and spacing is measured in the browser, not guessed from it.
What a screenshot cannot show — focus, a double click, what stays on
screen after an action — is tried. If something cannot be verified, say so
plainly.

To build a new screen, follow the `bretzel-screen` skill: mockup first.
