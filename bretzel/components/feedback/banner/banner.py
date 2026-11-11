"""``Banner`` — full-width page-level status strip.

Visually distinct from :class:`Alert` :

- **Alert** is inline (rounded, padded, sits where you put it
  inside a card or form). Use for context-local messages.
- **Banner** is full-width edge-to-edge with a coloured left bar.
  Use for page-level chrome announcements : "Your trial expires
  in 3 days", "Scheduled maintenance Sunday 02:00 UTC", "New
  dashboard available — try it now".

Six color flavours :

- ``info`` / ``success`` / ``warning`` / ``error`` — auto-pick a
  matching icon (same recipe as Alert).
- ``muted`` / ``primary`` — neutral and brand variants, no auto-icon
  (caller passes one via ``icon=`` if wanted).

Usage ::

    ui.banner("Trial expires in 3 days", color="warning")

    with ui.banner(
        "New dashboard available",
        title="What's new",
        color="info",
        dismissible=True,
    ):
        ui.button("Try it now", color="primary", size="sm")

The component is a container (:attr:`IS_CONTAINER`) so the action slot uses the
``with`` body — pass any number of buttons / links / IconButtons,
they all land in the right-aligned ``actions`` row.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import (
    Component,
    reactive_prop,
)
from bretzel.components.base.dismiss import (
    close_handler_wired,
    dismiss_button,
    dismiss_local_scope,
    split_icon_flag,
)
from bretzel.components.base.theme_values import theme_context
from bretzel.components.feedback.banner.theme import BANNER_THEME
from bretzel.components.primitives.icon import Icon
from bretzel.core.tree import Element, Node
from bretzel.render import text
from bretzel.state.scopes.client import ClientBinding


class Banner(Component):
    """Full-width page-level status strip."""

    THEME: ClassVar[dict[str, Any]] = BANNER_THEME
    THEME_KEY: ClassVar[str] = "banner"
    # design-time.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
    EVENTS: ClassVar[tuple[str, ...]] = ("close",)

    color: str = reactive_prop(default="info", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)
    dismissible: bool = reactive_prop(default=False, emit_attr=False)

    def __init__(
        self,
        message: str | Component | None = None,
        *,
        title: str | Component | None = None,
        icon: str | Component | bool | None = None,
        color: str | None = None,
        size: str | None = None,
        dismissible: bool | None = None,
        on_close: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            color=color, size=size,
            dismissible=dismissible,
            on_close=on_close,
            **kwargs,
        )
        self._title = title
        self._message = message
        # Explicit icon wins over the auto-pick (a string flows through:
        # render() owns the ``Icon`` wrap); ``icon=False`` suppresses it.
        self._user_icon, self._suppress_auto_icon = split_icon_flag(icon)

    def render(self) -> Element:
        theme, slots, _sizes, _size_key, color = theme_context(self, color_default="info")
        variants = theme.get("variants", {})

        dismissible_lit = bool(self._reactive_values.get("dismissible"))
        # ⚠️ ``emit_attrs()`` resolved HERE, before the decision, to PEEK
        # at the wired handler (cf. Badge § "Peek at the wired close
        # handler"). Without it, an ``on_close=`` with no × button would
        # be a dead letter: declaring a handler MUST bring out the
        # affordance.
        root_attrs = self.emit_attrs()
        close_wired = close_handler_wired(root_attrs)
        # The × appears when ``dismissible=True`` OR an ``on_close=``
        # is wired — declaring a handler MUST bring out the affordance
        # that fires it, otherwise it is a dead letter.
        show_close = dismissible_lit or close_wired

        variant_cfg = variants.get(color, {})

        children: list[Node] = []

        # ── Icon (explicit > auto-pick > none) ──────────────────────
        icon_render: Element | None = None
        if self._user_icon is not None:
            # A name, or a binding ``Icon`` follows live (R1: ``icon`` is
            # bindable on every icon slot).
            if isinstance(self._user_icon, str | ClientBinding):
                icon_obj = Icon(self._user_icon, size="md")
            else:
                icon_obj = self._user_icon
            Component._detach_from_parent(icon_obj)
            icon_render = icon_obj.render()
        elif not self._suppress_auto_icon and (
            icon_name := theme.get("color_icons", {}).get(color)
        ):
            icon_obj = Icon(icon_name, size="md")
            Component._detach_from_parent(icon_obj)
            icon_render = icon_obj.render()

        if icon_render is not None:
            children.append(
                Element(
                    tag="div",
                    attrs={"class": slots.get("icon", "")},
                    children=(icon_render,),
                )
            )

        # ── Content column (title + message) ────────────────────────
        content_kids: list[Node] = []

        title_node = self.emit_text_slot(self._title)
        if title_node is not None:
            title_class = self.compose_class("title")
            content_kids.append(
                Element(
                    tag="span",
                    attrs={"class": title_class},
                    children=(title_node,),
                )
            )

        message_node = self.emit_text_slot(self._message)
        if message_node is not None:
            content_kids.append(
                Element(
                    tag="span",
                    attrs={"class": slots.get("message", "")},
                    children=(message_node,),
                )
            )

        if content_kids:
            children.append(
                Element(
                    tag="div",
                    attrs={"class": slots.get("content", "")},
                    children=tuple(content_kids),
                )
            )

        # ── Action slot (IS_CONTAINER children) ─────────────────────
        body_nodes = list(self._render_children())
        if body_nodes:
            children.append(
                Element(
                    tag="div",
                    attrs={"class": slots.get("actions", "")},
                    children=tuple(body_nodes),
                )
            )

        # ── Dismiss button ──────────────────────────────────────────
        # The ``on_close=`` wiring stays on the root : the button's
        # ``$dispatch('close')`` bubbles up to the root listener
        # (``hx-trigger="close"`` for a server callable, ``bz-on:close``
        # for a client expression). (``root_attrs`` resolved above.)
        if show_close:
            # Pure-client dismiss: the × flips the local ``open`` flag;
            # the root's ``bz-show="open"`` unmounts the banner. Emission
            # + detach + gating single-sourced in ``dismiss_button``.
            children.append(dismiss_button(
                button_class=slots.get("close", ""),
                aria_label=text("banner.dismiss"),
                icon_size="sm",
            ))

        # ── Root ────────────────────────────────────────────────────
        # The slot and its size through the base composer; the tint is
        # keyed by ``color=`` (one row per semantic colour), not by a
        # ``variant=``, so it is added here.
        root_class = " ".join(p for p in (
            self.compose_class("root"),
            variant_cfg.get("root", ""),
        ) if p)
        root_attrs["class"] = root_class
        root_attrs.setdefault("role", "status")
        if show_close:
            # Local bz-data ``open`` scope (re-seeded only after a server
            # ``on_close``, cf. the helper). No FOUC pre-stamp — ``open: true`` paints visible.
            # The root ``bz-show="open"`` handles only the × dismiss ;
            # the binding gate lives on the button's own ``bz-show``.
            root_attrs.update(dismiss_local_scope(root_attrs))

        return Element(
            tag=self._tag, attrs=root_attrs, children=tuple(children),
        )


__all__ = ["Banner"]
