"""Smoke tests for :class:`PieChart`."""

from __future__ import annotations

from bretzel.components.base.testing import render_isolated
from bretzel.components.charts.pie_chart.pie_chart import PieChart
from bretzel.core.serialize import serialize


SAMPLE = [("Direct", 42), ("Search", 28), ("Social", 18), ("Email", 12)]


def _click_handler(label: str, value: float) -> None:
    """Module-level ``on_item_click=`` handler for the smoke test."""


class TestPieChart:
    def test_default_emits_wrapper_with_svg(self) -> None:
        with render_isolated():
            out = serialize(PieChart(SAMPLE).render())
        assert out.startswith("<div")
        assert "<svg" in out
        assert 'role="img"' in out

    def test_one_path_per_slice(self) -> None:
        with render_isolated():
            out = serialize(PieChart(SAMPLE).render())
        assert out.count("<path") == 4

    def test_arc_path_contains_arc_directive(self) -> None:
        with render_isolated():
            out = serialize(PieChart(SAMPLE).render())
        # SVG arc command marker.
        assert " A" in out  # space before A in path data

    def test_tooltip_payload_with_percent(self) -> None:
        with render_isolated():
            out = serialize(PieChart(SAMPLE).render())
        assert "data-bz-display" in out
        # 42 / (42 + 28 + 18 + 12) = 42 %
        assert "Direct: 42 (42%)" in out

    def test_tooltip_scope_on_wrapper(self) -> None:
        with render_isolated():
            out = serialize(PieChart(SAMPLE).render())
        # V3 chart scope rides bz-data ; slices wire hover via bz-on.
        assert 'bz-data="$bz.charts.tooltipScope()"' in out
        assert 'bz-on:mouseenter="show($event)"' in out
        assert 'bz-on:mouseleave="hide()"' in out

    def test_legend_emits_one_swatch_per_slice(self) -> None:
        with render_isolated():
            out = serialize(PieChart(SAMPLE).render())
        for label, _ in SAMPLE:
            assert label in out

    def test_show_legend_false_skips_legend(self) -> None:
        with render_isolated():
            out = serialize(PieChart(SAMPLE, show_legend=False).render())
        # Legend block uses "flex items-center gap-2" wrappers — absent here.
        assert out.count('flex items-center gap-2') == 0

    def test_donut_emits_inner_arc(self) -> None:
        with render_isolated():
            pie = serialize(PieChart(SAMPLE).render())
            donut = serialize(PieChart(SAMPLE, variant="donut").render())
        # Donut wedges carry two arcs per path ; pies one.
        assert donut.count(" A") > pie.count(" A")

    def test_donut_center_text(self) -> None:
        with render_isolated():
            out = serialize(
                PieChart(SAMPLE, variant="donut", center_text="100").render()
            )
        assert ">100<" in out

    def test_center_text_skipped_on_non_donut(self) -> None:
        with render_isolated():
            out = serialize(
                PieChart(SAMPLE, center_text="100").render()
            )
        assert ">100<" not in out

    def test_show_labels_emits_percent_text(self) -> None:
        with render_isolated():
            out = serialize(
                PieChart(SAMPLE, show_labels=True).render()
            )
        # 4 slices > 0.08 rad → 4 percent labels.
        assert out.count("%</text>") >= 4

    def test_tiny_slivers_skip_label(self) -> None:
        # 99 % vs 1 % — the 1 % slice is < 0.08 rad (≈4.6°) so it
        # skips the in-chart label to avoid overlap.
        with render_isolated():
            out = serialize(
                PieChart([("Big", 99), ("Tiny", 1)],
                         show_labels=True).render()
            )
        assert out.count("%</text>") == 1

    def test_empty_data_renders_no_data_placeholder(self) -> None:
        """L'état vide est un ``ui.empty_state``, pas un ``<text>`` SVG.

        Les quatre charts n'offraient que ``empty_text`` quand table,
        datatable et diagram offrent les quatre props — trois
        profondeurs pour un même besoin (audit § 1.3). Ils composent
        désormais le même ``EmptyState``, donc l'icône arrive.

        L'``aria-label`` reste vérifié : c'est le correctif F24, un
        chart vide doit annoncer SON identité et pas celle du voisin
        dont il a emprunté l'helper.
        """
        with render_isolated():
            out = serialize(PieChart([]).render())
        assert "<rect" not in out
        assert "No data" in out
        assert "pie-chart" in out
        assert 'aria-label="Pie chart — No data"' in out

    def test_negative_and_zero_values_skipped(self) -> None:
        with render_isolated():
            out = serialize(
                PieChart([("A", 10), ("B", 0), ("C", -5), ("D", 20)]).render()
            )
        # B and C dropped silently → only 2 slices.
        assert out.count("<path") == 2

    def test_colors_kwarg_overrides_palette(self) -> None:
        with render_isolated():
            out = serialize(
                PieChart([("A", 1), ("B", 1)],
                         colors=["info", "warning"]).render()
            )
        assert "fill-(--bz-solid)" in out
        assert "bz-c-info" in out
        assert "bz-c-warning" in out

    def test_default_palette_cycles(self) -> None:
        with render_isolated():
            out = serialize(PieChart(SAMPLE).render())
        # 4 slices → first 4 of the default palette.
        assert "fill-(--bz-solid)" in out
        assert "bz-c-primary" in out
        assert "bz-c-success" in out
        assert "bz-c-warning" in out
        assert "bz-c-info" in out

    def test_size_drives_square_dimensions(self) -> None:
        with render_isolated():
            xs = serialize(PieChart(SAMPLE, size="xs").render())
            xl = serialize(PieChart(SAMPLE, size="xl").render())
        assert 'width="140"' in xs
        assert 'height="140"' in xs
        assert 'width="440"' in xl

    def test_on_item_click_wires_action_per_slice(self) -> None:
        with render_isolated():
            out = serialize(
                PieChart(SAMPLE, on_item_click=_click_handler).render()
            )
        # V3 wire : one hx-post per slice, the partial-bound
        # (label, value) pair riding as the _args blob per slice.
        assert out.count('hx-post="/_bretzel/action/') == 4
        assert out.count("_args") == 4
        assert "cursor-pointer" in out

    def test_single_slice_renders_full_circle(self) -> None:
        with render_isolated():
            out = serialize(PieChart([("All", 100)]).render())
        # Full-circle arc_path emits two arcs ; one slice only.
        assert out.count("<path") == 1
        assert "(100%)" in out

    def test_value_format_threads_into_tooltip(self) -> None:
        with render_isolated():
            out = serialize(
                PieChart([("Revenue", 1500)],
                         value_format="abbreviated").render()
            )
        assert "Revenue: 1.5k" in out

    def test_no_bindable_props(self) -> None:
        assert PieChart.BINDABLE_PROPS == ()
