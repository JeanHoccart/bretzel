# Bretzel

<p align="center">
  <img src="assets/brand/bretzel-mark.png" width="160" alt="Bretzel">
</p>

> Server-Driven UI for Python — typed state, zero npm, batteries included.

Bretzel is a full-stack Python web framework for building reactive
applications. Python owns the routes, typed state, actions and interface; the
browser stays synchronized without a separate JavaScript application or an npm
pipeline to operate in production.

> **Alpha:** the first public candidate is `0.1.0a1`. APIs may change between
> alpha releases; only the latest alpha receives fixes.

## Quickstart

Requires Python 3.12 or 3.13.

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

## Architecture

Bretzel is the framework application developers program against—not a React
generator or a JavaScript build tool. Its implementation deliberately relies
on proven lower-level components:

- FastAPI and Starlette provide the ASGI and HTTP foundation;
- HTMX transports navigation, actions and targeted HTML updates;
- Idiomorph reconciles returned fragments with the current DOM;
- Bretzel's integrated runtime handles client state, directives, reconnection
  and the framework protocol.

These components are implementation infrastructure. A Bretzel application is
written, structured and deployed as a Python application; it does not require
a separate frontend repository or an npm toolchain.

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

From a repository checkout, launch that documentation with:

```bash
python -m examples.docs.main
```

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

The public repository contains 249 consistency-test modules. They pin API,
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
