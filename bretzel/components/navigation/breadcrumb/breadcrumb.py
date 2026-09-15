"""``Breadcrumb`` — page-location trail.

A flat row of links separated by a marker (chevron by default), with
the final entry rendered as plain text (the current location).

Deux niveaux, et c'est **l'auteur qui possède la boucle**
(``COLLECTION_OWNER = "author"``, cf. ``Component``) :

**Niveau 1 — le raccourci**, quand le fil n'est que du texte ::

    ui.breadcrumb([
        {"label": "Home", "href": "/"},
        {"label": "Projects", "href": "/projects"},
        {"label": "Tracker"},   # last item — no href, current page
    ])

Items can be plain dicts, ``(label, href)`` tuples, or bare strings ;
the last item becomes the ``current`` segment whether or not it has an
``href`` — the trail's last node is by definition where the user is.

**Niveau 2 — les enfants**, dès qu'un segment veut du balisage ::

    with ui.breadcrumb():
        ui.breadcrumb_item("Home", href="/")
        with ui.breadcrumb_item(href="/projects"):
            ui.icon("folder", size="xs")
            ui.text("Projects")
        ui.breadcrumb_item("Tracker")

C'est la forme de :class:`~bretzel.components.inputs.ToggleGroup`, et
l'idiome de dix des onze collections du catalogue. Le composant sait
tout seul quel segment est le dernier — l'auteur n'a pas à le lui dire.

Pour personnaliser le balisage d'un segment, utiliser
:class:`BreadcrumbItem` plutôt qu'un callback de rendu : ses paramètres
sont typés, autocomplétés et visibles dans ``bretzel describe``.

The separator is a string (interpreted as an Icon name or a literal
text) by default — pass ``separator="/"`` for a slash, or any
:class:`Component` / Element for a custom glyph.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base._wiring import theme_context, unwrap_transparent
from bretzel.components.navigation.breadcrumb.theme import BREADCRUMB_THEME
from bretzel.components.primitives.icon import Icon
from bretzel.core.tree import Element, Node
from bretzel.core.tree import TextNode as TextNode


class Breadcrumb(Component):
    """Page-location trail with chevron-separated parents."""

    THEME: ClassVar[dict[str, Any]] = BREADCRUMB_THEME
    THEME_KEY: ClassVar[str] = "breadcrumb"
    DEFAULT_TAG: ClassVar[str] = "nav"
    # Conteneur — c'est le défaut du socle, donc pas redéclaré ici :
    # l'auteur écrit son ``for``, il lui faut un endroit où poser son
    # balisage. ``items=`` reste le raccourci du cas texte, et
    # matérialise les mêmes enfants.
    COLLECTION_OWNER: ClassVar[str | None] = "author"
    # Pure structural display — items are a list rendered at server
    # time, no reactive props expected. Empty tuple = strict mode +
    # nothing bindable.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
    # most apps don't want a colored accent baked in. Inherits the
    # parent text colour via Tailwind's ``text-current``. Callers opt
    # in to a semantic palette (``color="primary"`` etc.) when they
    # want the trail to emphasise.
    color: str = reactive_prop(default="current", emit_attr=False)
    size: str = reactive_prop(default="sm", emit_attr=False)

    def __init__(
        self,
        items: Sequence[Any] = (),
        *,
        separator: str | Component = "chevron-right",
        color: str | None = None,
        size: str | None = None,
        **kwargs: Any,
    ) -> None:
        # Forward direct : le socle drope les kwargs reactive None (garde le défaut).
        super().__init__(color=color, size=size, **kwargs)
        # Le raccourci ``items=`` matérialise les MÊMES enfants que la
        # forme container — un seul chemin de rendu ensuite. (Mixer les
        # deux dans un même fil n'est pas supporté : c'est la règle de
        # ``ToggleGroup``, pour la même raison.)
        if items:
            with self:
                for entry in items:
                    label, href, icon = _normalise_item(entry)
                    BreadcrumbItem(label, href=href, icon=icon)
        # ``adopt_slot`` (no ``icon_shortcut`` — a string separator may be a
        # literal "/" as much as an icon name, ``_render_separator`` decides)
        # detaches a Component NOW, at construction. Detaching in render() is
        # TOO LATE : the parent walks its children in order and has already
        # rendered the auto-registered component as a SIBLING before it
        # reaches this Breadcrumb (the double-render orphan).
        self._separator: str | Component = Component.adopt_slot(separator)

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        _theme, slots, sizes, size_key, _color = theme_context(self, size_default="sm", color_default="current")
        size_class = sizes.get(size_key, sizes.get("sm", ""))

        item_class = " ".join(
            p
            for p in (
                slots.get("item", ""),
                size_class,
            )
            if p
        )
        current_class = " ".join(
            p
            for p in (
                slots.get("current", ""),
                size_class,
            )
            if p
        )
        separator_class = slots.get("separator", "")

        # ``unwrap_transparent`` : un segment ENVELOPPÉ — zone
        # ``@refreshable``, ``ui.fragment`` — n'est pas une instance de
        # ``BreadcrumbItem``, donc il DISPARAISSAIT du fil d'Ariane.
        # Mesuré le 2026-08-23 : 723 → 192 caractères, sans une erreur.
        segments = [
            (child, rewrap)
            for child, rewrap in (unwrap_transparent(c) for c in self._children)
            if isinstance(child, BreadcrumbItem)
        ]
        children: list[Element] = []
        for index, (seg, rewrap) in enumerate(segments):
            if children:
                children.append(
                    _render_separator(self._separator, separator_class)
                )
            children.append(
                rewrap(seg._render_segment(
                    is_last=index == len(segments) - 1,
                    item_class=item_class,
                    current_class=current_class,
                ))
            )

        root_attrs = self.emit_attrs()
        root_attrs["class"] = self.compose_class(
            "root", apply_variant_size_modifiers=False
        )
        root_attrs.setdefault("aria-label", "Breadcrumb")
        return Element(
            tag=self._tag, attrs=root_attrs, children=tuple(children)
        )


class BreadcrumbItem(Component):
    """Un segment du fil : un libellé, une icône optionnelle, un lien.

    ::

        ui.breadcrumb_item("Docs", icon="book", href="/docs")

    Même surface que ses dix pairs — ``ui.tab``, ``ui.sidebar_item``,
    ``ui.navbar_item``, ``ui.step``… — et pour la même raison : c'est
    ``label`` + ``icon`` dans 95 % des cas, et les deux sont des slots,
    donc ils acceptent un Component quand ce n'est pas le cas ::

        ui.breadcrumb_item(ui.badge(label="Tracker"))
        ui.breadcrumb_item(rich, icon=ui.avatar(src=…), href="/x")

    C'est ce qui rend le container inutile : pour un corps vraiment
    arbitraire, on bâtit le composant AVANT et on le passe en ``label``
    (``adopt_slot`` le détache, il ne rend pas deux fois).

    ⚠️ Une première version (2026-08-18) était un CONTENEUR — on y
    entrait en ``with`` pour poser icône et texte à la main. Elle
    n'exposait donc pas ``icon=``, seule des onze items du catalogue à
    ne pas l'avoir, et offrait une deuxième façon de poser un contenu que
    ``label`` accepte déjà (principe 4). Corrigé le jour même.

    Le segment ne sait PAS s'il est le dernier, et c'est voulu : seul
    :meth:`Breadcrumb.render` connaît la longueur du fil. L'auteur n'a
    donc jamais d'``is_last`` à calculer — le ``aria-current="page"``
    arrive tout seul sur le dernier.
    """

    THEME_KEY: ClassVar[str] = "breadcrumb"
    DEFAULT_TAG: ClassVar[str] = "a"
    IS_CONTAINER: ClassVar[bool] = False
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
    NAMED_SLOTS: ClassVar[tuple[str, ...]] = ("icon",)
    #: ``icon="book"`` plutôt que ``icon=ui.icon("book")`` — le raccourci
    #: string que les dix pairs offrent aussi.
    ICON_SLOTS: ClassVar[tuple[str, ...]] = ("icon",)

    def __init__(
        self,
        label: Any = None,
        *,
        icon: Any = None,
        href: str | None = None,
        **kwargs: Any,
    ) -> None:
        # ⚠️ Un ``icon="book"`` n'est PAS confié à ``ICON_SLOTS`` : le
        # socle l'emballerait en ``ui.icon(nom)`` à la taille par défaut
        # (``md`` = 18 px), calibrée pour un corps de page à 16 px. Le
        # libellé d'un fil d'Ariane fait 12 px — l'icône y était donc à
        # 1,50 fois son texte, le pire écart du catalogue (mesuré le
        # 2026-08-18). On garde le NOM et on bâtit l'Icon au rendu, quand
        # la taille du libellé est enfin connue.
        #
        # Un Component passé à la main garde SA taille : l'auteur l'a
        # choisie, ce n'est pas au composant de la corriger.
        self._icon_name = icon if isinstance(icon, str) else None
        super().__init__(icon=None if self._icon_name else icon, **kwargs)
        self._label = Component.adopt_slot(label)
        self._href = href

    # ── Rendu interne — appelé par Breadcrumb ─────────────────────────

    def _render_segment(
        self, *, is_last: bool, item_class: str, current_class: str
    ) -> Element:
        """L'enveloppe appartient au composant, le contenu à l'auteur.

        Le dernier segment est un ``<span aria-current="page">`` et non
        un lien : c'est la page où l'on EST, la rendre cliquable
        annoncerait une navigation qui n'a pas lieu.
        """
        body: list[Node] = []
        icon = self._slot_components.get("icon")
        if icon is None and self._icon_name:
            from bretzel.components.base.sizes import icon_size_for
            from bretzel.components.primitives.icon import Icon

            # La classe du segment porte la taille du libellé ; l'icône
            # prend le cran juste au-dessus. Repli ``sm`` quand le
            # segment est rendu hors d'un fil (aucune classe reçue).
            size = icon_size_for(current_class if is_last else item_class)
            icon = Icon(self._icon_name, size=size or "sm")
        if icon is not None:
            body.append(Component.render_detached(icon))
        label_node = self.emit_text_slot(self._label)
        if label_node is not None:
            body.append(label_node)

        if is_last:
            return Element(
                tag="span",
                attrs={"class": current_class, "aria-current": "page"},
                children=tuple(body),
            )
        attrs: dict[str, Any] = {"class": item_class}
        if self._href:
            attrs["href"] = str(self._href)
        return Element(
            tag="a" if self._href else "span",
            attrs=attrs,
            children=tuple(body),
        )

    def render(self) -> Element:
        """Hors d'un ``Breadcrumb``, un segment rend son contenu SANS les
        classes du parent, plutôt que de lever : c'est le contrat de ses
        pairs (``Tab``, ``Step``, ``TreeNode`` rendent vide hors de leur
        parent), et lever au rendu casserait une page pour une faute de
        composition qu'aucun test unitaire ne voit."""
        return self._render_segment(
            is_last=False, item_class="", current_class=""
        )


# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────


def _normalise_item(item: Any) -> tuple[Any, str | None, Any]:
    """Coerce a breadcrumb entry into ``(label, href, icon)``.

    Accepts dicts (``{"label", "href", "icon"}``), tuples
    (``(label, href)`` ou ``(label,)``), ou une string nue (libellé
    seul, sans lien).

    ``icon`` n'existe que sur la forme dict : c'est ce qui permet au
    raccourci ``items=`` d'exprimer TOUT ce que les enfants expriment.
    Sans lui, les deux niveaux de l'API divergeraient dès qu'on veut une
    icône — et ``test_items_shortcut_materialises_the_same_children``
    n'aurait plus rien à comparer.
    """
    if isinstance(item, dict):
        return item.get("label", ""), item.get("href"), item.get("icon")
    if isinstance(item, tuple):
        if len(item) >= 2:
            return item[0], item[1], None
        if len(item) == 1:
            return item[0], None, None
    if isinstance(item, str):
        return item, None, None
    raise TypeError(
        f"Unsupported breadcrumb item shape : {type(item).__name__}"
    )


def _render_separator(
    separator: str | Component, separator_class: str
) -> Element:
    """Render a single separator node between two items.

    Strings shorter than 3 chars (``"/"``, ``"›"``, ``">"``) are
    treated as literal text ; longer strings are assumed to be
    Iconify names and wrapped in an :class:`Icon`. Caller can also
    pass a pre-built :class:`Component` for full control.
    """
    if isinstance(separator, Component):
        Component._detach_from_parent(separator)
        node = separator.render()
        if isinstance(node, Element):
            return Component.with_slot_class(
                node, separator_class, **{"aria-hidden": "true"}
            )
        return Element(
            tag="span",
            attrs={"class": separator_class, "aria-hidden": "true"},
            children=(node,),
        )

    text = str(separator)
    if len(text) <= 2:
        return Element(
            tag="span",
            attrs={"class": separator_class, "aria-hidden": "true"},
            children=(TextNode(text),),
        )

    # Iconify name — wrap in an Icon, render, stamp the slot class.
    icon = Icon(text, size="xs")
    Component._detach_from_parent(icon)
    rendered = icon.render()
    existing = rendered.attrs.get("class", "")
    return Element(
        tag=rendered.tag,
        attrs={
            **rendered.attrs,
            "class": (
                f"{separator_class} {existing}".strip()
                if existing
                else separator_class
            ),
            "aria-hidden": "true",
        },
        children=rendered.children,
    )


__all__ = ["Breadcrumb"]


