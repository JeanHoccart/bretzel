"""``Accordion`` / ``AccordionItem`` — collapsible content panels.

Usage ::

    with ui.accordion(value=state.expanded):       # single, collapsible
        with ui.accordion_item("general", label="General settings"):
            ui.text("…")
        with ui.accordion_item("security", label="Security",
                               icon="shield"):
            ui.text("…")
        with ui.accordion_item("billing", label="Billing",
                               disabled=True):
            ui.text("…")

    with ui.accordion(multiple=True, value=state.expanded_list):
        with ui.accordion_item("a", label="Item A"):
            ui.text("body A")
        with ui.accordion_item("b", label="Item B"):
            ui.text("body B")

Deux modes, via ``multiple=`` :

- **single** (default) : at most one item open at a time. ``value`` is
  a string (the open item's id, ``""`` when nothing is open).
  ``collapsible=True`` (default) lets the user fully collapse — click
  the open header to close it. ``collapsible=False`` forces always-one-
  open semantics (click-on-self becomes a no-op).
- **multiple** : any subset open. ``value`` is a list of ids.
  ``collapsible`` is ignored (multiple is always free-collapse).

The active state lives client-side in a ``bz-data`` field (literal
mode) or is mirrored to a :class:`ClientBinding` (binding mode).
Headers toggle via local methods that respect the ``multiple`` /
``collapsible`` rules ; each item's body animates open/closed via a
``bz-class`` grid-template-rows swap (``0fr`` ↔ ``1fr``).

Form integration : when ``value`` is a binding, ``AUTONAME_FROM
= "value"`` derives the HTML ``name`` from the field — a hidden
``<input>`` rides the active id (or JSON-serialised list) into form
data, with the server change handler relocated onto it (same idiom as
:class:`Pagination`). A callable ``on_change`` produces ``hx-post`` +
``hx-trigger="change"`` ; a string ``on_change`` produces
``bz-on:change``. Both are relocated off the root ``<div>`` (which has
no ``name`` / ``value``) onto the hidden ``<input>`` so the dispatched
FormData is non-empty (cf. ``traps.md`` § "bz-event:change sur un div").

Imperative API : ``acc.expand(v)`` / ``collapse(v)`` / ``toggle(v)``
+ ``expand_all()`` / ``collapse_all()``. Write-only ; write-through
binding if one is provided, otherwise DOM dispatch caught by the root's
``bz-on:bz-*`` listeners. See ``imperative-api.md``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base._wiring import (
    bool_attr,
    hidden_carrier_attrs,
    server_sync_marker,
    theme_context,
    unwrap_transparent,
)
from bretzel.components.base._wiring import (
    pop_change_handler as _pop_change_handler,
)
from bretzel.components.data.accordion.theme import ACCORDION_THEME
from bretzel.components.primitives.icon import Icon
from bretzel.core.tree import Element, Node
from bretzel.core.tree import TextNode as TextNode

# ───────────────────────────────────────────────────────────────────────────
# bz-data builder — two modes (local field vs binding-getter)
# ───────────────────────────────────────────────────────────────────────────


def _build_bz_data(
    *,
    scope_key: str,
    multiple: bool,
    collapsible: bool,
    has_local_value: bool,
    initial_value: Any,
    binding_path: str | None,
    all_ids: list[str],
    server_synced: bool,
) -> str:
    """Le ``bz-data`` de l'instance : **des données, pas du code**.

    Les méthodes (``isOpen`` / ``toggle`` / ``expand`` / ``collapse`` /
    ``expandAll`` / ``collapseAll``) vivent une seule fois dans
    ``$bz.accordion.single`` ou ``$bz.accordion.multi``
    (``bretzel/runtime/_src/16_accordion.js``).

    Avant cette bascule, ce builder sérialisait les six corps dans CHAQUE
    instance — 622 octets — et y cuisait la configuration :
    ``if (true)`` pour ``collapsible``, la liste des ids en dur dans
    ``expandAll``. Deux accordéons de configurations différentes
    produisaient donc deux CODES différents, pas deux états.

    Deux variantes de scope plutôt qu'une paramétrée : single porte une
    CHAÎNE, multi un TABLEAU — les fusionner obligerait chaque méthode à
    re-tester le type à l'exécution. Même raison que
    ``$bz.select.single`` / ``$bz.select.multi``.

    ``_read`` / ``_write`` couvrent les deux modes de valeur (champ local
    ``value`` ou cellule du store) avec les mêmes méthodes. Pas de
    ``get expanded()`` : ``scope.absorb`` invoque chaque clé à
    l'enregistrement et figerait le getter (cf. traps.md).
    """
    # Sérialisation JS de l'état et de la config — inchangée, seul leur
    # DESTINATAIRE change : elles partent en données au lieu d'être cuites
    # dans des corps de méthode.
    initial_js = (
        json.dumps(
            list(initial_value)
            if isinstance(initial_value, (list, tuple, set))
            else []
        )
        if multiple
        else json.dumps(str(initial_value or ""))
    )
    all_ids_js = json.dumps(all_ids)
    collapsible_js = "true" if collapsible else "false"
    is_multiple = multiple

    # ``_allIds`` / ``_collapsible`` sont de la CONFIG : la liste des
    # panneaux et le mode viennent du serveur, le client ne les écrit
    # jamais → re-semés sans condition. ``absorb`` ne réécrit jamais un
    # signal existant, donc sans ça un accordéon qui gagne ou perd un
    # panneau gardait son ancienne liste d'ids (``expand_all`` en oubliait
    # un). Même racine que ``_total`` de Pagination.
    config_sync = ["_allIds"] if is_multiple else ["_allIds", "_collapsible"]

    if has_local_value:
        # La VALEUR reste gatée : sans propriété serveur, le morph d'un
        # @refreshable voisin effacerait l'expand/collapse du client.
        keys = [scope_key, *config_sync] if server_synced else config_sync
        sync = server_sync_marker(*keys, enabled=True)
        state = f"{scope_key}: {initial_js},{sync} "
        read_write = (
            f"_read() {{ return this.{scope_key}; }},"
            f"_write(v) {{ this.{scope_key} = v; }},"
        )
    else:
        assert binding_path is not None
        state = f"{server_sync_marker(*config_sync, enabled=True).lstrip()} "
        read_write = (
            f"_read() {{ return {binding_path}; }},"
            f"_write(v) {{ {binding_path} = v; }},"
        )

    variant = "multi" if is_multiple else "single"
    config = f"_allIds: {all_ids_js},"
    if not is_multiple:
        # ``collapsible`` ne concerne que le mode single : en multi, tout
        # panneau se referme toujours.
        config += f"_collapsible: {collapsible_js},"

    return (
        "{...$bz.accordion." + variant + ","
        + state
        + read_write
        + config.rstrip(",")
        + "}"
    )


# The change dispatcher (``change_emit_effect``) runs as a ``bz-effect``
# on the hidden input : it bootstraps quietly (no phantom change on the
# SSR→hydration handoff) then dispatches a bubbling ``change`` on a real
# mutation, so the relocated ``hx-post`` / ``bz-on:change`` listener
# fires with populated FormData.


# ───────────────────────────────────────────────────────────────────────────
# Accordion — root container
# ───────────────────────────────────────────────────────────────────────────


class Accordion(Component):
    """Stack of collapsible :class:`AccordionItem` panels."""

    THEME: ClassVar[dict[str, Any]] = ACCORDION_THEME
    THEME_KEY: ClassVar[str] = "accordion"
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("value",)
    IMPERATIVE: ClassVar[tuple[str, ...]] = ("expand", "collapse", "toggle", "expand_all", "collapse_all")
    EVENTS: ClassVar[tuple[str, ...]] = ("change",)

    value: Any = reactive_prop(default="", emit_attr=False, writes=True, names_field=True)
    # ``multiple=`` (not ``type="single"|"multiple"``) — unified with
    # Select / Combobox / FileUpload / ToggleGroup.
    multiple: bool = reactive_prop(default=False, emit_attr=False)
    collapsible: bool = reactive_prop(default=True, emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)

    def __init__(
        self,
        *,
        value: Any = None,
        multiple: bool | None = None,
        collapsible: bool | None = None,
        size: str | None = None,
        color: str | None = None,
        on_change: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Garde : sans elle un ancien ``type="multiple"`` filerait dans
        # **kwargs → attribut HTML mort → accordion silencieusement single.
        if "type" in kwargs:
            raise TypeError(
                "Accordion(type='single'|'multiple') a été remplacé "
                "par multiple=True|False — même API que Select / "
                "Combobox / FileUpload / ToggleGroup."
            )
        # Forward direct : le socle drope les kwargs reactive None (garde le defaut).
        super().__init__(
            value=value,
            multiple=multiple,
            collapsible=collapsible,
            size=size,
            color=color,
            on_change=on_change,
            **kwargs,
        )
        # ── Imperative write-only API ───────────────────────────────
        # Same non-data descriptor trick as Dialog/Drawer/etc. — install
        # the methods as instance attrs so they don't shadow the
        # reactive_prop descriptors at class level. Cf. imperative-api.md.
        self.expand = self._imperative_expand
        self.collapse = self._imperative_collapse
        self.toggle = self._imperative_toggle
        self.expand_all = self._imperative_expand_all
        self.collapse_all = self._imperative_collapse_all

    # ── Imperative API impls ────────────────────────────────────────────

    def _imperative_expand(self, item_value: str) -> str:
        """Open ``item_value``. Write-through binding if any, else DOM
        dispatch — root listener flips the local ``bz-data`` field."""
        binding = self._binding_metadata.get("value")
        is_multiple = bool(self._reactive_values.get("multiple"))
        if binding is not None and not is_multiple:
            # Single + binding : write the new value directly.
            return binding.set(str(item_value))
        # Multiple OR no-binding-single → always go through the DOM
        # dispatch so the bz-data's expand() method does the right
        # list-mutation / write-back-to-binding logic.
        return self._dispatch_command("bz-expand", value=str(item_value))

    def _imperative_collapse(self, item_value: str) -> str:
        # Toujours le dispatcher, binding ou pas : savoir si l'item à
        # replier EST celui qui est ouvert ne se décide pas au serveur,
        # seul le runtime connaît la valeur vivante. (Il y avait ici un
        # branchement binding/multiple/collapsible dont les deux bras
        # retournaient la MÊME expression — audit F33.)
        return self._dispatch_command("bz-collapse", value=str(item_value))

    def _imperative_toggle(self, item_value: str) -> str:
        return self._dispatch_command(
            "bz-toggle", value=str(item_value)
        )

    def _imperative_expand_all(self) -> str:
        return self._dispatch_command("bz-expand-all")

    def _imperative_collapse_all(self) -> str:
        return self._dispatch_command("bz-collapse-all")


    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        _theme, slots, sizes, size_key, _color = theme_context(self)

        is_multiple = bool(self._reactive_values.get("multiple"))
        collapsible = bool(self._reactive_values.get("collapsible", True))

        size_cfg = sizes.get(size_key, sizes.get("md", {}))

        def _resolve(template: str) -> str:
            return template

        # ── Resolve binding for ``value`` ────────────────────────────
        value_binding = self._binding_metadata.get("value")
        raw_initial = self._reactive_values.get("value")
        if is_multiple:
            if raw_initial is None or raw_initial == "":
                initial_value: Any = []
            elif isinstance(raw_initial, (list, tuple, set)):
                initial_value = [str(v) for v in raw_initial]
            else:
                initial_value = [str(raw_initial)]
        else:
            initial_value = str(raw_initial or "")

        # Server-backed values RE-ADOPT on a @refreshable swap via
        # ``_serverSync`` (else absorb keeps the stale client signal) ;
        # local literals don't. Same gate as ToggleGroup.
        value_server_backed = self._value_server_backed("value")

        binding_path = (
            self.path_of(value_binding)
            if value_binding is not None
            else None
        )
        # ``bz-attr:value`` on the hidden input — local field when no
        # binding, full state path otherwise.
        (scope_key,) = self._scope_keys("value")
        hidden_value_expr = binding_path or scope_key

        # ── Walk children, collect AccordionItem ids ─────────────────
        # Les couples ``(item, rehabillage)`` : un item ENVELOPPÉ — zone
        # ``@refreshable``, ``ui.fragment`` — n'est pas une instance
        # d'``AccordionItem``, donc le tri par type le ratait. Il tombait
        # alors dans la branche « enfant étranger », dont le rendu nu est
        # un ``<div>`` avec le CORPS et rien d'autre : plus d'en-tête,
        # plus de libellé, plus de bascule. Mesuré le 2026-08-23 : deux
        # boutons d'en-tête → un, et le libellé disparu.
        item_children: list[tuple[AccordionItem, Any]] = []
        passthrough: list[Element] = []
        for raw in self._children:
            child, rewrap = unwrap_transparent(raw)
            if isinstance(child, AccordionItem):
                item_children.append((child, rewrap))
            else:
                rendered = self._render_one(raw)
                if rendered is not None and isinstance(rendered, Element):
                    passthrough.append(rendered)

        all_ids = [
            str(item._reactive_values.get("value") or "")
            for item, _ in item_children
        ]

        bz_data = _build_bz_data(
            scope_key=scope_key,
            multiple=is_multiple,
            collapsible=collapsible,
            has_local_value=value_binding is None,
            initial_value=initial_value,
            binding_path=binding_path,
            all_ids=all_ids,
            server_synced=value_server_backed,
        )

        # ── Build item nodes ─────────────────────────────────────────
        # Compose per-item class once — the internal divider (from the
        # ``item`` slot). Header / body classes are composed per item to
        # fold in the size overrides.
        item_class = slots.get("item", "")
        header_base = _resolve(slots.get("header", ""))
        header_size = size_cfg.get("header", "")
        header_class = " ".join(p for p in (
            header_base, header_size,
        ) if p)
        label_class = slots.get("label", "")
        icon_size = size_cfg.get("icon_size", "sm")
        chevron_size = size_cfg.get("chevron_size", "sm")
        chevron_class = slots.get("chevron", "")
        body_class = slots.get("body", "")
        body_clip_class = slots.get("body_clip", "")
        body_inner_class = " ".join(p for p in (
            slots.get("body_inner", ""), size_cfg.get("body_inner", ""),
        ) if p)

        def _is_initially_open(item_value: str) -> bool:
            if is_multiple:
                return item_value in initial_value
            return item_value == initial_value

        item_nodes: list[Element] = []
        for item, rewrap in item_children:
            item_nodes.append(
                rewrap(item._render_in_accordion(
                    item_class=item_class,
                    header_class=header_class,
                    label_class=label_class,
                    icon_size=icon_size,
                    chevron_class=chevron_class,
                    chevron_size=chevron_size,
                    body_class=body_class,
                    body_clip_class=body_clip_class,
                    body_inner_class=body_inner_class,
                    initially_open=_is_initially_open(
                        str(item._reactive_values.get("value") or "")
                    ),
                ))
            )

        # ── Hidden input — form integration ──────────────────────────
        # The change handler must ride an element exposing ``name`` +
        # ``value`` so the dispatched FormData is non-empty (the root
        # ``<div>`` has neither — cf. ``traps.md`` § "bz-event:change sur
        # un div"). Pop the handler keys ``emit_attrs`` stamped on the root
        # (callable → ``hx-post`` set ; string → ``bz-on:change``) and
        # carry them onto the hidden input below.
        root_attrs = self.emit_attrs()
        relocated_change = _pop_change_handler(root_attrs)

        name = self._reactive_values.get("name") or self._derive_field_name()

        hidden_node: Element | None = None
        if name or relocated_change:
            # Multi : serialise the array as JSON so it survives one
            # form-data round-trip (server does json.loads on the field).
            if is_multiple:
                hidden_value_initial = json.dumps(
                    [str(v) for v in initial_value]
                )
                value_directive = (
                    f"JSON.stringify({hidden_value_expr} || [])"
                )
            else:
                hidden_value_initial = str(initial_value or "")
                value_directive = hidden_value_expr
            hidden_attrs: dict[str, Any] = {
                **hidden_carrier_attrs(value_directive, initial=hidden_value_initial),
                # Reactive change dispatcher — fires ``change`` on the input
                # (where the relocated handler lives) on a real value mutation.
            }
            if name:
                hidden_attrs["name"] = str(name)
            # Drop the relocated handler keys onto the input.
            hidden_attrs.update(relocated_change)
            hidden_node = Element(
                tag="input", attrs=hidden_attrs, children=()
            )

        # ── Assemble the root ────────────────────────────────────────
        root_class = slots.get("root", "")
        # ``overflow-hidden`` stays unconditional : anchored panels are
        # ``position: fixed`` at open time and escape the clip natively.
        # The body-clip animation lives one element deeper, untouched.
        root_attrs["class"] = root_class
        root_attrs["bz-data"] = bz_data
        # Imperative-API listeners — catch DOM commands from external
        # triggers (``acc.expand(v)`` etc.) and call the matching
        # local method. ``$event.detail.value`` carries the item id
        # for value-bearing commands ; ``expandAll`` / ``collapseAll``
        # are payload-less.
        root_attrs["bz-on:bz-expand"] = "expand($event.detail.value)"
        root_attrs["bz-on:bz-collapse"] = "collapse($event.detail.value)"
        root_attrs["bz-on:bz-toggle"] = "toggle($event.detail.value)"
        root_attrs["bz-on:bz-expand-all"] = "expandAll()"
        root_attrs["bz-on:bz-collapse-all"] = "collapseAll()"

        children: list[Node] = list(item_nodes)
        children.extend(passthrough)
        if hidden_node is not None:
            children.append(hidden_node)

        return Element(
            tag=self._tag, attrs=root_attrs, children=tuple(children)
        )


# ───────────────────────────────────────────────────────────────────────────
# AccordionItem — header + body, rendered by its parent Accordion
# ───────────────────────────────────────────────────────────────────────────


class AccordionItem(Component):
    """One collapsible row inside an :class:`Accordion`.

    Carries metadata (``value``, ``label``, ``icon``, ``disabled``) +
    a body composed via the ``with`` block. The parent ``Accordion``
    walks its children and calls ``_render_in_accordion`` on each item
    to build the full header + body tree with toggle wiring.

    Standalone ``render()`` falls back to a plain ``<div>`` with the
    body content — no header, no toggle — so a stray ``ui.accordion_item
    (...)`` at page scope doesn't blow up the renderer.
    """

    THEME_KEY: ClassVar[str] = "accordion_item"
    # ``value`` drives expansion ; per-item bindings would mean N
    # bindings instead of one and don't add expressive power.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
    NAMED_SLOTS: ClassVar[tuple[str, ...]] = ("icon",)
    ICON_SLOTS: ClassVar[tuple[str, ...]] = ("icon",)

    value: str = reactive_prop(default="", emit_attr=False)
    label: Any = reactive_prop(default="", emit_attr=False)
    disabled: bool = reactive_prop(default=False, emit_attr=False)

    def __init__(
        self,
        value: str = "",
        *,
        label: Any = None,
        icon: Any = None,
        disabled: bool | None = None,
        **kwargs: Any,
    ) -> None:
        # ``label`` is a ``reactive_prop`` — the base ``Component.__init__``
        # already auto-detaches any Component value landing in a
        # reactive_prop (cf. component.py's generic reactive-props loop),
        # so no manual adopt_slot/detach is needed here.
        # Forward direct : le socle drope les kwargs reactive None (garde le defaut).
        super().__init__(
            value=value,
            label=label,
            disabled=disabled,
            icon=icon,
            **kwargs,
        )

    # ── Internal render — invoked by Accordion ────────────────────────

    def _render_in_accordion(
        self,
        *,
        item_class: str,
        header_class: str,
        label_class: str,
        icon_size: str,
        chevron_class: str,
        chevron_size: str,
        body_class: str,
        body_clip_class: str,
        body_inner_class: str,
        initially_open: bool,
    ) -> Element:
        item_value = str(self._reactive_values.get("value") or "")
        label_value = self._reactive_values.get("label")
        disabled = bool(self._reactive_values.get("disabled"))
        value_js = json.dumps(item_value)

        # Stable id pair for aria-controls / aria-labelledby — the
        # accordion needs them to link the header button to the body
        # region.
        header_id = (
            f"{self.id}_header"
            if self.id
            else f"acc_h_{abs(hash(item_value))}"
        )
        body_id = (
            f"{self.id}_body"
            if self.id
            else f"acc_b_{abs(hash(item_value))}"
        )

        # ── Header — button + label + chevron ────────────────────────
        header_children: list[Node] = []

        # Optional leading icon. Detach from the auto-attach machinery
        # and render inline so it appears before the label inside the
        # button (vs. floating into the accordion's child list).
        icon = self._slot_components.get("icon")
        if isinstance(icon, Component):
            Component._detach_from_parent(icon)
            header_children.append(icon.render())

        # Label — string, Component (already adopted), or ClientBinding
        # passing through the standard emit_text_slot helper.
        label_span_attrs: dict[str, Any] = {"class": label_class}
        # Pas de branche ClientBinding : ``label`` n'est pas bindable et un
        # binding vit dans ``_binding_metadata``, jamais ``_reactive_values``
        # — cf. traps.md § « Lire un binding via _reactive_values + isinstance ».
        if isinstance(label_value, Component):
            label_span: Node = Element(
                tag="span",
                attrs=label_span_attrs,
                children=(label_value.render(),),
            )
        else:
            text = str(label_value) if label_value is not None else ""
            label_span = Element(
                tag="span",
                attrs=label_span_attrs,
                children=(TextNode(text),),
            )
        header_children.append(label_span)

        # Chevron — lucide icon rotated by data-open CSS.
        chevron = Icon(
            "chevron-down",
            size=chevron_size,
            classes=chevron_class,
        )
        Component._detach_from_parent(chevron)
        header_children.append(chevron.render())

        header_attrs: dict[str, Any] = {
            "type": "button",
            "id": header_id,
            "class": header_class,
            "aria-controls": body_id,
            # ``.toString()`` keeps these data/aria attrs as the literal
            # strings ``"true"`` / ``"false"`` so ``data-[open=...]``
            # CSS selectors match and bz-attr never drops the attribute
            # on a falsy boolean (cf. ``traps.md`` data-attr stringify).
            "bz-attr:aria-expanded": bool_attr(f"isOpen({value_js})"),
            "bz-attr:data-open": bool_attr(f"isOpen({value_js})"),
            "bz-on:click": f"toggle({value_js})",
        }
        if initially_open:
            # SSR-render the active state so CSS picks it up before
            # the runtime hydrates. Same idiom as Tabs' ``data-selected``.
            header_attrs["data-open"] = "true"
            header_attrs["aria-expanded"] = "true"
        else:
            header_attrs["aria-expanded"] = "false"
        if disabled:
            header_attrs["disabled"] = True

        header_button = Element(
            tag="button",
            attrs=header_attrs,
            children=tuple(header_children),
        )

        # ── Body — grid-template-rows trick for height animation ────
        # The wrapper is a 1-col grid whose single row track animates
        # between ``0fr`` (collapsed) and ``1fr`` (expanded) ; the inner
        # ``min-h-0 overflow-hidden`` div inherits that height, so the
        # transition adapts to the real content height, not an arbitrary cap.
        #
        # ⚠️ Both row classes must live EXCLUSIVELY in ``bz-class`` : the
        # handler only manages its own dynamic set and never touches the
        # static ``class=`` (02_directives.js), so a row class baked into
        # ``class`` would survive forever and clash with the active one.
        # No FOUC : the runtime keeps each ``bz-data`` subtree hidden until
        # its first scan applies the effects (00_index.js ``bz-ready``).
        # (A ``@refreshable`` morph strips this dynamic class back to the
        # SSR baseline, then the afterSwap rescan re-applies it — the
        # per-BIND managed set in the ``bz-class`` handler makes that
        # re-apply actually happen, cf. traps.md § "bz-class perdue après
        # un morph".)
        body_attrs: dict[str, Any] = {
            "id": body_id,
            "role": "region",
            "aria-labelledby": header_id,
            "class": body_class,
            "bz-class": (
                f"{{ 'grid-rows-[1fr]': isOpen({value_js}), "
                f"'grid-rows-[0fr]': !isOpen({value_js}) }}"
            ),
            "bz-attr:aria-hidden": bool_attr(f"!isOpen({value_js})"),
        }
        if not initially_open:
            body_attrs["aria-hidden"] = "true"

        body_inner = Element(
            tag="div",
            attrs={"class": body_inner_class} if body_inner_class else {},
            children=tuple(self._render_children()),
        )
        # The clipping element must keep ``min-h-0 overflow-hidden`` for
        # the grid-rows animation : without it the children render at full
        # height while the row track shrinks to ``0fr``, breaking the
        # collapse. Anchored overlays escape via ``bz-teleport`` to
        # ``<body>`` instead, so this clip doesn't trap them.
        body_clip = Element(
            tag="div",
            attrs={"class": body_clip_class} if body_clip_class else {},
            children=(body_inner,),
        )
        body = Element(
            tag="div",
            attrs=body_attrs,
            children=(body_clip,),
        )

        # ── Item wrapper ────────────────────────────────────────────
        # The item's ``rounded-box overflow-hidden`` wrapper never clips an
        # anchored panel (those are ``position: fixed`` at open time) ; the
        # body's animation-clip lives one element deeper.
        wrapper_attrs: dict[str, Any] = {"class": item_class}
        return Element(
            tag="div",
            attrs=wrapper_attrs,
            children=(header_button, body),
        )

    # ── Default render — silent fallback outside Accordion ──────────

    def render(self) -> Element:
        # Outside an Accordion the item has no meaningful toggle
        # context — emit a plain div with the body content so the
        # children at least appear. No header, no chevron.
        return Element(
            tag="div",
            attrs={"class": "outline-none"},
            children=tuple(self._render_children()),
        )


__all__ = ["Accordion", "AccordionItem"]
