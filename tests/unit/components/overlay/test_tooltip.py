"""Unit tests for :class:`bretzel.components.overlay.tooltip.Tooltip`.

Since 2026-10-27 a tooltip renders its WRAPPER and what it says, as
``data-bz-tip*`` attributes; the panel is the page's one ``#bz-tip``
(:func:`tooltip_host`), shown by ``tip.js``. The behaviour — delay,
hiding rules, live text, arrow, placement — is judged in the browser
(``tests/runtime_js/test_a_tooltip_*``); these tests hold the CONTRACT
between the two halves.
"""

from __future__ import annotations

import re

import pytest

from bretzel.components.actions.button import Button
from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.overlay.tooltip import Tooltip
from bretzel.components.overlay.tooltip.tooltip import tooltip_host
from bretzel.core.serialize import serialize
from bretzel.state import ClientExpression
from bretzel.theme import Theme


def fills(wrapper: str) -> bool:
    """The anchored wrapper fills its cell: a one-cell grid, full width, no fit."""
    classes = re.search(r'class="([^"]*)"', wrapper).group(1).split()
    return "grid" in classes and "w-full" in classes and "w-fit" not in classes

def _tip(text="Hi", **kwargs):
    with render_isolated():
        with Tooltip(text, **kwargs) as t:
            Button("X", size="sm")
        return t.render()


class TestStructure:
    def test_the_wrapper_holds_the_trigger_and_says_its_text(self) -> None:
        el = _tip("Helpful copy here.")
        assert "data-bz-tip-root" in el.attrs
        assert el.attrs.get("data-bz-tip") == "Helpful copy here."
        assert "<button" in serialize(el)

    def test_no_panel_and_no_machinery_per_tooltip(self) -> None:
        """The weight claim: no scope, no listener, no teleported panel.

        Before, a tooltip around a button added ~2 KB (measured on the
        kanban board: 35 tooltips, 17 % of the page)."""
        el = _tip()
        out = serialize(el)
        for gone in ("bz-data", "bz-on:", "bz-teleport", 'role="tooltip"', "bz-effect"):
            assert gone not in out, f"{gone} is back on the wrapper"
        with render_isolated():
            bare = serialize(Button("X", size="sm").render())
        assert len(out) - len(bare) < 200, f"a tooltip costs {len(out) - len(bare)} bytes"

    def test_a_bound_text_follows_the_store(self) -> None:
        from bretzel.state import ClientState, field
        from bretzel.state.scopes.client import rendering_scope

        class Hint(ClientState):
            text: str = field(default="live")

        with render_isolated(), rendering_scope():
            with Tooltip(Hint().text) as t:
                Button("X", size="sm")
            el = t.render()
        assert "Hint" in el.attrs.get("bz-attr:data-bz-tip", "")
        assert "data-bz-tip" not in el.attrs

    def test_rich_content_waits_in_an_inert_template(self) -> None:
        from bretzel.components.primitives.text import Text

        with render_isolated():
            with Tooltip(Text("RICH_PROBE")) as t:
                Button("X", size="sm")
            out = serialize(t.render())
        tpl = out.index("<template data-bz-tip-content")
        assert out.index("RICH_PROBE") > tpl, "the rich content is not in the template"
        assert out.index("<button") < tpl, "the trigger fell into the template"


class TestDisabled:
    """``disabled`` is read at HOVER time by the runtime, with ``$el`` =
    the trigger — never frozen at mount (the bug of 2026-07, when it rode
    a ``bz-data`` field)."""

    def test_never_off_says_nothing(self) -> None:
        assert "data-bz-tip-off" not in _tip().attrs
        assert "data-bz-tip-off" not in _tip(disabled=False).attrs

    def test_a_literal_true_is_the_constant(self) -> None:
        assert _tip(disabled=True).attrs.get("data-bz-tip-off") == "true"

    def test_an_expression_rides_verbatim(self) -> None:
        el = _tip(disabled=ClientExpression("window.innerWidth <= 600"))
        assert el.attrs.get("data-bz-tip-off") == "window.innerWidth <= 600"

    def test_a_plain_string_is_refused_with_the_remedy(self) -> None:
        """A string is data (2026-11-07): the last prop where it was code."""
        with pytest.raises(ComponentUsageError, match="ClientExpression"):
            _tip(disabled="window.innerWidth <= 600")


