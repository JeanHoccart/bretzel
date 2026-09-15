"""Gate : the committed ``runtime.js`` matches ``_src/``.

``bretzel/runtime/runtime.js`` is a **build artefact** — the concatenation
of ``_src/[0-9]*_*.js`` with the ``protocol.py`` tokens substituted in
(``bretzel/runtime/_build.py``). It is committed, and the browser loads it ;
``_src/`` is what humans edit. Nothing reconciles the two automatically.

``_build.py`` has always shipped a ``--check`` mode for exactly this, and
its docstring calls it « CI — a stale committed ``runtime.js`` fails the
build ». **Nothing in this repo ran it.** Grepped the 2026-08-10 : no test,
no hook, no workflow. So the promise in that docstring was aspirational,
the way the size budget in the same file was (measured 2× its stated cap,
and removed).

What the gap actually costs — the reason this landed while scoping the
drag-and-drop primitive rather than as a chore. Editing ``_src/`` and
forgetting the rebuild leaves the **fast subset entirely green** while the
browser runs the previous bundle. The failure then looks like a broken
component, not a stale artefact, and it is debugged in the browser where
it is most expensive to find.

``test_python_js_mirror`` does not cover this : it reads the *built*
bundle and only asserts that the wire tokens of ``protocol.py`` appear in
it. A whole new ``_src`` module — a component's shared scope factory, say —
is invisible to it.
"""

from __future__ import annotations

from pathlib import Path

from bretzel.runtime import _build


def test_committed_runtime_js_is_not_stale() -> None:
    assert _build.check() == 0, (
        "runtime.js is stale vs _src/ — run "
        "`py -m bretzel.runtime._build` and commit the result. "
        "Until you do, the browser runs the PREVIOUS bundle while this "
        "suite stays green everywhere else."
    )


def test_the_gate_would_notice_an_edit() -> None:
    """Floor : prove the comparison is live, not a tautology.

    ``check()`` reads the file and rebuilds from ``_src/`` — but if either
    side were ever stubbed (or the glob silently matched nothing), the
    equality would hold vacuously and the gate above would pass forever.
    Rebuild in memory, perturb it, and assert the comparison rejects it.
    """
    target = Path(_build.HERE) / "runtime.js"
    on_disk = target.read_text(encoding="utf-8")

    assert on_disk.strip(), "runtime.js is empty — nothing is being compared"
    assert on_disk == _build._bundle(), (
        "precondition: the bundle must match before we perturb it"
    )
    assert on_disk + "/* drift */" != _build._bundle(), (
        "the comparison in _build.check() is vacuous — a modified bundle "
        "still compares equal, so the gate above proves nothing"
    )


def test_every_src_module_reaches_the_bundle() -> None:
    """The glob is the other silent-failure surface.

    ``_bundle()`` collects ``_src/[0-9]*_*.js``. A module named outside that
    shape (``dnd.js``, ``_dnd.js``) is skipped **without a word** — the
    build succeeds, the check passes, and the code simply never ships. That
    is a nastier failure than staleness, because rebuilding does not fix it.
    """
    src = Path(_build.SRC)
    bundled = {p.name for p in sorted(src.glob("[0-9]*_*.js"))}
    present = {p.name for p in src.glob("*.js")}

    assert bundled, "no runtime module matched the build glob at all"
    orphans = present - bundled
    assert not orphans, (
        f"these _src/ modules are NOT in the bundle: {sorted(orphans)}. "
        "The build glob is `[0-9]*_*.js` — rename them `NN_name.js` or "
        "they ship to nobody."
    )
