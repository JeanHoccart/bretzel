"""``Alert`` — inline status panel.

Color is open : pass any theme color (``primary``, ``muted``,
``success``, custom palette names…). For the four standard a11y
semantic colors — ``info`` / ``success`` / ``warning`` / ``error`` —
an icon is picked automatically (the universal info / check /
triangle / octagon glyphs). For any other color, no icon is
rendered unless the caller passes ``icon=`` explicitly. ``icon=``
always overrides whatever auto-pick would have happened.

Composition pattern : ``ui.alert("Saved!", color="success")`` is the
common shape ; pass a child ``Component`` as ``message=`` for rich
content (links, formatted prose).

A11y note : we deliberately do NOT auto-set ``role="alert"`` — that
role carries "interrupt the user, announce now" semantics wrong for
a routine info panel. Callers who mean it pass ``role="alert"``.

Dismiss : ``dismissible=True`` adds a close icon-button that hides
the alert client-side (local ``bz-data`` ``open`` flag + root
``bz-show``, keyed by ``bz-id`` so it survives morphs). An optional
``on_close`` server handler fires AFTER the visual close (for
follow-up work like marking a notification read).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base._wiring import (
    close_handler_wired,
    dismiss_button,
    dismiss_local_scope,
)
from bretzel.components.feedback.alert.theme import ALERT_THEME
from bretzel.components.primitives.icon import Icon
from bretzel.core.tree import Element, Node
from bretzel.render import text


class Alert(Component):
    """Status panel : leading icon, optional title, message body,
    optional dismiss button on the right."""

    THEME: ClassVar[dict[str, Any]] = ALERT_THEME
    THEME_KEY: ClassVar[str] = "alert"
    IS_CONTAINER: ClassVar[bool] = False
    # Reactive surface — only title + message carry live text (bz-text).
    # color / dismissible are design-time.
    # Cf. .claude/bretzel/client-reactive-surface.md.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("title", "message")
    EVENTS: ClassVar[tuple[str, ...]] = ("close",)

    color: str = reactive_prop(default="info", emit_attr=False)
    title: str | None = reactive_prop(default=None, emit_attr=False)
    dismissible: bool = reactive_prop(default=False, emit_attr=False)

    def __init__(
        self,
        message: str | Component | None = None,
        *,
        color: str | None = None,
        icon: str | Component | bool | None = None,
        title: str | None = None,
        dismissible: bool | None = None,
        on_close: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            color=color, title=title, dismissible=dismissible,
            on_close=on_close,
            **kwargs,
        )
        # ``adopt_slot`` detaches a Component slot from its active parent
        # so it doesn't render twice (standalone sibling + inside alert),
        # and does the string→Icon shortcut for ``icon=``.
        self._message = Component.adopt_slot(message)
        # ``icon=False`` is the opt-out for the semantic auto-icon on
        # ``info`` / ``success`` / ``warning`` / ``error`` colours.
        # ``icon=None`` (default) keeps the auto-pick ; an explicit
        # string or Component overrides ; ``False`` suppresses entirely.
        self._suppress_auto_icon = icon is False
        icon_value: str | Component | None = None if icon is False else icon
        self._icon: Component | None = Component.adopt_slot(
            icon_value, icon_shortcut=True
        )

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme = self._resolved_theme()
        color = self._reactive_values.get("color") or "info"
        title = self._reactive_values.get("title")
        dismissible = bool(self._reactive_values.get("dismissible"))

        # ── Leading icon ─────────────────────────────────────────────
        # Explicit ``icon=`` wins ; ``icon=False`` opts out. Otherwise
        # auto-pick only for the four semantic colours (primary / muted /
        # custom render iconless — the auto-pick would be arbitrary).
        icon = self._icon
        if icon is None and not self._suppress_auto_icon:
            icon_name = theme.get("color_icons", {}).get(color)
            if icon_name:
                icon = Icon(icon_name, size=theme.get("icon_size", "md"))
                # Constructed inside render() — auto-detach from any
                # parent stack the constructor side-effects might have
                # registered the icon onto.
                Component._detach_from_parent(icon)

        children: list[Node] = []

        if icon is not None:
            icon_render = icon.render()
            icon_class = self.compose_class(
                "icon", apply_variant_size_modifiers=False
            )
            icon_render = Element(
                tag=icon_render.tag,
                attrs={
                    **icon_render.attrs,
                    "class": (
                        f"{icon_class} "
                        f"{icon_render.attrs.get('class', '')}"
                    ).strip(),
                },
                children=icon_render.children,
            )
            children.append(icon_render)

        # ── Content stack : title + message ────────────────────────────
        content_children: list[Node] = []
        # ``emit_text_slot`` handles str / ClientBinding / None uniformly,
        # dodging the ``if title:`` ``__bool__`` trap on a binding.
        title_binding = self._binding_metadata.get("title")
        title_value = title_binding if title_binding is not None else title
        title_node = self.emit_text_slot(title_value)
        if title_node is not None:
            content_children.append(
                Element(
                    tag="div",
                    attrs={
                        "class": self.compose_class(
                            "title",
                            apply_variant_size_modifiers=False,
                        )
                    },
                    children=(title_node,),
                )
            )
        if isinstance(self._message, Component):
            content_children.append(self._message.render())
        else:
            # ``emit_text_slot`` handles None / "" / str / ClientBinding /
            # ClientExpression uniformly.
            message_node = self.emit_text_slot(self._message)
            if message_node is not None:
                content_children.append(
                    Element(
                        tag="div",
                        attrs={
                            "class": self.compose_class(
                                "message",
                                apply_variant_size_modifiers=False,
                            )
                        },
                        children=(message_node,),
                    )
                )
        children.append(
            Element(
                tag="div",
                attrs={
                    "class": self.compose_class(
                        "content",
                        apply_variant_size_modifiers=False,
                    )
                },
                children=tuple(content_children),
            )
        )

        # ── Dismiss button : pure-client toggle + optional handler ─────
        # ⚠️ ``emit_attrs()`` resolved HERE, before the decision, to PEEK
        # at the wired handler (cf. Badge § "Peek at the wired close
        # handler"). Without that peek, an ``on_close=`` with no × button
        # would be a dead letter: declaring a handler MUST bring out the
        # affordance that fires it.
        attrs = self.emit_attrs()
        close_wired = close_handler_wired(attrs)
        show_dismiss = dismissible or close_wired
        if show_dismiss:
            # Emission + detach + gating single-sourced in
            # ``dismiss_button`` (the feedback family). The ×'s ghost look
            # now lives in the ``dismiss`` theme slot (resolved by
            # ``compose_class``) instead of an IconButton — a single
            # shape of × for Alert/Badge/Banner. The click flips the
            # local ``open`` flag (the root's ``bz-show`` hides the
            # alert) AND re-dispatches ``close`` for the server/client
            # ``on_close=``.
            children.append(dismiss_button(
                button_class=self.compose_class(
                    "dismiss",
                    apply_variant_size_modifiers=False,
                ),
                aria_label=text("alert.dismiss"),
                icon_size="sm",
            ))

        attrs["class"] = self.compose_class("root", )
        # No auto ``role="alert"`` (interrupt-now semantics, unwarranted
        # for a routine panel) — callers pass it explicitly.
        if show_dismiss:
            # Component-local ``open`` scope (keyed by ``bz-id``, survives
            # morphs) the dismiss click mutates ; root ``bz-show``
            # collapses the alert. No FOUC pre-stamp — ``open: true``
            # paints visible.
            attrs.update(dismiss_local_scope())

        return Element(tag=self._tag, attrs=attrs, children=tuple(children))
