"""La règle ``topic-half-wired`` : un sujet branché d'un seul côté fige l'écran."""

from __future__ import annotations

import ast
from pathlib import Path

from bretzel.lint.corpus import Module, bound
from bretzel.lint.rules import topics

_DECLARE = 'from bretzel.state import Topic\nCALENDAR = Topic("calendar")\n'


def _module(name: str, source: str) -> Module:
    return Module(Path(name), ast.parse(source), source)


def _findings(*modules: Module) -> list:
    with bound(modules):
        return [f for module in modules for f in topics.check(module)]


def test_a_topic_read_and_written_is_silent() -> None:
    assert not _findings(_module("a.py", _DECLARE + (
        "@reads(CALENDAR)\ndef read(): ...\n@writes(CALENDAR)\ndef write(): ...\n"
    )))


def test_reads_and_writes_are_seen_across_files() -> None:
    assert not _findings(
        _module("a.py", _DECLARE + "@reads(CALENDAR)\ndef read(): ...\n"),
        _module("b.py", "from a import CALENDAR\n@writes(CALENDAR)\ndef write(): ...\n"),
    )


def test_a_refresh_counts_as_a_write() -> None:
    assert not _findings(_module("a.py", _DECLARE + (
        "@reads(CALENDAR)\ndef read(): ...\ndef again():\n    refresh(CALENDAR)\n"
    )))


def test_a_refresh_in_a_loop_counts_as_a_write() -> None:
    assert not _findings(_module("a.py", _DECLARE + (
        "@reads(CALENDAR)\ndef read(): ...\n"
        "def everything():\n    for topic in (CALENDAR,):\n        refresh(topic)\n"
    )))


def test_an_imported_alias_is_followed() -> None:
    assert not _findings(
        _module("a.py", _DECLARE + "@reads(CALENDAR)\ndef read(): ...\n"),
        _module("b.py", "from a import CALENDAR as C\n@writes(C)\ndef write(): ...\n"),
    )


def test_a_topic_never_written_is_reported_where_it_is_declared() -> None:
    found = _findings(_module("a.py", _DECLARE + "@reads(CALENDAR)\ndef read(): ...\n"))
    assert len(found) == 1
    assert found[0].rule == "topic-half-wired"
    assert found[0].line == 2
    assert "never redraw" in found[0].message


def test_a_topic_never_read_is_reported() -> None:
    found = _findings(_module("a.py", _DECLARE + "@writes(CALENDAR)\ndef write(): ...\n"))
    assert len(found) == 1 and "no zone redraws" in found[0].message


def test_an_unused_topic_is_reported() -> None:
    found = _findings(_module("a.py", _DECLARE))
    assert len(found) == 1 and "declared" in found[0].message


def test_a_module_named_writes_is_not_a_decorator() -> None:
    """Admin importe un module ``writes`` : ``writes.invite(X)`` n'écrit pas X."""
    found = _findings(_module("a.py", _DECLARE + (
        "@reads(CALENDAR)\ndef read(): ...\ndef act():\n    writes.invite(CALENDAR)\n"
    )))
    assert len(found) == 1 and "never redraw" in found[0].message
