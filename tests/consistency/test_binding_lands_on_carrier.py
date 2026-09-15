"""Gate G1 — un ``bz-attr:<attr>`` réactif atterrit sur un tag où
``<attr>`` fait quelque chose.

Le piège wrapper-vs-carrier : ``emit_attrs`` pose ``bz-attr:<prop>`` sur
la RACINE du composant, mais ``disabled`` / ``checked`` / ``value`` /
``src`` … n'ont de sens que sur un tag précis. Sur le ``<div>`` wrapper
d'un composite, le runtime écrit l'attribut à chaque tick réactif et
**rien ne se passe** : le composant reste interactif alors que le binding
dit `True`.

Pourquoi cette gate existe (2026-07-27, audit F01-F04)
------------------------------------------------------
Ce contrat ÉTAIT gardé — par ``tests/audit/interaction.py``
``probe_client_binding_lands_on_carrier``, un probe Playwright. Sauf
qu'il interroge le DOM sur ``x-bz-prop:`` — le préfixe Alpine-era, mort
depuis le rebrand ``bz-``. Il ne matchait plus **aucun** attribut : il
passait au vert sur une page qui n'a jamais eu un seul directive du nom
qu'il cherche (cf. memory *« Les probes Playwright pourrissent en
silence »*). Pendant ce temps DatePicker et DateRangePicker laissaient un
``bz-attr:disabled`` inerte sur leur ``<div>`` racine, jamais forwardé
sur les champs visibles — un ``disabled=binding`` ne désactivait rien.

La leçon : ce contrat est **statique** (il se lit sur le HTML SSR), donc
il n'a rien à faire dans un navigateur. Ici il tourne dans le sous-ensemble
rapide, sans serveur, et il ne peut pas pourrir en silence — le préfixe
vient de ``protocol.BZ_ATTR_PREFIX``, pas d'une string recopiée. La table
attribut→tags vit dans ``tests/audit/carriers.py``, partagée avec le probe
DOM (qui, lui, voit en plus ce que le runtime a monté).

Ce que la gate NE couvre pas : la complétude (« le binding émet-il
quelque chose ? »), gardée par ``tests/audit/test_binding_completeness.py``.
Les deux sont complémentaires — un binding peut atterrir nulle part (là-bas)
ou atterrir sur le mauvais tag (ici).
"""

from __future__ import annotations

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from tests.audit.carriers import (
    ATTR_CARRIERS,
    BZ_ATTR_PREFIX,
    carrier_violations,
)
from tests.audit.test_binding_completeness import CONSTRUCT, _binding, _Skip
from tests.consistency._discovery import public_component_classes

#: Pas de détecteur à rendre aveugle — cf.
#: ``test_a_prohibition_gate_is_mutation_tested``.
MUTATION_NOT_APPLICABLE = (
    "pose un binding et vérifie sur quelle balise il atterrit ; "
    "`test_the_gate_has_a_population` garde la population"
)

_BINDABLE = [c for c in public_component_classes()
             if getattr(c, "BINDABLE_PROPS", None)]


def test_the_gate_has_a_population() -> None:
    """Plancher de non-vacuité. Cette gate est une INTERDICTION : elle
    affirme « zéro contrevenant ». Un refactor qui casserait la découverte
    la laisserait donc verte sur zéro vérification — et ce n'est pas
    théorique ici : cette gate a DÉJÀ été verte des mois durant en cherchant
    le préfixe ``x-bz-prop:``, mort depuis le rebrand ``bz-``, donc en ne
    matchant plus aucun attribut (cf. audit du 2026-07-27)."""
    assert len(_BINDABLE) >= 40, (
        f"seulement {len(_BINDABLE)} composants portent des BINDABLE_PROPS "
        f"(44 mesurés le 2026-07-29) — la découverte a régressé, la gate ne "
        f"vérifie plus grand-chose."
    )


@pytest.mark.parametrize("cls", _BINDABLE, ids=lambda c: c.__name__)
def test_bound_prop_lands_on_a_tag_that_honours_it(cls: type) -> None:
    """Binder chaque ``BINDABLE_PROPS`` puis vérifier que les directives
    réactives émises tiennent sur un tag qui les honore."""
    builder = CONSTRUCT.get(cls.__name__)
    seen: dict[tuple[str, str], str] = {}
    for prop in cls.BINDABLE_PROPS:
        try:
            with render_isolated():
                comp = (builder(cls, prop, _binding(prop)) if builder
                        else cls(**{prop: _binding(prop)}))
                html = serialize(comp.render())
        except _Skip:
            continue
        except Exception as exc:  # construction non fidèle → couvert ailleurs
            pytest.skip(f"{cls.__name__}({prop}=binding) : {type(exc).__name__}: {exc}")
        for tag, attr, expr in carrier_violations(html):
            seen[(tag, attr)] = expr

    assert not seen, (
        f"{cls.__name__} émet des directives réactives sur un tag inerte "
        f"(le runtime écrit l'attribut à chaque tick, le DOM ne bouge pas) :\n  "
        + "\n  ".join(
            f"{BZ_ATTR_PREFIX}{attr} sur <{tag}> — attendu sur "
            f"{sorted(ATTR_CARRIERS[attr])} — expr={expr!r}"
            for (tag, attr), expr in sorted(seen.items())
        )
        + "\n\nFix : `emit_attr=False` sur le reactive_prop + "
          "`self.forward_binding(prop, carrier_attrs)` vers l'élément réel "
          "(ou `BINDABLE_CARRIERS`), et `release_root_attr` si la racine "
          "porte encore la version littérale."
    )
