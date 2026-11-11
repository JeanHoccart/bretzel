"""Gate : deux éléments vivants d'une page ne partagent jamais un ``id``.

Mesuré le 2026-11-06 : deux ``ui.input(id="dup")`` se rendaient sans un
mot, et ``getElementById`` / un ``for=`` / ``.open()`` / ``.set()`` / une
cible htmx n'atteignent alors que le PREMIER. En posant la vérification
sur toutes les pages des apps, deux défauts du framework sont sortis :

- une table SANS clé de ligne nommait chaque ``<tr>``
  ``<table>__row_<table>`` (elle lisait son propre segment comme clé) —
  la dette ``/sparkline`` du playground, et une page de la doc ;
- des zones ``@refreshable`` fabriquées par une usine partageaient le nom
  de leur fonction, donc leur ``id`` ET leur entrée dans le registre des
  zones : rafraîchir l'une redessinait la première avec le contenu de la
  dernière. ``@refreshable(name=…)`` fixe désormais l'``id``.

La vérification vit sur l'arbre FINAL de la page (``render/ids.py``), en
dev : une page peut construire un composant une seconde fois pour montrer
son HTML en texte (le playground), et le contenu d'un ``<template>`` est
inerte tant que le runtime ne l'a pas cloné.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from bretzel import Bretzel, page, refreshable, ui
from bretzel.components.base import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.data.table import Table, column
from bretzel.core.serialize import serialize
from bretzel.core.tree import Element, TextNode
from bretzel.render.ids import refuse_duplicate_ids

_SECRET = "s" * 32


def _app(mode: str, body) -> Bretzel:
    app = Bretzel(secret_key=_SECRET, mode=mode)

    @page("/")
    def home() -> None:
        body()

    app.include(home)
    return app


def _dup() -> None:
    ui.input(id="dup")
    ui.input(id="dup")


def test_a_page_in_dev_refuses_an_id_written_twice() -> None:
    with (TestClient(_app("dev", _dup), raise_server_exceptions=True) as client,
          pytest.raises(ComponentUsageError, match="id='dup' on 2 elements")):
        client.get("/")


def test_production_keeps_serving() -> None:
    """Dev seulement : une app qui avait un doublon inoffensif ne tombe
    pas en production à la mise à jour ; elle le voit en dev."""
    with TestClient(_app("prod", _dup)) as client:
        assert client.get("/").status_code == 200


def test_what_is_not_live_does_not_count() -> None:
    """Le contenu d'un ``<template>`` (inerte) et du texte (le HTML qu'une
    page AFFICHE) ne sont pas des éléments vivants."""
    live = Element(tag="div", attrs={"id": "x"}, children=())
    inert = Element(tag="template", attrs={}, children=(
        Element(tag="div", attrs={"id": "x"}, children=()),))
    shown = Element(tag="pre", attrs={}, children=(TextNode('<div id="x">'),))
    refuse_duplicate_ids([live, inert, shown])
    with pytest.raises(ComponentUsageError):
        refuse_duplicate_ids([live, live])


def test_a_keyless_table_does_not_name_its_rows() -> None:
    """Une ligne est nommée par SA clé ; sans clé, pas d'``id`` du tout —
    et surtout pas le même sur toutes."""
    with render_isolated():
        html = serialize(Table(
            columns=[column("a", label="A")],
            rows=[{"a": 1}, {"a": 2}, {"a": 3}],
        ).render())
    assert "__row_" not in html
    with render_isolated():
        keyed = serialize(Table(
            columns=[column("a", label="A")],
            rows=[{"id": 1, "a": 1}, {"id": 2, "a": 2}],
        ).render())
    assert keyed.count("__row_") == 2


class _First:
    pass


class _Second:
    pass


def _zone_factory(state: type, *, named: bool):
    if named:
        @refreshable(name=f"factory_{state.__name__}")
        def zone() -> None:
            ui.text(state.__name__)
    else:
        @refreshable
        def zone() -> None:
            ui.text(state.__name__)
    return zone


def test_named_zones_from_one_factory_get_their_own_id() -> None:
    first = _zone_factory(_First, named=True)
    second = _zone_factory(_Second, named=True)
    assert first.id != second.id
    # Sans nom, la même fonction : le même id — c'est ce que la page
    # refuse en dev, avec le conseil dans le message.
    a, b = _zone_factory(_First, named=False), _zone_factory(_Second, named=False)
    assert a.id == b.id

    def body() -> None:
        a()
        b()

    with (TestClient(_app("dev", body), raise_server_exceptions=True) as client,
          pytest.raises(ComponentUsageError, match=r"@refreshable\(name=")):
        client.get("/")
