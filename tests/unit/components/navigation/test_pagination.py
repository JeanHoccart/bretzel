"""Unit tests for :class:`bretzel.components.navigation.pagination.Pagination`.

Three layers :

A. ``compute_range`` — pure-Python algorithm, ports the V1 contract
   (max_visible clamped to 5, ellipsis on first / last / both sides).
B. Render — DOM structure, ARIA, hidden input plumbing.
C. Reactive contract — literal / server-resolved / ClientBinding for
   ``value`` and ``total_pages``, plus the ``bz-data`` runtime state
   that wires it all up.
"""

from __future__ import annotations

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.navigation.pagination import (
    Pagination,
    compute_range,
)
from bretzel.core.serialize import serialize
from bretzel.state.scopes.client import ClientBinding


# Module-level handler — components route ``on_<event>`` through
# ``encode_handler_id`` which requires an addressable qualname (no
# closures, no lambdas).
def _change_handler() -> None:
    pass


# ───────────────────────────────────────────────────────────────────────────
# A. compute_range — pure function
# ───────────────────────────────────────────────────────────────────────────


class TestComputeRange:
    def test_few_pages_no_ellipsis(self) -> None:
        assert compute_range(1, 5, 7) == [1, 2, 3, 4, 5]
        assert compute_range(3, 5, 7) == [1, 2, 3, 4, 5]

    def test_first_page_with_right_ellipsis(self) -> None:
        assert compute_range(1, 10, 7) == [1, 2, 3, 4, 5, "ellipsis", 10]

    def test_middle_page_two_ellipsis(self) -> None:
        assert compute_range(5, 10, 7) == [
            1, "ellipsis", 4, 5, 6, "ellipsis", 10
        ]

    def test_last_page_with_left_ellipsis(self) -> None:
        assert compute_range(10, 10, 7) == [1, "ellipsis", 6, 7, 8, 9, 10]

    def test_max_visible_clamped_to_5(self) -> None:
        # max_visible<5 is clamped — keeps a sane minimum layout.
        assert compute_range(1, 10, 3) == [1, 2, 3, "ellipsis", 10]

    def test_total_one_page(self) -> None:
        assert compute_range(1, 1, 7) == [1]

    def test_just_at_threshold(self) -> None:
        # total_pages == max_visible → no ellipsis, all pages visible.
        assert compute_range(4, 7, 7) == [1, 2, 3, 4, 5, 6, 7]

    def test_just_over_threshold(self) -> None:
        # total_pages == max_visible + 1 → ellipsis kicks in.
        result = compute_range(1, 8, 7)
        assert "ellipsis" in result
        assert result[-1] == 8


# ───────────────────────────────────────────────────────────────────────────
# B. Render structure
# ───────────────────────────────────────────────────────────────────────────


class TestRender:
    def test_renders_nav_with_role(self) -> None:
        with render_isolated():
            out = serialize(Pagination(total_pages=10).render())
        assert "<nav" in out
        assert 'role="navigation"' in out
        assert 'aria-label="Pagination"' in out

    def test_prev_next_chevrons_present(self) -> None:
        with render_isolated():
            out = serialize(Pagination(total_pages=5).render())
        assert 'aria-label="Previous page"' in out
        assert 'aria-label="Next page"' in out
        # Chevron icons (lucide names).
        assert "chevron-left" in out
        assert "chevron-right" in out

    def test_n_item_buttons_rendered(self) -> None:
        # max_visible=7 → max(5,7)=7 static slots, plus prev + next
        # + chevron icons. Count `<button` occurrences.
        with render_isolated():
            out = serialize(Pagination(total_pages=20, max_visible=7).render())
        # 7 page buttons + prev + next = 9 buttons total.
        assert out.count("<button") == 9

    def test_max_visible_clamps_to_5(self) -> None:
        # max_visible=3 → still 5 slots (the V1/Alpine contract).
        with render_isolated():
            out = serialize(Pagination(total_pages=20, max_visible=3).render())
        # 5 page buttons + prev + next = 7 buttons.
        assert out.count("<button") == 7


class TestArias:
    def test_aria_current_is_reactive(self) -> None:
        # Active page is determined client-side, so the attr is
        # always emitted as the bound bz-attr:aria-current expression.
        with render_isolated():
            out = serialize(
                Pagination(total_pages=10, value=3).render()
            )
        assert "bz-attr:aria-current=" in out

    def test_aria_label_per_item_includes_page_number(self) -> None:
        with render_isolated():
            out = serialize(Pagination(total_pages=10).render())
        # Items wire ``bz-attr:aria-label="'Page ' + range()[i]"``. The
        # serialiser escapes single quotes inside attr values to
        # ``'`` so we look for the escaped form.
        assert "bz-attr:aria-label=" in out
        assert "'Page '" in out


