"""Kanban — a demonstrator of the **shared board**, dragged by several.

Run: ``py -m examples.kanban.main`` (port 8009).

⚠️ **What follows is what the app is FOR, and the code no longer does
it.** ``donnees.Tableau`` became a ``SessionState`` in ``75f9a702``, so
the board is per-visitor: two windows no longer share anything, and the
SSE broadcast has nobody to reach. Measured on 2026-09-20 —
``tests/probes/probe_kanban.py`` ① fails on its two checks ("B sees the
card arrive without having done anything", "B's activity feed says who
did it"), and it already failed before this file was touched. Either the
scope goes back to ``AppState``, or this docstring and the probe stop
promising a shared board. Written here rather than quietly corrected:
the choice is not a translator's to make.

What this example shows, and why it exists. The board is an
``AppState``: a SINGLE object every open window talks about. Each zone
declares two distinct lists —

    @refreshable(deps=[Tableau, Filtres], broadcast=[Tableau])

— and the question they ask is not the same. ``deps`` says *what
re-renders me*, in the response to my own action. ``broadcast`` says
*what the other windows must redo*, through an SSE signal. The board is
in both: I change it, they must see it. The filters are only in ``deps``
— what I hide concerns only me, and broadcasting it would make the whole
team work again at every keystroke of a single person.

**The trial that proves something is done with TWO windows.** One shows
nothing: it would have re-rendered its own zone anyway. Open the app
twice side by side — a private window to be somebody else — and drag a
card on the left: it moves on the right, and the activity feed writes
there who did it.

**Drag and drop** is the board's verb, and the server arbitrates it. "En
cours" and "En revue" carry a work-in-progress limit; beyond it, the
handler mutates nothing — and since the browser had already moved the
card, the render that contradicts it puts it back. There is no
``reject()``: refusing is writing nothing. The banner's "Archiver" zone
shows the other door, ``locked=True``: it accepts everything and lets
nothing leave.

**Bilingual**, and the seam is worth a look: the app declares
``languages=("en", "fr")`` and routes its own sentences through
``core/i18n.tr(en, fr)``. Bretzel resolves the language (cookie, then
``Accept-Language``) and translates ITS words; the app translates its
own, the seeded board included. The activity feed keeps what was written
AT THE TIME — a line filed in French stays in French, because a log
records what was said.

**No database**: restarting the server puts the board back to its
starting state. **No authentication**: the "You are…" selector changes
identity in one click, because this example's subject is shared state
and not signing in (``examples/auth`` does the other one). And **no
addressable field**: ``URL = {…}`` is ``examples/messagerie``'s
mechanic, taking it up here would give two subjects to an app that
demonstrates one.

This app does not use the ``Feature`` contracts: app structure is what
``examples/mad`` stages.
"""

from bretzel import Bretzel
from examples.kanban.core.theme import THEME
from examples.kanban.features import (
    donnees,
    fiche,
    logic,
    shell,
    state,
    tableau,
)

app = Bretzel(
    title="Bretzel · Kanban",
    secret_key="dev-kanban-secret-change-me",
    theme=THEME,
    mode="dev",
    # English is the source language and the default; French is one
    # click away, in the banner. The app's own sentences go through
    # ``core/i18n.tr``; the framework's own go through ``lang``.
    lang="en",
    languages=("en", "fr"),
)

app.include(donnees, state, logic, shell, fiche, tableau)


if __name__ == "__main__":
    app.run(port=8009, reload=True)
