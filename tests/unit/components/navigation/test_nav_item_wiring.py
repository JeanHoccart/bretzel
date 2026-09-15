"""Le contrat que les TROIS items de nav partagent — vérifié sur les trois.

``navigation/_wiring.py`` porte le comportement commun de ``NavbarItem``,
``SidebarItem`` et ``BottomBarItem`` : actif dérivé de l'URL, partial-nav
HTMX, garde sur les URLs externes, neutralisation d'un item désactivé. Son
docstring promet que les trois se comportent « à l'identique ».

Jusqu'ici, **rien ne vérifiait cette promesse** : le module n'avait aucun
fichier de test à lui, et chaque composant re-testait le comportement partagé
depuis sa propre page — trois copies des mêmes assertions, avec trois messages
d'erreur différents quand ``_wiring`` bougeait. Et la promesse avait déjà
été trahie deux fois sans que personne ne le voie (l'``aria-disabled``
réactif écrit de deux façons, le badge réactif qui peignait une pastille vide
d'un seul côté — cf. l'en-tête de ``_wiring.py``).

⚠️ Ce fichier est aussi une **gate de complétude** : un quatrième item de nav
doit entrer dans ``ITEMS``, sinon le paramétrage est visiblement incomplet et
la revue le voit. C'est le point qu'un ``test_wiring.py`` testant le helper
tout seul aurait perdu — ici, on prouve que le COMPOSANT appelle le câblage,
pas seulement que le câblage marche.
"""

from __future__ import annotations

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.navigation.bottom_bar import BottomBarItem
from bretzel.components.navigation.navbar import NavbarItem
from bretzel.components.navigation.sidebar import SidebarItem
from bretzel.core.serialize import serialize
from bretzel.state.scopes.client import ClientBinding

ITEMS = [NavbarItem, SidebarItem, BottomBarItem]
_ids = lambda cls: cls.__name__  # noqa: E731 — lisibilité des ids pytest


@pytest.fixture(params=ITEMS, ids=_ids)
def item_cls(request):
    return request.param


# ───────────────────────────────────────────────────────────────────────────
# Partial-nav HTMX
# ───────────────────────────────────────────────────────────────────────────


class TestPartialNav:
    def test_no_htmx_without_an_enclosing_layout(self, item_cls) -> None:
        """Hors layout, l'item retombe sur une ancre simple — rechargement
        complet, ce qui est correct."""
        with render_isolated():
            out = serialize(item_cls("Docs", href="/docs").render())
        assert 'href="/docs"' in out
        assert "hx-get" not in out
        # Pas de flip optimiste non plus : un rechargement complet démonterait
        # la nav de toute façon, le feedback serait perdu.
        assert "bz-on:click=" not in out

    def test_auto_injects_the_outlet_swap_inside_a_layout(self, item_cls) -> None:
        with render_isolated() as ctx:
            ctx.layout_stack.append("app_layout")
            out = serialize(item_cls("Docs", href="/docs").render())
        assert 'hx-get="/docs"' in out
        assert 'hx-target="#outlet_app_layout"' in out
        assert 'hx-swap="morph:innerHTML"' in out
        assert 'hx-push-url="true"' in out

    def test_innermost_layout_wins(self, item_cls) -> None:
        with render_isolated() as ctx:
            ctx.layout_stack.append("app_layout")
            ctx.layout_stack.append("admin_layout")
            out = serialize(item_cls("Users", href="/admin/users").render())
        assert 'hx-target="#outlet_admin_layout"' in out

    def test_external_href_opens_a_tab_and_skips_htmx(self, item_cls) -> None:
        """HTMX irait XHR-fetch l'hôte externe (bloqué par CORS) et le clic
        échouerait en silence."""
        with render_isolated() as ctx:
            ctx.layout_stack.append("app_layout")
            out = serialize(item_cls("GitHub", href="https://github.com/x").render())
        assert 'target="_blank"' in out
        assert 'rel="noopener noreferrer"' in out
        assert "hx-get" not in out
        # Ni flip optimiste : le document courant RESTE sur la page
        # précédente, donc basculer ``current_path`` afficherait un onglet
        # sélectionné alors que rien n'a changé.
        assert "bz-on:click=" not in out

    def test_optimistic_click_flips_current_path(self, item_cls) -> None:
        """Identifiant NU : l'expression résout dans le scope ``bz-data`` de
        la barre parente. Sans ce flip, le surlignage attendrait l'aller-retour."""
        with render_isolated() as ctx:
            ctx.layout_stack.append("app_layout")
            el = item_cls("Docs", href="/docs").render()
        assert el.attrs.get("bz-on:click") == 'current_path = "/docs"'


