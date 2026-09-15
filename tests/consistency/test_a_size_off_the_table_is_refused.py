"""Gate : ``size=`` / ``variant=`` hors table LÈVE, au lieu de se taire.

Le défaut qu'elle ferme
-----------------------
Une faute de frappe sur les deux props les plus fréquentes du catalogue
ne levait pas, ne s'affichait pas, et ne se voyait pas en revue.
Mesuré le 2026-09-06, avant le refus : sur les **57** couples
(composant, axe) portant ``size`` ou ``variant``, **56 rendaient quand
même** — et pas de la même façon ::

    ui.button(size="zzz")  → perd h-10, px-4, gap-2, text-sm
                              (le bouton rend SANS AUCUNE taille)
    ui.badge(size="zzz")   → retombe sur `sm`, une taille plus bas

Le dépôt appliquait pourtant déjà la règle et l'écrivait :
``bretzel describe`` dit du ``grow=`` de ``ui.flex`` « table FERMÉE, et une
valeur hors table LÈVE : elle rendrait la chaîne vide, donc un kwarg
mort ». Cette gate étend la phrase aux deux props qui la méritaient le
plus.

Pourquoi elle regarde les DEUX versants
---------------------------------------
Parce que le premier jet du refus ne regardait que le versant illicite,
et qu'il a coûté **198 tests rouges**. Le catalogue imbrique sa table
dans les deux sens, et rien dans sa structure ne dit lequel ::

    sizes = {"sm": "h-8"}                        # plate
    sizes = {"input_frame": {"md": "h-10"}}      # date_picker : slot → palier
    sizes = {"md": {"root": "h-10"}}             # badge : palier → slot

Lire une seule des deux formes rendait des noms de SLOTS en guise de
paliers — donc un refus de ``size="md"`` sur 37 composants, avec un
versant illicite parfaitement vert. D'où le second test : **chaque
palier déclaré doit rendre**. C'est lui qui mesure le taux de faux
positifs sur le corpus réel, et c'est le seul des deux qu'on ne peut
pas satisfaire par accident.

Ce que la gate NE dit pas
-------------------------
« Cette valeur aurait dû exister. » Elle ne juge pas le contenu des
tables, seulement l'écart entre ce qu'un thème DÉCLARE et ce qu'un
composant ACCEPTE.
"""

from __future__ import annotations

import inspect

import pytest

from bretzel.components.base._wiring import declared_steps
from bretzel.components.base.attrs import (
    ComponentDefinitionError,
    ComponentUsageError,
)
from tests.consistency._discovery import (
    public_component_classes,
    rendered_html_of,
    ui_name_of,
)

#: Une valeur qu'aucune table ne peut porter — le versant illicite.
OFF_THE_TABLE = "zzz-inexistant"

#: Refuser plus TÔT reste refuser. `ui.file_upload` valide son
#: `variant` dans son `__init__` et lève un `ComponentDefinitionError`
#: nommé : la gate mesure le REFUS, pas le point où il tombe.
REFUSALS = (ComponentUsageError, ComponentDefinitionError)

#: Les couples qui NE refusent pas, et pourquoi. **VIDE depuis le
#: 2026-09-07** — 57 couples sur 57 refusent.
#:
#: ⚠️ Elle en portait quatre, avec une raison écrite qui décrivait la
#: limite du DÉTECTEUR comme si c'était une propriété des composants :
#: « leur prop nomme un mode de tracé, elle n'indexe pas le thème »,
#: « sans palier par défaut on ne sait pas lequel des deux niveaux
#: porte les paliers ». Les deux constats étaient exacts — et aucun ne
#: rendait le silence acceptable. Mesuré : ``bar_chart(variant="zzz")``
#: rendait à l'identique de ``"grouped"``, et ``radio(size="zzz")``
#: rendait **sans aucune taille**, soit exactement le mode d'échec pour
#: lequel cette gate existe.
#:
#: Ce qui manquait n'était pas une exception, c'était une SOURCE :
#: ``reactive_prop(steps=)`` déclare les valeurs légales quand le thème
#: ne peut pas les dire. Trois des quatre y désignent la table qu'elles
#: rendent déjà (``tuple(RADIO_THEME["sizes"])``) plutôt que de la
#: retaper.
#:
#: ``radio_group.size`` en faisait partie et n'y est PAS revenu : le
#: groupe n'a pas de table à lui, mais il transmet aux enfants, et
#: l'enfant refuse la taille EFFECTIVE au rendu (``Radio.render``) —
#: ``ui.radio_group(size="zzz")`` lève donc par son premier
#: ``ui.radio``. Ce que refuser « à travers l'enfant » vaut dépend de
#: la construction : un groupe VIDE ne lit aucune table. ``CONSTRUCT``
#: en bâtit un avec son enfant, donc la gate le juge pour de bon.
#:
#: Pourquoi ne pas déclarer l'ensemble sur la prop du groupe : il
#: faudrait y figer les paliers du RADIO au corps de la classe, et
#: ``test_theme_reads_are_resolved`` l'interdit à raison — un
#: ``Theme(components={"radio": …})`` de l'app remplace ces paliers, et
#: une liste figée refuserait alors une valeur juste.
ABSTENTIONS: frozenset[str] = frozenset()


def axes() -> list[tuple[type, str, str]]:
    """Les couples (classe, prop, clé de table) du catalogue."""
    found = []
    for cls in sorted(public_component_classes(), key=ui_name_of):
        params = inspect.signature(cls.__init__).parameters
        for prop, table_key in (("size", "sizes"), ("variant", "variants")):
            if prop in params:
                found.append((cls, prop, table_key))
    return found


