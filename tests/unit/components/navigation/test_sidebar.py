"""Unit tests for :class:`Sidebar` / :class:`SidebarSection` / :class:`SidebarItem`."""

from __future__ import annotations

import re

import pytest

from bretzel.components.base import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.feedback.avatar import Avatar
from bretzel.components.navigation.sidebar import (
    Sidebar,
    SidebarFooter,
    SidebarFooterItem,
    SidebarItem,
    SidebarSection,
    SidebarTitle,
)
from bretzel.components.overlay.dropdown import DropdownItem
from bretzel.components.primitives.icon import Icon
from bretzel.core.serialize import serialize
from bretzel.state.scopes.client import ClientBinding


def _ctx_with_layout(name: str = "app_layout"):
    """Helper : open a render context with a layout pushed on the
    layout_stack so SidebarItem can capture the layout name at
    construction time (same condition as inside a real ``@layout``).
    """
    cm = render_isolated()
    return cm, name


# ───────────────────────────────────────────────────────────────────────────
# Sidebar — root
# ───────────────────────────────────────────────────────────────────────────


class TestSidebarRoot:
    def test_renders_aside_with_role(self) -> None:
        with render_isolated():
            out = serialize(Sidebar().render())
        assert "<aside" in out
        assert 'role="navigation"' in out
        assert 'aria-label="Sidebar"' in out

    def test_current_path_bzdata_wired(self) -> None:
        with render_isolated():
            out = serialize(Sidebar().render())
        assert "current_path" in out
        # V3 : window listeners ride ``$bz.helpers.onWindow`` from
        # ``bz-init`` (no ``.window`` modifier on bz-on). popstate
        # covers browser Back/Forward ; htmx:after-request covers every
        # htmx-driven nav (success + error rollback in one handler with
        # a no-op guard).
        assert "bz-init=" in out
        assert "onWindow('popstate'" in out
        assert "onWindow('htmx:after-request'" in out

    def test_after_request_guards_against_no_op_writes(self) -> None:
        """The after-request handler MUST guard ``current_path`` against
        unchanged values — without the guard every htmx event in the
        page (any button click anywhere) would re-fire
        ``bz-attr:data-active`` / ``bz-class`` / ``bz-attr:aria-current``
        on every SidebarItem, an O(N) reactive cascade for nothing.
        """
        with render_isolated():
            out = serialize(Sidebar().render())
        # Guarded form : compare-then-assign. The serializer hex-escapes
        # ``=`` as ``=`` so the inequality reads ``!==``
        # on the wire (the runtime decodes it back to ``!==`` at
        # directive eval time).
        assert "current_path !== p" in out

    def test_static_open_when_open_false(self) -> None:
        """``open=False`` bakes ``data-open="false"`` so the theme's
        ``data-[open=false]`` selectors fire on the first paint (before
        Alpine boots)."""
        with render_isolated():
            out = serialize(Sidebar(open=False).render())
        assert 'data-open="false"' in out

    def test_reactive_open_when_bound(self) -> None:
        binding = ClientBinding(
            class_name="UI",
            instance_key="default",
            field_name="expanded",
            value=True,
        )
        with render_isolated():
            out = serialize(Sidebar(open=binding).render())
        # ``bz-attr:data-open`` tracks the binding's value directly (no
        # inversion : ``open`` ⇔ ``data-open=true``).
        assert "bz-attr:data-open=" in out
        assert "$bz.state.UI.default.expanded" in out
        # No inverted form leaked anywhere.
        assert "!($bz.state.UI.default.expanded)" not in out

    def test_data_open_stringified_to_dodge_attr_removal(self) -> None:
        """The runtime's ``bz-attr:attr="expr"`` *removes* the attribute
        when ``expr`` evaluates to a boolean ``false`` (the
        boolean-HTML-attr idiom — right for ``disabled`` / ``hidden``,
        catastrophic for data-attrs since the CSS
        ``[data-open="false"]`` selector then never matches and the
        rail-collapse / drawer-slide rules silently no-op).

        The fix : always stringify via a ternary so the runtime writes
        the literal ``"false"`` / ``"true"`` string instead of removing.
        """
        with render_isolated():
            out = serialize(Sidebar().render())
        # The reactive directives must stringify, NOT pass the bare
        # boolean expression. The HTML serializer hex-escapes single
        # quotes as ``'`` ; the runtime decodes them at read time.
        assert (
            "bz-attr:data-open=\"(open) ? 'true' : "
            "'false'\""
        ) in out
        # Anti-regression — the bare-boolean form must NEVER appear.
        # ``bz-attr:data-open="open"`` would silently break the toggle,
        # and the failure mode is invisible in devtools (the attribute
        # just disappears, no error).
        assert 'bz-attr:data-open="open"' not in out

    @pytest.mark.parametrize(
        ("width", "expected"),
        [("sm", "w-48"), ("md", "w-64"), ("lg", "w-80")],
    )
    def test_width_applies(self, width: str, expected: str) -> None:
        with render_isolated():
            out = serialize(Sidebar(width=width).render())
        assert expected in out

    def test_side_is_cut_and_raises(self) -> None:
        """``side=`` a été COUPÉ le 2026-08-15 : une nav latérale vit à
        gauche, et les deux côtés ne coexistent jamais dans la même app.

        Le test porte sur la LEVÉE, pas sur l'absence de la prop : sans
        le garde ``_CUT``, le socle absorberait le kwarg inconnu dans les
        attrs bruts et ``ui.sidebar(side="right")`` émettrait un attribut
        HTML ``side="right"`` en silence, sans rien changer au rendu.
        Même contrat que ``bottom_bar`` pour ``variant=`` / ``sticky=``.
        """
        with render_isolated(), pytest.raises(ComponentUsageError) as err:
            Sidebar(side="right")
        assert "side" in str(err.value)

    def test_border_sits_on_the_right_edge(self) -> None:
        """La bordure vivait dans une table ``sides`` à deux entrées,
        supprimée avec la prop : elle est maintenant dans ``root``."""
        with render_isolated():
            out = serialize(Sidebar().render())
        assert "border-r" in out

    @pytest.mark.parametrize(
        "mode", ["rail", "offcanvas", "overlay", "none"]
    )
    def test_collapse_mode_emits_data_attr(self, mode: str) -> None:
        """Le mode de repli est porté sur la racine en ``data-collapse``
        (ex-``data-variant``, renommé avec la fusion des deux props)."""
        with render_isolated():
            out = serialize(Sidebar(collapsible=mode).render())
        assert f'data-collapse="{mode}"' in out

    def test_rail_is_the_default(self) -> None:
        """Le défaut est ``rail`` : replié, on garde une bande d'icônes
        de 64px plutôt que de disparaître."""
        with render_isolated():
            out = serialize(Sidebar().render())
        assert 'data-collapse="rail"' in out
        # Plus AUCUN gate ``md:`` : c'est le dev qui choisit le mode dans
        # son ``if Screen().is_mobile``, le CSS n'a pas à le contredire.
        # Tant qu'il le faisait, replier sous 768px ne faisait rien.
        assert "data-[open=false]:w-16" in out
        assert "md:data-[open=false]" not in out

    def test_variant_is_cut_and_raises(self) -> None:
        """``variant=`` a été fusionné dans ``collapsible=``. Le kwarg
        LÈVE : sans le garde il serait absorbé en attribut HTML muet et
        la sidebar retomberait en silence sur son mode par défaut."""
        with render_isolated(), pytest.raises(ComponentUsageError) as err:
            Sidebar(variant="drawer")
        assert "collapsible" in str(err.value)

    @pytest.mark.parametrize("legacy", [True, False])
    def test_boolean_collapsible_raises(self, legacy: bool) -> None:
        """``collapsible`` était un BOOL. Un appel resté à l'ancienne
        forme passerait sans bruit — ``True`` n'est aucun des quatre
        modes, donc aucune règle de repli ne serait composée et la
        sidebar cesserait juste de se replier."""
        with render_isolated(), pytest.raises(ComponentUsageError) as err:
            Sidebar(collapsible=legacy)
        assert "n'est plus un booléen" in str(err.value)

    def test_unknown_mode_raises(self) -> None:
        with render_isolated(), pytest.raises(ComponentUsageError):
            Sidebar(collapsible="drawer")

    def test_overlay_leaves_the_flow_with_a_backdrop(self) -> None:
        """``overlay`` est le mode mobile : hors du flux, glissé hors écran
        quand il est fermé, avec un fond assombri **frère** de l'aside.

        ⚠️ Ce test exigeait ``bz-teleport="body"`` sur le fond jusqu'au
        2026-08-15 — il figeait donc la structure qui PORTAIT le défaut.
        Téléporté sous ``<body>``, le fond quittait le contexte
        d'empilement du shell (``fixed inset-0``), son ``z-40`` cessait de
        se comparer au ``z-50`` de l'aside, et il recouvrait la sidebar en
        la floutant. Signalé à l'écran, puis mesuré.

        On assertit désormais l'INVARIANT et non le mécanisme : les deux
        nœuds sont frères sous une racine ``display:contents``, qui ne
        génère aucune boîte donc aucun contexte d'empilement. Le scope y
        remonte aussi — sans quoi le fond, n'ayant plus l'aside au-dessus
        de lui, n'aurait plus rien à lire (mesuré en le livrant : le fond
        restait ouvert, opaque et flou, sidebar fermée).

        La preuve que ça marche est navigateur, pas ici :
        ``tests/runtime_js/test_backdrop_never_covers_its_panel.py`` — le
        défaut est invisible dans le HTML, seule la composition ment.
        """
        with render_isolated():
            out = serialize(Sidebar(collapsible="overlay").render())
        assert "fixed inset-y-0 left-0" in out
        assert "data-[open=false]:-translate-x-full" in out
        assert "bg-black/50" in out
        assert 'bz-teleport="body"' not in out, (
            "le fond est de nouveau téléporté — il quitte le contexte "
            "d'empilement du shell et recouvrira la sidebar"
        )
        assert out.startswith('<div class="contents"'), (
            f"la racine du mode overlay n'est plus le wrapper "
            f"``display:contents`` : {out[:80]!r}"
        )
        assert "bz-data=" in out.split("<aside")[0], (
            "le scope ne vit plus sur la racine — le fond, qui n'a plus "
            "l'aside au-dessus de lui, n'aura rien à lire"
        )

    def test_overlay_carries_its_identity_on_exactly_one_node(self) -> None:
        """UN seul nœud porte l'``id`` — et c'est celui qui écoute.

        ``document.getElementById`` renvoie le PREMIER nœud portant l'id,
        et c'est par là que passe toute l'API impérative : ``sb.toggle()``
        compile en ``getElementById('<id>').dispatchEvent(...)``.

        Mesuré le 2026-08-15 : la racine ``display:contents`` ajoutée pour
        régler l'empilement a reçu l'``id`` du composant par le socle
        (``_stamp_scope_id`` estampille tout hôte de ``bz-data`` sans id)
        alors que l'aside le portait déjà. Deux nœuds, un id : l'événement
        partait sur le wrapper, l'écouteur était sur l'aside, **le
        hamburger est devenu inerte** — sans erreur, avec un état et un
        rendu corrects. Signalé deux fois à l'écran.

        La gate générale (``test_page_has_no_duplicate_html_id``) balaie le
        playground, qui n'instancie AUCUNE sidebar en mode overlay — elle
        n'aurait donc pas vu ce cas. D'où cette assertion ici, au plus près
        du composant.
        """
        with render_isolated():
            out = serialize(Sidebar(collapsible="overlay").render())

        ids = re.findall(r'(?<![\w:-])id="([^"]+)"', out)
        dupes = {k for k in ids if ids.count(k) > 1}
        assert not dupes, (
            f"l'identite du composant est portee par plusieurs noeuds : "
            f"{sorted(dupes)}. getElementById renverra le premier, et si "
            f"l'ecouteur est sur l'autre, l'API imperative est inerte."
        )
        # …et elle vit sur la racine, avec les ecouteurs qu'elle sert.
        root = out.split(">", 1)[0]
        assert "bz-on:bz-toggle" in root, (
            "l'ecouteur imperatif n'est pas sur la racine qui porte l'id"
        )

    def test_overlay_wires_escape_and_scroll_lock(self) -> None:
        """Un menu ouvert au-dessus du contenu se ferme par Escape et ne
        laisse pas la page défiler derrière lui. Les deux helpers sont
        ceux de Dialog/Drawer (``base/_wiring``), pas une réécriture."""
        with render_isolated():
            out = serialize(Sidebar(collapsible="overlay").render())
        assert "escapeKey" in out
        assert "scrollLock" in out

    @pytest.mark.parametrize("mode", ["rail", "offcanvas", "none"])
    def test_flow_modes_never_trap_the_page(self, mode: str) -> None:
        """Replier un rail sur desktop ne doit ni voler la touche Escape
        ni bloquer le scroll : le câblage modal est réservé à
        ``overlay``."""
        with render_isolated():
            out = serialize(Sidebar(collapsible=mode).render())
        assert "escapeKey" not in out
        assert "scrollLock" not in out
        assert "bg-black/50" not in out

    def test_overlay_keeps_its_current_path_resync(self) -> None:
        """``bz-init`` porte DÉJÀ le resync ``current_path``. Le mode
        overlay en veut un second (Escape) : les deux doivent COEXISTER.
        Écraser au lieu de composer est le piège « handler interne
        clobberé » de traps.md."""
        with render_isolated():
            out = serialize(Sidebar(collapsible="overlay").render())
        assert "onWindow('popstate'" in out
        assert "escapeKey" in out

    def test_variant_drawer_collapses_to_zero(self) -> None:
        """The ``drawer`` variant hides the desktop sidebar entirely
        when ``open=false`` (used for focus modes / hideable nav)."""
        with render_isolated():
            out = serialize(Sidebar(collapsible="offcanvas").render())
        assert "data-[open=false]:w-0" in out

    @pytest.mark.parametrize("mode", ["rail", "offcanvas", "none"])
    def test_flow_modes_are_relative(self, mode: str) -> None:
        """Les trois modes DE FLUX sont une colonne ordinaire du layout.

        ``relative`` vit dans la table ``collapse``, pas sur le slot
        ``root`` : ``relative`` et ``fixed`` sont deux utilitaires de même
        spécificité, donc en laisser un sur le root ferait dépendre le
        vainqueur de l'ordre de la feuille Tailwind. Mesuré le
        2026-08-15, c'est exactement ce qui empêchait ``overlay`` de
        sortir du flux (``position: relative`` rendu au lieu de
        ``fixed``).
        """
        with render_isolated():
            out = serialize(Sidebar(collapsible=mode).render())
        # La balise OUVRANTE de l'aside seulement : le panneau de tooltip
        # partagé du rail est lui-même ``fixed``, donc un ``not in out``
        # global testerait autre chose que ce qu'il annonce.
        aside = out[: out.index(">")]
        assert "relative" in aside
        assert "fixed" not in aside

    def test_overlay_is_the_only_fixed_mode(self) -> None:
        with render_isolated():
            out = serialize(Sidebar(collapsible="overlay").render())
        assert "fixed inset-y-0" in out
        # Aucun ``relative`` ne doit rester sur la racine pour le lui
        # disputer — c'est la régression que ce test garde.
        aside = out[: out.index(">")]
        assert "relative" not in aside

    def test_no_mobile_drawer_mechanics(self) -> None:
        """The mobile drawer / topbar / hamburger were stripped — the
        sidebar is desktop chrome only, responsive nav is the app
        layout's job (``if Screen().is_mobile:``). None of the old
        mobile-drawer wiring may leak into the output."""
        with render_isolated():
            out = serialize(Sidebar().render())
        assert "data-mob-open" not in out
        assert "mob_open" not in out
        assert "bz-sidebar-mobile-toggle" not in out
        assert "max-md:fixed" not in out

    def test_imperative_listeners_for_bz_events(self) -> None:
        """The root listens for ``bz-open`` / ``bz-close`` /
        ``bz-toggle`` so external callers using ``.open()`` /
        ``.close()`` / ``.toggle()`` work in both bound and unbound
        modes."""
        with render_isolated():
            out = serialize(Sidebar().render())
        assert "bz-on:bz-open" in out
        assert "bz-on:bz-close" in out
        assert "bz-on:bz-toggle" in out

    def test_sidebar_id_always_emitted(self) -> None:
        """The imperative API targets ``getElementById(self.id)`` so
        the id must always render (``_needs_identity → True``), unlike
        the default heuristic."""
        with render_isolated():
            out = serialize(Sidebar().render())
        assert 'id="' in out


