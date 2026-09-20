"""The state fields an app makes **addressable** — the URL as state.

A `PageState` lives in a server-side dictionary indexed by a render uuid,
**fresh on every navigation**. That is why a filter survives neither a
page change nor the back button: back does a real GET, gets a fresh uuid,
and lands on a URL that says nothing about the view.

This module gives the one remedy that fits a server-driven framework:
**declare the fields the URL is authoritative for.**

    class Issues(DatatableState, addressable=True):
        per_page: int = field(default=25)

    # /issues?sort=title&dir=desc&p=3

One line. The names come from the framework — ``DatatableState`` carries
them on its fields (``field(default="", url="sort")``) — and the app only
decides to PUBLISH. To rename, or for a home-made state, the dict
remains:

    class Filters(PageState):
        status: str = field(default="all")
        URL = {"status": "status"}

## Three decisions, and why

**0. Naming and the DECISION are separate.** That is what allows a
one-line opt-in without publishing anything by accident: ``field(url=…)``
only *names*, ``addressable=True`` alone *lights up*. A field the
framework has not named therefore cannot be lit — that is how ``filters``
stays out of the URL by construction, and not by instruction.

**1. Opt-in, never automatic.** The bridge has already met the automatic
version and treated it — rightly — as a leak: ``05_bridge.js`` strips the
client store from navigation GETs so as not to produce
``?ColorScheme.default.mode=dark&HubFilter...``. The fault was not
putting state in the URL, it was putting **everything** in it. A declared
field is a **PUBLIC** field: it goes into the browser history, into the
server logs, and into the ``Referer`` header of the next request. That is
why ``filters`` is addressable in none of the framework's defaults
(decision of 2026-08-29): it is the field most likely to carry sensitive
data.

⚠️ If a filter must **survive** without being published, the URL is not
what you need, the SCOPE is: ``class Issues(DatatableState,
scope="session")`` and it crosses navigations, server-side, exposing
nothing. Measured. No new mechanism, no browser memory to fiddle with.

**2. The URL name is WRITTEN, not derived from the Python name.** Three
reasons: a URL is a public API, so renaming a field would break bookmarks
and shared links; ``?Issues.sort_key=title`` is exactly the form rejected
above; and two tables on one page collide — an explicit name forces a
decision rather than an accident.

**3. The URL is authoritative AT RENDER TIME, and a mutation writes
both.** Since every mutation of a declared field pushes a fresh URL, the
two cannot diverge. The ``page_id`` stops being relevant for those fields
— which is precisely the point.

## What this module does not do

It knows neither the request nor the response: the ``state`` layer sits
below ``render`` and ``server`` in the DAG, and it does not reach back up.
The parameters **arrive by value** (``StateRegistry(url_params=…)``, like
``page_id`` and ``session_id`` before them), and the pushed URL is composed
by the caller. This file carries only the contract and the two
conversions.
"""

from __future__ import annotations

from typing import Any

from bretzel.core.errors import BretzelError
from bretzel.state.fields.descriptor import MISSING

#: "this field has no default" — distinct from ``None``, which IS a
#: legitimate default and must therefore disappear from the URL like the
#: others.
_NO_DEFAULT: Any = object()

__all__ = [
    "AddressableFieldError",
    "addressable_fields",
    "apply_url_params",
    "collect_url_params",
    "would_publish",
]


class AddressableFieldError(BretzelError):
    """Invalid ``URL`` declaration, or two states claiming the same name."""


def _default_of(cls: Any, field_name: str) -> Any:
    """The field's declared default, or ``_NO_DEFAULT`` if it has none."""
    fld = cls._all_fields().get(field_name)
    if fld is None:
        return _NO_DEFAULT
    if fld.default_factory is not None:
        return fld.default_factory()
    default = getattr(fld, "default", _NO_DEFAULT)
    return _NO_DEFAULT if default is MISSING else default


