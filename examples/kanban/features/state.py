"""kanban/state — what each person looks at, on top of the common board.

The board itself lives in ``donnees.Tableau`` (``AppState``): it is the
same for everyone. Everything here is PERSONAL, and the scope says so
without a comment having to repeat it.

- :class:`Moi` is a ``SessionState``: who I am hangs on the cookie, so
  two windows of the same browser are the same person and a private
  window is another. That is what makes the two-screen trial readable.
- :class:`Vue` and :class:`Filtres` are ``PageState``: what I look at
  concerns only me. Filtering on my cards must change nothing for the
  others — and that is precisely why these states are **not** broadcast
  (cf. ``broadcast=`` in ``tableau.py``).

**Nothing is addressable here, and that is a decision.** ``URL = {…}`` is
the mechanic ``examples/messagerie`` stages; taking it up would give two
subjects to an app that demonstrates one. A link to a card is therefore
this example's first acknowledged gap.
"""

from __future__ import annotations

from bretzel import Feature
from bretzel.state import (
    ClientState,
    PageState,
    SessionState,
    field,
    validator,
)
from examples.kanban.features.donnees import CLES, LIB_ETIQUETTE, NOMS


class Moi(SessionState):
    """Who I am on this board.

    There is no authentication: this example stages shared state, and a
    login page is ``auth``'s subject. The banner's selector therefore
    lets you change identity in one click, which is enough to see a
    journal signed by several hands.

    ``SessionState`` and not ``PageState``: changing identity in one tab
    must hold for all the tabs of the same person.
    """

    membre: str = field(default="cam")

    @validator("membre")
    def _membre(cls, value: str) -> str:
        return value if value in NOMS else "cam"


class Vue(PageState):
    """What this page shows on top of the board.

    ``ouverte`` carries the identifier of the card shown in the drawer,
    ``tiroir`` says whether it is open. Two fields for one idea, and it
    is the base layer that imposes it:

    ⚠️ An overlay's ``open=`` only resynchronises from the server if the
    value passed still carries its PROVENANCE — a state field, not an
    expression. ``open=vue.ouverte != ""`` returns an ordinary Python
    ``bool``: the base layer can no longer say where it comes from, does
    not emit the resynchronisation marker, and the drawer keeps its
    client state across the morph. Measured: the card did appear in the
    panel, and the panel stayed closed. It is the same family as
    ``bretzel check``'s ``state-lost-by-a-cast`` rule.
    """

    ouverte: str = field(default="")
    tiroir: bool = field(default=False)


class Affichage(ClientState):
    """What is unfolded on screen, and nothing else.

    ``ClientState`` because showing or hiding a column concerns nobody
    else and changes no data: making it travel to the server cost a round
    trip and a zone re-render to flip a class. Both versions — the panel
    and its rail — are rendered, and ``visible=`` hides one. Zero
    requests.

    It is the exact counterpart of the opposite choice taken for
    :class:`Filtres` just below: there the server MUST know, here it must
    not.
    """

    activite: bool = field(default=True)


class Filtres(PageState):
    """The banner's three filters. Server side, not client — and why.

    ``examples/messagerie`` filters in the browser with
    ``ui.filter_each``: zero requests per keystroke. Here that would be a
    bug. A client filter leaves the hidden cards IN the DOM; the base
    layer reads a drop's index among the draggable elements really
    present, so dropping "in second position" of a filtered column would
    aim at invisible neighbours, and the card would land somewhere other
    than where the finger let it go.

    The server, for its part, filters and computes the neighbours with
    the SAME function (``donnees.colonne_de``), so the two cannot
    diverge.
    """

    qui: str = field(default="tous")
    etiquette: str = field(default="toutes")
    q: str = field(default="")

    @validator("qui")
    def _qui(cls, value: str) -> str:
        return value if value in NOMS else "tous"

    @validator("etiquette")
    def _etiquette(cls, value: str) -> str:
        return value if value in LIB_ETIQUETTE else "toutes"


class Fiche(PageState):
    """WHICH card the drawer's draft belongs to.

    A single field, written by the server on opening. It is what stops a
    card's draft being saved onto another one when the save leaves while
    another is being opened.
    """

    carte_id: str = field(default="")


class Brouillon(ClientState):
    """What is being written in the drawer.

    ⚠️ **``ClientState``, and it took a measurement to write it.** These
    fields lived in the ``PageState`` above, so they were rendered by the
    server — inside a zone declaring ``broadcast=[Tableau]``.
    Consequence: **anybody moved a card, and what you were typing
    vanished.** Measured across two sessions on 2026-09-09 — B writes
    "brouillon en cours" without sending, A drags a card to the other end
    of the board, and four seconds later B's field is empty and their
    title has gone back to the server's.

    A ``ClientState`` value lives in the browser's store: the morph
    reapplies it, so it survives a re-render coming from elsewhere. It is
    the same decision as ``examples/messagerie``'s composing, and for the
    same reason.

    The server can still SEED it — ``logic.charger`` copies the open card
    into it, and the value comes back down in the patch. Writing a client
    state from a handler is a normal path of the base layer, not a
    detour.

    Two regimes still read on screen: the title, the description, the
    assignee, the due date and the points wait for "Enregistrer" —
    writing them at every keystroke would make one shared write per
    character. The labels, the subtasks and the comments leave on the
    click, because a click IS already the decision.
    """

    titre: str = field(default="")
    description: str = field(default="")
    qui: str = field(default="cam")
    echeance: str = field(default="")
    points: int = field(default=0)

    #: The drawer's two add fields. They empty after use, so they are not
    #: part of the draft one saves.
    sous_tache: str = field(default="")
    commentaire: str = field(default="")




class Avancement(ClientState):
    """How many subtasks are ticked, kept IN the browser.

    The truth stays the board: it is what the server writes, and it is
    from it that this counter is re-seeded at every render of the drawer.
    But ticking a box moves the bar **before** the request leaves,
    instead of waiting for the response's 180 kB. It is optimism in the
    strict sense — the client goes ahead, the server arbitrates, the next
    render realigns. Without it the bar was right and LATE, which is the
    worst of the two: the gesture looks as if it did nothing.

    ⚠️ **A separate class, and it is the measurement that imposes it.**
    This field first lived in :class:`Brouillon`. Writing ONE value of a
    client state from the server sends the WHOLE object back in the
    patch: reconciling this counter therefore also put ``commentaire``
    back to the value the server believed, that is, empty. Measured — you
    type, a neighbouring gesture's response arrives 1.2 s later, and the
    field empties on its own.

    The rule that comes out of it: **a draft the human edits and a value
    the server realigns do not share a class.**
    """

    faites: int = field(default=0)


class Nouvelle(PageState):
    """The card being created, in the dialog."""

    titre: str = field(default="")
    colonne: str = field(default="a_faire")

    @validator("colonne")
    def _colonne(cls, value: str) -> str:
        return value if value in CLES else "a_faire"


feature = Feature(
    name="state", kind="state",
    provides=[Moi, Vue, Affichage, Filtres, Fiche, Brouillon,
              Avancement, Nouvelle],
    uses=["donnees"],
)
