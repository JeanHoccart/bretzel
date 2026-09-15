"""Unit tests for :class:`bretzel.components.inputs.combobox.Combobox`.

V3 runtime port — the client behaviour lives inline in the ``bz-data``
scope (no more ``BZ_COMBO`` global), the anchored panel rides the
shared overlay wiring (``$bz.helpers.floating`` + ``anchored_dismiss``),
and every Alpine modifier is inlined (``bz-on:keydown`` with
``$event.key`` guards, no modifier grammar).
"""

from __future__ import annotations

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.inputs.combobox import Combobox
from bretzel.components.inputs.combobox.combobox import _normalise_text
from bretzel.core.serialize import serialize
from bretzel.state.scopes.client import ClientBinding
from bretzel.state.scopes.server import _BoundStr


def _synced_keys(out: str) -> set[str]:
    """Les clés réellement re-semées.

    ``_serverSync`` porte la clé de VALEUR (conditionnelle) ET la config
    server-owned préfixée ``_`` (inconditionnelle) : la présence du marker
    ne dit donc plus rien sur la valeur, il faut lire les clés.
    """
    import html as _html
    import re as _re
    keys: set[str] = set()
    for raw in _re.findall(r"_serverSync: \[([^\]]*)\]", _html.unescape(out)):
        keys |= {k.strip().strip("'\"") for k in raw.split(",") if k.strip()}
    return keys




# Module-level handlers — encode_handler_id needs an addressable
# qualname (no closures inside test methods).
def _change_handler() -> None: ...
def _search_handler() -> None: ...


def _build_basic(*, value=None, **kwargs) -> Combobox:
    """Stage a Combobox with three options."""
    return Combobox(
        options=[("a", "Alpha"), ("b", "Bravo"), ("c", "Charlie")],
        value=value,
        **kwargs,
    )


def _root_attrs(cb: Combobox) -> dict:
    return cb.render().attrs


def _hidden_input_attrs(out: str) -> str:
    """Slice the first ``<input>`` open tag from serialized output."""
    start = out.index("<input")
    return out[start:out.index(">", start)]


# ───────────────────────────────────────────────────────────────────────────
# A. Render structure
# ───────────────────────────────────────────────────────────────────────────


class TestStructure:
    def test_renders_root_wrapper(self) -> None:
        with render_isolated():
            out = serialize(_build_basic().render())
        assert "<div" in out
        assert "bz-data=" in out

    def test_trigger_has_combobox_role(self) -> None:
        with render_isolated():
            out = serialize(_build_basic().render())
        assert 'role="combobox"' in out
        assert 'aria-haspopup="listbox"' in out
        # V3 reactive attr — stringified so the data-attr stays present.
        assert "bz-attr:aria-expanded=" in out

    def test_panel_has_listbox_role(self) -> None:
        with render_isolated():
            out = serialize(_build_basic().render())
        assert 'role="listbox"' in out

    def test_options_emit_option_roles(self) -> None:
        with render_isolated():
            out = serialize(_build_basic().render())
        assert out.count('role="option"') == 3

    def test_inner_text_input_present(self) -> None:
        with render_isolated():
            out = serialize(_build_basic().render())
        assert '<input type="text"' in out
        # The input uses ``bz-attr:value`` + ``bz-on:input`` (not
        # ``bz-model``) so the display can compute ``open ? query :
        # label`` — picked label appears in the trigger when CLOSED,
        # search query when OPEN.
        assert 'bz-attr:value=' in out
        assert 'bz-on:input=' in out
        # And no bz-model — that would freeze the input value to the
        # typing buffer regardless of open/closed.
        assert 'bz-model="query"' not in out

    def test_chevron_renders(self) -> None:
        with render_isolated():
            out = serialize(_build_basic().render())
        assert "chevron-down" in out

    def test_clear_button_present(self) -> None:
        with render_isolated():
            out = serialize(_build_basic().render())
        assert 'aria-label="Clear"' in out

    def test_root_listens_to_imperative_commands(self) -> None:
        with render_isolated():
            out = serialize(_build_basic().render())
        for evt in (
            "bz-on:bz-set=", "bz-on:bz-select-all=", "bz-on:bz-deselect-all=",
        ):
            assert evt in out

    def test_close_on_click_outside_via_dismiss_init(self) -> None:
        # V3 : click-outside + Escape ride the shared anchored dismiss
        # init (``$bz.helpers.clickOutside`` / ``escapeKey``) on the
        # root, not a per-panel ``@click.outside``.
        with render_isolated():
            attrs = _root_attrs(_build_basic())
        assert "clickOutside" in attrs["bz-init"]
        assert "escapeKey" in attrs["bz-init"]
        assert "open = false" in attrs["bz-init"]


# ───────────────────────────────────────────────────────────────────────────
# B. Filter contract — normalize + tokenize + substring
# ───────────────────────────────────────────────────────────────────────────


