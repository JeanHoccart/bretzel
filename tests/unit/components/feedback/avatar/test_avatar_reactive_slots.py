"""Unit tests for reactive initials / src on the Avatar component."""

from __future__ import annotations

import pytest

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.feedback.avatar import Avatar
from bretzel.core.serialize import serialize
from bretzel.state import ClientState, field
from bretzel.state.scopes.client import rendering_scope


class _AvatarState(ClientState, persist="memory"):
    initials: str = field(default="JH")
    src: str = field(default="/jean.jpg")


class TestStaticAvatar:
    def test_static_initials_emit_plain_text(self) -> None:
        with render_isolated():
            a = Avatar(initials="JH")
        out = serialize(a.render())
        assert ">JH<" in out
        # ``bz-text=`` : la DIRECTIVE. Le palier ``text-(--bz-text)``
        # partage la sous-chaîne sans être elle.
        assert "bz-text=" not in out

    def test_long_initials_truncated_to_3_chars(self) -> None:
        # Avatar is sized for 1-3 letters by convention. Longer
        # strings would spill outside the rounded box ; truncating
        # at render is the standard fix (cf. Material UI / Chakra /
        # Mantine). Users wanting initials from a name should pre-
        # compute via ``initials_of(name)``.
        with render_isolated():
            a = Avatar(initials="ALOTOFINITIALS")
        out = serialize(a.render())
        assert ">ALO<" in out
        assert "OFINITIALS" not in out

    def test_exact_3_char_initials_pass_through(self) -> None:
        # Boundary : 3 chars is the limit, no truncation.
        with render_isolated():
            a = Avatar(initials="ABC")
        out = serialize(a.render())
        assert ">ABC<" in out


class TestReactiveAvatar:
    def test_initials_binding_is_refused(self) -> None:
        # ``initials`` coupé du bindable 2026-07-16 (règle « driver client,
        # sinon serveur » : les initiales ne changent qu'avec les données
        # serveur → @refreshable, ∅). Un binding y lève ComponentUsageError.
        with render_isolated(), rendering_scope():
            with pytest.raises(ComponentUsageError):
                Avatar(initials=_AvatarState().initials)

    def test_src_binding_is_refused(self) -> None:
        # ``src`` coupé du bindable 2026-07-16 (même raison : ∅). Seul
        # ``status`` (présence live) reste one-way.
        with render_isolated(), rendering_scope():
            with pytest.raises(ComponentUsageError):
                Avatar(src=_AvatarState().src, alt="x")
