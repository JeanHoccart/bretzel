"""Client verbs — BROWSER actions, written in Python.

::

    ui.button("Copy the key", on_click=bretzel.copy(state.api_key))
    ui.button("Print",        on_click=bretzel.print_page())
    ui.button("Fullscreen",   on_click=bretzel.fullscreen(dashboard))

Why this costs almost nothing
-----------------------------
Because the slot already exists. ``on_<event>=`` is **polymorphic**: a
callable goes out as a signed POST to the server, a **string** is client
source evaluated on the spot, with no round trip. That is the contract of
``dialog.open()`` and of ``ClientBinding.set()`` — the verbs add nothing
to it, they plug into it. No new directive, no scope, no request.

Why they live in ``runtime/`` and not in ``server/``
----------------------------------------------------
The other symbols exposed on ``bretzel`` — ``abort``, ``redirect``,
``push_url``, ``reload``, ``background``, ``idempotent`` — all live in
``bretzel/server/``, and for a reason: they act on the request/response
cycle. ``abort`` raises an HTTP status, ``redirect`` writes a header.

**A verb never touches the server.** Putting it in ``server/`` would make
the package name lie. Its place is here because it is the Python half of
a TWO-sided contract: ``copy`` only exists if ``$bz.verbs.copy`` exists,
and the two must stay in agreement. That is exactly the situation of
:mod:`bretzel.runtime.protocol` ↔ ``runtime.js``, and the remedy is the
same — both halves in the same package, within sight of each other.

The DAG allows it without bending anything: ``runtime`` sits above
``state`` (``envelope.py`` already imports ``ClientState``), and a verb
needs nothing else.

⚠️ The name, settled on 2026-09-01
-----------------------------------
The ``test_handler_helpers_have_one_home`` gate sets a **mechanical**
criterion: ``ui.*`` is called from a render body, ``bretzel.*`` from a
handler. A verb is written in a render body, so that criterion alone
would place it on ``ui``.

**The user settled on ``bretzel.*``**, and the arbitration holds: ``ui``
names what takes part in the TREE — components, descriptors
(``ui.column``, ``ui.track``), iteration keys, a reactive source a prop
consumes (``ui.pending``). A verb takes part in no tree: it triggers an
effect in the browser, the way ``redirect`` triggers one in the response.
The line becomes "what DOES something is on ``bretzel``, what IS
something is on ``ui``", and it stays checkable.

It is not perfect, and saying so is better than dressing it up:
``ui.notification`` produces an effect and lives on ``ui``. It predates
this, it is already declared as an exception in
``_EXPECTED_UI_FUNCTIONS``, and moving it would be a public break for a
vocabulary consistency — not a trade one makes without asking.

What is NOT here, and why
-------------------------
- ⚠️ **``share`` and ``vibrate`` were deferred here "to the touch
  slice". Shipped on 2026-09-02 — the deferral held for one and not for
  the other.** ``navigator.vibrate`` EXISTS everywhere (measured:
  ``function`` on desktop Chromium) and does nothing without hardware,
  so there was no absence decision to take: the "mobile axis" argument
  did not hold. ``navigator.share``, on the other hand, is ``undefined``
  on that same Chromium — the deferral was therefore justified, but not
  for the written reason: the absence is not an edge case, it is the
  NORMAL case on the machine one develops on.
- **Visual feedback on copy** — user decision of 2026-09-01: nothing by
  default. The verb copies, the app wires whatever feedback it wants. A
  ``ui.copy_button`` toggling for two seconds stays the obvious form the
  day the need comes up.

Cf. ``.claude/work/these-portee-2026-08-19.md`` § 6.a.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from bretzel.state.scopes.client import ClientBinding

__all__ = ["copy", "fullscreen", "print_page", "share", "vibrate"]


def _as_client_source(value: Any) -> str:
    """``value`` as JS source — a bound path, or a literal.

    Three possible inputs at a call site, and all three must work
    without the caller having to know which one it holds:

    - a :class:`~bretzel.state.scopes.client.ClientBinding` (so also a
      ``ClientExpression``, which inherits from it) → its client path,
      read at execution time. That is what makes it possible to copy a
      value the server does not know;
    - a SERVER state field (``state.api_key``) → at render time it is
      already the string itself, so it goes out as a literal;
    - any Python value → ``json.dumps``, whose output is a valid JS
      literal for scalars, lists and dicts.

    ``binding_path()`` rather than a ladder of ``isinstance``: it is the
    method ``Component.path_of`` calls for the same question, and it
    returns the right form for both subclasses.
    """
    if isinstance(value, ClientBinding):
        return value.binding_path()
    return json.dumps(value)


def copy(value: Any) -> str:
    """Copy ``value`` to the clipboard when the action runs."""
    return f"$bz.verbs.copy({_as_client_source(value)})"


def print_page() -> str:
    """Open the browser print dialog when the action runs."""
    return "window.print()"


def fullscreen(target: Any = None) -> str:
    """Enter fullscreen mode when the action runs."""
    if target is None:
        node = "document.documentElement"
    else:
        node_id = getattr(target, "id", None)
        if not node_id:
            raise ValueError(
                "bretzel.fullscreen(target=…): the target has no rendered "
                "``id``, so the client cannot find it. Pass a built "
                "component — ``ui.container(id='dashboard')`` — or nothing "
                "at all to target the whole page."
            )
        node = f"document.getElementById({json.dumps(str(node_id))})"
    # ``?.``: a browser without fullscreen must not raise inside an
    # ``on_click``, where nobody catches. And the ``catch`` covers the
    # refusal — the user may say no, that is not an app error.
    return (
        f"({node}.requestFullscreen && "
        f"{node}.requestFullscreen().catch(() => {{}}))"
    )


def share(
    url: Any = None, *, title: Any = None, text: Any = None
) -> str:
    """Open the native share sheet, or copy the URL when sharing is unavailable."""
    charge: dict[str, Any] = {}
    for key, value in (("url", url), ("title", title), ("text", text)):
        if value is not None:
            charge[key] = _as_client_source(value)
    body = ", ".join(f"{c}: {v}" for c, v in charge.items())
    return f"$bz.verbs.share({{{body}}})"


def vibrate(pattern: int | Sequence[int] = 50) -> str:
    """Vibrate the device when the action runs."""
    return f"$bz.verbs.vibrate({json.dumps(list(pattern) if not isinstance(pattern, int) else pattern)})"
