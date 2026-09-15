"""Unit tests for :class:`bretzel.components.overlay.tooltip.Tooltip`."""

from __future__ import annotations

import pytest

from bretzel.components.actions.button import Button
from bretzel.components.base.testing import render_isolated
from bretzel.components.overlay.tooltip import Tooltip
from bretzel.core.serialize import serialize


class TestStructure:
    def test_root_wraps_trigger_then_panel(self) -> None:
        with render_isolated():
            with Tooltip("Hi") as t:
                Button("Hover me", size="sm")
            out = serialize(t.render())
        # Trigger first, panel second — tab order matches reading order.
        # The panel is identified by ``role="tooltip"``.
        assert out.index("<button") < out.index('role="tooltip"')

    def test_panel_has_role_tooltip(self) -> None:
        with render_isolated():
            with Tooltip("Hi") as t:
                Button("X", size="sm")
            out = serialize(t.render())
        assert 'role="tooltip"' in out

    def test_panel_text_rendered(self) -> None:
        with render_isolated():
            with Tooltip("Helpful copy here.") as t:
                Button("X", size="sm")
            out = serialize(t.render())
        assert ">Helpful copy here.<" in out


def _teleport(el):
    """The ``<template bz-teleport>`` is the last child of the root."""
    return el.children[-1]


def _panel(el):
    """The tooltip panel lives inside the teleport template."""
    return _teleport(el).children[0]


class TestRuntimeWiring:
    """V3 : the Alpine ``x-data`` / ``x-show`` / ``_pos()`` JS is gone.
    The root carries a ``bz-data`` holding the open flag + debounce
    timer + ``_show()`` / ``_hide()`` ; the panel's display + position
    are owned by its ``bz-effect`` (``$bz.helpers.floating``)."""

    def test_bz_data_open_flag(self) -> None:
        with render_isolated():
            with Tooltip("Hi") as t:
                Button("X", size="sm")
            el = t.render()
        bz_data = el.attrs.get("bz-data") or ""
        # The bz-data carries the open flag, the debounce timer slot,
        # and the show/hide methods — assert the structural markers
        # rather than the exact literal (would couple to JS whitespace).
        # ``_pos()`` no longer exists (floating owns positioning).
        assert "open: false" in bz_data
        assert "_t: null" in bz_data
        # ``_show`` / ``_hide`` vivent dans ``$bz.tooltip.scope`` depuis le
        # 2026-07-29 — ils étaient sérialisés par instance en cuisant leur
        # config dans le corps (``if (!(true))``, le délai en littéral).
        # Ce que l'instance porte, ce sont ses DONNÉES.
        assert "$bz.tooltip.scope" in bz_data
        assert "_delay:" in bz_data
        # Sans ``enabled=``, rien à dire : la constante ``_enabled()`` du
        # slab suffit. Surtout, ``_enabled`` ne doit JAMAIS repartir en
        # champ — cf. ``test_enabled_condition_stays_a_method``.
        assert "_enabled" not in bz_data
        assert "_pos()" not in bz_data
        # The panel's display is driven by its bz-effect, not x-show.
        assert "bz-effect" in _panel(el).attrs

    def test_enabled_condition_stays_a_method(self) -> None:
        """Une condition vivante doit être RELUE à chaque survol.

        Elle partait en champ (``_enabled: <expr>``) depuis la bascule
        « config en données » : un champ de ``bz-data`` est évalué une
        seule fois, hors effet, et ``absorb`` en découple le snapshot du
        store — la condition était figée au montage alors que la docstring
        du builder promettait le survol. Seul un corps de méthode est relu.
        """
        with render_isolated():
            with Tooltip("Hi", enabled="window.innerWidth > 600") as t:
                Button("X", size="sm")
            el = t.render()
        bz_data = el.attrs.get("bz-data") or ""
        assert "_enabled() {" in bz_data, (
            f"la condition doit vivre dans un corps de méthode — {bz_data!r}"
        )
        assert "_enabled:" not in bz_data, (
            "champ = évalué une fois au montage, la condition ne suit plus"
        )
        assert "window.innerWidth > 600" in bz_data

    def test_hover_handlers_with_delay(self) -> None:
        with render_isolated():
            with Tooltip("Hi", delay=500) as t:
                Button("X", size="sm")
            el = t.render()
        bz_data = el.attrs.get("bz-data") or ""
        # Le délai passe en DONNÉE (``_delay``), plus en littéral cuit
        # dans un ``setTimeout`` sérialisé — c'était précisément ce qui
        # faisait que deux tooltips de délais différents produisaient deux
        # CODES différents.
        assert "_delay: 500" in bz_data
        assert "setTimeout" not in bz_data
        # Hover handlers ride ``bz-on:mouseenter`` / ``bz-on:mouseleave``.
        assert el.attrs.get("bz-on:mouseenter") == "_show()"
        assert el.attrs.get("bz-on:mouseleave") == "_hide()"

    def test_focus_handlers_for_keyboard_a11y(self) -> None:
        with render_isolated():
            with Tooltip("Hi") as t:
                Button("X", size="sm")
            el = t.render()
        # V3 : focus a11y rides ``bz-on:focusin`` / ``bz-on:focusout``.
        assert el.attrs.get("bz-on:focusin") == "_show()"
        assert el.attrs.get("bz-on:focusout") == "_hide()"