class TestSidebarToggleChevron:
    """⚠️ Le chevron flottant auto n'existe plus (2026-08-21).

    Il se rendait quand la barre n'avait pas de ``SidebarTitle``, en
    ``absolute top-2 right-2`` — c'est-à-dire sous l'ARÊTE cliquable, qui
    prend les 24 px de droite sur toute la hauteur. Mesuré au navigateur
    par ``test_the_sidebar_can_always_be_collapsed`` : le clic n'arrivait
    plus jusqu'à lui, timeout de 30 s sur un bouton pourtant « visible,
    enabled and stable ». Deux commandes au même endroit, dont une
    inatteignable.

    Ce que la barre doit encore garantir n'a pas changé — **une commande
    de repli, et une seule, atteignable** — et c'est ce que ces tests
    vérifient maintenant. Le fait qu'elle soit VISIBLE et qu'elle replie
    vraiment se mesure au navigateur ; ici on garde la forme SSR.
    """

    def test_a_collapsible_sidebar_ships_one_control(self) -> None:
        """Le défaut (``collapsible="rail"``) rend l'arête, et elle seule."""
        with render_isolated():
            out = serialize(Sidebar().render())
        assert out.count("Collapse or expand the sidebar") == 1
        assert "lucide:chevron-left" not in out, (
            "le chevron flottant est revenu : il se rendrait SOUS l'arête, "
            "donc inatteignable."
        )

    def test_collapsible_none_skips_every_control(self) -> None:
        """Opt-out — une barre toujours ouverte n'expose aucune commande."""
        with render_isolated():
            out = serialize(Sidebar(collapsible="none").render())
        assert "Collapse or expand the sidebar" not in out
        assert "Toggle sidebar" not in out

    def test_a_titled_sidebar_does_not_double_its_control(self) -> None:
        """Avec un titre, l'en-tête porte son bouton ET la barre son arête.

        Deux commandes, mais à deux ENDROITS distincts — c'est le cas
        qu'on veut (comme shadcn, qui livre son rail en plus d'un
        déclencheur visible). Ce qui est interdit, c'est deux commandes
        superposées.
        """
        with render_isolated():
            sb = Sidebar()
            with sb:
                SidebarTitle("App", icon="zap")
            out = serialize(sb.render())
        assert out.count("Collapse or expand the sidebar") == 1
        assert out.count('aria-label="Toggle sidebar"') == 1

    def test_chevron_click_flips_binding(self) -> None:
        """When a binding drives ``open``, the chevron flips the
        binding directly (write-through) — no DOM event roundtrip."""
        binding = ClientBinding(
            class_name="UI",
            instance_key="default",
            field_name="expanded",
            value=True,
        )
        with render_isolated():
            out = serialize(Sidebar(open=binding).render())
        # ``@click`` writes to the binding path, not a local Alpine var.
        assert "$bz.state.UI.default.expanded" in out

    def test_chevron_click_flips_local_open_when_unbound(self) -> None:
        """No binding → the sidebar carries an internal Alpine ``open``
        var (initialised from the literal default) so the chevron can
        still toggle without an externally-managed state."""
        with render_isolated():
            out = serialize(Sidebar().render())
        assert "open: true" in out


