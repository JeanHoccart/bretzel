"""Unit tests for :class:`bretzel.components.inputs.attachments.Attachments`."""

from __future__ import annotations

import pytest

from bretzel.components.base import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.inputs.attachments import Attachments
from bretzel.components.inputs.file_upload import FileUpload
from bretzel.core.serialize import serialize

HELD = [{"name": "devis.pdf", "size": 48213, "type": "application/pdf", "href": "/pj/1"}]


def _render(**kwargs) -> str:
    with render_isolated():
        return serialize(Attachments(**kwargs).render())


def removed(key: str) -> None:
    pass


def joined(pieces=None) -> None:
    pass


class TestEmpty:
    def test_an_empty_list_hides_until_a_file_or_a_refusal(self) -> None:
        html = _render()
        assert 'bz-show="files.length &gt; 0 || errors.length &gt; 0"' in html
        assert 'style="display:none"' in html.split(">", 1)[0]

    def test_a_list_holding_server_files_shows_at_once(self) -> None:
        root = _render(files=HELD).split(">", 1)[0]
        assert "bz-show" not in root and "display:none" not in root

    def test_file_upload_never_hides_its_root(self) -> None:
        with render_isolated():
            root = serialize(FileUpload().render()).split(">", 1)[0]
        assert "bz-show" not in root


class TestCommands:
    def test_pick_dispatches_at_the_instance(self) -> None:
        with render_isolated():
            pieces = Attachments()
            command = pieces.pick()
            html = serialize(pieces.render())
        assert f"getElementById('{pieces.id}')" in command and "'bz-pick'" in command
        assert 'bz-on:bz-pick="if ($event.target === $el) pick()"' in html

    def test_clear_dispatches_at_the_instance(self) -> None:
        with render_isolated():
            assert "'bz-clear'" in Attachments().clear()

    def test_the_input_carries_a_stable_test_hook(self) -> None:
        assert "data-bz-attachments-input" in _render()


class TestDisplays:
    def test_three_presentations_render_three_lists(self) -> None:
        shapes = {d: _render(display=d, files=HELD) for d in ("chips", "strip", "grid")}
        assert len(set(shapes.values())) == 3

    def test_a_chip_has_no_thumbnail_and_no_size(self) -> None:
        chips = _render(display="chips", files=[{**HELD[0], "type": "image/png"}])
        assert "<img" not in chips and "formatSize" not in chips

    def test_an_unknown_display_is_refused(self) -> None:
        with pytest.raises(ComponentUsageError, match="display"):
            _render(display="tiles")

    def test_an_unknown_drop_host_is_refused(self) -> None:
        with pytest.raises(ComponentUsageError, match="drop"):
            _render(drop="page")


class TestServerFiles:
    def test_a_held_file_links_and_sizes(self) -> None:
        html = _render(display="strip", files=HELD)
        assert 'href="/pj/1"' in html and ">devis.pdf</a>" in html
        assert "$bz.attachments.formatSize(48213)" in html and "47 kB" in html

    def test_a_held_picture_shows_its_thumbnail(self) -> None:
        html = _render(display="grid", files=[{"name": "p.png", "type": "image/png",
                                               "href": "/p.png"}])
        assert '<img src="/p.png"' in html

    def test_no_cross_without_on_remove(self) -> None:
        assert "Remove file" not in _render(files=HELD).split("<template")[0]

    def test_on_remove_puts_a_cross_posting_the_key(self) -> None:
        held = _render(files=HELD, on_remove=removed).split("<template")[0]
        assert "Remove file" in held
        assert "hx-post" in held

    def test_a_file_needs_a_name(self) -> None:
        with pytest.raises(ComponentUsageError, match="name"):
            _render(files=[{"size": 3}])


class TestOwnSend:
    def test_a_server_on_change_posts_multipart_with_its_inputs(self) -> None:
        with render_isolated():
            pieces = Attachments(name="pieces", on_change=joined)
            root = serialize(pieces.render()).split(">", 1)[0]
        assert 'hx-encoding="multipart/form-data"' in root
        assert f'hx-include="#{pieces.id} input"' in root
        assert "watchSend()" in root

    def test_a_client_on_change_posts_nothing(self) -> None:
        root = _render(on_change="console.log(1)").split(">", 1)[0]
        assert "hx-encoding" not in root and "_bz_fields" not in root


class TestInit:
    def test_paste_and_drop_watch_their_host(self) -> None:
        root = _render(paste=True, drop="form").split(">", 1)[0]
        assert "watchPaste()" in root and "watchDrop('form')" in root


class TestFileUploadApi:
    def test_variant_is_refused_with_the_list_and_a_button(self) -> None:
        with render_isolated(), pytest.raises(ComponentUsageError, match="pick"):
            FileUpload(variant="button")

    def test_list_is_renamed_display(self) -> None:
        with render_isolated(), pytest.raises(ComponentUsageError, match="display"):
            FileUpload(list="chips")

    def test_the_dropzone_opens_the_same_picker(self) -> None:
        with render_isolated():
            html = serialize(FileUpload().render())
        assert 'bz-on:click="pick()"' in html
