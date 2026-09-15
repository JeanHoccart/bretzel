"""Smoke tests for :class:`BarChart`."""

from __future__ import annotations

from bretzel.components.base.testing import render_isolated
from bretzel.components.charts.bar_chart.bar_chart import BarChart
from bretzel.components.charts.series import Series
from bretzel.core.serialize import serialize


SAMPLE = [("Jan", 12), ("Feb", 18), ("Mar", 7), ("Apr", 21), ("May", 15)]


def _click_handler(label: str, value: float) -> None:
    """Module-level handler for ``on_item_click=`` smoke test (closures are rejected)."""


_STACKED_MULTI = [
    Series(name="A", data=[("Q1", 10), ("Q2", 14)]),
    Series(name="B", data=[("Q1", 8), ("Q2", 6)]),
    Series(name="C", data=[("Q1", 5), ("Q2", 12)]),
]


_SAMPLE_SINGLE = [("Jan", 12), ("Feb", 18), ("Mar", 25), ("Apr", 8)]


class TestBarChart:
    def test_default_emits_wrapper_with_svg(self) -> None:
        with render_isolated():
            out = serialize(BarChart(SAMPLE).render())
        assert out.startswith("<div")
        assert "<svg" in out
        assert 'role="img"' in out

    def test_emits_one_rect_per_bar(self) -> None:
        with render_isolated():
            out = serialize(BarChart(SAMPLE).render())
        # Single series, 5 categories → 5 visible bars. Each bar also
        # carries a transparent full-column ``.bz-bar-hit`` overlay
        # (widened hover / click target), so ``<rect`` doubles — the
        # visible-bar count rides the ``bz-bar-fill`` marker.
        assert out.count("bz-bar-fill") == 5
        assert out.count("bz-bar-hit") == 5

    def test_bar_carries_tooltip_payload(self) -> None:
        with render_isolated():
            out = serialize(BarChart(SAMPLE).render())
        assert "data-bz-display" in out
        assert "Jan: 12" in out

    def test_tooltip_scope_on_wrapper(self) -> None:
        with render_isolated():
            out = serialize(BarChart(SAMPLE).render())
        # V3 chart scope rides bz-data ; bars wire hover via bz-on.
        assert 'bz-data="$bz.charts.tooltipScope()"' in out
        assert 'bz-on:mouseenter="show($event)"' in out
        assert 'bz-on:mouseleave="hide()"' in out

    def test_show_axis_emits_y_ticks(self) -> None:
        with render_isolated():
            out = serialize(BarChart(SAMPLE, show_axis=True).render())
        # At least 3 tick labels (Heckbert lands 4-6 ticks for 0-22).
        assert out.count("<text") >= 3 + 5  # ticks + 5 x-labels
        assert "<line" in out  # axis baseline

    def test_show_axis_false_drops_ticks_and_y_line(self) -> None:
        with render_isolated():
            out = serialize(
                BarChart(SAMPLE, show_axis=False,
                         show_gridlines=False).render()
            )
        # Only the X-axis label texts remain (5).
        text_count = out.count("<text")
        assert text_count == 5

    def test_show_values_emits_extra_text_per_bar(self) -> None:
        with render_isolated():
            plain = serialize(BarChart(SAMPLE).render())
            with_v = serialize(BarChart(SAMPLE, show_values=True).render())
        assert with_v.count("<text") > plain.count("<text")

    def test_y_format_currency(self) -> None:
        with render_isolated():
            out = serialize(
                BarChart([("Jan", 1200)], y_format="currency",
                         show_values=True).render()
            )
        assert "$1,200.00" in out

    def test_y_format_abbreviated(self) -> None:
        with render_isolated():
            out = serialize(
                BarChart([("Jan", 1500)], y_format="abbreviated",
                         show_values=True).render()
            )
        assert "1.5k" in out

    def test_color_threads_into_bar_fill(self) -> None:
        with render_isolated():
            out = serialize(BarChart(SAMPLE, color="success").render())
        assert "fill-(--bz-solid)" in out
        assert "bz-c-success" in out

    def test_size_drives_height(self) -> None:
        with render_isolated():
            xs = serialize(BarChart(SAMPLE, size="xs").render())
            xl = serialize(BarChart(SAMPLE, size="xl").render())
        assert 'height="140"' in xs
        assert 'height="440"' in xl

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
            out = serialize(BarChart([]).render())
        assert "<rect" not in out
        assert "No data" in out
        assert "bar-chart-3" in out
        assert 'aria-label="Bar chart — No data"' in out

    def test_custom_empty_text(self) -> None:
        with render_isolated():
            out = serialize(BarChart([], empty_text="Nothing yet").render())
        assert "Nothing yet" in out

    def test_multi_series_emits_grouped_bars(self) -> None:
        series = [
            Series(name="2024", data=[("Q1", 10), ("Q2", 14), ("Q3", 9)]),
            Series(name="2025", data=[("Q1", 12), ("Q2", 18), ("Q3", 11)]),
        ]
        with render_isolated():
            out = serialize(BarChart(series).render())
        # 2 series × 3 categories = 6 visible bars (each + a hit overlay).
        assert out.count("bz-bar-fill") == 6

    def test_multi_series_emits_legend(self) -> None:
        series = [
            Series(name="2024", data=[("Q1", 10)]),
            Series(name="2025", data=[("Q1", 12)]),
        ]
        with render_isolated():
            out = serialize(BarChart(series).render())
        assert "2024" in out
        assert "2025" in out

    def test_single_series_skips_legend(self) -> None:
        with render_isolated():
            out = serialize(BarChart(SAMPLE).render())
        # Wrapper has one direct child (the svg), no legend div sibling.
        assert out.count('<div class="flex items-center gap-2"') == 0

    def test_multi_series_palette_cycles(self) -> None:
        series = [
            Series(name="A", data=[("X", 5)]),
            Series(name="B", data=[("X", 8)]),
            Series(name="C", data=[("X", 3)]),
        ]
        with render_isolated():
            out = serialize(BarChart(series).render())
        # Default palette starts at primary → success → warning.
        assert "fill-(--bz-solid)" in out
        assert "bz-c-primary" in out
        assert "bz-c-success" in out
        assert "bz-c-warning" in out

    def test_negative_values_anchor_at_zero(self) -> None:
        with render_isolated():
            out = serialize(
                BarChart([("Loss", -5), ("Gain", 10)]).render()
            )
        # Both bars present, no crash.
        assert out.count("bz-bar-fill") == 2

    def test_stacked_variant_emits_one_segment_per_series_per_category(self) -> None:
        with render_isolated():
            out = serialize(BarChart(
                _STACKED_MULTI, variant="stacked").render())
        # 3 series × 2 categories = 6 segments total ; same count as
        # grouped but rendered in a different layout.
        assert out.count("<rect") == 6
        # Each category's bar carries its 3 segments — the tooltip
        # display for Q1 / Q2 must show all three series labels.
        for cat in ("Q1", "Q2"):
            assert out.count(f"{cat}:") == 3

    def test_stacked_y_domain_spans_per_category_sum(self) -> None:
        # Q2 total = 14 + 6 + 12 = 32 → axis should bracket past 32.
        with render_isolated():
            out = serialize(BarChart(
                _STACKED_MULTI, variant="stacked").render())
        # The nice-bracket ticks for [0, 32+5%] = [0, 33.6] cover up
        # to 35 (5×7 with the Heckbert nice-numbers algorithm).
        assert ">35<" in out or ">40<" in out

    def test_stacked_variant_skipped_on_single_series(self) -> None:
        # Single series with variant="stacked" should render exactly
        # like the grouped default ; the stacked branch only fires
        # when ``len(series) > 1``.
        single = [("Jan", 12), ("Feb", 18), ("Mar", 25)]
        with render_isolated():
            grouped = serialize(BarChart(single).render())
            stacked = serialize(BarChart(single, variant="stacked").render())
        # Same bar count (1 per category) ; identical bar geometry.
        assert grouped.count("bz-bar-fill") == stacked.count("bz-bar-fill") == 3

    # ──────────────────────────────────────────────────────────────
    # Orientation matrix : horizontal mode
    # ──────────────────────────────────────────────────────────────

    def test_horizontal_orientation_renders_y_category_labels(self) -> None:
        # Horizontal mode puts category labels on the left (Y axis).
        # The vertical mode uses an x-axis-labels group ; horizontal
        # uses a y-labels group instead.
        with render_isolated():
            out = serialize(BarChart(
                _SAMPLE_SINGLE, orientation="horizontal").render())
        assert "bz-bar-y-labels" in out
        assert "bz-bar-x-labels" not in out

    def test_horizontal_grouped_emits_one_rect_per_data_point(self) -> None:
        with render_isolated():
            out = serialize(BarChart(
                _SAMPLE_SINGLE, orientation="horizontal").render())
        # 4 categories × 1 series = 4 visible bars, just like vertical.
        assert out.count("bz-bar-fill") == 4

    def test_horizontal_stacked_emits_segments_per_category(self) -> None:
        with render_isolated():
            out = serialize(BarChart(
                _STACKED_MULTI, orientation="horizontal",
                variant="stacked",
            ).render())
        # 3 series × 2 categories = 6 segments.
        assert out.count("<rect") == 6
        # All series labels appear in the per-category tooltips.
        for cat in ("Q1", "Q2"):
            assert out.count(f"{cat}:") == 3

    def test_horizontal_reference_lines_render_vertical(self) -> None:
        from bretzel.components.charts.reference import Reference
        with render_isolated():
            out = serialize(BarChart(
                _SAMPLE_SINGLE, orientation="horizontal",
                reference_lines=[Reference(value=15, label="Goal",
                                           color="success")],
            ).render())
        # Reference line group is emitted ; the line uses x1==x2
        # (vertical) rather than y1==y2 (horizontal-mode equivalent
        # of vertical-orientation refs).
        assert "bz-bar-refs" in out
        assert ">Goal" in out

    # ──────────────────────────────────────────────────────────────
    # 100 %% stacked variant — vertical AND horizontal
    # ──────────────────────────────────────────────────────────────

    def test_stacked_100_normalises_to_percentage_domain(self) -> None:
        # The value scale spans 0-100 regardless of the raw data
        # magnitudes ; the displays carry both the percentage and the
        # original numeric value.
        with render_isolated():
            out = serialize(BarChart(
                _STACKED_MULTI, variant="stacked_100",
            ).render())
        # Y-axis ticks include 100 (the bracketed top).
        assert ">100<" in out
        # Tooltip displays carry the percentage marker.
        assert "%" in out

    def test_stacked_100_horizontal_renders(self) -> None:
        # The horizontal × stacked_100 combo just composes : reuse
        # the horizontal layout machinery + the 100 %% normalisation.
        with render_isolated():
            out = serialize(BarChart(
                _STACKED_MULTI, orientation="horizontal",
                variant="stacked_100",
            ).render())
        # 6 segments (3 series × 2 categories) ; horizontal y labels.
        assert out.count("<rect") == 6
        assert "bz-bar-y-labels" in out

    def test_stacked_100_skipped_on_single_series(self) -> None:
        # Single-series payloads ignore the variant — 100 %% stacking
        # of one series renders identically to the grouped default.
        with render_isolated():
            grouped = serialize(BarChart(_SAMPLE_SINGLE).render())
            stacked100 = serialize(BarChart(
                _SAMPLE_SINGLE, variant="stacked_100",
            ).render())
        # Same bar count, same shape.
        assert grouped.count("bz-bar-fill") == stacked100.count("bz-bar-fill") == 4

    def test_per_bar_on_item_click_wires_action(self) -> None:
        with render_isolated():
            out = serialize(
                BarChart(SAMPLE, on_item_click=_click_handler).render()
            )
        # V3 wire : each bar carries its own hx-post action, the
        # partial-bound (label, value) pair riding as the _args blob.
        assert 'hx-post="/_bretzel/action/' in out
        assert 'hx-trigger="click"' in out
        assert "_args" in out  # hx-vals payload from the partial
        assert "cursor-pointer" in out

    def test_hover_target_is_full_column_overlay(self) -> None:
        # The tooltip payload + handlers ride the transparent
        # ``.bz-bar-hit`` overlay (widened target), NOT the visible bar.
        # The overlay spans the full plot height so a tiny bar is still
        # easy to hover ; the runtime re-anchors the tooltip on the
        # sibling ``.bz-bar-fill`` (see 10_charts.js).
        import re
        with render_isolated():
            out = serialize(BarChart([("Jan", 1), ("Feb", 40)]).render())
        # Every hit rect carries the hover wiring + display.
        hit_rects = re.findall(r"<rect[^>]*bz-bar-hit[^>]*>", out)
        assert len(hit_rects) == 2
        for r in hit_rects:
            assert "data-bz-display" in r
            assert 'bz-on:mouseenter="show($event)"' in r
        # The two bars have very different heights (value 1 vs 40) but
        # their hit overlays share one height — the full plot band.
        heights = {
            re.search(r'height="([0-9.]+)"', r).group(1) for r in hit_rects
        }
        assert len(heights) == 1
        # The visible bar itself no longer carries the tooltip payload.
        fill_rects = re.findall(r"<rect[^>]*bz-bar-fill[^>]*>", out)
        assert len(fill_rects) == 2
        for r in fill_rects:
            assert "data-bz-display" not in r
            assert "bz-on:mouseenter" not in r

    def test_no_bindable_props(self) -> None:
        assert BarChart.BINDABLE_PROPS == ()