class TestImperativeAPI:
    def test_toggle_returns_binding_toggle_when_bound(self) -> None:
        """Imperative ``.toggle()`` writes through the binding (single
        source of truth) when one was passed at construct."""
        binding = ClientBinding(
            class_name="UI",
            instance_key="default",
            field_name="nav",
            value=True,
        )
        with render_isolated():
            sb = Sidebar(open=binding)
            expr = sb.toggle()
        assert "$bz.state.UI.default.nav" in expr

    def test_toggle_dispatches_bz_toggle_when_unbound(self) -> None:
        """No binding → the imperative method dispatches a DOM event
        that the sidebar's own ``@bz-toggle`` listener catches and
        flips its internal Alpine ``open`` flag."""
        with render_isolated():
            sb = Sidebar()
            expr = sb.toggle()
        assert "bz-toggle" in expr
        assert "dispatchEvent" in expr

    def test_no_mobile_toggle_method(self) -> None:
        """The mobile drawer was stripped — the sidebar no longer
        exposes a ``.mobile_toggle()`` imperative method."""
        with render_isolated():
            sb = Sidebar()
        assert not hasattr(sb, "mobile_toggle")


# ───────────────────────────────────────────────────────────────────────────
# SidebarSection — label + grouping
# ───────────────────────────────────────────────────────────────────────────


