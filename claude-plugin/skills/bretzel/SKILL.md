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
- Docs for the ideas: https://docs.bretzel-py.dev/llms.txt. Every component
  in real use, with its code: https://ui.bretzel-py.dev.

## Write in this shape

- State is a typed class: `PageState` (one tab), `SessionState`,
  `UserState`, `AppState` (everyone), `ClientState` (browser only). Mutate
  it in a handler; the regions that read it redraw, in every tab the scope
  allows. There is no refresh to call and no dependency to declare.
- Data that lives elsewhere (a database) is followed through a `Topic`
  (`from bretzel.state import Topic, reads, writes`): the function that
  queries it carries `@reads(topic)`, the ones that change it
  `@writes(topic)`.
- Use the components as they are: their props (`color=`, `size=`,
  `variant=`, `align=`) before any `classes=`. Keep Bretzel's base style;
  give the app its colors through its theme.
- An app is `main.py` (the `Bretzel(...)` instance and `app.include(...)`)
  plus `features/` (one module per screen or domain).

## Check before saying it works

1. `bretzel check <package>` — a plugin hook already runs it on each file
   you write with the Write or Edit tools (not on files written from a shell); run it on the whole package at the end, fix every finding in
   one pass, then once more.
2. `bretzel probe <module>:app --route /path --out shots` — a real browser:
   JavaScript errors, failed requests, overflow, keyboard, both themes, and
   screenshots. Look at the screenshots before reporting.
3. `bretzel features <module>:app` and `bretzel impact <module>:app <files>`
   — what a change touches, and which probes to run.

A green test is not a working screen: what is visual is judged on the
screenshot. If something cannot be verified, say so plainly.

To build a new screen, follow the `bretzel-screen` skill: mockup first.
