"""Gate : le contrat ``TWO_WAY_PROPS`` — « quelle prop le client écrit-il ? »

Un composant déclare dans ``TWO_WAY_PROPS`` les props dont le chemin
client sert de **cible d'assignation** dans le JS émis : ``bz-model``
compile ``<path> = $value`` ; les overlays émettent ``<path> = false`` ;
les scopes riches portent un ``_write(v) { <path> = v }``.

Conséquence : une ``ClientExpression`` y est structurellement invalide —
``(a || b) = $value`` est une SyntaxError, que le navigateur lève **au
bind** (``compile(expr, "set")``, 02_directives.js), pas au premier clic.
Le composant serait mort avant toute interaction. Le constructeur refuse
donc à la construction.

Pourquoi ce concept existe (audit 2026-07-15) : il manquait, et trois
mécanismes l'empruntaient ailleurs faute de mieux —
``_bind_x_model`` le hardcodait, le gate ``_serverSync`` réutilisait
``_derive_field_name`` (un helper d'**autoname**), et A2 ne l'avait pas
du tout d'où le SyntaxError. ``TWO_WAY_PROPS`` ≠ ``AUTONAME_FROM`` : les
deux coïncident sur les 15 inputs de formulaire mais divergent sur les
5 overlays (``open``, non form-bound) et ``Radio`` (le ``name`` vient du
groupe). Emprunter l'un pour l'autre couple le server-sync au
form-naming — cf. todo.md § A3.

La construction fidèle réutilise le registre ``CONSTRUCT`` de
``tests/audit/test_binding_completeness.py`` (source unique : un
composant à kwargs requis y est déjà décrit) plutôt que d'en réinventer
un second.
"""

from __future__ import annotations

import pytest

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.state.scopes.client import (
    ClientExpression,
    rendering_scope,
)
from tests.audit.test_binding_completeness import CONSTRUCT, _Skip
from tests.consistency._discovery import public_component_classes

_COMPONENTS = public_component_classes()
_TWO_WAY = [c for c in _COMPONENTS if getattr(c, "TWO_WAY_PROPS", ())]


def _expr() -> ClientExpression:
    return ClientExpression("$bz.state.S.default.a || $bz.state.S.default.b")


def _build(cls: type, prop: str, value):
    """Construire ``cls`` avec ``value`` sur ``prop``, fidèlement.

    On tente la construction directe D'ABORD, et on ne retombe sur le
    registre ``CONSTRUCT`` que si le composant exige des kwargs (Select
    veut ``options=``, Pagination ``total_pages=``…). Raison : certains
    builders du registre — ``_date_build`` — **remplacent** le binding
    reçu par une valeur type-correcte (une vraie ``date``). C'est juste
    pour le test de complétude qu'ils servent, mais ça défait celui-ci :
    l'expression n'atteindrait jamais le constructeur et le test de refus
    passerait à vide (faux vert).

    ⚠️ ``ComponentUsageError`` HÉRITE de ``TypeError`` — le refus qu'on
    cherche justement à observer serait donc avalé par un ``except
    TypeError`` nu, qui retomberait sur le builder rebindeur : faux vert
    garanti. On le laisse remonter explicitement.
    """
    try:
        return cls(**{prop: value})
    except ComponentUsageError:
        raise
    except TypeError:
        builder = CONSTRUCT.get(cls.__name__)
        if builder is None:
            raise
        return builder(cls, prop, value)


# ── Invariants structurels (aucune construction requise) ──────────────


@pytest.mark.parametrize("cls", _TWO_WAY, ids=lambda c: c.__name__)
def test_two_way_is_subset_of_bindable(cls: type) -> None:
    """On ne peut pas écrire dans une prop qui n'accepte pas de binding."""
    bindable = set(getattr(cls, "BINDABLE_PROPS", ()) or ())
    orphans = sorted(set(cls.TWO_WAY_PROPS) - bindable)
    assert not orphans, (
        f"{cls.__name__}.TWO_WAY_PROPS déclare {orphans} hors de "
        f"BINDABLE_PROPS ({sorted(bindable)}) — le constructeur rejetterait "
        f"le binding avant que le two-way ne serve. Config morte."
    )


