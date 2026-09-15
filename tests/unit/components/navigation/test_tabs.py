"""Unit tests for :class:`bretzel.components.navigation.tabs.Tabs`."""

from __future__ import annotations

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.navigation.tabs import Tab, TabPanel, Tabs
from bretzel.core.serialize import serialize
from bretzel.state.scopes.client import ClientBinding


# Module-level handler — encode_handler_id needs an addressable
# qualname (no closures inside test methods).
def _change_handler() -> None:
    pass


def _build_basic_tabs(*, value: str | ClientBinding = "a", **kwargs):
    """Stage a Tabs with two tabs / two panels — used by most tests."""
    with Tabs(value=value, **kwargs) as t:
        Tab("a", label="Alpha")
        Tab("b", label="Bravo")
        with TabPanel("a"):
            pass
        with TabPanel("b"):
            pass
    return t


# ───────────────────────────────────────────────────────────────────────────
# A. Render structure
# ───────────────────────────────────────────────────────────────────────────


class TestStructure:
    def test_renders_root_div_with_xdata(self) -> None:
        with render_isolated():
            out = serialize(_build_basic_tabs().render())
        assert "<div" in out
        assert "bz-data=" in out
        assert "setTab" in out

    def test_tablist_role_and_tabs(self) -> None:
        with render_isolated():
            out = serialize(_build_basic_tabs().render())
        assert 'role="tablist"' in out
        # Each tab carries role="tab".
        assert out.count('role="tab"') == 2

    def test_panels_have_tabpanel_role(self) -> None:
        with render_isolated():
            out = serialize(_build_basic_tabs().render())
        assert out.count('role="tabpanel"') == 2

    def test_tab_buttons_carry_clicks(self) -> None:
        with render_isolated():
            out = serialize(_build_basic_tabs().render())
        # Two tabs → two ``bz-on:click="setTab(...)"`` bindings (the
        # bz-data setter declaration is excluded from the count).
        assert out.count('bz-on:click="setTab(') == 2

    def test_panel_x_show_per_tab_id(self) -> None:
        with render_isolated():
            out = serialize(_build_basic_tabs().render())
        # Each panel toggles via bz-show against its tab id.
        assert "bz-show" in out
        # Both panel ids appear in the bz-show expressions.
        assert '&quot;a&quot;' in out
        assert '&quot;b&quot;' in out


class TestActiveStateExpression:
    def test_active_class_uses_bare_active(self) -> None:
        with render_isolated():
            out = serialize(_build_basic_tabs().render())
        # Directive expressions (``:class``, ``x-show``, ``@click``...)
        # are wrapped with ``with(scope)`` by Alpine, so bare ``active``
        # resolves to the scope's field/getter. ``this`` in a directive
        # context refers to the DOM ELEMENT, not the scope — using
        # ``this.active`` reads ``undefined`` and silently breaks tab
        # selection. ``this.`` stays correct INSIDE the setTab method
        # shorthand (that's a different evaluation context where this
        # IS the scope). Same convention used by Pagination.
        assert "value ===" in out
        # And NOT the wrong shape (the directive references that broke
        # selection in the original implementation) :
        assert ":class=\"this.value" not in out
        assert "x-show=\"this.value" not in out

    def test_aria_selected_reflects_active(self) -> None:
        with render_isolated():
            out = serialize(_build_basic_tabs().render())
        assert ":aria-selected=" in out

    def test_tab_keyboard_index(self) -> None:
        with render_isolated():
            out = serialize(_build_basic_tabs().render())
        # Active tab gets tabindex=0 ; others are -1 (so Tab moves
        # to the active tab from outside).
        assert ":tabindex=" in out


# ───────────────────────────────────────────────────────────────────────────
# B. Reactive contract — literal vs ClientBinding
# ───────────────────────────────────────────────────────────────────────────


class TestLiteralValue:
    def test_local_active_field_initialised(self) -> None:
        with render_isolated():
            out = serialize(_build_basic_tabs(value="b").render())
        # x-data has a local ``active : "b"`` field.
        assert 'value: &quot;b&quot;' in out

    def test_no_hidden_input_without_name(self) -> None:
        # No binding, no on_change → no hidden input.
        with render_isolated():
            out = serialize(_build_basic_tabs(value="a").render())
        assert 'type="hidden"' not in out


