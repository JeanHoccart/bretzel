"""Shared V3 client wiring for input components.

The write-only imperative API (``.set(value)`` / ``.clear()`` /
``.toggle()``) dispatches DOM CustomEvents at the real form control
(by id) when no :class:`ClientBinding` is in play. The control catches
them via ``bz-on:bz-*`` listeners that mutate the element directly and
re-fire the native sync events so ``bz-model`` (binding case) AND any
user ``on_input=`` / ``on_change=`` handler observe the change.

Two flavours, one per control family :

- :func:`value_command_listeners` — ``<input>`` / ``<textarea>``-shaped
  controls whose payload lands in ``$el.value`` (Input, Textarea ;
  future Select / NumberInput / Slider ports reuse it, overriding
  ``sync_events`` when their native event shape differs).
- :func:`checked_command_listeners` — boolean toggles whose payload
  lands in ``$el.checked`` (Checkbox, Switch).

``bz-on:`` listeners need NO enclosing scope — the runtime falls back
to the root scope (bare names resolve to JS globals, and these
expressions only touch ``$el`` / ``$event``).

Group-internal module (``inputs/``). The old anti-rule 5 ("no
cross-group import") was **relaxed on 2026-06-23** to "no cycles":
another group MAY import from here as long as it introduces no cycle
(cf. CLAUDE.md anti-rule 5). In practice these helpers stay
input-specific; if a shared need emerges, promoting it into
``components/base`` remains the right reflex — not out of prohibition,
but because that is the common base layer.
"""

from __future__ import annotations

import datetime as _dt
import json
from typing import Any

from bretzel.components.base import ComponentDefinitionError
from bretzel.components.base._wiring import server_sync_marker
from bretzel.core.tree import Element


def add_local_value_scope(
    component: Any,
    input_attrs: dict[str, Any],
    *,
    prop: str,
    ssr_value: Any,
) -> bool:
    """Give an INTERACTIVE, LOCAL simple input an internal value scope.

    The "rich" inputs (NumberInput / Slider / Select / Combobox) hold
    their value in a ``bz-data`` scope signal — so a user's edit survives
    a refresh of an enclosing ``@refreshable`` (``scope.absorb`` keeps the
    signal across the idiomorph morph). The "simple" inputs (Switch /
    Checkbox / Input / Textarea) historically held their value in the
    native DOM property (``.checked`` / ``.value``), which idiomorph
    clobbers back to the SSR value on morph — so a local toggle / typed
    text reset on every refresh.

    This brings the simple family into the SAME model : a tiny scope
    signal for the value, two-wayed via ``bz-model``, that absorb
    preserves. The scope lives on the ``<input>`` itself (it already
    carries the stable ``id`` / ``bz-id``), so wrapper-rooted controls
    (Switch / Checkbox) keep a scope-free root.

    Gated (the user's "seulement si interactif" rule) :

    - **ClientBinding** for ``prop`` → no-op : the value lives in
      ``$bz._store``, which survives swaps natively.
    - **Not interactive** (no user ``on_*`` handler) → no-op : a purely
      static input stays a lean native wrapper, no scope weight.
    - **Local + interactive** → emit ``bz-data="{<prop>: <ssr>}"`` +
      ``bz-model="<prop>"``. ``_serverSync`` re-adopts the value ONLY
      when server-backed (``value=state.field`` carries a ``field_name``)
      — a local literal keeps its client value across an unrelated
      refresh.

    ONLY the value rides this. Other internal UI state (a Select's open
    flag, a Combobox query) is never given a persistent / synced signal —
    it stays client-owned via absorb. Returns ``True`` when a scope was
    added (the caller skips its ``_bind_x_model`` literal fallback).
    """
    if component._binding_metadata.get(prop) is not None:
        return False  # ClientBinding : store-backed, survives natively.
    if not component._event_attrs:
        return False  # not interactive → keep it a thin native wrapper.
    # A single rule — cf. ``Component._value_server_backed``. It also
    # covers the binding mode (redundant here: we bailed above) and the
    # ``[state.field]`` case, which reading the ``field_name`` directly
    # missed.
    sync = server_sync_marker(
        prop, enabled=component._value_server_backed(prop)
    )
    input_attrs["bz-data"] = (
        "{" + f"{prop}: {json.dumps(ssr_value)},{sync}" + "}"
    )
    input_attrs["bz-model"] = prop
    return True


def force_boolean_form_vals(
    input_attrs: dict[str, Any], *, name: str | None,
) -> None:
    """Make a server-bound checkbox/switch always transmit its boolean.

    The classic HTML gotcha : an **unchecked** checkbox submits *nothing*.
    So a server round-trip (``hx-post`` fired on ``change``) loses the
    ``false`` entirely — the handler never sees the field, the stale
    ``True`` survives, and the refresh snaps the control back on.

    Fix : force the live ``.checked`` onto every request via
    ``hx-vals="js:{<name>: event.target.checked}"``. HTMX evaluates it at
    send time and **overrides** the native value (absent when unchecked),
    so checked→``true`` / unchecked→``false`` both ride the POST. The
    server's bool coercion turns the string back into a real bool.

    Mutates ``input_attrs`` in place. No-op unless there's a server
    action (``hx-post``) AND a form ``name``. Merges with any existing
    ``hx-vals`` (the ``_args`` blob a partial-bound handler rides) by
    rebuilding it as one ``js:`` object literal.

    Call sites gate this themselves : skip when ``checked=`` is a
    :class:`ClientBinding` (the bridge already ships the client store,
    ``false`` included) and when an explicit ``value=`` is set (value-list
    semantics — there, *unchecked = absent* is the correct HTML).
    """
    if not name or "hx-post" not in input_attrs:
        return
    bool_expr = f"{json.dumps(name)}: event.target.checked"
    existing = input_attrs.get("hx-vals")
    if existing:
        try:
            data = json.loads(existing)
        except (TypeError, ValueError):
            data = {}
        static = ", ".join(
            f"{json.dumps(k)}: {json.dumps(v)}" for k, v in data.items()
        )
        merged = f"{static}, {bool_expr}" if static else bool_expr
        input_attrs["hx-vals"] = "js:{" + merged + "}"
    else:
        input_attrs["hx-vals"] = "js:{" + bool_expr + "}"


