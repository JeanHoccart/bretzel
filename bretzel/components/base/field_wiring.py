"""How a field reaches its carriers: handlers, the hidden input, ARIA, and value changes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.base.overlay_wiring import ROOT_DISPATCHED_EVENTS
from bretzel.runtime import (
    BZ_ATTR_PREFIX,
    BZ_ON_PREFIX,
    DATA_BZ_SIG,
    DATA_BZ_TS,
)


def change_emit_effect(value_expr: str) -> str:
    """``bz-effect`` body that fires ``change`` on a hidden input.

    Runs in directive context (``$el`` / ``$nextTick`` injected, unlike a
    bz-data method body), re-evaluating ``value_expr`` on every state tick.
    Bootstraps quietly — the first run only records the baseline, so the
    SSR→hydration handoff never fires a phantom change ; a genuine change
    dispatches a bubbling ``change`` so the relocated ``hx-post`` /
    ``bz-on:change`` handler on the same input fires with a populated
    FormData. ``$nextTick`` lets the runtime flush ``bz-attr:value`` onto
    the DOM input BEFORE HTMX serialises it.

    Shared by every value-holding control that relocates its change wiring
    onto a hidden input. The population is NOT copied here; it is read in
    ``tests/consistency/test_a_relocated_change_reaches_its_carrier.py``,
    which DISCOVERS it. ``base/`` is importable by all, so the single
    source lives here.

    A value the SERVER wrote (``resyncScopes`` adopting a re-rendered
    value, ``$bz._serverWriting``) is a new baseline, never a ``change``:
    a select a morph turns into another one at the same place would post
    the server's value back to the old action — a 403.
    """
    return (
        f"((v) => {{ "
        f"if ($el._bzLast === undefined || $bz._serverWriting) {{ $el._bzLast = v; }} "
        f"else if (v !== $el._bzLast) {{ $el._bzLast = v; "
        f"$nextTick(() => $el.dispatchEvent("
        f"new Event('change', {{bubbles: true}}))); }} "
        f"}})({value_expr})"
    )


# ── Server-action wire attrs — the ONE definition ────────────────────
# The native-HTMX bundle ``emit_attrs`` stamps on a component root for a
# callable ``on_change=`` handler : ``hx-post`` + ``hx-trigger`` +
# ``hx-target`` + ``hx-swap`` + optional ``hx-vals`` + the HMAC stamps
# ``data-bz-sig`` / ``data-bz-ts``. Value-holding controls whose root
# carries no ``name`` / ``value`` (Accordion, Pagination, Tree, Tabs,
# Select, Combobox, ToggleGroup, Slider, NumberInput, Calendar) relocate
# this bundle onto a hidden ``<input>`` so the dispatched FormData is
# non-empty (cf. traps.md § "Un event déclaré doit partir du bon élément").
#
# ``DATA_BZ_TS`` MUST travel with ``DATA_BZ_SIG`` : the HMAC v2 signature
# is computed over ``action_id|args|render_ts`` and the bridge reads the
# ts off ``closest("[data-bz-sig]")`` — i.e. the SAME element as the sig.
# Relocating the sig without the ts leaves the ts on the (now
# handler-less) root, so the bridge forwards an empty ``X-Bz-Ts`` and
# every POST 403s. This bit the framework once already : at the HMAC-v2
# rollout four component-LOCAL copies of this tuple missed ``data-bz-ts``.
# There are now NO component-local copies — every value-holding control imports
# ``SERVER_ACTION_ATTRS`` from here, so the sig+ts couple can only change
# in one place. Guarded by ``tests/consistency/test_action_wire_attrs.py``.
SERVER_ACTION_ATTRS: tuple[str, ...] = (
    "hx-post",
    "hx-trigger",
    "hx-target",
    "hx-swap",
    "hx-vals",
    DATA_BZ_SIG,
    DATA_BZ_TS,
)


def trigger_event(attrs: Mapping[str, Any]) -> str:
    """The EVENT ``hx-trigger`` serves, without its modifiers.

    ``action_attrs`` writes ``hx-trigger`` in the form
    ``"<event> [modifier] [from:#id]"`` — the modifier coming from a
    ``debounce=`` (``delay:300ms``) or a ``throttle=``. **The event is the
    first word, never the whole string.**

    Why this reader exists
    ----------------------
    A relocation site that compares the WHOLE STRING to an event name
    (``== "change"``, ``in ("focus", "blur")``) or, worse, looks for a
    substring in it (``"change" in trigger``) fails as soon as a
    ``debounce=`` is set — and each site fails DIFFERENTLY:

    ===================================  ==================================
    ``ui.combobox(on_change=, debounce=)``   the popped bundle is re-set
                                             nowhere → ``hx-post``
                                             **gone**, handler dead
    ``ui.toggle_group(…)`` likewise          bundle left on the root, which
                                             does not fire ``change`` →
                                             handler dead
    ``ui.file_upload(on_focus=, …)``         same on the focusable wrapper
    Select / Slider / the 4 pickers          modifier overwritten → the
                                             requested ``debounce=``
                                             **silently lost**
    ===================================  ==================================

    And the substring test was wrong the other way round too:
    ``"change" in "month_change"`` is true, so the day Calendar adopted
    :func:`relocate_handlers`, its ``on_month_change`` would leave
    on the value carrier with a trigger rewritten to ``change``.

    Gated by ``tests/consistency/test_trigger_modifiers_survive.py``.
    """
    return str(attrs.get("hx-trigger", "")).split(" ", 1)[0]


def retrigger(trigger: str, event: str) -> str:
    """Rename an ``hx-trigger``'s event while KEEPING its modifiers.

    Calendar renames ``month_change`` to the kebab CustomEvent
    ``month-change``; rewriting the whole string would throw away the
    ``delay:`` that ``debounce=`` had put in it.
    """
    _, separator, modifiers = str(trigger).partition(" ")
    return event + separator + modifiers


#: ``dispatch=`` by default: "the same expression as the value". A string
#: impossible to write by accident, rather than a ``None`` that would mean
#: two things ("by default" and "certainly not").
_SAME_AS_VALUE = "\x00same-as-value"


def hidden_carrier_attrs(
    value_expr: str,
    *,
    initial: Any = "",
    ref: str = "bzhidden",
    dispatch: str | None = _SAME_AS_VALUE,
) -> dict[str, Any]:
    """The SKELETON of a value-carrying ``<input type="hidden">``.

    A ``<div>`` carries neither ``name``/``value`` nor a native
    ``change``. Components whose root is not a form control therefore set
    a hidden input that does both — 12 sites in 11 files.

    This helper renders the **five invariant attributes**:

    - ``type="hidden"``;
    - ``bz-ref`` — how the scope finds the carrier again;
    - ``value`` — the SSR value, so the first POST leaves correct even
      before the runtime has booted;
    - ``bz-attr:value`` — the reactive binding that keeps it up to date;
    - ``bz-effect`` — :func:`change_emit_effect`, **the dispatcher
      without which everything above is mute**.

    The dispatcher is acquired, not left to the caller
    --------------------------------------------------
    The components that dispatch from the runtime (Slider, Calendar,
    Dropzone) write their skeleton by hand, declared in
    ``_SKELETON_DEBT``; they are not callers of this helper.

    The carrier relocates the ``hx-post`` bundle of a server
    ``on_change=`` — but a hidden input never fires ``change`` by itself,
    and a programmatic write of ``.value`` emits no event. Forgetting the
    ``bz-effect`` is therefore an INERT control, with no error and no
    warning.

    Hence the default: the dispatch is **acquired**, and one refuses it
    explicitly (``dispatch=None``) or sets it on another expression
    (``dispatch=<expr>``, ToggleGroup's case, whose posted value and
    observed value differ). An opt-out is read back; an opt-in is
    forgotten.

    ⚠️ **``name`` and ``required``, though, stay with the caller.**

    ``name`` is the important case: sticking a default ``name="value"``
    on a ``Tabs`` or an ``Accordion`` would inject a **stray field into
    every enclosing form**. A Tabs is not a form control — it has a
    ``name`` only if the caller wants one. It is a LEGITIMATE variance,
    and a ``hidden_carrier_input`` that uniformised it would uniformise a
    bug. ``required`` concerns only form controls.

    Gated by ``tests/consistency/test_hidden_carrier_skeleton_is_shared.py``
    (the skeleton comes from here) and
    ``tests/consistency/test_a_relocated_change_reaches_its_carrier.py``
    (no mute carrier receives a server action) — the second also covers
    the four hand-written carriers, out of reach of this default.
    """
    attrs: dict[str, Any] = {
        "type": "hidden",
        "bz-ref": ref,
        "value": initial,
        f"{BZ_ATTR_PREFIX}value": value_expr,
    }
    if dispatch is not None:
        attrs["bz-effect"] = change_emit_effect(
            value_expr if dispatch == _SAME_AS_VALUE else dispatch
        )
    return attrs


#: What names, describes and validates a control: a screen reader reads it
#: on the FOCUSABLE element only. :func:`relocate_aria` moves these from a
#: layout wrapper onto that element.
ARIA_OF_THE_FOCUSABLE: tuple[str, ...] = (
    "aria-labelledby",
    "aria-describedby",
    "aria-invalid",
    "aria-required",
)


def relocate_aria(
    root_attrs: dict[str, Any],
    focusable: dict[str, Any],
    *,
    takes_required: bool = True,
) -> None:
    """Move what ``ui.form_field`` stamped on a wrapper root onto ``focusable``.

    ``takes_required=False`` for a focusable whose role has no
    ``aria-required`` (``button``, ``slider``): the attribute is dropped,
    the form control that carries the value keeps the real ``required``.
    """
    for aria in ARIA_OF_THE_FOCUSABLE:
        if aria in root_attrs:
            value = root_attrs.pop(aria)
            if takes_required or aria != "aria-required":
                focusable[aria] = value


def keep_own_name(attrs: dict[str, Any], element_id: str) -> None:
    """Keep an element's own name next to the label of its field.

    ``aria-labelledby`` replaces ``aria-label`` and the element's text. When
    one label covers several elements (the two ends of a range), or an
    element whose text says what it does, the id of the element itself
    follows the label's: « Period, Start ». No label, nothing changes.
    """
    if "aria-labelledby" in attrs:
        attrs["id"] = element_id
        attrs["aria-labelledby"] = f"{attrs['aria-labelledby']} {element_id}"


def relocate_handlers(
    root_attrs: dict[str, Any],
    routes: Mapping[str, dict[str, Any] | tuple[dict[str, Any], str]],
    *,
    client_stays: tuple[str, ...] = (),
) -> None:
    """Move each event's handlers onto the element where it really fires, **in place**.

    ``emit_attrs`` sets every handler on the root, and the root of a rich
    component is a ``<div>``: it holds neither ``name`` nor ``value``, and
    never receives ``focus``. ``routes`` says where each event goes::

        relocate_handlers(root_attrs, {
            "change": hidden,               # the value the form data reads
            "focus": trigger,               # the only focusable element
            "search": (search, "input"),    # fired under another name
        })

    A target is the attrs of the element, filled in place; a pair
    ``(attrs, name)`` also renames the event, for one the DOM fires under
    another name. **An event absent from the table stays on the root**, where
    ``open`` / ``close`` are dispatched.

    Both shapes of a handler take the same road: the client string
    (``bz-on:<event>``) and the server bundle, picked by the event
    ``hx-trigger`` really names (:func:`trigger_event`), its ``debounce=``
    modifier intact. Moved one by one, a callable ``on_focus`` left on the
    hidden input with the ``change``, and ran at every drag.

    ``client_stays`` keeps a client string on the root for an event that
    bubbles up to it: no carrier needs to exist for a string handler.

    A bundle that leaves for an element other than the value carrier brings
    the field's values along: a handler on a field gets the field, every
    event.
    """
    if misrouted := ROOT_DISPATCHED_EVENTS & routes.keys():
        raise ComponentUsageError(
            f"relocate_handlers cannot move {sorted(misrouted)}: the runtime "
            f"dispatches them on the root, a listener anywhere else never fires."
        )
    server_event = trigger_event(root_attrs)
    for event, route in routes.items():
        target, fired_as = route if isinstance(route, tuple) else (route, event)
        client_key = f"{BZ_ON_PREFIX}{event}"
        if client_key in root_attrs and event not in client_stays:
            target[f"{BZ_ON_PREFIX}{fired_as}"] = root_attrs.pop(client_key)
        if event != server_event or "hx-post" not in root_attrs:
            continue
        bundle = {a: root_attrs.pop(a) for a in SERVER_ACTION_ATTRS if a in root_attrs}
        if fired_as != event:
            bundle["hx-trigger"] = retrigger(bundle["hx-trigger"], fired_as)
        target.update(bundle)
        leaves_the_field = event != "change" and "change" in routes and target is not root_attrs
        if leaves_the_field and "id" in root_attrs:
            from bretzel.components.base.events import fields_of

            target.setdefault("hx-include", fields_of(root_attrs["id"]))


def activate_keydown(action_js: str) -> str:
    """Enter / Space activate a NON-native element.

    A ``<button>`` gets keyboard activation for free from the browser. A
    ``<div role="button">`` / ``<tr role="button">`` / ``<div
    role="treeitem">`` gets **nothing**: without this handler, the element
    is reachable with Tab and completely inert at the keyboard.

    Two parts of this guard are FUNCTIONAL, not cosmetic:

    - ``'Spacebar'``, the old key name (IE, old Firefox): without it,
      those browsers do not activate on Space;
    - the **target guard** ``$event.target === $el``. Without it, a
      keystroke on a CHILD control bubbles up to the parent and activates
      it too — a Space on a button nested in a tree node would fire the
      node.

    The helper takes the correct superset: the three key names and the
    guard. ``action_js`` is the component's gesture — ``$el.click()`` to
    delegate to its own ``hx-trigger``, a scope call, or inlined JS.
    """
    return (
        "if ($event.target === $el && ($event.key === 'Enter' "
        "|| $event.key === ' ' || $event.key === 'Spacebar')) "
        f"{{ $event.preventDefault(); {action_js} }}"
    )


def coerce_index(
    value: Any, *, default: int = 0, minimum: int | None = None
) -> int:
    """The SSR value of a driven index — best effort, never an exception.

    Three components carry the same "bounded index" archetype —
    ``Pagination``, ``Stepper``, ``Carousel``, all three
    ``IMPERATIVE = ("set", "next", "prev")`` — and share this conversion.

    Why a tolerant conversion and not a cast: **the value crosses a form
    data**. The hidden input serialises it, so it comes back as a STRING
    (``"2"``), and a carousel driven by a binding can receive it empty.
    The FINE bounding, though, is not here: it lives in the scope methods,
    the only place that knows the live value and the real bound (the
    number of pages, the track's geometry). Here we only produce a
    reasonable SSR starting point.

    - ``default``: what an absent or unreadable value is worth — ``0`` for
      a 0-based index, ``1`` for a pagination.
    - ``minimum``: optional floor, for the 0-based indices that must never
      go negative. ``None`` = no floor (pagination lets its ``setActive``
      bound it).
    """
    if value is None:
        return default
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    return result if minimum is None else max(minimum, result)
