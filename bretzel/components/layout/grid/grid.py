"""``Grid`` — CSS-grid container, sibling of :class:`Flex`.

Use a grid (not a flex) when you want **two-dimensional alignment** :
items lined up both along rows AND columns. Flex aligns along a
single axis ; Grid aligns along both.

API :

- ``cols=int`` — static N columns at every breakpoint.
- ``cols=dict`` — responsive : ``{"base": 1, "sm": 2, "md": 3, "lg": 4}``.
  Keys are Tailwind breakpoint prefixes ; ``"base"`` (or empty / ``"xs"``)
  applies at all sizes and gets no prefix.
- ``cols=str`` — escape hatch : ``"none"`` / ``"auto"`` / any literal
  Tailwind class (``"grid-cols-[200px_1fr]"``) flows through verbatim.
- ``min_col=`` — **la grille compte ses colonnes elle-même**. Au lieu de
  déclarer combien de colonnes à quelle largeur d'écran, on déclare la
  largeur MINIMALE d'une colonne : ``ui.grid(min_col="16rem")``. Exclusif
  avec ``cols=``.
- ``gap=`` — same 5-palier scale as :class:`Flex` / :class:`VStack`
  (``none / xs / sm / md / lg / xl``), and it takes the SAME responsive
  dict as ``cols`` : ``gap={"base": "sm", "md": "lg"}``.
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import (
    Component,
    ComponentUsageError,
    reactive_prop,
    responsive_classes,
)
from bretzel.components.layout.grid.theme import GRID_THEME
from bretzel.core.tree import Element


def _cols_class(cols: Any) -> str:
    """Translate ONE ``cols`` value into its Tailwind class.

    ``int`` → ``grid-cols-N``. ``str`` → ``"none"`` / ``"auto"`` map to
    ``grid-cols-{value}`` ; anything else flows through verbatim (raw
    Tailwind escape hatch). Breakpoints are NOT handled here —
    :func:`responsive_classes` wraps this and owns the ``{bp}:`` prefixing
    for every graded prop in the library.
    """
    if cols is None or isinstance(cols, bool):
        return ""
    if isinstance(cols, int):
        return f"grid-cols-{cols}"
    if isinstance(cols, str):
        if cols in ("none", "auto"):
            return f"grid-cols-{cols}"
        return cols
    return ""


class Grid(Component):
    """Two-dimensional layout container."""

    THEME: ClassVar[dict[str, Any]] = GRID_THEME
    THEME_KEY: ClassVar[str] = "grid"
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
    # ``cols`` ne passe pas par une table : ``_cols_class`` l'assemble en
    # f-string, et son domaine est clôturé par ``_LAYOUT_CLASSES``.
    RESPONSIVE_THEME_KEYS: ClassVar[tuple[str, ...]] = ("gaps",)
    RESPONSIVE_PROPS: ClassVar[frozenset[str]] = frozenset({"cols", "gap"})

    cols: Any = reactive_prop(default=None, emit_attr=False)
    #: La largeur MINIMALE d'une colonne. La grille en met alors autant
    #: qu'elle peut et replie le reste — ``repeat(auto-fit, minmax(X,
    #: 1fr))``, l'idiome CSS canonique, le ``minChildWidth`` de Chakra.
    #:
    #: Pourquoi il existe alors que ``cols=`` est déjà responsive : un
    #: préfixe ``xl:`` lit la largeur de la FENÊTRE, pas celle de la
    #: grille. Sous une coque à barre latérale, les deux divergent de la
    #: largeur de la barre — mesuré sur le CRM, 4 colonnes de 244 px là où
    #: le contenu n'a que 1024 px, donc un ``ui.toggle_group`` de 256 px
    #: dehors. ``auto-fit`` lit la place réelle.
    min_col: Any = reactive_prop(default=None, emit_attr=False)
    # ``Any``, not ``str`` : both graded props take a breakpoint dict.
    gap: Any = reactive_prop(default="md", emit_attr=False)

    def __init__(
        self,
        *,
        cols: int | dict | str | None = None,
        min_col: str | None = None,
        gap: str | dict | None = None,
        **kwargs: Any,
    ) -> None:
        # Forward direct : le socle drope les kwargs reactive ``None``
        # (garde le défaut) — plus de garde ``if x is not None`` à re-taper.
        super().__init__(cols=cols, min_col=min_col, gap=gap, **kwargs)
        # Les deux décident du nombre de colonnes. Les accepter ensemble
        # laisserait l'ordre de la feuille trancher — donc un résultat qui
        # ne se lit dans aucun des deux appels. Refus à la CONSTRUCTION,
        # où la pile porte encore la ligne de l'appelant.
        if cols is not None and min_col is not None:
            raise ComponentUsageError(
                "ui.grid(cols=…, min_col=…) : les deux décident du nombre "
                "de colonnes, et les deux posent `grid-template-columns` — "
                "le vainqueur dépendrait de l'ordre de la feuille Tailwind, "
                "pas du tien.\n"
                "  cols=      tu déclares combien de colonnes, par palier "
                "de FENÊTRE ;\n"
                "  min_col=   tu déclares la largeur minimale d'une "
                "colonne, et la grille compte elle-même, sur sa place RÉELLE."
            )
        # Validée ICI et pas au rendu : une levée depuis ``render``
        # remonte une pile sans aucune frame de l'appelant, donc elle nomme
        # les valeurs acceptées sans dire lequel des N ``ui.grid`` de la
        # page est fautif. Même arbitrage que ``Flex.grow``.
        if min_col is not None:
            self._min_col_class(min_col, self._min_col_table())

    def _min_col_table(self) -> dict[str, str]:
        """La table ``min_cols`` de ce composant, override utilisateur
        compris. Une méthode et pas deux lectures : ``__init__`` valide et
        ``render`` résout, et les deux doivent regarder la MÊME table —
        sinon un ``Theme(components=…)`` ferait passer la validation et
        rendre autre chose."""
        return self._resolved_theme().get("min_cols", {})

    @staticmethod
    def _min_col_class(min_col: Any, table: dict[str, str]) -> str:
        """La classe de ``min_col=``, ou une levée qui NOMME les valeurs.

        Une largeur hors table rendrait la chaîne vide : la grille
        retomberait sur une seule colonne, sans erreur et sans rien dire.
        """
        entry = table.get(min_col)
        if entry is None:
            accepted = ", ".join(repr(k) for k in table)
            raise ComponentUsageError(
                f"min_col={min_col!r} n'est pas une largeur connue. Valeurs "
                f"acceptées : {accepted}. La table est fermée pour que "
                f"chaque classe soit ENTIÈRE, donc visible au compilateur "
                f"Tailwind de prod ; pour une autre largeur, écris-la à "
                f"l'appel avec cols='grid-cols-[…]'."
            )
        return entry

    def render(self) -> Element:
        theme = self._resolved_theme()
        cols = self._reactive_values.get("cols")
        gap = self._reactive_values.get("gap") or "md"

        parts: list[str] = []
        root = theme.get("slots", {}).get("root")
        if root:
            parts.append(root)
        min_col = self._reactive_values.get("min_col")
        if min_col:
            # Ne peut plus lever : ``__init__`` a déjà refusé l'inconnu.
            parts.append(self._min_col_class(min_col, self._min_col_table()))
        else:
            cols_cls = responsive_classes(cols, _cols_class)
            if cols_cls:
                parts.append(cols_cls)
        gaps = theme.get("gaps", {})
        gap_cls = responsive_classes(gap, lambda v: gaps.get(v, ""))
        if gap_cls:
            parts.append(gap_cls)
        # Classes user posées par le wrap ``_apply_universal_modifiers`` —
        # ne pas ré-append ici (doublon). Gardé par
        # test_no_manual_user_class_append.py.

        attrs = self.emit_attrs()
        attrs["class"] = " ".join(p for p in parts if p).strip()

        return Element(
            tag=self._tag,
            attrs=attrs,
            children=self._render_children(),
        )
