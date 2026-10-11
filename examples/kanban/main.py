"""Kanban — a demonstrator of the **shared board**, dragged by several.

Run: ``py -m examples.kanban.main`` (port 8009).

**One board per visitor, shared by that visitor's windows.**
``donnees.Tableau`` is a ``SessionState`` since ``75f9a702``, on purpose:
on the public demo, a board common to every visitor would let anyone
write anything for everyone to read. Its windows still share it — two
tabs of the same browser are one session — and the broadcast reaches
exactly them: a ``SessionState`` signal stays in its session (decided on
2026-10-03, ``tests/integration/server/test_a_session_state_broadcast_
stays_in_its_session.py``), so other visitors are neither reached nor
re-rendered. An ``AppState`` board would be shared by everyone, with the
same code.

Each zone declares two distinct lists —

    @refreshable(deps=[Tableau, Filtres], broadcast=[Tableau])

— and the question they ask is not the same. ``deps`` says *what
re-renders me*, in the response to my own action. ``broadcast`` says
*what the other windows must redo*, through an SSE signal. The board is
in both: I change it, they must see it. The filters are only in ``deps``
— what I hide concerns only me, and broadcasting it would make the whole
team work again at every keystroke of a single person.

**The trial that proves something is done with TWO windows.** One shows
nothing: it would have re-rendered its own zone anyway. Open the app
twice side by side in the same browser and drag a card on the left: it
moves on the right, and the activity feed writes there who did it. (A
private window is another session, hence another board.)

**Drag and drop** is the board's verb, and the server arbitrates it. "En
cours" and "En revue" carry a work-in-progress limit; beyond it, the
handler mutates nothing — and since the browser had already moved the
card, the render that contradicts it puts it back. There is no
``reject()``: refusing is writing nothing. The archive strip under the board
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

**An API, on the same board** — ``features/api.py``: the banner's ``</>``
button shows a ready ``curl`` whose card lands on the visitor's board,
live, and ``/docs`` lists and tries the routes.

This app does not use the ``Feature`` contracts: app structure is what
``examples/mad`` stages.
"""

import os

from bretzel import Bretzel
from examples.kanban.core.theme import THEME
from examples.kanban.features import (
    api,
    donnees,
    fiche,
    logic,
    shell,
    state,
    tableau,
)

#: A local run stays in dev with a throwaway key. The public demo sets
#: ``BRETZEL_MODE=prod`` in its compose file: the key then comes from
#: ``$BRETZEL_SECRET_KEY`` (``secret_key=None`` falls through to it), and
#: the framework refuses to start without one.
MODE = os.environ.get("BRETZEL_MODE", "dev")

app = Bretzel(
    title="Bretzel · Kanban",
    secret_key="dev-kanban-secret-change-me" if MODE == "dev" else None,
    mode=MODE,
    theme=THEME,
    # English is the source language and the default; French is one
    # click away, in the banner. The app's own sentences go through
    # ``core/i18n.tr``; the framework's own go through ``lang``.
    lang="en",
    languages=("en", "fr"),
    api_docs=True,
)

app.include(donnees, state, logic, shell, fiche, tableau)
app.fastapi.include_router(api.router)


if __name__ == "__main__":
    app.run(port=8009, reload=True)
