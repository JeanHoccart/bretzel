"""Drift gate — a server-state ``default_factory`` must not mint random identity.

A ``ServerState`` (``SessionState`` / ``UserState`` / ``AppState`` /
``PageState``) is **re-materialised from its defaults on every request until a
mutation persists it** — this is the framework's deliberate lazy-default design
(``tests/unit/state/test_registry.py::test_clean_state_not_saved``). So a
``default_factory`` that mints a *random identity* (``uuid4``,
``secrets.token_*``, ``random.*``) produces **fresh ids on each render** : the
id baked into a Move/Delete button at render time never matches the store when
the handler runs → id-keyed actions silently no-op until the first mutation.

This bit kanban / contacts / expenses at once (2026-07-14). The fix is stable
seed identity — ``{"id": f"seed-{i}", …}`` — exactly what ``tracker._seed``
(``f"iss-{1001+i}"``) already did. See ``.claude/bretzel/traps.md`` §
"``default_factory`` NON-DÉTERMINISTE".

Scope, deliberately tight to stay precise :

- Only **server** states (ClientState rides the client envelope, different
  semantics).
- Only **randomness / uuid / token** roots (``uuid`` / ``secrets`` /
  ``random``). ``datetime.now()`` / ``date.today()`` are NOT flagged : a seed
  with *relative dates* is a legitimate value (not an action key), and expenses
  keeps exactly that after fixing its ids.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.consistency._discovery import EXAMPLES_FLOOR, parsed_sources

_EXAMPLES = Path(__file__).resolve().parents[2] / "examples"

# Class bases that denote a server-side scope (value re-derived per request).
_SERVER_STATE_BASES = {
    "SessionState",
    "UserState",
    "AppState",
    "PageState",
    "ServerState",
}

# Non-deterministic *identity/randomness* roots. ``x.<attr>()`` where ``x`` is
# one of these, or a bare ``<name>()`` from-imported off one of these modules.
_RANDOM_ROOTS = {"uuid", "secrets", "random"}
_RANDOM_NAMES = {
    "uuid1", "uuid3", "uuid4", "uuid5",
    "token_hex", "token_urlsafe", "token_bytes",
    "getrandbits", "randint", "randrange", "random", "choice", "choices",
    "shuffle", "sample", "uniform",
}


def _module_functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }


def _is_server_state(cls: ast.ClassDef) -> bool:
    for base in cls.bases:
        # Bare ``SessionState`` (the idiom in every example) OR a qualified
        # ``bretzel.state.SessionState`` — match the trailing name either way,
        # so an attribute base can't silently slip past a gate whose whole
        # job is confidence. (A ``... as SS`` alias would still miss; no
        # example aliases scope bases, so resolving imports isn't worth it.)
        name = base.id if isinstance(base, ast.Name) else getattr(base, "attr", None)
        if name in _SERVER_STATE_BASES:
            return True
    return False


def _factory_arg(call: ast.Call) -> ast.expr | None:
    """Return the ``default_factory=`` argument of a ``field(...)`` call."""
    if not (isinstance(call.func, ast.Name) and call.func.id == "field"):
        return None
    for kw in call.keywords:
        if kw.arg == "default_factory":
            return kw.value
    return None


def _mints_randomness(node: ast.AST) -> bool:
    """True iff ``node`` (a function body or lambda) calls uuid/secrets/random.

    Two branches on purpose — they catch the same intent through the two ways
    the call can be written, so neither spelling is a silent miss :

    - **root-qualified** ``uuid.uuid4()`` / ``random.choice()`` — matched by
      module root alone (every current example imports the module, not the
      function), so the exact method name is irrelevant ;
    - **from-imported** ``uuid4()`` / ``token_hex()`` — no root to key on, so
      matched against the curated identity/randomness name set.
    """
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id in _RANDOM_ROOTS
        ):
            return True
        if isinstance(func, ast.Name) and func.id in _RANDOM_NAMES:
            return True
    return False


def test_server_state_default_factory_is_deterministic() -> None:
    offenders: list[str] = []

    for source in parsed_sources(_EXAMPLES, floor=EXAMPLES_FLOOR):
        py, tree = source.path, source.tree
        # State classes + their factories are top-level by convention, so a flat
        # ``tree.body`` scan suffices (and matches ``_module_functions``). The
        # name→func map is built lazily : most files have no server state at all.
        funcs: dict[str, ast.FunctionDef] | None = None

        for cls in tree.body:
            if not (isinstance(cls, ast.ClassDef) and _is_server_state(cls)):
                continue
            for stmt in cls.body:
                if not isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                    continue
                if not isinstance(stmt.value, ast.Call):
                    continue
                factory = _factory_arg(stmt.value)
                if factory is None:
                    continue
                # Resolve the factory: a named module function, or a lambda.
                target: ast.AST | None = None
                if isinstance(factory, ast.Name):
                    if funcs is None:
                        funcs = _module_functions(tree)
                    target = funcs.get(factory.id)
                elif isinstance(factory, ast.Lambda):
                    target = factory
                if target is not None and _mints_randomness(target):
                    tgt = stmt.target if isinstance(stmt, ast.AnnAssign) else stmt.targets[0]
                    field_name = getattr(tgt, "id", "?")
                    rel = py.relative_to(_EXAMPLES.parent).as_posix()
                    offenders.append(f"{rel} :: {cls.name}.{field_name}")

    assert not offenders, (
        "Server-state default_factory mints random identity (uuid/secrets/"
        "random) — re-run every request until a mutation persists it, so "
        "id-keyed actions no-op. Use stable seed ids (f\"seed-{i}\").\n  "
        + "\n  ".join(offenders)
    )


def test_the_detector_still_bites() -> None:
    """Mutation : une graine non déterministe est encore reconnue.

    Un ``default_factory`` qui tire au hasard donne un état différent à
    chaque worker — et le bug ne se voit qu'en production multi-process.
    Si le détecteur cessait de matcher, l'interdiction passerait sur
    tous les exemples sans rien regarder.
    """
    # Les deux orthographes que le détecteur couvre à dessein : racine de
    # module, et nom importé directement.
    for source in ("uuid.uuid4()", "random.random()", "uuid4()", "token_hex()"):
        assert _mints_randomness(ast.parse(source)), f"{source} devrait mordre"
    # ⚠️ ``datetime.now()`` n'y est PAS, et ce n'est pas un oubli : la gate
    # porte sur l'ALÉA et l'identité, pas sur le temps. Une graine
    # temporelle est un autre sujet, avec un autre remède.
    for licit in ("list()", "dict()", "MyState()", "datetime.now()"):
        assert not _mints_randomness(ast.parse(licit)), f"{licit} : faux positif"
