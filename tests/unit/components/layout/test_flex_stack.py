"""Unit tests for :class:`Flex` and the stack shortcuts (VStack/HStack)."""

from __future__ import annotations

import pytest

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.layout.flex import Flex
from bretzel.components.layout.stack import HStack, VStack
from bretzel.components.primitives.text import Text
from bretzel.core.serialize import serialize

# ───────────────────────────────────────────────────────────────────────────
# Flex — full API
# ───────────────────────────────────────────────────────────────────────────


class TestFlexDefaults:
    def test_defaults(self) -> None:
        with render_isolated():
            f = Flex()
        out = serialize(f.render())
        # ``flex`` (root), ``flex-row`` (default direction),
        # ``items-stretch`` (align), ``justify-start`` (justify),
        # ``gap-4`` (md gap).
        for cls in ("flex", "flex-row", "items-stretch", "justify-start", "gap-4"):
            assert cls in out

    def test_defaults_no_wrap(self) -> None:
        with render_isolated():
            f = Flex()
        assert "flex-wrap" not in serialize(f.render())


class TestFlexProps:
    @pytest.mark.parametrize(
        ("direction", "expected"),
        [
            ("row", "flex-row"),
            ("col", "flex-col"),
            ("row-reverse", "flex-row-reverse"),
            ("col-reverse", "flex-col-reverse"),
        ],
    )
    def test_direction(self, direction: str, expected: str) -> None:
        with render_isolated():
            f = Flex(direction=direction)
        assert expected in serialize(f.render())

    @pytest.mark.parametrize(
        ("align", "expected"),
        [
            ("start", "items-start"),
            # ⚠️ ``safe`` depuis le 2026-08-29 : un centrage nu rend le
            # haut d'un contenu trop grand INATTEIGNABLE (454 px mesurés).
            # Cf. tests/consistency/test_a_scrolling_container_never_centers_unsafely.
            ("center", "[align-items:safe_center]"),
            ("baseline", "items-baseline"),
        ],
    )
    def test_align(self, align: str, expected: str) -> None:
        with render_isolated():
            f = Flex(align=align)
        assert expected in serialize(f.render())

    @pytest.mark.parametrize(
        ("justify", "expected"),
        [
            ("start", "justify-start"),
            ("center", "[justify-content:safe_center]"),
            ("between", "justify-between"),
            ("around", "justify-around"),
        ],
    )
    def test_justify(self, justify: str, expected: str) -> None:
        with render_isolated():
            f = Flex(justify=justify)
        assert expected in serialize(f.render())

    @pytest.mark.parametrize(
        ("gap", "expected"),
        [
            ("none", "gap-0"),
            ("xs", "gap-1"),
            ("sm", "gap-2"),
            ("md", "gap-4"),
            ("lg", "gap-6"),
            ("xl", "gap-8"),
        ],
    )
    def test_gap(self, gap: str, expected: str) -> None:
        with render_isolated():
            f = Flex(gap=gap)
        assert expected in serialize(f.render())

    def test_wrap(self) -> None:
        with render_isolated():
            f = Flex(wrap=True)
        assert "flex-wrap" in serialize(f.render())


class TestFlexChildren:
    def test_with_block_collects(self) -> None:
        with render_isolated(), Flex() as f:
            Text("a")
            Text("b")
        out = serialize(f.render())
        # Both children rendered inside the flex container.
        assert ">a<" in out
        assert ">b<" in out
        assert out.index(">a<") < out.index(">b<")

    def test_user_classes_appended(self) -> None:
        with render_isolated():
            f = Flex(classes="my-extra")
        out = serialize(f.render())
        assert "my-extra" in out


# ───────────────────────────────────────────────────────────────────────────
# VStack — vertical flex shortcut
# ───────────────────────────────────────────────────────────────────────────


class TestVStack:
    def test_direction_col_baked(self) -> None:
        with render_isolated():
            v = VStack()
        out = serialize(v.render())
        assert "flex-col" in out
        assert "flex-row" not in out

    def test_default_gap_align(self) -> None:
        with render_isolated():
            v = VStack()
        out = serialize(v.render())
        assert "gap-4" in out
        assert "items-stretch" in out

    def test_is_a_flex_subclass(self) -> None:
        # VStack bakes direction on top of Flex ; Flex stays the escape
        # hatch for a runtime-chosen axis (there is no bare Stack).
        assert issubclass(VStack, Flex)

    def test_no_direction_kwarg(self) -> None:
        # The axis is fixed : passing ``direction`` is a TypeError, not a
        # silent flip (drop to ``ui.flex`` for a runtime axis).
        with render_isolated():
            with pytest.raises(TypeError):
                VStack(direction="row")


