"""``Button`` — Archetype 3 action component.

A callable ``on_click`` becomes an HMAC-stamped ``hx-post`` action route ;
a string is emitted as a ``bz-on:click`` expression evaluated client-side.

``href=`` turns the button into an **anchor** — même habillage, autre
sémantique. C'est une distinction fonctionnelle, pas décorative : un
``<a>`` s'ouvre au clic-milieu, se copie par « ouvrir dans un nouvel
onglet », et se dit « lien » à un lecteur d'écran. Un appel à l'action
qui NAVIGUE doit donc utiliser ``href=`` plutôt qu'un changement manuel de
balise. :class:`~bretzel.components.layout.card.Card` suit le même contrat.

``loading=True`` swaps the ``icon_left`` slot for a :class:`Spinner`,
suppresses ``icon_right``, and forces the rendered ``<button>`` into the
disabled state (50 % opacity, ``cursor-not-allowed`` via the root slot's
``disabled:`` variant) so the click is blocked while in flight. No separate
``loading`` modifier — that would reintroduce a source-order race against
``disabled:cursor-not-allowed``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.actions._wiring import (
    apply_loading_disabled,
    build_loading_spinner,
    loading_leading_children,
)
from bretzel.components.actions.button.theme import BUTTON_THEME
from bretzel.components.base import Component, reactive_prop
from bretzel.components.primitives.spinner import Spinner
from bretzel.core.tree import Element, Node
from bretzel.state.scopes.client import ClientBinding


class Button(Component):
    """Action button with variant / size / color theming + named slots."""

    THEME: ClassVar[dict[str, Any]] = BUTTON_THEME
    THEME_KEY: ClassVar[str] = "button"
    DEFAULT_TAG: ClassVar[str] = "button"
    IS_CONTAINER: ClassVar[bool] = False
    NAMED_SLOTS: ClassVar[tuple[str, ...]] = ("icon_left", "icon_right")
    ICON_SLOTS: ClassVar[tuple[str, ...]] = ("icon_left", "icon_right")
    EVENTS: ClassVar[tuple[str, ...]] = (
        "click",
        "focus",
        "blur",
        "mouseenter",
        "mouseleave",
    )
    # Reactive surface : props that change during the button's lifecycle
    # (label, disabled, loading). variant / size / color / type / icons are
    # design-time — conditional render covers the rest.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = (
        "label", "disabled", "loading", "href",
    )

    # Cosmetic props (consumed by ``_compose_classes`` only — kept off
    # the DOM via ``emit_attr=False``). ``type`` and ``disabled`` are
    # real HTML attributes so they ride through.
    variant: str = reactive_prop(default="solid", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    loading: bool = reactive_prop(default=False, emit_attr=False)
    type: str = reactive_prop(default="button")
    disabled: bool = reactive_prop(default=False)
    href: str | None = reactive_prop(default=None, never_code=True)

    def __init__(
        self,
        label: str | ClientBinding | None = None,
        *,
        variant: str | None = None,
        size: str | None = None,
        color: str | None = None,
        type: str | None = None,
        href: str | ClientBinding | None = None,
        external: bool = False,
        disabled: Any = None,
        loading: Any = None,
        icon_left: Component | str | None = None,
        icon_right: Component | str | None = None,
        on_click: Callable[..., Any] | str | None = None,
        on_focus: Callable[..., Any] | str | None = None,
        on_blur: Callable[..., Any] | str | None = None,
        on_mouseenter: Callable[..., Any] | str | None = None,
        on_mouseleave: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Forward direct : le socle drope les kwargs reactive ``None`` (garde
        # le défaut du descripteur) ; un slot ``None`` se lit ``.get()``→None.
        super().__init__(
            variant=variant,
            size=size,
            color=color,
            type=type,
            href=href,
            disabled=disabled,
            loading=loading,
            icon_left=icon_left,
            icon_right=icon_right,
            on_click=on_click,
            on_focus=on_focus,
            on_blur=on_blur,
            on_mouseenter=on_mouseenter,
            on_mouseleave=on_mouseleave,
            **kwargs,
        )
        # ``adopt_slot`` detaches a Component passed as label from the parent
        # its own ``__init__`` auto-registered into — else it renders twice
        # (standalone in the parent flow AND inside this Button). Strings /
        # ClientBindings / None flow through unchanged.
        self._label = Component.adopt_slot(label)
        self._external = external

        # ── Un href fait de ce bouton un ANCRE ────────────────────────
        # Le tag bascule ici et pas dans ``render`` : ``self._tag`` est
        # lu par l'introspection et par les gates, et un composant dont
        # la balise ne se connaît qu'au rendu ment à qui l'interroge.
        # Un ``tag=`` explicite gagne — c'est l'échappatoire tier 2, et
        # l'appelant qui l'écrit sait ce qu'il fait.
        if href is not None and "tag" not in kwargs:
            self._tag = "a"
        if href is not None and on_click is not None:
            raise TypeError(
                "ui.button ne prend pas `href=` ET `on_click=` : ce sont "
                "deux métiers (naviguer / agir) sur une même cible, et "
                "rien n'annoncerait lequel s'applique. Choisis — ou pose "
                "deux contrôles."
            )
        if href is not None and type is not None:
            raise TypeError(
                "ui.button(href=…) rend un `<a>`, où `type=` désigne le "
                "type MIME de la cible et non la nature d'un bouton. "
                "Retire `type=`."
            )

        # Build the spinner eagerly here (not in render()) : Spinner's ctor
        # needs a live render context for ID allocation, and render() may run
        # after the context is torn down (notably in unit tests). Spinner's
        # default ``color="current"`` inherits the button's text colour. Build
        # it whenever loading is truthy OR carries a binding — the reactive
        # case needs the DOM node ready even if loading defaults False at SSR,
        # since the mutex emits both branches for the runtime to bz-show.
        self._loading_spinner: Spinner | None = build_loading_spinner(self)

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        attrs = self.emit_attrs()
        self.apply_class_attrs(attrs)

        # ── Ce qui n'a plus de sens une fois la balise changée ────────
        # ``type`` est déclaré avec ``default="button"``, donc il sort
        # de ``emit_attrs`` même quand personne ne l'a demandé. Sur un
        # ``<a>`` il désigne le type MIME de la cible : le laisser
        # produisait `<a type="button">`, du HTML qui ne veut rien dire
        # et que le mode d'emploi `tag="a"` livrait tel quel.
        if self._tag != "button":
            attrs.pop("type", None)

        # Loading forces the rendered ``<button>`` disabled to block double-
        # submits during the async window ; the reactive ``disabled`` prop
        # itself stays untouched so toggling loading off restores it.
        loading_binding = self._binding_metadata.get("loading")
        loading = bool(self._reactive_values.get("loading"))
        if loading:
            attrs["disabled"] = True

        # Reactive ``loading || disabled`` : OR-combine both bindings so the
        # HTML disabled attr stays true while EITHER side is. ``path_of``
        # resolves a ClientBinding or ClientExpression to its JS source.
        if loading_binding is not None:
            path = self.path_of(loading_binding)
            apply_loading_disabled(self, attrs, path)

        icon_left = self._slot_components.get("icon_left")
        icon_right = self._slot_components.get("icon_right")

        children: list[Node] = []

        children.extend(loading_leading_children(
            self,
            loading=loading,
            loading_path=path if loading_binding is not None else None,
            spinner=self._loading_spinner,
            icon=icon_left,
        ))

        label_node = self.emit_text_slot(self._label)
        if label_node is not None:
            children.append(label_node)

        if loading_binding is not None:
            if icon_right is not None:
                children.append(
                    self._cloak_show(
                        icon_right.render(), f"!{path}", initial=not loading
                    )
                )
        elif not loading and icon_right is not None:
            children.append(icon_right.render())

        if self._tag == "a":
            # Externe : nouvel onglet + opener neutralisé. Même écriture
            # que ``ui.link`` — la paire ``rel`` n'est pas cosmétique,
            # elle empêche la page ouverte d'atteindre ``window.opener``.
            if self._external:
                attrs.setdefault("target", "_blank")
                attrs.setdefault("rel", "noopener noreferrer")
            # Désactivé : un ``<a>`` n'a pas d'attribut ``disabled``, et
            # le poser ne bloque RIEN. On retire la destination, on le
            # sort de l'ordre de tabulation et on le dit à voix haute —
            # exactement ce que fait ``ui.link``, dont le thème et
            # celui-ci partagent le sélecteur ``aria-disabled:``.
            if attrs.pop("disabled", None):
                attrs.pop("href", None)
                attrs["aria-disabled"] = "true"
                attrs["tabindex"] = "-1"

        return Element(tag=self._tag, attrs=attrs, children=tuple(children))