def false_companion_input(name: str, *, disabled: bool = False) -> Element:
    """The other half of "an unticked box still sends its false".

    :func:`force_boolean_form_vals` covers the request the box pulls
    ITSELF (its ``on_change``): htmx evaluates its ``hx-vals`` at send
    time and overrides the native value. It only exists if there is an
    ``hx-post`` on the input, and it reads ``event.target.checked``.

    This function covers the other request: the **parent form's
    submission**, where the event does not come from the box and where
    ``event.target.checked`` designates nothing. A hidden field of the
    same ``name`` carrying ``"false"``, placed BEFORE the box: both
    leave when it is ticked, and the server keeps the last value
    (``FormData`` like ``parse_qsl``: the last one wins).

    Both are necessary — neither covers the other's case.

    ⚠️ It is NOT a :func:`hidden_carrier_attrs`. A carrier reflects a
    live value: it has a ``bz-ref`` by which the scope finds it again
    and a ``bz-attr:value`` that keeps it up to date. This one is inert
    — its value is the constant ``"false"``, nobody reads it on the
    client side, and giving it the carrier's four invariants would give
    it two attributes designating nothing (the defect for which
    ``dropzone`` is declared in skeleton debt).

    ⚠️ ``disabled`` propagates, and forgetting it INVERTS the bug. A
    disabled control submits nothing — neither htmx (``shouldInclude``
    skips an ``elt.disabled``) nor the browser. A companion left active
    would then be the ONLY one to leave, and a disabled-but-true setting
    would be written ``False`` at the first save: exactly the failure
    this function exists to prevent, inverted.

    Measured on 2026-08-19 on the CRM's Settings screen: a ``ui.switch``
    with no ``on_change`` unticked itself on screen and came back ticked
    after "Save".
    """
    attrs: dict[str, Any] = {"type": "hidden", "name": name, "value": "false"}
    if disabled:
        attrs["disabled"] = True
    return Element(tag="input", attrs=attrs, children=())


def _sync_events_js(events: tuple[str, ...]) -> str:
    """JS statements re-firing the native events after a mutation."""
    return "; ".join(
        f"$el.dispatchEvent(new Event('{e}', {{bubbles: true}}))"
        for e in events
    )


def value_command_listeners(
    *,
    sync_events: tuple[str, ...] = ("input", "change"),
) -> dict[str, str]:
    """``bz-on:bz-set`` for ``$el.value`` carriers.

    ``bz-on:bz-set`` catches the CustomEvent dispatched by ``.set(value)``,
    writes ``$event.detail.value`` into ``$el.value``, then fires the
    synthetic ``sync_events``. ``.clear()`` is sugar for ``.set("")`` — it
    dispatches the same ``bz-set`` event with an empty value, so no
    dedicated ``bz-clear`` listener exists.

    The default ``("input", "change")`` matches the native sequence a
    user typing into a text input would produce — which is also what
    the runtime's ``bz-model`` listens for on text controls.
    """
    sync_js = _sync_events_js(sync_events)
    return {
        "bz-on:bz-set": f"$el.value = $event.detail.value; {sync_js}",
    }


def checked_command_listeners() -> dict[str, str]:
    """``bz-on:bz-toggle`` / ``bz-on:bz-set`` for ``$el.checked`` toggles.

    Fires a single synthetic ``change`` after the flip — the native
    event a real click on a checkbox produces, and the one the
    runtime's ``bz-model`` listens for on checkbox-type controls.
    """
    sync_js = _sync_events_js(("change",))
    return {
        "bz-on:bz-toggle": f"$el.checked = !$el.checked; {sync_js}",
        "bz-on:bz-set": f"$el.checked = !!$event.detail.value; {sync_js}",
    }


def date_to_iso(value: Any, *, owner: str) -> str:
    """Coerce a date-ish prop value to an ISO ``YYYY-MM-DD`` string.

    ``None`` → ``""`` (empty field) ; a ``date`` → its ISO form ; a
    string passes through (already normalised, or the caller's SSR
    seed). Anything else is a usage error, raised with ``owner`` in the
    message so the author sees WHICH component rejected the value.

    Single-sourced for the date family (Calendar, DatePicker,
    DateRangePicker), which each carried a byte-identical private copy
    differing only in that message (audit F50) — three copies of the
    same coercion drifting independently.
    """
    if value is None:
        return ""
    if isinstance(value, _dt.date):
        return value.isoformat()
    if isinstance(value, str):
        return value
    raise ComponentDefinitionError(
        f"{owner} value must be date / None / str, "
        f"got {type(value).__name__}: {value!r}"
    )