class TestHStack:
    def test_direction_row_baked(self) -> None:
        with render_isolated():
            h = HStack()
        out = serialize(h.render())
        assert "flex-row" in out
        assert "flex-col" not in out

    def test_default_align_center(self) -> None:
        # HStack centers vertically by default — most common UX intent.
        # Le centrage porte ``safe`` : cf. le commentaire de ``test_align``.
        with render_isolated():
            h = HStack()
        assert "[align-items:safe_center]" in serialize(h.render())

    def test_gap_xl(self) -> None:
        with render_isolated():
            h = HStack(gap="xl")
        assert "gap-8" in serialize(h.render())


# ───────────────────────────────────────────────────────────────────────────
# Composition — nested layout
# ───────────────────────────────────────────────────────────────────────────


def test_nested_stacks_render() -> None:
    with render_isolated(), VStack() as outer:
        with HStack(gap="sm"):
            Text("first")
            Text("second")
        Text("trailing")
    out = serialize(outer.render())
    # Every child surfaces in the rendered HTML.
    for word in ("first", "second", "trailing"):
        assert f">{word}<" in out
    # Outer has flex-col, inner has flex-row.
    assert out.count("flex-col") >= 1
    assert out.count("flex-row") >= 1


class TestFlexResponsive:
    """``direction`` and ``gap`` are the GRADED props, so they take a
    ``{breakpoint: value}`` dict. ``align`` / ``justify`` / ``wrap`` do
    not — a binary choice belongs to ``if Screen().is_mobile:``."""

    def test_direction_dict_prefixes_each_breakpoint(self) -> None:
        with render_isolated():
            f = Flex(direction={"base": "col", "md": "row"})
        out = serialize(f.render())
        # ``base`` emits unprefixed, the rest carry their ladder prefix.
        assert "flex-col" in out
        assert "md:flex-row" in out
        assert "md:flex-col" not in out

    def test_gap_dict_prefixes_each_breakpoint(self) -> None:
        with render_isolated():
            f = Flex(gap={"base": "sm", "md": "lg"})
        out = serialize(f.render())
        assert "gap-2" in out
        assert "md:gap-6" in out

    def test_both_axes_at_once(self) -> None:
        with render_isolated():
            f = Flex(direction={"base": "col", "lg": "row"}, gap={"base": "xs", "2xl": "xl"})
        out = serialize(f.render())
        assert "flex-col" in out
        assert "lg:flex-row" in out
        assert "gap-1" in out
        assert "2xl:gap-8" in out

    def test_scalar_still_works(self) -> None:
        # Regression : the dict path must not disturb the scalar path.
        with render_isolated():
            f = Flex(direction="col", gap="lg")
        out = serialize(f.render())
        assert "flex-col" in out
        assert "gap-6" in out
        assert ":" not in out.split('class="')[1].split('"')[0]

    @pytest.mark.parametrize("prop", ["align", "justify"])
    def test_non_graded_prop_rejects_a_dict(self, prop: str) -> None:
        """Le refus arrive à la CONSTRUCTION, pas au rendu.

        Il vivait dans ``Flex.render`` jusqu'au 2026-09-04 ; il est
        depuis dans le socle (``reject_stray_breakpoints``), donc il
        vaut pour les ~100 composants et plus seulement pour deux.
        Ce qu'on vérifie ici, c'est ce qui rend le message UTILE : le
        nom du composant, le nom du prop, et ce qui EST gradué.
        """
        with render_isolated():
            with pytest.raises(ComponentUsageError) as caught:
                Flex(**{prop: {"base": "start", "md": "center"}})
        message = str(caught.value)
        assert f"Flex({prop}=" in message
        assert "does not take a step dict" in message
        assert "``direction``" in message and "``gap``" in message

    def test_unknown_breakpoint_is_refused(self) -> None:
        # ``tablet:`` is a prefix Tailwind never generates — silently dead
        # classes, so we refuse rather than ship a no-op.
        with render_isolated():
            f = Flex(gap={"base": "sm", "tablet": "lg"})
            with pytest.raises(ComponentUsageError, match="unknown breakpoint"):
                f.render()

    @pytest.mark.parametrize("cls", [VStack, HStack])
    def test_shortcuts_inherit_responsive_gap(self, cls: type) -> None:
        with render_isolated():
            s = cls(gap={"base": "sm", "md": "lg"})
        out = serialize(s.render())
        assert "gap-2" in out
        assert "md:gap-6" in out