# ───────────────────────────────────────────────────────────────────────────
# État actif — les trois sources
# ───────────────────────────────────────────────────────────────────────────


class TestActiveState:
    def test_explicit_true_bakes_a_static_attribute(self, item_cls) -> None:
        with render_isolated():
            el = item_cls("Docs", href="/docs", active=True).render()
        assert el.attrs.get("data-active") == "true"
        assert "bz-attr:data-active" not in el.attrs

    def test_explicit_false_bakes_the_string_false(self, item_cls) -> None:
        """La chaîne littérale, pas l'absence d'attribut : les styles
        ``data-[active=false]:hover:*`` des thèmes en dépendent."""
        with render_isolated():
            el = item_cls("Docs", href="/docs", active=False).render()
        assert el.attrs.get("data-active") == "false"

    def test_auto_mode_compares_to_current_path(self, item_cls) -> None:
        with render_isolated():
            el = item_cls("Docs", href="/docs").render()
        expr = el.attrs.get("bz-attr:data-active", "")
        assert "current_path" in expr
        # Ternaire stringifié : ``bz-attr`` retirerait l'attribut sur un
        # ``false`` nu (cf. traps.md § data-attrs stringifiés).
        assert expr.endswith("? 'true' : 'false'")
        assert el.attrs.get("bz-attr:aria-current", "").endswith("? 'page' : null")

    def test_root_href_matches_only_the_root(self, item_cls) -> None:
        """``/`` ne doit pas matcher tout chemin qui commence par ``/``."""
        with render_isolated():
            el = item_cls("Home", href="/").render()
        assert "startsWith" not in el.attrs.get("bz-attr:data-active", "")

    def test_binding_drives_the_reactive_attribute(self, item_cls) -> None:
        binding = ClientBinding(
            class_name="UI", instance_key="default",
            field_name="show_admin", value=False,
        )
        with render_isolated():
            el = item_cls("Admin", href="/admin", active=binding).render()
        expr = el.attrs.get("bz-attr:data-active", "")
        assert "$bz.state.UI.default.show_admin" in expr
        assert expr.endswith("? 'true' : 'false'")

    def test_active_layer_lives_in_bz_class_only(self, item_cls) -> None:
        """``bz-class`` n'ajoute/retire que ce que son expression produit — le
        ``class=`` statique n'est jamais touché, donc l'expression ne doit PAS
        répéter les classes de base (c'était le mécanisme V2 d'Alpine)."""
        with render_isolated():
            el = item_cls("Docs", href="/docs").render()
        bz_class = el.attrs.get("bz-class", "")
        base = el.attrs.get("class", "")
        assert "current_path" in bz_class
        assert base, "la classe de base doit rester dans l'attribut statique"
        assert base.split()[0] not in bz_class


# ───────────────────────────────────────────────────────────────────────────
# Désactivation — a11y, tabulation, canaux de clic
# ───────────────────────────────────────────────────────────────────────────


