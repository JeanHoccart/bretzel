"""Couches SVG partagées par les charts — les morceaux qui construisent
des ``Element``.

Distinct de :mod:`._svg`, qui est volontairement I/O-free (maths pures,
aucun import Bretzel, aucune construction d'``Element``). Ici on assemble
des nœuds, donc ça ne pouvait pas y aller.

Trois couches, chacune était recopiée d'un chart à l'autre (audit F10,
F43, F45) :

- :func:`render_empty_state` — l'état vide, un ``ui.empty_state`` dans
  une boîte à la taille du tracé ;
- :func:`render_axis_layer` — l'axe vertical + gridlines + labels ;
- :func:`render_static_legend` — la légende non-interactive.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from bretzel.components.base import reject_component
from bretzel.components.charts._svg import _fmt, format_value
from bretzel.core.tree import Element
from bretzel.core.tree import TextNode as TextNode


def reject_empty_text_component(value: Any, *, owner: str) -> None:
    """``empty_text=`` n'est pas un slot — les quatre charts le refusent.

    La raison est structurelle et se lit dans :func:`render_empty_state`
    juste dessous : le texte part à DEUX endroits, le titre de
    l'``EmptyState`` **et** l'``aria-label`` de la boîte. Un attribut
    HTML ne porte qu'une string, donc un Component y serait sérialisé en
    son ``repr`` Python pour le lecteur d'écran — c'est mot pour mot
    l'argument par lequel ``file_upload.label`` refuse déjà.

    ⚠️ La raison a survécu au changement de rendu (SVG → ``EmptyState``,
    2026-09-07) parce qu'elle porte sur le DOUBLE emploi du texte, pas
    sur la balise. Elle disait « un ``<text>`` SVG et l'``aria-label`` du
    ``<svg>`` » ; les deux destinations existent toujours.

    Écrit une fois ici plutôt que quatre fois dans les charts : la raison
    est la même pour les quatre, et une raison recopiée quatre fois
    dérive (audit F10/F43/F45, le motif de ce module).
    """
    reject_component(
        value,
        owner=owner,
        prop="empty_text",
        because=(
            "ce texte part AUSSI dans l'``aria-label`` de la boîte, et un "
            "attribut HTML ne peut porter qu'une string (le Component y "
            "serait annoncé au lecteur d'écran sous son repr Python)."
        ),
        instead=(
            "Pour un état vide composé, c'est ``empty=`` : "
            "``ui.bar_chart(data, empty=lambda: ui.button('Importer'))``."
        ),
    )


def render_empty_state(
    component: Any,
    *,
    width: int,
    height: int,
    kind: str,
    message: str,
    icon: str | None,
    description: str | None,
    escape: Callable[[], Any] | None,
    size_key: str,
) -> Element:
    """L'état vide d'un chart : un ``ui.empty_state`` dans une boîte à la
    taille du tracé, ou l'échappatoire que l'auteur a posée.


    **Pourquoi ce n'est plus un ``<text>`` SVG centré.** Les quatre
    charts n'offraient que ``empty_text``, quand ``table``,
    ``datatable`` et ``diagram`` offrent les quatre — trois profondeurs
    pour un même besoin (audit du 2026-09-06, § 1.3). Un graphique vide
    disait « No data » et rien d'autre : ni pourquoi, ni quoi faire.
    Composer :class:`EmptyState`, comme le fait ``diagram``, aligne les
    quatre sur le reste du catalogue et leur donne l'icône, la
    hiérarchie de titre et l'espacement du thème sans les réécrire.

    ⚠️ **``role="img"`` + ``aria-label`` sur la BOÎTE**, pas sur le
    contenu, et c'est ce qui préserve le correctif F24 : un scatter vide
    s'annonçait « Line chart » quand l'helper était privé à line_chart.
    ``kind`` reste donc obligatoire, et ``role="img"`` rend les
    descendants présentationnels — exactement la sémantique qu'avait le
    ``<svg role="img">``, sans quoi le lecteur d'écran perdrait
    l'identité du composant en gagnant le message.

    ⚠️ **``_detach_from_parent`` AVANT ``render()``.** Un Component bâti
    dans un ``render()`` s'auto-enregistre au parent ACTIF et fuit —
    piège « Icon construit dans render() sans detach » de traps.md, payé
    par ``diagram`` avant nous.
    """
    from bretzel.components.base import coerce_children
    from bretzel.components.base.component import Component
    from bretzel.components.feedback.empty_state import EmptyState

    box_attrs = {
        "class": "flex items-center justify-center w-full",
        "style": f"min-height:{height}px",
        "role": "img",
        "aria-label": f"{kind} — {message}",
    }
    if escape is not None:
        return Element(
            tag="div", attrs=box_attrs, children=coerce_children(escape())
        )
    empty = EmptyState(
        message,
        icon=icon,
        description=description,
        # L'état vide suit le palier du chart : sans ça un ``size=`` ne
        # changerait RIEN sur un graphique vide — le kwarg mort que ce
        # dépôt traque. Même raison, même ligne que ``diagram``.
        size=size_key,
    )
    Component._detach_from_parent(empty)
    return Element(tag="div", attrs=box_attrs, children=(empty.render(),))


def render_axis_layer(
    slot: Callable[..., str],
    ticks: list[float],
    y_scale: Callable[[float], float],
    plot_left: float,
    plot_right: float,
    axis_font: int,
    show_axis: bool,
    show_gridlines: bool,
    y_format: Any,
    y_unit: str | None = None,
    *,
    group_class: str,
) -> Element:
    """L'axe vertical : la ligne d'axe, les gridlines horizontales, les
    labels de graduation.

    ``group_class`` est la classe du ``<g>`` conteneur. Elle est
    paramétrée — et non unifiée — parce que line et bar émettent des noms
    différents (``bz-line-axes`` / ``bz-bar-axes``) qu'aucun CSS ni JS du
    framework ne lit : les fusionner ne gagnerait rien et casserait un
    éventuel sélecteur applicatif. Les unifier reste possible, ce sera un
    geste conscient.

    (BarChart en portait une copie identique au caractère près, modulo
    ce nom de classe et le retour à la ligne — audit F10.)
    """
    gridline_cls = slot("gridline")
    axis_cls = slot("axis")
    label_cls = slot("axis_label")
    children: list[Element] = []
    if show_axis:
        children.append(Element(tag="line", attrs={
            "class": axis_cls,
            "x1": _fmt(plot_left), "x2": _fmt(plot_left),
            "y1": _fmt(y_scale(ticks[0])),
            "y2": _fmt(y_scale(ticks[-1])),
        }, children=()))
    for tick in ticks:
        ty = y_scale(tick)
        if show_gridlines:
            children.append(Element(tag="line", attrs={
                "class": gridline_cls,
                "x1": _fmt(plot_left), "x2": _fmt(plot_right),
                "y1": _fmt(ty), "y2": _fmt(ty),
            }, children=()))
        if show_axis:
            children.append(Element(tag="text", attrs={
                "class": label_cls,
                "x": _fmt(plot_left - 6), "y": _fmt(ty),
                "font-size": str(axis_font),
                "text-anchor": "end",
                "dominant-baseline": "middle",
            }, children=(TextNode(format_value(tick, y_format, y_unit)),)))
    return Element(tag="g", attrs={"class": group_class},
                   children=tuple(children))


def render_static_legend(
    slot: Callable[..., str],
    entries: Sequence[tuple[str | None, str]],
) -> Element:
    """La légende non-interactive : une pastille + un libellé par entrée.

    ``entries`` est une séquence de ``(couleur, libellé)`` — les charts à
    séries passent ``(s.color, s.name)``, le camembert passe
    ``(palette[i], label)``. C'est la seule chose qui différait entre les
    deux copies (audit F45) ; la version interactive (line / scatter,
    avec toggle de série) reste distincte, elle a un vrai comportement.
    """
    label_cls = slot("legend_label")
    children: list[Element] = []
    for colour, label in entries:
        children.append(Element(tag="div", attrs={
            "class": "flex items-center gap-2",
        }, children=(
            Element(tag="span", attrs={"class": slot("legend_dot", colour)},
                    children=()),
            Element(tag="span", attrs={"class": label_cls},
                    children=(TextNode(label),)),
        )))
    return Element(tag="div", attrs={"class": slot("legend")},
                   children=tuple(children))


__all__ = [
    "render_axis_layer",
    "render_empty_state",
    "render_static_legend",
]