class TestNormaliseText:
    """The server-side normalise mirrors the JS recipe and pre-bakes
    each option's haystack at render time. Same recipe must run
    both sides."""

    def test_lowercases(self) -> None:
        assert _normalise_text("Hello WORLD") == "hello world"

    def test_strips_diacritics(self) -> None:
        assert _normalise_text("Österreich") == "osterreich"
        assert _normalise_text("España") == "espana"
        assert _normalise_text("résumé") == "resume"

    def test_preserves_non_latin_letters(self) -> None:
        # Greek / CJK letters are not combining marks — they survive.
        assert _normalise_text("日本") == "日本"
        assert _normalise_text("Ελλάδα") == "ελλαδα"


class TestFilterEmission:
    def test_options_carry_bz_show_against_matches(self) -> None:
        with render_isolated():
            out = serialize(_build_basic().render())
        # Each option has bz-show="_matches('<haystack>')" — three of them.
        assert out.count('bz-show="_matches(') == 3

    def test_baked_haystack_is_normalised(self) -> None:
        with render_isolated():
            cb = Combobox(
                options=[("at", "Österreich")],
                value="",
            )
            out = serialize(cb.render())
        # The haystack baked into the bz-show call is the
        # diacritics-stripped lowercase form, so the JS only needs to
        # do token.includes() — no work to normalise on each keystroke.
        assert "osterreich at" in out

    def test_a_label_equal_to_its_value_is_baked_once(self) -> None:
        """``options=["open"]`` donnait la meule ``"open open"``.

        Le cas COURANT — une liste de chaînes nues a label == value — et
        la répétition se paie deux fois : dans ``_options``, et dans le
        ``_matches(…)`` de chaque option.

        Dédupliquer ne change aucun verdict : ``_matches`` teste
        ``haystack.includes(token)`` sur des tokens découpés aux espaces,
        donc aucun ne peut chevaucher la jointure — le seul endroit où
        « X X » dirait oui quand « X » dit non.
        """
        with render_isolated():
            out = serialize(Combobox(options=["open", "merged"]).render())
        assert '_matches(&quot;open&quot;)' in out
        assert "open open" not in out, (
            "la meule redit la valeur : elle pèse deux fois la liste, "
            "dans ``_options`` et dans chaque ``bz-show``"
        )

    def test_a_label_that_differs_still_carries_both(self) -> None:
        """Le versant licite. Sans lui, « ne jamais concaténer » passerait
        le test du haut tout en rendant les valeurs infiltrables."""
        with render_isolated():
            out = serialize(Combobox(options=[("at", "Autriche")]).render())
        assert "autriche at" in out, (
            "le libellé et la valeur diffèrent : les DEUX doivent être "
            "cherchables, sinon taper le code d'un pays ne le trouve plus"
        )

    def test_tokens_helper_in_bz_data(self) -> None:
        with render_isolated():
            out = serialize(_build_basic().render())
        # The filter algorithm (_tokens / _matches / _visibleIndices)
        # lives in the shared $bz.combobox.common factory ; the render
        # spreads it in.
        assert "$bz.combobox.common" in out

    def test_norm_function_uses_nfd_strip(self) -> None:
        with render_isolated():
            out = serialize(_build_basic().render())
        # The _norm recipe (lowercase + NFD + strip diacritics) lives in
        # the shared $bz.combobox.common factory.
        assert "$bz.combobox.common" in out


# ───────────────────────────────────────────────────────────────────────────
# C. Single vs multiple mode
# ───────────────────────────────────────────────────────────────────────────


class TestSingleMode:
    def test_default_mode_is_single(self) -> None:
        with render_isolated():
            out = serialize(_build_basic().render())
        # Single mode renders no TRIGGER pills template. The
        # selected_bar template (panel header) exists in both modes
        # but only one — so exactly 1 ``<template bz-for>``.
        assert out.count("<template bz-for") == 1

    def test_single_initial_value_in_bz_data(self) -> None:
        with render_isolated():
            out = serialize(_build_basic(value="b").render())
        # Local value field carries the initial scalar.
        assert 'value: &quot;b&quot;' in out

    def test_single_pick_method_emitted(self) -> None:
        with render_isolated():
            out = serialize(_build_basic().render())
        # _pick (single-mode setter) lives in the $bz.combobox.single
        # factory ; single mode spreads it in.
        assert "$bz.combobox.single" in out

    def test_single_input_display_branches_on_open(self) -> None:
        """The input value comes from ``open ? query : label`` :
        when CLOSED, the trigger shows the picked option's label ;
        when OPEN, a clean search query. The value reader is the
        mode-aware ``_value()`` method (works for literal + binding)."""
        with render_isolated():
            out = serialize(_build_basic(value="b").render())
        # ``_labelOf`` et pas une carte inlinée : ``_options`` porte
        # déjà chaque libellé, donc la carte ``_labels`` que le composant
        # émettait en plus a disparu (2026-08-28).
        assert 'bz-attr:value="open ? query : _labelOf(_value())"' in out

    def test_single_query_always_starts_empty(self) -> None:
        """Query is the search buffer — never seeded with a label.
        The label appears via the input's ``bz-attr:value`` expression
        when closed, the query takes over when open."""
        with render_isolated():
            out = serialize(_build_basic(value="b").render())
        # ``query: ''`` in the bz-data : the serialiser escapes
        # single quotes to ``'``.
        assert "query: ''," in out

    def test_single_pick_does_not_mirror_label_into_query(self) -> None:
        """The CLOSED trigger reads ``label`` via ``_labelOf`` in the
        ``bz-attr:value`` directive ; ``_pick`` no longer mutates
        ``query`` with a label."""
        with render_isolated():
            out = serialize(_build_basic().render())
        # _pick body must NOT write ``this.query = this._labels[...]``.
        assert "this.query = this._labels[" not in out


