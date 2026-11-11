"""Kanban — a demonstrator of the **shared board**, dragged by several.

Run: ``py -m examples.kanban.main`` (port 8009).

**One board per visitor, shared by that visitor's windows.**
``donnees.Tableau`` is a ``SessionState`` since ``75f9a702``, on purpose:
on the public demo, a board common to every visitor would let anyone
write anything for everyone to read. Its windows still share it — two
tabs of the same browser are one session — and the signal reaches
exactly them: a ``SessionState`` signal stays in its session (decided on
2026-10-03, ``tests/integration/server/test_a_session_state_broadcast_
stays_in_its_session.py``), so other visitors are neither reached nor
re-rendered. An ``AppState`` board would be shared by everyone, with the
same code.

A zone re-renders when what it read changes, in every window showing
it, as far as that state's scope allows — nothing to write. The board
is a ``SessionState``: I change it, my other windows see it. The filters
are ``PageState``: what I hide concerns only this window, and nobody
else redraws at every keystroke.

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
``languages=("en", "fr")`` and writes its own sentences ``t("Create")`` —
English is the source, ``core/i18n.FR`` the French, the sentence as its
key. Bretzel resolves the language (cookie, then ``Accept-Language``),
says its own words in it, and the app's through ``t()``, the seeded board
included; ``bretzel translations examples.kanban.main:app`` lists what
the French table lacks. The activity feed keeps what was written
AT THE TIME — a line filed in French stays in French, because a log
records what was said.

**No database**: restarting the server puts the board back to its
starting state. **No authentication**: the "You are…" selector changes
identity in one click, because this example's subject is shared state
and not signing in. And **no addressable field**: taking up
``URL = {…}`` here would give two subjects to an app that demonstrates
one.

**An API, on the same board** — ``features/api.py``: the banner's ``</>``
button shows a ready ``curl`` whose card lands on the visitor's board,
live, and ``/docs`` lists and tries the routes.

This app does not use the ``Feature`` contracts: app structure is what
``examples/mad`` stages.
"""

import os

from bretzel import Bretzel
from examples.kanban.core.i18n import FR
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
    # ``t()`` and the French table; the framework's own through ``lang``.
    lang="en",
    languages=("en", "fr"),
    translations={"fr": FR},
    api_docs=True,
)

app.include(donnees, state, logic, shell, fiche, tableau)
app.fastapi.include_router(api.router)


if __name__ == "__main__":
    app.run(port=8009, reload=True)
