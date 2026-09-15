"""Unit tests for :class:`BottomBar` / :class:`BottomBarItem`."""

from __future__ import annotations

import pytest

from bretzel.components.base import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.navigation.bottom_bar import BottomBar, BottomBarItem
from bretzel.core.serialize import serialize
from bretzel.core.tree import Element
from bretzel.state.scopes.client import ClientBinding

# ───────────────────────────────────────────────────────────────────────────
# BottomBar — root container
# ───────────────────────────────────────────────────────────────────────────


class TestBottomBarRoot:
    def test_renders_nav_landmark(self) -> None:
        with render_isolated():
            out = serialize(BottomBar().render())
        assert out.startswith("<nav")

    def test_always_sticky(self) -> None:
        """Il n'y a PAS de prop : une tab bar est toujours collée au bord.
        Une barre qui s'en va au scroll n'est plus une tab bar."""
        with render_isolated():
            out = serialize(BottomBar().render())
        assert "sticky" in out
        assert "bottom-0" in out

    def test_sticky_stays_in_flow_so_no_spacer_node(self) -> None:
        """Le choix ``sticky`` plutôt que ``fixed`` tient à ça : un seul
        nœud racine, donc les kwargs universels (``classes=`` / ``style=`` /
        ``visible=`` / ``tooltip=``) restent applicables. Un
        ``Fragment(spacer, barre)`` les perdrait en silence."""
        with render_isolated():
            node = BottomBar().render()
        assert isinstance(node, Element)
        assert "fixed" not in str(node.attrs.get("class", ""))

    def test_reserves_the_home_indicator_area(self) -> None:
        """Sans ce padding, le dernier onglet passe sous la barre gestuelle
        de l'iPhone. Sur un écran sans encoche, ``env()`` vaut 0."""
        with render_isolated():
            out = serialize(BottomBar().render())
        assert "pb-[env(safe-area-inset-bottom)]" in out

    @pytest.mark.parametrize("cut", ["variant", "sticky"])
    def test_cut_kwarg_is_refused_not_absorbed(self, cut: str) -> None:
        """Les deux axes livrés puis coupés (2026-08-09) lèvent au lieu
        d'être absorbés. Sans ce garde, le socle range le kwarg inconnu dans
        les attrs bruts et `ui.bottom_bar(sticky=False)` émettrait un
        attribut HTML `sticky="false"` **en silence**, sans rien changer au
        rendu — d'autant plus tentant que la navbar, dont ce composant est
        le miroir, a gardé les deux."""
        with render_isolated(), pytest.raises(ComponentUsageError) as err:
            BottomBar(**{cut: False})
        assert cut in str(err.value)
        assert "root" in str(err.value)          # l'échappatoire est nommée

    def test_one_declaration_per_css_property(self) -> None:
        """Deux utilitaires concurrents de même spécificité laisseraient
        l'ordre de la feuille Tailwind trancher, pas l'ordre du `class=`
        (cf. traps.md). Le thème n'en déclare donc qu'un par propriété."""
        with render_isolated():
            cls = BottomBar().render().attrs["class"].split()
        assert [c for c in cls if c.startswith("bg-")] == ["bg-surface/95"]
        assert [c for c in cls if c.startswith("border")] == [
            "border-t-(length:--bz-stroke)", "border-text/10",
        ]
        assert [c for c in cls if c in ("static", "sticky", "fixed",
                                        "relative", "absolute")] == ["sticky"]

    def test_current_path_scope_wired(self) -> None:
        """Même scope que Navbar et Sidebar — une page qui monte plusieurs
        navs reste d'accord avec elle-même sur l'item actif."""
        with render_isolated():
            out = serialize(BottomBar().render())
        assert 'bz-data="{ current_path: window.location.pathname }"' in out

    def test_resync_listeners_wired(self) -> None:
        """Le bug que la navbar a porté jusqu'au 2026-07-27 : sans ces deux
        écoutes, le surlignage se décolle de l'URL au premier back."""
        with render_isolated():
            el = BottomBar().render()
        init = el.attrs.get("bz-init", "")
        assert "popstate" in init
        assert "htmx:after-request" in init

    def test_children_land_in_the_inner_row(self) -> None:
        with render_isolated():
            with BottomBar() as bar:
                BottomBarItem("Accueil", href="/")
            out = serialize(bar.render())
        assert "Accueil" in out
        assert "flex flex-row" in out

    def test_binding_on_a_layout_prop_raises(self) -> None:
        """Le composant n'a AUCUN axe — ``BINDABLE_PROPS`` est ``()``, pas
        ``None``, donc un binding sur un kwarg universel bindable-only reste
        refusé explicitement plutôt qu'accepté puis jeté en silence."""
        binding = ClientBinding(
            class_name="UI", instance_key="default",
            field_name="pinned", value=True,
        )
        with render_isolated(), pytest.raises(ComponentUsageError):
            BottomBar(sticky=binding)      # coupé ET non-bindable


