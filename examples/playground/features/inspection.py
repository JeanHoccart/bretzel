"""Shared inspection helper — collapsible Emitted HTML blocks.

Every playground feature page has between 1 and 4 ``Emitted HTML``
blocks in its stateful cards (Server playground / Server events /
Client playground / Client events ; cf. ``playground-pattern.md``).
These blocks are long, syntax-highlighted, and noisy — useful when
you want to inspect the framework's output, distracting when you're
scanning the visual demos.

This module ships :

- :class:`PlaygroundInspector` : a single ``ClientState`` shared
  across every page. ``show_html`` defaults to ``False`` ; flipping
  it once reveals every Emitted HTML block on every page until
  flipped back.
- :func:`emitted_html_block` : the helper feature files call instead
  of writing their own ``ui.text(label) + ui.code(html)`` pair. It
  renders the toggle switch (always visible) followed by the label +
  code wrapped in ``visible=inspector.show_html``.

The toggle row stays visible at all times so the user can always
re-enable inspection after collapsing it. The shared
``PlaygroundInspector`` means flipping the switch on one card flips
it on every card on every page — sticky session-wide preference.
"""

from __future__ import annotations

from bretzel import ui
from bretzel.state import ClientState, field


class PlaygroundInspector(ClientState, persist="memory"):
    """Session-wide toggle for every Emitted HTML block in the playground."""

    show_html: bool = field(default=False)


def emitted_html_block(label: str, html_source: str) -> None:
    """One inspection row : ``Show emitted HTML`` switch + collapsible
    label + code block.

    The switch is bound to the shared :class:`PlaygroundInspector`
    so toggling any block flips all blocks on every playground page
    at once. The label + ``ui.code`` are wrapped in a vstack with
    ``visible=inspector.show_html`` so the framework emits
    ``bz-show`` on the wrapper — plus a pre-stamped
    ``style="display:none"`` while the binding starts falsy, which is
    what keeps them from flashing before the runtime takes over."""

    inspector = PlaygroundInspector()
    with ui.hstack(align="center", gap="sm"):
        ui.switch(checked=inspector.show_html)
        ui.text("Show emitted HTML", color="muted", size="sm")
    with ui.vstack(gap="xs", visible=inspector.show_html):
        ui.text(label, color="muted", size="xs")
        ui.code(html_source, lang="html")
