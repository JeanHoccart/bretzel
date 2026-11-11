"""``ui.stat`` — a key figure, its gauge drawn by its meaning (2026-11-06).

What is tested is the rule Jean validated: nothing picks a shape, the
meaning draws it. ``max=`` → a gauge; ``target=`` → the mark and the
colour; ``good=`` → which way is better, for the objective and the
change. And the numbers in the page's language.
"""

from __future__ import annotations

import re

import pytest

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.charts._svg import number
from bretzel.components.charts.stat.stat import Stat, reached
from bretzel.core.serialize import serialize
from bretzel.render.languages.fr import TEXTS as FRENCH
from bretzel.render.texts import DEFAULT_TEXTS


def html(*args, french: bool = False, **props) -> str:
    with render_isolated() as ctx:
        if french:
            ctx.texts = {**DEFAULT_TEXTS, **FRENCH}
        return serialize(Stat(*args, **props).render())


def words(markup: str) -> list[str]:
    """The texts of the stat, in order — the icons' SVG left out."""
    markup = re.sub(r"<svg.*?</svg>", "", markup, flags=re.S)
    return [t.strip() for t in re.split(r"<[^>]+>", markup) if t.strip()]


def meter(markup: str) -> str | None:
    found = re.search(r"<div[^>]*role=\"meter\"[^>]*>", markup)
    return found.group(0) if found else None


def bridge(markup: str, slot_text: str) -> str | None:
    """The colour bridge of the element that writes ``slot_text``."""
    found = re.search(rf'class="[^"]*bz-c-(\w+)[^"]*"[^>]*>{re.escape(slot_text)}<', markup)
    return found.group(1) if found else None


class TestTheMeaningDrawsIt:
    def test_a_number_alone_draws_no_gauge(self) -> None:
        out = html("Active customers", 1284)
        assert meter(out) is None
        assert words(out) == ["Active customers", "1,284"]

    def test_a_range_draws_a_gauge_and_its_scale(self) -> None:
        out = html("Class average", 12.4, max=20)
        gauge = meter(out)
        assert gauge is not None
        assert 'aria-valuemin="0"' in gauge and 'aria-valuemax="20"' in gauge
        assert 'aria-valuenow="12.4"' in gauge and 'aria-valuetext="12.4"' in gauge
        assert 'aria-label="Class average"' in gauge
        assert "width: 62.00%" in out
        # No objective: the primary colour, the scale from 0.
        assert "bz-c-primary" in gauge
        assert words(out)[-2:] == ["0", "20"]

    def test_an_objective_reached_is_success_missed_is_warning(self) -> None:
        assert "bz-c-success" in meter(html("Mastered", 71, unit="%", max=100, target=60))
        assert "bz-c-warning" in meter(html("Copies typed", 19, max=24, target=24))
        # Exactly on target is reached.
        assert "bz-c-success" in meter(html("On target", 60, max=100, target=60))

    def test_the_objective_marks_the_track(self) -> None:
        out = html("Copies typed", 19, max=24, target=12)
        assert "left: 50.00%" in out
        assert "Target 12" in words(out)

    def test_less_is_better_turns_the_objective_around(self) -> None:
        out = html("Below 10", 4, unit="pupils", max=28, target=2, good="down")
        assert "bz-c-warning" in meter(out)
        assert "Target ≤ 2" in words(out)
        assert "bz-c-success" in meter(
            html("Below 10", 1, max=28, target=2, good="down"))

    def test_an_objective_without_a_range_is_said_in_a_line(self) -> None:
        out = html("Churn", 2.1, unit="%", target=2, good="down")
        assert meter(out) is None
        assert "Target ≤ 2% · not reached" in words(out)
        assert bridge(out, "Target ≤ 2% · not reached") == "warning"
        assert "Target 50\u202f€ · reached" in words(html("Sales", 60, unit="€", target=50))

    def test_past_the_range_the_gauge_is_full_not_overflowing(self) -> None:
        out = html("Over", 23, max=20, target=30)
        assert "width: 100.00%" in out and "left: 100.00%" in out
        assert "width: 0.00%" in html("Under", -3, max=10)