class TestSelectedBar:
    """The panel header pills bar — shows the user's current picks
    above the options list. Decouples the trigger (clean search
    input when open) from the picks display."""

    def test_selected_bar_present_in_single_mode(self) -> None:
        """Single mode also gets the selected_bar — the user wants
        consistency between modes."""
        with render_isolated():
            out = serialize(_build_basic(value="b").render())
        # The bar uses ``<template bz-for="v in _picked() :key=v">``
        # driven by _picked() which is mode-aware (single returns a
        # 1-elem or empty array). ``=`` escapes to ``=``.
        assert 'bz-for="v in _picked() :key=v"' in out

    def test_selected_bar_present_in_multi_mode(self) -> None:
        with render_isolated():
            cb = Combobox(
                options=[("a", "A"), ("b", "B")],
                value=["a"],
                multiple=True,
            )
            out = serialize(cb.render())
        # Two ``<template bz-for>`` in multi : trigger pills (CLOSED
        # state) + selected_bar (panel header).
        assert out.count('bz-for="v in _picked() :key=v"') == 2

    def test_selected_bar_hidden_when_nothing_picked(self) -> None:
        with render_isolated():
            out = serialize(_build_basic().render())
        # ``bz-show="_hasPicked()"`` on the bar — the runtime hides it
        # when the picked-list is empty.
        assert 'bz-show="_hasPicked()"' in out

    def test_trigger_pills_hidden_when_open_in_multi(self) -> None:
        """In multi mode, trigger pills must disappear when the
        panel opens — they migrate to the selected_bar inside the
        panel so the trigger becomes a clean search input."""
        with render_isolated():
            cb = Combobox(
                options=[("a", "A")],
                value=["a"],
                multiple=True,
            )
            out = serialize(cb.render())
        # Wrapper carries class="contents" (transparent to flex
        # layout) + bz-show="!open" (hides all pills at once when
        # the panel opens).
        assert 'class="contents" bz-show="!open"' in out

    def test_single_option_click_calls_toggle(self) -> None:
        """Click on an option goes through ``_togglePick`` (not
        ``_pick``) in single mode so that re-clicking the picked
        option deselects it."""
        with render_isolated():
            out = serialize(_build_basic().render())
        # ⚠️ Le clic a changé de PORTEUR le 2026-09-02, pas de
        # comportement : il est DÉLÉGUÉ sur le panneau au lieu d'être
        # recopié sur chaque option. Ce test épinglait la chaîne exacte
        # par option, donc il rougissait sur un déplacement — c'est le
        # bon signal, et la bonne réponse est de viser le nouveau
        # porteur, pas de relâcher l'assertion.
        assert "_togglePick(" in out
        # Il passe toujours par ``_togglePick`` et coupe toujours la
        # propagation en ligne (pas de modificateur ``.stop`` en V3).
        assert "$event.stopPropagation()" in out
        assert "_togglePick(o.getAttribute('data-value'))" in out
        # Et il n'est PLUS sur les options : une par option serait la
        # duplication qu'on vient de retirer.
        assert 'bz-on:click="$event.stopPropagation(); _togglePick(' not in out

    def test_single_toggle_deselects_when_repicked(self) -> None:
        """Single mode ``_togglePick`` (deselect-on-repick) lives in the
        $bz.combobox.single factory ; the per-instance ``_write`` clears
        the local ``value`` cell. Behaviour is browser-probed."""
        with render_isolated():
            out = serialize(_build_basic().render())
        assert "$bz.combobox.single" in out
        # Local mode wires _write onto the value field.
        assert "this.value = v" in out


