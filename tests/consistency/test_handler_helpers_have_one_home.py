"""Gate : un helper de handler a EXACTEMENT un point d'accès, et ``ui``
ne contient que du rendu.

Les deux moitiés d'une même frontière
--------------------------------------
``ui.*`` s'appelle depuis un corps de rendu (``@page`` / ``@layout`` /
``@refreshable``) ; ``bretzel.*`` s'appelle depuis un handler. C'est un
critère **mécanique**, donc vérifiable — contrairement à « ``ui``, c'est
ce qui se rend », qui était la justification écrite et que
``ui.notification`` démentait dans son propre commentaire (« a
fire-and-forget server-side helper, **not a component** »).

L'état mesuré le 2026-08-14, avant ce fichier :

===============  ==========================================================
``abort``        **trois** points d'accès — ``bretzel.abort``,
                 ``ui.abort`` (corps RECOPIÉ, ``is`` faux entre les deux)
                 et ``Bretzel.abort`` (``@staticmethod``, zéro appelant)
``notification`` un — ``ui.notification``
``redirect``     un — ``bretzel.redirect``
``background``   un, mais en **méthode d'instance** ``app.background``,
                 alors qu'il n'utilise pas ``self``
``idempotent``   un, en fonction module
===============  ==========================================================

Cinq helpers de même nature, quatre formes. Et les ``examples/`` — le code
de référence — n'utilisaient aucun des points documentés : ils faisaient
``from bretzel.server import abort``, c'est-à-dire l'interne.

Pourquoi ça compte au-delà de l'esthétique : ``ui.abort`` existait *parce
que* le DAG interdit ``components → server``. Le doublon n'était pas un
oubli, c'était un contournement — donc il se serait reproduit à chaque
helper suivant. Sortir ``abort`` de ``ui`` supprime le contournement avec
le doublon.

Ce qu'elle ne peut PAS attraper
--------------------------------
Un helper qui n'est exposé nulle part (donc introuvable) : elle compte des
points d'accès, pas des besoins. Et elle ne lit pas le *corps* des
fonctions — deux points d'accès qui seraient le même objet passeraient ici
et seraient attrapés par ``test_one_name_one_object``.
"""

from __future__ import annotations

import inspect

import pytest

from bretzel.components.base.component import Component

#: Pas de détecteur à rendre aveugle — cf.
#: ``test_a_prohibition_gate_is_mutation_tested``.
MUTATION_NOT_APPLICABLE = (
    "compare des ENSEMBLES de symboles exportés à une règle mécanique "
    "(rendu / handler) ; une comparaison d'ensembles ne cesse pas de "
    "reconnaître"
)

#: Les helpers appelables depuis un handler. Un nom ajouté ici est un nom
#: gardé — c'est le seul endroit à toucher.
_HANDLER_HELPERS = ("abort", "redirect", "background", "idempotent")


def _access_points(name: str) -> list[str]:
    """Tous les endroits publics d'où ``name`` est atteignable."""
    import bretzel
    from bretzel.components import ui

    found = []
    if name in getattr(bretzel, "__all__", ()):
        found.append(f"bretzel.{name}")
    if hasattr(type(ui), name):
        found.append(f"ui.{name}")
    if hasattr(bretzel.Bretzel, name):
        found.append(f"Bretzel.{name}")
    return found


@pytest.mark.parametrize("name", _HANDLER_HELPERS)
def test_helper_has_exactly_one_access_point(name: str) -> None:
    points = _access_points(name)
    assert points == [f"bretzel.{name}"], (
        f"{name!r} est atteignable depuis {points} — attendu "
        f"['bretzel.{name}'] et rien d'autre. Un helper appelable depuis "
        f"un handler a UN point d'accès : la fonction sur ``bretzel``. "
        f"S'il t'en faut un second parce que le DAG bloque, c'est le DAG "
        f"qu'il faut respecter autrement, pas le helper qu'il faut "
        f"recopier — c'est ce qui a produit ``ui.abort``."
    )


def test_no_handler_helper_survives_on_ui() -> None:
    """``ui`` ne porte aucun helper de handler — la moitié « rendu »."""
    from bretzel.components import ui

    leaked = [n for n in _HANDLER_HELPERS if hasattr(type(ui), n)]
    assert not leaked, (
        f"{leaked} sur ``ui`` : ce namespace ne contient que ce qui "
        f"s'appelle depuis un corps de rendu. Un ``abort`` produit un "
        f"statut HTTP, pas des pixels."
    )


