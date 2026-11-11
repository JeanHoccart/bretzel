"""``Stat`` — a key figure, and what it means.

Usage ::

    ui.stat("Clients actifs", 1284, delta=36)
    ui.stat("Moyenne de la classe", 12.4, max=20, delta=0.8,
            description="vs 1er trimestre")
    ui.stat("Copies saisies", 19, max=24, target=24)
    ui.stat("Sous 10 de moyenne", 4, unit="élèves", max=28, target=2,
            good="down", delta=-2)
    ui.stat("Désabonnements", 2.1, unit="%", target=2, good="down")

**Nothing picks a shape; the meaning draws it.** No ``variant=``, no
``color=``: what the app SAYS about the number decides what is drawn —
the way HTML's ``<meter>`` derives its colour from ``low`` / ``high`` /
``optimum`` rather than from a colour attribute.

- ``max=`` — the value has a range, from 0 to ``max``: a gauge appears,
  its scale written under it (0 … max), as on the gauges of Power BI and
  Plotly. Without it, a number alone.
- ``target=`` — an objective. On a gauge, a mark across it; the gauge is
  ``success`` when the objective is reached, ``warning`` when it is not,
  ``primary`` when there is none. Without a range, a line says it
  (« Objectif ≤ 2 % · pas atteint »).
- ``good=`` — which way is better, ``"up"`` (the default) or
  ``"down"`` (a cost, an absence). It decides whether the objective is
  reached, and colours the change: ``success`` the good way, ``error``
  the other. Streamlit's ``delta_color="inverse"``, Tremor's
  ``isIncreasePositive`` — named by what it means, not by its colour.
- ``delta=`` — the change since a reference, a number (signed for you,
  « +0,8 ») or a text already written (« +12,4 % »: its first character
  gives the way).
- ``unit=`` — what the number counts (« € », « élèves »); ``"%"`` takes
  the page's shape of a percentage (« 71 % » in French, « 71% » in
  English).

The value is a NUMBER, written in the page's language (« 48 240 »,
« 12,4 »): the app does not format it. A text is accepted too — an
amount the app already wrote, a « — » — but a text has no size, so it
takes neither a range nor an objective. ``None`` writes « — ».

The words are the inputs' and the charts' (R1): ``max`` as on
``ui.progress`` and ``ui.slider``, ``label`` first (R5),
``description`` as on ``ui.empty_state``. The gauge is a
``role="meter"`` — a measure in a known range, not a task's progress —
with its value, its bounds and its text for a screen reader.
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import Component
from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.charts._svg import number
from bretzel.components.charts.stat.theme import STAT_THEME
from bretzel.components.feedback.badge import Badge
from bretzel.core.tree import Element, Node, TextNode
from bretzel.render import text
from bretzel.theme.bridges import bridge_class

#: The two ways a number can be better.
GOOD = ("up", "down")

#: The leading characters that give a written change its way.
_UP, _DOWN = "+", "-−"

#: The value of a stat that has none yet (no marks, no sale).
NO_VALUE = "—"


def _amount(name: str, value: Any) -> float | None:
    """A number given to ``name=``, or ``None`` when not given."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ComponentUsageError(
            f"Stat: {name}={value!r} — expected a number.")
    return float(value)


def reached(value: float, target: float, good: str) -> bool:
    """Whether ``value`` meets ``target`` the good way."""
    return value >= target if good == "up" else value <= target


