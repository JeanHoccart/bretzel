"""Unit tests for :class:`MessageInput` and :class:`MessageInputTool`.

The box is a ``<form>`` whose text, files and buttons are composed from
the framework's own components; what the browser does with it (Enter,
the emptying, the microphone) is ``components/inputs/message_input/message_input.js``,
measured by ``tests/runtime_js/test_a_message_box_sends_and_empties.py``.
"""

from __future__ import annotations

import re

import pytest

from bretzel.components.base import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.feedback.badge import Badge
from bretzel.components.inputs.message_input import MessageInput, MessageInputTool
from bretzel.core.serialize import serialize
from bretzel.state.scopes.client import ClientBinding


def bound(field: str, value: object) -> ClientBinding:
    return ClientBinding(class_name="ask", instance_key="default", field_name=field,
                         value=value)


def send() -> None: ...


def stop() -> None: ...


def off(tag: str) -> bool:
    """The ``disabled`` ATTRIBUTE — not the ``disabled:`` of a class."""
    return re.search(r'\sdisabled(?=[\s>/=])', tag) is not None


def html(**kwargs) -> str:
    with render_isolated():
        return serialize(MessageInput(**kwargs).render())


class TestTheBox:
    def test_it_is_a_form_around_a_textarea(self) -> None:
        out = html(on_submit=send)
        assert out.startswith("<form") and "bz-message-input" in out
        assert "<textarea" in out and 'data-bz-message-field=""' in out
        assert 'hx-trigger="submit"' in out

    def test_the_text_carries_the_name_and_the_binding(self) -> None:
        out = html(value=bound("question", ""), on_submit=send)
        field = re.search(r"<textarea[^>]*>", out).group(0)
        assert 'name="ask.question"' in field
        assert 'bz-model="$bz.state.ask.default.question"' in field
        root = re.search(r"<form[^>]*>", out).group(0)
        assert "name=" not in root and "bz-model" not in root

    def test_a_given_value_is_the_text_content(self) -> None:
        out = html(value="A draft <kept>")
        assert ">A draft &lt;kept&gt;</textarea>" in out

    def test_placeholder_and_disabled_reach_the_text(self) -> None:
        field = re.search(r"<textarea[^>]*>", html(placeholder="Ask…", disabled=True)).group(0)
        assert 'placeholder="Ask…"' in field and "disabled" in field

    def test_an_unnamed_text_still_leaves_as_message(self) -> None:
        assert 'name="message"' in re.search(r"<textarea[^>]*>", html()).group(0)

    def test_an_explicit_name_wins(self) -> None:
        assert 'name="q"' in re.search(r"<textarea[^>]*>", html(name="q")).group(0)


class TestLimitsAndNames:
    def test_the_text_has_a_stable_accessible_name(self) -> None:
        field = re.search(r"<textarea[^>]*>", html(placeholder="Ask…")).group(0)
        assert 'aria-label="Your message"' in field

    def test_max_length_bounds_the_text_and_shows_a_counter(self) -> None:
        out = html(max_length=500, value="Bonjour")
        assert 'maxlength="500"' in re.search(r"<textarea[^>]*>", out).group(0)
        assert re.search(r"data-bz-message-count[^>]*>7 / 500<", out)

    def test_file_limits_reach_the_picker(self) -> None:
        out = html(files=".pdf", max_files=2, max_size_mb=5)
        assert "&quot;maxFiles&quot;: 2" in out and "&quot;maxSizeMB&quot;: 5" in out

    def test_off_the_top_row_is_inert(self) -> None:
        with render_isolated():
            box = MessageInput(disabled=True)
            with box:
                Badge("5e1", dismissible=True)
            out = serialize(box.render())
        assert "data-disabled" in re.search(r"<form[^>]*>", out).group(0)
        assert re.search(r'<div class="[^"]*empty:hidden[^"]*" inert', out)


