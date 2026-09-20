"""``Badge`` — small inline label / status / count pill.

Three variants (``soft`` / ``solid`` / ``outline``), all theme
colors, optional inline icon left or right, optional ``×`` close
button when the caller wants the badge dismissible ::

    # Static label / status flag.
    ui.badge("New",    color="primary")
    ui.badge("3",      color="error", variant="solid")
    ui.badge("Active", color="success", icon_left="check")

    # Dismissible — filter chip, applied tag, user-managed entry.
    ui.badge(
        "React",
        color="info",
        on_close=partial(remove_filter, "react"),
    )

``dismissible=True`` **or** ``on_close`` is the only structural
difference between "static indicator" and "user-managed entry" —
without it, the badge is a leaf span ; with it, the framework appends a
real ``<button>`` with ``aria-label="Remove"``. The button dispatches a
bubbling ``close`` CustomEvent that the root's ``on_close=`` wiring
catches (``hx-trigger="close"`` for a server callable,
``bz-on:close`` for a client expression) — only the × triggers it,
a click on the badge body itself doesn't dismiss.

The pill is softly-rounded (``rounded-selector``) to read as "label / chip"
and pair with the form components, not as a "tracker / counter" capsule.
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
from bretzel.components.feedback.badge.theme import BADGE_THEME
from bretzel.components.primitives.icon import Icon
from bretzel.core.tree import Element, Node
from bretzel.render import text
from bretzel.state.scopes.client import ClientBinding


class Badge(Component):
    """Inline pill — count / status / tag / filter chip."""

    THEME: ClassVar[dict[str, Any]] = BADGE_THEME
    THEME_KEY: ClassVar[str] = "badge"
    DEFAULT_TAG: ClassVar[str] = "span"
    IS_CONTAINER: ClassVar[bool] = False
    # Only ``label`` carries live text (bz-text). variant / size / color /
    # icons / dismissible are design-time.
    # Cf. .claude/bretzel/client-reactive-surface.md.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("label",)
    EVENTS: ClassVar[tuple[str, ...]] = ("close",)

    variant: str = reactive_prop(default="soft", emit_attr=False)
    size: str = reactive_prop(default="sm", emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    dismissible: bool = reactive_prop(default=False, emit_attr=False)

    def __init__(
        self,
        label: str | ClientBinding | None = None,
        *,
        variant: str | None = None,
        size: str | None = None,
        color: str | None = None,
        icon_left: str | Component | ClientBinding | None = None,
        icon_right: str | Component | ClientBinding | None = None,
        dismissible: bool | None = None,
        on_close: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            variant=variant, size=size,
            color=color, dismissible=dismissible,
            on_close=on_close,
            **kwargs,
        )
        # ``adopt_slot`` detaches a Component slot (already
        # auto-registered with the parent) otherwise it renders twice;
        # string / ClientBinding pass through intact. Cf. traps.md § "A
        # Component slot without adopt_slot".
        self._label = Component.adopt_slot(label)

        # Icons scale with the badge size : ``adopt_slot(icon_shortcut)``
        # would build the Icon at its own ``sm`` default regardless. So
        # resolve the matching ``icon_size`` HERE and pre-build any
        # string-shortcut Icon at that size. Caller-passed Icon instances
        # are left alone (explicit choice).
        size_key = self._reactive_values.get("size") or "sm"
        # ``_resolved_theme()``, NOT ``self.THEME`` (the shipped dict
        # ignores a ``Theme(components={"badge": …})``) — otherwise the
        # icon does not follow the size table the app overrode.
        size_map = self._resolved_theme().get("sizes", {}).get(size_key, {})
        icon_size = size_map.get("icon_size", "sm")

        self._icon_left: Component | None = self._adopt_icon(
            icon_left, icon_size,
        )
        self._icon_right: Component | None = self._adopt_icon(
            icon_right, icon_size,
        )

    @staticmethod
    def _adopt_icon(
        value: Any,
        icon_size: str,
    ) -> Component | None:
        """Wrap a string shortcut into an :class:`Icon` of the right
        size, or pass an existing Component / ClientBinding through
        the standard adopt_slot detach pipeline. Returns ``None``
        when ``value`` is absent."""
        if value is None:
            return None
        if isinstance(value, str):
            value = Icon(value, size=icon_size)
        return Component.adopt_slot(value, icon_shortcut=True)

    def render(self) -> Element:
        theme = self._resolved_theme()
        slots = theme.get("slots", {})
        variants = theme.get("variants", {})
        sizes = theme.get("sizes", {})

        size_key = self._reactive_values.get("size") or "sm"
        size_map = sizes.get(size_key, sizes.get("sm", {}))
        variant_key = self._reactive_values.get("variant") or "soft"
        variant_cfg = variants.get(variant_key, variants.get("soft", {}))
        dismissible_lit = bool(self._reactive_values.get("dismissible"))

        def _resolve(template: str) -> str:
            return template

        # ── Peek at the wired close handler on the root ─────────────
        # Resolve ``emit_attrs`` early to peek at the listeners. The
        # ``on_close=`` wiring stays on the root ; the × button's
        # ``$dispatch('close')`` bubbles up to it. The peek decides
        # whether to show the × when ``dismissible`` wasn't set.
        root_attrs = self.emit_attrs()
        close_wired = close_handler_wired(root_attrs)

        # ── Dismiss UI: the × takes ``icon_right``'s place ───────────
        # Two shapes, not three: the × appears on a literal true
        # ``dismissible`` OR a wired ``on_close=``, and it OCCUPIES the
        # right-hand slot (``icon_right`` is then dropped). Otherwise no
        # ×, and ``icon_right`` renders normally.
        #
        # ⚠️ There was a 3rd "reactive" mode for a
        # ``dismissible=<ClientBinding>`` — ~20 lines that could NOT run:
        # the constructor has refused that binding since the 2026-07-16
        # cut (``dismissible`` is not in ``BINDABLE_PROPS``). Removed
        # (audit F06).
        show_close = dismissible_lit or close_wired

        # ── Root classes : slot base + variant.root + size.root ─────
        root_class = " ".join(p for p in (
            _resolve(slots.get("root", "")),
            _resolve(variant_cfg.get("root", "")),
            size_map.get("root", ""),
        ) if p)

        # ── Children ─────────────────────────────────────────────────
        children: list[Node] = []

        if self._icon_left is not None:
            children.append(self._icon_left.render())

        # Label : str / Component / ClientBinding via the standard
        # text-slot emission so all three shapes work uniformly.
        label_node = self.emit_text_slot(self._label)
        if label_node is not None:
            label_class = slots.get("label", "")
            if label_class:
                children.append(
                    Element(
                        tag="span",
                        attrs={"class": label_class},
                        children=(label_node,),
                    )
                )
            else:
                children.append(label_node)

        # ``icon_right`` renders ONLY with no × — the two compete for
        # the same right-hand slot.
        if self._icon_right is not None and not show_close:
            children.append(self._icon_right.render())

        # ── × button + local close flag ─────────────────────────────
        # Close is client-side : local ``open`` flag drives root
        # ``bz-show``, the × flips it false. If a handler is wired,
        # ``$dispatch('close')`` fires AFTER the visual close and bubbles
        # to the root listener.
        if show_close:
            close_class = " ".join(p for p in (
                _resolve(slots.get("close", "")),
                size_map.get("close", ""),
            ) if p)
            # Emission + detach single-sourced in ``dismiss_button``.
            children.append(dismiss_button(
                button_class=close_class,
                aria_label=text("badge.remove"),
                icon_size=size_map.get("close_icon_size", "xs"),
                extra_attrs={"tabindex": "0"},
            ))

        # ── Root assembly ───────────────────────────────────────────
        root_attrs["class"] = root_class
        if show_close:
            # Local bz-data ``open`` scope (keyed by bz-id, survives
            # morphs). No FOUC pre-stamp — ``open: true`` paints visible.
            # Both modes share this wiring : the × click sets ``open =
            # false`` and the root ``bz-show`` hides the badge.
            root_attrs.update(dismiss_local_scope())
        return Element(
            tag=self._tag,
            attrs=root_attrs,
            children=tuple(children),
        )
