"""Unit tests for :class:`bretzel.components.actions.button.Button`."""

from __future__ import annotations

import re

import pytest

from bretzel.components.actions.button import Button
from bretzel.components.base import HandlerError
from bretzel.components.base.testing import render_isolated
from bretzel.components.primitives.text import Text
from bretzel.core.serialize import serialize


# Tailwind ships ``disabled:opacity-50 disabled:cursor-not-allowed`` on
# the button root, so a naive ``" disabled" in out`` would match the
# class string instead of the bare HTML attribute. Match boundary on
# either side : space or quote before, space or ``>`` after.
_BARE_DISABLED_ATTR = re.compile(r'[ "\']disabled[ >]')


# Module-level handler — addressable via ``module::qualname``.
def my_action() -> None:
    pass


# ───────────────────────────────────────────────────────────────────────────
# Construction + label
# ───────────────────────────────────────────────────────────────────────────


class TestLabel:
    def test_positional_label(self) -> None:
        with render_isolated():
            b = Button("Save")
        assert ">Save<" in serialize(b.render())

    def test_no_label_renders_empty_button(self) -> None:
        with render_isolated():
            b = Button()
        out = serialize(b.render())
        assert "<button" in out
        assert "</button>" in out


# ───────────────────────────────────────────────────────────────────────────
# Theme classes — variant / size / modifiers
# ───────────────────────────────────────────────────────────────────────────


class TestTheme:
    @pytest.mark.parametrize(
        ("variant", "expected"),
        [
            # Le PALIER, pas la couleur : la variante décide du rôle
            # peint, le pont (``bz-c-primary``, testé plus bas) décide de
            # la teinte. Deux moitiés, deux tests.
            ("solid", "bg-(--bz-solid)"),
            ("outline", "border-(--bz-solid)"),
            ("ghost", "text-(--bz-text)"),
            ("soft", "bg-(--bz-bg)"),
        ],
    )
    def test_variant_classes(self, variant: str, expected: str) -> None:
        with render_isolated():
            b = Button("X", variant=variant)
        assert expected in serialize(b.render())

    @pytest.mark.parametrize(
        ("size", "expected"),
        [
            ("xs", "h-7"),
            ("sm", "h-8"),
            ("md", "h-10"),
            # lg/xl aligned to the shared control-height ladder (h-12/h-14),
            # so a Button sits flush next to an Input on the same row.
            ("lg", "h-12"),
            ("xl", "h-14"),
        ],
    )
    def test_size_classes(self, size: str, expected: str) -> None:
        with render_isolated():
            b = Button("X", size=size)
        assert expected in serialize(b.render())

    def test_color_substitutes_into_template(self) -> None:
        with render_isolated():
            b = Button("X", color="success", variant="solid")
        out = serialize(b.render())
        # ``{bg_color}`` resolved to ``success`` (semantic — no prefix).
        assert "bg-(--bz-solid)" in out
        assert "bz-c-success" in out
        assert "{bg_color}" not in out

    def test_loading_paints_disabled_variants(self) -> None:
        # ``loading=True`` flips the HTML ``disabled`` attribute so
        # the click is blocked (no double-submit) and the root-slot
        # disabled: variants paint the visual. (The bare-attr angle is
        # covered by ``TestLoading.test_loading_forces_disabled_attr``.)
        with render_isolated():
            b = Button("X", loading=True)
        out = serialize(b.render())
        opening = out.split(">", 1)[0]
        assert " disabled" in opening
        assert "disabled:opacity-50" in out
        assert "disabled:cursor-not-allowed" in out

    def test_disabled_emits_disabled_attr(self) -> None:
        with render_isolated():
            b = Button("X", disabled=True)
        out = serialize(b.render())
        opening = out.split(">", 1)[0]
        assert " disabled" in opening
        assert "disabled:opacity-50" in out

    def test_root_classes_always_present(self) -> None:
        with render_isolated():
            b = Button("X")
        out = serialize(b.render())
        assert "inline-flex" in out
        # V2 visual standard : ``rounded-field`` (12px) — same as V1, the
        # softer-than-Shadcn radius the project's design language goes
        # for. Adjust here if the BUTTON_THEME radius is ever moved.
        assert "rounded-field" in out

    def test_user_classes_appended(self) -> None:
        with render_isolated():
            b = Button("X", classes="my-extra")
        assert "my-extra" in serialize(b.render())


# ───────────────────────────────────────────────────────────────────────────
# Disabled / type — plain reactive props that surface as HTML attrs
# ───────────────────────────────────────────────────────────────────────────


class TestPlainAttrs:
    def test_disabled_renders_as_bare_attr(self) -> None:
        with render_isolated():
            b = Button("X", disabled=True)
        out = serialize(b.render())
        assert _BARE_DISABLED_ATTR.search(out) is not None

    def test_type_default_button(self) -> None:
        with render_isolated():
            b = Button("X")
        assert 'type="button"' in serialize(b.render())

    def test_type_submit(self) -> None:
        with render_isolated():
            b = Button("X", type="submit")
        assert 'type="submit"' in serialize(b.render())


# ───────────────────────────────────────────────────────────────────────────
# Named slots — icon + icon_right
# ───────────────────────────────────────────────────────────────────────────


