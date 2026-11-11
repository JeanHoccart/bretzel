"""How a component talks to the client: commands, bindings, the fields it names."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bretzel.components.base.attrs import (
    normalize_attr_name,
)
from bretzel.components.base.reactive_prop import (
    MISSING,
)
from bretzel.components.base.scope_wiring import bound_wire_name
from bretzel.runtime.protocol import (
    BZ_ATTR_PREFIX,
    BZ_MODEL_PREFIX,
)
from bretzel.state.scopes.client import ClientBinding, _to_js

if TYPE_CHECKING:
    pass


class ClientWiring:
    """Mixed into :class:`Component`."""

    def _scope_keys(self, prop: str = "value") -> tuple[str, ...]:
        """The key(s) under which ``prop`` lives in the ``bz-data``.

        Derived from ``reactive_prop(scope_keys=)`` by the metaclass;
        default ``(prop,)`` when the scope key IS the prop's name. The
        key is declared in the same place as the prop, because the names
        differ from one component to the next
        (value/picked/active/expanded/sel) and a key retyped by hand in a
        ``server_sync_marker("active"/"picked"/…, …)`` can miss its
        ``_serverSync``.
        """
        return type(self).__scope_keys__.get(prop, (prop,))

    def _value_server_backed(self, prop: str = "value") -> bool:
        """Does ``prop`` hold a value coming from the SERVER, in local mode?

        It is the condition — and the ONLY one — for emitting
        ``_serverSync`` (cf. ``base/scope_wiring.server_sync_marker``): on the
        next swap, the bridge will re-adopt that scope signal from the
        freshly morphed attribute, because the server is authoritative.

        Three cases, in order:

        1. **Client-binding mode** → ``False``. The value lives in
           ``$bz._store``, which the envelope already patches: nothing to
           re-adopt, and rewriting the signal would overwrite the
           client's edit.
        2. **Stamped scalar or list** (``_BoundStr`` / ``_BoundInt`` /
           ``_BoundList``… set by ``state/scopes/server._stamp``) →
           ``True``.
        3. **``[state.field]``** — a literal list one of whose ITEMS
           carries the stamp (a multi fed by a scalar server pick, the
           playground's pattern) → ``True``.

        ⚠️ **This is NOT ``_derive_field_name``**, and the confusion is
        expensive. That helper answers "where do I derive my HTML
        ``name=`` from"; this one answers "where does my value come
        from". They coincide on form inputs, hence the temptation to
        reuse one for the other. That produces TWO flaws: case 3 is lost
        (a multi fed by ``[state.field]`` does not re-adopt), and the
        server-sync dies silently if ``AUTONAME_FROM`` is removed. A
        component with no ``name=`` (Tabs, Accordion, Tree, the overlays)
        still has a server value.

        Every call site goes through this helper, so the decision is
        written once. Cf. traps.md § "Une config serveur se re-sème aussi
        quand la valeur est liée".
        """
        if self._binding_metadata.get(prop) is not None:
            return False
        raw = self._reactive_values.get(prop)
        if getattr(raw, "field_name", None) is not None:
            return True
        if isinstance(raw, (list, tuple)):
            return any(getattr(v, "field_name", None) is not None for v in raw)
        return False

    def _derive_field_name(self) -> str | None:
        """Autoname field name from the bound / server-stamped ``AUTONAME_FROM`` prop.

        Two sources, in order : (1) a ``ClientBinding`` passed as
        ``value=state.foo`` (its ``field_name``), (2) a server-state scalar
        stamped by :func:`bretzel.state.scopes.server._stamp` (a ``_Bound*``
        carrying ``field_name``). Returns ``None`` when neither is present.

        Placement-agnostic : returns only the string. The base
        :meth:`emit_attrs` lands it on the root ``name`` ; composite inputs
        (root is a ``<div>`` / ``<label>`` / custom element) layer their own
        explicit-``name=`` and fallback around it and stamp the hidden
        ``<input>`` carrier themselves. Single source for the derivation,
        shared by every carrier component.
        """
        prop = type(self).AUTONAME_FROM
        if not prop:
            return None
        # ``Delivery.mode``, not ``mode``: the name says WHOSE field it is
        # (``state/_wire_name.py``).
        return bound_wire_name(self._binding_metadata.get(prop)) or bound_wire_name(
            self._reactive_values.get(prop)
        )

    def _dispatch_command(
        self,
        event_name: str,
        *,
        value: Any = MISSING,
    ) -> str:
        """Build the client-expr source for dispatching a command event.

        Used by the write-only imperative API (`.open()` / `.close()` /
        `.toggle()` and value-bearing methods `.set(value)` /
        `.clear()`) when no :class:`ClientBinding` is in play for the
        target prop. Returns a client expression string, same return
        shape as ``ClientBinding.set/toggle`` — so the result is
        consumable by ``on_click=`` and any other ``on_*`` slot.

        The dispatched CustomEvent bubbles, so the component's root
        can listen via a single ``@<event_name>`` directive without
        worrying about which descendant the original click landed on.

        Pass ``value=`` to attach a payload that the component's
        listener can read via ``$event.detail.value``. Used by
        ``.set(value)`` style methods on Checkbox / Switch / Input /
        Select where the new value has to travel with the event.
        Skipping ``value=`` emits the event with no detail (for
        valueless commands like ``.open()`` / ``.close()`` /
        ``.toggle()``).

        Convention : framework-internal commands are prefixed ``bz-``
        (``bz-open``, ``bz-close``, ``bz-toggle``, ``bz-set``,
        ``bz-step``, etc.) so they never collide with user-defined
        custom events. See `imperative-api.md`.
        """
        if value is MISSING:
            return (
                f"document.getElementById('{self.id}').dispatchEvent("
                f"new CustomEvent('{event_name}', {{bubbles: true}}))"
            )
        return (
            f"document.getElementById('{self.id}').dispatchEvent("
            f"new CustomEvent('{event_name}', "
            f"{{bubbles: true, detail: {{value: {_to_js(value)}}}}}))"
        )

    def _value_command(
        self,
        value: Any,
        *,
        prop: str = "value",
        event: str = "bz-set",
    ) -> str:
        """The body of ``.set(value)``: write-through, otherwise dispatch.

        An imperative method carrying a value has exactly two paths —
        writing into the :class:`ClientBinding` passed at construction
        (the single source of truth), or, failing that, dispatching a DOM
        command the component's root catches. It is the same switch that
        :func:`base/overlay_wiring.install_open_close_toggle` factors out for
        the overlay family.

        Shared by every component offering such a method, on ``value`` or
        on ``checked`` (with boolean coercion): a change to the contract
        — a new binding subtype, another event name — is made here once.

        What stays per-component, rightly: ``.clear()`` (the reset value
        is semantic — ``""``, ``[]``, ``min``, ``None``) and ``.focus()``
        / ``.blur()`` (the focusable surface differs).
        """
        binding = self._binding_metadata.get(prop)
        if binding is not None:
            return binding.set(value)
        return self._dispatch_command(event, value=value)

    def _toggle_command(
        self,
        *,
        prop: str = "checked",
        event: str = "bz-toggle",
    ) -> str:
        """The body of ``.toggle()`` — same switch as
        :meth:`_value_command`, with ``binding.toggle()`` on the binding
        side.

        Copied identically into Checkbox and Switch.
        """
        binding = self._binding_metadata.get(prop)
        if binding is not None:
            return binding.toggle()
        return self._dispatch_command(event)

    @staticmethod
    def path_of(binding: ClientBinding) -> str:
        """Canonical client-side path for ``binding``, whatever its
        concrete subclass.

        - :class:`ClientBinding` → ``$bz.state.Class.key.field`` (the
          full form, ready to interpolate into a client expression
          like ``bz-attr:disabled="…"`` or ``bz-on:click="… = …"`` — the
          ``:``/``@`` forms are dead Alpine dialect).
        - :class:`ClientExpression` → the verbatim JS expression the
          builder accumulated (no ``$bz.state.`` prefix is added —
          the expression already contains the path fragments).

        This unifies the if/else ladder that lived in every component
        rendering a bz-attr binding manually: ``isinstance(b,
        ClientExpression) ? b.binding_path() : f"$bz.state.{b.serialize_path()}"``.
        The forms are equivalent because :py:meth:`ClientExpression.binding_path`
        returns the same string as :py:meth:`ClientExpression.serialize_path`
        (the raw expression), and ``binding_path`` on a plain binding
        prepends ``$bz.state.`` itself. Funneling through this helper
        kills a recurring source of divergence between components.
        """
        return binding.binding_path()

    def release_root_attr(
        self,
        prop: str,
        root_attrs: dict[str, Any],
    ) -> None:
        """Strip the literal AND reactive directives for ``prop`` from
        the component's root attrs.

        Use when a binding-bearing prop is wired to an INNER element
        (via :py:meth:`forward_binding`) OR when the component manages
        the value via custom client wiring (date pickers' ``$watch``
        pair on the wrapper). Leaving the wrapper-level directive
        emitted means the runtime writes a useless ``X=""`` on the wrapper
        every reactive tick and the carrier-landing audit flags it.

        Pops both the literal ``<prop>="…"`` and the reactive
        ``bz-attr:<prop>="…"`` so neither survives.
        """
        attr_name = normalize_attr_name(prop)
        root_attrs.pop(attr_name, None)
        root_attrs.pop(f"{BZ_ATTR_PREFIX}{attr_name}", None)

    def forward_binding(
        self,
        prop: str,
        target_attrs: dict[str, Any],
        *,
        as_attr: str | None = None,
        root_attrs: dict[str, Any] | None = None,
    ) -> ClientBinding | None:
        """Forward ``prop``'s :class:`ClientBinding` onto a carrier
        element's attrs.

        Solves the wrapper-vs-carrier trap : :py:meth:`emit_attrs`
        lands ``bz-attr:<prop>`` on the component's ROOT, but many
        HTML attributes only do something on a specific tag —
        ``disabled`` / ``multiple`` / ``accept`` / ``required`` on
        form controls ; ``src`` / ``srcset`` on media ; ``value`` on
        the form-data carrier. Writing them on the wrapper ``<div>``
        / ``<span>`` is a no-op the runtime silently performs every
        reactive tick, and the unit tests don't notice because the
        SSR HTML "looks right".

        This method :

        - Adds ``bz-attr:<as_attr or prop>="$bz.state.<path>"`` to
          ``target_attrs`` (the inner carrier's attrs dict).
        - When ``root_attrs`` is passed, pops the duplicate
          ``bz-attr:<as_attr or prop>`` AND its literal-value
          equivalent (``as_attr or prop``) from the wrapper so the
          binding lives on the carrier alone — exactly one writer
          per attribute, no runtime tick wasted patching a div.

        Returns the resolved binding (or ``None`` when ``prop`` had
        no binding) so callers can branch on the static-value
        fallback path without re-reading ``_binding_metadata``.

        Use this in every component whose render emits a nested
        carrier element distinct from the root.
        """
        binding = self._binding_metadata.get(prop)
        if not isinstance(binding, ClientBinding):
            return None
        attr = as_attr or prop
        attr_name = normalize_attr_name(attr)
        # ⚠️ ARIA wants the STRING "true"/"false", not the semantics of
        # native boolean attributes. ``bz-attr`` treats a boolean the way
        # HTML wants — ``true`` → EMPTY attribute, ``false`` → attribute
        # removed (directives.js) — which is correct for ``disabled``
        # / ``checked``, and WRONG for ``aria-*``: the Tailwind
        # ``aria-disabled:`` variant compiles to
        # ``[aria-disabled="true"]``, which an empty attribute does not
        # match, and a screen reader reads nothing. Derived here, the
        # ternary cannot be forgotten.
        from bretzel.components.base.scope_wiring import bool_attr

        path = self.path_of(binding)
        value = bool_attr(path) if attr_name.startswith("aria-") else path
        target_attrs[f"{BZ_ATTR_PREFIX}{attr_name}"] = value
        if root_attrs is not None:
            self.release_root_attr(attr, root_attrs)
        return binding

    def _bind_x_model(
        self,
        attrs: dict[str, Any],
        prop: str = "value",
        *,
        binding: ClientBinding | None = None,
    ) -> ClientBinding | None:
        """Wire ``bz-model`` two-way binding for ``prop`` on ``attrs``.

        Form-input components call this with the dict that will
        become the real ``<input>`` attrs. When a :class:`ClientBinding`
        is in play for ``prop`` (typically ``"value"`` for text inputs /
        select, ``"checked"`` for checkbox / switch), we drop the
        read-only ``bz-attr:<prop>`` directive that
        :py:meth:`emit_attrs` set and replace it with
        ``bz-model="$bz.state.<path>"``, which the runtime propagates
        in BOTH directions.

        By default the binding is read from ``self._binding_metadata``.
        Composite inputs whose binding lives on an enclosing parent
        (Radio inherits the group's ``value=binding`` ; date-range
        pickers split a single binding across two child inputs) pass
        ``binding=...`` explicitly to override the lookup.

        Returns the resolved binding (or ``None`` when none was found)
        so callers can branch on the literal-value fallback — Textarea
        uses it to suppress the ``initial_text`` emission, Radio to
        compute ``checked`` from a static value comparison.

        Reading the binding from ``_binding_metadata`` is mandatory :
        the matching entry in ``_reactive_values`` carries the
        binding's underlying SSR value, not the binding object itself,
        so an ``isinstance(_reactive_values[prop], ClientBinding)``
        check is always False at runtime (cf. ``traps.md``).
        """
        if binding is None:
            binding = self._binding_metadata.get(prop)
        if binding is None:
            return None
        attr_name = normalize_attr_name(prop)
        attrs.pop(f"{BZ_ATTR_PREFIX}{attr_name}", None)
        attrs[BZ_MODEL_PREFIX] = f"$bz.state.{binding.serialize_path()}"
        return binding
