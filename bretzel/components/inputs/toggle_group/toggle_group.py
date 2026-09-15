"""``ToggleGroup`` + ``ToggleButton`` — multi-button selector cluster.

A joined-button bar (filters, formatting toolbar, multi-select chip
row). Items share edges ; the selected state is a coloured bg fill
via ``data-selected="true"``.

- ``multiple=False`` (default) — value is a scalar str.
- ``multiple=True`` — value is a ``list[str]``.

*(``multiple=`` — the same word as Select / Combobox / FileUpload —
rather than shadcn's ``type="single"|"multiple"``, so the API stays
one-of-a-kind across the framework.)*

Composition pattern : children :class:`ToggleButton` instances live
inside a ``with ToggleGroup(...)`` block. The group holds the bound
``value`` and the visual configuration ; each toggle reads them at
render time and emits a ``<button data-selected="…">`` whose bz-data
expression flips an element in or out of the selection.

Shortcut : pass ``options=[(value, label), ...]`` to the constructor
to build the items in one line — the group materialises the matching
ToggleButtons internally. Mix-and-match with the container API is
**not** supported (one or the other per group).

Imperative API mirrors :class:`Combobox` :

- ``.set(value)`` — replace selection (scalar for single, list for
  multi).
- ``.clear()`` — empty selection (``""`` single, ``[]`` multi).
- ``.focus()`` / ``.blur()`` — target the first focusable item.
- ``.select_all()`` / ``.deselect_all()`` — multi only ; pick every
  ToggleButton in the group / drop every pick.

No per-item ``.add(v)`` / ``.remove(v)`` / ``.toggle(v)`` — the click
handlers already do that UI-side. Server-side mutations use
``.set(new_list)`` (or write through the bound state field directly).

La clé de scope s'appelle ``value``, comme pour les autres contrôles. Elle
peut cohabiter avec l'attribut HTML ``value`` des boutons : l'élément est
exposé sous ``$el`` et n'entre pas dans la chaîne du scope. Ce contrat est
gardé par ``tests/runtime_js/test_a_scope_key_survives_a_child_of_the_same_name.py``.
"""

from __future__ import annotations

import json as _json
from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base._wiring import (
    SERVER_ACTION_ATTRS,
    bool_attr,
    hidden_carrier_attrs,
    reject_sealed,
    server_sync_marker,
    theme_context,
    trigger_event,
    unwrap_transparent,
)
from bretzel.components.base.component import finish_render
from bretzel.components.inputs.toggle_group.theme import TOGGLE_GROUP_THEME
from bretzel.components.primitives.icon import Icon
from bretzel.core.tree import Element

# Server-action attrs relocated from the wrapper onto the hidden input
# (the element that actually fires ``change``). Single source :
# ``base/_wiring.SERVER_ACTION_ATTRS``.
_SERVER_ACTION_ATTRS = SERVER_ACTION_ATTRS


def _pop_server_action(root_attrs: dict[str, Any]) -> dict[str, Any] | None:
    """Pop the ``change``-triggered ``hx-*`` server-action bundle off
    ``root_attrs`` for re-stamping on the hidden input.

    Returns the relocated attrs, or ``None`` when no server handler is
    wired. ToggleGroup also exposes ``focus`` / ``blur`` events, but
    those stay on the root (the root carries no focusable element to
    relocate them to — they're client-string only in practice) ; only
    the ``change`` server action moves to the hidden form carrier.
    """
    # L'EVENT, pas la chaîne : avec un ``debounce=`` le trigger vaut
    # ``"change delay:300ms"``, la comparaison échouait, et le bundle
    # restait sur la racine — un ``<div>`` qui ne fire jamais
    # ``change``. Handler mort, sans un mot.
    if trigger_event(root_attrs) != "change":
        return None
    return {
        key: root_attrs.pop(key)
        for key in _SERVER_ACTION_ATTRS
        if key in root_attrs
    }