@pytest.mark.parametrize("cls", _TWO_WAY, ids=lambda c: c.__name__)
def test_two_way_names_a_real_reactive_prop(cls: type) -> None:
    reactive = set(getattr(cls, "__reactive_props__", {}) or {})
    orphans = sorted(set(cls.TWO_WAY_PROPS) - reactive)
    assert not orphans, (
        f"{cls.__name__}.TWO_WAY_PROPS nomme {orphans}, qui n'est pas un "
        f"reactive_prop déclaré ({sorted(reactive)}) — typo ou renommage."
    )


@pytest.mark.parametrize("cls", _COMPONENTS, ids=lambda c: c.__name__)
def test_autoname_prop_is_always_two_way(cls: type) -> None:
    """``AUTONAME_FROM`` = « la prop qui porte ma valeur de formulaire ».
    Une valeur de formulaire est toujours écrite par le client — l'inverse
    n'est pas vrai (les overlays écrivent ``open`` sans être form-bound)."""
    auto = getattr(cls, "AUTONAME_FROM", None)
    if auto is None:
        return
    assert auto in getattr(cls, "TWO_WAY_PROPS", ()), (
        f"{cls.__name__}.AUTONAME_FROM = {auto!r} mais TWO_WAY_PROPS = "
        f"{getattr(cls, 'TWO_WAY_PROPS', ())} — une valeur de formulaire "
        f"est écrite par le client, elle doit être déclarée two-way "
        f"(sinon une ClientExpression y passerait et casserait au bind)."
    )


# ── Invariant comportemental : le refus fonctionne vraiment ───────────


@pytest.mark.parametrize(
    "cls,prop",
    [(c, p) for c in _TWO_WAY for p in c.TWO_WAY_PROPS],
    ids=lambda v: v if isinstance(v, str) else v.__name__,
)
def test_expression_on_two_way_prop_is_refused(cls: type, prop: str) -> None:
    with render_isolated(), rendering_scope():
        with pytest.raises(ComponentUsageError, match="two-way"):
            _build(cls, prop, _expr())


@pytest.mark.parametrize(
    "cls,prop",
    [
        (c, p)
        for c in _COMPONENTS
        for p in (getattr(c, "BINDABLE_PROPS", ()) or ())
        if p not in getattr(c, "TWO_WAY_PROPS", ())
        and p in (getattr(c, "__reactive_props__", {}) or {})
    ],
    ids=lambda v: v if isinstance(v, str) else v.__name__,
)
def test_expression_on_read_only_prop_works(cls: type, prop: str) -> None:
    """Le contrat universel : toute prop LUE accepte les 3 shapes.
    C'est le trou qui a laissé A2 vivre — aucun test ne passait une
    expression à une reactive prop, sur 76 paires possibles."""
    with render_isolated(), rendering_scope():
        try:
            comp = _build(cls, prop, _expr())
        except _Skip as exc:
            pytest.skip(str(exc))
        except ComponentUsageError as exc:
            pytest.fail(
                f"{cls.__name__}.{prop} est bindable et NON two-way, donc "
                f"une ClientExpression doit passer — refusée : {exc}"
            )
        rendered = repr(comp.render())
    assert "$bz.state.$bz.state" not in rendered, (
        f"{cls.__name__}.{prop} : double préfixe — un chemin est construit "
        f"à la main quelque part (utilise path_of)."
    )
    # ⚠️ Une expression est parenthésée : la forme naïve ci-dessus ne la
    # voit PAS. C'est ce piège qui donne un faux pass à un probe naïf.
    assert "$bz.state.($bz.state" not in rendered, (
        f"{cls.__name__}.{prop} : double préfixe (forme parenthésée)."
    )


def test_gate_is_not_vacuous() -> None:
    assert len(_TWO_WAY) >= 20, (
        f"seulement {len(_TWO_WAY)} composants two-way — la famille en "
        f"compte 23 (15 inputs + 5 overlays + calendar/month + form_field)."
    )
