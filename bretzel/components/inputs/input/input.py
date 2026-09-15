"""``Input`` — text input with prefix/suffix/icon slots.

The render path picks one of two layouts depending on whether the
caller passed a prefix / suffix string :

- **Bare** (``ui.input(name="email")``) : a single ``<input>`` styled
  with the ``input`` slot, optionally with absolute-positioned icons
  overlaid via ``icon_left`` / ``icon_right`` slots.
- **With affixes** (``ui.input(prefix="$", suffix=".com", …)``) : a
  ``<div class="prefix_root">`` wraps a transparent ``<input
  class="input_inner">`` flanked by inline ``<span>`` prefix/suffix.
  The frame and the focus ring move to the wrapper so the affix and
  the input share one visual unit.

Two-way binding via ``bz-model`` when ``value`` is a ClientBinding —
the user's typing flows back into the reactive store live.

"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.inputs._picker_field import icon_button
from bretzel.components.inputs._wiring import (
    add_local_value_scope,
    value_command_listeners,
)
from bretzel.components.inputs.input.theme import INPUT_THEME
from bretzel.components.primitives.icon import Icon
from bretzel.core.tree import Element
from bretzel.core.tree import TextNode as TextNode
from bretzel.render import text

# HTML5 ``<input>`` types that ship a native browser popup (calendar,
# clock, color wheel, file picker). Native UX is inconsistent across
# browsers AND not themable to match the rest of Bretzel — each kind
# has its own dedicated component instead. Block at construction time
# so the dev sees the right component to use, with a clear pointer.
_NATIVE_PICKER_TYPES: dict[str, str] = {
    "date":           "ui.date_picker (coming soon)",
    "time":           "ui.time_picker (coming soon)",
    "datetime-local": "ui.datetime_picker (coming soon)",
    "month":          "ui.month_picker (coming soon)",
    "color":          "ui.color_picker (coming soon)",
    "file":           "ui.file_upload (coming soon)",
    # Native ``type=number`` has too many cross-browser quirks (leading
    # zeros stripped, ``e`` scientific notation, inconsistent clamp/step,
    # FormData returns a string that may not parse). ``ui.number_input``
    # ships steppers, clamp-on-blur, and float precision instead.
    "number":         "ui.number_input",
}


class Input(Component):
    """Text input. ``value`` accepts a ClientBinding for live two-way
    bind ; ``prefix`` / ``suffix`` / ``icon_left`` / ``icon_right``
    decorate the field without changing the underlying ``<input>``.
    ``on_input`` suit chaque édition ; ``on_change`` suit la validation
    du changement par le navigateur (habituellement à la sortie du champ).
    Pour une recherche pendant la frappe, utiliser ``on_input`` avec
    ``debounce``.
    """

    THEME: ClassVar[dict[str, Any]] = INPUT_THEME
    THEME_KEY: ClassVar[str] = "input"
    DEFAULT_TAG: ClassVar[str] = "input"
    IS_CONTAINER: ClassVar[bool] = False
    EVENTS: ClassVar[tuple[str, ...]] = (
        "change", "input", "focus", "blur", "keydown", "keyup",
    )
    # Reactive surface — only props that change during the input's
    # lifecycle (value: bz-model two-way; disabled: form locks;
    # readonly: edit/view). Everything else is design-time config.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = (
        "value", "disabled", "readonly",
    )
    IMPERATIVE: ClassVar[tuple[str, ...]] = ("set", "clear", "focus", "blur")

    type: str = reactive_prop(default="text")
    name: str | None = reactive_prop(default=None)
    placeholder: str | None = reactive_prop(default=None)
    value: Any = reactive_prop(default=None, writes=True, names_field=True)
    disabled: bool = reactive_prop(default=False)
    readonly: bool = reactive_prop(default=False)
    required: bool = reactive_prop(default=False)
    # HTML5 native validation passthrough — emitted as plain attrs.
    min: Any = reactive_prop(default=None)
    max: Any = reactive_prop(default=None)
    step: Any = reactive_prop(default=None)
    pattern: str | None = reactive_prop(default=None)
    minlength: int | None = reactive_prop(default=None)
    maxlength: int | None = reactive_prop(default=None)
    autocomplete: str | None = reactive_prop(default=None)
    # Visual props — consumed by the slot composer, kept off the DOM.
    color: str = reactive_prop(default="primary", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)

    # Whitelist of accepted input types. Native UI types (date / time /
    # color / file / number / ...) are blocked at ``__init__`` so the dev
    # gets pointed to the right Bretzel component (cf. _NATIVE_PICKER_TYPES).
    ALLOWED_TYPES: ClassVar[frozenset[str]] = frozenset({
        "text", "email", "password",
        "tel", "url", "search", "hidden",
    })

    def __init__(
        self,
        *,
        type: str | None = None,
        name: str | None = None,
        placeholder: str | None = None,
        value: Any = None,
        disabled: bool | None = None,
        readonly: bool | None = None,
        required: bool | None = None,
        min: Any = None,
        max: Any = None,
        step: Any = None,
        pattern: str | None = None,
        minlength: int | None = None,
        maxlength: int | None = None,
        autocomplete: str | None = None,
        color: str | None = None,
        size: str | None = None,
        # Decorative slots — strings or Component instances.
        prefix: str | Component | None = None,
        suffix: str | Component | None = None,
        icon_left: str | Component | None = None,
        icon_right: str | Component | None = None,
        clearable: bool = False,
        on_change: Callable[..., Any] | str | None = None,
        on_input: Callable[..., Any] | str | None = None,
        on_focus: Callable[..., Any] | str | None = None,
        on_blur: Callable[..., Any] | str | None = None,
        on_keydown: Callable[..., Any] | str | None = None,
        on_keyup: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Block native-picker types early so the dev sees the right
        # Bretzel component. Only validate literal strings : a binding
        # carries a value we can't statically inspect (``in`` on a
        # binding returns a ClientExpression, not a bool), so reactive
        # ``type=`` is accepted as-is.
        if isinstance(type, str):
            if type in _NATIVE_PICKER_TYPES:
                raise ComponentUsageError(
                    f"Input does not accept type={type!r} — native "
                    f"browser pickers are inconsistent across browsers "
                    f"and don't honour the Bretzel theme. Use "
                    f"{_NATIVE_PICKER_TYPES[type]} instead."
                )
            if type not in self.ALLOWED_TYPES:
                raise ComponentUsageError(
                    f"Input does not accept type={type!r}. Allowed : "
                    f"{sorted(self.ALLOWED_TYPES)!r}."
                )

        # Forward direct : le socle drope les kwargs reactive None (garde le defaut).
        super().__init__(
            type=type, name=name, placeholder=placeholder,
            value=value, disabled=disabled, readonly=readonly,
            required=required, min=min, max=max,
            step=step, pattern=pattern, minlength=minlength,
            maxlength=maxlength, autocomplete=autocomplete,
            color=color, size=size,
            on_change=on_change,
            on_input=on_input,
            on_focus=on_focus,
            on_blur=on_blur,
            on_keydown=on_keydown,
            on_keyup=on_keyup,
            **kwargs,
        )
        # ``adopt_slot`` auto-converts string shortcuts
        # (``icon_left="search"`` → ``Icon("search")``) and detaches
        # Component values from the active parent so they don't ALSO
        # render as siblings. ``prefix`` / ``suffix`` are plain text
        # affixes, so no icon shortcut for them.
        self._prefix = Component.adopt_slot(prefix)
        self._suffix = Component.adopt_slot(suffix)
        self._icon_left = Component.adopt_slot(icon_left, icon_shortcut=True)
        self._icon_right = Component.adopt_slot(icon_right, icon_shortcut=True)
        # Design-time, donc un attribut d'instance et pas un
        # ``reactive_prop`` : rien côté client ne bascule un champ entre
        # effaçable et non-effaçable.
        #
        # Défaut ``False``, à REBOURS des cinq pickers qui l'ont à
        # ``True``. Ce n'est pas une incohérence : la valeur d'un picker
        # est formatée (``2026-08-07``, ``09:30``) et pénible à effacer à
        # la main, alors qu'un champ de texte libre se vide au clavier.
        # Mettre une croix sur CHAQUE input de chaque application serait
        # un changement global pour un gain qui n'existe que sur les
        # champs de recherche.
        self._clearable = bool(clearable)

    # ── Imperative write-only API ─────────────────────────────────────
    #
    # Methods returning client JS for ``on_click=`` (or any ``on_*``).
    # ``.set`` write-throughs the binding if any, else DOM dispatch ;
    # ``.focus`` / ``.blur`` are direct DOM commands. Cf. `imperative-api.md`.

    def set(self, value: Any) -> str:
        return self._value_command(value)

    def clear(self) -> str:
        # ``.clear()`` is sugar for ``.set("")`` — empty string covers
        # the text-input case. NumberInput / Slider override if they
        # need a different reset value (0, min, etc.).
        return self.set("")

    def focus(self) -> str:
        return f"document.getElementById('{self.id}').focus()"

    def blur(self) -> str:
        return f"document.getElementById('{self.id}').blur()"


    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        size_key = self._reactive_values.get("size") or "md"
        size_map = (
            self._resolved_theme().get("sizes", {}).get(size_key) or {}
        )

        has_affix = self._prefix is not None or self._suffix is not None
        has_icon = (
            self._icon_left is not None
            or self._icon_right is not None
            or self._clearable
        )

        if has_affix:
            return self._render_with_affixes(size_map)
        return self._render_simple(size_map, has_icon)

    def _clear_button(self, size_map: dict[str, str]) -> Element:
        """Le ``×`` — visible seulement quand il y a quelque chose à effacer.

        **Sa visibilité est du CSS pur** (``peer-placeholder-shown:hidden``
        dans le slot), pas un ``bz-show``. C'est ce qui permet d'ajouter
        l'affordance sans toucher au scope de valeur : celui-ci vit sur
        l'``<input>`` (cf. ``add_local_value_scope``), où il porte le
        ``bz-id`` stable qui fait survivre le texte tapé à un morph — et
        un frère de l'``<input>`` ne peut de toute façon pas le lire.

        **Le clic passe par les mêmes ÉVÉNEMENTS qu'une frappe humaine.**
        Écrire ``.value = ''`` ne suffit pas : ``bz-model`` s'abonne à
        ``input`` (cf. ``02_directives.js``), donc sans ce dispatch le
        signal garderait l'ancien texte et le réécrirait au prochain
        tick ; et un handler serveur écoute ``change``, que le DOM
        n'émet pas non plus pour une écriture programmée. Les deux
        événements partent donc, dans cet ordre, et tout suit — binding,
        scope local, ou input nu.

        La traversée est locale (``$el.parentElement``) plutôt qu'un
        ``bz-ref`` : une ref s'enregistre dans le scope le plus proche,
        et un input sans scope irait polluer le ``rootScope`` partagé où
        deux champs de la même page s'écraseraient.
        """
        return icon_button(
            icon="x",
            css=" ".join(p for p in (
                self.compose_class(
                    "clear_button", apply_variant_size_modifiers=False,
                ),
            ) if p),
            icon_css=Component.render_detached(
                Icon("x", size=size_map.get("clear_icon_size", "sm")),
            ).attrs.get("class", ""),
            aria_label=text("input.clear"),
            on_click=(
                "$event.stopPropagation(); "
                "const i = $el.parentElement.querySelector('input'); "
                "if (i) { i.value = ''; "
                "i.dispatchEvent(new Event('input', {bubbles: true})); "
                "i.dispatchEvent(new Event('change', {bubbles: true})); "
                "i.focus(); }"
            ),
            disabled=bool(self._reactive_values.get("disabled")),
        )

    # ── Layout : bare or icon-decorated ────────────────────────────────

    def _render_simple(
        self, size_map: dict[str, str], has_icon: bool
    ) -> Element:
        # Compose the input's own classes — frame + ring + size +
        # extra left/right padding when icons overlay.
        input_class = " ".join(
            p
            for p in (
                self.compose_class(
                    "input", apply_variant_size_modifiers=False
                ),
                size_map.get("input", ""),
                size_map.get("icon_pad_left", "")
                if self._icon_left is not None
                else "",
                size_map.get("icon_pad_right", "")
                if (self._icon_right is not None or self._clearable)
                else "",
                # ``peer`` : c'est LUI que le ``×`` interroge via
                # ``peer-placeholder-shown``. Sans le marqueur sur
                # l'input, le sélecteur du bouton ne trouve rien et la
                # croix reste visible sur un champ vide.
                "peer" if self._clearable else "",
            )
            if p
        )

        input_attrs = self.emit_attrs()
        input_attrs["class"] = input_class
        # ``:placeholder-shown`` ne matche QUE si l'attribut existe : sans
        # placeholder, le sélecteur du ``×`` ne trouve jamais rien et la
        # croix resterait affichée sur un champ vide — l'inverse exact de
        # ce qu'elle promet. Une espace suffit et ne peint rien.
        if self._clearable and not input_attrs.get("placeholder"):
            input_attrs["placeholder"] = " "
        self._bind_x_model(input_attrs)
        # Local + interactive : internal ``value`` scope on the <input> so
        # typed text survives a @refreshable morph (same model as the rich
        # inputs). No-op in binding mode or for a handler-less input.
        add_local_value_scope(
            self, input_attrs, prop="value",
            ssr_value=self._reactive_values.get("value"),
        )
        # Imperative-API listeners (``.set(value)`` / ``.clear()``) —
        # cf. ``inputs/_wiring.py``.
        input_attrs.update(value_command_listeners())
        input_el = Element(tag="input", attrs=input_attrs, children=())

        # No icons → just emit the bare input, no wrapper noise.
        if not has_icon:
            return input_el

        # Icons → wrap in ``root`` with absolute-positioned overlays.
        children: list[Any] = []
        if self._icon_left is not None:
            children.append(self._slot_element("icon_left", self._icon_left))
        children.append(input_el)
        if self._icon_right is not None:
            children.append(self._slot_element("icon_right", self._icon_right))
        # APRÈS l'input : ``peer-*`` ne regarde qu'un frère PRÉCÉDENT.
        if self._clearable:
            children.append(self._clear_button(size_map))

        root_class = self.compose_class(
            "root", apply_variant_size_modifiers=False
        )
        return Element(
            tag="div",
            attrs={"class": root_class},
            children=tuple(children),
        )

    # ── Layout : with prefix / suffix ──────────────────────────────────

    def _render_with_affixes(self, size_map: dict[str, str]) -> Element:
        # The frame + ring move to the wrapper ; the input goes
        # transparent (``input_inner`` slot) and sits between the
        # affix spans.
        wrapper_class = self.compose_class(
            "prefix_root", apply_variant_size_modifiers=False
        )
        input_inner_class = " ".join(
            p
            for p in (
                self.compose_class(
                    "input_inner", apply_variant_size_modifiers=False
                ),
                size_map.get("input", ""),
                "peer" if self._clearable else "",
            )
            if p
        )

        input_attrs = self.emit_attrs()
        input_attrs["class"] = input_inner_class
        # ``:placeholder-shown`` ne matche QUE si l'attribut existe : sans
        # placeholder, le sélecteur du ``×`` ne trouve jamais rien et la
        # croix resterait affichée sur un champ vide — l'inverse exact de
        # ce qu'elle promet. Une espace suffit et ne peint rien.
        if self._clearable and not input_attrs.get("placeholder"):
            input_attrs["placeholder"] = " "
        self._bind_x_model(input_attrs)
        # Local + interactive : internal ``value`` scope (cf. _render_simple).
        add_local_value_scope(
            self, input_attrs, prop="value",
            ssr_value=self._reactive_values.get("value"),
        )
        # Imperative-API listeners (``.set(value)`` / ``.clear()``) —
        # cf. ``inputs/_wiring.py``.
        input_attrs.update(value_command_listeners())
        input_el = Element(tag="input", attrs=input_attrs, children=())

        children: list[Any] = []
        if self._prefix is not None:
            children.append(self._slot_element("prefix", self._prefix))
        children.append(input_el)
        if self._suffix is not None:
            children.append(self._slot_element("suffix", self._suffix))
        # APRÈS l'input : ``peer-*`` ne regarde qu'un frère PRÉCÉDENT.
        # Ici le cadre vit sur l'enveloppe (pas sur l'input), donc le
        # ``×`` s'y positionne de la même façon — ``absolute right-3``
        # sur un parent qui n'est pas ``relative`` retomberait sur le
        # premier ancêtre positionné.
        if self._clearable:
            children.append(self._clear_button(size_map))

        return Element(
            tag="div",
            attrs={"class": wrapper_class},
            children=tuple(children),
        )

    # ── helpers ────────────────────────────────────────────────────────

    def _slot_element(self, slot: str, content: Any) -> Element:
        """Build the ``<span>`` (or pre-rendered Component) for a
        decorative slot."""
        slot_class = self.compose_class(
            slot, apply_variant_size_modifiers=False
        )
        if isinstance(content, Component):
            # Component author : render as-is and stamp the slot class
            # on its root attrs.
            node = content.render()
            return Component.with_slot_class(  # type: ignore[return-value]
                node, slot_class
            )
        return Element(
            tag="span",
            attrs={"class": slot_class},
            children=(TextNode(str(content)),),
        )
