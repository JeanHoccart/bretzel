"""Chapters not yet written — placeholders generated from ``NAV``.

The nav shows the complete map right away; the chapters not delivered
render this stub instead of a 404. Every stub is a decorated page dropped
into the module's namespace; ``app.include(stubs)`` discovers them like
any feature.

⚠️ **The list of delivered chapters is DERIVED, no longer kept by hand**
(2026-09-03). It was a copied ``_BUILT``, and it had drifted in both
directions at once:

- **three routes were served TWICE.** ``/browser``, ``/capabilities``
  and ``/tree`` had a real page AND a generated stub, because nobody had
  thought to list them. Only the order of ``app.include``'s arguments
  decided which won — a ranking written nowhere and that nothing
  protected;
- **seven delivered chapters were announced "not yet".** The nav's
  convention was "empty blurb = delivered", and seven delivered entries
  still carried a blurb.

Both halves of the same bug: a list written by hand beside the truth. The
truth, here, is the mark ``@page`` sets on the function — cf.
:func:`routes_livrees`. Guarded by ``test_no_route_is_served_twice``.
"""

from __future__ import annotations

import sys

from bretzel import page, ui

from examples.docs.features.shell import NAV, localized_nav_label, shell
from examples.docs.lib.i18n import tr


def routes_livrees() -> frozenset[str]:
    """The routes a REAL chapter already serves.

    Read from the ``_bz_page`` mark the decorator sets, in the sibling
    modules ALREADY IMPORTED — ``main`` imports this module last, so they
    all are.

    Why this source and not the ``PATH`` constants
    -----------------------------------------------
    Because six chapters have none: ``home``, ``how``, ``describe``, the
    two ``actions_*`` and ``reactivity_server`` write their route
    directly in ``@page("…")``. Relying on ``PATH`` would declare them
    undelivered, and one would have replaced one duplicate by six.

    The mark, on the other hand, is set by the decorator whatever the
    writing form. It is the same mechanism the framework uses everywhere
    else to find a handler (``sys.modules`` + ``getattr``), so there is
    nothing new to understand.
    """
    paquet = __name__.rsplit(".", 1)[0] + "."
    livrees: set[str] = set()
    for nom, module in list(sys.modules.items()):
        if not nom.startswith(paquet) or nom == __name__ or module is None:
            continue
        for objet in vars(module).values():
            marque = getattr(objet, "_bz_page", None)
            chemin = getattr(marque, "path", None)
            if isinstance(chemin, str):
                livrees.add(chemin)
    return frozenset(livrees)


def stub_body(title: str, blurb: str) -> None:
    with ui.container(width="md"):
        with ui.vstack(gap="lg", align="center", justify="center",
                       classes="min-h-[60vh] text-center"):
            ui.icon("hard-hat", size="xl", color="muted")
            ui.heading(localized_nav_label(title), level=1, size="2xl")
            ui.text(blurb, color="muted", size="lg")
            ui.badge(tr("Coming next", "Prochaine tranche"), color="warning", variant="soft")
            ui.link(tr("← Back to home", "← Retour à l'accueil"), href="/")


def make(title: str, blurb: str):
    def _stub() -> None:
        stub_body(title, blurb)
    return _stub


_LIVREES = routes_livrees()

for _section, _items in NAV:
    for _label, _path, _icon, _blurb in _items:
        if _path in _LIVREES or _path.startswith("http"):
            continue
        _slug = _path.strip("/").replace("-", "_") or "root"
        _fn = make(_label, _blurb or tr("Coming soon.", "Bientôt."))
        _fn.__name__ = f"stub_{_slug}"
        _fn.__qualname__ = _fn.__name__
        globals()[_fn.__name__] = page(_path, layout=shell, title=_label)(_fn)
