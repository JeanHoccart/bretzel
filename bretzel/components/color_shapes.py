"""What the component themes know and the Tailwind scanner does not.

A class that appears literally in no source file never reaches the
compiled ``style.css``. A graded class (``md:gap-6``) is only prefixed at
render, so the production compiler cannot guess it, and the bug shows
**only in production**.

Why this module exists
----------------------

⚠️ The file's name is wider than its contents: colours need nothing here,
since the themes read STEPS (``ring-(--bz-focus)``), which are complete
classes the compiler sees. Only the GRADED half exists
(``dynamic_responsive_classes``).

In dev it does not show — ``@tailwindcss/browser`` scans the live DOM,
so it sees the already-resolved classes. In prod the Tailwind binary
only scans the sources: with no help, it generates none of those rules.

The help is the ``@source inline(...)`` directive produced by
:func:`bretzel.theme.tailwind.generate_safelist_comment`. The safelist
is *derived* from the themes themselves, so it cannot diverge from them. The gate
``tests/consistency/test_no_colour_class_is_assembled_by_hand.py`` covers
the residual risk (a shape built in render code rather than in a
``THEME`` dict, which introspection would not see).

Direction of the dependency: ``theme`` is in the base layer and is not
allowed to import ``components`` (the import-linter contract
*base-independent-of-app*). So it is ``components`` that exposes its
templates, and the assembly at startup (``server.lifecycle``) that
passes them to the generator.
"""

from __future__ import annotations

from typing import Any

from bretzel.components.base.component import Component


def _component_classes() -> set[type]:
    """Every live subclass of :class:`Component`, recursively.

    Deliberately wider than the ``ui`` namespace: internal components
    (leaves of a container, calendar sub-parts…) carry their own
    ``THEME`` without being exposed.

    Real scope: the classes **already imported** at call time.
    ``components/__init__`` imports the framework's catalogue in one go,
    so coverage there is complete (the gate checks it). A user component
    defined after startup — in a function body, in a module imported
    lazily at the first render — arrives too late and is not swept.

    No global registry: we read the live classes at call time, after the
    imports have happened.
    """
    found: set[type] = set()
    stack: list[type] = list(Component.__subclasses__())
    while stack:
        cls = stack.pop()
        if cls in found:
            continue
        found.add(cls)
        stack.extend(cls.__subclasses__())
    return found


def dynamic_responsive_classes() -> tuple[str, ...]:
    """Return responsive classes that a graduated property may emit."""
    tokens: set[str] = set()
    for cls in _component_classes():
        keys = cls.__dict__.get("RESPONSIVE_THEME_KEYS") or ()
        if not keys:
            continue
        # An explicit walk up the MRO rather than a ``cls.THEME``: the
        # declaration can live on a subclass that INHERITS its theme
        # (VStack / HStack inherit Flex's), so reading only the class's
        # ``__dict__`` would miss the table. And attribute access is
        # refused here by ``test_theme_reads_are_resolved``, which guards
        # a RENDER contract (going through ``_resolved_theme()`` so an
        # app's ``Theme(components=…)`` applies) — inapplicable to class
        # introspection, with no instance and no context.
        theme: dict[str, Any] = next(
            (
                found
                for base in cls.__mro__
                if (found := base.__dict__.get("THEME"))
            ),
            {},
        )
        for key in keys:
            table = theme.get(key)
            if not isinstance(table, dict):
                continue
            for value in table.values():
                if isinstance(value, str):
                    tokens.update(value.split())
    return tuple(sorted(tokens))


__all__ = ["dynamic_responsive_classes"]
