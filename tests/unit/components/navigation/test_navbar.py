"""Unit tests for :class:`Navbar` / :class:`NavbarSection` / :class:`NavbarItem`."""

from __future__ import annotations

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.navigation.navbar import (
    Navbar,
    NavbarItem,
    NavbarSection,
)
from bretzel.core.serialize import serialize

# ───────────────────────────────────────────────────────────────────────────
# Navbar — root container
# ───────────────────────────────────────────────────────────────────────────


class TestNavbarRoot:
    def test_renders_header_with_role(self) -> None:
        with render_isolated():
            out = serialize(Navbar().render())
        assert "<header" in out
        assert 'role="banner"' in out

    def test_emits_inner_nav(self) -> None:
        """The navbar wraps its children in an inner ``<nav>`` so the
        outer ``<header>`` carries the bar chrome and the inner element
        carries the semantic nav landmark."""
        with render_isolated():
            out = serialize(Navbar().render())
        assert "<nav" in out

    def test_current_path_scope_wired(self) -> None:
        """Navbar owns the same ``current_path`` reactive scope as
        Sidebar (component-local ``bz-data``) so a page hosting both
        stays in sync on partial nav."""
        with render_isolated():
            out = serialize(Navbar().render())
        assert (
            'bz-data="{ current_path: window.location.pathname }"' in out
        )

    def test_no_alpine_residue(self) -> None:
        """V3 purge — the Alpine scope and its two window-level
        watchers are gone. ``bz-on:`` has no ``.window`` modifier, so
        back/forward + externally-triggered partial nav resync is
        deferred to the batch-3 window-event runtime primitive (cf. the
        TODO in ``Navbar.render``) — until then nothing may emit the
        old directives."""
        with render_isolated():
            out = serialize(Navbar().render())
        assert "x-data" not in out
        assert "@popstate.window" not in out
        assert "@htmx:after-request.window" not in out

    def test_sticky_injects_position(self) -> None:
        with render_isolated():
            out = serialize(Navbar(sticky=True).render())
        assert "sticky" in out
        assert "top-0" in out

    def test_sticky_false_omits_position(self) -> None:
        with render_isolated():
            out = serialize(Navbar(sticky=False).render())
        # ``sticky`` class is absent — the default standard variant has
        # no positioning of its own.
        assert "sticky top-0" not in out

    @pytest.mark.parametrize("variant", ["standard", "floating"])
    def test_variant_applies(self, variant: str) -> None:
        with render_isolated():
            out = serialize(Navbar(variant=variant).render())
        if variant == "floating":
            # The floating variant turns the bar into a rounded card.
            assert "rounded-box" in out
        else:
            assert "rounded-box" not in out

    def test_inner_nav_clamps_max_width(self) -> None:
        """The inner ``<nav>`` carries the max-width + horizontal
        padding so the bar bleeds to the screen edges but the content
        stays comfortably readable on wide viewports."""
        with render_isolated():
            out = serialize(Navbar().render())
        assert "max-w-screen-2xl" in out


# ───────────────────────────────────────────────────────────────────────────
# NavbarSection — positional grouping
# ───────────────────────────────────────────────────────────────────────────


class TestNavbarSection:
    def test_renders_div(self) -> None:
        with render_isolated():
            out = serialize(NavbarSection().render())
        assert out.startswith("<div")

    def test_left_default(self) -> None:
        """Default ``side="left"`` → ``me-auto`` (pushes the trailing
        siblings to their corner via flex).

        ⚠️ ``me-auto`` et plus ``mr-auto`` depuis le 2026-09-02 : la
        classe est LOGIQUE, donc elle pousse vers la fin de la ligne et
        non vers la droite. En ``dir="ltr"`` c'est la même chose au
        pixel (mesuré) ; en RTL l'ancienne poussait du mauvais côté.
        """
        with render_isolated():
            out = serialize(NavbarSection().render())
        assert "me-auto" in out

    def test_center_uses_mx_auto(self) -> None:
        with render_isolated():
            out = serialize(NavbarSection(side="center").render())
        assert "mx-auto" in out

    def test_right_uses_ms_auto(self) -> None:
        with render_isolated():
            out = serialize(NavbarSection(side="right").render())
        assert "ms-auto" in out


