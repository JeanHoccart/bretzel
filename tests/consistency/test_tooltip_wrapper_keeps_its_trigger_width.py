"""Gate : envelopper un composant dans un tooltip ne doit pas le rétrécir.

``tooltip=`` est un modificateur **universel** : n'importe quel composant
peut le recevoir. Le wrapper que ça pose a pour racine
``inline-block w-fit h-fit`` — correct pour une pastille, désastreux pour
un conteneur, qui s'effondre alors sur la largeur de son plus long enfant.

``trigger_is_full_width`` arbitre. Jusqu'au 2026-08-10 elle répondait par
« la racine contient-elle la chaîne ``w-full`` ? » — un signal que **le
dépôt déclarait déjà non fiable ailleurs** : la docstring de
``test_input_root_fills_width`` dit mot pour mot « radio_group / form fill
without a literal ``w-full``, so we forbid the shrink tokens rather than
require ``w-full`` ». Les deux composants qu'elle cite en exemple étaient
précisément parmi les cassés.

**Population mesurée avant correction : 8 composants livrés** rendaient un
tooltip qui les rétrécissait — ``grid``, ``vstack``, ``hstack``, ``flex``,
``form``, ``radio_group``, ``tabs``, plus ``dropzone`` qui l'a fait
remonter. Trouvé par l'utilisateur en regardant une page, pas par un test.

Deux signaux gouvernent la réponse, et il faut les DEUX :

1. la classe — un token de largeur intrinsèque (``inline-*``, ``w-fit``,
   ``w-max``, ``w-<n>``, ``w-[…]``) veut dire « je me dimensionne à mon
   contenu » ;
2. **la balise** — ``ui.text`` rend un ``<span>`` sans aucun token : il
   hugge parce qu'il est inline PAR NATURE. Juger la seule classe le
   classait « remplit », et son tooltip s'ancrait sur la ligne entière au
   lieu du mot.

Auto-évolutive : tout composant public doit figurer dans ``_EXPECTED``.
Un composant neuf que personne n'a classé fait rougir le test de
complétude — ce qui force la question « est-ce que ma racine remplit sa
cellule ? » à la revue, exactement celle que ``dropzone`` avait ratée.
"""

from __future__ import annotations

import re

import pytest

from bretzel.components import ui
from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from tests.consistency._discovery import (
    bare_kwargs,
    public_component_classes,
    ui_name_of,
)

#: Preuve de morsure : re-mesure la table de classification : une entree qui ne designe plus
#: un composant reel doit sortir, sinon la gate juge un fantome et laisse
#: le vrai composant non classe.
MUTATION_PROOF = "test_every_hug_entry_is_a_real_component"

#: ``ui_name -> classe`` — pour retrouver ce que le socle exige d'un
#: composant qu'on ne connaît que par son nom de fabrique.
_CLASS_BY_UI_NAME = {
    ui_name_of(cls): cls for cls in public_component_classes()
}

#: ``HUG`` = le wrapper doit rester ``w-fit`` (pastilles, contrôles
#: inline, mots). ``FILL`` = il doit s'étendre en ``block w-full``.
#: Chaque entrée est vérifiée sur la racine de son thème, pas supposée.
_HUG = {
    # Racine ``inline-flex`` / ``inline-block`` explicite.
    "button", "icon_button", "badge", "avatar", "spinner", "icon",
    "checkbox", "switch", "radio", "navbar_item", "sparkline",
    "toggle_group",
    # ``sidebar_trigger`` rend un ``ui.icon_button`` — même boîte, donc
    # même verdict que lui, deux lignes plus haut.
    "sidebar_trigger",
    # Les ancrés : leur racine EST le ``w-fit`` qui doit hugger son
    # déclencheur — un tooltip sur un dropdown enveloppe le déclencheur du
    # dropdown, pas son panneau.
    "popover", "dropdown", "tooltip",
    # Inline par BALISE, sans le déclarer en classe.
    "text", "link", "tab",
    # Largeur fixe déclarée (``w-<n>``) : une barre latérale ne remplit
    # pas, elle impose sa colonne.
    "sidebar",
    # Le calendrier ne hugge plus son CONTENU depuis le 2026-08-25 : sa
    # largeur vient de sa table de tailles (``w-56`` … ``w-97``). Il
    # reste ici parce que la question posée est « le wrapper doit-il
    # coller à la boîte du déclencheur ? » — et une largeur définie y
    # répond oui aussi bien qu'un ``w-fit``, en mieux : elle ne dépend
    # plus du nom du mois affiché.
    "calendar",
    # ── Ajoutés le 2026-08-25, et ce n'est pas un choix de goût ──────
    # Leur wrapper est ``w-fit max-w-full``, donc ils huggent — mais
    # ``_class_decides_width`` testait ``"w-full" in cls``, une
    # SOUS-CHAÎNE, et ``max-w-full`` la contient. Les deux étaient donc
    # classés « remplit » et recevaient une enveloppe pleine largeur :
    # le panneau du tooltip s'ancrait sur la rangée, pas sur le
    # graphique. Le test est maintenant un MOT (``_FILL_WIDTH_RE``), et
    # ces deux-là retrouvent leur vraie réponse.
    "line_chart", "scatter_chart",
}


