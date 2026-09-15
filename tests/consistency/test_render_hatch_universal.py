"""Une échappatoire `render=` rend le CORPS — une fois, sans orphelin.

Le motif que ce fichier fige : quand un composant rend une **collection**
(des cellules, des segments de fil d'Ariane, des options), l'auteur n'a
aucun moyen d'y mettre du balisage — le composant boucle sur des données
et pose du texte. L'échappatoire est un rappel ::

    ui.breadcrumb(items, render=lambda item, is_last: ui.badge(…))
    ui.column("statut", render=lambda value, row: ui.badge(value))

Le partage, qui est TOUT le contrat
-----------------------------------

Le composant garde son **enveloppe** — le ``<td>`` d'une cellule, le
``<a href>`` et le ``<span aria-current="page">`` d'un segment, les
classes du thème. Le rappel remplit le **corps**. Une échappatoire qui
avalerait l'enveloppe ferait perdre la navigation et l'annonce « page
courante » au premier usage : l'auteur devrait les réécrire à la main
pour poser une icône, et se tromperait.

Ce que la gate exige, pour chaque échappatoire du catalogue :

1. le retour du rappel **atteint le DOM** ;
2. **une occurrence par appel** — c'est la moitié qu'on oublie. Un
   Component bâti dans le corps du rappel s'auto-enregistre auprès du
   parent actif, donc sans ``coerce_children`` (qui détache) il rend DEUX
   fois : une fois à sa place, une fois en frère. Le nombre d'appels est
   MESURÉ, pas supposé — une échappatoire de collection est appelée une
   fois par item ;
3. il ne laisse **aucun orphelin** à la racine du contexte de rendu — la
   même faute vue par l'autre bout, celui que le point 2 rate quand le
   composant est rendu détaché.

Sœur de ``test_render_never_orphans``, qui couvre les Components que le
FRAMEWORK construit dans un ``render()``. Ici ce sont ceux que
l'UTILISATEUR construit, dans un rappel que le framework appelle — même
mécanisme d'auto-enregistrement, autre population.

Pourquoi la découverte est en deux morceaux
-------------------------------------------

Un balayage purement signature-driven (« tout paramètre annoté
``Callable`` ») ramène 6 entrées dont **3 ne sont pas des échappatoires
de contenu** : ``datatable.rows`` est une source de données,
``table.row_key`` et ``datatable.row_key`` calculent une clé qui part en
attribut. Le discriminant n'est pas l'annotation, c'est **où le retour
atterrit** — d'où le filtre empirique (la sentinelle ressort-elle en
CONTENU du DOM ?), le même que celui du contrat de slot textuel.

Et il manque l'inverse : ``ui.column(render=)`` vit sur une **dataclass**,
pas sur la signature d'un composant, donc aucune introspection de
composant ne le voit. Il est déclaré à la main dans :data:`EXTRA`, et
``test_extra_hatches_still_exist`` re-vérifie l'entrée à chaque run — une
liste écrite à la main qu'on ne re-mesure pas est une gate qui a déjà
perdu.
"""

from __future__ import annotations

import pytest

from bretzel import ui
from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from bretzel.introspect import describe_component
from bretzel.render.context import current_context
from tests.consistency._discovery import (
    in_text_content,
    public_component_classes,
    ui_name_of,
)

#: Preuve de morsure : controle POSITIF — les echappatoires declarees a la main existent
#: encore, donc la population ajoutee n'est pas une liste de fantomes.
MUTATION_PROOF = "test_extra_hatches_still_exist"

SENTINEL = "ZZRENDERHATCH"