class TestMultipleMode:
    def _build_multi(self, *, value=None, **kwargs) -> Combobox:
        return Combobox(
            options=[("a", "A"), ("b", "B"), ("c", "C")],
            value=value if value is not None else [],
            multiple=True,
            **kwargs,
        )

    def test_multi_renders_pills_template(self) -> None:
        with render_isolated():
            out = serialize(self._build_multi(value=["a"]).render())
        # The pills are rendered via <template bz-for> driven by
        # _picked() so removals re-render reactively.
        assert '<template bz-for="v in _picked() :key=v"' in out

    def test_multi_toggle_pick_method(self) -> None:
        with render_isolated():
            out = serialize(self._build_multi().render())
        # Multi-mode option clicks call _togglePick rather than _pick.
        assert "_togglePick(" in out

    def test_multi_initial_array(self) -> None:
        with render_isolated():
            out = serialize(
                self._build_multi(value=["a", "c"]).render()
            )
        # bz-data carries value as JS array.
        assert 'value: [&quot;a&quot;, &quot;c&quot;]' in out

    def test_backspace_on_empty_pops_last_pill(self) -> None:
        with render_isolated():
            out = serialize(self._build_multi().render())
        # The backspace handler only fires when the input is empty —
        # inlined inside the fused bz-on:keydown (no ``.backspace``
        # modifier in V3).
        assert "Backspace" in out
        assert "_removeLast()" in out

    def test_single_mode_has_no_backspace_branch(self) -> None:
        # Single mode leaves the default text-delete behaviour — no
        # Backspace guard in the fused keydown.
        with render_isolated():
            out = serialize(_build_basic().render())
        assert "Backspace" not in out

    def test_bulk_actions_off_no_bar(self) -> None:
        with render_isolated():
            out = serialize(self._build_multi().render())
        # Default bulk_actions=False → no Select all / Deselect all.
        assert "Select all" not in out
        assert "Deselect all" not in out

    def test_bulk_actions_on_adds_bar(self) -> None:
        with render_isolated():
            out = serialize(
                self._build_multi(bulk_actions=True).render()
            )
        assert "Select all" in out
        assert "Clear" in out
        assert "_selectAll()" in out
        assert "_clearAll()" in out

    def test_bulk_actions_ignored_in_single_mode(self) -> None:
        with render_isolated():
            cb = Combobox(
                options=[("a", "A")],
                multiple=False,
                bulk_actions=True,
            )
            out = serialize(cb.render())
        assert "Select all" not in out


class TestHeaderBar:
    """The unified header at the top of the panel — counter +
    pills + bulk actions."""

    def test_counter_renders_in_multi_mode(self) -> None:
        with render_isolated():
            cb = Combobox(
                options=[("a", "A"), ("b", "B"), ("c", "C")],
                value=["a"],
                multiple=True,
            )
            out = serialize(cb.render())
        # Counter span has ``bz-text="_picked().length + ' / 3'"``.
        assert "_picked().length + ' / 3'" in out

    def test_no_counter_in_single_mode(self) -> None:
        with render_isolated():
            out = serialize(_build_basic(value="a").render())
        # 0/1 counter is noise for single mode — we skip it.
        assert "_picked().length + " not in out

    def test_header_visible_when_picked_no_bulk(self) -> None:
        """Without bulk_actions, the bar is gated on _hasPicked()."""
        with render_isolated():
            out = serialize(_build_basic(value="b").render())
        assert 'bz-show="_hasPicked()"' in out

    def test_header_always_visible_with_bulk_actions(self) -> None:
        """When bulk_actions=True, the header must be visible even
        without picks — Select all has to be discoverable."""
        with render_isolated():
            cb = Combobox(
                options=[("a", "A")],
                multiple=True,
                bulk_actions=True,
            )
            out = serialize(cb.render())
        assert "Select all" in out
        # The header has bz-show="true" (always shown).
        assert 'bz-show="true"' in out

    def test_clear_button_disabled_when_no_picks(self) -> None:
        """Clear button gates on ``!_hasPicked()`` — disabled when
        nothing to clear."""
        with render_isolated():
            cb = Combobox(
                options=[("a", "A")],
                multiple=True,
                bulk_actions=True,
            )
            out = serialize(cb.render())
        assert 'bz-attr:disabled="!_hasPicked()"' in out

    def test_select_all_disabled_when_everything_picked(self) -> None:
        """Select all disables when the picked count already equals
        the visible-options count (nothing left to add). The visible
        count is hoisted into a single ``_visibleCount()`` call to
        avoid scanning the option list twice per reactive tick."""
        with render_isolated():
            cb = Combobox(
                options=[("a", "A"), ("b", "B")],
                multiple=True,
                bulk_actions=True,
            )
            out = serialize(cb.render())
        # Hoisted form : ``((c) => c > 0 && _picked().length === c)
        # (_visibleCount())`` — _visibleCount called once.
        assert "_picked().length === c" in out
        assert out.count("_visibleCount()") >= 1
        # The disabled gate still wires onto the Select all button.
        assert "bz-attr:disabled" in out

    def test_multi_placeholder_suppressed_when_picked_and_closed(
        self,
    ) -> None:
        """Multi mode : the placeholder hint is noise when the
        trigger is filled with pills. Use ``bz-attr:placeholder`` so
        the runtime empties it when ``_hasPicked() && !open``."""
        with render_isolated():
            cb = Combobox(
                options=[("a", "A"), ("b", "B")],
                value=["a"],
                multiple=True,
                placeholder="Pick stuff",
            )
            out = serialize(cb.render())
        assert "bz-attr:placeholder=" in out
        # Single quotes escape to ' in the attribute payload.
        assert (
            'bz-attr:placeholder="(_hasPicked() &amp;&amp; !open) ? '
            "'' : &quot;Pick stuff&quot;\"" in out
        )
        # No static ``placeholder=`` attribute on the input.
        assert 'placeholder="Pick stuff"' not in out

    def test_single_placeholder_stays_static(self) -> None:
        """Single mode : static placeholder is fine — the browser
        hides it automatically when the input has a value."""
        with render_isolated():
            cb = Combobox(
                options=[("a", "A")],
                placeholder="Pick one",
            )
            out = serialize(cb.render())
        assert 'placeholder="Pick one"' in out
        assert "bz-attr:placeholder=" not in out

    def test_header_uses_distinct_button_colors(self) -> None:
        """Select all in primary subtle, Clear in muted → error on
        hover. Different visual weight makes the constructive /
        destructive distinction obvious."""
        with render_isolated():
            cb = Combobox(
                options=[("a", "A")],
                multiple=True,
                bulk_actions=True,
            )
            out = serialize(cb.render())
        assert "text-(--bz-text)" in out
        assert "bz-c-primary" in out
        assert "text-muted" in out
        assert "hover:text-error" in out
        assert "hover:bg-error/10" in out