def addressable_fields(cls: type) -> dict[str, str]:
    """``{field name: parameter name}`` declared by ``cls``.

    Empty — therefore inert — for any class that declares nothing, which
    is the default across the whole framework.

    Raises on a declaration that cannot work, rather than letting it
    through: a non-existent field name would produce no render error,
    just a URL that does nothing — the failure mode that costs the most
    to diagnose.
    """
    # Two sources, in this order — the second can RENAME the first.
    #
    #   1. ``addressable=True`` on the class lights up every field
    #      carrying a ``field(url="…")``. That is the one-line opt-in:
    #      the naming comes from the framework, the decision to publish
    #      comes from you.
    #   2. ``URL = {field: name}`` renames, adds, or stands alone when the
    #      class declared no per-field names.
    #
    # A field WITHOUT ``url=`` is never lit by ``addressable=True`` —
    # that is what keeps ``filters`` out of the URL without a line of
    # documentation having to say so: the framework gave it no name, so
    # there is nothing to light up.
    if getattr(cls, "__addressable__", False):
        return would_publish(cls)
    declared = _declared_map(cls)
    return _validated(cls, declared) if declared else {}


def would_publish(cls: type) -> dict[str, str]:
    """What ``addressable=True`` would publish — VALIDATED, therefore true.

    The same read as :func:`addressable_fields`, with the switch forced
    ON. Serves whoever must show the naming of a class that does not
    publish yet (``describe``, and its "off" line).

    ⚠️ **It validates.** The version that merely read the ``url=`` lived
    an hour: on a state naming a ``dict`` field, it answered
    "``addressable=True`` would publish filters→f" — advice that RAISES
    as soon as you follow it, since that is exactly what the structure
    guard refuses. A card describing an impossible declaration is worse
    than a mute one.
    """
    merged = {**_named_map(cls), **_declared_map(cls)}
    return _validated(cls, merged) if merged else {}


def _named_map(cls: Any) -> dict[str, str]:
    """The fields the framework has NAMED — the naming, not the decision."""
    return {
        name: fld.url
        for name, fld in cls._all_fields().items()
        if getattr(fld, "url", None)
    }


def _declared_map(cls: Any) -> dict[str, str]:
    """The class's ``URL = {…}``, whose SHAPE is checked here.

    The check lives in the reader and not in its two callers: a
    malformed declaration must speak as clearly to whoever publishes as
    to whoever only asks what would be published.
    """
    declared = getattr(cls, "URL", None)
    if not declared:
        return {}
    if not isinstance(declared, dict):
        raise AddressableFieldError(
            f"{cls.__name__}.URL must be a dict {{field: URL name}}, not "
            f"a {type(declared).__name__}. The URL name is written — it is "
            f"not derived from the Python name, because a URL is a public "
            f"API that a field rename must not break."
        )
    return dict(declared)


def _validated(cls: Any, declared: dict[str, str]) -> dict[str, str]:
    """The same guards, whatever the source of the declaration.

    Extracted so that ``addressable=True`` and ``URL = {…}`` cannot
    diverge: an unknown field, an empty name, an internal collision or a
    non-serialisable structure are refused on both sides.

    ⚠️ Its messages no longer say "``X.URL`` declares": since it also
    serves :func:`would_publish`, the fault may come from a
    ``field(url=…)`` and pointing at the ``URL`` dict would send the
    reader looking for a line that does not exist.
    """
    # ``_all_fields`` is the canonical enumeration of a ``State`` — the
    # one the registry diffs. Guessing again through ``dir()`` would pick
    # up ``errors`` / ``to_dict`` and accept ``URL = {"to_dict": …}``.
    known = set(cls._all_fields())

    seen: dict[str, str] = {}
    for field_name, param in declared.items():
        if field_name not in known:
            raise AddressableFieldError(
                f"{cls.__name__} names {field_name!r} for the URL, which is "
                f"not a field of this state. Known fields: "
                f"{sorted(known)}. Without this guard, the URL would "
                f"simply do nothing — without raising, without a trace."
            )
        if not isinstance(param, str) or not param:
            raise AddressableFieldError(
                f"{cls.__name__}: the URL name of {field_name!r} must be a "
                f"non-empty parameter name, not {param!r}."
            )
        if param in seen:
            raise AddressableFieldError(
                f"{cls.__name__}: {field_name!r} and {seen[param]!r} both "
                f"claim the parameter {param!r}. The last one would "
                f"overwrite the other silently."
            )
        default = _default_of(cls, field_name)
        if isinstance(default, (dict, list, set, tuple)):
            raise AddressableFieldError(
                f"{cls.__name__} names {field_name!r} for the URL, whose "
                f"value is a {type(default).__name__}. A query carries only "
                f"strings, and no format exists for this one yet: the URL "
                f"value would replace the structure with a string, and the "
                f"component's first `.get()` would break — WITHOUT the "
                f"declaration having reported anything. That is the case of "
                f"`filters` on a datatable. It will become declarable again "
                f"once an encoding is chosen; in the meantime, address the "
                f"SCALAR fields (sort, page, search) and let the filter live "
                f"in the state."
            )
        seen[param] = field_name
    return dict(declared)