def test_ui_entries_are_render_callables() -> None:
    """Toute entrée de ``ui`` est un composant OU une fonction de rendu.

    Le critère n'est PAS « retourne un ``Node`` » : ``ui.notification``
    produit un toast dont le runtime auto-monte le DOM, les ``*_each``
    produisent des clés d'itération, ``ui.column`` décrit une colonne.
    Ce n'est pas non plus « a un effet visible à l'écran », comme cette
    ligne l'a dit jusqu'au 2026-08-27 : ``ui.pending`` ne peint rien du
    tout. C'est une **source réactive** — une valeur qu'une AUTRE prop
    consomme (``loading=`` / ``disabled=`` / ``visible=``). La catégorie
    est nommée ici plutôt que plaidée dans l'entrée d'allowlist, sinon
    la deuxième source réactive livrée s'ajouterait comme une exception
    de plus à une règle qu'aucune des deux ne satisfait.

    Ce qui reste mécanique, et qui EST le critère : **d'où on
    l'appelle**. Un corps de rendu, pas un handler.
    """
    from bretzel.components import ui

    non_component = {}
    for name in dir(type(ui)):
        if name.startswith("_"):
            continue
        value = getattr(ui, name)
        if inspect.isclass(value) and issubclass(value, Component):
            continue
        non_component[name] = value

    unexpected = set(non_component) - _EXPECTED_UI_FUNCTIONS
    assert not unexpected, (
        f"Entrées non-composant inattendues sur ``ui`` : {sorted(unexpected)}. "
        f"Si elles s'appellent depuis un corps de rendu, ajoute-les à "
        f"``_EXPECTED_UI_FUNCTIONS`` en disant pourquoi. Si elles "
        f"s'appellent depuis un handler, leur place est sur ``bretzel``."
    )
    missing = _EXPECTED_UI_FUNCTIONS - set(non_component)
    assert not missing, (
        f"{sorted(missing)} n'est plus sur ``ui`` — mets à jour la liste "
        f"plutôt que de la laisser pourrir (elle deviendrait une allowlist "
        f"vide de sens, la pathologie que ce dossier traque)."
    )


#: Les entrées de ``ui`` qui ne sont pas des sous-classes de ``Component``,
#: avec la raison de leur présence. Égalité stricte des deux côtés.
_EXPECTED_UI_FUNCTIONS = frozenset({
    "notification",   # produit un toast — le runtime auto-monte le DOM
    "pending",        # source réactive « action en vol » : elle se BINDE
                      # sur une prop (loading=/disabled=/visible=), donc
                      # elle s'écrit dans le rendu, pas dans le handler
    "column",         # descripteur de colonne, consommé par ui.table
    "node",           # les deux descripteurs du graphe, consommés par
    "edge",           # ui.diagram — même nature que ``column``, et pour
                      # la même raison : un graphe ne s'imbrique pas, donc
                      # aucun bloc ``with`` ne peut décrire une arête
    "track",          # descripteur de piste de sous-titres, consommé par
                      # ui.video — même nature que ``column`` : il se
                      # construit dans le rendu, jamais dans un handler
    "each",           # les six ci-dessous poussent des clés d'itération
    "drag_each",
    "filter_each",
    "limit_each",
    "paginate_each",
    "show_more",
})


def test_sweep_is_not_vacuous() -> None:
    """Plancher : le balayage voit un vrai catalogue et de vrais helpers.

    Ancré sur la DÉCOUVERTE. Sans ça, un ``ui`` vidé par un refactor
    d'import ferait passer ``test_no_handler_helper_survives_on_ui`` au
    vert en ne regardant rien.
    """
    from bretzel.components import ui

    entries = [n for n in dir(type(ui)) if not n.startswith("_")]
    assert len(entries) >= 90, (
        f"Seulement {len(entries)} entrées sur ``ui`` (>= 90 attendues, "
        f"105 au 2026-08-15) — le namespace ne se charge probablement plus."
    )
    assert _access_points("abort"), (
        "``abort`` n'est atteignable de nulle part — le balayage lit-il "
        "encore ``bretzel.__all__`` ?"
    )