def _public_components() -> list[str]:
    """Les entrées de ``ui`` qui sont des classes de composant."""
    from bretzel.components.base import Component

    return sorted(
        name
        for name in dir(ui)
        if not name.startswith("_")
        and isinstance(getattr(ui, name, None), type)
        and issubclass(getattr(ui, name), Component)
    )


def _bare_kwargs_for(name: str) -> dict[str, object]:
    """Le mot obligatoire du composant, pris au socle PARTAGÉ.

    Sans lui, ``ui.image`` / ``ui.iframe`` / ``ui.meta_tag`` / ``ui.title``
    échouaient à la construction et sortaient du balayage en silence —
    alors que ``_BARE_ARGS`` les connaît.
    """
    cls = _CLASS_BY_UI_NAME.get(name)
    return bare_kwargs(cls) if cls is not None else {}


def _wrapper_class(name: str) -> str | None:
    """La classe de la racine rendue avec ``tooltip=``.

    ``None`` = hors population, pour deux raisons distinctes :

    - le composant ne s'instancie pas nu (il exige des arguments) ;
    - **il ne rend rien seul.** ``ui.step`` sort ``<span></span>`` : c'est
      un sous-composant de DÉCLARATION, consommé par son ``Stepper``
      parent. Il n'y a aucune boîte de déclencheur à mesurer, donc le
      classer « hugge » ou « remplit » serait mesurer du bruit et figer
      une réponse à une question qui ne se pose pas.
    """
    factory = getattr(ui, name)
    kwargs = _bare_kwargs_for(name)
    try:
        with render_isolated():
            bare = serialize(factory(**kwargs).render())
            html = serialize(factory(**kwargs, tooltip="t").render())
    except Exception:
        # Abstention de CONSTRUCTION — déclarée dans ``_CANNOT_BUILD``,
        # sinon un composant sortirait du balayage sans un mot.
        return None
    if not re.search(r"class=\"[^\"]+\"", bare):
        return None
    match = re.match(r"<\w+[^>]*class=\"([^\"]*)\"", html)
    return (match.group(1) if match else "").strip()


_MEASURED: dict[str, str] = {
    name: cls
    for name in _public_components()
    if (cls := _wrapper_class(name)) is not None
}


def test_the_sweep_is_not_vacuous() -> None:
    """Plancher : sans lui, un ``ui`` vide ou un rendu qui lève partout
    rendrait la table vide et TOUS les cas ci-dessous passeraient à vide."""
    assert len(_MEASURED) > 25, (
        f"seulement {len(_MEASURED)} composants ont pu être rendus avec un "
        f"tooltip — le balayage est cassé, pas le catalogue"
    )
    assert any("w-fit" in cls for cls in _MEASURED.values()), (
        "aucun wrapper ne reste w-fit : le mécanisme mesuré n'existe plus, "
        "et la gate ne compare plus rien"
    )
    assert any("w-fit" not in cls for cls in _MEASURED.values()), (
        "aucun wrapper ne s'étend : `expand_fit_wrapper` ne s'applique "
        "jamais, donc la moitié FILL de la gate est morte"
    )