#: Plancher de non-vacuité. Mesuré le 2026-08-18 : 5 échappatoires
#: découvertes (``table.empty``, ``table.head_render``,
#: ``datatable.empty``, ``select.render``, ``combobox.render``) plus la
#: 1 de :data:`EXTRA`.
#:
#: ⚠️ Il valait 5 pendant une demi-journée : ``breadcrumb.render`` en
#: faisait partie, puis la règle ``COLLECTION_OWNER`` a montré que
#: breadcrumb ne devait PAS avoir de rappel (l'auteur possède sa boucle,
#: donc il prend des enfants). Un plancher qui baisse doit dire pourquoi
#: — celui-ci le dit.
_FLOOR = 6


#: Combien de fois le rappel a été appelé depuis le dernier ``_reset``.
#: Mesuré plutôt que supposé : une échappatoire de COLLECTION est appelée
#: une fois PAR ITEM (``breadcrumb.render`` sur trois segments = trois
#: appels), donc « la sentinelle apparaît une fois » serait faux. Ce qui
#: est invariant, c'est **une occurrence par appel** — au-delà, le
#: Component a rendu deux fois.
_CALLS = [0]


def _callback(*_args, **_kwargs):
    """Le rappel que la gate injecte partout. Arité variable exprès : les
    échappatoires n'ont pas la même (``table.empty`` ne prend aucun
    argument, ``head_render`` un, ``breadcrumb.render`` et
    ``column.render`` deux)."""
    _CALLS[0] += 1
    return ui.text(SENTINEL)


def _build_table(hatch):
    from bretzel.components.data.table.table import column

    return ui.table(
        columns=[column("nom", label="Nom")],
        rows=[{"nom": "a"}],
        **{hatch: _callback},
    )


def _build_table_empty(hatch):
    """``empty=`` n'est atteint que par une table VIDE — la construire
    avec des lignes rendrait la gate vacante sur cette entrée."""
    from bretzel.components.data.table.table import column

    return ui.table(
        columns=[column("nom", label="Nom")], rows=[], **{hatch: _callback}
    )


def _build_datatable_empty(hatch):
    from bretzel.components import DatatableState
    from bretzel.components.data.table.table import column

    class _Probe(DatatableState):
        pass

    return ui.datatable(
        state=_Probe,
        columns=[column("nom", label="Nom")],
        rows=[],
        search=False,
        **{hatch: _callback},
    )


#: Comment bâtir un composant dans l'état où son échappatoire est
#: RÉELLEMENT atteinte. Sans ça, ``table.empty`` sur une table qui a des
#: lignes n'est jamais appelé, et la gate resterait verte sur une
#: échappatoire débranchée.
BUILD = {
    ("table", "empty"): _build_table_empty,
    ("table", "head_render"): _build_table,
    ("datatable", "empty"): _build_datatable_empty,
    # Sans ``options=``, le rappel d'un picker n'est JAMAIS appelé — la
    # découverte concluait « pas une échappatoire de contenu » et les
    # deux sortaient du balayage sans un mot. Mesuré le 2026-08-18, en
    # les câblant.
    ("select", "render"): lambda hatch: ui.select(
        options=[("a", "Alpha")], **{hatch: _callback}
    ),
    ("combobox", "render"): lambda hatch: ui.combobox(
        options=[("a", "Alpha")], **{hatch: _callback}
    ),
}


def _build_column_render():
    """``ui.column(render=)`` — l'échappatoire qui vit sur une dataclass."""
    from bretzel.components.data.table.table import column

    return ui.table(
        columns=[column("nom", label="Nom", render=_callback)],
        rows=[{"nom": "a"}],
    )


#: Les échappatoires qu'aucune introspection de COMPOSANT ne peut voir,
#: parce qu'elles vivent ailleurs que sur une signature de composant.
EXTRA = {"column.render": _build_column_render}


def _construct(name: str, param: str):
    """Bâtit le composant ``name`` avec son échappatoire ``param`` câblée."""
    builder = BUILD.get((name, param))
    if builder is not None:
        return builder(param)
    cls = next(c for c in public_component_classes() if ui_name_of(c) == name)
    return cls(**{param: _callback})