class TestSidebarSection:
    def test_renders_div(self) -> None:
        with render_isolated():
            out = serialize(SidebarSection().render())
        assert out.startswith("<div")

    def test_label_emits_uppercase_header(self) -> None:
        with render_isolated():
            out = serialize(SidebarSection(label="MAIN").render())
        # Section labels hide on collapse via group-data selector.
        assert "MAIN" in out
        assert "uppercase" in out

    def test_no_label_renders_plain_div(self) -> None:
        with render_isolated():
            out = serialize(SidebarSection().render())
        assert "uppercase" not in out


# ───────────────────────────────────────────────────────────────────────────
# SidebarItem — base attributes
# ───────────────────────────────────────────────────────────────────────────


class TestSidebarItem:
    def test_no_href_renders_as_div(self) -> None:
        with render_isolated():
            out = serialize(SidebarItem("Dashboard").render())
        # No href → no anchor tag.
        assert "<a " not in out
        assert "Dashboard" in out

    def test_with_href_renders_as_anchor(self) -> None:
        with render_isolated():
            out = serialize(
                SidebarItem("Dashboard", href="/dashboard").render()
            )
        assert "<a " in out
        assert 'href="/dashboard"' in out

    def test_icon_shortcut_wraps_iconify(self) -> None:
        with render_isolated():
            out = serialize(
                SidebarItem("Dashboard", icon="home").render()
            )
        assert "lucide:home" in out

    def test_label_text(self) -> None:
        with render_isolated():
            out = serialize(SidebarItem("Dashboard").render())
        assert ">Dashboard</span>" in out

    def test_badge_number(self) -> None:
        with render_isolated():
            out = serialize(
                SidebarItem("Issues", badge=12).render()
            )
        assert ">12</span>" in out