class Stat(Component):
    """A key figure: its label, its value, and what the app says it means."""

    THEME: ClassVar[dict[str, Any]] = STAT_THEME
    THEME_KEY: ClassVar[str] = "stat"
    IS_CONTAINER: ClassVar[bool] = False

    def __init__(
        self,
        label: str | Component | None = None,
        value: float | str | None = None,
        *,
        unit: str | None = None,
        max: float | None = None,
        target: float | None = None,
        good: str = "up",
        delta: float | str | None = None,
        description: str | Component | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        if good not in GOOD:
            raise ComponentUsageError(
                f"Stat: good={good!r} — expected \"up\" (the default: more "
                "is better) or \"down\" (less is better: a cost, an absence).")
        if isinstance(value, bool) or not isinstance(value, int | float | str | None):
            raise ComponentUsageError(
                f"Stat: value={value!r} — expected a number (the page writes "
                "it), a text already written, or None.")
        self._max = _amount("max", max)
        self._target = _amount("target", target)
        if isinstance(value, str) and (self._max is not None or self._target is not None):
            raise ComponentUsageError(
                f"Stat: value={value!r} is a text — a gauge and an objective "
                "need its size. Pass the number (12.4), the page writes it.")
        if self._max is not None and self._max <= 0:
            raise ComponentUsageError(
                f"Stat: max={max!r} — the range goes from 0 to max, so max is "
                "above 0.")
        if delta is not None and (isinstance(delta, bool)
                                  or not isinstance(delta, int | float | str)):
            raise ComponentUsageError(
                f"Stat: delta={delta!r} — expected a number or a text.")
        self._label = label
        self._value = value
        self._unit = unit
        self._good = good
        self._description = description
        self._delta: Component | None = self._change(delta)

    # ── What the app said ─────────────────────────────────────────────

    def _change(self, delta: float | str | None) -> Component | None:
        """The change, as a badge coloured by the good way — or nothing."""
        if delta is None or delta == "":
            return None
        if isinstance(delta, str):
            written, way = delta, ("up" if delta[0] in _UP
                                   else "down" if delta[0] in _DOWN else None)
        else:
            way = "up" if delta > 0 else "down" if delta < 0 else None
            written = ("+" if delta > 0 else "−" if delta < 0 else "") + number(abs(delta))
        color = "muted" if way is None else (
            "success" if way == self._good else "error")
        icon = None if way is None else f"trending-{way}"
        return Component.adopt_slot(Badge(written, color=color, icon_left=icon))

    def _written(self) -> str:
        """The value as the page shows it."""
        value = self._value
        if value is None:
            return NO_VALUE
        if isinstance(value, str):
            return value
        return self._with_unit(number(value))

    def _with_unit(self, shown: str) -> str:
        if self._unit == "%":
            return text("number.percent", value=shown)
        return f"{shown}\u202f{self._unit}" if self._unit else shown

    def _tone(self) -> str | None:
        """``success`` / ``warning`` against the objective, ``None`` without."""
        if self._target is None or not isinstance(self._value, int | float):
            return None
        return "success" if reached(float(self._value), self._target, self._good) else "warning"

    def _objective(self) -> str:
        key = "stat.target_at_most" if self._good == "down" else "stat.target"
        target = number(self._target or 0)
        # On a gauge the unit is the scale's, written once at its end.
        return text(key, value=target if self._max is not None else self._with_unit(target))

    # ── Render ────────────────────────────────────────────────────────

    def _line(self, slot: str, node: Node, tag: str = "p") -> Element:
        return Element(tag=tag, attrs={"class": self.compose_class(slot)}, children=(node,))

    def _gauge(self, written: str, tone: str | None) -> list[Node]:
        top = self._max or 1.0

        def share(n: float) -> str:
            return f"{max(0.0, min(1.0, n / top)) * 100:.2f}%"

        value = float(self._value)  # type: ignore[arg-type]
        marks: list[Node] = [Element(
            tag="div", attrs={"class": self.compose_class("fill"), "style": f"width: {share(value)}"},
            children=())]
        if self._target is not None:
            marks.append(Element(
                tag="div",
                attrs={"class": self.compose_class("target"), "style": f"left: {share(self._target)}"},
                children=()))
        meter: dict[str, str] = {
            "class": f"{self.compose_class('meter')} {bridge_class(tone or 'primary')}",
            "role": "meter",
            "aria-valuemin": "0",
            "aria-valuemax": f"{top:g}",
            "aria-valuenow": f"{value:g}",
            "aria-valuetext": written,
        }
        if isinstance(self._label, str) and self._label:
            meter["aria-label"] = self._label
        start: Element
        if self._target is not None:
            start = Element(tag="span", attrs={
                "class": f"{self.compose_class('toned')} {bridge_class(tone or 'primary')}"},
                children=(TextNode(self._objective()),))
        else:
            start = Element(tag="span", attrs={}, children=(TextNode(number(0)),))
        scale = Element(tag="div", attrs={"class": self.compose_class("scale")}, children=(
            start, Element(tag="span", attrs={}, children=(TextNode(number(top)),))))
        return [Element(tag="div", attrs=meter, children=tuple(marks)), scale]

    def render(self) -> Element:
        written = self._written()
        tone = self._tone()
        children: list[Node] = []

        label = self.emit_text_slot(self._label)
        if label is not None:
            children.append(self._line("label", label))

        row: list[Node] = [Element(tag="span", attrs={
            "class": self.compose_class("value"), "title": written,
        }, children=(TextNode(written),))]
        if self._delta is not None:
            row.append(self._delta.render())
        children.append(Element(
            tag="div", attrs={"class": self.compose_class("value_row")}, children=tuple(row)))

        measured = isinstance(self._value, int | float)
        if measured and self._max is not None:
            children.extend(self._gauge(written, tone))
        elif measured and self._target is not None and tone is not None:
            status = text("stat.reached") if tone == "success" else text("stat.missed")
            children.append(Element(
                tag="p",
                attrs={"class": f"{self.compose_class('status')} {bridge_class(tone)}"},
                children=(TextNode(f"{self._objective()} · {status}"),)))

        description = self.emit_text_slot(self._description)
        if description is not None:
            children.append(self._line("description", description))

        attrs = self.emit_attrs()
        attrs["class"] = self.compose_class("root", apply_variant_size_modifiers=False)
        return Element(tag=self._tag, attrs=attrs, children=tuple(children))
