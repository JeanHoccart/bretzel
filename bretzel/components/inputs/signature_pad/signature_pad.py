"""``SignaturePad`` — sign with a finger or a mouse, inside a form.

Usage ::

    class Contract(PageState):
        signature: str = field(default="")

    with ui.form(on_submit=sign):
        ui.signature_pad(value=contract.signature)
        ui.button("Sign", type="submit")

    def sign(doc: Contract) -> None:
        doc.signature      # "data:image/png;base64,iVBORw0KG…"

**The value is a PNG data URL**, and it lives in your `ServerState`.
``AUTONAME_FROM = "value"`` derives the hidden input's ``name`` from the
field you pass it, and
:func:`~bretzel.server.routing.actions._hydrate_state` writes it back
into the instance on submit — like any form field. No endpoint, no
encoding to write.

The PNG rather than the points or SVG: the consumer of a signature wants
an IMAGE (to embed it in a PDF, show it in a record, store it).
Returning the points would force every caller to rewrite the rasteriser.

⚠️ **``value`` is bindable, but binding a ``ClientState`` to it costs.**
The base layer requires it (``TWO_WAY_PROPS ⊆ BINDABLE_PROPS``: a field
the client writes cannot be form-bound without being bindable), and in
LOCAL mode — the normal case, ``value=doc.signature`` on a ServerState —
the data URL lives in the JS scope and costs nothing on the wire. The
``ClientState`` snapshot, on the other hand, leaves **whole on every
action POST** (``runtime/_src/05_bridge.js``), so a pad bound to a
``ClientState`` would send its tens of kilobytes back on every click of
the page. There is no "delta" mode to avoid it — it was removed on
2026-08-14, its semantics being wrong (cf. ``ClientState``'s docstring).
The only lever is ``send_to_server=False``, which does NOT apply here: a
signature is written by the client, it has to travel back. Only do this
if another component has to read the signature on the client side.

**Nothing is published during the gesture**: the data URL is written
when the pen LIFTS. A wired ``on_change`` therefore makes one POST per
stroke — that is bearable and it is explicit, where publishing per frame
would not be.

**The pad is EMPTY, not white, as long as nothing is drawn.** A fresh
canvas returns a perfectly valid PNG — a white rectangle — and
publishing it would pass "not signed yet" off as "signed" on the server
side, with nothing looking wrong. Zero strokes ⇒ empty string.

**A signature already there is REPAINTED.** Passing an existing data URL
(a reopened record) loads it at hydration and paints it as a background
layer, under the new strokes — so it survives a resize like the rest,
and resubmitting without touching it does not erase it. ``.clear()``
takes it away along with the strokes: "clear" means an empty frame, not
"go back to the previous signature". *(The first version did not load
it: the frame showed empty AND with no prompt, since the SSR had already
set ``data-empty="false"`` — the component announced a signature while
showing none.)*

The stroke is inked with the text colour READ on the canvas, never
configured: it follows dark mode by itself. So there is no
``pen_color=`` — it would have frozen an invisible ink on the other
background.

Imperative API : ``.clear()``. A signature is redone, it is not touched
up — no ``undo()``. (The runtime does keep the points, but in order to
redraw after a size change: a canvas clears when you resize it, and a
phone you turn resizes it.)
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.actions.button import Button
from bretzel.components.base import Component, reactive_prop
from bretzel.components.base._wiring import (
    hidden_carrier_attrs,
    pop_change_handler,
    server_sync_marker,
)
from bretzel.components.inputs.signature_pad.theme import SIGNATURE_PAD_THEME
from bretzel.core.tree import Element, Node
from bretzel.render import text


class SignaturePad(Component):
    """Surface de signature — pointeur / doigt → PNG en data-URL."""

    THEME: ClassVar[dict[str, Any]] = SIGNATURE_PAD_THEME
    THEME_KEY: ClassVar[str] = "signature_pad"
    # ``value`` IS bindable, and the base layer's invariant requires it:
    # ``TWO_WAY_PROPS ⊆ BINDABLE_PROPS`` (``test_two_way_props``). A
    # field the client writes — and it does write it, the user draws —
    # cannot be form-bound without being bindable. The reservation about
    # weight stays true and lives in the module's docstring: it concerns
    # ONLY the case where the caller binds to a ``ClientState``.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("value",)
    IMPERATIVE: ClassVar[tuple[str, ...]] = ("clear",)
    EVENTS: ClassVar[tuple[str, ...]] = ("change",)

    # ``names_field=True``: it is THIS prop that gives the hidden
    # carrier its HTML ``name``, so the ServerState field passed to it.
    # The ``AUTONAME_FROM`` ClassVar is DERIVED from it — declaring it by
    # hand is refused at load time (two places for a single fact).
    # ``writes=True`` is required by ``names_field`` and it is right: the
    # CLIENT does write this value (it draws) — and that is precisely
    # what forces ``value`` into ``BINDABLE_PROPS`` above. What NEVER
    # goes back into a signal is the stroke itself: the points live in
    # the canvas, only the data URL lands on the carrier.
    # ``never_code``: this value is a **data URL**, and its base64
    # padding is written ``=`` or ``==`` — so roughly one stroke in four
    # came out classified "client expression" by the heuristic, left as
    # ``bz-attr:value=`` and crashed the runtime's boot (measured on
    # 2026-08-13). It had been repaired by a ``data:`` exclusion INSIDE
    # the heuristic; that is gone since 2026-08-26 in favour of this
    # declaration, which states the fact where it is true. It is the
    # only URI carrier whose prop name does not announce it — hence its
    # by-name entry in ``test_a_url_prop_is_never_read_as_code``.
    value: str | None = reactive_prop(
        default=None, emit_attr=False, writes=True, names_field=True,
        never_code=True,
    )
    # ``None``: a ``reactive_prop`` default is resolved at import, so it
    # would freeze English whatever the app's language.
    placeholder: str | None = reactive_prop(default=None, emit_attr=False)
    clear_label: str | None = reactive_prop(default=None, emit_attr=False)
    disabled: bool = reactive_prop(default=False, emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    name: str | None = reactive_prop(default=None, emit_attr=False)

    def __init__(
        self,
        *,
        value: str | None = None,
        placeholder: str | None = None,
        clear_label: str | None = None,
        disabled: bool | None = None,
        size: str | None = None,
        color: str | None = None,
        name: str | None = None,
        on_change: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs.
        super().__init__(
            value=value,
            placeholder=placeholder,
            clear_label=clear_label,
            disabled=disabled,
            size=size,
            color=color,
            name=name,
            on_change=on_change,
            **kwargs,
        )

    # ── Imperative API ─────────────────────────────────────────────────

    def clear(self) -> str:
        """Clear the drawing. Always a DOM dispatch.

        **Including when ``value`` carries a binding**, and it is the
        only reason that holds: clearing is not "writing the empty
        string". One also has to throw away ``_strokes``, forget the
        ``_base`` of a reopened signature and repaint the canvas — three
        things only the runtime knows how to do. A write-through
        (:meth:`Component._value_command`, the pattern of the eleven
        ``.set()``) would leave the frame showing a drawing the state
        says is absent.
        """
        return self._dispatch_command("bz-clear")

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme = self._resolved_theme()
        size_table = theme.get("sizes", {})
        size_key = self._reactive_values.get("size") or "md"
        size_cfg = size_table.get(size_key, size_table.get("md", {}))
        disabled = bool(self._reactive_values.get("disabled"))
        initial = self._reactive_values.get("value") or ""
        # ``is None`` and not ``or``: ``placeholder=""`` is an explicit
        # opt-out that must stay silent, and an ``or`` would give it the
        # default back.
        placeholder = self._reactive_values.get("placeholder")
        if placeholder is None:
            placeholder = text("signature_pad.placeholder")

        # ── Binding de ``value`` ─────────────────────────────────────
        value_binding = self._binding_metadata.get("value")
        scope_key = self._scope_keys("value")[0]
        binding_path = (
            self.path_of(value_binding) if value_binding is not None else None
        )
        value_expr = binding_path or scope_key

        canvas_attrs: dict[str, Any] = {
            "class": self.slot_class("canvas"),
            "bz-ref": "bzcanvas",
            # The canvas is NOT focusable and carries no role: what is
            # announced and reachable from the keyboard is the hidden
            # input (a real form control, with its ``name``) and the
            # Clear button. Setting a ``role`` on a drawing surface would
            # announce a control no key drives.
            "aria-hidden": "true",
        }
        if disabled:
            # Read by ``_locked()`` on the runtime side. An attribute
            # rather than a scope field: ``disabled`` is not bindable, so
            # the value is frozen at render and has no business being in
            # a signal.
            canvas_attrs["data-bz-pad-locked"] = ""
        else:
            canvas_attrs["bz-on:pointerdown"] = "_start($event)"
            canvas_attrs["bz-on:pointermove"] = "_draw($event)"
            canvas_attrs["bz-on:pointerup"] = "_end($event)"
            canvas_attrs["bz-on:pointercancel"] = "_end($event)"
            # Re-wired at every rescan, not at ``bz-init``: that one is
            # one-shot per node, yet a canvas replaced by a morph would
            # then never be observed (same reason, same remedy as the
            # Carousel's ``_observeGeom``).
            canvas_attrs["bz-effect"] = "_observe()"

        pad_children: list[Node] = [
            Element(tag="canvas", attrs=canvas_attrs, children=()),
            Element(
                tag="div",
                attrs={"class": self.slot_class("baseline")},
                children=(),
            ),
        ]
        if placeholder:
            pad_children.append(
                Element(
                    tag="div",
                    attrs={
                        "class": self.slot_class(
                            "hint", size_cfg.get("hint", "")
                        ),
                        # The same ``data-empty`` the frame carries:
                        # the prompt's Tailwind variant reads it on
                        # itself, so it must be there too.
                        "data-empty": "false" if initial else "true",
                    },
                    children=(self.emit_text_slot(placeholder),),
                )
            )

        pad = Element(
            tag="div",
            attrs={
                "class": self.slot_class("pad", size_cfg.get("pad", "")),
                # SSR: empty unless a signature is already there (a
                # reopened record). The runtime takes over at the first
                # stroke.
                "data-empty": "false" if initial else "true",
                "data-locked": "true" if disabled else "false",
            },
            children=tuple(pad_children),
        )

        # ── Hidden input — form data + source of the ``change`` ─────
        # The standard carrier: ``bz-attr:value`` reports the state into
        # the DOM, ``change_emit_effect`` draws the ``change`` from it.
        # So the runtime writes ONLY the state, never the input — a
        # single author.
        root_attrs = self.emit_attrs()
        relocated = pop_change_handler(root_attrs)
        field_name = (
            self._reactive_values.get("name") or self._derive_field_name()
        )
        hidden_attrs: dict[str, Any] = {
            **hidden_carrier_attrs(value_expr, initial=initial, ref="bzpad"),
        }
        if field_name:
            hidden_attrs["name"] = str(field_name)
        if disabled:
            hidden_attrs["disabled"] = True
        hidden_attrs.update(relocated)
        children: list[Node] = [
            pad,
            Element(tag="input", attrs=hidden_attrs, children=()),
        ]

        # ── The action bar ───────────────────────────────────────────
        # The button IS a ``ui.button``, not an imitation: it is the
        # repository's dogfooding rule, and it brings the focus ring, the
        # disabled state and the size scale for free.
        clear_label = self._reactive_values.get("clear_label")
        if clear_label is None:
            clear_label = text("signature_pad.clear")
        if clear_label:
            children.append(
                Element(
                    tag="div",
                    attrs={"class": self.slot_class("actions")},
                    children=(
                        Component.render_detached(
                            Button(
                                clear_label,
                                variant="ghost",
                                size=size_cfg.get("button", "sm"),
                                color=self._reactive_values.get("color")
                                or "primary",
                                icon_left="eraser",
                                disabled=disabled,
                                on_click=self.clear(),
                            )
                        ),
                    ),
                )
            )

        # ── Assemblage ───────────────────────────────────────────────
        root_attrs["class"] = self.slot_class("root")
        root_attrs["bz-data"] = self._build_bz_data(
            scope_key=scope_key,
            has_local_value=value_binding is None,
            initial=initial,
            binding_path=binding_path,
            server_synced=self._value_server_backed("value"),
        )
        # A scope method has no ``$refs`` — it is here, in directive
        # context, that we capture the canvas into the scope.
        root_attrs["bz-init"] = "_canvas = $refs.bzcanvas"
        root_attrs["bz-on:bz-clear"] = "clear()"

        return Element(
            tag=self._tag, attrs=root_attrs, children=tuple(children)
        )

    @staticmethod
    def _build_bz_data(
        *,
        scope_key: str,
        has_local_value: bool,
        initial: str,
        binding_path: str | None,
        server_synced: bool,
    ) -> str:
        """The instance's ``bz-data``: **data, not code**.

        The drawing (pointer, resize, render, publish) lives once in
        ``$bz.signaturePad.scope``.

        ``_canvas`` is declared ``null`` then filled by the root's
        ``bz-init``: a scope method has no access to ``$refs``, only
        directives do (same constraint and same remedy as Slider,
        Carousel and Resizable).

        ``_strokes`` lives HERE rather than on the node because it must
        survive the rescan without surviving the canvas — a scope is
        re-paired by ``bz-id``, exactly like the signature it carries.
        """
        if has_local_value:
            sync = server_sync_marker(scope_key, enabled=server_synced)
            state = f"{scope_key}: {json.dumps(initial)},{sync} "
            target = f"this.{scope_key}"
        else:
            assert binding_path is not None
            state = ""
            target = binding_path

        return (
            "{...$bz.signaturePad.scope,"
            + state
            + "_canvas: null,"
            + "_strokes: [],"
            + "_drawing: null,"
            # The signature ALREADY THERE, loaded once at hydration and
            # painted UNDER the new strokes. Declared here rather than
            # set on the fly on the JS side: an undeclared field becomes
            # a signal at its first write, so assigning it from the
            # image's ``onload`` would wake the scope's effects for
            # nothing.
            + "_base: null,"
            + f"_read() {{ return {target}; }},"
            + f"_write(v) {{ {target} = v; }}"
            + "}"
        )


__all__ = ["SignaturePad"]