# ───────────────────────────────────────────────────────────────────────────
# SidebarTitle — icon arg accepts a name OR a ui.icon(...) component
# ───────────────────────────────────────────────────────────────────────────


class TestSidebarTitle:
    """The ``icon=`` arg accepts a bare name (magic ``primary``) OR a
    built ``ui.icon(...)`` (its own colour). A passed component must NOT
    also render standalone (regression : the logo showed twice)."""

    def _zap_color_classes(self, html: str) -> list[str]:
        import re

        glyphs = re.findall(
            r'<iconify-icon[^>]*icon="lucide:zap"[^>]*class="([^"]*)"', html
        ) + re.findall(
            r'<iconify-icon[^>]*class="([^"]*)"[^>]*icon="lucide:zap"', html
        )
        # La couleur d'un glyphe vit dans son PONT, plus dans sa classe
        # de texte : le palier ``text-(--bz-text)`` est le même pour
        # tous, c'est ``bz-c-<couleur>`` qui les distingue.
        color = r"bz-c-(?:primary|secondary|success|error|warning|info|muted|current)"
        return sorted({c for g in glyphs for c in re.findall(color, g)})

    def test_string_icon_is_primary(self) -> None:
        with render_isolated():
            sb = Sidebar(collapsible="rail")
            with sb:
                SidebarTitle("App", icon="zap")
            out = serialize(sb.render())
        # brand + rail = exactly 2 zap glyphs, all primary.
        assert out.count("lucide:zap") == 2
        assert self._zap_color_classes(out) == ["bz-c-primary"]

    def test_icon_component_not_doubled(self) -> None:
        with render_isolated():
            sb = Sidebar(collapsible="rail")
            with sb:
                SidebarTitle("App", icon=Icon("zap"))
            out = serialize(sb.render())
        # Regression : the standalone Icon must be detached → still 2, not 3.
        assert out.count("lucide:zap") == 2

    def test_icon_component_keeps_its_color(self) -> None:
        with render_isolated():
            sb = Sidebar(collapsible="rail")
            with sb:
                SidebarTitle("App", icon=Icon("zap", color="warning"))
            out = serialize(sb.render())
        assert out.count("lucide:zap") == 2
        # The title must NOT force primary over the icon's own colour.
        assert self._zap_color_classes(out) == ["bz-c-warning"]

    def test_set_prefix_not_double_lucided(self) -> None:
        with render_isolated():
            sb = Sidebar(collapsible="rail")
            with sb:
                SidebarTitle("App", icon="mdi:home")
            out = serialize(sb.render())
        assert "mdi:home" in out
        assert "lucide:mdi" not in out