# ───────────────────────────────────────────────────────────────────────────
# C. Reactive contract
# ───────────────────────────────────────────────────────────────────────────


class TestLiteralValue:
    def test_local_active_field_initialised(self) -> None:
        with render_isolated():
            out = serialize(
                Pagination(total_pages=10, value=4).render()
            )
        # x-data has a local ``active: 4`` field.
        assert "value: 4" in out

    def test_no_xmodel_for_literal_value(self) -> None:
        # value=int doesn't introduce an x-model anywhere — pagination
        # uses x-data getters, not Alpine's two-way directive.
        with render_isolated():
            out = serialize(Pagination(total_pages=10, value=2).render())
        assert "x-model" not in out

    def test_no_hidden_input_when_no_name(self) -> None:
        # No binding, no explicit name, no on_change handler → the
        # hidden input is dead weight, skip it.
        with render_isolated():
            out = serialize(Pagination(total_pages=10, value=2).render())
        assert 'type="hidden"' not in out


class TestServerSyncGating:
    """``_serverSync: ['value']`` re-adopts the page from the server on a
    @refreshable morph — idiomorph preserves the ``active`` signal
    otherwise, so ``value=state.page`` would never move the UI. Emitted
    ONLY when server-backed, else an unrelated refresh wipes the client's
    page click. Same gate as Tabs / Select."""

    # ``_serverSync`` porte DEUX catégories, et seule la première est
    # conditionnelle : la clé de valeur (``active``, re-semée uniquement si
    # le serveur en est propriétaire) et la config server-owned (``_total`` /
    # ``_maxVisible``, TOUJOURS re-semée — le serveur en est toujours la
    # source, et sans ça le nombre de pages restait figé au premier montage).
    # Ces tests portent sur ``active`` : ils lisent donc les CLÉS, pas la
    # simple présence du marker.

    @staticmethod
    def _synced_keys(out: str) -> set[str]:
        import html as _html
        import re
        keys: set[str] = set()
        for raw in re.findall(r"_serverSync: \[([^\]]*)\]", _html.unescape(out)):
            keys |= {k.strip().strip("'\"") for k in raw.split(",") if k.strip()}
        return keys

    def test_literal_value_omits_serversync(self) -> None:
        with render_isolated():
            out = serialize(Pagination(total_pages=10, value=2).render())
        assert "value" not in self._synced_keys(out)

    def test_server_backed_value_keeps_serversync(self) -> None:
        from bretzel.state.scopes.server import _BoundInt

        with render_isolated():
            out = serialize(
                Pagination(total_pages=10, value=_BoundInt(2, "page")).render()
            )
        assert "value" in self._synced_keys(out)

    def test_binding_value_omits_serversync(self) -> None:
        binding = ClientBinding(
            class_name="ListState", instance_key="default",
            field_name="page", value=2,
        )
        with render_isolated():
            out = serialize(Pagination(total_pages=10, value=binding).render())
        assert "value" not in self._synced_keys(out)


    def test_config_is_always_resynced(self) -> None:
        """``_total`` / ``_maxVisible`` sont re-semés dans les trois modes.

        C'est le correctif du bug « les contrôles du playground ne font
        rien » : le serveur renvoyait bien ``_total: 16``, mais ``absorb``
        ne réécrit jamais un signal existant, donc le scope répondait
        toujours la valeur du premier montage. Le serveur est TOUJOURS
        propriétaire de la configuration — contrairement à la valeur.
        """
        from bretzel.state.scopes.server import _BoundInt

        binding = ClientBinding(
            class_name="ListState", instance_key="default",
            field_name="page", value=2,
        )
        for value in (2, _BoundInt(2, "page"), binding):
            with render_isolated():
                out = serialize(
                    Pagination(total_pages=10, value=value).render()
                )
            keys = self._synced_keys(out)
            assert {"_total", "_maxVisible"} <= keys, (
                f"value={value!r} : config non re-semée ({sorted(keys)}) — "
                f"un changement serveur de total_pages / max_visible "
                f"resterait invisible."
            )


