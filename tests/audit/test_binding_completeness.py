"""Binding completeness probe — the cheap inner net (no browser).

For every component declaring ``BINDABLE_PROPS``, bind each prop to a
``ClientBinding``, render, and assert a reactive directive actually
references the binding path. A binding that VANISHES (carrier ref not
found + ``emit_attr=False`` on the root) emits nothing — and is caught
HERE, at unit speed, instead of three layers downstream (the visual
IA+photo net, or the user).

Why this exists : ``forward_binding`` (component.py) silently ``continue``s
when a carrier ``bz-ref`` is missing, and the existing carrier-landing
audit only checks that *emitted* directives sit on valid tags — a binding
that emits *nothing* passes it. This probe checks the missing direction :
COMPLETENESS (every bound prop produces a working directive), not just
validity.

Run it (full report)::

    py -m tests.audit.test_binding_completeness

As a regression guard (green now ; fails on any NEW vanished binding)::

    py -m pytest tests/audit/test_binding_completeness.py

⚠️ A "VANISHED" verdict is a POINTER, not an oracle (same discipline as
the vision judge). Naive construction false-positives : an empty composite
(RadioGroup with no Radio), an unrealistic SSR value (``src=""`` → Avatar
renders initials, no <img>), a missing parent context. The CONSTRUCT
registry below feeds each component a realistic construction so the verdict
is trustworthy ; components we can't yet construct faithfully are SKIPPED
with a reason rather than false-flagged.
"""

from __future__ import annotations

import datetime as _dt
import importlib
import pkgutil
from dataclasses import dataclass

import bretzel.components as _comps_pkg
from bretzel.components.base.component import Component
from bretzel.components.data.table import column as _dt_column
from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from bretzel.components import DatatableState as _DatatableState
from bretzel.state.scopes.client import ClientBinding

_PATH = "draft.default.field"
_BOOLISH = ("checked", "disabled", "open", "required", "readonly", "loading",
            "dismissible", "visible", "selected", "active", "multiple",
            "indeterminate")


def _sample(prop: str):
    """A REALISTIC SSR value so the component takes its full render path
    (a degenerate value — empty src, False dismissible — hides the very
    element the binding should land on → false 'vanished')."""
    p = prop.lower()
    if any(k in p for k in _BOOLISH):
        return True
    if "src" in p or "href" in p:
        return "/x.png"
    if p in ("min", "max"):
        return None              # date components override via CONSTRUCT
    if p in ("step", "page", "total_pages", "value_min", "value_max"):
        return 1
    return "x"


def _binding(prop: str) -> ClientBinding:
    return ClientBinding(class_name="draft", instance_key="default",
                         field_name="field", value=_sample(prop))


class _Skip(Exception):
    """Raised by a CONSTRUCT builder when faithful construction isn't wired
    yet (→ reported as SKIP with a reason, never a false 'vanished')."""


# ── CONSTRUCT registry : faithful construction per component ──────────
# Each entry is build(Cls, prop, binding) -> component instance (already
# composed with children / parent context / realistic args). Default
# (absent) = ``Cls(**{prop: binding})``.

def _radio_group(Cls, prop, b):
    from bretzel.components.inputs.radio import Radio
    with Cls(**{prop: b}) as g:
        Radio("a", label="A")
    return g


def _rebind(prop: str, value):
    return ClientBinding(class_name="draft", instance_key="default",
                         field_name="field", value=value)


def _date_build(Cls, prop, b):
    # Calendar/DatePicker date-typed props (value/min/max/month) want a date.
    if any(k in prop for k in ("min", "max", "month", "value")):
        b = _rebind(prop, _dt.date(2024, 1, 1))
    return Cls(**{prop: b})


def _toggle_button(Cls, prop, b):
    # ToggleButton only renders inside a ToggleGroup ``with`` block.
    from bretzel.components.inputs.toggle_group import ToggleGroup
    with ToggleGroup() as g:
        Cls("a", "A", **{prop: b})
    return g


