"""Unit tests for :class:`Editor` and :class:`EditorTool`.

The server side: the frame, the bar, the hidden carrier, the first paint.
What the browser does with it (ProseMirror, the Markdown both ways, the
paste) is ``components/inputs/editor/editor.js``, measured by
``tests/runtime_js/test_an_editor_keeps_its_markdown.py``.
"""

from __future__ import annotations

import re

import pytest

from bretzel.components.base import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.feedback.badge import Badge
from bretzel.components.inputs.editor import Editor, EditorTool
from bretzel.components.inputs.editor.editor import preview_html
from bretzel.core.serialize import serialize
from bretzel.render import prosemirror_asset
from bretzel.runtime.protocol import DATA_BZ_CLIENT_DOM
from bretzel.state.scopes.client import ClientBinding


def bound(value: object = "") -> ClientBinding:
    return ClientBinding(class_name="reply", instance_key="default", field_name="text",
                         value=value)


def html(**kwargs) -> str:
    with render_isolated():
        return serialize(Editor(**kwargs).render())


def tag(out: str, marker: str) -> str:
    return re.search(rf"<[^>]*{re.escape(marker)}[^>]*>", out).group(0)


class TestTheFrame:
    def test_a_bar_above_the_text_and_a_hidden_carrier(self) -> None:
        out = html(value="Du **gras**")
        assert out.index('role="toolbar"') < out.index(DATA_BZ_CLIENT_DOM)
        carrier = tag(out, 'type="hidden"')
        assert 'value="Du **gras**"' in carrier

    def test_the_bar_holds_the_five_commands_each_named(self) -> None:
        out = html()
        commands = re.findall(r'data-bz-editor-command="([a-z_]+)"', out)
        assert commands == ["bold", "italic", "bullet_list", "ordered_list", "link"]
        for button in re.findall(r"<button[^>]*data-bz-editor-command[^>]*>", out):
            assert 'aria-label="' in button and 'aria-pressed="false"' in button

    def test_the_brick_is_named_by_the_element_never_by_the_runtime(self) -> None:
        out = html()
        src = re.search(r'data-bz-editor-src="([^"]+)"', out).group(1)
        assert src.startswith("/_bretzel/vendor/") and src.endswith(".js")
        assert prosemirror_asset().sha256[:8] in src

    def test_the_first_paint_is_formatted_not_markdown(self) -> None:
        out = html(value="- un\n- **deux**")
        assert "<ul>" in out and "<strong>deux</strong>" in out and "**" not in out.split(
            DATA_BZ_CLIENT_DOM)[1].split("</div>")[0]

    def test_an_empty_editor_says_its_placeholder(self) -> None:
        surface = tag(html(placeholder="Votre réponse"), DATA_BZ_CLIENT_DOM)
        assert 'data-empty=""' in surface
        assert 'data-bz-placeholder="Votre réponse"' in surface
        # Named by the table, never by its hint (a placeholder is not a name).
        assert 'aria-label="Text"' in surface and 'role="textbox"' in surface

    def test_disabled_marks_the_root_and_the_carrier(self) -> None:
        out = html(disabled=True)
        assert "data-disabled" in tag(out, "data-bz-editor=")
        assert re.search(r"\sdisabled(?=[\s>/=])", tag(out, 'type="hidden"'))


class TestTheValue:
    def test_a_bound_value_names_the_field_and_reads_the_store(self) -> None:
        out = html(value=bound("x"))
        assert 'name="reply.text"' in tag(out, 'type="hidden"')
        assert "$bz.state.reply.default.text" in tag(out, "data-bz-editor=")

    def test_name_wins_over_nothing(self) -> None:
        assert 'name="reply"' in tag(html(name="reply"), 'type="hidden"')

    def test_a_component_is_refused_as_value_nowhere_else(self) -> None:
        with render_isolated(), pytest.raises(ComponentUsageError):
            Editor(placeholder=bound())

    def test_commands_return_client_expressions(self) -> None:
        with render_isolated():
            editor = Editor()
            for expression in (editor.set("a"), editor.clear(), editor.insert("**b**"),
                               editor.focus(), editor.blur()):
                assert isinstance(expression, str) and expression
            assert "bz-insert" in editor.insert("**b**")


class TestVariants:
    def test_surface_frames_and_ghost_does_not(self) -> None:
        surface = tag(html(), "data-bz-editor=")
        ghost = tag(html(variant="ghost"), "data-bz-editor=")
        assert "bg-interface" in surface and "border-line" in surface
        assert "bg-interface" not in ghost and "border-line" not in ghost
        assert "[[data-bz-keyboard]_" in ghost

    def test_another_word_is_refused(self) -> None:
        with render_isolated(), pytest.raises(ComponentUsageError):
            Editor(variant="outline").render()


class TestTools:
    def test_a_tool_goes_to_the_bar_after_a_rule(self) -> None:
        with render_isolated():
            with Editor() as editor:
                EditorTool("Demander à Claude", icon="sparkles")
            out = serialize(editor.render())
        bar = out.split(DATA_BZ_CLIENT_DOM)[0]
        assert 'aria-label="Demander à Claude"' in bar
        assert bar.index('data-bz-editor-command="link"') < bar.index("Demander à Claude")

    def test_an_editor_switched_off_switches_its_tools_off(self) -> None:
        with render_isolated():
            with Editor(disabled=True) as editor:
                EditorTool("Outil", icon="plus")
            out = serialize(editor.render())
        assert re.search(r'<button[^>]*aria-label="Outil"[^>]*\sdisabled', out)

    def test_anything_else_inside_is_refused(self) -> None:
        with render_isolated():
            with Editor() as editor:
                Badge("pas un outil")
            with pytest.raises(ComponentUsageError, match=r"ui.editor_tool"):
                editor.render()

    def test_a_tool_needs_its_label_and_its_icon(self) -> None:
        with render_isolated(), pytest.raises(ComponentUsageError):
            EditorTool("", icon="plus")
        with render_isolated(), pytest.raises(ComponentUsageError):
            EditorTool("Outil", icon="")


class TestThePreview:
    def test_markup_and_script_links_stay_out(self) -> None:
        out = preview_html("<script>x</script> [a](javascript:alert(1))")
        # mistune 3.2 drops the link, 3.4 leaves its source as plain text:
        # either way nothing can run — no tag, no javascript: href.
        assert "<script>" not in out and 'href="javascript:' not in out

    def test_what_the_editor_does_not_show_stays_text(self) -> None:
        out = preview_html("## Titre\n\n> citation")
        assert "<h2>" not in out and "<blockquote>" not in out
        assert "## Titre" in out