# ───────────────────────────────────────────────────────────────────────────
# BottomBarItem — structure d'un onglet
# ───────────────────────────────────────────────────────────────────────────


class TestBottomBarItem:
    def test_no_href_renders_as_div(self) -> None:
        with render_isolated():
            out = serialize(BottomBarItem("Profil").render())
        assert "<a " not in out
        assert "Profil" in out

    def test_with_href_renders_as_anchor(self) -> None:
        with render_isolated():
            out = serialize(BottomBarItem("Accueil", href="/").render())
        assert "<a " in out
        assert 'href="/"' in out

    def test_equal_width_tabs(self) -> None:
        """``flex-1`` sur chaque onglet : c'est l'identité de la tab bar, et
        ce qui la sépare de la pilule au contenu de NavbarItem."""
        with render_isolated():
            el = BottomBarItem("Accueil", href="/").render()
        assert "flex-1" in el.attrs.get("class", "")

    def test_icon_sits_above_the_label(self) -> None:
        with render_isolated():
            el = BottomBarItem("Accueil", icon="home").render()
        assert "flex-col" in el.attrs.get("class", "")
        # icon_wrap puis label, dans cet ordre.
        assert len(el.children) == 2
        assert "lucide:home" in serialize(el.children[0])
        assert "Accueil" in serialize(el.children[1])

    def test_icon_shortcut_is_upsized_for_touch(self) -> None:
        """Le raccourci string est ré-emballé en ``Icon(size="lg")`` : 24px,
        l'ordre de grandeur d'une cible tactile, là où le défaut ``md`` rend
        du 18px calibré pour une ligne de texte."""
        with render_isolated():
            out = serialize(BottomBarItem("Accueil", icon="home").render())
        assert "text-2xl" in out

    def test_caller_built_icon_keeps_its_own_size(self) -> None:
        """On ne re-taille QUE le raccourci — un ``ui.icon(size=…)`` construit
        par l'appelant garde sa taille (même geste que EmptyState)."""
        from bretzel.components.primitives.icon.icon import Icon

        with render_isolated():
            out = serialize(
                BottomBarItem("Accueil", icon=Icon("home", size="xs")).render()
            )
        assert "text-xs" in out
        assert "text-2xl" not in out

    def test_label_only_emits_no_icon_wrapper(self) -> None:
        with render_isolated():
            el = BottomBarItem("Profil").render()
        assert len(el.children) == 1
        assert "Profil" in serialize(el.children[0])

    def test_badge_is_anchored_to_the_icon_not_the_tab(self) -> None:
        """L'onglet est bien plus large que son contenu (``flex-1``) : un
        badge ancré à SON coin flotterait dans le vide. Il vit donc dans le
        wrapper relatif qui entoure l'icône."""
        with render_isolated():
            el = BottomBarItem("Alertes", icon="bell", badge=3).render()
        wrap = el.children[0]
        assert "relative" in wrap.attrs.get("class", "")
        assert len(wrap.children) == 2          # icône + pastille
        assert ">3</span>" in serialize(wrap.children[1])

    def test_component_badge_keeps_its_own_look(self) -> None:
        """Un Component passé en badge ne reçoit que le PLACEMENT. Mesuré
        avant la coupure des deux slots : il ressortait avec `bg-error` (du
        thème de l'onglet) ET `bg-success/15` (le sien), deux `text-[10px]`
        et deux couleurs de texte. Il rendait vert en dev par chance d'ordre
        de feuille — `error` étant généré APRÈS `success`, un build compilé
        aurait viré au rouge."""
        from bretzel.components.feedback.badge.badge import Badge

        with render_isolated():
            el = BottomBarItem(
                "Alertes", icon="bell",
                badge=Badge("new", color="success", size="xs"),
            ).render()
        pill = el.children[0].children[1]
        cls = pill.attrs["class"]
        assert "absolute" in cls                  # le placement, lui, s'applique
        assert "bg-error" not in cls              # le look du parent, non
        assert "text-error-foreground" not in cls

    def test_scalar_badge_gets_the_default_pill(self) -> None:
        """Le scalaire est le seul cas où le framework doit inventer un
        visuel — là, le look par défaut s'applique."""
        with render_isolated():
            el = BottomBarItem("Alertes", icon="bell", badge=3).render()
        cls = el.children[0].children[1].attrs["class"]
        assert "absolute" in cls
        assert "bg-error" in cls

    def test_badge_binding_drives_a_live_counter(self) -> None:
        binding = ClientBinding(
            class_name="UI", instance_key="default",
            field_name="unread", value=0,
        )
        with render_isolated():
            out = serialize(
                BottomBarItem("Alertes", icon="bell", badge=binding).render()
            )
        assert "bz-text" in out
        # ``bz-show`` replie la pastille sur un compte falsy (« 0 non lus »
        # disparaît au lieu d'afficher un zéro périmé).
        assert "bz-show" in out

    def test_binding_on_a_non_bindable_prop_raises(self) -> None:
        binding = ClientBinding(
            class_name="UI", instance_key="default",
            field_name="target", value="/x",
        )
        with render_isolated(), pytest.raises(ComponentUsageError):
            BottomBarItem("Accueil", href=binding)


