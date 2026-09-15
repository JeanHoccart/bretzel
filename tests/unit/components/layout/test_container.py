"""Unit tests for :class:`bretzel.components.layout.container.Container`."""

from __future__ import annotations

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.layout.container import Container
from bretzel.components.primitives.text import Text
from bretzel.core.serialize import serialize


class TestDefaults:
    def test_default_render(self) -> None:
        with render_isolated():
            c = Container()
        out = serialize(c.render())
        # Default width="lg" → max-w-5xl ; root slot adds mx-auto w-full
        # + baked px-6 py-8.
        for cls in ("mx-auto", "w-full", "px-6", "py-8", "max-w-5xl"):
            assert cls in out
        # Default tag is <div>.
        assert out.startswith("<div")
        assert out.endswith("</div>")


class TestWidths:
    @pytest.mark.parametrize(
        ("width", "expected"),
        [
            ("sm",  "max-w-2xl"),
            ("md",  "max-w-3xl"),
            ("lg",  "max-w-5xl"),
            ("xl",  "max-w-7xl"),
            ("2xl", "max-w-screen-2xl"),
        ],
    )
    def test_width_emits_clamp(self, width: str, expected: str) -> None:
        with render_isolated():
            c = Container(width=width)
        assert expected in serialize(c.render())

    def test_width_full_emits_no_clamp(self) -> None:
        # ``full`` opts out of the max-width clamp entirely. The root
        # slot (``mx-auto w-full px-6 py-8``) still ships.
        with render_isolated():
            c = Container(width="full")
        out = serialize(c.render())
        assert "max-w-" not in out
        # Still centered and padded — the clamp opt-out doesn't
        # disable the surrounding chrome.
        assert "mx-auto" in out
        assert "px-6" in out

    def test_unknown_width_silently_drops(self) -> None:
        # Mirrors the Flex/Stack pattern : an unknown lookup falls
        # through to no class rather than raising. Lets future
        # widths land in the theme without breaking the constructor.
        with render_isolated():
            c = Container(width="nonsense")
        out = serialize(c.render())
        assert "max-w-" not in out
        # Root slot still emitted.
        assert "mx-auto" in out


class TestEscapeHatches:
    def test_user_classes_appended(self) -> None:
        with render_isolated():
            c = Container(classes="my-extra")
        assert "my-extra" in serialize(c.render())

    def test_tag_override(self) -> None:
        # Container is a layout primitive — override the tag for
        # semantic HTML (<main>, <section>, …).
        with render_isolated():
            c = Container(tag="main")
        out = serialize(c.render())
        assert out.startswith("<main")
        assert out.endswith("</main>")

    def test_with_block_collects_children(self) -> None:
        with render_isolated(), Container() as c:
            Text("inside")
        out = serialize(c.render())
        assert ">inside<" in out

    def test_no_identity_attrs_when_static(self) -> None:
        # Bare layout primitives carry no reactive binding, no Alpine
        # expression, no event handler → the framework skips emitting
        # id / bz-id / bz-version. Matches Flex/Stack behaviour.
        with render_isolated():
            c = Container()
        out = serialize(c.render())
        assert "bz-id" not in out
        assert "bz-version" not in out