# ───────────────────────────────────────────────────────────────────────────
# NavbarItem — base attributes
# ───────────────────────────────────────────────────────────────────────────


class TestNavbarItem:
    def test_no_href_renders_as_div(self) -> None:
        with render_isolated():
            out = serialize(NavbarItem("Profile").render())
        assert "<a " not in out
        assert "Profile" in out

    def test_with_href_renders_as_anchor(self) -> None:
        with render_isolated():
            out = serialize(NavbarItem("Docs", href="/docs").render())
        assert "<a " in out
        assert 'href="/docs"' in out

    def test_icon_shortcut_wraps_iconify(self) -> None:
        with render_isolated():
            out = serialize(NavbarItem("Docs", icon="book").render())
        assert "lucide:book" in out

    def test_label_text(self) -> None:
        with render_isolated():
            out = serialize(NavbarItem("Pricing").render())
        assert ">Pricing</span>" in out

    def test_badge_number(self) -> None:
        with render_isolated():
            out = serialize(NavbarItem("Inbox", badge=5).render())
        assert ">5</span>" in out


# ───────────────────────────────────────────────────────────────────────────
# NavbarItem — HTMX wiring (mirrors SidebarItem behaviour)
# ───────────────────────────────────────────────────────────────────────────




# ───────────────────────────────────────────────────────────────────────────
# NavbarItem — active state
# ───────────────────────────────────────────────────────────────────────────


class TestNavbarItemActive:
    def test_active_layer_lives_in_bz_class_only(self) -> None:
        """``bz-class`` never touches the static ``class=""`` attr, so
        the expression carries JUST the conditional active layer — the
        base classes must not be duplicated inside it (V2's Alpine
        ``:class`` needed the base repeated ; V3 must not)."""
        with render_isolated():
            el = NavbarItem("Docs", href="/docs").render()
        bz_class = el.attrs.get("bz-class", "")
        # Active layer present — le RÔLE peint vit dans l'expression…
        assert "bg-(--bz-bg)" in bz_class
        # …et la COULEUR sur l'élément, dans la classe statique.
        assert "bz-c-primary" in el.attrs.get("class", "")
        # …and conditional on the same current_path comparison.
        assert "current_path" in bz_class
        # Base classes stay in the static attribute only.
        assert "group/row" in el.attrs.get("class", "")
        assert "group/row" not in bz_class


# ───────────────────────────────────────────────────────────────────────────
# Integration — full navbar tree
# ───────────────────────────────────────────────────────────────────────────


class TestNavbarIntegration:
    def test_full_tree(self) -> None:
        with render_isolated() as ctx:
            ctx.layout_stack.append("app_layout")
            with Navbar(sticky=True) as nb:
                with NavbarSection(side="left"):
                    NavbarItem("Bretzel", href="/")
                with NavbarSection(side="center"):
                    NavbarItem("Docs",    href="/docs")
                    NavbarItem("Pricing", href="/pricing")
                with NavbarSection(side="right"):
                    NavbarItem("Sign in", href="/login")
            out = serialize(nb.render())

        # All items present.
        assert "Bretzel" in out
        assert "Docs" in out
        assert "Pricing" in out
        assert "Sign in" in out
        # 4 href-bearing items → 4 hx-target attrs.
        assert out.count('hx-target="#outlet_app_layout"') == 4
        # All three sections rendered with their margin-auto classes.
        # ``me-``/``ms-`` (logiques) et non ``mr-``/``ml-`` : cf.
        # ``TestNavbarSection.test_left_default``.
        assert "me-auto" in out
        assert "mx-auto" in out
        assert "ms-auto" in out