class TestServerSyncGating:
    """``_serverSync: ['value']`` re-adopts the active tab id from the
    server on a @refreshable morph — idiomorph preserves the live scope
    signal otherwise, so a server-driven ``value=`` change would never
    reach the DOM (bug : the server playground's ``value`` control moved
    nothing). It must be emitted ONLY when the value is server-backed,
    else an unrelated section refresh would wipe a user's tab click.
    Same gate as Select / Slider / ToggleGroup."""

    def test_literal_value_omits_serversync(self) -> None:
        # A one-time literal initial is client-owned across refreshes.
        with render_isolated():
            out = serialize(_build_basic_tabs(value="a").render())
        assert "_serverSync" not in out

    def test_server_backed_value_keeps_serversync(self) -> None:
        # ``value=server_state.field`` carries a ``field_name`` stamp —
        # the server is authoritative, a re-render should win.
        from bretzel.state.scopes.server import _BoundStr

        with render_isolated():
            out = serialize(
                _build_basic_tabs(value=_BoundStr("b", "tab")).render()
            )
        assert "_serverSync" in out

    def test_binding_value_omits_serversync(self) -> None:
        # Binding mode : the value lives in ``$bz._store`` (patched by the
        # envelope), read directly by the directives — never a scope
        # signal, so no _serverSync.
        binding = ClientBinding(
            class_name="UI", instance_key="default",
            field_name="tab", value="a",
        )
        with render_isolated():
            out = serialize(_build_basic_tabs(value=binding).render())
        assert "_serverSync" not in out


class TestClientBindingValue:
    def _binding(self, *, value: str = "a") -> ClientBinding:
        return ClientBinding(
            class_name="UI",
            instance_key="default",
            field_name="tab",
            value=value,
        )

    def test_value_expr_targets_state_path(self) -> None:
        binding = self._binding(value="b")
        with render_isolated():
            out = serialize(_build_basic_tabs(value=binding).render())
        assert "$bz.state.UI.default.tab" in out

    def test_no_local_active_field_when_bound(self) -> None:
        binding = self._binding(value="b")
        with render_isolated():
            out = serialize(_build_basic_tabs(value=binding).render())
        # Local field is omitted — the binding is the source of truth.
        assert 'value: &quot;b&quot;' not in out

    def test_binding_directives_read_store_directly_no_getter(self) -> None:
        # Regression : a ``get active()`` scope getter is FROZEN by
        # ``absorb`` (03_scope.js evaluates each declared key once and
        # bakes the result into a dead local signal), so tab/panel
        # directives reading it never react to a store write — a click or
        # a Select bound to the same field would move the store while the
        # active tab stays put. Binding mode must therefore read
        # ``$bz.state.<path>`` DIRECTLY in every directive (bz-show /
        # data-selected / aria-selected / tabindex) and carry NO getter.
        # Cf. traps.md § "getter de scope figé par absorb".
        binding = self._binding(value="a")
        with render_isolated():
            out = serialize(_build_basic_tabs(value=binding).render())
        assert "get active" not in out
        # The reactive directives read the tracked store cell, not a
        # scope-local ``active`` name. (``===`` serialises to ``=``.)
        assert "bz-show=\"$bz.state.UI.default.tab ===" in out
        assert (
            "bz-attr:data-selected=\"($bz.state.UI.default.tab ==="
            in out
        )
        # No stray bare ``active`` comparison leaked into a directive.
        assert "&gt;active ===" not in out

    def test_autoname_derives_from_field(self) -> None:
        binding = self._binding(value="a")
        with render_isolated():
            out = serialize(_build_basic_tabs(value=binding).render())
        assert 'type="hidden"' in out
        assert 'name="tab"' in out


