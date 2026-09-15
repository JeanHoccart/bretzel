"""Unit tests for :class:`bretzel.components.data.accordion.Accordion`."""

from __future__ import annotations

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.data.accordion import Accordion, AccordionItem
from bretzel.core.serialize import serialize
from bretzel.state.scopes.client import ClientBinding

def _synced_keys(out: str) -> set[str]:
    """Les clés réellement re-semées.

    ``_serverSync`` porte la clé de VALEUR (conditionnelle) ET la config
    server-owned préfixée ``_`` (inconditionnelle) : la simple présence du
    marker ne dit donc plus rien sur la valeur, il faut lire les clés.
    """
    import html as _html
    import re as _re
    keys: set[str] = set()
    for raw in _re.findall(r"_serverSync: \[([^\]]*)\]", _html.unescape(out)):
        keys |= {k.strip().strip("'\"") for k in raw.split(",") if k.strip()}
    return keys




# Module-level handler — encode_handler_id needs an addressable
# qualname (no closures inside test methods).
def _change_handler() -> None:
    pass


def _build_basic_accordion(
    *,
    value: str | ClientBinding = "a",
    **kwargs,
) -> Accordion:
    """Stage an Accordion with three items — used by most tests."""
    with Accordion(value=value, **kwargs) as acc:
        with AccordionItem("a", label="Alpha"):
            pass
        with AccordionItem("b", label="Bravo"):
            pass
        with AccordionItem("c", label="Charlie"):
            pass
    return acc


class TestServerSyncGating:
    """``_serverSync: ['value']`` re-adopts the value from the server
    on a @refreshable morph — idiomorph preserves the ``expanded`` signal
    otherwise, so ``value=state.field`` would never move the UI. Emitted
    ONLY when server-backed, else an unrelated refresh wipes the client's
    expand/collapse. Same gate as Tabs / Select / ToggleGroup."""

    def test_literal_value_omits_serversync(self) -> None:
        with render_isolated():
            out = serialize(_build_basic_accordion(value="a").render())
        assert "value" not in _synced_keys(out)

    def test_server_backed_value_keeps_serversync(self) -> None:
        from bretzel.state.scopes.server import _BoundStr

        with render_isolated():
            out = serialize(
                _build_basic_accordion(value=_BoundStr("a", "sec")).render()
            )
        assert "value" in _synced_keys(out)

    def test_server_backed_multiple_keeps_serversync(self) -> None:
        from bretzel.state.scopes.server import _BoundList

        with render_isolated():
            out = serialize(
                _build_basic_accordion(
                    value=_BoundList(["a", "b"], "secs"), multiple=True
                ).render()
            )
        assert "value" in _synced_keys(out)

    def test_binding_value_omits_serversync(self) -> None:
        binding = ClientBinding(
            class_name="UI", instance_key="default",
            field_name="sec", value="a",
        )
        with render_isolated():
            out = serialize(_build_basic_accordion(value=binding).render())
        assert "value" not in _synced_keys(out)


# ───────────────────────────────────────────────────────────────────────────
# A. Render structure
# ───────────────────────────────────────────────────────────────────────────