class TestClientBindingValue:
    def _binding(self, *, value: int = 1) -> ClientBinding:
        return ClientBinding(
            class_name="ListState",
            instance_key="default",
            field_name="page",
            value=value,
        )

    def test_value_expr_targets_state_path(self) -> None:
        binding = self._binding(value=3)
        with render_isolated():
            out = serialize(
                Pagination(total_pages=10, value=binding).render()
            )
        # Binding path lands inside the x-data getters.
        assert "$bz.state.ListState.default.page" in out

    def test_no_local_active_field_when_bound(self) -> None:
        binding = self._binding(value=3)
        with render_isolated():
            out = serialize(
                Pagination(total_pages=10, value=binding).render()
            )
        # The local ``active: <int>`` field is omitted — the binding
        # is the source of truth.
        assert "value: 3" not in out
        assert "value:1" not in out
        # Sanity : the binding path replaces it everywhere.
        assert "(active)" not in out  # never references local field

    def test_autoname_derives_from_field(self) -> None:
        # value=binding → name="page" auto on the hidden input.
        binding = self._binding(value=1)
        with render_isolated():
            out = serialize(
                Pagination(total_pages=5, value=binding).render()
            )
        assert 'type="hidden"' in out
        assert 'name="page"' in out

    def test_hidden_input_value_attr_seeded_with_initial(self) -> None:
        # SSR fallback : the hidden input carries the literal initial
        # value too, so a JS-disabled client / pre-Alpine boot still
        # sees a coherent form value.
        binding = self._binding(value=4)
        with render_isolated():
            out = serialize(
                Pagination(total_pages=10, value=binding).render()
            )
        assert 'value="4"' in out


class TestReactiveTotalPages:
    """``total_pages`` coupé du bindable 2026-07-16 (règle « driver
    client, sinon serveur » : le total change avec le compte de résultats
    serveur → @refreshable re-render, pas de driver client → ∅). Un
    binding y lève ComponentUsageError ; la valeur littérale reste OK."""

    def test_total_pages_binding_is_refused(self) -> None:
        from bretzel.components.base.attrs import ComponentUsageError

        binding = ClientBinding(
            class_name="ListState",
            instance_key="default",
            field_name="total",
            value=42,
        )
        with render_isolated():
            with pytest.raises(ComponentUsageError):
                Pagination(total_pages=binding, value=1)


class TestDisabledFlag:
    def test_disabled_literal_flows_into_xdata(self) -> None:
        with render_isolated():
            out = serialize(
                Pagination(total_pages=5, disabled=True).render()
            )
        # Embedded literal — Alpine isDisabled getter reads "true".
        # We check the specific shape inside x-data (value lookups
        # happen there, not on the buttons themselves).
        assert "isDisabled" in out


class TestEvents:
    def test_change_handler_relocates_to_hidden_input(self) -> None:
        """V3 : a callable ``on_change`` emits the native HTMX action
        set (``hx-post`` + ``hx-trigger`` + …). The dispatcher reads
        ``name`` + ``value`` off the source element, so the action set
        is relocated off the wrapper <nav> (no name/value) onto the
        hidden input (cf. ``traps.md``)."""
        binding = ClientBinding(
            class_name="ListState",
            instance_key="default",
            field_name="page",
            value=1,
        )
        with render_isolated():
            comp = Pagination(
                total_pages=10, value=binding, on_change=_change_handler
            )
            out = serialize(comp.render())
        # The action set lives inside the hidden input opening tag.
        opening = out[out.index("<input"):out.index(">", out.index("<input"))]
        assert "hx-post=" in opening
        assert 'hx-trigger="change"' in opening
        # It must NOT remain on the root <nav>.
        nav_open = out[out.index("<nav"):out.index(">", out.index("<nav"))]
        assert "hx-post=" not in nav_open
        assert "hx-trigger=" not in nav_open
        # The reactive change-dispatch effect rides the same input.
        assert "bz-effect=" in opening

    def test_string_change_handler_relocates_to_hidden_input(self) -> None:
        """A string ``on_change`` emits ``bz-on:change`` — same
        relocation onto the hidden input."""
        binding = ClientBinding(
            class_name="ListState",
            instance_key="default",
            field_name="page",
            value=1,
        )
        with render_isolated():
            comp = Pagination(
                total_pages=10,
                value=binding,
                on_change="console.log('page changed')",
            )
            out = serialize(comp.render())
        opening = out[out.index("<input"):out.index(">", out.index("<input"))]
        assert "bz-on:change=" in opening
        nav_open = out[out.index("<nav"):out.index(">", out.index("<nav"))]
        assert "bz-on:change=" not in nav_open


# ───────────────────────────────────────────────────────────────────────────
# D. Theme integration
# ───────────────────────────────────────────────────────────────────────────


class TestTheme:
    @pytest.mark.parametrize(
        ("size", "item_dim"),
        [("sm", "w-8"), ("md", "w-10"), ("lg", "w-12")],
    )
    def test_size_classes_propagate(self, size: str, item_dim: str) -> None:
        with render_isolated():
            out = serialize(
                Pagination(total_pages=5, size=size).render()
            )
        assert item_dim in out

    def test_color_substituted_in_active_class(self) -> None:
        with render_isolated():
            out = serialize(
                Pagination(total_pages=5, color="success").render()
            )
        # Active slot template uses {bg_color}/{fg_color} — should
        # resolve to bg-success / text-success-foreground.
        assert "bg-(--bz-solid)" in out
        assert "bz-c-success" in out
        # No raw placeholder left behind.
        assert "{bg_color}" not in out
        assert "{fg_color}" not in out
