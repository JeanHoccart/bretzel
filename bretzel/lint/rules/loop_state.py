"""Rule: a `ServerState` built in an ``async def`` body.

The silence it closes, and it is silent ONLY IN DEV
---------------------------------------------------

``MyState()`` is a constructor: it cannot wait. When the backend also
reads synchronously — which is the case of ``MemoryBackend``, so of any
app started without ``redis_url`` — hydration happens on the spot and
everything works. When it only reads with ``await`` (Redis), the registry
goes through a pool thread… and an ``async def`` body does NOT run in
that thread, it runs on the loop, where waiting would freeze the whole
worker. ``StateRegistry`` therefore raises
:class:`~bretzel.state.StateHydrationError` rather than returning default
values the end-of-request commit would write over the real ones.

Consequence: **the same line works in dev and raises in production**, the
day somebody sets ``redis_url``. It is this repository's most expensive
class of failure — the one that waits for deployment to show itself, like
the assembled Tailwind class (``rules/tailwind.py``). Hence a static
rule: it gives the verdict in dev, with no backend, executing nothing.

The correct gesture is written in the message: ``state = await
MyState.load()``, or put the body back to ``def`` — the framework will
offload it onto a thread, where ``MyState()`` works as-is.

⚠️ What this rule does NOT see
------------------------------

It reads **one** module and follows the LEXICON, not the calls. A
construction tucked into a synchronous helper called from the ``async
def`` escapes it entirely — and that is the real case that motivated the
rule: ``examples/crm/features/import_screen.py`` does
``judge(rows, visible_owner())`` in an ``async`` handler, and it is
``visible_owner()``, in ANOTHER file, that builds the state. Following
that would require an inter-module call graph, which
``bretzel.lint``'s corpus does not build (a rule sees one
:class:`~bretzel.lint.corpus.Module`, one only).

So it catches the direct FORM, not the chain. That is written here so
that its silence is not read as an acquittal.

What it spares, and why that is the half that counts
----------------------------------------------------

- ``await MyState.load()`` — an ATTRIBUTE call, never a bare name: it is
  the intended door, it cannot be confused.
- A ``ClientState``: it touches no backend, its value arrives in the
  request body. Building it on the loop is free.
- A ``def`` nested inside an ``async def`` still counts as "on the
  loop": the framework will not offload a local function the author
  calls themselves.
"""

from __future__ import annotations

import ast
from functools import lru_cache

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding

RULE = "state-built-on-the-loop"


@lru_cache(maxsize=1)
def _server_state_names() -> frozenset[str]:
    """The public SERVER state classes, derived and not copied.

    Derived, because a hand-written table of names drifts from the code
    it judges — that is the folder's rule. The filter is ``ServerState``
    and not ``State`` — a ``ClientState`` has no backend to wait for, so
    nothing to refuse.
    """
    import inspect

    import bretzel
    import bretzel.state as state_module
    from bretzel.state.scopes.server import ServerState

    names = set()
    for module in (bretzel, state_module):
        for name in dir(module):
            obj = getattr(module, name, None)
            if inspect.isclass(obj) and issubclass(obj, ServerState):
                names.add(name)
    return frozenset(names)


def _base_names(node: ast.ClassDef) -> set[str]:
    """The base names written, ``module.Class`` reduced to ``Class``."""
    names: set[str] = set()
    for base in node.bases:
        if isinstance(base, ast.Name):
            names.add(base.id)
        elif isinstance(base, ast.Attribute):
            names.add(base.attr)
    return names


def _local_server_states(tree: ast.Module) -> set[str]:
    """The server states declared IN this module.

    An app readily derives a common base state; recognising only the
    framework's classes would miss the whole second generation. The
    classes are read in file order, so a local base is known before its
    children — Python's writing order.
    """
    known = _server_state_names()
    local: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and _base_names(node) & (known | local):
            local.add(node.name)
    return local


def check(module: Module) -> list[Finding]:
    """The server-state constructions made from the loop."""
    names = _server_state_names() | _local_server_states(module.tree)

    findings: list[Finding] = []
    for func in ast.walk(module.tree):
        if not isinstance(func, ast.AsyncFunctionDef):
            continue
        for node in ast.walk(func):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            built = node.func.id
            if built not in names:
                continue
            findings.append(
                Finding(
                    rule=RULE,
                    path=module.path,
                    line=node.lineno,
                    message=(
                        f"`{built}()` is built in `{func.name}`, which is "
                        f"`async def` — so on the loop, where the state "
                        f"cannot hydrate if the backend reads over the "
                        f"network."
                    ),
                    hint=(
                        f"Write `state = await {built}.load()`, or put "
                        f"`{func.name}` back to `def` (the framework will "
                        f"offload it onto a thread, where `{built}()` works "
                        f"as-is). In memory the current line works; with "
                        f"`redis_url` it raises — it is a fault that waits "
                        f"for production."
                    ),
                )
            )
    return findings