class TestStructure:
    def test_renders_root_div_with_bzdata(self) -> None:
        with render_isolated():
            out = serialize(_build_basic_accordion().render())
        assert "<div" in out
        assert "bz-data=" in out
        # Five methods on the local scope.
        assert "isOpen(" in out
        assert "toggle(" in out
        assert "expand(" in out
        assert "collapse(" in out
        assert "expandAll(" in out
        assert "collapseAll(" in out

    def test_three_items_three_headers(self) -> None:
        with render_isolated():
            out = serialize(_build_basic_accordion().render())
        # Each item → one <button type="button"> header.
        # Other buttons may exist in the page chrome, but in this
        # isolated test only the headers appear.
        assert out.count('<button type="button"') == 3

    def test_headers_aria_controls_match_body_id(self) -> None:
        with render_isolated():
            out = serialize(_build_basic_accordion().render())
        # Both header and body should appear with linked ids :
        # aria-controls=... AND a region body with the same id +
        # aria-labelledby pointing back.
        assert 'aria-controls=' in out
        assert 'role="region"' in out
        assert 'aria-labelledby=' in out

    def test_chevron_renders_per_item(self) -> None:
        with render_isolated():
            out = serialize(_build_basic_accordion().render())
        # Three items → three chevrons.
        assert out.count('chevron-down') == 3

    def test_body_uses_grid_template_rows_animation(self) -> None:
        """Body height animates via the grid-template-rows trick :
        a 1-col grid whose row track moves between ``0fr`` (collapsed)
        and ``1fr`` (expanded). Adapts to actual content height
        without the ``max-h-screen`` cap bug."""
        with render_isolated():
            out = serialize(_build_basic_accordion().render())
        # Static class includes the transition + grid-template-rows
        # property explicit (Tailwind arbitrary-value syntax).
        assert "transition-[grid-template-rows]" in out
        # Each item carries the reactive bz-class object-syntax that
        # both adds the active size class and removes the opposite.
        # The two row classes live exclusively in bz-class (no static
        # SSR row class). A @refreshable morph strips them back to the
        # SSR baseline, but the afterSwap rescan re-applies them — the
        # per-bind managed set in the bz-class handler makes that
        # re-apply actually stick (cf. runtime_js morph regression +
        # traps.md § "bz-class perdue après un morph").
        assert out.count("bz-class") >= 3
        assert "grid-rows-[1fr]" in out
        assert "grid-rows-[0fr]" in out
        # The inner clip element receives ``min-h-0 overflow-hidden``
        # so the grid can squeeze it below natural height.
        assert "min-h-0 overflow-hidden" in out

    def test_root_listens_to_imperative_commands(self) -> None:
        with render_isolated():
            out = serialize(_build_basic_accordion().render())
        # All five imperative commands listened on the root (V3
        # ``bz-on:bz-<command>`` directives).
        for evt in (
            "bz-on:bz-expand=",
            "bz-on:bz-collapse=",
            "bz-on:bz-toggle=",
            "bz-on:bz-expand-all=",
            "bz-on:bz-collapse-all=",
        ):
            assert evt in out

    def test_initially_open_item_has_data_open_true(self) -> None:
        with render_isolated():
            out = serialize(_build_basic_accordion(value="b").render())
        # SSR : the initially-open header gets data-open="true" so
        # the chevron rotation lands before Alpine boots.
        assert 'data-open="true"' in out
        assert 'aria-expanded="true"' in out

    def test_initially_closed_body_carries_grid_rows_0fr(self) -> None:
        with render_isolated():
            out = serialize(_build_basic_accordion(value="a").render())
        # SSR : closed items render with ``grid-rows-[0fr]`` in the
        # bz-class object — no flash before the runtime hydrates, no
        # display:none needed. ``aria-hidden=true`` for AT users.
        assert "grid-rows-[0fr]" in out
        assert 'aria-hidden="true"' in out

    def test_initially_open_body_carries_grid_rows_1fr(self) -> None:
        with render_isolated():
            out = serialize(_build_basic_accordion(value="b").render())
        # The open item gets ``grid-rows-[1fr]`` in its bz-class object.
        assert "grid-rows-[1fr]" in out


# ───────────────────────────────────────────────────────────────────────────
# B. type=single vs multiple
# ───────────────────────────────────────────────────────────────────────────


class TestTypeSingle:
    def test_default_type_is_single(self) -> None:
        with render_isolated():
            out = serialize(_build_basic_accordion().render())
        # Le comportement vit dans ``$bz.accordion.single`` (runtime) —
        # on vérifie donc QUELLE variante est spreadée, pas la forme du JS
        # sérialisé. Figer la chaîne rendait un refactor correct
        # indistinguable d'une régression.
        assert "$bz.accordion.single" in out
        assert "$bz.accordion.multi" not in out

    def test_single_initial_value_is_string(self) -> None:
        with render_isolated():
            out = serialize(_build_basic_accordion(value="b").render())
        # x-data carries expanded: "b" — not an array.
        assert 'value: &quot;b&quot;' in out
        assert "value: []" not in out

    def test_single_collapsible_true_allows_clear(self) -> None:
        with render_isolated():
            out = serialize(
                _build_basic_accordion(
                    value="a", collapsible=True
                ).render()
            )
        # ``collapsible`` passe désormais en DONNÉE — c'était une
        # constante cuite dans le corps de ``toggle`` (``if (true)``), ce
        # qui faisait que deux accordéons de configs différentes
        # produisaient deux CODES différents.
        assert "_collapsible: true" in out

    def test_single_collapsible_false_blocks_clear(self) -> None:
        with render_isolated():
            out = serialize(
                _build_basic_accordion(
                    value="a", collapsible=False
                ).render()
            )
        assert "_collapsible: false" in out


