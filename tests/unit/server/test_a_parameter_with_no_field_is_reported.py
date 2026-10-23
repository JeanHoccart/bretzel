"""In dev, a handler parameter that no field fills is reported, once.

``def set_search(q: str = "")`` ran with ``q=""`` when the input had lost
its ``name=`` (a ``str()`` cast on the state field): 204, nothing changed,
no message. Found by an outside build on 2026-10-22.
"""

from __future__ import annotations

from types import SimpleNamespace

from bretzel.server.routing.actions import _say_a_parameter_got_no_field


def set_search(q: str = "") -> None:
    pass


def ctx(dev: bool) -> SimpleNamespace:
    return SimpleNamespace(app=SimpleNamespace(config=SimpleNamespace(is_dev=dev)))


def test_dev_says_it_once(capsys) -> None:
    c = ctx(dev=True)
    _say_a_parameter_got_no_field(c, set_search, "q", {"query": "x", "_args": ""})
    _say_a_parameter_got_no_field(c, set_search, "q", {"query": "x"})
    out = capsys.readouterr().out
    assert out.count("WARN") == 1, out
    assert "set_search(q)" in out and "query" in out and "_args" not in out


def test_production_stays_quiet(capsys) -> None:
    _say_a_parameter_got_no_field(ctx(dev=False), set_search, "q", {"query": "x"})
    assert capsys.readouterr().out == ""