class TestEvents:
    def test_change_handler_relocates_to_hidden_input(self) -> None:
        """V3 : a server ``on_change=`` callable emits the ``hx-*``
        action bundle. The root <div> has no native ``change`` event,
        so the bundle is relocated onto the hidden input — the element
        whose ``bz-effect`` actually fires ``change`` when the active
        value moves. Without relocation, ``hx-trigger="change"`` sits
        on a wrapper that never fires and the server call silently
        never happens."""
        binding = ClientBinding(
            class_name="UI",
            instance_key="default",
            field_name="tab",
            value="a",
        )
        with render_isolated():
            with Tabs(value=binding, on_change=_change_handler) as t:
                Tab("a", label="A")
                Tab("b", label="B")
                with TabPanel("a"):
                    pass
                with TabPanel("b"):
                    pass
            out = serialize(t.render())
        # The server action lives inside the hidden input opening tag,
        # not on the wrapper <div>.
        opening = out[out.index("<input"):out.index(">", out.index("<input"))]
        assert "hx-post=" in opening
        assert 'hx-trigger="change"' in opening
        # HMAC v2 : ``data-bz-ts`` (the signed render timestamp) MUST
        # relocate WITH the sig — the bridge reads it off the sig-bearing
        # element. Left on the root, the POST forwards an empty X-Bz-Ts
        # and the action 403s. (``data-bz-sig`` itself is empty in the
        # test rig — no action_key — so we assert the ts, which is
        # always stamped from ``ctx.render_ts``.)
        assert "data-bz-ts=" in opening
        # Root <div> must not retain the relocated server action / ts.
        root_open = out[:out.index(">")]
        assert "hx-post" not in root_open
        assert "hx-trigger" not in root_open
        assert "data-bz-ts" not in root_open

    def test_string_change_handler_relocates_to_hidden_input(self) -> None:
        """A client string ``on_change=`` is emitted as ``bz-on:change``
        and relocated to the hidden input for the same reason."""
        binding = ClientBinding(
            class_name="UI",
            instance_key="default",
            field_name="tab",
            value="a",
        )
        with render_isolated():
            with Tabs(value=binding, on_change="console.log('x')") as t:
                Tab("a", label="A")
                Tab("b", label="B")
                with TabPanel("a"):
                    pass
                with TabPanel("b"):
                    pass
            out = serialize(t.render())
        opening = out[out.index("<input"):out.index(">", out.index("<input"))]
        assert "bz-on:change=" in opening
        root_open = out[:out.index(">")]
        assert "bz-on:change" not in root_open


# ───────────────────────────────────────────────────────────────────────────
# C. Single-style theme — pill badge + CSS underline, sizes
# ───────────────────────────────────────────────────────────────────────────