#: Les couples ``ui_name.param`` typés ``Callable`` que la sonde ne
#: construit pas, avec leur raison. Mesuré le 2026-08-19 en remplaçant
#: l'``except`` par un enregistrement : deux, et les deux sont
#: définitifs — ``datatable`` exige un ``state=``, donc la sonde ne peut
#: pas le monter avec un rappel seul.
_CANNOT_PROBE: dict[str, str] = {
    "datatable.rows": "datatable exige un `state=` — la sonde ne le monte pas",
    "datatable.row_key": "idem",
}


def callable_params() -> list[tuple[str, str]]:
    """``(ui_name, param)`` pour tout paramètre typé ``Callable`` qui
    n'est pas un handler d'event."""
    out: list[tuple[str, str]] = []
    for cls in public_component_classes():
        name = ui_name_of(cls)
        for p in describe_component(name, cls).params:
            if "Callable" in p.type_label and not p.name.startswith("on_"):
                out.append((name, p.name))
    return out


def probe_abstentions() -> dict[str, str]:
    """``ui_name.param -> type d'erreur`` pour ce que la sonde ne monte pas."""
    out: dict[str, str] = {}
    for name, param in callable_params():
        try:
            with render_isolated():
                serialize(_construct(name, param).render())
        except Exception as exc:
            out[f"{name}.{param}"] = type(exc).__name__
    return out


def _discover() -> list[str]:
    """Les ``ui_name.param`` dont le retour du rappel atterrit dans le
    CONTENU du DOM. Empirique — cf. l'en-tête du module sur les 3 faux
    positifs qu'une lecture d'annotation ramène."""
    found: list[str] = []
    for cls in public_component_classes():
        name = ui_name_of(cls)
        for p in describe_component(name, cls).params:
            if "Callable" not in p.type_label or p.name.startswith("on_"):
                continue
            try:
                with render_isolated():
                    html = serialize(_construct(name, p.name).render())
            except Exception:
                # Un ``Callable`` qui n'est pas une échappatoire de
                # contenu (``datatable.rows`` est une source de données)
                # refuse ce rappel — il sort de la population par
                # DÉFINITION, pas par accident de balayage. Le plancher
                # est ce qui protège du cas où cette branche avalerait
                # tout.
                continue
            if in_text_content(html, SENTINEL):
                found.append(f"{name}.{p.name}")
    return found


_ALL = _discover() + sorted(EXTRA)


def _render(label: str) -> tuple[str, list[str], int]:
    """Rend l'échappatoire ``label`` → (html, orphelins, nb d'appels)."""
    _CALLS[0] = 0
    with render_isolated():
        make = EXTRA.get(label)
        built = make() if make else _construct(*label.split(".", 1))
        html = serialize(built.render())
        roots = [type(r).__name__ for r in current_context().root_children]
    # Le composant sous test s'auto-enregistre lui aussi : c'est le
    # premier, et il est légitime. Tout ce qui SUIT est un orphelin.
    return html, roots[1:], _CALLS[0]


@pytest.mark.parametrize("label", _ALL)
def test_render_hatch_reaches_the_dom_once(label: str) -> None:
    html, orphans, calls = _render(label)
    count = html.count(SENTINEL)

    assert calls >= 1, (
        f"{label} : le rappel n'a JAMAIS été appelé — la gate ne mesure "
        f"rien. Le builder doit bâtir le composant dans l'état où son "
        f"échappatoire est atteinte (une table VIDE pour ``empty=``)."
    )
    assert count >= 1, (
        f"{label} : le retour du rappel n'atteint pas le DOM (appelé "
        f"{calls} fois). Une échappatoire `render=` doit poser ce que "
        f"l'auteur a rendu — passe-le par ``coerce_children`` "
        f"(``bretzel.components.base``)."
    )
    assert count == calls, (
        f"{label} : le rappel a été appelé {calls} fois et son retour "
        f"apparaît {count} fois — il faut UNE occurrence par appel. Un "
        f"Component "
        f"bâti dans le corps du rappel s'auto-enregistre auprès du parent "
        f"actif ; sans détachement il rend une fois à sa place ET une fois "
        f"en frère. ``coerce_children`` fait les deux moitiés — ne rappelle "
        f"pas ``.render()`` à la main."
    )
    assert not orphans, (
        f"{label} : le rappel a laissé {orphans} à la racine du contexte. "
        f"Invisible tant que le composant rend en place, VISIBLE dès qu'il "
        f"rend détaché (``serialize_html``, snapshot, sous-arbre extrait) — "
        f"cf. ``test_render_never_orphans``, même mécanisme, autre "
        f"population."
    )