def _progress(Cls, prop, b):
    # Progress value is a float — rebind, give it a max.
    if prop == "value":
        b = _rebind(prop, 50.0)
    return Cls(**{prop: b}, max=100)


def _needs_context(reason):
    def _b(Cls, prop, b):
        raise _Skip(reason)
    return _b


def _navbar_item(Cls, prop, b):
    # NavbarItem only carries its binding inside the real nav chrome :
    # Navbar > NavbarSection > NavbarItem (the section is the positional
    # flex container, the navbar owns the ``current_path`` scope the item's
    # auto-active mode reads). Build the item INSIDE the ``with`` blocks so
    # the parent registers + renders it ; return the Navbar root to render.
    from bretzel.components.navigation.navbar.navbar import Navbar, NavbarSection
    with Navbar() as nav:
        with NavbarSection(side="center"):
            # ``href`` en DÉFAUT, pas en dur : quand c'est ``href``
            # qu'on sonde, la sonde gagne. Sans ce sens, la table
            # levait « multiple values » et le composant sortait du
            # balayage de la gate appelante.
            Cls("Home", **{"href": "/", prop: b})
    return nav


def _sidebar_item(Cls, prop, b):
    # SidebarItem only carries its binding inside the real rail chrome :
    # Sidebar > SidebarSection > SidebarItem (the sidebar owns the
    # ``current_path`` + ``data-open`` scope, the section groups the rows).
    # Build the item INSIDE the ``with`` blocks so the parent renders it ;
    # return the Sidebar root to render.
    from bretzel.components.navigation.sidebar.sidebar import (
        Sidebar,
        SidebarSection,
    )
    with Sidebar() as side:
        with SidebarSection(label="MENU"):
            Cls("Home", icon="home", **{"href": "/", prop: b})
    return side


class _DatatableProbe(_DatatableState):
    """A throwaway query state so the shared builder can construct a
    Datatable. One subclass per table is the component's rule ; this is
    the probe's table."""


CONSTRUCT = {
    "Select": lambda C, p, b: C(**{p: b}, options=[("a", "A")]),
    "Combobox": lambda C, p, b: C(**{p: b}, options=[("a", "A")]),
    "RadioGroup": _radio_group,
    "ToggleGroup": lambda C, p, b: C(**{p: b}, options=[("a", "A"), ("b", "B")]),
    "ToggleButton": _toggle_button,
    "Pagination": lambda C, p, b: C(**{p: b},
                                    **{k: v for k, v in (("total_pages", 10),
                                                         ("value", 1))
                                       if k != p}),
    "Progress": _progress,
    "Calendar": _date_build,
    "DatePicker": _date_build,
    "DateRangePicker": _date_build,
    # Items carry their binding inside their parent nav container — built
    # faithfully INSIDE Navbar/Sidebar > Section > Item so the binding has
    # somewhere to land (the parent owns the current_path scope the item's
    # auto-active mode reads).
    "NavbarItem": _navbar_item,
    "SidebarItem": _sidebar_item,
    # Datatable has no bindable prop (the whole query is server state), so
    # ``p``/``b`` go unused — the entry exists for the SHARED constructor
    # (`tests/consistency/_discovery.py::bz_data_of`), which without it
    # left 14 auto-discovering gates skipping the component entirely
    # ("Datatable non constructible nu : missing argument 'state'").
    # Built in its NON-interactive shape on purpose : an interactive one
    # legitimately refuses to construct outside a @refreshable zone.
    "Datatable": lambda C, p, b: C(
        **{p: b},
        state=_DatatableProbe,
        columns=[_dt_column("name", label="Name")],
        rows=[{"name": "a"}, {"name": "b"}],
        search=False,
    ),
    # ``label`` is an A.2 slot binding (ClientBinding-on-slot is a known
    # framework limit, see todo.md) — not a fresh carrier bug.
    "Link": _needs_context("label/href are A.2 slot bindings (known limit)"),
}


@dataclass
class _Result:
    component: str
    prop: str
    status: str          # PASS | VANISHED | SKIP | CONSTRUCT-ERR
    detail: str = ""


