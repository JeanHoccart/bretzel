"""Unit tests for :class:`Message` and :class:`MessageList` — a conversation,
whoever speaks in it."""

from __future__ import annotations

import re

import pytest

from bretzel.components.base import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.data.message import Message, MessageList
from bretzel.components.primitives.icon import Icon
from bretzel.components.primitives.text import Text
from bretzel.core.serialize import serialize
from bretzel.state.scopes.client import ClientBinding


def bound(field: str, value: object) -> ClientBinding:
    return ClientBinding(class_name="answer", instance_key="default", field_name=field,
                         value=value)


def retry() -> None: ...


def html(*args, **kwargs) -> str:
    with render_isolated():
        return serialize(Message(*args, **kwargs).render())


class TestWhereAndWho:
    def test_the_others_speak_on_the_start_side_by_default(self) -> None:
        out = html("Salut")
        assert 'data-side="start"' in out and "bg-text/5" in out
        assert 'aria-label="Message"' in out

    def test_mine_sit_on_the_end_side_in_the_accent(self) -> None:
        out = html("Bonjour", side="end")
        assert 'data-side="end"' in out and "bz-c-primary" in out
        assert 'aria-label="Your message"' in out

    def test_the_sides_are_logical_and_staggered(self) -> None:
        out = html("x")
        assert "data-[side=start]:pe-[15%]" in out and "data-[side=end]:ps-[15%]" in out

    def test_the_author_is_shown_and_names_the_message(self) -> None:
        out = html("Salut", author="Marie")
        assert ">Marie</span>" in out and 'aria-label="Message from Marie"' in out

    def test_an_avatar_string_is_initials_a_component_is_itself(self) -> None:
        assert ">MA</span>" in html("x", avatar="MA")
        with render_isolated():
            out = serialize(Message("x", avatar=Icon("sparkles")).render())
        # The chip's classes as a SET: their order in ``class=`` paints
        # nothing (the avatar's size comes from the base composer since
        # 2026-11-06, before its shape).
        chips = [set(c.split()) for c in re.findall(r'class="([^"]*)"', out)]
        assert "lucide:sparkles" in out and any(
            {"rounded-full", "h-8", "w-8"} <= c for c in chips
        ), "an icon is a chip"

    def test_an_avatar_address_is_a_photo(self) -> None:
        assert 'src="/photos/marie.png"' in html("x", avatar="/photos/marie.png")

    def test_no_avatar_no_empty_place(self) -> None:
        assert "size-8" not in html("x")


class TestWhatItSays:
    def test_the_text_is_kept_as_typed_by_default(self) -> None:
        out = html("One\n**two**")
        assert "**two**" in out and "<strong" not in out and "whitespace-pre-wrap" in out

    def test_markdown_is_asked(self) -> None:
        assert "<strong" in html("**12 %**", markdown=True)

    def test_plain_has_no_bubble(self) -> None:
        out = html("Une réponse", variant="plain")
        assert "rounded-box" not in out and "Une réponse" in out

    def test_what_someone_wrote_is_never_read_as_code(self) -> None:
        out = html("a && b == c", author="x && y")
        assert "a &amp;&amp; b == c" in out and "bz-text" not in out

    def test_files_are_chips_above_the_text(self) -> None:
        out = html("Here", side="end", files=["a.pdf", "b.png"])
        assert out.index("a.pdf") < out.index("Here") and "lucide:file-text" in out

    def test_no_text_renders_no_empty_paragraph(self) -> None:
        out = html(side="end", files=["only.pdf"])
        assert "only.pdf" in out and "<p" not in out

    def test_children_go_under_the_text(self) -> None:
        with render_isolated():
            msg = Message("Done.")
            with msg:
                Text("24 pupils added")
            out = serialize(msg.render())
        assert out.index("Done.") < out.index("24 pupils added")


class TestWhereItStands:
    def test_writing_shows_a_spinner_in_a_live_region(self) -> None:
        out = html("Looking", writing=True)
        assert 'role="status"' in out and 'aria-live="polite"' in out
        assert "aria-live" not in html("Done")

    def test_bound_text_is_plain_and_follows_its_field(self) -> None:
        out = html(bound("text", "Bonj"), markdown=True, writing=bound("busy", True))
        assert 'bz-text="$bz.state.answer.default.text"' in out
        assert 'bz-show="$bz.state.answer.default.busy"' in out

    def test_time_and_sending_under_the_words(self) -> None:
        out = html("x", time="14:02", status="sending")
        assert ">14:02</span>" in out and "Sending…" in out

    def test_an_error_is_said_as_an_alert(self) -> None:
        out = html("x", status="error")
        assert re.search(r'role="alert"[^>]*>Not sent<', out)


class TestActions:
    def test_copyable_copies_the_text(self) -> None:
        out = html("Le texte", copyable=True)
        assert "$bz.verbs.copy(&quot;Le texte&quot;)" in out and 'aria-label="Copy"' in out

    def test_on_retry_adds_the_button_and_relays_the_event(self) -> None:
        with render_isolated():
            out = serialize(Message("x", status="error", on_retry=retry).render())
        assert 'aria-label="Retry"' in out and "$dispatch('retry')" in out
        assert 'hx-trigger="retry"' in out

    def test_no_action_no_foot(self) -> None:
        assert "lucide:copy" not in html("x") and "rotate-ccw" not in html("x")


class TestTheList:
    def thread(self) -> str:
        with render_isolated():
            lst = MessageList()
            with lst:
                Message("Bonjour", side="end")
                Message("Salut", author="Marie", avatar="MA")
                Message("Ça va ?", author="Marie", avatar="MA")
                Message("Oui", side="end")
            return serialize(lst.render())

    def test_it_is_a_log_that_scrolls_itself(self) -> None:
        out = self.thread()
        assert 'role="log"' in out and 'aria-label="Conversation"' in out
        assert "overflow-y-auto" in out and "data-bz-message-list" in out

    def test_a_follower_of_the_same_author_is_grouped(self) -> None:
        out = self.thread()
        assert out.count('data-grouped="true"') == 1
        assert out.count(">Marie</span>") == 1, "the name is not repeated"
        assert out.count(">MA</span>") == 1, "nor the avatar — its place stays"

    def test_it_offers_a_way_back_to_the_latest_message(self) -> None:
        out = self.thread()
        assert "data-bz-message-list-bottom" in out
        assert 'aria-label="Back to the latest message"' in out


@pytest.mark.parametrize("bad", [{"side": "left"}, {"variant": "card"}, {"status": "read"}])
def test_a_closed_choice_refuses_another_word(bad) -> None:
    with render_isolated(), pytest.raises(ComponentUsageError, match=next(iter(bad))):
        Message("Hi", **bad).render()
