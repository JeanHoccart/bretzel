"""Un chemin de binding n'atterrit jamais en CHAMP nu d'un ``bz-data``.

Un ``bz-data`` est un littéral objet évalué **une seule fois**, hors
effet, par ``evalDataLiteral`` (``03_scope.js``). ``absorb`` prend ce que
chaque clé vaut à cet instant et, pour une valeur non-fonction, l'emballe
dans un signal NEUF (``signals.set(key, $bz.signal(v))``) — un signal
découplé de la cellule du store, que plus rien ne réécrit. Un champ
``_x: $bz.state.Foo.default.bar`` est donc un **snapshot au montage**,
pas un binding.

Une expression liée doit vivre dans un CORPS DE MÉTHODE : c'est le seul
endroit relu à chaque appel, donc tracé par l'effet appelant. C'est
exactement pourquoi ``_read() { return <path>; }`` reste réactif quand
``_disabled: <path>`` ne l'est pas.

Ce que ça a coûté
------------------
Le passage « la config entre en données » (112fb527, 30 juil. 2026) a
converti cinq composants. Deux y ont perdu un binding vivant, en silence,
pendant deux jours :

- ``Pagination`` : ``isDisabled() { return !!(<expr>); }`` →
  ``_disabled: <expr>``. Mesuré : le switch bascule, les neuf boutons
  restent cliquables. ``value`` survivait — il passe par
  ``_read``/``_write``, des corps de méthode.
- ``Tooltip`` : ``_enabled: <expr>``, alors que le commentaire trois
  lignes plus haut promettait « évaluée au moment du survol, pas au
  montage ». Pire, ``enabled`` n'est pas dans ``BINDABLE_PROPS``, donc
  aucune gate de binding ne le regardait — d'où le balayage par
  ANNOTATION ci-dessous, pas seulement par ``BINDABLE_PROPS``.

``Slider`` a survécu parce qu'il avait gardé ``_disabledState() { return
<expr>; }``. C'est la forme à copier.
"""

from __future__ import annotations

import html as _html
import inspect
import re

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from bretzel.state.scopes.client import ClientBinding
from tests.audit.test_binding_completeness import CONSTRUCT, _Skip
from tests.consistency._discovery import (
    assert_sweep_is_not_vacuous,
    public_component_classes,
)

_SENTINEL = "$bz.state.probe.default.flag"
_BZ_DATA = re.compile(r"bz-data=\"([^\"]*)\"")
# En-tête de méthode : ``nom(args) {``. Un getter (``get x()``) n'existe
# pas dans un bz-data (absorb le figerait) et n'est donc pas cherché.
_METHOD_HEAD = re.compile(r"\w+\s*\([^)]*\)\s*\{")


def _binding() -> ClientBinding:
    return ClientBinding(class_name="probe", instance_key="default",
                         field_name="flag", value=False)


def _outside_method_bodies(literal: str) -> str:
    """Le littéral avec chaque corps de méthode blanchi.

    L'ancrage sur l'EN-TÊTE de méthode est nécessaire, pas décoratif : une
    règle « précédé de return » rate ``isDisabled() { return !!(<path>); }``
    (le ``!!(`` s'intercale) et ``_write(v) { <path> = v; }`` ; une règle
    « profondeur d'accolades >= 2 » classe ``_cfg: { x: <path> }`` comme sûr
    alors que c'est un champ imbriqué, donc gelé lui aussi.
    """
    out = list(literal)
    for head in _METHOD_HEAD.finditer(literal):
        depth = 0
        for i in range(head.end() - 1, len(literal)):
            depth += (literal[i] == "{") - (literal[i] == "}")
            out[i] = " "
            if depth == 0:
                break
    return "".join(out)


def _frozen_occurrences(html: str) -> list[str]:
    """Les ``bz-data`` où le sentinel subsiste hors de tout corps de méthode."""
    frozen: list[str] = []
    for raw in _BZ_DATA.findall(html):
        literal = _html.unescape(raw)
        if _SENTINEL in literal and _SENTINEL in _outside_method_bodies(literal):
            frozen.append(literal)
    return frozen