class TestTypeMultiple:
    def _build_multi(
        self,
        *,
        value=None,
        **kwargs,
    ) -> Accordion:
        if value is None:
            value = ["a"]
        with Accordion(
            multiple=True, value=value, **kwargs
        ) as acc:
            with AccordionItem("a", label="A"):
                pass
            with AccordionItem("b", label="B"):
                pass
            with AccordionItem("c", label="C"):
                pass
        return acc

    def test_multiple_uses_indexof(self) -> None:
        with render_isolated():
            out = serialize(self._build_multi().render())
        # Sémantique de liste → la variante ``multi`` du scope partagé.
        assert "$bz.accordion.multi" in out
        assert "$bz.accordion.single" not in out

    def test_multiple_initial_value_is_array(self) -> None:
        with render_isolated():
            out = serialize(
                self._build_multi(value=["a", "b"]).render()
            )
        # x-data carries expanded as a JS array.
        assert "value: [" in out

    def test_multiple_expand_all_writes_all_ids(self) -> None:
        with render_isolated():
            out = serialize(self._build_multi().render())
        # expandAll() writes the full id list to expanded.
        # The list is computed at render time from the children.
        assert "[&quot;a&quot;, &quot;b&quot;, &quot;c&quot;]" in out

    def test_multiple_collapse_all_clears_to_empty_array(self) -> None:
        with render_isolated():
            out = serialize(self._build_multi().render())
        # ``collapseAll`` vide toujours en mode multi — le comportement
        # est dans le scope partagé, pas dans l'instance. Ce qui reste
        # vérifiable ici, c'est que l'instance porte bien la variante
        # multi et son état de liste.
        assert "$bz.accordion.multi" in out
        assert "value: [" in out


# ───────────────────────────────────────────────────────────────────────────
# C. Reactive contract — literal vs ClientBinding
# ───────────────────────────────────────────────────────────────────────────


class TestLiteralValue:
    def test_local_expanded_field_initialised(self) -> None:
        with render_isolated():
            out = serialize(
                _build_basic_accordion(value="b").render()
            )
        assert 'value: &quot;b&quot;' in out

    def test_no_hidden_input_without_name(self) -> None:
        with render_isolated():
            out = serialize(
                _build_basic_accordion(value="a").render()
            )
        assert 'type="hidden"' not in out


class TestClientBindingValue:
    def _binding(self, *, value="a") -> ClientBinding:
        return ClientBinding(
            class_name="UI",
            instance_key="default",
            field_name="expanded",
            value=value,
        )

    def test_value_path_resolves(self) -> None:
        binding = self._binding(value="b")
        with render_isolated():
            out = serialize(
                _build_basic_accordion(value=binding).render()
            )
        assert "$bz.state.UI.default.expanded" in out

    def test_no_local_expanded_field_when_bound(self) -> None:
        binding = self._binding(value="b")
        with render_isolated():
            out = serialize(
                _build_basic_accordion(value=binding).render()
            )
        # Binding mode reads / writes the state path directly inside
        # the methods — no local ``expanded`` field literal, and (V3)
        # no ``get expanded()`` getter either (bz-data has none).
        assert "get expanded(" not in out
        assert 'value: &quot;b&quot;' not in out
        assert "$bz.state.UI.default.expanded" in out

    def test_autoname_derives_from_field(self) -> None:
        binding = self._binding(value="a")
        with render_isolated():
            out = serialize(
                _build_basic_accordion(value=binding).render()
            )
        assert 'type="hidden"' in out
        assert 'name="expanded"' in out

    def test_multiple_hidden_value_is_json_stringify(self) -> None:
        binding = ClientBinding(
            class_name="UI",
            instance_key="default",
            field_name="expanded",
            value=["a"],
        )
        with render_isolated():
            with Accordion(multiple=True, value=binding) as acc:
                with AccordionItem("a", label="A"):
                    pass
                with AccordionItem("b", label="B"):
                    pass
            out = serialize(acc.render())
        # The hidden input's :value uses JSON.stringify so the array
        # survives one round-trip through form data.
        assert "JSON.stringify" in out