# ───────────────────────────────────────────────────────────────────────────
# D. Reactive contract — literal vs ClientBinding
# ───────────────────────────────────────────────────────────────────────────


class TestLiteralValue:
    def test_local_value_field_when_no_binding(self) -> None:
        with render_isolated():
            out = serialize(_build_basic(value="a").render())
        assert 'value: &quot;a&quot;' in out

    def test_no_hidden_input_without_name_or_event(self) -> None:
        with render_isolated():
            out = serialize(_build_basic(value="a").render())
        assert 'type="hidden"' not in out


class TestClientBindingValue:
    def _binding(self, *, value="a", multi=False) -> ClientBinding:
        return ClientBinding(
            class_name="UI",
            instance_key="default",
            field_name="picked",
            value=([value] if multi else value),
        )

    def test_value_path_resolves(self) -> None:
        binding = self._binding(value="b")
        with render_isolated():
            out = serialize(_build_basic(value=binding).render())
        assert "$bz.state.UI.default.picked" in out

    def test_no_local_value_field_when_bound(self) -> None:
        binding = self._binding(value="b")
        with render_isolated():
            out = serialize(_build_basic(value=binding).render())
        # ``_value()`` reads the binding path — no local field literal.
        assert "_value()" in out
        assert 'value: &quot;b&quot;' not in out
        # And NO V2 getter (it would freeze under scope.absorb).
        assert "get value(" not in out

    def test_autoname_derives_from_field(self) -> None:
        binding = self._binding(value="a")
        with render_isolated():
            out = serialize(_build_basic(value=binding).render())
        assert 'type="hidden"' in out
        assert 'name="picked"' in out

    def test_multi_hidden_uses_json_stringify(self) -> None:
        binding = self._binding(value="a", multi=True)
        with render_isolated():
            cb = Combobox(
                options=[("a", "A"), ("b", "B")],
                value=binding,
                multiple=True,
            )
            out = serialize(cb.render())
        assert "JSON.stringify" in out


