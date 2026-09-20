"""``FormField`` — wraps an input with label / hint / error display.

Error inference is **implemented**: ``_infer_child_error()`` reads
``owner.errors[field_name]`` through the child's ``AUTONAME_FROM`` stamp,
and ``render()`` calls it — so a ``ui.input(value=form.email)`` inside a
``form_field`` surfaces ``form.errors["email"]`` by itself, with no
explicit ``error=``. ``error`` and ``hint`` are bindable besides
(``BINDABLE_PROPS``).

An explicit ``error="…"`` stays possible and beats the inference.

Usage ::

    with ui.form(on_submit=submit):
        with ui.form_field(label="Email", required=True, hint="…"):
            ui.input(name="email", type="email", required=True)
        with ui.form_field(label="Password", required=True):
            ui.input(name="password", type="password", minlength=12)
        ui.button("Sign up", type="submit")
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop, stamp_display_none
from bretzel.components.inputs.form_field.theme import FORM_FIELD_THEME
from bretzel.core.tree import Element
from bretzel.core.tree import TextNode as TextNode


class FormField(Component):
    """Field wrapper : label on top, child input in the middle,
    hint or error below."""

    THEME: ClassVar[dict[str, Any]] = FORM_FIELD_THEME
    THEME_KEY: ClassVar[str] = "form_field"
    # both change at runtime. label/required/name are design-time.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("error", "hint")

    label: str | None = reactive_prop(default=None, emit_attr=False)
    hint: str | None = reactive_prop(default=None, emit_attr=False)
    error: str | None = reactive_prop(default=None, emit_attr=False, writes=True)
    required: bool = reactive_prop(default=False, emit_attr=False)
    name: str | None = reactive_prop(default=None, emit_attr=False)

    def __init__(
        self,
        *,
        label: str | None = None,
        hint: str | None = None,
        error: str | None = None,
        required: bool | None = None,
        name: str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            label=label, hint=hint, error=error,
            required=required, name=name,
            **kwargs,
        )

    def _infer_child_error(self) -> str | None:
        """Resolve the validation message for the wrapped form-control's
        bound field, or ``None``.

        The child carries its field via the autoname stamp : the value
        bound to ``AUTONAME_FROM`` (``value=form.amount``) is a server-
        state scalar wrapper exposing ``field_name`` (which field) and
        ``owner`` (which state instance). ``owner.errors[field_name]`` is
        the message the action dispatcher collected when hydrating the
        form. Mirrors the autoname lookup in
        :meth:`Component.emit_attrs` — so no ``error=form.errors.get(...)``
        is needed at the call site.
        """
        for child in self._children:
            autoname_prop = getattr(type(child), "AUTONAME_FROM", None)
            if not autoname_prop:
                continue
            raw = child._reactive_values.get(autoname_prop)
            field_name = getattr(raw, "field_name", None)
            owner = getattr(raw, "owner", None)
            if not field_name or owner is None:
                continue
            errors = getattr(owner, "errors", None)
            if isinstance(errors, dict):
                message = errors.get(field_name)
                if message:
                    return str(message)
        return None

    def render(self) -> Element:
        theme = self._resolved_theme()
        slots = theme.get("slots", {})

        # ── Resolve the error up front (inference + binding) ───────────
        # Done BEFORE children render so we can stamp aria-invalid /
        # aria-describedby on the bound form-control. When no explicit
        # ``error=`` was passed, the wrapped input's bound server-state
        # field supplies the message via ``owner.errors[field]`` (zero
        # call-site wiring). Explicit ``error=`` (literal or binding) wins.
        inferred_error = False
        if (self._reactive_values.get("error") is None
                and self._binding_metadata.get("error") is None):
            inferred = self._infer_child_error()
            if inferred:
                self._reactive_values["error"] = inferred
                inferred_error = True

        error_raw = self._reactive_values.get("error")
        hint_raw = self._reactive_values.get("hint")
        error_binding = self._binding_metadata.get("error")
        hint_binding = self._binding_metadata.get("hint")

        error_expr = (
            self.path_of(error_binding) if error_binding is not None
            else None
        )
        hint_expr = (
            self.path_of(hint_binding) if hint_binding is not None
            else None
        )

        # An error span is rendered when there's a static message OR a
        # bound error path (shown/hidden reactively). Give it a stable id
        # so the input's ``aria-describedby`` can point at it.
        has_error_span = error_expr is not None or bool(error_raw)
        error_id = f"{self.id}-error" if has_error_span else None

        # ── Propagate required + error a11y to form-control children ────
        # ``required`` → native HTML5 validation + ``aria-required`` (the
        # latter covers custom controls whose trigger isn't a native
        # ``<input>``). On error → ``aria-invalid`` + ``aria-describedby``
        # link the control to its message for assistive tech. Per-item
        # ``required=True`` wins. Duck-typed on ``__reactive_props__`` to
        # avoid importing the concrete Input / Select / Textarea (circular).
        required = bool(self._reactive_values.get("required"))
        for child in self._children:
            descriptors = getattr(type(child), "__reactive_props__", {})
            if "required" not in descriptors:
                continue
            if required:
                if not child._reactive_values.get("required"):
                    child._reactive_values["required"] = True
                child._raw_attrs["aria-required"] = "true"
            if error_id is not None:
                child._raw_attrs["aria-describedby"] = error_id
            if error_raw:
                # A concrete message is present at render → mark invalid.
                child._raw_attrs["aria-invalid"] = "true"

        children: list[Any] = []

        # ── Label ──────────────────────────────────────────────────────
        label = self._reactive_values.get("label")
        if label:
            label_children: list[Any] = [self.emit_text_slot(label)]
            if self._reactive_values.get("required"):
                label_children.append(
                    Element(
                        tag="span",
                        attrs={
                            "class": slots.get("label_required", ""),
                            "aria-hidden": "true",
                        },
                        children=(TextNode("*"),),
                    )
                )
            label_attrs: dict[str, Any] = {"class": slots.get("label", "")}
            # When the field has a ``name``, point the <label for=…> at
            # the input id (HTML5 association — clicking the label
            # focuses the input). The input typically uses ``name`` as
            # the implicit id ; explicit author intent wins.
            name = self._reactive_values.get("name")
            if name:
                label_attrs["for"] = str(name)
            children.append(
                Element(
                    tag="label",
                    attrs=label_attrs,
                    children=tuple(label_children),
                )
            )

        # ── Children (the actual input(s)) ─────────────────────────────
        children.extend(self._render_children())

        # ── Error or hint span (mutex — error wins ; hint shows only
        # when there is no error). Bound error/hint = reactive
        # ``bz-show``/``bz-text`` ; static literal = frozen ; inferred =
        # auto-clear via the local ``bz-data`` flag set on the root. FOUC :
        # the falsy branch is pre-stamped ``display:none`` (cf.
        # .claude/bretzel/runtime.md) so nothing flashes either way.
        if error_expr is not None:
            error_attrs: dict[str, Any] = {
                "class": slots.get("error", ""),
                "role": "alert",
                "id": error_id,
                "bz-show": error_expr,
                "bz-text": error_expr,
            }
            if not error_raw:
                # FOUC pre-stamp : hidden before the runtime's first
                # effect when the binding's SSR value is falsy.
                stamp_display_none(error_attrs)
            children.append(
                Element(
                    tag="span",
                    attrs=error_attrs,
                    children=(TextNode(str(error_raw or "")),),
                )
            )
        elif error_raw:
            err_attrs: dict[str, Any] = {
                "class": slots.get("error", ""),
                "role": "alert",
                "id": error_id,
            }
            if inferred_error:
                # Auto-clear : the span hides when the local ``errShown``
                # flag (declared + flipped on the root below) goes false.
                err_attrs["bz-show"] = "errShown"
            children.append(
                Element(
                    tag="span",
                    attrs=err_attrs,
                    children=(self.emit_text_slot(error_raw),),
                )
            )

        # Hint span — reactive when bound, static otherwise. Only
        # shown when error is falsy (error wins the mutex).
        if hint_expr is not None:
            hint_show = (
                f"({hint_expr}) && !({error_expr})"
                if error_expr is not None
                else hint_expr
            )
            ssr_visible = bool(hint_raw) and not bool(error_raw)
            hint_attrs: dict[str, Any] = {
                "class": slots.get("hint", ""),
                "bz-show": hint_show,
                "bz-text": hint_expr,
            }
            if not ssr_visible:
                # FOUC pre-stamp : hide pre-boot too so the SSR pass
                # doesn't flash a stale hint when an error is already
                # present.
                stamp_display_none(hint_attrs)
            children.append(
                Element(
                    tag="span",
                    attrs=hint_attrs,
                    children=(TextNode(str(hint_raw or "")),),
                )
            )
        elif hint_raw and not error_raw:
            children.append(
                Element(
                    tag="span",
                    attrs={"class": slots.get("hint", "")},
                    children=(self.emit_text_slot(hint_raw),),
                )
            )

        attrs = self.emit_attrs()
        attrs["class"] = self.compose_class("root")

        # ── Auto-clear stale errors on user input ──────────────────────
        # When ``error=`` is a ClientBinding, stamp ``bz-on:input`` at
        # the FormField root that resets the bound path to ``""`` on
        # any input event bubbling from the child form-control. This
        # implements the standard form UX : once the user starts editing
        # a field, the previous server-side error verdict is stale and the
        # message disappears instantly — no round-trip, no wait for
        # re-submit. Static literal ``error="..."`` keeps its message
        # frozen (the caller asked for a fixed error).
        #
        # ``bz-on:`` has no ``.capture`` modifier, so this listens in the
        # bubble phase — fine here : native ``input`` events bubble and no
        # descendant stops their propagation.
        if error_expr is not None:
            attrs["bz-on:input"] = f"{error_expr} = ''"
        elif inferred_error:
            # Server-collected (inferred) error : auto-clear the stale
            # validation message once the user edits the field. A local
            # ``bz-data`` flag, flipped by any child ``input`` event —
            # same local-scope pattern as Alert / Banner dismiss (keyed by
            # ``bz-id``, survives morphs ; descendants inherit the scope so
            # the error span's ``bz-show="errShown"`` reads it). An explicit
            # literal ``error=`` keeps its message frozen.
            attrs["bz-data"] = "{errShown: true}"
            attrs["bz-on:input"] = "errShown = false"

        return Element(
            tag=self._tag,
            attrs=attrs,
            children=tuple(children),
        )