class TestSlots:
    def test_icon_left_slot_renders_before_label(self) -> None:
        with render_isolated():
            b = Button("Save", icon_left=Text("★"))
        out = serialize(b.render())
        # Icon span comes before the label text.
        assert out.index(">★<") < out.index(">Save<")

    def test_icon_right_slot_after_label(self) -> None:
        with render_isolated():
            b = Button("Next", icon_right=Text("→"))
        out = serialize(b.render())
        assert out.index(">Next<") < out.index(">→<")

    def test_both_slots(self) -> None:
        with render_isolated():
            b = Button("Save", icon_left=Text("★"), icon_right=Text("→"))
        out = serialize(b.render())
        assert out.index(">★<") < out.index(">Save<") < out.index(">→<")


# ───────────────────────────────────────────────────────────────────────────
# Loading — swaps icon_left for Spinner, hides icon_right, forces disabled
# ───────────────────────────────────────────────────────────────────────────


class TestLoading:
    def test_loading_emits_spinner_and_drops_icon_left(self) -> None:
        with render_isolated():
            b = Button("Save", icon_left=Text("★"), loading=True)
        out = serialize(b.render())
        assert ">★<" not in out
        assert 'role="status"' in out

    def test_loading_hides_icon_right(self) -> None:
        with render_isolated():
            b = Button("Next", icon_right=Text("→"), loading=True)
        out = serialize(b.render())
        assert ">→<" not in out

    def test_loading_forces_disabled_attr(self) -> None:
        with render_isolated():
            b = Button("Save", loading=True)
        out = serialize(b.render())
        assert _BARE_DISABLED_ATTR.search(out) is not None

    def test_not_loading_keeps_button_enabled(self) -> None:
        with render_isolated():
            b = Button("Save")
        assert _BARE_DISABLED_ATTR.search(serialize(b.render())) is None


# ───────────────────────────────────────────────────────────────────────────
# Events
# ───────────────────────────────────────────────────────────────────────────


class TestEvents:
    def test_callable_routes_to_hx_post_action(self) -> None:
        with render_isolated() as ctx:
            b = Button("Save", on_click=my_action)
        out = serialize(b.render())
        # V3 wire : native HTMX attribute set targeting the sink.
        assert 'hx-post="/_bretzel/action/' in out
        assert 'hx-trigger="click"' in out
        assert 'hx-target="#bz-sink"' in out
        assert 'hx-swap="innerHTML"' in out
        # The action_id was stashed on the live context.
        assert any("my_action" in aid for aid in ctx.action_registry)

    def test_string_routes_to_bz_on(self) -> None:
        with render_isolated():
            b = Button("X", on_click="$bz.toggle('menu')")
        out = serialize(b.render())
        assert 'bz-on:click="$bz.toggle(' in out
        assert "hx-post" not in out

    def test_lambda_rejected(self) -> None:
        with render_isolated(), pytest.raises(HandlerError, match="Lambda"):
            Button("X", on_click=lambda: None)

    def test_two_server_handlers_rejected(self) -> None:
        # V3 constraint : an element carries ONE hx-post — two server
        # handlers on the same Button raise at construction.
        with render_isolated(), pytest.raises(HandlerError, match="ONE hx-post"):
            Button("X", on_focus=my_action, on_blur=my_action)

    def test_server_handler_coexists_with_client_string(self) -> None:
        # A single server handler can coexist with any number of
        # client-only string handlers.
        with render_isolated():
            b = Button("X", on_focus=my_action, on_blur="$bz.log('bye')")
        out = serialize(b.render())
        assert 'hx-trigger="focus"' in out
        assert 'bz-on:blur="$bz.log(' in out


# ───────────────────────────────────────────────────────────────────────────
# Framework attrs
# ───────────────────────────────────────────────────────────────────────────


def _module_level_click() -> None:
    """Module-level handler — Mode A requires ``module::qualname``
    addressability, so closures are rejected by ``encode_handler_id``."""


class TestFrameworkAttrs:
    def test_id_and_bz_id_present_when_eventful(self) -> None:
        # A click handler triggers the conditional identity emission —
        # the runtime needs to find the button again on swap.
        with render_isolated():
            b = Button("X", on_click=_module_level_click)
        out = serialize(b.render())
        assert f'id="{b.id}"' in out
        assert f'bz-id="{b.id}"' in out

    def test_no_bz_version_even_when_eventful(self) -> None:
        # V3 : ``bz-version`` is dead — scope state lives in a runtime
        # Map keyed by ``bz-id`` and survives morphs without a version
        # guard. Identity is just ``id`` + ``bz-id``.
        with render_isolated():
            b = Button("X", on_click=_module_level_click)
        out = serialize(b.render())
        assert f'id="{b.id}"' in out
        assert f'bz-id="{b.id}"' in out
        assert "bz-version" not in out

    def test_static_button_skips_identity_attrs(self) -> None:
        # No handler, no reactive binding → no need to find this
        # element again ; framework attrs stay off.
        with render_isolated():
            b = Button("X")
        out = serialize(b.render())
        assert f'id="{b.id}"' not in out
        assert "bz-id" not in out
        assert "bz-version" not in out


# ───────────────────────────────────────────────────────────────────────────
# Leaf semantics
# ───────────────────────────────────────────────────────────────────────────


def test_with_block_rejected() -> None:
    with render_isolated():
        b = Button("X")
        with pytest.raises(TypeError, match="leaf"), b:
            pass
