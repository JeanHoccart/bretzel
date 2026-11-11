"""A server handler gets its component's fields — every event, never a file.

Audit of the events (2026-10-29), measured in the browser by
``tests/probes/probe_events.py``; held here at the HTML, in the fast suite:

- a second server handler rides a hidden carrier whose ``hx-include``
  brings the fields — but not a file input, which a urlencoded POST
  turns into the text ``[object File]`` (a file_upload's
  ``on_upload_start`` received it);
- the carrier lists itself first: a list that matches nothing is an htmx
  error in the console (a file_upload holds no other field);
- a rich field's ``on_focus``, relocated to its trigger, brings the field
  it no longer sits on (a select's posted nothing, its ``on_blur`` the
  value).
"""

from __future__ import annotations

import re

from bretzel import ui
from bretzel.components.base.events import fields_of
from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize


def _handler() -> None:
    pass


def _other() -> None:
    pass


def _includes(html: str) -> list[str]:
    return re.findall(r'hx-include="([^"]*)"', html)


def test_fields_of_keeps_a_file_out_and_never_uses_a_comma_inside() -> None:
    selector = fields_of("r")
    assert "#r input:not([type=file])" in selector
    # htmx splits ``hx-include`` on its commas: no ``:is(a, b)``.
    assert ":is(" not in selector
    assert all(part.strip().startswith("#r") for part in selector.split(","))


def test_a_carrier_lists_itself_first_then_the_fields() -> None:
    with render_isolated():
        html = serialize(ui.input(name="q", on_change=_handler, on_keydown=_other).render())
    (include,) = _includes(html)
    first = include.split(",")[0].strip()
    assert first.endswith("__onkeydown")
    assert f"id=\"{first[1:]}\"" in html
    assert "input:not([type=file])" in include


def test_a_file_upload_carrier_does_not_post_its_file() -> None:
    with render_isolated():
        html = serialize(ui.file_upload(name="fu", upload_url="/up", on_change=_handler,
                                        on_upload_start=_other).render())
    (include,) = _includes(html)
    root = include.split(",")[1].strip().split(":")[0]
    # The root is taken whole only when it holds no file input.
    assert f"{root}:not(:has(input[type=file]))" in include
    assert f'"{root}"' not in f'"{include}"'


def test_a_select_focus_handler_brings_the_field() -> None:
    with render_isolated():
        select = ui.select(name="s", options=[("a", "A")], on_focus=_handler)
        html = serialize(select.render())
    (include,) = _includes(html)
    assert include == fields_of(select.id)