class TestTeleport:
    """The panel teleports to ``<body>`` via ``bz-teleport`` so ancestor
    ``overflow-hidden`` (accordion body, sticky header, table cell)
    can't clip it. Positioning rides ``$bz.helpers.floating``
    (``position: fixed``) on the panel's ``bz-effect``."""

    def test_panel_uses_template_teleport(self) -> None:
        with render_isolated():
            with Tooltip("X") as t:
                Button("Y", size="sm")
            out = serialize(t.render())
        # ``<template bz-teleport="body">`` wraps the panel so the
        # runtime relocates it under <body> at init.
        assert '<template bz-teleport="body">' in out

    def test_panel_has_bz_ref_for_positioning(self) -> None:
        with render_isolated():
            with Tooltip("X") as t:
                Button("Y", size="sm")
            el = t.render()
        # The panel exposes ``bz-ref="bzpanel"`` ; floating anchors it
        # against the root (``bzroot``).
        panel = _panel(el)
        assert panel.attrs.get("bz-ref") == "bzpanel"
        assert "$refs.bzroot" in panel.attrs.get("bz-effect", "")

    def test_panel_uses_fixed_positioning(self) -> None:
        with render_isolated():
            with Tooltip("X") as t:
                Button("Y", size="sm")
            el = t.render()
        # ``fixed`` (substituted for ``absolute`` at render time) is
        # the contract — the panel positions itself relative to the
        # viewport, not any ancestor.
        assert "fixed" in _panel(el).attrs.get("class", "")


class TestPositioning:
    """V3 : the per-side ``_pos()`` JS artefacts are GONE — floating owns
    positioning. The visible artefacts are the ``placement`` string
    handed to floating in the panel's ``bz-effect`` and the panel's
    ``data-side`` (the runtime-resolved side, which the arrow follows)."""

    def test_default_placement_is_auto(self) -> None:
        # No ``position=`` → best-fit : floating gets ``'auto'`` and the
        # panel pre-stamps ``data-side="bottom"`` (overwritten on open).
        with render_isolated():
            with Tooltip("X") as t:
                Button("Y", size="sm")
            el = t.render()
        panel = _panel(el)
        assert "__p = 'auto'" in panel.attrs.get("bz-effect", "")
        assert panel.attrs.get("data-side") == "bottom"

    @pytest.mark.parametrize("position", ["top", "bottom", "left", "right"])
    def test_pinned_placement_flows_through(self, position: str) -> None:
        # A pinned side rides to floating as the placement literal AND
        # pre-stamps ``data-side`` so the arrow points right before JS.
        with render_isolated():
            with Tooltip("X", position=position) as t:
                Button("Y", size="sm")
            el = t.render()
        panel = _panel(el)
        assert f"__p = '{position}'" in panel.attrs.get("bz-effect", "")
        assert panel.attrs.get("data-side") == position

    def test_arrow_follows_data_side(self) -> None:
        # The arrow no longer bakes ONE side : it carries all four
        # ``group-data-[side=…]`` variants, and the panel is a ``group``
        # so the arrow reads the panel's runtime ``data-side``.
        with render_isolated():
            with Tooltip("X") as t:
                Button("Y", size="sm")
            el = t.render()
        panel = _panel(el)
        assert "group" in panel.attrs.get("class", "").split()
        arrow_cls = panel.children[-1].attrs.get("class", "")
        for side, anchor in (
            ("top", "top-full"), ("bottom", "bottom-full"),
            ("left", "left-full"), ("right", "right-full"),
        ):
            assert f"group-data-[side={side}]:{anchor}" in arrow_cls


