"""Gate : les classes user (``classes=``) atterrissent EXACTEMENT une fois.

Le mécanisme. ``_apply_universal_modifiers`` (le wrap ``render`` de la
métaclasse, ``component.py``) pose les classes user (``self._classes``) sur
le VRAI root de tout composant — c'est le point UNIQUE d'application. Un
``render()`` qui ré-append ``self._classes`` à sa propre string de classe
DOUBLE la classe : ``ui.card(classes="X")`` rend ``… X X``.

Pourquoi cette gate (audit de standardisation, 2026-07-16). ``compose_class``
avait été refactoré pour NE PLUS append les classes user (le wrap s'en
charge), avec un commentaire « so there's no doubling ». Mais ~15 composants
n'utilisent pas ``compose_class`` — ils assemblent leur string de classe à
la main et ré-appendaient ``self._classes``, sans savoir que le wrap le fait
déjà. Doublaient : les 6 layout (Card / Container / Grid + Flex → VStack /
HStack par héritage) ET 9 autres (RadioGroup, ToggleGroup, Dropdown,
Popover, Tooltip, Divider, Heading, MenuItem, Text). L'audit n'en avait
échantillonné que 6 ; le grep + probe ont trouvé les 15. C'est la racine
« primitive refactorée, call-sites jamais alignés » (cf.
feedback_root_cause_not_bandaid) — le fix couvre TOUS les call-sites et
cette gate empêche la récidive.

Deux gardes complémentaires :

1. **SOURCE** (complète, ne pourrit pas) : aucun module composant hors
   ``base/`` ne référence ``self._classes``. Le socle possède l'application
   des classes user ; un composant n'y touche jamais. Attrape même les
   composants non-constructibles isolément (enfants de compound, primitives
   internes) qu'une sonde de rendu manquerait.

2. **COMPORTEMENTALE** (teste le symptôme réel) : on force ``_classes`` sur
   une instance et on compte les occurrences dans le HTML rendu — jamais
   plus d'une. Attrape un doublement par N'IMPORTE QUEL mécanisme, pas
   seulement le pattern ``self._classes`` que la garde 1 bannit.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from tests.consistency._discovery import (
    bare_kwargs,
    parsed_sources,
    public_component_classes,
)

_COMPONENTS_DIR = pathlib.Path(
    "bretzel/components"
).resolve()
_BASE_DIR = _COMPONENTS_DIR / "base"

#: 272 fichiers sous bretzel/components le 2026-08-19.
_COMPONENTS_FLOOR = 200

# La forme du doublement : une référence à ``self._classes`` dans un module
# composant. Le socle (``base/``) est le SEUL autorisé à la lire.
_BANNED = re.compile(r"self\._classes\b")


def _component_source_files() -> list[pathlib.Path]:
    return [
        s.path
        for s in parsed_sources(_COMPONENTS_DIR, floor=_COMPONENTS_FLOOR)
        if _BASE_DIR not in s.path.parents
    ]


@pytest.mark.parametrize(
    "path",
    _component_source_files(),
    ids=lambda p: str(p.relative_to(_COMPONENTS_DIR)),
)
def test_no_component_module_reads_self_classes(path: pathlib.Path) -> None:
    """Garde SOURCE : le socle possède l'application des classes user.

    Un composant qui lit ``self._classes`` dans son ``render()`` va ré-append
    ce que ``_apply_universal_modifiers`` pose déjà → doublon. Le seul endroit
    légitime est ``base/`` (le wrap, ``_user_classes_str``, ``__init__``)."""
    hits = [
        i + 1
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines())
        if _BANNED.search(line)
    ]
    assert not hits, (
        f"{path.relative_to(_COMPONENTS_DIR)} référence `self._classes` "
        f"(ligne(s) {hits}). Les classes user sont posées sur le vrai root "
        f"par le wrap métaclasse `_apply_universal_modifiers` — un composant "
        f"qui les ré-append double la classe (`ui.x(classes='X')` → 'X X'). "
        f"Retire l'append manuel ; laisse le socle le faire."
    )


# ── Garde comportementale : classes user rendues au plus une fois ────────

_SENTINEL = "bzSentinelUserCls"


def _render_sentinel_count(cls: type) -> int | None:
    """Construit ``cls`` par cascade, force ``_classes`` post-hoc (contourne
    les kwargs de constructeur), rend, compte les occurrences. ``None`` si la
    construction ou le rendu échoue (couvert par la garde SOURCE)."""
    attempts = (
        # Le mot obligatoire du socle D'ABORD : sans lui, la cascade
        # échouait sur Image / Iframe / MetaTag / Title, qui sortaient du
        # balayage en silence alors que ``_BARE_ARGS`` les connaît.
        lambda: cls(**bare_kwargs(cls)),
        lambda: cls(),
        lambda: cls("x"),
        lambda: cls(label="x"),
        lambda: cls("x", "y"),
        lambda: cls(options=[("a", "A"), ("b", "B")]),
        lambda: cls("x", options=[("a", "A"), ("b", "B")]),
    )
    with render_isolated():
        instance = None
        for attempt in attempts:
            try:
                instance = attempt()
                break
            except Exception:
                continue
        if instance is None:
            return None
        instance._classes = _SENTINEL
        try:
            html = serialize(instance.render())
        except Exception:
            return None
    return len(re.findall(re.escape(_SENTINEL), html))


_RENDERABLE = [
    (cls, count)
    for cls in public_component_classes()
    for count in (_render_sentinel_count(cls),)
    if count is not None
]


@pytest.mark.parametrize(
    "cls,count",
    _RENDERABLE,
    ids=[c.__name__ for c, _ in _RENDERABLE],
)
def test_user_classes_not_duplicated(cls: type, count: int) -> None:
    """Garde COMPORTEMENTALE : ``classes=`` apparaît au plus une fois.

    0 est légitime (un composant sans root porteur de classe — head-injection
    Fragment, etc.) ; 1 est le cas normal ; ≥ 2 est le bug de doublement."""
    assert count <= 1, (
        f"{cls.__name__} rend les classes user {count} fois — doublement. "
        f"Son `render()` ré-append `classes=` alors que le wrap métaclasse "
        f"`_apply_universal_modifiers` le fait déjà. Retire l'append manuel."
    )


def test_behavioral_gate_is_not_vacuous() -> None:
    """Au moins une poignée de composants doit rendre la sentinelle EXACTEMENT
    une fois — sinon la cascade de construction ne teste plus rien (tout
    skippé / tout à 0)."""
    exactly_one = [c.__name__ for c, n in _RENDERABLE if n == 1]
    assert len(exactly_one) >= 15, (
        f"seulement {len(exactly_one)} composants exercent le chemin "
        f"`classes=` (x1) : {exactly_one}. La cascade de construction "
        f"a-t-elle cessé de fonctionner, ou le wrap a-t-il été retiré ?"
    )


#: Ce que la cascade ne construit pas, avec sa raison. Mesuré le
#: 2026-08-19 en remplaçant l'``except`` par un enregistrement.
_CANNOT_BUILD: dict[str, str] = {
    # `datatable` est SORTI de cette liste le 2026-09-07 : en déclarant
    # son `item_click`, il est entré dans le recensement de
    # `wired_couples`, et `bare_kwargs` a appris à le bâtir (état
    # sonde, une colonne, deux lignes). Il n'y a plus de raison de
    # s'en abstenir.
    "ToggleButton": "ne se rend que dans le ``with`` d'un ToggleGroup",
}


def test_the_abstentions_are_declared() -> None:
    """Ce que la cascade ne monte pas est NOMMÉ, pas compté.

    Un plafond chiffré dirait « pas plus de deux » ; une table dit
    LESQUELS. La différence compte le jour où un composant sort du
    balayage pendant qu'un autre y rentre.
    """
    missing = {
        cls.__name__ for cls in public_component_classes()
        if _render_sentinel_count(cls) is None
    }
    surprise = sorted(missing - set(_CANNOT_BUILD))
    assert not surprise, (
        f"{surprise} ne se construi(sen)t plus par la cascade : ils sortent "
        f"du balayage EN SILENCE, et la garde anti-doublement de `classes=` "
        f"ne les juge plus. Répare, ou déclare AVEC la raison."
    )
    stale = sorted(set(_CANNOT_BUILD) - missing)
    assert not stale, (
        f"{stale} se construi(sen)t de nouveau — retire l'entrée."
    )
