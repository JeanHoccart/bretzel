"""Unit tests for reactive label + icon on the Badge component."""

from __future__ import annotations

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.feedback.badge import Badge
from bretzel.core.serialize import serialize
from bretzel.state import ClientState, field
from bretzel.state.scopes.client import ClientBinding, rendering_scope


class _BadgeState(ClientState, persist="memory"):
    label: str = field(default="3")
    icon: str = field(default="check")


class TestStaticBadge:
    def test_literal_label_emits_plain_text_node(self) -> None:
        with render_isolated():
            b = Badge("Active")
        out = serialize(b.render())
        assert ">Active<" in out
        # ``bz-text=`` et non ``bz-text`` : le PALIER de couleur
        # ``text-(--bz-text)`` contient la même sous-chaîne sans être la
        # directive. Deux familles ``bz-*`` qui se ressemblent, une
        # assertion qui doit dire laquelle elle cherche.
        assert "bz-text=" not in out


class TestReactiveBadge:
    def test_label_binding_wraps_in_bz_text_span(self) -> None:
        with render_isolated(), rendering_scope():
            state = _BadgeState()
            b = Badge(state.label)
        out = serialize(b.render())
        assert 'bz-text="$bz.state._BadgeState.default.label"' in out
        # Literal SSR value should NOT appear (emit_text_slot returns
        # Text OR span, never both).
        assert ">3<" not in out

    def test_icon_left_binding_propagates_to_iconify(self) -> None:
        with render_isolated(), rendering_scope():
            state = _BadgeState()
            b = Badge("Active", icon_left=state.icon)
        out = serialize(b.render())
        # The Icon component routes name=binding through $bz._resolveIcon
        # (V3 bz-attr:icon directive).
        assert "bz-attr:icon=\"$bz._resolveIcon($bz.state._BadgeState.default.icon" in out

    def test_icon_right_binding_propagates_to_iconify(self) -> None:
        with render_isolated(), rendering_scope():
            state = _BadgeState()
            b = Badge("Active", icon_right=state.icon)
        out = serialize(b.render())
        assert "bz-attr:icon=\"$bz._resolveIcon($bz.state._BadgeState.default.icon" in out


# ───────────────────────────────────────────────────────────────────────────
# Dismissible — × button, local bz-data close flag, icon_right suppression
# ───────────────────────────────────────────────────────────────────────────


def _close_handler() -> None: ...


class TestDismissible:
    def test_default_static_no_close_button(self) -> None:
        with render_isolated():
            out = serialize(Badge("Static").render())
        assert "<button" not in out
        assert 'bz-data="{open: true}"' not in out

    def test_dismissible_true_emits_close_button(self) -> None:
        """Pure-client dismiss : no handler needed, just
        ``dismissible=True`` and the × button materialises with a
        local ``open`` flag the click flips."""
        with render_isolated():
            out = serialize(
                Badge("X", dismissible=True).render()
            )
        assert "<button" in out
        assert 'aria-label="Remove"' in out

    def test_dismissible_wires_local_open_flag(self) -> None:
        """The local ``bz-data="{open: true}"`` + ``bz-show="open"``
        on the root drives the dismiss : the × button flips
        ``open`` to false ; the badge disappears via the runtime's
        ``bz-show`` without a server round-trip."""
        with render_isolated():
            out = serialize(
                Badge("X", dismissible=True).render()
            )
        assert 'bz-data="{open: true}"' in out
        assert 'bz-show="open"' in out
        # × button flips the flag + dispatches a ``close`` event.
        assert "open = false" in out
        assert "$dispatch('close')" in out

    def test_on_close_alone_also_opts_in(self) -> None:
        """Back-compat shortcut : passing ``on_close=`` alone (no
        ``dismissible=True``) also shows the × button and wires the
        local close flag — same UX as ``dismissible=True,
        on_close=fn``. V3 wiring : the server handler stays on the
        root (``hx-trigger="close"`` + ``hx-post``) ; only the ×
        button dispatches the bubbling ``close`` event, so a click
        on the badge body itself never fires it."""
        with render_isolated():
            out = serialize(
                Badge("X", on_close=_close_handler).render()
            )
        assert "<button" in out
        # Server wiring landed on the root span.
        root_open = out[:out.index(">")]
        assert 'hx-trigger="close"' in root_open
        assert 'hx-post="/_bretzel/action/' in root_open
        # The × button is the only ``close`` dispatcher.
        button_block = out[out.index("<button"):out.index("</button>")]
        assert "$dispatch('close')" in button_block
        # Local close machinery still wired (same as dismissible=True).
        assert 'bz-data="{open: true}"' in out

    def test_dismissible_suppresses_icon_right(self) -> None:
        """When the × is showing, ``icon_right`` is dropped — the
        two would crowd the pill AND give the user two competing
        clickable targets on the right edge. Dismiss wins."""
        with render_isolated():
            out = serialize(
                Badge(
                    "X",
                    icon_right="external-link",
                    dismissible=True,
                ).render()
            )
        # × is rendered.
        assert 'aria-label="Remove"' in out
        # icon_right is NOT.
        assert "external-link" not in out

    def test_icon_right_kept_when_not_dismissible(self) -> None:
        """Regression : ``icon_right`` rendering stays unchanged
        when ``dismissible`` is off and ``on_close`` is absent."""
        with render_isolated():
            out = serialize(
                Badge("X", icon_right="external-link").render()
            )
        assert "external-link" in out
        assert "<button" not in out