class TestSingleStyle:
    def test_tablist_carries_baseline_border(self) -> None:
        # The single style hangs the tabs off a shared hairline
        # baseline on the tablist ; the active tab's coloured
        # underline overlaps it.
        with render_isolated():
            out = serialize(_build_basic_tabs().render())
        assert "border-b-(length:--bz-stroke) border-text/10" in out

    def test_label_lives_in_a_pill_badge(self) -> None:
        # Each label rides inside a rounded pill (badge) — the
        # Crédit-Agricole look. The pill is a <span> with
        # rounded-full inside the <button>.
        with render_isolated():
            out = serialize(_build_basic_tabs().render())
        # The label rides in a rounded pill badge (``rounded-selector``, same
        # radius family as Badge).
        assert "rounded-selector" in out
        # The active tint is driven by group-data-[selected] on the
        # pill, reading the button's data-selected. (``=`` serialises
        # to ``=`` inside the class attribute, so match the fill
        # token rather than the raw selector.)
        assert "group-data-[selected" in out
        assert "bg-(--bz-bg)" in out
        assert "bz-c-primary" in out

    def test_active_underline_is_pure_css(self) -> None:
        # The active underline is a border driven by the
        # data-selected attribute — NO JS measurement, no sliding
        # indicator, no ResizeObserver.
        with render_isolated():
            out = serialize(_build_basic_tabs().render())
        assert "data-[selected" in out
        assert "border-(--bz-solid)" in out
        assert "bz-c-primary" in out
        # None of the old sliding-indicator machinery survives.
        assert "updateIndicator" not in out
        assert "data-tab-indicator" not in out
        assert "translateX(" not in out
        assert "ResizeObserver" not in out

    def test_no_variant_or_orientation_kwargs(self) -> None:
        # variant / orientation were dropped ; the strip is a single
        # horizontal style. The root stacks the tablist above panels.
        with render_isolated():
            out = serialize(_build_basic_tabs().render())
        assert "flex-col" in out
        # No stray attribute leaks from a removed prop name.
        assert "orientation=" not in out
        assert "variant=" not in out

    def test_tab_panels_toggle_via_bz_show(self) -> None:
        # Panels switch via ``bz-show`` keyed on the active id. V3
        # dropped the per-attribute ``x-transition`` directives — the
        # cross-fade lives in the stylesheet (theme pass) now — so we
        # assert the toggle wiring, not the transition classes.
        with render_isolated():
            out = serialize(_build_basic_tabs().render())
        assert out.count("bz-show=") == 2
        assert "x-transition" not in out

    def test_initial_active_tab_carries_static_data_selected(self) -> None:
        # The initial active tab gets ``data-selected="true"`` rendered
        # statically by the server so the
        # ``data-[selected=true]:border-{color}`` underline + the pill's
        # ``group-data-[selected=true]:*`` tint pick the active styling up
        # at first paint, BEFORE the runtime initialises. Without this,
        # the active visual flashes in only after hydration (V1's bug,
        # fixed here).
        with render_isolated():
            out = serialize(_build_basic_tabs(value="b").render())
        # Look for the Bravo button carrying data-selected="true". The
        # label now lives in a nested <span> pill, so the capture spans
        # the button body (DOTALL) rather than a flat text run.
        import re
        bravo = re.search(
            r'<button[^>]*data-selected="true"[^>]*>(.*?)</button>',
            out,
            re.DOTALL,
        )
        assert bravo is not None
        assert "Bravo" in bravo.group(1)

    def test_initial_active_panel_skips_display_none(self) -> None:
        # V3 FOUC strategy : non-active panels are pre-stamped
        # ``display:none`` (via ``stamp_display_none``) so they don't
        # flash before the runtime's first ``bz-show`` effect runs. The
        # initial active panel skips the stamp so it's visible at first
        # paint. ``x-cloak`` is gone — V3 has no cloak directive.
        with render_isolated():
            out = serialize(_build_basic_tabs(value="b").render())
        assert "x-cloak" not in out
        import re
        panels = re.findall(r'<div role="tabpanel"[^>]*>', out)
        # The panel for "b" must NOT carry display:none ; the others
        # must.
        for panel in panels:
            if 'bz-show="value === &quot;b&quot;"' in panel:
                assert "display:none" not in panel
            else:
                assert "display:none" in panel

    @pytest.mark.parametrize(
        ("size", "expected"),
        [("sm", "text-xs"), ("md", "text-sm"), ("lg", "text-base")],
    )
    def test_size_applies_to_tab_buttons(
        self, size: str, expected: str
    ) -> None:
        with render_isolated():
            out = serialize(_build_basic_tabs(size=size).render())
        assert expected in out

    def test_color_substitutes_in_active_class(self) -> None:
        with render_isolated():
            out = serialize(
                _build_basic_tabs(color="success").render()
            )
        assert "text-(--bz-text)" in out
        assert "bz-c-success" in out
        assert "{bg_color}" not in out


# ───────────────────────────────────────────────────────────────────────────
# D. Optional features
# ───────────────────────────────────────────────────────────────────────────


class TestDisabledTab:
    def test_disabled_attr_emitted(self) -> None:
        with render_isolated():
            with Tabs(value="a") as t:
                Tab("a", label="A")
                Tab("b", label="B", disabled=True)
                with TabPanel("a"):
                    pass
                with TabPanel("b"):
                    pass
            out = serialize(t.render())
        # Just one disabled token (on the second tab button).
        # We can't simply assert " disabled " because the framework
        # also bakes ``disabled:opacity-50`` etc. into class names —
        # check for the bare attribute via the equality-free form.
        opening_b = out.find("Bravo")  # bravo not actually in this test ; use 'B'
        # Look for ``disabled>`` boolean-attr form on a button.
        # The Bravo button is the second one — find it by its label.
        bb = out[out.index('>B<'):out.index('>B<') + 100] if '>B<' in out else ''
        # Easier check : there's exactly one bare ``disabled`` attr
        # outside class strings — count buttons with disabled=true.
        # Scan all <button …> opening tags.
        cursor = 0
        disabled_buttons = 0
        while True:
            idx = out.find("<button", cursor)
            if idx == -1:
                break
            end = out.find(">", idx)
            tag = out[idx:end]
            if " disabled" in tag.replace('disabled:', '').replace(
                'disabled="', '###'
            ):
                disabled_buttons += 1
            cursor = end + 1
        assert disabled_buttons == 1, out


class TestIconShortcut:
    def test_icon_kwarg_string_wraps_to_iconify(self) -> None:
        with render_isolated():
            with Tabs(value="a") as t:
                Tab("a", label="Alpha", icon="info")
                Tab("b", label="Bravo")
                with TabPanel("a"):
                    pass
                with TabPanel("b"):
                    pass
            out = serialize(t.render())
        # Icon shortcut wraps "info" → iconify-icon with lucide:info.
        assert "lucide:info" in out