@pytest.mark.parametrize("name", sorted(_MEASURED))
def test_the_wrapper_matches_the_trigger_box(name: str) -> None:
    hugs = "w-fit" in _MEASURED[name]
    if name in _HUG:
        assert hugs, (
            f"{name} : le wrapper de tooltip s'étend en pleine largeur alors "
            f"que le composant se dimensionne à son contenu — le panneau "
            f"s'ancrera sur toute la ligne au lieu de l'élément."
        )
    else:
        assert not hugs, (
            f"{name} : le wrapper de tooltip reste w-fit, donc "
            f"`ui.{name}(tooltip=…)` sort RÉTRÉCI à la largeur de son "
            f"contenu alors que sans tooltip il remplit son parent. C'est "
            f"le défaut mesuré sur 8 composants le 2026-08-10.\n"
            f"  Classe rendue : {_MEASURED[name]!r}\n"
            f"  Si {name} doit vraiment hugger, ajoute-le à _HUG."
        )


def test_every_hug_entry_is_a_real_component() -> None:
    """Une entrée de ``_HUG`` qui ne correspond à rien est du bruit que la
    prochaine lecture prendra pour une décision."""
    unknown = sorted(set(_HUG) - set(_public_components()))
    assert not unknown, (
        f"_HUG nomme des composants qui n'existent pas : {unknown} — "
        f"retire-les, ou ce sont des exemptions qui ne protègent rien."
    )


#: Ce que le balayage ne construit pas, avec sa raison. Mesuré le
#: 2026-08-19 en remplaçant l'``except`` par un enregistrement.
#:
#: ⚠️ Avant l'usage de ``bare_kwargs``, ils étaient SEPT : les quatre
#: composants qui exigent un mot obligatoire (``image``, ``iframe``,
#: ``meta_tag``, ``title``) y tombaient aussi, alors que le socle sait
#: les bâtir.
_CANNOT_BUILD: dict[str, str] = {
    # `datatable` est SORTI de cette liste le 2026-09-07 : en déclarant
    # son `item_click`, il est entré dans le recensement de
    # `wired_couples`, et `bare_kwargs` a appris à le bâtir (état
    # sonde, une colonne, deux lignes). Il n'y a plus de raison de
    # s'en abstenir.
    "toggle_button": "ne se rend que dans le ``with`` d'un ToggleGroup",
    "fragment": "conteneur pur — pas de racine à mesurer",
    # Ces deux-là REFUSENT les kwargs universels, ``tooltip=`` compris :
    # ce sont des composants à effet de bord (ils poussent dans le
    # ``<head>``), pas des boîtes. Il n'y a donc pas de wrapper à mesurer.
    "meta_tag": "refuse les kwargs universels — composant à effet de bord",
    "title": "idem",
}


def build_abstentions() -> dict[str, str]:
    """``ui_name -> type d'erreur`` pour ce que le balayage ne monte pas."""
    out: dict[str, str] = {}
    for name in _public_components():
        factory = getattr(ui, name)
        kwargs = _bare_kwargs_for(name)
        try:
            with render_isolated():
                serialize(factory(**kwargs).render())
                serialize(factory(**kwargs, tooltip="t").render())
        except Exception as exc:
            out[name] = type(exc).__name__
    return out


def test_the_abstentions_are_declared() -> None:
    """Ce que le balayage ne monte pas est NOMMÉ, pas compté.

    Le plancher au-dessus compte la population MESURÉE ; il a de la
    marge, donc un composant qui cesse de se construire n'y ferait rien
    rougir. C'est ici qu'il se voit, par son nom.
    """
    measured = build_abstentions()
    surprise = sorted(set(measured) - set(_CANNOT_BUILD))
    assert not surprise, (
        f"{ {k: measured[k] for k in surprise} } ne se monte(nt) plus : "
        f"ils sortent du balayage EN SILENCE, et la règle « le wrapper de "
        f"tooltip garde la boîte de son déclencheur » ne les juge plus."
    )
    stale = sorted(set(_CANNOT_BUILD) - set(measured))
    assert not stale, (
        f"{stale} se monte(nt) de nouveau — retire l'entrée."
    )
