"""The ``loading=`` wiring shared by Button and IconButton.

Both components have the same loading mechanics — build the spinner
early, lock the button during the async window, and mutex the spinner
against the leading icon — and only the dressing around differs (Button
inserts a label and a right icon, IconButton has only a glyph).

The mutex wrapper itself (``Component._cloak_show``) is a base-layer
primitive: what this module shares is the early construction of the
spinner, the ``loading || disabled`` OR-combine, and the glue that
assembles them.
"""

from __future__ import annotations

from typing import Any

from bretzel.components.base import Component, ComponentUsageError
from bretzel.components.primitives.spinner import Spinner
from bretzel.core.tree import Node
from bretzel.runtime.protocol import BZ_ATTR_PREFIX


def build_loading_spinner(component: Component) -> Spinner | None:
    """The button's spinner, built **in ``__init__``**.

    ⚠️ Early on purpose: ``Spinner.__init__`` needs a live render context
    to allocate its id, and ``render()`` can run after that context has
    been torn down (the unit-test case).

    Built as soon as ``loading`` is true **or** carries a binding — the
    reactive case needs the DOM node even if ``loading`` is False at SSR,
    since the mutex emits both branches for the runtime to toggle with
    ``bz-show``.
    """
    if not (component._reactive_values.get("loading")
            or "loading" in component._binding_metadata):
        return None
    size = component._reactive_values.get("size") or "md"
    return Component.adopt_slot(Spinner(size=size))


def apply_loading_disabled(
    component: Component, attrs: dict[str, Any], loading_path: str,
) -> None:
    """``bz-attr:disabled = (loading) || (disabled)``.

    The HTML ``disabled`` attribute must stay true as long as EITHER is —
    otherwise a ``loading`` falling back would unlock a button that is
    otherwise disabled. The ``disabled`` side is either a binding, or the
    SSR snapshot frozen as a JS literal.
    """
    disabled_binding = component._binding_metadata.get("disabled")
    if disabled_binding is not None:
        dis_path = component.path_of(disabled_binding)
    else:
        dis_path = (
            "true" if component._reactive_values.get("disabled") else "false"
        )
    attrs[f"{BZ_ATTR_PREFIX}disabled"] = f"({loading_path}) || ({dis_path})"


def loading_leading_children(
    component: Component,
    *,
    loading: bool,
    loading_path: str | None,
    spinner: Spinner | None,
    icon: Component | None,
) -> list[Node]:
    """The spinner ↔ leading icon mutex, in the children's order.

    - **Reactive** (``loading_path``): BOTH branches are emitted and the
      runtime mutexes them with ``bz-show`` — one cannot choose at SSR
      what the client will decide.
    - **Static**: one OR the other, never both.

    Each caller then adds what is proper to it (the label and the right
    icon for Button).
    """
    children: list[Node] = []
    if loading_path is not None:
        assert spinner is not None, (
            "a reactive loading requires the spinner built in __init__"
        )
        children.append(component._cloak_show(
            spinner.render(), loading_path, initial=loading,
        ))
        if icon is not None:
            children.append(component._cloak_show(
                icon.render(), f"!{loading_path}", initial=not loading,
            ))
        return children
    if loading and spinner is not None:
        children.append(spinner.render())
    elif not loading and icon is not None:
        children.append(icon.render())
    return children


__all__ = [
    "apply_loading_disabled",
    "build_loading_spinner",
    "loading_leading_children",
]


def anchor_tag(component: Component, *, href: Any, on_click: Any, type: Any,
               kwargs: dict[str, Any], name: str) -> None:
    """An ``href`` makes an action an ANCHOR — ``ui.button`` and
    ``ui.icon_button`` alike, one rule for both.

    The tag switches in the constructor and not in ``render``:
    ``self._tag`` is read by introspection and by the gates, and a
    component whose tag only knows itself at render lies to whoever asks
    it. An explicit ``tag=`` wins — the tier-2 escape hatch.
    """
    if href is None:
        return
    if "tag" not in kwargs:
        component._tag = "a"
    if on_click is not None:
        raise ComponentUsageError(
            f"ui.{name} does not take `href=` AND `on_click=`: they are two "
            f"jobs (navigate / act) on one target, and nothing would "
            f"announce which applies. Choose — or place two controls."
        )
    if type is not None:
        raise ComponentUsageError(
            f"ui.{name}(href=…) renders an `<a>`, where `type=` names the "
            f"target's MIME type and not a button's nature. Remove `type=`."
        )


def finish_anchor(tag: str, attrs: dict[str, Any], *, external: bool) -> None:
    """What changes once an action renders as an ``<a>``.

    - ``type`` (declared ``default="button"``) names a MIME type there:
      ``<a type="button">`` means nothing;
    - external: a new tab and a neutralised opener — the ``rel`` pair is
      not cosmetic, it stops the opened page reaching ``window.opener``;
    - disabled: an ``<a>`` has no ``disabled`` attribute, and setting it
      blocks NOTHING — remove the destination, leave the tab order and
      say so out loud, as ``ui.link`` does.
    """
    if tag == "button":
        return
    attrs.pop("type", None)
    if tag != "a":
        return
    if external:
        attrs.setdefault("target", "_blank")
        attrs.setdefault("rel", "noopener noreferrer")
    if attrs.pop("disabled", None):
        attrs.pop("href", None)
        attrs["aria-disabled"] = "true"
        attrs["tabindex"] = "-1"