class TestDisabled:
    def test_every_click_channel_is_stripped(self, item_cls) -> None:
        """Un item désactivé les perd TOUS : ``href``, les ``hx-*``, et le
        flip optimiste — sinon le surlignage se désynchronise de l'URL sans
        navigation pour le réconcilier."""
        with render_isolated() as ctx:
            ctx.layout_stack.append("app_layout")
            el = item_cls("Bientôt", href="/soon", disabled=True).render()
        assert el.attrs.get("aria-disabled") == "true"
        assert el.attrs.get("tabindex") == "-1"
        for channel in ("href", "hx-get", "hx-target", "hx-swap",
                        "hx-push-url", "bz-on:click"):
            assert channel not in el.attrs, channel

    def test_binding_drives_the_reactive_lock(self, item_cls) -> None:
        binding = ClientBinding(
            class_name="UI", instance_key="default",
            field_name="locked", value=False,
        )
        with render_isolated():
            el = item_cls("Admin", href="/admin", disabled=binding).render()
        assert el.attrs.get("bz-attr:aria-disabled", "").endswith(
            "? 'true' : 'false'"
        )
        assert el.attrs.get("bz-attr:tabindex", "").endswith("? '-1' : null")

    def test_no_path_cancels_its_own_cursor(self, item_cls) -> None:
        """L'affordance disabled peint dans les DEUX chemins.

        ``pointer-events-none`` annule ``cursor-not-allowed`` sur le même
        élément — aucun événement de pointeur, aucun curseur peint. Il
        vivait dans ``root``, donc les trois items annonçaient une
        affordance morte (audit du 2026-08-13).

        Une étape intermédiaire ne l'avait retiré que du chemin STATIQUE,
        en le gardant pour le réactif : le strip des canaux de clic étant
        SSR-only, il fallait bien que quelque chose bloque le clic. C'est
        désormais le socle runtime (``$bz._inert``, dérivé
        d'``aria-disabled``), donc la classe ne sert plus nulle part — et
        le curseur peint aussi quand le verrou arrive à chaud.

        ⚠️ Ce test ne prouve pas l'inertie, seulement qu'on ne l'obtient
        plus au prix du curseur. L'inertie est prouvée côté runtime
        (``tests/runtime_js/test_inert_controls.py``).
        """
        binding = ClientBinding(
            class_name="UI", instance_key="default",
            field_name="locked", value=False,
        )
        with render_isolated():
            live = item_cls("Admin", href="/admin", disabled=binding).render()
            static = item_cls("Admin", href="/admin", disabled=True).render()

        for label, el in (("réactif", live), ("statique", static)):
            assert "pointer-events-none" not in el.attrs["class"], (
                f"chemin {label} : `pointer-events-none` est de retour, "
                f"il annulera le `cursor-not-allowed` du même élément"
            )
        assert "cursor-not-allowed" in static.attrs["class"]
        assert "bz-attr:aria-disabled" in live.attrs, (
            "le chemin réactif doit émettre `aria-disabled` — c'est ce "
            "dont le socle dérive l'inertie ET ce que le thème habille"
        )


# ───────────────────────────────────────────────────────────────────────────
# Badge — la pastille réactive
# ───────────────────────────────────────────────────────────────────────────


class TestBadge:
    def test_scalar_badge_is_painted_server_side(self, item_cls) -> None:
        with render_isolated():
            out = serialize(item_cls("Inbox", badge=5).render())
        assert ">5</span>" in out

    def test_binding_makes_a_live_counter_that_folds_at_zero(
        self, item_cls
    ) -> None:
        """``bz-show`` replie la pastille sur un compte falsy — un « 0 non
        lus » disparaît au lieu d'afficher un zéro périmé. C'est l'un des deux
        écarts que la duplication avait laissé dériver."""
        binding = ClientBinding(
            class_name="UI", instance_key="default",
            field_name="unread", value=0,
        )
        with render_isolated():
            out = serialize(item_cls("Inbox", badge=binding).render())
        assert "bz-text" in out
        assert "bz-show" in out