class TestArrow:
    def test_arrow_always_present(self) -> None:
        # The arrow is unconditional now — there is no arrowless mode.
        with render_isolated():
            with Tooltip("X") as t:
                Button("Y", size="sm")
            out = serialize(t.render())
        # Arrow has rotate-45 + the same surface color as the panel.
        assert "rotate-45" in out


class TestColor:
    """``color=`` accepts any theme color, defaulting to ``"text"``
    for the V1-style neutral dark surface. Semantic colors paint the
    panel + arrow in the matching tinted background."""

    def test_default_color_is_neutral_dark(self) -> None:
        # ``bg-text`` + ``text-background`` = dark panel, light text.
        with render_isolated():
            with Tooltip("X") as t:
                Button("Y", size="sm")
            out = serialize(t.render())
        assert "bg-(--bz-solid)" in out
        assert "bz-c-text" in out

    @pytest.mark.parametrize(
        "color", ["info", "success", "warning", "error", "primary"],
    )
    def test_color_substitutes_into_panel(self, color: str) -> None:
        with render_isolated():
            with Tooltip("X", color=color) as t:
                Button("Y", size="sm")
            out = serialize(t.render())
        assert "bg-(--bz-solid)" in out
        assert f"bz-c-{color}" in out


class TestFullWidthDetection:
    """Tooltip auto-swaps its ``inline-block`` wrapper to ``block w-full``
    when the wrapped trigger is full-width (Input / Form / Textarea /
    etc.). Without this, the trigger collapses to content width — a
    V1 trap re-discovered in V2 (cf ``traps.md`` § Tooltip full-width)."""

    def test_input_inside_with_block_keeps_full_width(self) -> None:
        """Native CM path : ``with ui.tooltip(): ui.input(...)``."""
        from bretzel.components.inputs.input import Input

        with render_isolated():
            with Tooltip("hint") as t:
                Input(placeholder="email")
            out = serialize(t.render())
        # The wrapper class should be ``block w-full`` instead of
        # ``inline-block`` because Input's theme root carries ``w-full``.
        assert "inline-block" not in out.split("</div>")[0]
        assert "block w-full" in out.split("</div>")[0]

    def test_button_keeps_inline_block(self) -> None:
        """Button is NOT full-width — wrapper stays ``inline-block``."""
        with render_isolated():
            with Tooltip("hint") as t:
                Button("Y", size="sm")
            out = serialize(t.render())
        # The wrapper opener should carry ``inline-block``.
        assert "inline-block" in out.split("</div>")[0]

    def test_button_with_user_w_full_class_fills_row(self) -> None:
        """A user-passed ``classes="w-full"`` on the trigger (not just the
        theme root) must make the wrapper full-width — else tooltip'd rows
        come out narrower than their non-tooltip siblings."""
        with render_isolated():
            with Tooltip("hint") as t:
                Button("Y", size="sm", classes="w-full")
            out = serialize(t.render())
        wrapper = out.split("</div>")[0]
        assert "block w-full" in wrapper
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
        # should carry ``block w-full``.
        assert "block w-full" in out

    def test_full_width_path_strips_w_fit_h_fit(self) -> None:
        """When the trigger is full-width, the wrapper switches to
        ``block w-full`` — and must NOT carry leftover ``w-fit`` /
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
    off to the side of the trigger. Cf. ``traps.md`` § "Root inline-
    flex étirée par un parent flex/grid items-stretch"."""

    def test_default_wrapper_carries_w_fit_h_fit(self) -> None:
        with render_isolated():
            with Tooltip("hint") as t:
                Button("X", size="sm")
            out = serialize(t.render())
        wrapper_open = out.split("</div>")[0]
        assert "w-fit" in wrapper_open
        assert "h-fit" in wrapper_open
