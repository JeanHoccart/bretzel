"""``VStack`` and ``HStack`` — Flex shortcuts with a baked direction.

Both are :class:`Flex` subclasses that bake one ``direction`` value in
(and trim the surface a bit, since ``justify`` matters less in the
canonical "list of items" case). Pick :class:`VStack` for a vertical
list, :class:`HStack` for a horizontal row ; drop to :class:`Flex`
directly when you need a runtime-chosen direction, ``justify``, or
``wrap``. There is deliberately no bare ``Stack`` — the symmetric
``VStack`` / ``HStack`` pair says the axis explicitly (a bare "stack"
that could silently flip direction was per-instance ambiguity).

``gap`` inherits :class:`Flex`'s responsive form —
``ui.vstack(gap={"base": "sm", "md": "lg"})`` works. ``direction`` does
NOT : the axis is the shortcut's identity, so a responsive axis means
``ui.flex(direction={...})``.

"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import reactive_prop
from bretzel.components.base._wiring import reject_sealed
from bretzel.components.layout.flex.flex import Flex


class VStack(Flex):
    """Vertical stack — :class:`Flex` with ``direction="col"`` baked in.

    The most-used layout in any app. Exposes only ``gap`` + ``align``
    because justifying a vertical list of items rarely says what the
    developer means ; pass ``justify=`` through (it reaches Flex via
    ``**kwargs``) or drop to :class:`Flex` when you truly need it.
    """

    THEME_KEY: ClassVar[str] = "vstack"

    # Pin the axis to ``col`` — a VStack is vertical BY DEFINITION (it must
    # stay col even if Flex's default axis ever changed), and unlike Flex
    # it does NOT expose ``direction`` in ``__init__``. ``gap`` / ``align``
    # inherit Flex's defaults (``md`` / ``stretch``) — no restatement.
    direction: str = reactive_prop(default="col", emit_attr=False)
    SEALED_PROPS: ClassVar[tuple[str, ...]] = ("direction",)

    def __init__(
        self,
        *,
        gap: str | dict | None = None,
        align: str | None = None,
        **kwargs: Any,
    ) -> None:
        reject_sealed(kwargs, type(self))
        super().__init__(gap=gap, align=align, **kwargs)


class HStack(Flex):
    """Horizontal stack — :class:`Flex` with ``direction="row"`` baked in.

    Trimmed API like :class:`VStack` — ``gap`` + ``align`` cover the
    standard horizontal-row cases (``align`` defaults to ``center``, the
    usual "vertically-centred row" intent).
    """

    THEME_KEY: ClassVar[str] = "hstack"

    # Pin the axis to ``row`` (identity, as VStack pins ``col``). ``align``
    # defaults to ``center`` — HStack's own opinion (rows want vertically-
    # centred children), distinct from Flex's ``stretch``. ``gap`` inherits
    # Flex's ``md``.
    direction: str = reactive_prop(default="row", emit_attr=False)
    SEALED_PROPS: ClassVar[tuple[str, ...]] = ("direction",)
    align: str = reactive_prop(default="center", emit_attr=False)

    def __init__(
        self,
        *,
        gap: str | dict | None = None,
        align: str | None = None,
        **kwargs: Any,
    ) -> None:
        reject_sealed(kwargs, type(self))
        super().__init__(gap=gap, align=align, **kwargs)