# ───────────────────────────────────────────────────────────────────────────
# BottomBarItem — câblage HTMX (partagé mot pour mot avec NavbarItem)
# ───────────────────────────────────────────────────────────────────────────




# ───────────────────────────────────────────────────────────────────────────
# BottomBarItem — état actif
# ───────────────────────────────────────────────────────────────────────────


class TestBottomBarItemActive:
    def test_active_layer_recolours_instead_of_filling(self) -> None:
        """Sur une tab bar, l'onglet courant se signale par la COULEUR de son
        icône et de son label — pas par un fond plein comme la pilule d'une
        navbar."""
        with render_isolated():
            el = BottomBarItem("Accueil", href="/", color="accent").render()
        bz_class = el.attrs.get("bz-class", "")
        assert "text-(--bz-text)" in bz_class
        # Le pont vit sur l'ÉLÉMENT, pas dans l'expression : c'est la
        # classe statique qui nomme la couleur, le ``bz-class`` ne
        # porte que le rôle peint quand l'onglet est actif.
        assert "bz-c-accent" in str(el.attrs.get("class", ""))
        assert "bg-accent" not in bz_class
        # Les classes de base restent dans l'attribut statique seul.
        assert "group/tab" in el.attrs.get("class", "")
        assert "group/tab" not in bz_class


# ───────────────────────────────────────────────────────────────────────────
# Intégration — l'arbre complet
# ───────────────────────────────────────────────────────────────────────────


class TestBottomBarIntegration:
    def test_full_tree(self) -> None:
        with render_isolated() as ctx:
            ctx.layout_stack.append("app_layout")
            with BottomBar() as bar:
                BottomBarItem("Accueil",   icon="home",   href="/")
                BottomBarItem("Recherche", icon="search", href="/search")
                BottomBarItem("Alertes",   icon="bell",   href="/alerts",
                              badge=3)
                BottomBarItem("Profil",    icon="user",   href="/me")
            out = serialize(bar.render())

        assert out.count('hx-target="#outlet_app_layout"') == 4
        for label in ("Accueil", "Recherche", "Alertes", "Profil"):
            assert label in out
        assert ">3</span>" in out