class TestEvents:
    def test_change_handler_lives_on_hidden_input(self) -> None:
        binding = ClientBinding(
            class_name="UI", instance_key="default",
            field_name="picked", value="a",
        )
        with render_isolated():
            cb = Combobox(
                options=[("a", "A")],
                value=binding,
                on_change=_change_handler,
            )
            out = serialize(cb.render())
        # The callable change handler's HTMX bundle relocates onto the
        # hidden input — the root wrapper does not retain it.
        op = _hidden_input_attrs(out)
        assert "hx-post=" in op
        # Pinned to the synthetic ``change`` the hidden input dispatches.
        assert 'hx-trigger="change"' in op
        # The change-emit effect lives on the hidden input.
        assert "bz-effect=" in op
        root_open = out[:out.index("<input")]
        assert "hx-post" not in root_open

    def test_string_change_relocates_to_hidden(self) -> None:
        with render_isolated():
            cb = Combobox(
                options=["a"], name="fruit", value="a",
                on_change="state.x = 1",
            )
            out = serialize(cb.render())
        op = _hidden_input_attrs(out)
        assert "bz-on:change=" in op
        root = out[: out.index("<input")]
        assert "bz-on:change" not in root

    def test_callable_focus_blur_wire_to_input_not_dropped(self) -> None:
        """Regression : a callable ``on_focus`` / ``on_blur`` used to be
        popped off the root and only re-applied for change/search, so it
        was SILENTLY DROPPED (no hx-post anywhere). It must land on the
        focusable search input, keyed to its own event."""
        with render_isolated():
            out = serialize(
                Combobox(options=["a"], on_focus=_change_handler).render()
            )
        assert "hx-post=" in out                  # not dropped
        assert 'hx-trigger="focus"' in out        # fires on focus, not change
        with render_isolated():
            out = serialize(
                Combobox(options=["a"], on_blur=_change_handler).render()
            )
        assert "hx-post=" in out
        assert 'hx-trigger="blur"' in out

    def test_search_handler_relocated_onto_input_via_input_event(
        self,
    ) -> None:
        """`on_search=` is exposed via a native `input` event on the
        inner text field, with a second hidden input named ``query``
        carrying the live query for FormData. Both have to be present."""
        with render_isolated():
            cb = Combobox(
                options=[("a", "A")],
                on_search=_search_handler,
            )
            out = serialize(cb.render())
        # The callable search handler's HTMX bundle re-pins its trigger
        # to ``input`` and rides the search input.
        assert "hx-post=" in out
        assert "input changed delay" in out
        # Second hidden input mirrors query for FormData.
        assert 'name="query"' in out

    def test_string_search_relocates_onto_input_event(self) -> None:
        with render_isolated():
            cb = Combobox(
                options=[("a", "A")],
                on_search="state.q = 1",
            )
            out = serialize(cb.render())
        # String search handler rides bz-on:input (native keystroke).
        assert "bz-on:input=" in out
        # Two bz-on:input on the search input : the built-in query
        # mirror + the user handler. Both must be present.
        assert out.count("bz-on:input=") >= 1
        assert 'name="query"' in out

    def test_change_dispatched_by_hidden_input_effect_not_scope(self) -> None:
        """``change`` is dispatched by the hidden input's
        ``_change_emit_effect`` (from ``$el``), NOT by a scope method.
        The removed ``_emitChange`` / ``_carrier`` carrier machinery
        dispatched a SECOND, redundant change (a double server event) and
        must leave no trace."""
        with render_isolated():
            cb = _build_basic(name="x", value="a", on_change="y = 1")
            attrs = _root_attrs(cb)
            out = serialize(cb.render())
        assert "$bz.combobox.common" in attrs["bz-data"]
        assert "_carrier" not in attrs["bz-data"]
        assert "_carrier" not in attrs.get("bz-init", "")
        assert "_emitChange" not in out
        # The hidden input carries the dispatcher.
        op = _hidden_input_attrs(out)
        assert "bz-effect=" in op and "dispatchEvent" in op

    def test_serversync_only_when_server_backed(self) -> None:
        # ``_serverSync`` re-adopts the value on a @refreshable swap —
        # gated to server-backed values so an unbound combobox keeps its
        # client pick (no value loss + no phantom change(value='')).
        with render_isolated():
            unbound = serialize(_build_basic(on_change="x=1").render())
            literal = serialize(_build_basic(value="a").render())
            backed = serialize(
                _build_basic(value=_BoundStr("a", "fruit")).render()
            )
        # On lit les CLÉS, pas la présence du marker : la config
        # (``_options``) est re-semée dans les trois cas — le serveur en
        # est toujours propriétaire. Seule la VALEUR est conditionnelle.
        assert "value" not in _synced_keys(unbound)
        assert "value" not in _synced_keys(literal)
        assert "value" in _synced_keys(backed)
        for html in (unbound, literal, backed):
            assert {"_options"} <= _synced_keys(html)
            assert "_labels" not in _synced_keys(html), (
                "la carte ``_labels`` est de retour : elle redit le "
                "``label`` que chaque entrée d'``_options`` porte déjà"
            )


class TestUserHandlerDoesNotClobberInternalWiring:
    """Regression : a user-supplied on_focus= CLIENT-STRING handler
    used to silently OVERWRITE the search input's own internal
    "open panel + clear search buffer" wiring (dict.update() by key),
    not combine with it. Fixed by concatenating (internal first)
    instead of overwriting when both target bz-on:focus."""

    def test_on_focus_preserves_open_panel_wiring(self) -> None:
        with render_isolated():
            out = serialize(
                Combobox(options=["a"], on_focus="console.log(2)").render()
            )
        marker = "open = true; query = ''"
        i = out.index("bz-on:focus=")
        segment = out[i:i + 200]
        assert marker in segment
        assert "console.log(2)" in segment
        assert segment.index(marker) < segment.index("console.log(2)")

    def test_no_handler_still_wires_internal_only(self) -> None:
        with render_isolated():
            out = serialize(Combobox(options=["a"]).render())
        i = out.index("bz-on:focus=")
        segment = out[i:i + 200]
        assert "open = true; query = ''" in segment


