"""The components published by INSTALLED packages — and why it is not the
same entry point as the roots to scan.

The missing half
----------------
Since 2026-08-29, a third-party library has its Tailwind classes
compiled: it declares a root in ``bretzel.scan_roots`` and the production
``style.css`` keeps them. But the THEME door stayed closed ::

    Theme(components={"gauge": {...}})
    # ThemeError: no component has this theme key

``server/lifecycle._validate_theme`` judges against
:func:`~bretzel.introspect.theme_vocabulary`, which sweeps the
**framework**'s ``ui.*`` surface only. A ``THEME_KEY`` shipped by a
package was not in it, so the app installing it could not override it —
all it had left was ``classes=`` at the call site, repeated everywhere,
with no cascade and no dark-theme consistency. That is exactly the
difference between "a themed component" and "copied HTML".

Why a DISTINCT entry point
--------------------------
``bretzel.scan_roots`` already names a module, and we could have imported
it to look for :class:`Component` subclasses there. That would have been
a reversal, not an extension: its contract is written in black and white
— "a declared root is a folder READ at startup, **not code that runs**",
and resolution goes through ``find_spec``, which loads nothing. Turning
it into a silent import would change what an author accepted when writing
the line.

Hence two declarations for one package, but two honest contracts: "scan
my files" is not "load my code" ::

    [project.entry-points."bretzel.scan_roots"]
    my-components = "my_components"

    [project.entry-points."bretzel.components"]
    my-components = "my_components"

The second line **imports** the module at startup, and that is the price
to pay: a ``THEME_KEY`` cannot be read without loading the class carrying
it.

Key collisions
--------------
``"gauge"`` is free, ``"card"`` is not. A package publishing a component
under a framework key would make every ``Theme(components={"card": …})``
ambiguous — the app would believe it was styling one and would style the
other. The collision is therefore REFUSED, and the message names both
sides: it is the only moment where one still knows what comes from whom.
"""

from __future__ import annotations

import inspect
from functools import cache
from importlib import import_module, metadata
from typing import Any

#: The entry-point group. Distinct from ``bretzel.scan_roots`` — cf. the
#: module's docstring.
ENTRY_POINT_GROUP = "bretzel.components"


class ThemeKeyCollision(RuntimeError):
    """A package publishes a ``THEME_KEY`` the framework already carries."""


@cache
def third_party_components() -> tuple[type, ...]:
    """The ``Component`` classes published by the installed packages.

    An unusable entry does not bring startup down — the app is not
    responsible for a third party's metadata — but it does not pass in
    silence either: that package's components would stay unthemeable and
    nothing else would say so. Same arbitration as
    ``discovered_source_roots``, whose twin it is.

    Memoised: installation metadata does not change during a process's
    life. ``third_party_components.cache_clear()`` exists for the tests,
    which fabricate entry points.
    """
    from bretzel.components.base import Component

    found: list[type] = []
    for point in metadata.entry_points(group=ENTRY_POINT_GROUP):
        try:
            module = import_module(point.module)
        except Exception as exc:  # a third party breaks, not us
            print(
                f"[bretzel] WARN: the {ENTRY_POINT_GROUP} entry point "
                f"\"{point.name}\" names {point.module!r}, which does not "
                f"import ({type(exc).__name__}).\n"
                "[bretzel]        Its components will not be themeable."
            )
            continue
        for _name, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, Component)
                and obj is not Component
                and getattr(obj, "THEME_KEY", "")
                # A class RE-EXPORTED from bretzel is not published by
                # the package: without this test, a plain ``from bretzel
                # import ui`` at the head of a module would bring in the
                # whole catalogue.
                and not obj.__module__.startswith("bretzel.")
            ):
                found.append(obj)
    # De-duplicated by identity: a package exposing the same class from
    # two modules would declare it twice.
    unique = {id(c): c for c in found}
    return tuple(
        sorted(unique.values(), key=lambda c: (c.THEME_KEY, c.__name__))
    )


def third_party_theme_vocabulary() -> dict[str, dict[str, frozenset[str]]]:
    """``THEME_KEY`` → group → keys, for third-party components.

    Same shape as :func:`~bretzel.introspect.theme_vocabulary` so that
    merging is a plain dictionary update.

    RAISES on a collision with a framework key — cf. the module's
    docstring.
    """
    from bretzel.introspect.components import theme_vocabulary

    framework_keys = theme_vocabulary()
    out: dict[str, dict[str, frozenset[str]]] = {}
    for cls in third_party_components():
        key = cls.THEME_KEY
        if key in framework_keys:
            raise ThemeKeyCollision(
                f"{cls.__module__}.{cls.__qualname__} publishes "
                f"``THEME_KEY = {key!r}``, which the framework already "
                f"carries.\n"
                f"  A ``Theme(components={{{key!r}: …}})`` would become "
                f"ambiguous: the app would believe it was styling one and "
                f"would style the other.\n"
                f"  Prefix the package's key — ``{_suggestion(cls)}`` for "
                f"example."
            )
        out.setdefault(key, {}).update(_groups_of(cls))
    return out


def _suggestion(cls: type) -> str:
    """A plausible prefixed key, so the message is actionable."""
    package = cls.__module__.split(".")[0].replace("_", "-")
    return f"{package}-{cls.THEME_KEY}"


def _groups_of(cls: type) -> dict[str, frozenset[str]]:
    """A ``THEME``'s overridable groups, as the base layer does."""
    theme: dict[str, Any] = getattr(cls, "THEME", {}) or {}
    return {
        group: frozenset(value)
        for group, value in theme.items()
        if isinstance(value, dict)
    }


__all__ = [
    "ENTRY_POINT_GROUP",
    "ThemeKeyCollision",
    "third_party_components",
    "third_party_theme_vocabulary",
]