# ───────────────────────────────────────────────────────────────────────────
# SidebarFooter — account row + popover ; the avatar=ui.avatar(...) case
# ───────────────────────────────────────────────────────────────────────────


class TestSidebarFooter:
    def test_renders_name_subtitle_initials(self) -> None:
        with render_isolated():
            sb = Sidebar()
            with sb:
                with SidebarFooter(name="Jean Hoccart", subtitle="jean@acme.com"):
                    DropdownItem(label="Logout", icon_left="log-out")
            out = serialize(sb.render())
        assert "Jean Hoccart" in out
        assert "jean@acme.com" in out
        assert ">JH<" in out  # initials auto-derived from name

    def test_color_prop_tints_avatar(self) -> None:
        with render_isolated():
            sb = Sidebar()
            with sb:
                with SidebarFooter(name="Jean", color="success"):
                    DropdownItem(label="Logout")
            out = serialize(sb.render())
        # ``{bg_color}`` resolved against the color prop (no literal token).
        assert "bg-(--bz-bg)" in out
        assert "bz-c-success" in out
        assert "{bg_color}" not in out

    def test_avatar_component_not_doubled(self) -> None:
        # Regression : a ``ui.avatar(...)`` passed as a prop must be detached
        # by Component.__init__ so it doesn't ALSO render standalone.
        with render_isolated():
            sb = Sidebar()
            with sb:
                with SidebarFooter(
                    name="Jean Hoccart",
                    avatar=Avatar(initials="JH", color="secondary"),
                ):
                    DropdownItem(label="Logout")
            out = serialize(sb.render())
        assert out.count(">JH<") == 1  # once, not standalone + footer

    def test_trigger_selected_while_open(self) -> None:
        # The footer trigger mirrors the open flag onto ``data-menu-open``
        # so the theme can keep it visually selected while the popover is up.
        with render_isolated():
            sb = Sidebar()
            with sb:
                with SidebarFooter(name="Jean"):
                    SidebarFooterItem(label="Logout")
            out = serialize(sb.render())
        assert 'data-menu-open="false"' in out
        assert "bz-attr:data-menu-open" in out