class TestMethodShorthandScope:
    """Regression guard for the ``this.value`` rule in method
    shorthand bodies — cf. ``traps.md`` § "open = false dans une
    méthode shorthand x-data".

    Methods declared in the ``bz-data`` object literal are bound to
    the scope proxy (``this`` = scope), but bare identifiers in a
    method body do NOT auto-scope — a bare ``value = …`` write inside
    a method body lands on ``window.value`` instead of touching
    ``this.value``. The fix : every method body reads/writes via
    ``this.value`` (local) or the full ``$bz.state.<path>`` (binding).
    """

    def test_local_mode_methods_use_this_value(self) -> None:
        """All method bodies in local mode go through ``this.value``."""
        import re
        with render_isolated():
            out = serialize(_build_basic(value="a").render())
        xd_start = out.index("bz-data=")
        xd_end = out.index('"', xd_start + 10)
        xd = out[xd_start:xd_end]
        # No bare ``value = `` assignments outside this.value (the
        # serialiser HTML-escapes ``=`` to ``=``).
        bare = len(re.findall(r" value =", xd))
        through_this = len(re.findall(r"this\.value =", xd))
        assert bare == 0, (
            "Bare 'value =' in bz-data → creates window.value "
            "global, breaks reactivity. Use this.value."
        )
        assert through_this >= 1

    def test_multi_local_mode_methods_use_this_value(self) -> None:
        import re
        with render_isolated():
            cb = Combobox(
                options=[("a", "A"), ("b", "B")],
                value=["a"],
                multiple=True,
            )
            out = serialize(cb.render())
        xd_start = out.index("bz-data=")
        xd_end = out.index('"', xd_start + 10)
        xd = out[xd_start:xd_end]
        bare = len(re.findall(r" value =", xd))
        assert bare == 0, (
            "Bare 'value =' in multi-mode bz-data → pills won't "
            "render because bz-for tracks this.value. Use this.value."
        )

    def test_binding_mode_methods_use_full_state_path(self) -> None:
        """Binding mode writes go to the full ``$bz.state.<path>`` —
        no scope-wrap ambiguity possible."""
        binding = ClientBinding(
            class_name="UI", instance_key="default",
            field_name="picked", value=["a"],
        )
        with render_isolated():
            cb = Combobox(
                options=[("a", "A")],
                value=binding,
                multiple=True,
            )
            out = serialize(cb.render())
        assert "$bz.state.UI.default.picked =" in out

    def test_directive_context_uses_value_reader(self) -> None:
        """Directives evaluate under ``with($scope)`` so a method call
        like ``_value()`` resolves the scope helper. The hidden
        input's ``bz-attr:value`` in binding mode binds to the full
        state path (works in any surface)."""
        binding = ClientBinding(
            class_name="UI", instance_key="default",
            field_name="picked", value="a",
        )
        with render_isolated():
            out = serialize(_build_basic(value=binding).render())
        assert (
            'bz-attr:value="String($bz.state.UI.default.picked)"' in out
            or 'bz-attr:value="JSON.stringify(' in out
        )


class TestAnchoredPanel:
    """The panel rides the shared overlay wiring : a panel bz-effect
    toggles display + attaches floating against the ``bztrigger``
    ref ; the root carries open/close dispatch + dismiss init."""

    def test_panel_has_floating_effect_and_ref(self) -> None:
        with render_isolated():
            out = serialize(_build_basic().render())
        assert 'bz-ref="bzpanel"' in out
        assert "floating" in out
        # FOUC pre-stamp keeps the panel hidden before boot.
        assert "display:none" in out or "display: none" in out

    def test_trigger_carries_anchor_ref(self) -> None:
        with render_isolated():
            out = serialize(_build_basic().render())
        assert 'bz-ref="bztrigger"' in out

    def test_root_dispatch_and_dismiss_wiring(self) -> None:
        with render_isolated():
            attrs = _root_attrs(_build_basic())
        assert "bz-effect" in attrs
        assert "clickOutside" in attrs["bz-init"]
        assert "escapeKey" in attrs["bz-init"]


class TestKeyboardNav:
    """V3 fuses every per-key handler into ONE ``bz-on:keydown`` with
    ``$event.key`` guards (the runtime has no Alpine modifier
    grammar)."""

    def test_arrow_keys_wired_into_one_keydown(self) -> None:
        with render_isolated():
            out = serialize(_build_basic().render())
        assert "bz-on:keydown=" in out
        assert "ArrowDown" in out
        assert "ArrowUp" in out
        # No leftover Alpine modifier directives.
        assert "@keydown" not in out
        assert "keydown.arrow-down" not in out

    def test_enter_picks_highlighted(self) -> None:
        with render_isolated():
            out = serialize(_build_basic().render())
        assert "Enter" in out
        assert "_pickHighlighted()" in out
        assert "preventDefault" in out

    def test_escape_closes(self) -> None:
        with render_isolated():
            out = serialize(_build_basic().render())
        # Escape handled both in the fused keydown guard and via the
        # root dismiss init.
        assert "Escape" in out


# ───────────────────────────────────────────────────────────────────────────
# E. Theme sizes
# ───────────────────────────────────────────────────────────────────────────