class TestSettings:
    """A setting rides only when it differs from the default — the
    common ``tooltip="Edit"`` stays one attribute."""

    def test_defaults_say_nothing(self) -> None:
        attrs = _tip().attrs
        for name in ("data-bz-tip-position", "data-bz-tip-delay", "data-bz-tip-color", "data-bz-tip-class"):
            assert name not in attrs

    @pytest.mark.parametrize("position", ["top", "bottom", "left", "right"])
    def test_a_pinned_side_rides(self, position: str) -> None:
        assert _tip(position=position).attrs.get("data-bz-tip-position") == position

    def test_a_delay_rides(self) -> None:
        assert _tip(delay=500).attrs.get("data-bz-tip-delay") == "500"

    @pytest.mark.parametrize("color", ["info", "success", "warning", "error", "primary"])
    def test_a_colour_rides(self, color: str) -> None:
        assert _tip(color=color).attrs.get("data-bz-tip-color") == color

    def test_one_panel_slot_override_rides(self) -> None:
        el = _tip(slots={"panel": "ring-2"})
        assert el.attrs.get("data-bz-tip-class") == "ring-2"

    def test_the_colour_paints_the_panel_not_the_trigger(self) -> None:
        """The wrapper encloses a FOREIGN trigger: a bridge there gave the
        trigger the tooltip's colour — a toggle button read ``bz-c-text``
        instead of its group's primary, its selected fill went black.
        The colour now travels as data, to the panel only."""
        from bretzel.components.inputs.toggle_group import ToggleButton, ToggleGroup

        with render_isolated():
            with ToggleGroup(value="a", color="primary") as group:
                ToggleButton("a", label="A", tooltip="Première")
            out = serialize(group.render())
        assert "bz-c-text" not in out, "the tooltip's colour reached the trigger"
        assert "bz-c-primary" in out


class TestHost:
    """The page's ONE panel, rendered by the pipeline."""

    def _host(self, theme=None):
        with render_isolated(theme=theme):
            return tooltip_host()

    def test_the_host_is_the_page_tooltip(self) -> None:
        el = self._host()
        assert el.attrs.get("id") == "bz-tip"
        assert el.attrs.get("role") == "tooltip"
        assert "display:none" in el.attrs.get("style", "").replace(" ", "")

    def test_it_floats_fixed_and_names_its_group(self) -> None:
        cls = self._host().attrs.get("class", "").split()
        assert "fixed" in cls and "absolute" not in cls
        assert "group" in cls
        assert "bz-c-text" in cls, "the neutral colour by default"
        assert "bg-(--bz-solid)" in cls

    def test_the_arrow_follows_the_side(self) -> None:
        arrow = self._host().children[-1].attrs.get("class", "")
        assert "rotate-45" in arrow
        for side, anchor in (("top", "top-full"), ("bottom", "bottom-full"),
                             ("left", "left-full"), ("right", "right-full")):
            assert f"group-data-[side={side}]:{anchor}" in arrow

    def test_the_delay_comes_from_the_budget(self) -> None:
        assert self._host().attrs.get("data-bz-tip-delay") == str(Tooltip.DEFAULT_DELAY_MS)

    def test_the_app_theme_reaches_every_tooltip(self) -> None:
        """``Theme(components={"tooltip": …})`` restyles THE panel — so
        every tooltip of the page at once."""
        theme = Theme(components={"tooltip": {"slots": {"panel": "absolute HOST_PROBE"}}})
        assert "HOST_PROBE" in self._host(theme).attrs.get("class", "")