class TestSidebarFooterItem:
    """Same API as ui.dropdown_item (both are MenuItem) — bound to the
    footer-item theme."""

    def test_renders_label_icon_and_pick_dispatch(self) -> None:
        with render_isolated():
            out = serialize(
                SidebarFooterItem(label="Settings", icon_left="settings").render()
            )
        assert ">Settings</span>" in out
        assert "lucide:settings" in out
        # Closes the enclosing popover on click.
        assert "bz-dropdown-pick" in out

    def test_href_renders_anchor(self) -> None:
        with render_isolated():
            out = serialize(
                SidebarFooterItem(label="Account", href="/me").render()
            )
        assert "<a " in out
        assert 'href="/me"' in out

    def test_color_tints_the_row(self) -> None:
        with render_isolated():
            out = serialize(
                SidebarFooterItem(label="Delete", color="error").render()
            )
        assert "text-error" in out


# ───────────────────────────────────────────────────────────────────────────
# SidebarItem — HTMX wiring under an active layout
# ───────────────────────────────────────────────────────────────────────────


class TestHtmxPartialNav:
    def test_optimistic_click_absent_when_disabled(self) -> None:
        """Disabled items strip every nav channel ; the optimistic
        click handler must be stripped too so a click on the disabled
        row doesn't desync ``current_path`` from the URL.
        """
        with render_isolated() as ctx:
            ctx.layout_stack.append("app_layout")
            item = SidebarItem(
                "Settings", href="/settings", disabled=True,
            )
            out = serialize(item.render())
        assert "bz-on:click=" not in out

    def test_scroll_into_view_on_mount(self) -> None:
        """Partial-nav items carry a ``bz-init`` that scrolls the
        active item into view at page load — covers the long-sidebar
        case (50+ items) where a refresh on a deep route would
        otherwise leave the active highlight off-screen.
        """
        with render_isolated() as ctx:
            ctx.layout_stack.append("app_layout")
            item = SidebarItem("Markdown", href="/markdown")
            out = serialize(item.render())
        assert "bz-init=" in out
        assert "scrollIntoView" in out
        # Guard inside the bz-init : only scroll when this item is the
        # active one (the common case is N-1 items doing nothing).
        assert "data-active" in out
        # ``block: 'nearest'`` makes the scroll a no-op when the item
        # is already visible — important for items already in view.
        assert "nearest" in out

    def test_scroll_into_view_absent_without_layout(self) -> None:
        """No partial-nav (no layout captured) → no bz-init scroll
        helper. These anchors trigger a full page reload anyway, the
        new page wouldn't see this DOM.
        """
        with render_isolated():
            item = SidebarItem("Dashboard", href="/")
            out = serialize(item.render())
        assert "scrollIntoView" not in out


# ───────────────────────────────────────────────────────────────────────────
# SidebarItem — active state
# ───────────────────────────────────────────────────────────────────────────


class TestActiveState:
    def test_explicit_active_true(self) -> None:
        with render_isolated():
            out = serialize(
                SidebarItem("Dashboard", href="/", active=True).render()
            )
        assert 'data-active="true"' in out
        # Active classes appear baked in (not reactive expression).
        assert "bz-attr:data-active" not in out

    def test_explicit_active_false(self) -> None:
        with render_isolated():
            out = serialize(
                SidebarItem("Dashboard", href="/", active=False).render()
            )
        assert 'data-active="false"' in out
        assert "bz-attr:data-active" not in out

    def test_auto_mode_drives_reactive_data_active(self) -> None:
        with render_isolated():
            out = serialize(
                SidebarItem("Issues", href="/issues").render()
            )
        # active=None default → reactive compare against current_path.
        assert "bz-attr:data-active=" in out
        assert "current_path" in out

    def test_binding_drives_reactive_data_active(self) -> None:
        binding = ClientBinding(
            class_name="UI",
            instance_key="default",
            field_name="show_admin",
            value=False,
        )
        with render_isolated():
            out = serialize(
                SidebarItem("Admin", href="/admin", active=binding).render()
            )
        assert "bz-attr:data-active=" in out
        assert "$bz.state.UI.default.show_admin" in out


# ───────────────────────────────────────────────────────────────────────────
# Integration — full sidebar inside a layout
# ───────────────────────────────────────────────────────────────────────────