class TestTabPanelChildren:
    def test_panel_children_render_inside(self) -> None:
        from bretzel.components.primitives.text import Text

        with render_isolated():
            with Tabs(value="a") as t:
                Tab("a", label="A")
                with TabPanel("a"):
                    Text("Hello panel")
            out = serialize(t.render())
        assert "Hello panel" in out


# ───────────────────────────────────────────────────────────────────────────
# I. L'onglet a une adresse — la moitié SERVEUR
# ───────────────────────────────────────────────────────────────────────────
#
# L'autre moitié (pousser au clic, restaurer au retour) vit dans le
# navigateur et se mesure dans ``tests/probes/probe_tabs_url.py`` — il
# faut une vraie pile d'historique, qu'aucun rendu ne peut simuler.
#
# Ce qui se vérifie ICI : la déclaration atteint le scope, le semis
# depuis la query marche, et surtout **rien de tout ça n'existe sans
# ``url=``**. Ce dernier point est celui qui protège : ce qui part dans
# l'URL part aussi dans l'historique, les logs et le ``Referer``.


class TestUrlAddressable:
    def test_no_url_declared_emits_nothing(self) -> None:
        """La contre-épreuve, en premier parce que c'est elle qui borne.

        Sans elle, « toujours pousser » passerait tous les tests suivants
        et chaque onglet du dépôt publierait son état.
        """
        with render_isolated():
            out = serialize(_build_basic_tabs().render())
        assert "_url" not in out
        assert "_urlInit()" not in out

    def test_declaring_url_puts_the_param_name_in_the_scope(self) -> None:
        """Le NOM, pas la valeur : ``setTab`` le lit pour pousser."""
        with render_isolated():
            out = serialize(_build_basic_tabs(url="onglet").render())
        assert "_url: &quot;onglet&quot;" in out
        assert 'bz-init="_urlInit()"' in out, (
            "sans le câblage du retour, la flèche du navigateur changerait "
            "l'adresse en laissant l'onglet — l'URL mentirait alors sur ce "
            "qui est à l'écran"
        )

    def test_url_is_not_bindable(self) -> None:
        """C'est un nom de paramètre, pas une valeur.

        Le rendre réactif reviendrait à renommer un paramètre d'URL en
        cours de route, ce qui casserait le retour sur les entrées déjà
        empilées.
        """
        binding = ClientBinding(
            class_name="UI", instance_key="default",
            field_name="which", value="onglet",
        )
        with render_isolated():
            with pytest.raises(Exception, match="not bindable"):
                _build_basic_tabs(url=binding)


class TestUrlSeeding:
    """``?onglet=b`` doit OUVRIR l'onglet b, pas le défaut.

    Sans ça un lien partagé montrerait autre chose que ce que
    l'expéditeur voyait — et c'est aussi ce qui fait marcher le retour
    après un rechargement, quand le scope client n'existe plus.
    """

    @staticmethod
    def _with_query(query: dict[str, str], **kwargs) -> str:
        class _Params:
            def __init__(self, data): self._data = data
            def get(self, key, default=None): return self._data.get(key, default)

        class _Request:
            query_params = None

        with render_isolated() as ctx:
            request = _Request()
            request.query_params = _Params(query)
            ctx.request = request
            return serialize(_build_basic_tabs(**kwargs).render())

    def test_the_query_decides_the_open_tab(self) -> None:
        out = self._with_query({"onglet": "b"}, url="onglet", value="a")
        assert "value: &quot;b&quot;" in out, (
            "l'URL ne sème pas l'onglet : un lien partagé ouvrirait le "
            "défaut, donc autre chose que ce que l'expéditeur voyait"
        )

    def test_an_absent_param_leaves_the_default(self) -> None:
        """Même règle que côté état serveur : absent = on ne touche à rien."""
        out = self._with_query({"autre": "b"}, url="onglet", value="a")
        assert "value: &quot;a&quot;" in out

    def test_the_query_is_ignored_without_a_declaration(self) -> None:
        """Un paramètre qui traîne ne pilote pas un onglet qui n'a rien demandé."""
        out = self._with_query({"onglet": "b"}, value="a")
        assert "value: &quot;a&quot;" in out