class TestBindableSurface:
    def test_dismissible_not_bindable(self) -> None:
        """``dismissible`` n'est plus bindable (règle « driver client,
        sinon serveur » figée 2026-07-16 : ∅). Seul ``label`` l'est."""
        assert "dismissible" not in Badge.BINDABLE_PROPS
        assert Badge.BINDABLE_PROPS == ("label",)

    def test_close_event_declared(self) -> None:
        assert Badge.EVENTS == ("close",)


class TestIconScalesWithSize:
    """The icon shortcut (``icon_left="check"``) must inherit the
    badge's size palette — a ``size="xl"`` badge ships a larger icon
    than a ``size="xs"`` one. Without this, the icon's default
    ``sm`` would lock its rendering regardless of the badge."""

    @pytest.mark.parametrize(
        ("badge_size", "expected_text_class"),
        [
            ("xs", "text-xs"),
            ("sm", "text-xs"),
            ("md", "text-sm"),
            ("lg", "text-sm"),
        ],
    )
    def test_icon_left_text_class_follows_badge_size(
        self, badge_size: str, expected_text_class: str,
    ) -> None:
        import re
        with render_isolated():
            out = serialize(
                Badge("X", icon_left="check", size=badge_size).render()
            )
        # Find the iconify-icon element + grab the size token from
        # its class list.
        m = re.search(r"<iconify-icon[^>]+>", out)
        assert m is not None, "no iconify-icon emitted"
        assert expected_text_class in m.group(0)

    def test_user_passed_icon_instance_keeps_its_own_size(self) -> None:
        """A pre-built Icon instance passed by the caller is an
        explicit choice — Badge must NOT override its size to match
        the badge's palette."""
        from bretzel.components.primitives.icon import Icon

        import re
        with render_isolated():
            # Explicitly size the icon as ``xl`` and put it in a
            # ``sm`` badge — the icon stays ``xl`` (text-lg / text-xl
            # — whichever Icon's theme picks).
            out = serialize(
                Badge(
                    "X",
                    icon_left=Icon("check", size="xl"),
                    size="sm",
                ).render()
            )
        m = re.search(r"<iconify-icon[^>]+>", out)
        assert m is not None
        # ``sm`` badge would normally pick text-xs ; an explicit xl
        # Icon picks a larger token.
        assert "text-xs" not in m.group(0)


class TestDismissibleNotBindable:
    """``dismissible`` a été coupé du bindable (règle « driver client,
    sinon serveur » figée 2026-07-16). Un binding y lève désormais
    ComponentUsageError ; la valeur littérale ``dismissible=True`` reste
    supportée (rendu statique du × — couvert ailleurs)."""

    def test_reactive_dismissible_is_refused(self) -> None:
        from bretzel.components.base.attrs import ComponentUsageError

        binding = ClientBinding(
            class_name="UI", instance_key="default",
            field_name="dismissible", value=False,
        )
        with render_isolated():
            with pytest.raises(ComponentUsageError):
                Badge("X", dismissible=binding)