def steps_of(cls: type, prop: str, table_key: str) -> frozenset[str]:
    anchor = getattr(cls.__reactive_props__.get(prop), "default", None)
    table = (getattr(cls, "THEME", {}) or {}).get(table_key, {})
    return declared_steps(table, anchor=anchor)


# ── Les planchers ─────────────────────────────────────────────────────


def test_the_sweep_finds_the_two_props() -> None:
    """Sans lui, une signature renommée viderait le balayage en
    silence et laisserait la gate verte sur un catalogue non gardé."""
    found = axes()
    assert len(found) >= 50, (
        f"seulement {len(found)} couple(s) (composant, axe) trouvé(s) — "
        f"il y en avait 57 le 2026-09-06. La lecture des signatures est "
        f"cassée, ou `size`/`variant` ont changé de nom."
    )


def test_the_reader_finds_real_steps() -> None:
    """Second plancher : les tables sont LUES.

    Un ``declared_steps`` rendant toujours l'ensemble vide rendrait le
    refus muet partout — et les deux tests ci-dessous verts.
    """
    steps = {
        step
        for cls, prop, key in axes()
        for step in steps_of(cls, prop, key)
    }
    assert len(steps) >= 20, (
        f"seulement {len(steps)} palier(s) distinct(s) lu(s) dans tout "
        f"le catalogue : {sorted(steps)}. Le lecteur de table est cassé."
    )


# ── Les deux versants ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("cls", "prop", "table_key"), axes(), ids=lambda v: getattr(v, "__name__", v)
)
def test_an_off_table_value_is_refused(
    cls: type, prop: str, table_key: str
) -> None:
    """Versant ILLICITE : une valeur inventée lève."""
    couple = f"{ui_name_of(cls)}.{prop}"
    try:
        html = rendered_html_of(cls, prop=prop, value=OFF_THE_TABLE)
    except REFUSALS:
        assert couple not in ABSTENTIONS, (
            f"`{couple}` refuse désormais une valeur hors table, mais "
            f"reste listé dans ABSTENTIONS. Retire-le : une liste de "
            f"dettes qui ment ne protège plus rien."
        )
        return
    if html is None:  # le banc ne peut pas fabriquer son contexte
        return
    assert couple in ABSTENTIONS, (
        f"`ui.{ui_name_of(cls)}({prop}={OFF_THE_TABLE!r})` rend sans un "
        f"mot. Une valeur hors table ne lève pas d'elle-même : elle "
        f"rend la chaîne vide, donc un kwarg mort — le composant perd "
        f"ce palier en silence.\n"
        f"  Le refus vit dans `refuse_a_value_off_the_table`, appelé "
        f"depuis `finish_render` : s'il s'abstient ici, c'est que la "
        f"table de ce thème est vide ou que son palier par défaut n'est "
        f"dans aucun de ses deux niveaux."
    )


@pytest.mark.parametrize(
    ("cls", "prop", "table_key"), axes(), ids=lambda v: getattr(v, "__name__", v)
)
def test_every_declared_step_still_renders(
    cls: type, prop: str, table_key: str
) -> None:
    """Versant LICITE : le seul qu'on ne peut pas satisfaire par accident.

    C'est ce test qui aurait attrapé les 198 rouges du premier jet.

    Aucun ``except`` de confort ici. Un ``except Exception: pass`` ferait
    sortir en silence tout composant qui cesse de se construire — la
    maladie que ``test_no_gate_swallows_a_component`` interdit, et elle
    l'a attrapée sur ce fichier même. Mesuré : **252 paliers, 0 échec**,
    donc la branche était morte en plus d'être aveugle.
    """
    for step in sorted(steps_of(cls, prop, table_key)):
        try:
            rendered_html_of(cls, prop=prop, value=step)
        except ComponentUsageError as exc:  # pragma: no cover — la faute
            pytest.fail(
                f"`ui.{ui_name_of(cls)}({prop}={step!r})` est REFUSÉ "
                f"alors que son propre thème le déclare.\n"
                f"  {exc}\n"
                f"  Le refus lit la table dans le mauvais sens : le "
                f"catalogue l'imbrique dans les deux (slot → palier ET "
                f"palier → slot), et `declared_steps` tranche par le "
                f"palier PAR DÉFAUT du composant."
            )


# ── La morsure ────────────────────────────────────────────────────────


def test_the_detector_reads_both_nesting_orders() -> None:
    """Mutation : le lecteur tranche par l'ancre, dans les deux sens.

    Le versant licite compte autant que le fautif — un lecteur qui rend
    toujours l'union ne refuserait plus une faute de frappe déguisée en
    nom de slot, et un lecteur qui devine l'ordre casse un composant
    sur deux.
    """
    plate = {"sm": "h-8", "md": "h-10"}
    par_slot = {"input_frame": {"sm": "h-8", "md": "h-10"}}
    par_palier = {"sm": {"root": "h-8"}, "md": {"root": "h-10"}}

    assert declared_steps(plate, anchor="md") == {"sm", "md"}
    assert declared_steps(par_slot, anchor="md") == {"sm", "md"}
    assert declared_steps(par_palier, anchor="md") == {"sm", "md"}

    # Sans ancre lisible, on s'abstient — jamais de faux positif.
    assert declared_steps(par_slot, anchor=None) == frozenset()
    assert declared_steps(par_slot, anchor="introuvable") == frozenset()
    assert declared_steps({}, anchor="md") == frozenset()

    # Et le niveau non choisi ne fuit pas dans la liste.
    assert "input_frame" not in declared_steps(par_slot, anchor="md")
    assert "root" not in declared_steps(par_palier, anchor="md")
