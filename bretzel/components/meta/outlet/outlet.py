"""``Outlet`` — page-content injection point inside an ``@layout``.

The outlet is the only thing that bridges a layout's frame and the
page's body :

- The :func:`bretzel.render.decorators.layout.layout` decorator marks
  a function as a layout.
- At render time, the pipeline runs the layout first (which calls
  ``ui.outlet()`` once or more), finds the Outlet instances in the
  resulting tree, and feeds the page's children into them.
- The outlet renders a ``<main id="outlet_<layout>">`` whose ``id``
  doubles as the htmx swap target — clicks on internal links land
  inside this element without re-rendering the whole layout.

Auto-id : when no explicit ``id=`` is passed, the outlet derives it
from the active layout name on the render context (``ctx.layout``).
A custom suffix can be passed via ``id="left"`` to support multiple
outlets in the same layout (``outlet_<layout>_left``).

⚠️ **Layout pleine hauteur : l'outlet ne transmet AUCUNE contrainte.**

Le ``<main>`` est un bloc ordinaire, sans hauteur ni ``flex``. Une page
qui veut occuper l'écran et faire défiler une zone INTERNE (chat, boîte
mail, tableau de bord) doit donc câbler la chaîne à la main, sur DEUX
maillons — le parent de l'outlet **et** l'outlet ::

    with ui.container(classes="flex-1 min-h-0 overflow-hidden flex flex-col"):
        ui.outlet(classes="flex-1 min-h-0 flex flex-col")

    # puis, dans la page :
    with ui.vstack(classes="flex-1 min-h-0"):
        ...
        with ui.vstack(classes="flex-1 min-h-0 overflow-y-auto"):  # ← défile

Les deux sont nécessaires : ``ui.container`` est un ``block``, donc son
enfant ne peut pas prendre ``flex-1`` sans le ``flex flex-col``.

**Le mode d'échec est silencieux**, et c'est ce qui le rend cher :
sans ces classes, la zone interne grandit avec son contenu au lieu de
déborder, l'``overflow-y-auto`` n'a jamais rien à faire, et le trop-plein
est simplement clippé par un ancêtre. Mesuré le 2026-08-15 en montant
``examples/chat`` : ``<main>`` à 1 888 px dans un parent de 855 px,
aucune barre de défilement, aucune erreur. Gate :
``tests/runtime_js/test_full_height_layout_scrolls.py``.

Pourquoi ce n'est pas corrigé dans le composant : baker ces classes
changerait tous les layouts existants, et ``display:contents`` — qui
rendrait le slot vraiment transparent — risque de faire sauter le repère
ARIA du ``<main>`` selon les navigateurs. À trancher quand le shell sera
repensé ; chantier dans ``.claude/work/todo.md``.

"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import Component
from bretzel.core.tree import Element
from bretzel.render.context import maybe_current_context
from bretzel.runtime.protocol import outlet_id_for


def _derive_outlet_id(
    explicit_id: str | None,
) -> str:
    """Return the outlet's HTML ``id`` attribute value.

    The base form is ``outlet_<layout-name>``, where ``<layout-name>``
    is the innermost layout function currently being rendered. If a
    non-empty ``explicit_id`` is passed we append it as a suffix
    (``outlet_<layout>_<suffix>``) so a single layout can host
    multiple outlets. When no layout is active and no suffix was
    passed we fall back to a plain ``outlet`` — the component still
    renders, the ``id`` is just less informative.
    """
    ctx = maybe_current_context()
    layout_stack = list(getattr(ctx, "layout_stack", ()) or ()) if ctx else []
    base = outlet_id_for(layout_stack[-1]) if layout_stack else "outlet"
    if explicit_id:
        return f"{base}_{explicit_id}"
    return base


class Outlet(Component):
    """``<main>`` slot where the page content lands inside a layout."""

    DEFAULT_TAG: ClassVar[str] = "main"
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
    def __init__(
        self,
        id: str | None = None,
        **kwargs: Any,
    ) -> None:
        # Resolve the outlet's id NOW (still inside the layout's
        # ``with`` block, where ``ctx.layout_stack`` is populated).
        # The base ``Component.__init__`` accepts this ``id`` via the
        # explicit-id branch and stops auto-numbering.
        derived = _derive_outlet_id(id)
        super().__init__(id=derived, **kwargs)
        self._explicit_suffix = id

    @property
    def child_scope_id(self) -> str:
        """L'id que les enfants de la page prennent pour parent.

        **Il DIVERGE de ``self.id``, et c'est tout le mécanisme.**
        L'outlet rend un id stable — htmx le renvoie en ``HX-Target``,
        donc le bouger casserait la navigation partielle suivante. Mais
        ce que la PAGE construit dessous doit être unique à la page :
        sans ça, ``/accordion`` et ``/markdown`` émettent le même
        ``outlet_shell_container_0_…_accordion_0``, et le magasin de
        scopes du runtime — une ``Map`` indexée par cette chaîne, qu'un
        ``hx-boost`` ne vide pas — rend à la seconde l'état de la
        première.

        Mesuré le 2026-08-13 : 13 collisions sur les 68 pages du
        playground. Cf. ``RenderContext.page_scope``.
        """
        ctx = maybe_current_context()
        return f"{self.id}{ctx.child_scope_root}" if ctx else self.id

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        attrs = self.emit_attrs()
        # The outlet always carries its own ``id`` (not auto-numbered
        # — _derive_outlet_id baked it). Make sure ``emit_attrs``
        # didn't drop it because the ``_needs_identity`` heuristic
        # said no (no bindings / events / raw directives on this
        # element).
        attrs["id"] = self.id
        attrs.setdefault("data-bz-outlet", "1")
        # NO reveal-gate (``bz-show`` + ``display:none``) : the outlet is
        # server-rendered content, idiomorph morphs it in place on a swap.
        # A gate keyed on "outlet WAS the swap target" would break nested
        # layouts — a partial-nav swap targets the OUTERMOST outlet, so an
        # inner sub-layout outlet never gets the event → stays hidden →
        # sub-page renders BLANK. Cf. ``traps.md`` § "Nested partial-nav
        # blanks the inner outlet".
        children = self._render_children()
        return Element(tag=self._tag, attrs=attrs, children=children)


__all__ = ["Outlet"]