def _coerce(current: Any, raw: str) -> Any:
    """The URL parameter, brought back to the field's type.

    A query has only strings. The type is read from the CURRENT value
    rather than from the annotation: that is what an already-built state
    has to hand, and it follows a changed default without asking the
    class again.

    Best-effort and never raising — a URL is typed by a human and
    fiddled with by robots. A ``?p=banana`` must render the page, not a
    500; the unreadable value is ignored, so the default holds.
    """
    if isinstance(current, bool):
        low = raw.strip().lower()
        if low in ("1", "true", "yes", "on"):
            return True
        if low in ("0", "false", "no", "off"):
            return False
        return current
    if isinstance(current, int):
        try:
            return int(raw)
        except ValueError:
            return current
    if isinstance(current, float):
        try:
            return float(raw)
        except ValueError:
            return current
    return raw


def apply_url_params(instance: Any, params: dict[str, str]) -> list[str]:
    """Seed the declared fields from ``params``. Returns the names touched.

    **Absent = nothing is touched.** That is what makes the mechanism
    work on an action, whose URL carries no query: the state keeps what
    it had, the handler mutates it, and the caller pushes the new URL.

    ⚠️ To be called BEFORE the registry's reference snapshot, otherwise
    the seeding reads as a mutation: the state would leave ``dirty`` and
    push a URL on the first render, with nothing having moved.
    """
    if not params:
        return []
    touched: list[str] = []
    for field_name, param in addressable_fields(type(instance)).items():
        if param not in params:
            continue
        current = getattr(instance, field_name)
        value = _coerce(current, params[param])
        if value != current:
            setattr(instance, field_name, value)
        touched.append(field_name)
    return touched


def collect_url_params(instances: list[Any]) -> dict[str, str]:
    """``{parameter: value}`` for every declared field of ``instances``.

    **A field at its default value does not appear.** That is the exact
    counterpart of the read ("absent = nothing is touched"): both
    directions agree, so a round trip through the URL is faithful. And it
    avoids a table you have only just sorted showing
    ``?sort=name&dir=asc&p=1&q=`` — three parameters out of four to say
    "as usual". A URL must be readable.

    Raises when two states on the SAME page claim the same parameter. The
    check is here — so per request — and not in a module-level table of
    reserved names: a mutable global registry is forbidden (anti-rule 2),
    and above all the collision is only a fault if the two states
    REALLY meet.
    """
    out: dict[str, str] = {}
    owner: dict[str, str] = {}
    for instance in instances:
        cls = type(instance)
        for field_name, param in addressable_fields(cls).items():
            if param in owner and owner[param] != cls.__name__:
                raise AddressableFieldError(
                    f"{cls.__name__} and {owner[param]} both claim the URL "
                    f"parameter {param!r} on the same page. One would "
                    f"overwrite the other on every navigation. Give one of "
                    f"the two a distinct name in its ``URL = {{…}}``."
                )
            owner[param] = cls.__name__
            value = getattr(instance, field_name)
            if value == _default_of(cls, field_name):
                out.pop(param, None)
                continue
            out[param] = "" if value is None else str(value)
    return out
