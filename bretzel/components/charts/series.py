"""Light ``Series`` dataclass for multi-series chart payloads.

A chart's ``data=`` kwarg accepts three shapes :

- ``list[number]``           — single series, x = index (sparklines only)
- ``list[tuple[x, y]]``      — single series with explicit x values
- ``list[Series]``           — N series for bar / line charts

``Series`` carries an optional ``color=`` override so an app can pin a
specific series to a semantic color (``"success"`` for the active
metric, ``"muted"`` for the comparison baseline). When ``color=None``
the chart picks from its theme palette in declaration order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class Series:
    """One data series in a multi-series chart."""

    name: str
    data: list[float | tuple[float, float]] = field(default_factory=list)
    color: str | None = None


def to_timestamp(x: Any) -> float:
    """Convert a ``date`` / ``datetime`` / number to a POSIX timestamp.

    ``date`` is widened to midnight UTC so ``timestamp()`` doesn't
    depend on the host TZ for day-precision inputs.
    """
    if isinstance(x, datetime):
        return x.timestamp()
    if isinstance(x, date):
        return datetime(x.year, x.month, x.day).timestamp()
    return float(x)


def coerce_xy_series(
    data: Any,
    palette: tuple,
    *,
    default_color: str,
    owner: str,
    validate_shared_x: bool,
    allow_index: bool,
) -> list[Series]:
    """Normalise a chart's ``data=`` into ``list[Series]`` of ``(x, y)``.

    Accepts the three documented shapes — ``list[Series]``,
    ``list[(x, y)]``, ``list[number]`` — converts x values through
    :func:`to_timestamp` and cycles ``palette`` for series that carry no
    ``color=``.

    Two flags carry the whole difference between LineChart and
    ScatterChart, which maintained near-identical private copies (audit
    F46) :

    - ``validate_shared_x`` : a line chart draws one shared x axis, so
      its series MUST agree on x values in the same order ; scatter
      series are independent clouds and must not be constrained.
      ``owner`` names the component in that error message.
    - ``allow_index`` : a bare ``list[number]`` means "x = index" on a
      line, and means nothing on a scatter (a cloud needs both
      coordinates), where such an item is skipped.
    """
    if not data:
        return []
    if isinstance(data[0], Series):
        out: list[Series] = []
        for i, s in enumerate(data):
            colour = s.color or palette[i % len(palette)]
            pairs = [(to_timestamp(x), float(y)) for x, y in s.data]
            out.append(Series(name=s.name, data=pairs, color=colour))
        if validate_shared_x and len(out) > 1:
            ref = [pt[0] for pt in out[0].data]
            for s in out[1:]:
                if [pt[0] for pt in s.data] != ref:
                    raise ValueError(
                        f"{owner} multi-series payloads must share "
                        "the same x values in the same order — got "
                        f"{[pt[0] for pt in s.data]!r} vs {ref!r}."
                    )
        return out

    pairs: list[tuple] = []
    for i, item in enumerate(data):
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            try:
                pairs.append((to_timestamp(item[0]), float(item[1])))
            except (TypeError, ValueError):
                continue
        elif allow_index:
            try:
                pairs.append((float(i), float(item)))
            except (TypeError, ValueError):
                continue
    return [Series(name="", data=pairs, color=default_color)]


def coloured_slot(component: Any, name: str, override: str | None,
                  fallback: str) -> str:
    """La classe d'un slot de chart, PLUS le pont de sa couleur.

    Un chart est le seul composant dont **plusieurs enfants portent des
    couleurs différentes** : une série par couleur, sur une racine qui
    n'en a qu'une. Le pont posé par le socle sur la racine ne peut donc
    pas les servir tous.

    Depuis que les thèmes se peignent aux paliers, la classe d'un slot ne
    porte plus la couleur du tout : ``fill-(--bz-solid)`` est la même
    pour toutes les séries. C'est la classe-pont, ajoutée ici, qui dit
    laquelle. Sans elle, toutes les séries d'un même graphe rendraient de
    la couleur de la racine — mesuré le 2026-08-30 en migrant les
    thèmes : `fill-success` était devenu introuvable dans le HTML du
    `bar_chart`, alors que la série le demandait.

    ``override`` est la couleur de la SÉRIE (``Series(color=…)``),
    ``fallback`` celle du composant.

    **Le pont n'est ajouté que s'il y a un override.** Sans override la
    couleur est celle du composant, donc celle du pont que le socle a
    déjà posé sur la racine : le redire sur chaque `<line>`, chaque
    étiquette d'axe et chaque grille alourdirait le SVG pour rien.
    Mesuré en l'écrivant sans ce garde : le slot ``crosshair``, qui ne
    parle d'aucune couleur, ressortait avec un ``bz-c-primary`` collé.
    """
    classes = component.compose_class(
        name,
        apply_variant_size_modifiers=False,
    )
    if override is None:
        return classes

    from bretzel.theme.bridges import bridge_class

    return f"{classes} {bridge_class(override)}"
