"""``Dialog`` — modal overlay with backdrop, escape, scroll lock.

Composition pattern : Dialog is purely visual — every child captured
inside the ``with`` block is the dialog body (header / body / footer
all composed there). Open from outside via the imperative API
(``.open()`` / ``.close()`` / ``.toggle()``) or by binding ``open=``
to a ``ClientState`` field ::

    with ui.dialog(title="Delete your account?") as dlg:
        ui.text("This is irreversible. All projects will be lost.")
        with ui.hstack(justify="end", gap="sm"):
            ui.button("Cancel", variant="ghost", on_click=dlg.close())
            ui.button("Delete", color="error",
                      on_click=[delete_account, dlg.close()])
    ui.button("Delete account", variant="outline", color="error",
              on_click=dlg.open())

Open / close — the framework's universal contract :

  ``open=`` accepts the same three shapes every reactive prop does :
  a literal ``bool`` (self-sufficient, the dialog owns its own state via
  ``bz-data``), a server-resolved value (resolved once at render),
  or a :class:`ClientBinding` (live two-way reactive — the panel carries
  ``bz-attr:data-open`` which reads the binding's path. The trigger and
  the close button write to
  it via standard ``binding.set(value)`` / ``binding.toggle()``
  expressions). No dialog-specific helpers ; the same primitive that
  drives any other reactive prop drives this one ::

      class AccountUI(ClientState):
          delete_open: bool = field(default=False)

      ui_state = AccountUI()

      with ui.dialog(open=ui_state.delete_open, title="Delete?"):
          ui.text("Irreversible.")
          ui.button("Cancel", on_click=ui_state.delete_open.set(False))
          ui.button(
              "Delete",
              on_click=[delete_account, ui_state.delete_open.set(False)],
          )

  The list-valued ``on_click=`` chains a server callable + any
  number of client-side action strings into the right pair of
  attributes (one ``hx-post`` + one ``bz-on:click``), so the
  Delete button POSTs to the server AND closes the dialog
  optimistically in a single click.

A11y :
- ``role="dialog"`` + ``aria-modal="true"`` on the panel.
- ``aria-labelledby`` points at the title id when ``title=`` is set.
- The close button gets an explicit ``aria-label="Close"``.
- Focus is trapped while open : the panel engages
  ``$bz.helpers.focusTrap`` on open — Tab/Shift+Tab cycle inside, the
  first interactive child receives focus, and the previously-focused
  element is restored on close.

Notes :
- Client wiring : ``bz-data`` (component-local scope, keyed by ``bz-id``,
  survives morphs) + ``bz-attr:data-open`` / ``bz-on:`` / ``bz-effect``.
  The element stays **MOUNTED**: ``show_attrs`` sets ``data-open`` +
  ``data-bz-overlay`` and the animation is CSS on ``data-[open=…]``. No
  ``bz-show``, no ``display:none`` prestamp — ``_ANTI_FLASH_STYLE``'s
  ``[data-bz-overlay][data-open="false"]`` selector does the anti-flash
  work.
- Enter/leave animations are CSS-only — the theme owns them.
- ``on_open=`` / ``on_close=`` : BOTH may be server callables on the same
  dialog. A root element hosts a single ``hx-post``, so ``on_open`` rides
  the root and ``on_close`` is relocated onto a hidden HTMX *carrier* that
  listens for the ``close`` event ``from:`` the root (cf.
  ``Component.ALLOW_MULTI_SERVER_EVENTS``). Either may instead be a client
  expression string (then it's a plain ``bz-on:`` on the root, no carrier).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base._wiring import install_open_close_toggle
from bretzel.components.overlay._modal import render_modal_overlay
from bretzel.components.overlay.dialog.theme import DIALOG_THEME
from bretzel.core.tree import Element


class Dialog(Component):
    """Centered modal with backdrop + escape + scroll lock."""

    THEME: ClassVar[dict[str, Any]] = DIALOG_THEME
    THEME_KEY: ClassVar[str] = "dialog"
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("open",)
    IMPERATIVE: ClassVar[tuple[str, ...]] = ("open", "close", "toggle")
    EVENTS: ClassVar[tuple[str, ...]] = ("open", "close")
    # ``open`` AND ``close`` both fire on the root, so a single dialog can
    # wire on_open + on_close to the server (the second rides a hidden
    # carrier — cf. ``Component.ALLOW_MULTI_SERVER_EVENTS``).
    ALLOW_MULTI_SERVER_EVENTS: ClassVar[bool] = True

    open: Any = reactive_prop(default=False, emit_attr=False, writes=True)
    title: str | None = reactive_prop(default=None, emit_attr=False)
    width: str = reactive_prop(default="md", emit_attr=False)
    dismissible: bool = reactive_prop(default=True, emit_attr=False)
    persistent: bool = reactive_prop(default=False, emit_attr=False)

    def __init__(
        self,
        *,
        open: Any = None,
        title: str | None = None,
        width: str | None = None,
        dismissible: bool | None = None,
        persistent: bool | None = None,
        on_open: Callable[..., Any] | str | None = None,
        on_close: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
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
        # Write-only imperative API ``.open()`` / ``.close()`` /
        # ``.toggle()`` — installed as instance attributes (shadowing the
        # ``open`` descriptor) by the base helper, identical on the 4
        # open-driven overlays. Cf. `imperative-api.md`.
        install_open_close_toggle(self)

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme = self._resolved_theme()
        widths = theme.get("widths", {})
        width = self._reactive_values.get("width") or "md"

        return render_modal_overlay(
            self,
            slots=theme.get("slots", {}),
            panel_extra=(widths.get(width, widths.get("md", "")),),
        )