class TestChangeDispatch:
    """V3 dispatch contract : the change event is fired by a reactive
    ``bz-effect`` on the hidden form input — NOT from inside the
    bz-data methods (a bz-data helper only sees ``$el`` / ``$bz``, so
    ``$refs`` / ``$nextTick`` are out of reach). The effect watches the
    input's value expression, bootstraps quietly, and dispatches a
    bubbling ``change`` on a real mutation. The methods themselves just
    mutate ``expanded`` — no inline dispatch plumbing."""

    def _bound_accordion(self) -> Accordion:
        # The hidden-input change effect only exists when a name is in
        # play (binding mode autonames it).
        binding = ClientBinding(
            class_name="UI",
            instance_key="default",
            field_name="expanded",
            value="a",
        )
        return _build_basic_accordion(value=binding)

    def test_change_effect_dispatches_on_real_mutation(self) -> None:
        with render_isolated():
            out = serialize(self._bound_accordion().render())
        # The effect lives on the hidden input, bootstraps via
        # ``$el._bzLast``, and dispatches a bubbling change.
        assert "bz-effect=" in out
        assert "$el._bzLast" in out
        assert "new Event(" in out and "change" in out
        assert "bubbles: true" in out

    def test_methods_do_not_inline_dispatch(self) -> None:
        with render_isolated():
            out = serialize(self._bound_accordion().render())
        # No leftover V2 ``_emitChange`` / ``$refs`` plumbing inside the
        # bz-data method bodies.
        assert "_emitChange" not in out
        assert "$refs" not in out


class TestEvents:
    def test_change_handler_relocates_to_hidden_input(self) -> None:
        """V3 : a callable ``on_change`` emits the native HTMX action
        set (``hx-post`` + ``hx-trigger`` + …). Those keys must ride the
        hidden ``<input>`` (which carries ``name`` + ``value``), NOT the
        root ``<div>`` (no name/value → empty FormData — cf.
        ``traps.md`` § "bz-event:change sur un div")."""
        binding = ClientBinding(
            class_name="UI",
            instance_key="default",
            field_name="expanded",
            value="a",
        )
        with render_isolated():
            with Accordion(
                value=binding, on_change=_change_handler
            ) as acc:
                with AccordionItem("a", label="A"):
                    pass
                with AccordionItem("b", label="B"):
                    pass
            out = serialize(acc.render())
        # The action set lives inside the hidden input opening tag.
        opening = out[out.index("<input"):out.index(">", out.index("<input"))]
        assert "hx-post=" in opening
        assert 'hx-trigger="change"' in opening
        # It must NOT remain on the root wrapper <div>.
        root_open = out[:out.index(">")]
        assert "hx-post=" not in root_open
        assert "hx-trigger=" not in root_open

    def test_string_change_handler_relocates_to_hidden_input(self) -> None:
        """A string ``on_change`` emits ``bz-on:change`` — same
        relocation onto the hidden input."""
        binding = ClientBinding(
            class_name="UI",
            instance_key="default",
            field_name="expanded",
            value="a",
        )
        with render_isolated():
            with Accordion(
                value=binding, on_change="console.log('changed')"
            ) as acc:
                with AccordionItem("a", label="A"):
                    pass
                with AccordionItem("b", label="B"):
                    pass
            out = serialize(acc.render())
        opening = out[out.index("<input"):out.index(">", out.index("<input"))]
        assert "bz-on:change=" in opening
        root_open = out[:out.index(">")]
        assert "bz-on:change=" not in root_open


# ───────────────────────────────────────────────────────────────────────────
# D. Theme frame + sizes
# ───────────────────────────────────────────────────────────────────────────


class TestThemeFrame:
    def test_root_is_the_opinionated_bordered_frame(self) -> None:
        # One structure : an outer border + rounded corners wrapping the
        # stack, with a thin internal divider on each item (``variant``
        # removed — the gapped-card / borderless looks are theme
        # overrides, not props).
        with render_isolated():
            out = serialize(_build_basic_accordion().render())
        assert "border-(length:--bz-stroke) border-text/10 rounded-box" in out
        assert "border-b-(length:--bz-stroke) border-text/10 last:border-b-0" in out


class TestThemeSizes:
    @pytest.mark.parametrize(
        ("size", "marker"),
        [
            ("xs", "px-3 py-2 text-xs"),
            ("sm", "px-3.5 py-2.5 text-sm"),
            ("md", "px-4 py-3 text-sm"),
            ("lg", "px-5 py-3.5 text-base"),
            ("xl", "px-6 py-4 text-lg"),
        ],
    )
    def test_size_applies_header_theme(
        self, size: str, marker: str
    ) -> None:
        with render_isolated():
            out = serialize(
                _build_basic_accordion(size=size).render()
            )
        assert marker in out


# ───────────────────────────────────────────────────────────────────────────
# E. AccordionItem — icon, disabled, standalone fallback
# ───────────────────────────────────────────────────────────────────────────