class ToggleGroup(Component):
    """Cluster of :class:`ToggleButton` items — single or multi-select."""

    THEME: ClassVar[dict[str, Any]] = TOGGLE_GROUP_THEME
    THEME_KEY: ClassVar[str] = "toggle_group"
    #: L'auteur possède la boucle : il ouvre un ``with`` et pose ses
    #: ``ToggleButton``. ``options=`` est le raccourci du cas simple et
    #: matérialise les mêmes enfants — c'est le patron à deux niveaux que
    #: ``Breadcrumb`` reprend. Cf. ``Component.COLLECTION_OWNER``.
    COLLECTION_OWNER: ClassVar[str | None] = "author"
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("value", "disabled")
    IMPERATIVE: ClassVar[tuple[str, ...]] = ("set", "clear", "focus", "blur", "select_all", "deselect_all")
    EVENTS: ClassVar[tuple[str, ...]] = ("change", "focus", "blur")

    value: Any = reactive_prop(default=None, emit_attr=False, writes=True, names_field=True)
    multiple: bool = reactive_prop(default=False, emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)
    disabled: bool = reactive_prop(default=False, emit_attr=False)
    name: str | None = reactive_prop(default=None, emit_attr=False)

    def __init__(
        self,
        *,
        value: Any = None,
        options: list[tuple[str, str]] | None = None,
        multiple: bool | None = None,
        color: str | None = None,
        size: str | None = None,
        disabled: bool | None = None,
        name: str | None = None,
        on_change: Callable[..., Any] | str | None = None,
        on_focus: Callable[..., Any] | str | None = None,
        on_blur: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Garde : sans elle, un ancien ``type="multiple"`` filerait dans
        # **kwargs → attribut HTML mort sur le <div> → groupe
        # silencieusement single.
        if "type" in kwargs:
            raise TypeError(
                "ToggleGroup(type='single'|'multiple') a été remplacé "
                "par multiple=True|False — même API que Select / "
                "Combobox / FileUpload."
            )
        # Forward direct : le socle drope les kwargs reactive None (garde le defaut).
        super().__init__(
            value=value,
            multiple=multiple,
            color=color,
            size=size,
            disabled=disabled,
            name=name,
            on_change=on_change,
            on_focus=on_focus,
            on_blur=on_blur,
            **kwargs,
        )
        # ``options=`` shortcut materialises ToggleButton children at
        # construction time (still inside the ``with self:`` scope,
        # so they auto-attach as our children). Reject 3-tuples or
        # other shapes — surface the misuse explicitly.
        self._shortcut_options: list[tuple[str, str]] = []
        if options is not None:
            for i, item in enumerate(options):
                if not (isinstance(item, tuple) and len(item) == 2):
                    raise TypeError(
                        f"ToggleGroup options[{i}] must be a "
                        f"(value, label) 2-tuple — got {item!r}. "
                        f"For icons or richer items, use the "
                        f"container API : ``with ui.toggle_group(): "
                        f"ui.toggle_button(value, label, icon=...)``."
                    )
                self._shortcut_options.append(item)
            # Build the items now. They register themselves on our
            # parent_stack via Component.__init__ auto-attach.
            with self:
                for value_str, label_str in self._shortcut_options:
                    ToggleButton(value_str, label_str)

    # ── Imperative write-only API ─────────────────────────────────────

    def set(self, value: Any) -> str:
        """Write the picked value. Single → scalar str ; multi → list."""
        return self._value_command(value)

    def clear(self) -> str:
        """Empty the selection. Single → ``""`` ; multi → ``[]``."""
        is_multi = bool(self._reactive_values.get("multiple"))
        return self.set([] if is_multi else "")

    def focus(self) -> str:
        return (
            f"document.getElementById('{self.id}')"
            ".querySelector('button:not([disabled])')?.focus()"
        )

    def blur(self) -> str:
        return (
            f"document.activeElement?.closest("
            f"'#{self.id}')?.querySelector("
            f"'button:focus')?.blur()"
        )

    def select_all(self) -> str:
        """Pick every ToggleButton in the group. Multi-mode only."""
        if not self._reactive_values.get("multiple"):
            raise RuntimeError(
                "ToggleGroup.select_all() is multi-only — "
                "set multiple=True on the group first."
            )
        return self._dispatch_command("bz-select-all")

    def deselect_all(self) -> str:
        """Drop every pick. Multi-mode only (single uses .clear())."""
        if not self._reactive_values.get("multiple"):
            raise RuntimeError(
                "ToggleGroup.deselect_all() is multi-only — "
                "use .clear() for single-mode."
            )
        return self._dispatch_command("bz-deselect-all")


    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        _theme, slots, sizes, size_key, _color = theme_context(self)

        size_cfg = sizes.get(size_key, sizes.get("md", {}))
        is_multi = bool(self._reactive_values.get("multiple"))

        def _resolve(template: str) -> str:
            return template

        # ── Resolve value binding ──────────────────────────────────────
        # Two streams from the user-passed ``value`` :
        # - ``binding_path`` : where the runtime reads/writes when a binding
        #   was provided (``$bz.state.X.Y.field``).
        # - ``initial_value`` : the SSR snapshot rendered into the
        #   ``value`` field of the ``bz-data`` scope + the hidden input's static
        #   ``value=`` + the buttons' static ``data-selected=``.
        value_binding = self._binding_metadata.get("value")
        binding_path: str | None = (
            self.path_of(value_binding) if value_binding is not None else None
        )

        raw_initial = self._reactive_values.get("value")
        if is_multi:
            initial_value: Any = list(raw_initial) if raw_initial else []
        else:
            initial_value = str(raw_initial) if raw_initial is not None else ""

        # Server-backed (``value=state.field`` carries a ``field_name``)
        # vs local literal. A server-backed group must RE-ADOPT its value
        # from the server on a @refreshable swap — ``scope.absorb`` keeps
        # the existing ``value`` signal across the morph (preserving a
        # user's client click), so without an opt-in the new server value
        # never lands. Same ``_serverSync`` boundary the rich inputs use
        # (cf. traps.md § value lié-serveur suit le refresh). A local
        # literal stays client-owned (no re-adopt). Binding mode needs
        # nothing — the value lives in ``$bz._store``.
        value_server_backed = self._value_server_backed("value")

        # La clé de scope — ``value``, comme la prop, comme partout
        # ailleurs (cf. docstring de module). Avec un binding en jeu,
        # toutes les expressions tapent le chemin du magasin à la place.
        (scope_key,) = self._scope_keys("value")
        picked_expr = binding_path if binding_path is not None else scope_key

        # ── bz-data ────────────────────────────────────────────────────
        # Local ``bz-data`` state ; carries the live value when no binding
        # is in play. With a binding the path is the source of truth
        # so we don't duplicate it locally (would race the framework's
        # delta apply).
        if binding_path is None:
            # La clé vient de ``_scope_keys``, plus d'un littéral
            # recopié ici : elle vivait à TROIS endroits (la variable
            # locale, la déclaration, le marker) et un rename devait
            # toucher les trois (audit F84). C'est la divergence de
            # nommage (value/picked/active/sel) qui a causé 5 des 8
            # oublis de ``_serverSync`` — elle est supprimée depuis le
            # 2026-09-07, la clé vaut le nom de la prop.
            sync = server_sync_marker(
                *self._scope_keys("value"), enabled=value_server_backed)
            bz_data_obj = (
                f"{scope_key}: {_json.dumps(initial_value)}"
                + (f",{sync}" if sync else "")
            )
        else:
            bz_data_obj = ""

        # ── Click + selected expressions ───────────────────────────────
        # Single-mode click : assign picked = "x".
        # Multi-mode  click : flip membership via filter / spread.
        def _click_expr(item_value: str) -> str:
            quoted = _json.dumps(item_value)
            if is_multi:
                return (
                    f"{picked_expr} = {picked_expr}.includes({quoted}) "
                    f"? {picked_expr}.filter(v => v !== {quoted}) "
                    f": [...{picked_expr}, {quoted}]"
                )
            return f"{picked_expr} = {quoted}"

        def _selected_expr(item_value: str) -> str:
            quoted = _json.dumps(item_value)
            if is_multi:
                return f"{picked_expr}.includes({quoted})"
            return f"{picked_expr} === {quoted}"

        def _is_initially_selected(item_value: str) -> bool:
            """SSR initial state — used to stamp ``data-selected=true``
            on the right button at first paint so the active style is
            visible before the runtime boots (same idiom as Tabs)."""
            if is_multi:
                return item_value in (initial_value or [])
            return item_value == initial_value

        # ── Walk children — collect ToggleButton items only ────────────
        buttons: list[Element] = []
        item_values: list[str] = []
        item_class = " ".join(
            p
            for p in (
                _resolve(slots.get("item", "")),
                size_cfg.get("item", ""),
            )
            if p
        )

        # Group-level ``disabled`` resolution — same dual-stream as
        # ``value`` :
        # - ``group_disabled_binding`` carries the live binding when
        #   one was passed (then each button stamps
        #   ``bz-attr:disabled=<path>`` so the runtime flips the HTML
        #   attr reactively).
        # - ``group_disabled_static`` is the SSR snapshot — used to
        #   stamp the initial ``disabled`` HTML attr at first paint,
        #   so the locked visual lands before the runtime boots.
        # Per-item ``disabled=True`` on a ToggleButton always wins
        # (static, opt-in for "this option locked").
        group_disabled_binding = self._binding_metadata.get("disabled")
        group_disabled_static = bool(
            self._reactive_values.get("disabled")
        )
        group_disabled_path: str | None = (
            self.path_of(group_disabled_binding)
            if group_disabled_binding is not None else None
        )

        for raw in self._children:
            # ``unwrap_transparent`` : un bouton ENVELOPPÉ — zone
            # ``@refreshable``, ``ui.fragment`` — n'est pas une instance
            # de ``ToggleButton``, donc il tombait dans la branche
            # « enfant étranger » et son ``render()`` nu LEVAIT
            # (« only valid inside a ToggleGroup »). Le seul des cinq
            # conteneurs qui trient à être bruyant ; les autres se
            # dégradaient en silence.
            child, rewrap = unwrap_transparent(raw)
            if isinstance(child, ToggleButton):
                buttons.append(rewrap(
                    child._render_button(
                        item_class=item_class,
                        click_expr=_click_expr(child._option_value),
                        selected_expr=_selected_expr(child._option_value),
                        initially_selected=_is_initially_selected(
                            child._option_value
                        ),
                        group_disabled=group_disabled_static,
                        group_disabled_path=group_disabled_path,
                    )
                ))
                item_values.append(child._option_value)
            # Foreign children (rare — text dividers, etc.) flow
            # untouched.
            else:
                rendered = self._render_one(raw)
                if isinstance(rendered, Element):
                    buttons.append(rendered)

        # ── Assemble bz-data ────────────────────────────────────────────
        bz_data: str
        if bz_data_obj:
            bz_data = "{ " + bz_data_obj + " }"
        else:
            bz_data = "{}"

        # ── Hidden input ───────────────────────────────────────────────
        # Form integration — the dispatcher walks up to the nearest
        # <form> and submits the input's value. In multi-mode we
        # JSON.stringify the array so the server-side handler gets
        # a parseable string. Single-mode ships the raw string.
        root_attrs = self.emit_attrs()
        relocated_change = root_attrs.pop("bz-on:change", None)
        relocated_server = _pop_server_action(root_attrs)

        # ── focus / blur : re-clés en focusin / focusout ────────────────
        # ``focus`` / ``blur`` ne BULLENT PAS : posé sur la root ``<div>``
        # (non focusable), un listener ne se déclencherait jamais — les
        # éléments focusables sont les ``<button>`` ENFANTS. ``focusin`` /
        # ``focusout`` sont les jumeaux BULLANTS : posés sur le conteneur,
        # ils se déclenchent quand n'importe quel enfant prend / perd le
        # focus. Même relais que ``<bz-calendar>`` (07_calendar.js).
        # Préféré à la relocation sur le premier ``<button>`` (idiome
        # Select) : « le premier » serait arbitraire, le focus peut entrer
        # par n'importe lequel.
        for src, dst in (("focus", "focusin"), ("blur", "focusout")):
            attr = f"bz-on:{src}"
            if attr in root_attrs:
                root_attrs[f"bz-on:{dst}"] = root_attrs.pop(attr)
        if root_attrs.get("hx-trigger") in ("focus", "blur"):
            root_attrs["hx-trigger"] = (
                "focusin" if root_attrs["hx-trigger"] == "focus" else "focusout"
            )

        name = self._reactive_values.get("name") or self._derive_field_name()

        hidden_node: Element | None = None
        if (
            name
            or relocated_change is not None
            or relocated_server is not None
        ):
            hidden_value_expr = (
                f"JSON.stringify({picked_expr})" if is_multi else picked_expr
            )
            ssr_value: str
            if is_multi:
                ssr_value = _json.dumps(initial_value)
            else:
                ssr_value = (
                    initial_value if isinstance(initial_value, str)
                    else str(initial_value)
                )
            hidden_attrs: dict[str, Any] = {
                # ``dispatch=`` : le SEUL appelant du catalogue dont la
                # valeur postée (``hidden_value_expr``, sérialisée) et la
                # valeur observée (``picked_expr``) ne sont pas la même
                # expression. C'est cette divergence-là qui a fait garder
                # le paramètre plutôt que de câbler le dispatcher en dur.
                **hidden_carrier_attrs(
                    hidden_value_expr, initial=ssr_value, dispatch=picked_expr
                ),
            }
            if name:
                hidden_attrs["name"] = str(name)
            if relocated_change is not None:
                hidden_attrs["bz-on:change"] = relocated_change
            if relocated_server is not None:
                hidden_attrs.update(relocated_server)
            hidden_node = Element(
                tag="input", attrs=hidden_attrs, children=()
            )

        # ── Imperative-API listeners ───────────────────────────────────
        # ``bz-on:bz-set`` / ``bz-on:bz-select-all`` /
        # ``bz-on:bz-deselect-all`` — caught by the wrapper and applied
        # to ``value`` (no-binding case) or to the binding path. When a
        # binding is in play, ``.set(...)`` writes through the binding
        # directly and these listeners never fire ; we still emit them
        # so external callers using the no-binding ``.set()`` path work.
        cmd_listeners: dict[str, Any] = {}
        cmd_listeners["bz-on:bz-set"] = (
            f"{picked_expr} = $event.detail.value"
        )
        if is_multi:
            quoted_items = (
                "[" + ", ".join(_json.dumps(v) for v in item_values) + "]"
            )
            cmd_listeners["bz-on:bz-select-all"] = (
                f"{picked_expr} = [...{quoted_items}]"
            )
            cmd_listeners["bz-on:bz-deselect-all"] = f"{picked_expr} = []"

        # ── Root assembly ──────────────────────────────────────────────
        # ``classes=`` posé par le wrap métaclasse — pas ici (doublon).
        root_class = " ".join(
            p
            for p in (
                _resolve(slots.get("root", "")),
                # La hauteur du palier : elle est sur la root parce que
                # c'est elle qui porte la bordure du cadre (cf. le
                # commentaire de ``TOGGLE_GROUP_THEME["sizes"]``).
                size_cfg.get("root", ""),
            )
            if p
        )
        root_attrs["class"] = root_class
        root_attrs["bz-data"] = bz_data
        root_attrs.setdefault("role", "group")
        for key, val in cmd_listeners.items():
            root_attrs[key] = val

        children: list[Any] = []
        children.extend(buttons)
        if hidden_node is not None:
            children.append(hidden_node)

        return Element(
            tag=self._tag, attrs=root_attrs, children=tuple(children),
        )


class ToggleButton(Component):
    """One item inside a :class:`ToggleGroup`."""

    THEME_KEY: ClassVar[str] = "toggle_button"
    DEFAULT_TAG: ClassVar[str] = "button"
    IS_CONTAINER: ClassVar[bool] = False
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("disabled",)
    option_value: str = reactive_prop(default="", emit_attr=False)
    # Nourrie depuis le ``value`` positionnel de l'option. La passer
    # explicitement est refusé par ``reject_sealed``, appelé en tête
    # de ``__init__`` — il FAUT que ce soit là, avant le
    # ``super().__init__`` : la collision de kwargs est levée par
    # Python au moment de construire l'appel, donc le socle ne la
    # voit jamais.
    #
    # ⚠️ Ce commentaire disait « produit un multiple values » et
    # s'en contentait, jusqu'au 2026-09-04. C'était décrire un
    # message illisible au lieu de le réparer — rien n'aurait
    # rappelé d'y revenir.
    SEALED_PROPS: ClassVar[tuple[str, ...]] = ("option_value",)
    #: Le message du refus. Sans lui, le défaut de ``reject_sealed``
    #: parle d'AXE — vrai pour une pile, faux ici.
    SEALED_REASONS: ClassVar[dict[str, str]] = {
        "option_value": (
            "ToggleButton(option_value=…) : ce prop est alimenté par le "
            "``value`` positionnel de l'option — écrivez "
            "``ui.toggle_button(\"ma-valeur\")``. Le passer en plus produirait "
            "deux valeurs pour le même champ, ce qui est une "
            "ambiguïté, pas un raccourci."
        ),
    }
    disabled: bool = reactive_prop(default=False, emit_attr=False)

    def __init__(
        self,
        value: str,
        label: str | None = None,
        *,
        icon: str | Component | None = None,
        disabled: bool | None = None,
        tooltip: str | None = None,
        **kwargs: Any,
    ) -> None:
        reject_sealed(kwargs, type(self))
        # Forward direct : le socle drope les kwargs reactive None (garde le defaut).
        # ``option_value`` (le ``value`` positionnel de l'item) est toujours
        # transmis — ce n'est pas une garde None.
        super().__init__(
            option_value=value,
            disabled=disabled,
            **kwargs,
        )
        self._option_value = value
        self._label = label
        self._tooltip = tooltip
        # ⚠️ Un ``icon="star"`` garde son NOM ici : sa taille dépend du
        # ``size=`` du GROUPE, qu'un enfant ne connaît pas à sa
        # construction. Elle est dérivée au rendu, où ``item_class``
        # porte enfin la classe de texte du libellé — un cran au-dessus,
        # cf. ``base.sizes.ICON_SIZE_ABOVE``.
        #
        # Une taille littérale ici serait figée quel que soit le
        # ``size=`` du groupe : c'est la dette que
        # ``test_child_component_size_is_not_frozen`` interdit, et elle
        # se voit — ``xs`` veut une icône ``sm``, ``xl`` une ``lg``.
        #
        # Un Component passé à la main garde SA taille : l'auteur l'a
        # choisie.
        self._icon_name = icon if isinstance(icon, str) else None
        if icon is None or self._icon_name:
            self._icon: Component | None = None
        else:
            self._icon = Component.adopt_slot(icon, icon_shortcut=True)

    def render(self) -> Element:
        raise RuntimeError(
            "ToggleButton.render() is only valid inside a "
            "ToggleGroup ``with`` block. Use ``ui.toggle_group(...)`` "
            "and put your ``ui.toggle_button(...)`` items inside it."
        )

    # ── Internal API for ToggleGroup.render() ─────────────────────────

    def _render_button(
        self,
        *,
        item_class: str,
        click_expr: str,
        selected_expr: str,
        initially_selected: bool,
        group_disabled: bool,
        group_disabled_path: str | None = None,
    ) -> Element:
        """Materialise the actual ``<button>``. Called by the parent
        group with composed expressions + the SSR initial-selected
        flag (so the active style paints before the runtime hydrates — same
        idiom as Tabs ``data-selected``).

        ``group_disabled_path`` is the JS expression carrying the
        group's disabled binding (``$bz.state.X.Y.disabled``) when one
        was passed. When set, the button stamps ``bz-attr:disabled``
        so the runtime writes the disabled HTML attribute reactively
        (truthy → empty attr present, falsy → attr removed, exactly the
        boolean-attr semantics ``disabled`` needs). Without the path,
        ``group_disabled`` is the static SSR snapshot used to lock the
        button at first paint only."""
        attrs: dict[str, Any] = {
            "type": "button",
            "class": item_class,
            "bz-on:click": click_expr,
            # ``data-selected`` is the source of truth for the Tailwind
            # variant ``data-[selected=true]:bg-…``. Both static SSR
            # value AND reactive bind so the active style is right at
            # first paint AND tracks live state. The reactive expression
            # yields a ``true`` / ``false`` value ; ``bz-attr`` keeps
            # the data attribute present in both states only because
            # ``data-[selected=false]`` needs the literal string —
            # ``selected_expr`` is an equality / ``.includes`` test that
            # returns a real boolean, so wrap it to a string to dodge
            # the "bz-attr strips the attr on false" trap.
            "data-selected": "true" if initially_selected else "false",
            "bz-attr:data-selected": bool_attr(f"{selected_expr}"),
            # ``aria-pressed`` stays for accessibility — screen readers
            # announce the toggle state. Same expression, stringified
            # for the same reason.
            "bz-attr:aria-pressed": bool_attr(f"{selected_expr}"),
            "value": self._option_value,
        }
        # Disabled — composed from up to FOUR sources : the per-item lock
        # (static ``disabled=True`` OR a per-item ClientBinding) and the
        # group lock (static OR a group binding). The button is disabled if
        # ANY is truthy. Reactive bindings drive ``bz-attr:disabled`` live ;
        # the static snapshots stamp the HTML attr for first paint. Both the
        # per-item and group bindings flow into one OR-expression.
        per_item_binding = self._binding_metadata.get("disabled")
        per_item_path = (
            self.path_of(per_item_binding)
            if per_item_binding is not None else None
        )
        per_item_static = bool(self._reactive_values.get("disabled"))

        def _term(path: str | None, static: bool) -> str | None:
            if path is not None:
                return f"({path})"
            return "true" if static else None

        reactive_terms = [
            t for t in (_term(per_item_path, per_item_static),
                        _term(group_disabled_path, group_disabled))
            if t
        ]
        has_binding = (per_item_path is not None
                       or group_disabled_path is not None)
        if has_binding and reactive_terms:
            attrs["bz-attr:disabled"] = " || ".join(reactive_terms)
        if per_item_static or group_disabled:
            attrs["disabled"] = True

        if self._tooltip:
            attrs["title"] = self._tooltip

        # Icon + label children. ``label is None`` is a valid case —
        # icon-only buttons. Don't emit a stray empty text node.
        children: list[Any] = []
        icon = self._icon
        if icon is None and self._icon_name:
            from bretzel.components.base.sizes import icon_size_for

            icon = Icon(
                self._icon_name, size=icon_size_for(item_class) or "md"
            )
            Component._detach_from_parent(icon)
        if icon is not None:
            children.append(icon.render())
        # ``is not None`` ne suffit PAS : ``emit_text_slot`` renvoie aussi
        # ``None`` pour la chaîne vide, et un ``None`` dans ``children``
        # fait lever le sérialiseur. C'est le nœud émis qu'on teste, pas
        # la valeur d'entrée.
        label_node = self.emit_text_slot(self._label)
        if label_node is not None:
            children.append(label_node)

        # ⚠️ ``finish_render`` et non un ``Element`` rendu tel quel.
        #
        # Ce chemin court-circuite le ``render()`` de l'enfant — donc le
        # wrap métaclasse, donc les trois passes que TOUT nœud de composant
        # doit subir. Mesuré avant ce fix :
        # ``ui.toggle_button(..., classes=…, style=…, slots={"root": …})``
        # perdait **les trois** kwargs universels, en silence, dès qu'il
        # était dans un ``ui.toggle_group`` — alors qu'ils marchent sur les
        # 75 autres composants.
        #
        # Tout parent qui rebâtit un enfant au lieu de l'appeler doit finir
        # par ici. C'est le seul endroit qui décrit ce que « rendre un
        # composant » veut dire.
        return finish_render(
            self,
            Element(
                tag=self.DEFAULT_TAG, attrs=attrs, children=tuple(children),
            ),
        )


__all__ = ["ToggleGroup", "ToggleButton"]