def test_the_wrapper_survives_the_hatch() -> None:
    """Le composant garde son enveloppe — le point du contrat qu'un
    balayage générique ne peut pas vérifier, donc épinglé ici.

    ``ui.column(render=)`` remplace le CONTENU d'une cellule ; le
    ``<td>`` et ses classes restent au composant. Si le rappel avalait
    l'enveloppe, l'auteur perdrait l'alignement, la largeur et le
    comportement de tri en posant une simple icône."""
    from bretzel.components.data.table.table import column

    with render_isolated():
        html = serialize(
            ui.table(
                columns=[column("nom", label="Nom", render=_callback)],
                rows=[{"nom": "a"}],
            ).render()
        )
    assert "<td" in html, (
        "`render=` a mangé la cellule — l'enveloppe appartient au "
        "composant, le rappel n'en remplace que le CORPS."
    )
    assert SENTINEL in html.split("<td", 1)[1], (
        "le retour du rappel n'est pas DANS la cellule."
    )


def test_extra_hatches_still_exist() -> None:
    """Re-mesure :data:`EXTRA` à chaque run. Une échappatoire déclarée à
    la main qu'on ne re-vérifie pas est une gate qui a déjà perdu : le
    jour où ``ui.column`` perd son ``render=``, l'entrée doit rougir, pas
    se taire."""
    from bretzel.components.data.table.table import Column

    assert "render" in Column.__dataclass_fields__, (
        "``ui.column(render=)`` a disparu — retire-le d'EXTRA, ou répare."
    )


def test_population_is_not_vacuous() -> None:
    """Sans plancher, un ``describe_component`` cassé ou un ``BUILD``
    périmé viderait la population et la gate resterait verte en n'ayant
    rien vérifié."""
    assert len(_ALL) >= _FLOOR, (
        f"la gate n'exerce plus que {len(_ALL)} échappatoires (plancher "
        f"{_FLOOR}, 5 mesurées le 2026-08-18) : {_ALL}. Vérifie la "
        f"découverte — ne baisse pas le plancher."
    )


def test_the_abstentions_are_declared() -> None:
    """Ce que la sonde ne monte pas est NOMMÉ, pas compté.

    Le commentaire de ``_discover`` disait déjà que ces refus sont
    définitionnels — un ``Callable`` qui n'est pas une échappatoire de
    contenu refuse le rappel. Il avait raison, et il ne le VÉRIFIAIT
    pas : un composant qui cesse de se monter tomberait dans la même
    branche et passerait pour un refus de principe.
    """
    measured = probe_abstentions()
    surprise = sorted(set(measured) - set(_CANNOT_PROBE))
    assert not surprise, (
        f"Ces paramètres typés `Callable` ne se montent plus sous la sonde, "
        f"et personne ne l'avait déclaré : "
        f"{ {k: measured[k] for k in surprise} }. Ils sortent du balayage "
        f"EN SILENCE — répare, ou déclare AVEC la raison."
    )
    stale = sorted(set(_CANNOT_PROBE) - set(measured))
    assert not stale, (
        f"{stale} se monte(nt) de nouveau — retire l'entrée de `_CANNOT_PROBE`."
    )
