"""features/vue_classe — state: what is being looked at of a class.

``kind="state"``: a feature carrying only a typed state, and existing for
a precise reason — **breaking a contract cycle**.

How it came about
------------------
The class screen (``features/classe.py``) mounts its tabs, and every tab
is a separate feature: ``evaluations`` in batch 5, the summary in 6, the
plan in 7. Both sides need the same thing — which class, which term — so
the first attempt put ``VueClasse`` in ``classe.py`` and made the panel
import from there. Result: ``classe`` imports ``evaluations`` which
imports ``classe``.

``bretzel check --deep`` said so in three lines (*"the feature `classe`
imports ['evaluations'] without declaring it"*), and declaring the
``uses`` on both sides would have closed the cycle in the CONTRACT
instead of removing it from the code — that is, written in so many words
that it is accepted.

The shared state in its own feature costs ten lines and makes the graph
acyclic: ``classe`` and ``evaluations`` both depend on it, neither
depends on the other. It is also what allowed removing the app's only
deferred import.
"""

from __future__ import annotations

from bretzel import Feature, refreshable, ui
from bretzel.state import PageState, field


class VueClasse(PageState, addressable=True):
    """The class open and the term being looked at.

    ⚠️ **``classe_id`` lives here and not in the zones' signature**, and
    it is the base layer that imposes it: a ``@refreshable`` zone is
    called back WITHOUT arguments on refresh. A required parameter raises
    a 500 at the first action touching a ``deps`` — never on load, hence
    never on re-reading the page; a parameter with a default value raises
    nothing and simply re-renders ANOTHER class.

    Only ``trimestre`` carries a ``url=``: the class is in the PATH, it
    is a resource identifier and not a view setting (EF-U1).
    """

    classe_id: int = field(default=0)
    trimestre: int = field(default=1, url="t")


def changer_trimestre(vue: VueClasse) -> None:
    """The body is empty **and that is the mechanism**: the base layer
    hydrated ``vue.trimestre`` before the call, and the mutation alone
    re-renders the zones declaring ``deps=[VueClasse]``. The TYPED
    parameter is what hydrates — without it, the handler would answer
    zero bytes."""


@refreshable(deps=[VueClasse])
def selecteur_trimestre() -> None:
    """The term being looked at (EF-C2), and it lives in the address
    (EF-U1).

    A zone of its own: it commands ALL the screen's panels — the pupils,
    the assessments, the summary — so it cannot live in any of them.
    """
    vue = VueClasse()
    with ui.hstack(gap="md", align="center", wrap=True):
        ui.text("Trimestre", color="muted")
        ui.toggle_group(
            value=vue.trimestre,
            options=[(1, "1"), (2, "2"), (3, "3")],
            on_change=changer_trimestre,
        )


feature = Feature(
    name="vue_classe",
    kind="state",
    provides=[VueClasse, changer_trimestre, selecteur_trimestre],
)