class TestTheChange:
    def _badge(self, **props) -> tuple[str, str | None]:
        out = html("x", 10, **props)
        found = re.search(r'<span[^>]*bz-c-(\w+)[^>]*>(?:(?!</span>).)*?([+−-]?[\d.,]+[^<]*)</span>', out, re.S)
        assert found is not None, out
        return found.group(2).strip(), found.group(1)

    def test_a_number_is_signed_and_coloured_the_good_way(self) -> None:
        assert self._badge(delta=0.8) == ("+0.8", "success")
        assert self._badge(delta=-2) == ("−2", "error")
        assert self._badge(delta=-2, good="down") == ("−2", "success")
        assert self._badge(delta=3, good="down") == ("+3", "error")

    def test_zero_is_neither_way(self) -> None:
        out = html("x", 10, delta=0)
        assert "bz-c-muted" in out and "trending" not in out

    def test_a_written_change_gives_its_way_by_its_first_character(self) -> None:
        assert "bz-c-success" in html("x", 10, delta="+12.4 %")
        assert "bz-c-error" in html("x", 10, delta="−3 %")
        assert "bz-c-success" in html("x", 10, delta="-3 %", good="down")
        assert "bz-c-muted" in html("x", 10, delta="stable")

    def test_no_change_no_badge(self) -> None:
        assert "trending" not in html("x", 10)


class TestTheNumbers:
    def test_the_value_is_written_in_the_page_s_language(self) -> None:
        assert words(html("Revenue", 48240, unit="€"))[1] == "48,240\u202f€"
        fr = words(html("Revenue", 48240, unit="€", french=True))
        assert fr[1] == "48\u202f240\u202f€"
        assert words(html("Average", 12.4, french=True))[1] == "12,4"
        assert words(html("Share", 71, unit="%", french=True))[1] == "71\u202f%"
        assert words(html("Share", 71, unit="%"))[1] == "71%"

    def test_the_objective_s_words_follow_the_language(self) -> None:
        out = words(html("Churn", 2.1, unit="%", target=2, good="down", french=True))
        assert "Objectif ≤ 2\u202f% · pas atteint" in out

    def test_a_text_is_shown_as_written(self) -> None:
        assert words(html("Revenue", "1 234,50 €"))[1] == "1 234,50 €"

    def test_no_value_is_a_dash_and_no_gauge(self) -> None:
        out = html("Average", None, max=20)
        assert words(out) == ["Average", "—"] and meter(out) is None

    def test_number_groups_and_drops_trailing_zeros(self) -> None:
        assert number(1234567.891) == "1,234,567.89"
        assert number(12.0) == "12"
        assert number(-1234.5) == "-1,234.5"
        assert number(-0.5) == "-0.5"


class TestRefusals:
    @pytest.mark.parametrize("props", [
        {"value": "12,4", "max": 20},
        {"value": "12,4", "target": 10},
        {"value": 4, "good": "better"},
        {"value": 4, "max": 0},
        {"value": 4, "max": "20"},
        {"value": True},
        {"value": 4, "delta": [1]},
    ])
    def test_a_misuse_is_refused_out_loud(self, props) -> None:
        with render_isolated(), pytest.raises(ComponentUsageError):
            Stat("x", **props)


def test_reached_reads_the_good_way() -> None:
    assert reached(5, 5, "up") and reached(6, 5, "up") and not reached(4, 5, "up")
    assert reached(5, 5, "down") and reached(4, 5, "down") and not reached(6, 5, "down")


def test_the_description_closes_the_card() -> None:
    assert words(html("Average", 12.4, max=20, description="vs first term"))[-1] == "vs first term"
