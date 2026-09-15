"""Unit tests for binding-aware ``classes=`` and ``style=`` kwargs.

⚠️ Ces tests décrivaient le mécanisme **V2/Alpine** (``:class`` /
``:style``) et verrouillaient le bug : ils EXIGEAIENT que le ``class=``
statique disparaisse quand on passe un ``classes=binding`` — c'est-à-dire
un Button sans aucune classe de thème, avec une directive que le runtime
V3 ne lit pas. Réécrits sur le contrat V3 le 2026-07-27 (cf.
``tests/consistency/test_reactive_classes_universal.py`` pour la gate
qui étend le contrat aux 55 composants).

Le test de ``style=`` passait, lui, par accident : il cherchait la
sous-chaîne ``:style="`` — que ``bz-attr:style="`` contient.
"""

from __future__ import annotations

from bretzel.components.actions.button import Button
from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from bretzel.state import ClientState, field
from bretzel.state.scopes.client import rendering_scope


class _ExtrasState(ClientState, persist="memory"):
    extra_cls: str = field(default="ring-2")
    extra_style: str = field(default="opacity: 0.5")


class TestClassesBinding:
    def test_static_classes_emits_static_extras(self) -> None:
        with render_isolated():
            b = Button("Save", classes="ring-2")
        out = serialize(b.render())
        # Static classes show up *inside* the static class= attribute ;
        # no reactive directive is emitted for a literal.
        assert "ring-2" in out
        assert "bz-class=" not in out

    def test_classes_binding_emits_bz_class(self) -> None:
        with render_isolated(), rendering_scope():
            state = _ExtrasState()
            b = Button("Save", classes=state.extra_cls)
        out = serialize(b.render())
        # V3 : ``bz-class`` takes the path directly (it accepts a plain
        # string and splits on whitespace).
        assert 'bz-class="$bz.state._ExtrasState.default.extra_cls"' in out
        # ⚠️ La composition statique SURVIT — ``bz-class`` piste les
        # classes qu'il ajoute et ne touche jamais au ``class=`` serveur.
        # L'ancien ``:class`` la supprimait, laissant le bouton nu.
        button_open = out.split(">", 1)[0]
        assert ' class="' in button_open
        assert "rounded-field" in button_open  # part of Button's root slot
        # Plus aucune syntaxe Alpine : le runtime V3 ne lit que bz-*.
        assert ":class=" not in out


class TestStyleBinding:
    def test_static_style_emits_static_attr(self) -> None:
        with render_isolated():
            b = Button("Save", style="opacity: 0.5")
        out = serialize(b.render())
        assert 'style="opacity: 0.5"' in out

    def test_style_binding_emits_bz_attr_style(self) -> None:
        with render_isolated(), rendering_scope():
            state = _ExtrasState()
            b = Button("Save", style=state.extra_style)
        out = serialize(b.render())
        assert (
            'bz-attr:style="$bz.state._ExtrasState.default.extra_style"'
            in out
        )
        # No leftover static style attr.
        assert 'style="opacity:' not in out