def _bindable_kwargs(cls: type) -> list[str]:
    """``BINDABLE_PROPS`` + tout paramètre annoté ``ClientBinding``.

    Le second terme n'est pas du zèle : ``Tooltip.enabled`` accepte un
    ``ClientBinding`` sans être dans ``BINDABLE_PROPS``, et c'est
    précisément le trou par lequel sa régression est passée.
    """
    props = list(cls.BINDABLE_PROPS)
    try:
        sig = inspect.signature(cls.__init__)
    except (TypeError, ValueError):
        return props
    for name, param in sig.parameters.items():
        if name in ("self", "kwargs") or name in props:
            continue
        if "ClientBinding" in str(param.annotation):
            props.append(name)
    return props


def _render_bound(cls: type, prop: str) -> str:
    builder = CONSTRUCT.get(cls.__name__)
    with render_isolated():
        if builder is not None:
            comp = builder(cls, prop, _binding())
        else:
            comp = cls(**{prop: _binding()})
        return serialize(comp.render())


_CASES = [
    (cls, prop)
    for cls in public_component_classes()
    for prop in _bindable_kwargs(cls)
]


@pytest.mark.parametrize(
    "cls,prop", _CASES, ids=lambda v: v if isinstance(v, str) else v.__name__
)
def test_bound_prop_is_not_snapshotted_in_a_bz_data_field(
    cls: type, prop: str
) -> None:
    try:
        html = _render_bound(cls, prop)
    except _Skip as exc:
        pytest.skip(str(exc))
    except Exception as exc:
        pytest.skip(f"{cls.__name__}.{prop} non constructible : "
                    f"{type(exc).__name__}: {exc}")

    frozen = _frozen_occurrences(html)
    assert not frozen, (
        f"{cls.__name__}.{prop}= : le chemin du binding atterrit en CHAMP "
        f"nu d'un `bz-data`, hors de tout corps de méthode —\n  {frozen[0]}\n\n"
        f"Un littéral objet est évalué une fois, au montage, hors effet : "
        f"`absorb` en emballe le snapshot dans un signal découplé du store, "
        f"que plus rien ne réécrit. Le binding est mort-né.\n\n"
        f"Mets l'expression dans un corps de méthode — surcharge la "
        f"constante du slab, comme `_disabledState()` du Slider :\n"
        f"    f\"{prop}Something() {{ return !!({{expr}}); }},\""
    )


def test_the_sweep_actually_binds_something() -> None:
    """Plancher de non-vacuité (règle 8 du CLAUDE.md).

    « Aucun binding gelé » passe aussi bien quand rien n'a été lié : nom
    de sentinel changé, rendu vide, ``bz-data`` renommé. On exige de VOIR
    le sentinel ressortir dans des ``bz-data``, et de le voir sur les deux
    composants dont la régression a motivé la gate.
    """
    assert_sweep_is_not_vacuous()
    assert len(_CASES) >= _CASE_FLOOR, (
        f"seulement {len(_CASES)} couples (composant, prop bindable) — "
        f"plancher {_CASE_FLOOR}. Le balayage ne trouve plus la surface."
    )

    reached: set[str] = set()
    for cls, prop in _CASES:
        try:
            html = _render_bound(cls, prop)
        except Exception:
            continue
        if any(_SENTINEL in _html.unescape(raw)
               for raw in _BZ_DATA.findall(html)):
            reached.add(cls.__name__)

    assert {"Pagination", "Tooltip"} <= reached, (
        f"Pagination et Tooltip doivent rester atteints : ce sont les deux "
        f"régressions qui ont motivé la gate, et leur binding transite par "
        f"un `bz-data`. Vu : {sorted(reached)}."
    )


# Mesuré le 2026-08-02 : 86 couples (composant, prop bindable).
_CASE_FLOOR = 40


def test_the_detector_still_bites() -> None:
    """Mutation : un chemin de binding GELÉ dans un ``bz-data`` est vu.

    Gelé, il ne suit plus la valeur : le composant affiche l'état du
    premier rendu pour toujours. La subtilité est qu'un chemin DANS un
    corps de méthode est légitime — il se réévalue à l'appel. Le
    détecteur doit donc distinguer les deux places.
    """
    fautif = f'<div bz-data="{{val: {_SENTINEL}}}"></div>'
    assert _frozen_occurrences(fautif), "un chemin hors méthode devrait mordre"

    licite = f'<div bz-data="{{_read() {{ return {_SENTINEL}; }}}}"></div>'
    assert not _frozen_occurrences(licite), (
        "dans un corps de méthode, le chemin se réévalue — faux positif"
    )
