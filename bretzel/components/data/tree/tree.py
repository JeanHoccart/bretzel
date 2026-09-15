"""``Tree`` / ``TreeNode`` — a recursive, collapsible hierarchy.

Usage ::

    with ui.tree(value=state.picked, expanded=["src", "ui"],
                 on_change=open_file):
        with ui.tree_node("src", label="src", icon="folder"):
            with ui.tree_node("ui", label="ui", icon="folder"):
                ui.tree_node("button.py", label="button.py", icon="file")
            ui.tree_node("app.py", label="app.py", icon="file")
        ui.tree_node("README", label="README.md", icon="file")

A node that owns child ``tree_node``\\s is a **branch** (chevron,
collapsible) ; a childless one is a **leaf**. Disclosure is entirely
**client-side** — the root carries a ``bz-data`` object with the open
set (``open``) + the selection (``value``) and the methods every row
calls (``isOpen`` / ``toggle`` / ``isSel`` / ``select``). Because a
``bz-data`` scope is inherited by every descendant, a deeply-nested
row's ``toggle('id')`` resolves to the single root scope — no per-node
state, no server round-trip to expand a folder.

The chevron is **two glyphs toggled per node by ``bz-show``** (inline
``display`` keyed to ``isOpen(id)``) — not a CSS class swap, which
would (a) lose to the ``<iconify-icon>`` base ``inline-flex`` and (b)
match any ancestor ``.group`` in a recursive tree. Cf. ``theme.py``.

Selection mirrors the single-mode :class:`Accordion` machinery : the
``value`` prop is the selected node id, bindable (client highlight with
zero server hit when ``value`` is a :class:`ClientBinding`) and
form-integrated (``AUTONAME_FROM = "value"`` → a hidden ``<input>``
rides the selection into FormData ; a callable ``on_change`` relocates
its native ``hx-post`` onto that input via the shared
:func:`pop_change_handler`, fired by a ``change`` the
:func:`change_emit_effect` dispatches when the selection genuinely
mutates). Same idiom, one level of recursion added.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop, reject_component
from bretzel.components.base._wiring import (
    SERVERSYNC_KEY,
    activate_keydown,
    bool_attr,
    hidden_carrier_attrs,
    theme_context,
    unwrap_transparent,
)
from bretzel.components.base._wiring import (
    pop_change_handler as _pop_change_handler,
)
from bretzel.components.data.tree.theme import TREE_THEME
from bretzel.components.primitives.icon import Icon
from bretzel.core.tree import Element, Node
from bretzel.core.tree import TextNode as TextNode

# ───────────────────────────────────────────────────────────────────────────
# Tree — root container
# ───────────────────────────────────────────────────────────────────────────


class Tree(Component):
    """Root of a collapsible hierarchy of :class:`TreeNode`\\s."""

    THEME: ClassVar[dict[str, Any]] = TREE_THEME
    THEME_KEY: ClassVar[str] = "tree"
    DEFAULT_TAG: ClassVar[str] = "ul"
    # client-managed (seeded by ``expanded=``) and intentionally NOT a
    # binding : two bindings would double the plumbing without adding
    # expressive power for the 99% case (apps care which node is picked).
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("value",)
    EVENTS: ClassVar[tuple[str, ...]] = ("change",)

    value: Any = reactive_prop(default="", emit_attr=False, writes=True, names_field=True)
    selectable: bool = reactive_prop(default=True, emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)

    def __init__(
        self,
        *,
        value: Any = None,
        expanded: Sequence[str] | None = None,
        selectable: bool | None = None,
        size: str | None = None,
        color: str | None = None,
        on_change: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Forward direct : le socle drope les kwargs reactive None (garde le defaut).
        super().__init__(
            value=value,
            selectable=selectable,
            size=size,
            color=color,
            on_change=on_change,
            **kwargs,
        )
        # Initially-open branch ids — client-managed after mount, so a
        # plain instance attr (not a reactive_prop / binding).
        self._expanded: list[str] = [str(v) for v in (expanded or ())]

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        _theme, slots, sizes, size_key, _color = theme_context(self)
        selectable = bool(self._reactive_values.get("selectable", True))
        size_cfg = sizes.get(size_key, sizes.get("md", {}))

        def _resolve(template: str) -> str:
            return template

        # ── bz-data — the single shared disclosure (+ selection) scope ─
        # Disclosure methods are always present ; selection methods +
        # the local ``value`` field only when ``selectable`` (no dead code
        # in the scope otherwise). Binding mode reads / writes the state
        # path directly ; local mode keeps a ``value`` field. ``sel_expr``
        # is that read/write target — the two never diverge, so one name.
        value_binding = self._binding_metadata.get("value")
        raw_sel = self._reactive_values.get("value")
        initial_sel = str(raw_sel or "")
        # Server-backed selection RE-ADOPTS from the server on a
        # @refreshable morph via ``_serverSync`` (else absorb keeps the
        # stale ``value`` signal) ; a literal stays client-owned. ``open``
        # (disclosure) is pure client UI, never synced. Same gate as Tabs.
        sel_server_backed = self._value_server_backed("value")
        # La clé de scope vient de ``reactive_prop(scope_keys=)`` — elle
        # était recopiée en littéral à trois endroits (le seed, l'expr,
        # le marker) et un rename devait toucher les trois (audit F47).
        (sel_key,) = self._scope_keys("value")
        sel_expr = f"this.{sel_key}"
        # ── bz-data : des DONNÉES, les méthodes vivent au runtime ──────
        # ``isOpen`` / ``toggle`` / ``isSel`` / ``select`` sortent une
        # seule fois de ``$bz.tree.scope``
        # (``bretzel/runtime/_src/16_accordion.js``). Ce builder les
        # sérialisait dans CHAQUE instance — 293 octets — alors qu'ils sont
        # rigoureusement identiques d'un arbre à l'autre.
        #
        # ``_read``/``_write`` (nœuds dépliés) et ``_readSel``/``_writeSel``
        # (sélection) portent l'indirection : les mêmes méthodes servent le
        # champ local et la cellule du store. Pas de getter — ``absorb``
        # invoque chaque clé une fois et le figerait.
        parts: list[str] = [
            f"open: {json.dumps(self._expanded)}",
            "_read() { return this.open; }",
            "_write(v) { this.open = v; }",
        ]
        if selectable:
            if value_binding is not None:
                sel_expr = self.path_of(value_binding)
            else:
                parts.append(f"{sel_key}: {json.dumps(initial_sel)}")
                if sel_server_backed:
                    parts.append(f"{SERVERSYNC_KEY}: ['{sel_key}']")
            parts.append(f"_readSel() {{ return {sel_expr}; }}")
            parts.append(f"_writeSel(v) {{ {sel_expr} = v; }}")
        bz_data = "{...$bz.tree.scope," + ",".join(parts) + "}"

        # ── Precompute the resolved slot classes + the constant spacer ─
        # The chevron is per-node (its ``bz-show`` keys on THIS node's
        # ``isOpen(id)``) so it is built in the recursion ; only the leaf
        # spacer is truly constant, so build that one Element once and
        # share it. The spacer shares the indicator cell's width so leaf
        # labels line up under branch labels.
        row_class = " ".join(
            p for p in (_resolve(slots.get("row", "")), size_cfg.get("row", "")) if p
        )
        indicator_w = size_cfg.get("indicator", "w-4")
        spacer_class = " ".join(
            p for p in (slots.get("spacer", ""), indicator_w) if p
        )
        spacer_span = Element(
            tag="span",
            attrs={"class": spacer_class, "aria-hidden": "true"},
            children=(),
        )

        ctx = _RenderCtx(
            selectable=selectable,
            row_class=row_class,
            row_disabled=slots.get("row_disabled", ""),
            indicator_class=" ".join(
                p for p in (slots.get("indicator", ""), indicator_w) if p
            ),
            chevron_glyph=slots.get("chevron", ""),
            chevron_size=size_cfg.get("chevron_size", "sm"),
            icon_class=_resolve(slots.get("icon", "")),
            label_class=slots.get("label", ""),
            icon_size=size_cfg.get("icon_size", "sm"),
            group_class=slots.get("group", ""),
            base_pad=float(size_cfg.get("base", 0.5)),
            step_pad=float(size_cfg.get("step", 1.0)),
            expanded=set(self._expanded),
            selected=initial_sel,
            spacer_span=spacer_span,
        )

        # ``unwrap_transparent`` : un nœud ENVELOPPÉ — zone
        # ``@refreshable``, ``ui.fragment`` — n'est pas une instance de
        # ``TreeNode``, donc il DISPARAISSAIT de l'arbre. Mesuré le
        # 2026-08-23 : 2 211 → 1 249 caractères, sans une erreur.
        # ``rewrap`` rend son ``bz-id`` à la zone.
        top_nodes = [unwrap_transparent(c) for c in self._children]
        node_els = [
            rewrap(self._render_node(n, 0, ctx))
            for n, rewrap in top_nodes
            if isinstance(n, TreeNode)
        ]

        # ── Hidden input — form / server-action integration ──────────
        root_attrs = self.emit_attrs()
        relocated_change = _pop_change_handler(root_attrs)
        name = self._reactive_values.get("name") or self._derive_field_name()

        hidden_node: Element | None = None
        if selectable and (name or relocated_change):
            value_directive = sel_expr if value_binding is not None else sel_key
            hidden_attrs: dict[str, Any] = {
                **hidden_carrier_attrs(value_directive, initial=initial_sel),
            }
            if name:
                hidden_attrs["name"] = str(name)
            hidden_attrs.update(relocated_change)
            hidden_node = Element(tag="input", attrs=hidden_attrs, children=())

        # ── Assemble the root <ul> ───────────────────────────────────
        root_attrs["class"] = _resolve(slots.get("root", ""))
        root_attrs["role"] = "tree"
        root_attrs["bz-data"] = bz_data

        children: list[Node] = list(node_els)
        if hidden_node is not None:
            children.append(hidden_node)

        return Element(tag=self._tag, attrs=root_attrs, children=tuple(children))

    # ── Recursive node render ──────────────────────────────────────────

    def _render_node(self, node: TreeNode, depth: int, ctx: _RenderCtx) -> Element:
        node_id = str(node._reactive_values.get("value") or "")
        id_js = json.dumps(node_id)
        disabled = bool(node._reactive_values.get("disabled"))
        # Les enfants d'un nœud se déballent comme ceux de la racine : un
        # sous-arbre rafraîchissable est un cas d'usage tout aussi normal.
        kids = [
            child
            for child, _ in (unwrap_transparent(c) for c in node._children)
            if isinstance(child, TreeNode)
        ]
        is_branch = bool(kids)
        is_open = node_id in ctx.expanded
        is_sel = ctx.selectable and node_id == ctx.selected

        # ── Row content : chevron / spacer + icon + label ────────────
        row_children: list[Node] = [
            self._chevron(id_js, is_open, ctx) if is_branch else ctx.spacer_span
        ]
        icon_el = self._node_icon(node, ctx)
        if icon_el is not None:
            row_children.append(icon_el)
        row_children.append(self._node_label(node, ctx))

        # ── Row interaction ──────────────────────────────────────────
        commands: list[str] = []
        if is_branch:
            commands.append(f"toggle({id_js})")
        if ctx.selectable:
            commands.append(f"select({id_js})")
        command_js = "; ".join(commands)

        row_cls = ctx.row_class
        if disabled:
            row_cls = f"{row_cls} {ctx.row_disabled}".strip()
        row_attrs: dict[str, Any] = {
            "class": row_cls,
            "role": "treeitem",
            "tabindex": "0" if not disabled else "-1",
            "aria-level": str(depth + 1),
            "style": f"padding-left:{ctx.base_pad + depth * ctx.step_pad:.3f}rem",
        }
        if disabled:
            # ``role=treeitem`` is a non-native element : the visual dim +
            # ``tabindex=-1`` don't tell a screen reader it's disabled — only
            # ``aria-disabled`` does. (Native ``<button disabled>`` items —
            # accordion/tabs — get this for free ; role-based rows don't.)
            row_attrs["aria-disabled"] = "true"
        if is_branch:
            # aria only — the chevron is driven by bz-show, not a
            # ``data-open`` CSS hook, so no data attribute is needed.
            row_attrs["aria-expanded"] = "true" if is_open else "false"
            row_attrs["bz-attr:aria-expanded"] = bool_attr(f"isOpen({id_js})")
        if ctx.selectable:
            # ``data-selected`` drives the row's own ``data-[selected]``
            # tint (a self-selector, not a group one) ; aria mirrors it.
            row_attrs["aria-selected"] = "true" if is_sel else "false"
            row_attrs["bz-attr:aria-selected"] = bool_attr(f"isSel({id_js})")
            if is_sel:
                row_attrs["data-selected"] = "true"
            row_attrs["bz-attr:data-selected"] = bool_attr(f"isSel({id_js})")
        if command_js and not disabled:
            row_attrs["bz-on:click"] = command_js
            row_attrs["bz-on:keydown"] = activate_keydown(
                f"{command_js};"
            )
        row = Element(tag="div", attrs=row_attrs, children=tuple(row_children))

        # ── Leaf : the row is the whole li ───────────────────────────
        if not is_branch:
            return Element(tag="li", attrs={"role": "none"}, children=(row,))

        # ── Branch : row + collapsible <ul role="group"> ─────────────
        group_attrs: dict[str, Any] = {
            "class": ctx.group_class,
            "role": "group",
            "bz-show": f"isOpen({id_js})",
        }
        if not is_open:
            # Pre-stamp display:none so SSR paints the collapsed state
            # before the runtime hydrates (bz-show flips it after).
            group_attrs["style"] = "display:none"
        group = Element(
            tag="ul",
            attrs=group_attrs,
            children=tuple(self._render_node(k, depth + 1, ctx) for k in kids),
        )
        return Element(tag="li", attrs={"role": "none"}, children=(row, group))

    @staticmethod
    def _chevron(id_js: str, is_open: bool, ctx: _RenderCtx) -> Element:
        """The disclosure triangle : two glyphs in the fixed-width cell,
        each shown/hidden by ``bz-show`` keyed to THIS node's open state.

        Inline ``display`` (what bz-show sets) beats the ``<iconify-icon>``
        base ``inline-flex`` a CSS ``hidden`` class loses to ; keying on
        ``isOpen(id)`` — not an ancestor-matching ``.group`` variant —
        keeps a nested node's chevron bound to its own state. The
        initially-hidden glyph is pre-stamped ``display:none`` so the
        SSR paint already shows the right one (bz-show re-confirms it on
        hydration)."""
        def glyph(name: str, show: bool, expr: str) -> Node:
            attrs: dict[str, Any] = {"bz-show": expr}
            if not show:
                attrs["style"] = "display:none"
            # render_detached : un Icon construit pendant render() fuit à
            # la racine quand le Tree est détaché (cf. banner/badge).
            return Component.render_detached(Icon(
                name, size=ctx.chevron_size, classes=ctx.chevron_glyph,
                attrs=attrs,
            ))

        return Element(
            tag="span",
            attrs={"class": ctx.indicator_class, "aria-hidden": "true"},
            children=(
                glyph("chevron-right", not is_open, f"!isOpen({id_js})"),
                glyph("chevron-down", is_open, f"isOpen({id_js})"),
            ),
        )

    @staticmethod
    def _node_icon(node: TreeNode, ctx: _RenderCtx) -> Element | None:
        icon = node._icon
        if icon is None:
            return None
        if isinstance(icon, Component):
            return Component.render_detached(icon)
        # String name → build a themed Icon at the tree's size.
        return Component.render_detached(
            Icon(str(icon), size=ctx.icon_size, classes=ctx.icon_class)
        )

    @staticmethod
    def _node_label(node: TreeNode, ctx: _RenderCtx) -> Element:
        label = node._reactive_values.get("label")
        attrs = {"class": ctx.label_class}
        # Pas de branche ClientBinding : ``label`` n'est pas bindable et un
        # binding vit dans ``_binding_metadata``, jamais ``_reactive_values``
        # — cf. traps.md § « Lire un binding via _reactive_values + isinstance ».
        if isinstance(label, Component):
            return Element(tag="span", attrs=attrs, children=(label.render(),))
        # Empty / omitted label → fall back to the node id (a labelless
        # node still needs something to read). ``label`` defaults to ""
        # (a reactive_prop), never None, so the guard is truthiness.
        text = str(label) if label else str(
            node._reactive_values.get("value") or ""
        )
        return Element(tag="span", attrs=attrs, children=(TextNode(text),))


# Lightweight bag of the resolved, per-render styling passed down the
# recursion — a plain object (not a closure over ``render``) so the walk
# carries only the fields it needs. ``spacer_span`` is the shared
# immutable sub-node built once in ``render``.
class _RenderCtx:
    __slots__ = (
        "base_pad",
        "chevron_glyph",
        "chevron_size",
        "expanded",
        "group_class",
        "icon_class",
        "icon_size",
        "indicator_class",
        "label_class",
        "row_class",
        "row_disabled",
        "selectable",
        "selected",
        "spacer_span",
        "step_pad",
    )

    def __init__(self, **kw: Any) -> None:
        for k, v in kw.items():
            setattr(self, k, v)


# ───────────────────────────────────────────────────────────────────────────
# TreeNode — one row, rendered by its parent Tree
# ───────────────────────────────────────────────────────────────────────────


class TreeNode(Component):
    """One node inside a :class:`Tree`.

    Carries its ``value`` (node id), ``label``, optional ``icon`` and
    ``disabled`` flag. A ``with`` block of nested ``tree_node``\\s makes
    it a branch. The parent :class:`Tree` walks the node graph and
    renders each row + collapsible group — an isolated ``tree_node`` at
    page scope falls back to a plain ``<div>`` with its children so a
    stray one never blows up the renderer.
    """

    THEME_KEY: ClassVar[str] = "tree_node"
    DEFAULT_TAG: ClassVar[str] = "li"
    # ``value`` drives selection ; per-node bindings would mean N bindings.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
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
        reject_component(
            value,
            owner="TreeNode",
            prop="value",
            because=(
                "``value`` est l'IDENTIFIANT du nœud — c'est lui que le "
                "Tree compare pour la sélection et le pliage, et il part "
                "dans le littéral de scope lu par le runtime. Un Component "
                "y était stringifié en son repr Python, donc l'identifiant "
                "changeait à chaque rendu."
            ),
            instead="Le contenu affiché, c'est ``label=`` — il accepte un Component.",
        )
        # ``label`` is a ``reactive_prop`` — the base ``Component.__init__``
        # already auto-detaches any Component value landing in a
        # reactive_prop (cf. component.py's generic reactive-props loop),
        # so no manual adopt_slot/detach is needed here.
        # Forward direct : le socle drope les kwargs reactive None (garde le defaut).
        super().__init__(
            value=value,
            label=label,
            disabled=disabled,
            **kwargs,
        )
        # Icon is rendered by the parent Tree (which knows the size) —
        # detach a Component icon so it doesn't leak into the child list.
        if isinstance(icon, Component):
            icon = Component.adopt_slot(icon)
        self._icon: Any = icon

    def render(self) -> Element:
        # Outside a Tree the node has no disclosure context — emit a
        # plain div with the body so children at least appear.
        return Element(
            tag="div",
            attrs={"class": "outline-none"},
            children=tuple(self._render_children()),
        )


__all__ = ["Tree", "TreeNode"]