class TestAccordionItem:
    def test_icon_renders_inside_header(self) -> None:
        with render_isolated():
            with Accordion() as acc, AccordionItem("a", label="A", icon="shield"):
                pass
            out = serialize(acc.render())
        assert "shield" in out

    def test_disabled_item_has_disabled_attr(self) -> None:
        with render_isolated():
            with Accordion() as acc, AccordionItem("a", label="A", disabled=True):
                pass
            out = serialize(acc.render())
        assert "disabled" in out

    def test_item_renders_standalone_fallback(self) -> None:
        """Used outside an Accordion, an item renders as a plain
        div with its body children — no header, no toggle wiring."""
        with render_isolated():
            item = AccordionItem("a", label="A")
            out = serialize(item.render())
        assert "<div" in out
        # No toggle wiring in the standalone fallback.
        assert "isOpen" not in out
        assert "chevron" not in out


# ───────────────────────────────────────────────────────────────────────────
# F. Imperative API
# ───────────────────────────────────────────────────────────────────────────


class TestImperativeAPI:
    def test_expand_dispatches_when_no_binding(self) -> None:
        with render_isolated():
            acc = _build_basic_accordion()
            out = acc.expand("a")
        assert "dispatchEvent" in out
        assert "bz-expand" in out
        assert "value: " in out and '"a"' in out
        assert acc.id in out

    def test_collapse_dispatches_when_no_binding(self) -> None:
        with render_isolated():
            acc = _build_basic_accordion()
            out = acc.collapse("a")
        assert "dispatchEvent" in out
        assert "bz-collapse" in out
        assert '"a"' in out

    def test_toggle_dispatches_when_no_binding(self) -> None:
        with render_isolated():
            acc = _build_basic_accordion()
            out = acc.toggle("a")
        assert "dispatchEvent" in out
        assert "bz-toggle" in out
        assert '"a"' in out

    def test_expand_all_dispatches_no_payload(self) -> None:
        with render_isolated():
            acc = _build_basic_accordion()
            out = acc.expand_all()
        assert "dispatchEvent" in out
        assert "bz-expand-all" in out
        # No payload :
        assert "detail" not in out

    def test_collapse_all_dispatches_no_payload(self) -> None:
        with render_isolated():
            acc = _build_basic_accordion()
            out = acc.collapse_all()
        assert "dispatchEvent" in out
        assert "bz-collapse-all" in out

    def test_expand_writes_through_binding_when_single(self) -> None:
        """Single + binding : `.expand(v)` delegates to `binding.set(v)`
        directly — no DOM dispatch, single source of truth preserved."""
        binding = ClientBinding(
            class_name="UI",
            instance_key="default",
            field_name="expanded",
            value="a",
        )
        with render_isolated():
            acc = _build_basic_accordion(value=binding)
            out = acc.expand("b")
        assert "$bz.state.UI.default.expanded" in out
        assert "= " in out and '"b"' in out
        assert "dispatchEvent" not in out

    def test_expand_multiple_with_binding_still_dispatches(self) -> None:
        """Multiple + binding : always dispatch — the x-data's
        expand() method knows the array semantics, the Python side
        doesn't try to recompute the list."""
        binding = ClientBinding(
            class_name="UI",
            instance_key="default",
            field_name="expanded",
            value=["a"],
        )
        with render_isolated():
            with Accordion(multiple=True, value=binding) as acc:
                with AccordionItem("a", label="A"):
                    pass
                with AccordionItem("b", label="B"):
                    pass
            out = acc.expand("b")
        assert "dispatchEvent" in out
        assert "bz-expand" in out

    def test_needs_identity_is_true(self) -> None:
        """Identity must always be emitted — external triggers
        need to address the root via getElementById."""
        with render_isolated():
            acc = _build_basic_accordion()
            assert acc._needs_identity() is True


# ───────────────────────────────────────────────────────────────────────────
# G. Bindable surface + EVENTS
# ───────────────────────────────────────────────────────────────────────────


class TestBindableSurface:
    def test_bindable_props_is_value_only(self) -> None:
        assert Accordion.BINDABLE_PROPS == ("value",)

    def test_events_is_change_only(self) -> None:
        assert Accordion.EVENTS == ("change",)

    def test_autoname_from_is_value(self) -> None:
        assert Accordion.AUTONAME_FROM == "value"

    def test_item_has_no_bindable_props(self) -> None:
        # AccordionItem fields are design-time — the parent's
        # value= drives every expansion decision.
        assert AccordionItem.BINDABLE_PROPS == ()