class TestSidebarIntegration:
    def test_full_tree(self) -> None:
        with render_isolated() as ctx:
            ctx.layout_stack.append("app_layout")
            with Sidebar(collapsible="rail") as sb:
                with SidebarSection(label="MAIN"):
                    SidebarItem("Dashboard", icon="home", href="/")
                    SidebarItem("Issues", icon="bug", href="/issues", badge=3)
                with SidebarSection(label="ACCOUNT"):
                    SidebarItem("Settings", icon="settings", href="/settings")
            out = serialize(sb.render())

        assert "MAIN" in out
        assert "ACCOUNT" in out
        assert "Dashboard" in out
        assert "Issues" in out
        assert "Settings" in out
        # Three href-bearing items → three hx-target attrs.
        assert out.count('hx-target="#outlet_app_layout"') == 3
        # Badge renders.
        assert ">3</span>" in out


# ───────────────────────────────────────────────────────────────────────────
# Scroll layout — pinned header/footer, scrollable middle
# ───────────────────────────────────────────────────────────────────────────


def _cls(node: object) -> str:
    attrs = getattr(node, "attrs", None)
    return attrs.get("class", "") if isinstance(attrs, dict) else ""


def _direct(el: object, needle: str) -> object | None:
    """First DIRECT child of ``el`` whose class contains ``needle``."""
    for child in getattr(el, "children", ()):
        if needle in _cls(child):
            return child
    return None


def _descendants(el: object) -> list[object]:
    """Every node under ``el`` (recursive), excluding ``el`` itself."""
    out: list[object] = []
    if el is None:
        return out
    for child in getattr(el, "children", ()):
        out.append(child)
        out.extend(_descendants(child))
    return out


class TestSidebarScrollLayout:
    """The ``<aside>`` is a rigid ``flex-col h-screen`` frame ; the scroll
    moved OFF it onto a middle ``flex-1 min-h-0 overflow-y-auto`` box.
    Title + footer are pinned ``shrink-0`` siblings of that box — never
    INSIDE it — so an overflowing nav list can't scroll the footer away.
    (Real geometry proven by
    ``tests/probes/probe_sidebar_scroll.py`` ; here we lock the
    DOM shape that makes the pin possible.)"""

    def test_aside_does_not_carry_the_scroll(self) -> None:
        # Regression : ``overflow-y-auto`` used to sit on the aside, so a
        # long list scrolled the whole column (footer included).
        with render_isolated():
            with Sidebar() as s:
                with SidebarSection(label="MAIN"):
                    SidebarItem("Home", icon="home", href="/")
            el = s.render()
        assert "overflow-y-auto" not in _cls(el)

    def test_middle_children_wrapped_in_scroll_box(self) -> None:
        with render_isolated():
            with Sidebar() as s:
                with SidebarSection(label="MAIN"):
                    SidebarItem("Home", icon="home", href="/")
            el = s.render()
        scroll = _direct(el, "min-h-0")
        assert scroll is not None
        cls = _cls(scroll)
        assert "flex-1" in cls and "overflow-y-auto" in cls
        # The section is INSIDE the scroll box, not a direct aside child.
        assert any("flex flex-col gap-0.5" in _cls(c) for c in scroll.children)

    def test_footer_is_sibling_of_scroll_not_inside_it(self) -> None:
        with render_isolated():
            with Sidebar() as s:
                with SidebarSection(label="MAIN"):
                    SidebarItem("Home", icon="home", href="/")
                with SidebarFooter(name="Jean"):
                    SidebarFooterItem(label="Settings")
            el = s.render()
        scroll = _direct(el, "min-h-0")
        footer = _direct(el, "mt-auto")
        assert footer is not None
        # Footer is a DIRECT child of the aside (identity, not value eq) …
        assert any(c is footer for c in el.children)
        # … and NOT nested anywhere inside the scroll box.
        assert not any(d is footer for d in _descendants(scroll))

    def test_title_is_sibling_of_scroll_not_inside_it(self) -> None:
        with render_isolated():
            with Sidebar() as s:
                SidebarTitle("App", icon="box")
                with SidebarSection(label="MAIN"):
                    SidebarItem("Home", icon="home", href="/")
            el = s.render()
        scroll = _direct(el, "min-h-0")
        # The title root is the first ``flex-row`` direct child of the aside.
        title = next(
            (c for c in el.children if "flex-row" in _cls(c)), None
        )
        assert title is not None
        assert not any(d is title for d in _descendants(scroll))

    def test_no_middle_no_scroll_box(self) -> None:
        # A footer-only sidebar (no sections/items) needs no scroll box ;
        # the footer's own ``mt-auto`` still pins it to the bottom.
        with render_isolated():
            with Sidebar() as s:
                with SidebarFooter(name="Jean"):
                    SidebarFooterItem(label="Settings")
            el = s.render()
        assert _direct(el, "min-h-0") is None
        assert _direct(el, "mt-auto") is not None