class TestTheRoundButton:
    def test_it_sends_by_default(self) -> None:
        out = html(on_submit=send)
        assert 'type="submit"' in out and "data-bz-message-send" in out
        assert "lucide:square" not in out

    def test_busy_makes_it_stop_and_relays_the_event(self) -> None:
        out = html(on_submit=send, loading=True, on_stop=stop)
        assert "data-bz-message-send" not in out
        assert "lucide:square" in out and "$dispatch('stop')" in out
        assert 'hx-trigger="stop from:#' in out, "on_stop rides a carrier on the form"

    def test_the_submit_stays_the_form_s_own_request(self) -> None:
        # Its client half first (``busy.set(True)``): the list once sent
        # the submit to a carrier and the stop to the form — the box never
        # saw its request, and kept the text.
        busy = bound("busy", False)
        out = html(on_submit=[busy.set(True), send], loading=busy, on_stop=stop)
        form = out.split(">", 1)[0]
        assert "::send" in form and 'hx-trigger="submit"' in form
        assert 'hx-trigger="stop from:#' in out

    def test_a_bound_busy_renders_both_shown_by_the_binding(self) -> None:
        out = html(on_submit=send, loading=bound("busy", False), on_stop=stop)
        assert "lucide:arrow-up" in out and "lucide:square" in out
        assert out.count("$bz.state.ask.default.busy") >= 2


class TestWhatIsInside:
    def test_files_add_the_clip_and_the_picker(self) -> None:
        out = html(files=(".pdf", "image/*"))
        assert 'type="file"' in out and 'name="files"' in out
        assert 'accept=".pdf,image/*"' in out
        assert "lucide:paperclip" in out
        assert 'enctype="multipart/form-data"' in out

    def test_a_single_accepted_type_is_a_tuple(self) -> None:
        assert 'accept=".pdf"' in html(files=".pdf")

    def test_no_files_no_clip(self) -> None:
        out = html()
        assert "paperclip" not in out and 'type="file"' not in out

    def test_voice_adds_the_microphone(self) -> None:
        out = html(voice=True)
        assert "data-bz-voice" in out and 'aria-pressed="false"' in out
        assert "[[data-bz-can-dictate]_&amp;]:contents" in out

    def test_a_tool_goes_to_the_bar_anything_else_to_the_top(self) -> None:
        with render_isolated():
            box = MessageInput(on_submit=send)
            with box:
                MessageInputTool("Templates", icon="file-text", on_click=send)
                Badge("5e1")
            out = serialize(box.render())
        top_end = out.index("</div>")
        assert "5e1" in out[:top_end], "the badge is in the top row"
        assert out.index("lucide:file-text") > out.index("<textarea"), "the tool is in the bar"


class TestTheTool:
    def test_its_label_names_it(self) -> None:
        with render_isolated():
            out = serialize(MessageInputTool("Templates", icon="file-text").render())
        assert 'aria-label="Templates"' in out and 'data-bz-tip="Templates"' in out
        assert 'type="button"' in out

    def test_a_label_and_an_icon_are_required(self) -> None:
        with pytest.raises(ComponentUsageError, match="label"):
            MessageInputTool("", icon="star")

    def test_a_disabled_box_disables_its_tools(self) -> None:
        with render_isolated():
            box = MessageInput(disabled=True)
            with box:
                MessageInputTool("Templates", icon="file-text", on_click=send)
            out = serialize(box.render())
        assert off(re.search(r'<button[^>]*aria-label="Templates"[^>]*>', out).group(0))

    def test_a_tool_can_be_off_in_a_box_that_works(self) -> None:
        with render_isolated():
            box = MessageInput(on_submit=send)
            with box:
                MessageInputTool("Later", icon="star", disabled=True)
                MessageInputTool("Now", icon="file-text")
            out = serialize(box.render())
        assert off(re.search(r'<button[^>]*aria-label="Later"[^>]*>', out).group(0))
        assert not off(re.search(r'<button[^>]*aria-label="Now"[^>]*>', out).group(0))
        assert not off(re.search(r"<textarea[^>]*>", out).group(0))

    def test_disabled_reaches_the_button(self) -> None:
        with render_isolated():
            out = serialize(MessageInputTool("Later", icon="star", disabled=True).render())
        assert re.search(r"<button[^>]*disabled", out)


def test_the_imperative_api_returns_client_code() -> None:
    with render_isolated():
        box = MessageInput()
        assert isinstance(box.set("x"), str) and isinstance(box.clear(), str)
        assert box.focus() == f"$bz.helpers.focusIn('{box.id}', [\"textarea\"])"


def test_the_old_name_says_the_new_one() -> None:
    with pytest.raises(ComponentUsageError, match="loading="):
        html(busy=True)