def _discover() -> dict[str, type]:
    found: dict[str, type] = {}
    for mi in pkgutil.walk_packages(_comps_pkg.__path__,
                                    _comps_pkg.__name__ + "."):
        try:
            mod = importlib.import_module(mi.name)
        except Exception:
            continue
        for _nm, obj in vars(mod).items():
            if (isinstance(obj, type) and issubclass(obj, Component)
                    and obj is not Component
                    and getattr(obj, "BINDABLE_PROPS", None)):
                found[obj.__name__] = obj
    return found


def _check(Cls: type, prop: str) -> _Result:
    builder = CONSTRUCT.get(Cls.__name__)
    try:
        with render_isolated():
            comp = (builder(Cls, prop, _binding(prop)) if builder
                    else Cls(**{prop: _binding(prop)}))
            out = serialize(comp.render())
    except _Skip as s:
        return _Result(Cls.__name__, prop, "SKIP", str(s))
    except Exception as e:
        return _Result(Cls.__name__, prop, "CONSTRUCT-ERR",
                       f"{type(e).__name__}: {str(e)[:70]}")
    if _PATH in out:
        return _Result(Cls.__name__, prop, "PASS")
    return _Result(Cls.__name__, prop, "VANISHED",
                   "no directive references the binding path")


def run() -> list[_Result]:
    comps = _discover()
    out: list[_Result] = []
    for name in sorted(comps):
        for prop in comps[name].BINDABLE_PROPS:
            out.append(_check(comps[name], prop))
    return out


# ── Regression guard ─────────────────────────────────────────────────
#
# Known vanished bindings : a (component, prop) that declares itself in
# BINDABLE_PROPS but emits NO reactive directive (the binding degrades to
# a one-time SSR value) — a "soft" binding contract that fails silently.
# REMOVE an entry when you fix it ; the guard then enforces it stays fixed.
#
# EMPTY as of 2026-06-29 : the whole class is closed. The probe found 7
# instances (ToggleButton.disabled, Select.disabled, Banner.dismissible,
# Navbar/SidebarItem.{badge,disabled}) and all were wired reactively — the
# guard now fails the moment ANY new vanished binding ships.
KNOWN_VANISHED: set[tuple[str, str]] = set()


def test_no_new_vanished_bindings() -> None:
    """Completeness guard : every bound BINDABLE_PROP must emit a reactive
    directive. Fails on any NEW vanished binding ; the known-broken ones
    live in ``KNOWN_VANISHED`` until fixed (shrink it as you go)."""
    results = run()
    vanished = {(r.component, r.prop) for r in results if r.status == "VANISHED"}
    new = vanished - KNOWN_VANISHED
    assert not new, (
        "NEW vanished binding(s) — declared in BINDABLE_PROPS but emit no "
        f"reactive directive (carrier missing / emit_attr=False) : {sorted(new)}"
    )
    now_fixed = KNOWN_VANISHED - vanished
    if now_fixed:
        print(f"FIXED (remove from KNOWN_VANISHED): {sorted(now_fixed)}")


def main() -> None:
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    results = run()
    by = lambda s: [r for r in results if r.status == s]
    npass, vanished = by("PASS"), by("VANISHED")
    skip, errs = by("SKIP"), by("CONSTRUCT-ERR")
    total_checked = len(npass) + len(vanished)
    print(f"\n=== binding completeness : {len(npass)}/{total_checked} OK "
          f"({len(skip)} skipped, {len(errs)} construct-err) ===\n")
    if vanished:
        print(f"VANISHED ({len(vanished)}) — binding emits NOTHING "
              "(candidate bugs — verify each) :")
        for r in vanished:
            print(f"  X {r.component}.{r.prop}")
    if skip:
        print(f"\nSKIP ({len(skip)}) — faithful construction not wired :")
        for r in skip:
            print(f"  - {r.component}.{r.prop}  ({r.detail})")
    if errs:
        print(f"\nCONSTRUCT-ERR ({len(errs)}) :")
        for r in errs:
            print(f"  ? {r.component}.{r.prop}  {r.detail}")


if __name__ == "__main__":
    main()


__all__ = ["run", "main"]
