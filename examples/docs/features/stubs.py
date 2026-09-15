"""Chapitres pas encore écrits — placeholders générés depuis ``NAV``.

La nav montre la carte complète dès maintenant ; les chapitres non
livrés rendent ce stub au lieu d'un 404. Chaque stub est une page
décorée déposée dans le namespace du module ; ``app.include(stubs)``
les découvre comme n'importe quelle feature.

⚠️ **La liste des chapitres livrés est DÉRIVÉE, plus tenue à la main**
(2026-09-03). Elle était un ``_BUILT`` recopié, et elle avait dérivé
dans les deux sens à la fois :

- **trois routes étaient servies DEUX fois.** ``/browser``,
  ``/capabilities`` et ``/tree`` avaient une vraie page ET un stub
  généré, parce que personne n'avait pensé à les inscrire. Seul l'ordre
  des arguments d'``app.include`` décidait laquelle gagnait — un
  classement qui n'est écrit nulle part et que rien ne protégeait ;
- **sept chapitres livrés étaient annoncés « pas encore ».** La
  convention de la nav était « blurb vide = livré », et sept entrées
  livrées portaient encore un blurb.

Les deux moitiés du même bug : une liste écrite à la main à côté de la
vérité. La vérité, ici, c'est la marque que ``@page`` pose sur la
fonction — cf. :func:`routes_livrees`. Gardé par
``test_no_route_is_served_twice``.
"""

from __future__ import annotations

import sys

from bretzel import page, ui

from examples.docs.features.shell import NAV, shell


def routes_livrees() -> frozenset[str]:
    """Les routes qu'un VRAI chapitre sert déjà.

    Lues sur la marque ``_bz_page`` que le décorateur pose, dans les
    modules frères DÉJÀ IMPORTÉS — ``main`` importe ce module en
    dernier, donc ils le sont tous.

    Pourquoi cette source et pas les constantes ``PATH``
    -----------------------------------------------------
    Parce que six chapitres n'en ont pas : ``home``, ``how``,
    ``describe``, les deux ``actions_*`` et ``reactivity_server``
    écrivent leur route directement dans ``@page("…")``. Se fier à
    ``PATH`` les déclarerait non livrés, et on aurait remplacé un
    doublon par six.

    La marque, elle, est posée par le décorateur quelle que soit la
    forme d'écriture. C'est le même mécanisme que le framework emploie
    partout ailleurs pour retrouver un handler (``sys.modules`` +
    ``getattr``), donc rien de neuf à comprendre.
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
            ui.heading(title, level=1, size="2xl")
            ui.text(blurb, color="muted", size="lg")
            ui.badge("Prochaine tranche", color="warning", variant="soft")
            ui.link("← Retour à l'accueil", href="/")


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
        _fn = make(_label, _blurb or "Bientôt.")
        _fn.__name__ = f"stub_{_slug}"
        _fn.__qualname__ = _fn.__name__
        globals()[_fn.__name__] = page(_path, layout=shell, title=_label)(_fn)