class TestThemeSizes:
    @pytest.mark.parametrize(
        ("size", "marker"),
        [
            ("xs", "min-h-[1.75rem]"),
            ("sm", "min-h-[2rem]"),
            ("md", "min-h-[2.5rem]"),
            ("lg", "min-h-[3rem]"),
            ("xl", "min-h-[3.5rem]"),
        ],
    )
    def test_size_applies_trigger_height(
        self, size: str, marker: str
    ) -> None:
        with render_isolated():
            out = serialize(_build_basic(size=size).render())
        assert marker in out


# ───────────────────────────────────────────────────────────────────────────
# F. Imperative API
# ───────────────────────────────────────────────────────────────────────────


class TestImperativeAPI:
    def test_set_dispatches_when_no_binding(self) -> None:
        with render_isolated():
            cb = _build_basic()
            out = cb.set("b")
        assert "dispatchEvent" in out
        assert "bz-set" in out
        assert '"b"' in out
        assert cb.id in out

    def test_set_writes_through_binding_single(self) -> None:
        binding = ClientBinding(
            class_name="UI", instance_key="default",
            field_name="picked", value="a",
        )
        with render_isolated():
            cb = _build_basic(value=binding)
            out = cb.set("b")
        assert "$bz.state.UI.default.picked" in out
        assert '"b"' in out
        assert "dispatchEvent" not in out

    def test_clear_single(self) -> None:
        with render_isolated():
            cb = _build_basic()
            out = cb.clear()
        assert "bz-set" in out
        assert '""' in out

    def test_clear_multi_sends_empty_array(self) -> None:
        with render_isolated():
            cb = Combobox(
                options=[("a", "A")], multiple=True,
            )
            out = cb.clear()
        assert "bz-set" in out
        assert "[]" in out

    def test_select_all_dispatches_no_payload(self) -> None:
        with render_isolated():
            cb = Combobox(
                options=[("a", "A")], multiple=True,
            )
            out = cb.select_all()
        assert "bz-select-all" in out
        assert "detail" not in out

    def test_deselect_all_dispatches_no_payload(self) -> None:
        with render_isolated():
            cb = Combobox(
                options=[("a", "A")], multiple=True,
            )
            out = cb.deselect_all()
        assert "bz-deselect-all" in out

    def test_focus_targets_inner_input(self) -> None:
        with render_isolated():
            cb = _build_basic()
            out = cb.focus()
        assert "querySelector" in out
        assert "input[type=text]" in out
        assert ".focus()" in out
        assert cb.id in out

    def test_blur_targets_inner_input(self) -> None:
        with render_isolated():
            cb = _build_basic()
            out = cb.blur()
        assert "querySelector" in out
        assert ".blur()" in out

    def test_needs_identity_is_true(self) -> None:
        with render_isolated():
            cb = _build_basic()
            assert cb._needs_identity() is True


# ───────────────────────────────────────────────────────────────────────────
# G. Bindable surface + EVENTS
# ───────────────────────────────────────────────────────────────────────────


class TestBindableSurface:
    def test_bindable_props(self) -> None:
        assert set(Combobox.BINDABLE_PROPS) == {"value", "disabled"}

    def test_events_declared(self) -> None:
        assert set(Combobox.EVENTS) == {
            "change", "focus", "blur", "search", "close",
        }

    def test_autoname_from_is_value(self) -> None:
        assert Combobox.AUTONAME_FROM == "value"


# ───────────────────────────────────────────────────────────────────
# render= — le corps de l'option, et ce que le filtre en pense
# ───────────────────────────────────────────────────────────────────


class TestRenderHatch:
    """Le cas propre au Combobox : le rappel ne doit RIEN changer au
    filtre, qui est la raison d'être du composant."""

    def _html(self, **kwargs) -> str:
        from bretzel.components.inputs.combobox import Combobox

        with render_isolated():
            return serialize(
                Combobox(options=[("a", "Alpha"), ("b", "Beta")], **kwargs)
                .render()
            )

    def test_the_callback_body_reaches_the_option(self) -> None:
        from bretzel import ui

        out = self._html(render=lambda v, label: ui.badge(label="ZZ"))
        assert out.count("ZZ") == 2

    def test_the_filter_still_searches_the_text_label(self) -> None:
        """La limite à connaître, figée ici. Le haystack est bâti côté
        serveur depuis le label TEXTE ; rendre un badge ne change pas ce
        qui est cherché. Si ce test rougit, c'est que le rappel a fui
        dans le haystack — et le filtre chercherait alors dans du
        balisage."""
        from bretzel import ui

        plain = self._html()
        rich = self._html(render=lambda v, label: ui.badge(label="ZZ"))
        assert '_matches("alpha a")' in plain.replace("&quot;", '"')
        assert '_matches("alpha a")' in rich.replace("&quot;", '"'), (
            "le haystack a changé avec ``render=`` — le filtre doit "
            "rester indexé sur le label texte."
        )

    def test_the_click_and_selected_state_survive(self) -> None:
        from bretzel import ui

        out = self._html(render=lambda v, label: ui.badge(label="ZZ"))
        assert "_togglePick" in out
        assert "aria-selected" in out
        assert 'data-value="a"' in out