class TestFullWidthDetection:
    """Tooltip auto-swaps its ``inline-flex`` wrapper to a one-cell
    ``grid grid-cols-1 w-full`` (2026-11-06; it was ``block w-full``, which
    did not hand the cell's height down)
    when the wrapped trigger is full-width (Input / Form / Textarea /
    etc.). Without this, the trigger collapses to content width — a
    V1 trap re-discovered in V2."""

    def test_input_inside_with_block_keeps_full_width(self) -> None:
        """Native CM path : ``with ui.tooltip(): ui.input(...)``."""
        from bretzel.components.inputs.input import Input

        with render_isolated():
            with Tooltip("hint") as t:
                Input(placeholder="email")
            out = serialize(t.render())
        # The wrapper should fill instead of hugging,
        # ``inline-flex`` because Input's theme root carries ``w-full``.
        assert "inline-flex" not in out.split("</div>")[0]
        assert fills(out.split("</div>")[0])

    def test_button_keeps_inline_flex(self) -> None:
        """Button is NOT full-width — wrapper stays ``inline-flex``."""
        with render_isolated():
            with Tooltip("hint") as t:
                Button("Y", size="sm")
            out = serialize(t.render())
        # The wrapper opener should carry ``inline-flex``.
        assert "inline-flex" in out.split("</div>")[0]

    def test_button_with_user_w_full_class_fills_row(self) -> None:
        """A user-passed ``classes="w-full"`` on the trigger (not just the
        theme root) must make the wrapper full-width — else tooltip'd rows
        come out narrower than their non-tooltip siblings."""
        with render_isolated():
            with Tooltip("hint") as t:
                Button("Y", size="sm", classes="w-full")
            out = serialize(t.render())
        wrapper = out.split("</div>")[0]
        assert fills(wrapper)
        assert "w-fit" not in wrapper

    def test_universal_modifier_input_keeps_full_width(self) -> None:
        """Universal modifier path : ``ui.input(tooltip="hint")``.

        Different code path — the tooltip wrapper's _children is set
        to the RENDERED Element (not the Component). Full-width
        detection must still kick in by reading the ``class`` attr
        of that Element.
        """
        from bretzel.components.inputs.input import Input

        with render_isolated():
            i = Input(placeholder="email", tooltip="hint")
            out = serialize(i.render())
        # The tooltip wrap is around the input, so the outer <div>
        # should fill.
        assert fills(out)

    def test_full_width_path_strips_w_fit_h_fit(self) -> None:
        """When the trigger is full-width, the wrapper switches to
        a one-cell grid that fills — and must NOT carry leftover ``w-fit`` /
        ``h-fit`` tokens from the default root slot (Tailwind ordering
        of ``w-full w-fit`` is non-deterministic and the input would
        collapse to content width)."""
        from bretzel.components.inputs.input import Input

        with render_isolated():
            with Tooltip("hint") as t:
                Input(placeholder="email")
            wrapper_open = serialize(t.render()).split("</div>")[0]
        assert "w-fit" not in wrapper_open
        assert "h-fit" not in wrapper_open


class TestWrapperResistsStretch:
    """The tooltip wrapper must SHRINK to its trigger's content size,
    not get stretched by a vstack / grid parent with the default
    ``align-items: stretch``. Without ``w-fit h-fit`` on the wrapper,
    ``_pos()`` reads a stretched bounding rect and the panel floats
    off to the side of the trigger."""

    def test_default_wrapper_carries_w_fit_h_fit(self) -> None:
        with render_isolated():
            with Tooltip("hint") as t:
                Button("X", size="sm")
            out = serialize(t.render())
        wrapper_open = out.split("</div>")[0]
        assert "w-fit" in wrapper_open
        assert "h-fit" in wrapper_open
