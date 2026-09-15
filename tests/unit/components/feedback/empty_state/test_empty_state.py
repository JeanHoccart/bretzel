"""Unit tests for :class:`bretzel.components.feedback.empty_state.EmptyState`."""

from __future__ import annotations

import re

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.feedback.empty_state import EmptyState
from bretzel.components.primitives.icon.icon import Icon
from bretzel.core.serialize import serialize
from bretzel.state.scopes.client import ClientBinding


class TestStructure:
    def test_renders_root_with_aria(self) -> None:
        with render_isolated():
            out = serialize(
                EmptyState("Nothing here", icon="inbox").render()
            )
        # The framework signals "transient information" via role=status
        # + aria-live=polite so screen readers announce the empty
        # message without interrupting the user.
        assert 'role="status"' in out
        assert 'aria-live="polite"' in out

    def test_title_renders_as_h3(self) -> None:
        with render_isolated():
            out = serialize(
                EmptyState("No tasks yet").render()
            )
        assert "<h3" in out
        assert "No tasks yet" in out

    def test_description_renders_as_paragraph(self) -> None:
        with render_isolated():
            out = serialize(
                EmptyState(
                    "No results",
                    description="Try a different search.",
                ).render()
            )
        assert "<p" in out
        assert "Try a different search." in out

    def test_no_description_no_p_tag(self) -> None:
        """When description is omitted, no empty ``<p>`` is rendered
        — just the title + icon."""
        with render_isolated():
            out = serialize(
                EmptyState("Just title", icon="x").render()
            )
        # No empty paragraph.
        assert "<p" not in out

    def test_icon_renders_inside_box(self) -> None:
        with render_isolated():
            out = serialize(
                EmptyState("No msgs", icon="mail").render()
            )
        # Lucide icon inside the box wrapper.
        assert "lucide:mail" in out
        # The box wrapper has the rounded-full / muted bg.
        assert "rounded-full" in out

    def test_no_icon_no_box(self) -> None:
        """No icon kwarg → no icon box rendered."""
        with render_isolated():
            out = serialize(EmptyState("Bare title").render())
        # No rounded-full box.
        assert "rounded-full" not in out

    def test_actions_slot_via_with_block(self) -> None:
        """``IS_CONTAINER`` — children inside the ``with`` block
        appear in the actions row."""
        from bretzel.components.actions.button import Button

        with render_isolated():
            es = EmptyState("No issues")
            with es:
                Button("Create")
            out = serialize(es.render())
        assert "Create" in out
        # actions row wrapper.
        assert "flex flex-wrap" in out

    def test_no_actions_no_wrapper(self) -> None:
        """No ``with`` body → no empty actions row rendered."""
        with render_isolated():
            out = serialize(
                EmptyState("Alone").render()
            )
        # actions wrapper class only appears when children exist.
        assert "flex flex-wrap items-center justify-center" not in out


class TestSizes:
    @pytest.mark.parametrize(
        ("size", "icon_box_marker"),
        [
            ("xs", "h-8 w-8"),
            ("sm", "h-10 w-10"),
            ("md", "h-14 w-14"),
            ("lg", "h-16 w-16"),
            ("xl", "h-20 w-20"),
        ],
    )
    def test_size_applies_icon_box(
        self, size: str, icon_box_marker: str,
    ) -> None:
        with render_isolated():
            out = serialize(
                EmptyState("X", icon="dot", size=size).render()
            )
        assert icon_box_marker in out

    def test_default_size_is_md(self) -> None:
        with render_isolated():
            out = serialize(
                EmptyState("X", icon="dot").render()
            )
        # md size = h-14 w-14.
        assert "h-14 w-14" in out

    def test_size_reaches_the_glyph_not_just_its_box(self) -> None:
        """Régression : la boîte scalait, le glyphe restait figé.

        La table portait un token ``icon_size`` par palier qui n'était
        branché nulle part — donc ``h-8`` → ``h-20`` (2,5 fois) autour d'un
        glyphe immuable. Le test d'à côté n'assertait que la boîte, la
        moitié qui marchait, d'où la survie du bug.
        """
        seen = []
        for size in ("xs", "md", "xl"):
            with render_isolated():
                out = serialize(
                    EmptyState("X", icon="dot", size=size).render()
                )
            glyph = re.search(r"<iconify-icon class=\"([^\"]*)\"", out)
            assert glyph is not None
            seen.append({
                c for c in glyph.group(1).split()
                if c.startswith("text-") and c != "text-current"
            })
        assert seen[0] != seen[1] != seen[2], (
            f"le glyphe ne suit pas `size=` : {seen}"
        )

    def test_an_explicit_icon_keeps_its_own_size(self) -> None:
        """``size=`` ne re-taille QUE le raccourci string.

        Un ``ui.icon(size=…)` construit par l'appelant porte une intention
        explicite — la table du thème ne doit pas l'écraser.
        """
        with render_isolated():
            out = serialize(
                EmptyState(
                    "X", icon=Icon("dot", size="xs"), size="xl",
                ).render()
            )
        glyph = re.search(r"<iconify-icon class=\"([^\"]*)\"", out)
        assert glyph is not None
        assert "text-xs" in glyph.group(1).split()


class TestReactiveText:
    def test_binding_title_emits_bz_text(self) -> None:
        binding = ClientBinding(
            class_name="UI", instance_key="default",
            field_name="empty_msg", value="No matches",
        )
        with render_isolated():
            out = serialize(EmptyState(binding).render())
        assert "bz-text=" in out
        assert "$bz.state.UI.default.empty_msg" in out

    def test_binding_description_emits_bz_text(self) -> None:
        binding = ClientBinding(
            class_name="UI", instance_key="default",
            field_name="hint", value="Refine your query",
        )
        with render_isolated():
            out = serialize(
                EmptyState("Title", description=binding).render()
            )
        assert "$bz.state.UI.default.hint" in out


class TestBindableSurface:
    def test_bindable_props(self) -> None:
        assert set(EmptyState.BINDABLE_PROPS) == {"title", "description"}

    def test_is_container(self) -> None:
        assert EmptyState.IS_CONTAINER is True
