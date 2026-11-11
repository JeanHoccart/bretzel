"""The contract of the open-driven overlays: modal and anchored.

Rendering is shared by ``_modal.py`` and ``_anchored.py``; this module holds
what they declare. Each overlay keeps its theme and its ``render()``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base.overlay_wiring import (
    FLOATING_ALIGNS,
    FLOATING_POSITIONS,
    install_open_close_toggle,
)


class Overlay(Component):
    """A panel that opens and closes, from a binding or from its commands."""

    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("open",)
    IMPERATIVE: ClassVar[tuple[str, ...]] = ("open", "close", "toggle")
    EVENTS: ClassVar[tuple[str, ...]] = ("open", "close")
    # ``open`` AND ``close`` both fire on the root, so one overlay can wire
    # on_open + on_close to the server (the second rides a hidden carrier).
    ALLOW_MULTI_SERVER_EVENTS: ClassVar[bool] = True

    open: Any = reactive_prop(default=False, emit_attr=False, writes=True)
    dismissible: bool = reactive_prop(default=True, emit_attr=False)

    def __init__(
        self,
        *,
        on_open: Callable[..., Any] | str | None = None,
        on_close: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(on_open=on_open, on_close=on_close, **kwargs)
        # Instance attributes, shadowing the ``open`` descriptor; after
        # ``super().__init__``, which fills ``_binding_metadata``.
        install_open_close_toggle(self)


class ModalOverlay(Overlay):
    """An overlay above the page, with a backdrop."""

    title: str | Component | None = reactive_prop(default=None, emit_attr=False)
    width: str = reactive_prop(default="md", emit_attr=False)
    persistent: bool = reactive_prop(default=False, emit_attr=False)

    def __init__(
        self,
        *,
        open: Any = None,
        title: str | Component | None = None,
        width: str | None = None,
        dismissible: bool | None = None,
        persistent: bool | None = None,
        on_open: Callable[..., Any] | str | None = None,
        on_close: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            open=open,
            title=title,
            width=width,
            dismissible=dismissible,
            persistent=persistent,
            on_open=on_open,
            on_close=on_close,
            **kwargs,
        )


class AnchoredOverlay(Overlay):
    """An overlay floating next to its trigger."""

    # ``auto`` = best-fit (``$bz.helpers.floating`` picks the roomiest side
    # that fits); pin a side to override.
    position: str = reactive_prop(default="auto", emit_attr=False, steps=FLOATING_POSITIONS)
    align: str = reactive_prop(default="start", emit_attr=False, steps=FLOATING_ALIGNS)

    def __init__(
        self,
        *,
        trigger: Component | None = None,
        open: Any = None,
        position: str | None = None,
        align: str | None = None,
        dismissible: bool | None = None,
        on_open: Callable[..., Any] | str | None = None,
        on_close: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            open=open,
            position=position,
            align=align,
            dismissible=dismissible,
            on_open=on_open,
            on_close=on_close,
            **kwargs,
        )
        self._trigger: Component | None = trigger
