"""User-facing theme configuration dataclasses.

Two small frozen records exposed at the top level of
:mod:`bretzel.theme` :

- :class:`IconConfig` — default icon set, style, sizing.
- :class:`ScrollbarConfig` — width + colors for the synthesised
  scrollbar CSS rules.

Lifted into their own module to break the circular shape that
otherwise forms when ``css.py`` (a consumer) and ``__init__.py``
(the re-exporter) need to know about them.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IconConfig:
    """Defaults consumed by the ``ui.icon(...)`` component.

    - ``default_set`` : the iconify set name used when an icon is
      passed without an explicit ``<set>:<name>`` prefix.
    - ``default_style`` : optional iconify style modifier (``outline``
      / ``solid`` / ``duotone``). ``None`` lets the set's default win.
    - ``default_size`` : Tailwind class string applied when no
      ``size=`` prop is given on a particular icon.
    """

    default_set: str = "lucide"
    default_style: str | None = "outline"
    default_size: str = "text-lg w-[1em] h-[1em]"


@dataclass(frozen=True, slots=True)
class ScrollbarConfig:
    """Style for the synthesised scrollbar (WebKit + Firefox).

    Color values are CSS *expressions* — typically ``"muted/30"`` to
    reference a semantic color via the framework's own palette
    machinery, but a literal ``"#ccc"`` works too. The css generator
    is responsible for translating either form into a final ``rgb()``
    declaration.
    """

    width: str = "4px"
    track: str = "transparent"
    thumb: str = "muted/30"
    thumb_hover: str = "muted/50"
