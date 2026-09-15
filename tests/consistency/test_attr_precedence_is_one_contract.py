"""Rien de ce que l'utilisateur écrit ne disparaît en silence.

LE contrat de précédence, en une phrase :

- ``class`` / ``style`` **se composent** — chaque source s'ajoute, dans
  l'ordre : composition du thème, puis HTML brut (``class_=`` /
  ``attrs={"class": …}``), puis ``classes=`` en dernier (donc gagnant en
  cas de conflit Tailwind, où la dernière classe l'emporte) ;
- tout le reste **s'écrase** — un élément n'a qu'un ``id`` ;
- pour ``id``, le kwarg **nommé** bat ``attrs={"id": …}`` : l'API
  explicite gagne sur l'échappatoire brute.

Pourquoi cette gate existe (audit du socle 2026-07-29, item 6)
---------------------------------------------------------------
Il y avait **quatre résolutions différentes pour la même collision** —
produit de l'ordre des ``attrs.update`` dans ``emit_attrs``, jamais énoncé
comme contrat. ``kwarg-routing.md`` documentait le *stockage* de chaque
bucket, jamais l'*ordre d'application*. Mesuré avant le fix :

===============================  ==========================================
collision                        résultat
===============================  ==========================================
``id=`` + ``attrs["id"]``        ``attrs`` gagnait — le kwarg nommé perdu
``classes=`` + ``attrs[class]``  l'un des deux disparaissait
``classes=`` + ``class_=``       ``class_`` disparaissait
``style=`` + ``attrs[style]``    les deux survivaient (seul cas correct)
===============================  ==========================================

**Trois entrées utilisateur perdues sans un mot.**

⚠️ Pourquoi le fix ne pouvait PAS vivre dans ``emit_attrs``
------------------------------------------------------------
Un composant qui reconstruit sa ``class=`` dans ``render()`` —
``attrs["class"] = " ".join(parts)``, ce que fait ``Card`` — écrase tout ce
que ``emit_attrs`` a posé. Les classes brutes sont donc appliquées
**post-render**, par le wrap métaclasse, au même point que ``classes=`` et
``slots={"root"}``. C'est le troisième kwarg universel à remonter là, et
pour la même raison exactement.

D'où le paramétrage sur des composants aux ``render()`` DIVERGENTS : un
seul composant testé n'aurait rien prouvé.
"""

from __future__ import annotations

import re

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from tests.audit.test_binding_completeness import CONSTRUCT, _Skip
from tests.consistency._discovery import public_component_classes

# Quatre familles de ``render()`` volontairement différentes : classe
# fabriquée à la main, ``compose_class``, slots multiples, helper privé.
_SPREAD = ("Card", "Button", "Input", "Text", "Badge", "Alert")


def _render(name: str, **kwargs) -> str:
    cls = next(
        (c for c in public_component_classes() if c.__name__ == name), None
    )
    assert cls is not None, f"{name} n'est plus un composant public"
    builder = CONSTRUCT.get(name)
    with render_isolated():
        if builder is not None:
            # Les builders posent une prop ; on complète avec nos kwargs.
            node = builder(cls, "slots", {}).render()
            # Le builder ne connaît pas nos kwargs — on reconstruit à la
            # main quand il y en a.
            if kwargs:
                node = cls(**kwargs).render()
        else:
            node = cls(**kwargs).render()
        return serialize(node)


def _attr(html: str, name: str) -> str:
    m = re.search(rf'\s{re.escape(name)}="([^"]*)"', html)
    return m.group(1) if m else ""


def _marks(html: str, name: str) -> list[str]:
    """Les seuls tokens qu'on a injectés — le thème est du bruit ici."""
    raw = _attr(html, name).replace(";", " ")
    return [t for t in raw.split() if t.startswith("ZZ") or t.startswith("color:")]


@pytest.mark.parametrize("name", _SPREAD)
def test_class_sources_all_compose(name: str) -> None:
    """``class_=`` (brut) ET ``classes=`` (API) survivent tous les deux."""
    try:
        html = _render(name, classes="ZZapi", class_="ZZraw")
    except (_Skip, TypeError) as exc:
        pytest.skip(f"{name} non constructible nu : {exc}")
    got = _marks(html, "class")
    assert "ZZraw" in got, (
        f"{name} : `class_=\"ZZraw\"` a disparu (class={got}). Le HTML brut "
        f"doit survivre à la composition du thème — il est appliqué "
        f"post-render par le wrap, précisément pour qu'un `render()` qui "
        f"écrit `attrs[\"class\"] = …` ne puisse pas l'écraser."
    )
    assert "ZZapi" in got, f"{name} : `classes=` a disparu (class={got})"
    assert got.index("ZZraw") < got.index("ZZapi"), (
        f"{name} : ordre inversé ({got}). Le contrat est « thème, puis "
        f"brut, puis `classes=` en dernier » — la dernière classe gagne "
        f"chez Tailwind, donc l'API de l'utilisateur doit fermer la marche."
    )


@pytest.mark.parametrize("name", _SPREAD)
def test_style_sources_all_compose(name: str) -> None:
    try:
        html = _render(name, style="color:red", attrs={"style": "color:blue"})
    except (_Skip, TypeError) as exc:
        pytest.skip(f"{name} non constructible nu : {exc}")
    got = _marks(html, "style")
    assert "color:blue" in got and "color:red" in got, (
        f"{name} : une des deux déclarations de style a disparu ({got}). "
        f"`style` est composable — les deux sources s'ajoutent."
    )


@pytest.mark.parametrize("name", _SPREAD)
def test_named_id_beats_the_raw_escape_hatch(name: str) -> None:
    try:
        html = _render(name, id="ZZnamed", attrs={"id": "ZZraw"})
    except (_Skip, TypeError) as exc:
        pytest.skip(f"{name} non constructible nu : {exc}")
    assert _attr(html, "id") == "ZZnamed", (
        f"{name} : `attrs={{'id': …}}` a battu le kwarg nommé `id=` "
        f"(id={_attr(html, 'id')!r}). `id` n'est pas composable — un élément "
        f"n'en a qu'un — et c'est l'API explicite qui gagne sur "
        f"l'échappatoire brute."
    )


def test_the_merge_helper_owns_the_contract() -> None:
    """Le contrat est UNE fonction, pas un ordre d'``update`` implicite.

    C'était le vrai défaut : la précédence était le produit accidentel de
    l'ordre des lignes dans ``emit_attrs``. On fige ici que le helper
    existe et se comporte comme annoncé, pour qu'un futur lecteur ait un
    seul endroit à lire."""
    from bretzel.components.base.component import merge_attr

    attrs: dict[str, object] = {}
    merge_attr(attrs, "class", "a")
    merge_attr(attrs, "class", "b")
    assert attrs["class"] == "a b", "class doit composer"

    merge_attr(attrs, "style", "color:red")
    merge_attr(attrs, "style", "margin:0")
    assert attrs["style"] == "color:red; margin:0", "style doit composer"

    merge_attr(attrs, "role", "button")
    merge_attr(attrs, "role", "link")
    assert attrs["role"] == "link", "un attribut non composable s'écrase"

    # Idempotence : recomposer la même valeur ne fait pas enfler class=.
    merge_attr(attrs, "class", "a")
    assert attrs["class"] == "a b", "une valeur déjà présente ne se duplique pas"

    # ``None`` ne pose rien (une prop absente ne doit pas écrire "None").
    merge_attr(attrs, "role", None)
    assert attrs["role"] == "link"
