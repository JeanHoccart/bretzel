"""The client scope a component declares, and its server-side twins."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.runtime import (
    SERVERSYNC_KEY,
)
from bretzel.runtime.protocol import outlet_id_for
from bretzel.state._wire_name import wire_name


def bool_attr(expr: str) -> str:
    """A reactive attribute that must carry the STRING ``"true"``/``"false"``.

    ``bz-attr`` treats a boolean the way HTML wants: ``true`` → **empty**
    attribute, ``false`` → attribute **removed**. That is the right
    semantics for ``disabled`` / ``checked`` / ``required``, where the
    PRESENCE of the attribute is the information.

    Two families need the opposite — the literal value:

    - **ARIA** (``aria-disabled``, ``aria-expanded``, ``aria-pressed``,
      ``aria-selected``): a screen reader reads the value, and the
      Tailwind ``aria-disabled:`` variant compiles to
      ``[aria-disabled="true"]``, which an empty attribute does not match;
    - **the ``data-*`` that drive a style** (``data-open``,
      ``data-active``, ``data-menu-open``): ``data-[open=true]:`` matches
      the literal.

    In both cases, forgetting the ternary breaks NOTHING visible — neither
    the style nor the announcement applies, in silence. The rule lives
    here, once.

    The parentheses are not cosmetic: ``a || b ? 'true' : 'false'`` reads
    as ``(a || b) ? …`` by luck, but any looser expression would
    re-associate. Same class as the parenthesising of the binding algebra
    (cf. ``tests/consistency/test_client_expression_atomic.py``).
    """
    return f"({expr}) ? 'true' : 'false'"


def server_sync_marker(*props: str, enabled: bool) -> str:
    """``_serverSync`` fragment for a component's ``bz-data`` object literal.

    ``" _serverSync: ['<prop>', …],"`` when ``enabled`` (the value(s) are
    server-backed → a ``@refreshable`` morph re-adopts them from the freshly
    rendered attr, server wins) ; ``""`` otherwise (a client-owned value
    keeps its state through the morph). Accepts one OR several keys — a
    control whose scope holds several server-driven signals (calendar's
    ``year``+``month``, the range picker's ``vstart``+``vend``) lists them
    all in one marker. The ``_serverSync`` key is single-sourced from
    :data:`protocol.SERVERSYNC_KEY` and mirrored into the JS scope reader, so
    a rename can't silently strand one control. The leading space + trailing
    comma suit emission after a leading field in a ``{...}`` literal.
    """
    if not enabled:
        return ""
    return f" {_server_sync_entry(props)},"


def _server_sync_entry(keys: Iterable[str]) -> str:
    """``_serverSync: ['<key>', …]`` — the entry itself, no punctuation
    around it. The one spelling shared by :func:`server_sync_marker` and
    :func:`scope_literal`."""
    listed = ", ".join(f"'{k}'" for k in keys)
    return f"{SERVERSYNC_KEY}: [{listed}]"


def scope_literal(
    *slabs: str,
    cell: str | None = None,
    initial: str = "null",
    binding_path: str | None = None,
    server_synced: bool = False,
    accessors: tuple[str, str] = ("_read", "_write"),
    bound_read: str | None = None,
    fields: Mapping[str, str] | None = None,
    config: Mapping[str, str] | None = None,
    methods: Iterable[str] = (),
) -> str:
    """The ``bz-data`` object literal of a component with a runtime slab.

    The methods live ONCE in the runtime (``$bz.<name>.<scope>``); an
    instance only emits DATA, spread after the slab(s). ``slabs`` are
    written WHOLE at the call site (``"$bz.tabs.scope"``, or
    ``"$bz.combobox.common", "$bz.combobox.single"``): that is where
    ``test_bz_globals_emitted_by_python_exist_in_js`` reads the names
    Python emits. The spreads come FIRST, since a key written before them
    would be overwritten.

    **The value cell** (``cell=``, its scope key) is the switch every
    two-way component carries, and the reason this function exists:

    - **local** (``binding_path=None``): a ``<cell>: <initial>`` field,
      and the accessors address ``this.<cell>``;
    - **bound**: NO local field — the accessors address the store cell
      ``binding_path`` directly.

    Either way the slab's methods go through the two accessors
    (``_read()`` / ``_write(v)``, renamed by ``accessors=`` when the slab
    already uses those names for another cell). ⚠️ Never a getter
    (``get value()``): ``scope.absorb`` invokes each key once at
    registration and would freeze it on its first value (``traps.md``).
    ``bound_read`` is the expression of ``v`` the bound ``_read`` returns
    — a coercion of the raw store value (``v == null ? [] : v``).
    ``cell=None``: the component carries no value (``ui.tooltip``).
    The local target is ``this.<cell>`` and never the bare key: a method
    body is not evaluated in ``with($scope)``, so a bare identifier raises
    there — the whole panel of a picker went inert in literal mode only.

    **What the server re-seeds** (``_serverSync``). ``absorb`` never
    rewrites an existing signal, so a key the server changes reaches a
    live scope only if it is listed:

    - ``config`` — server-owned fields the client never writes (the
      options, the bounds, the page count): listed ALWAYS, in both value
      modes. The owner of the value does not change who owns the config
      — the bound branch of ``ui.select`` / ``ui.combobox`` forgot it,
      and a bound select never learnt the options a refresh added
      (``tests/runtime_js/test_a_bound_list_follows_its_refreshed_options.py``);
    - the cell — only when the SERVER owns the value (``server_synced``,
      from ``Component._value_server_backed``). A literal stays
      client-owned: re-seeding it would erase the user's pick on every
      neighbouring refresh. A bound value lives in the store, patched by
      the envelope: never listed.

    ``fields`` are seeded once and client-owned afterwards (``open``, a
    drag in progress, a ref filled at ``bz-init``). ``methods`` are
    overrides of a slab method, whole (``isDisabled() { … }``): a bound
    expression must live in a method body, the only place re-read on
    every call — as a field it would freeze at mount.
    """
    entries = [f"...{slab}" for slab in slabs]
    accessor_pair: list[str] = []
    synced: list[str] = []
    if cell is not None:
        if binding_path is None:
            entries.append(f"{cell}: {initial}")
            target = f"this.{cell}"
            if server_synced:
                synced.append(cell)
        else:
            target = binding_path
        read, write = accessors
        body = (
            f"const v = {target}; return {bound_read};"
            if binding_path is not None and bound_read is not None
            else f"return {target};"
        )
        accessor_pair = [f"{read}() {{ {body} }}", f"{write}(v) {{ {target} = v; }}"]
    elif binding_path is not None:
        raise ComponentUsageError("scope_literal: a binding_path needs a cell")
    config = config or {}
    synced.extend(config)
    if synced:
        entries.append(_server_sync_entry(synced))
    entries.extend(f"{key}: {value}" for key, value in (fields or {}).items())
    entries.extend(accessor_pair)
    entries.extend(methods)
    entries.extend(f"{key}: {value}" for key, value in config.items())
    return "{" + ", ".join(entries) + "}"


def outlet_target_attrs(component_name: str, outlet: Any) -> dict[str, str]:
    """``{"hx-target": "#outlet_<shell>"}`` for a link that names its region.

    Without ``outlet=``, the shell boosts every internal link towards
    ``[data-bz-outlet]`` (``render/shell.py``) and htmx keeps the FIRST
    outlet in the document. With nested shells that is always the
    outermost: the server therefore re-renders the inner shell AS WELL AS
    the page, whereas the link only changes the page.

    ⚠️ **We take the shell FUNCTION, never its id**, and that is what
    makes the mistake impossible. The id is written ``outlet_<name>``;
    writing it by hand gives a selector that matches nothing, and htmx
    then sends NO request — with no error, no trace.
    """
    if outlet is None:
        return {}
    if not callable(outlet) or not hasattr(outlet, "_bz_layout"):
        raise ComponentUsageError(
            f"{component_name}: ``outlet=`` takes a function decorated "
            f"``@layout``, not {type(outlet).__name__}. It is the shell "
            f"whose region must be replaced."
        )
    return {"hx-target": "#" + outlet_id_for(outlet.__name__)}


def bound_wire_name(bound: Any) -> str | None:
    """The ``name`` a control bound to ``bound`` sends its field under —
    ``Delivery.mode`` / ``Delivery[paris].mode`` — or ``None`` when
    ``bound`` is no state field.

    Two shapes carry a field: a ``ClientBinding`` (``class_name``,
    ``instance_key``) and a server scalar stamped with its ``owner``
    instance (``state/scopes/server._stamp``).
    """
    field = getattr(bound, "field_name", None)
    if not field:
        return None
    cls = getattr(bound, "class_name", None)
    key = getattr(bound, "instance_key", None)
    if cls is None:
        owner = getattr(bound, "owner", None)
        if owner is None:
            return field
        cls, key = type(owner).__name__, getattr(owner, "_key", None)
    return wire_name(cls, key, field)


def own_field(component: Any) -> str | None:
    """The field a control sends on its own: its explicit ``name=``, else
    the one its binding derives. Signed into its action's blob, it is the
    only field that action may write into a state without a form around
    it (:func:`bretzel.server.handlers.writable_fields`)."""
    explicit = component._reactive_values.get("name")
    return explicit if isinstance(explicit, str) else component._derive_field_name()
