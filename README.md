# Bretzel

<p align="center">
  <img src="assets/brand/bretzel-mark.png" width="160" alt="Bretzel">
</p>

> Server-Driven UI for Python — typed state, zero npm, batteries included.

Bretzel is a full-stack Python web framework for reactive web apps. Python owns
the application state and the interface that follows it. The browser receives
targeted HTML updates through a small runtime built on HTMX and idiomorph: no
React application, no duplicated client store and no npm pipeline to operate in
production.

<p align="center">
  <a href="https://demo.bretzel-py.dev">
    <img src="assets/demo/kanban-two-windows.gif" width="900"
         alt="The Kanban example open in two windows: a card dragged to Done in the left window appears in the right one with its activity line, then Undo in the right window moves it back in both.">
  </a>
  <br>
  <sub>One Python app, two windows: drag on the left, the right follows; undo on the right, both follow. No JavaScript written.</sub>
</p>

> **Alpha:** the latest public alpha is `0.1.0a2`. APIs may change between
> alpha releases; only the latest alpha receives fixes.

See it first: [component gallery](https://ui.bretzel-py.dev) ·
[documentation](https://docs.bretzel-py.dev) ·
[live Kanban](https://demo.bretzel-py.dev).

## Quickstart

Requires Python 3.12, 3.13 or 3.14.

```bash
python -m pip install bretzel
bretzel new hello
cd hello
python -m pip install -e .
bretzel dev
```

Open <http://127.0.0.1:8000>, then edit `app/features/home.py`.

For an existing application:

```bash
bretzel dev my_package.main:app --port 8010
```

## The model

```python
from bretzel import page, refreshable, ui
from bretzel.state import SessionState


class Counter(SessionState):
    value: int = 0


def increment() -> None:
    Counter().value += 1


@refreshable(deps=[Counter])
def count() -> None:
    ui.heading(str(Counter().value))


@page("/", title="Counter")
def home() -> None:
    count()
    ui.button("+1", on_click=increment)
```

`deps=` names the typed state read by a fragment. When that state changes,
Bretzel renders and ships only that fragment. `broadcast=` can send the same
mutation to other open windows without polling or subscription code.

## What is included

- typed server and client state;
- more than 100 UI components;
- partial navigation and refreshable fragments;
- realtime updates over SSE;
- signed actions, CSRF protection and security headers;
- OAuth/OIDC doors and signed-cookie identity;
- drag-and-drop with server arbitration;
- server-rendered SVG charts;
- `bretzel describe`, `bretzel check` and browser probes;
- a production wheel containing the readable and minified runtime.

Start with `examples/pomodoro` for a small application, `examples/kanban` for
realtime collaboration, `examples/playground` for the component catalogue and
`examples/docs` for the live reference.

## How it compares

NiceGUI keeps a live server-side UI object tree, Reflex compiles Python into a
React application, and FastHTML stays deliberately close to HTML. Bretzel
instead combines typed state and declared dependencies with targeted
server-rendered fragments, multi-user updates and 100+ integrated components,
without a Node or Bun build pipeline. Coming from Streamlit or Dash, you keep
the Python-first workflow and gain explicit state with partial updates instead
of reruns or callback wiring. The detailed comparison, with sources:
<https://docs.bretzel-py.dev/compare>.

## Repository

```text
bretzel/             framework source
examples/            complete demonstration applications
tests/               unit, integration, consistency and browser suites
.claude/bretzel/     detailed framework reference checked against the code
```

A bare `pytest` runs the fast unit, integration and consistency suites. Heavy
suites are explicit:

```bash
pytest -m e2e
pytest -m browser
pytest -m probes
pytest -m audit
```

The public repository contains 262 consistency-test modules. They pin API,
rendering, accessibility and architecture invariants so that fixes cannot
silently drift back.

## Production

Run the generated application as a regular ASGI app and provide a private
secret through the environment:

```bash
BRETZEL_MODE=prod BRETZEL_SECRET_KEY="replace-with-a-random-secret" \
  uvicorn app.main:app --host 0.0.0.0 --port 8000
```

See `SECURITY.md` for private vulnerability reports and `CONTRIBUTING.md` for
the development workflow.

## License

MIT — see [`LICENSE`](LICENSE).
