"""Unit tests for ``@download`` — le routable qui rend un fichier."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.responses import Response

from bretzel import Bretzel, download
from bretzel.render.decorators.download import DownloadAlreadyMarkedError


def _app(*fonctions):
    app = Bretzel(secret_key="x" * 32, mode="dev")
    for fonction in fonctions:
        app.include(fonction)
    return app


class TestFormesRendues:
    def test_a_list_of_dicts_becomes_a_csv(self) -> None:
        @download("/c.csv")
        def c() -> list[dict]:
            return [{"nom": "Ada", "ville": "Londres"}]

        with TestClient(_app(c)) as client:
            r = client.get("/c.csv")
        assert r.status_code == 200
        # BOM d'abord — sans lui Excel lit l'UTF-8 dans la page de codes
        # du système et chaque accent arrive en mojibake.
        assert r.text.startswith("﻿")
        assert "nom,ville" in r.text
        assert "Ada,Londres" in r.text

    def test_the_csv_quotes_only_what_needs_it(self) -> None:
        @download("/q.csv")
        def q() -> list[dict]:
            return [{"a": 'Dupont, "Jean"', "b": "simple"}]

        with TestClient(_app(q)) as client:
            texte = client.get("/q.csv").text
        assert '"Dupont, ""Jean"""' in texte   # cité et guillemet doublé
        assert ",simple" in texte              # pas cité pour rien

    def test_a_string_travels_as_text(self) -> None:
        @download("/n.txt")
        def n() -> str:
            return "bonjour"

        with TestClient(_app(n)) as client:
            r = client.get("/n.txt")
        assert r.text == "bonjour"

    def test_bytes_travel_untouched(self) -> None:
        @download("/b.bin")
        def b() -> bytes:
            return b"\x00\x01\x02"

        with TestClient(_app(b)) as client:
            r = client.get("/b.bin")
        assert r.content == b"\x00\x01\x02"
        assert r.headers["content-type"] == "application/octet-stream"

    def test_a_response_passes_through(self) -> None:
        """L'échappatoire doit être testée AVANT tout le reste."""
        @download("/r.dat")
        def r() -> Response:
            return Response("brut", media_type="application/x-maison")

        with TestClient(_app(r)) as client:
            reponse = client.get("/r.dat")
        assert reponse.headers["content-type"] == "application/x-maison"

    def test_an_unknown_shape_is_REFUSED(self) -> None:
        """Deviner le type d'un objet quelconque ferait télécharger
        n'importe quoi sous n'importe quel nom."""
        @download("/x.dat")
        def x() -> object:
            return object()

        with TestClient(_app(x)) as client, pytest.raises(TypeError, match="rendu un"):
            client.get("/x.dat")

    def test_an_async_function_is_awaited(self) -> None:
        @download("/a.txt")
        async def a() -> str:
            return "async"

        with TestClient(_app(a)) as client:
            assert client.get("/a.txt").text == "async"


class TestEnTetes:
    def test_the_filename_comes_from_the_path(self) -> None:
        @download("/exports/clients.csv")
        def c() -> str:
            return ""

        with TestClient(_app(c)) as client:
            entete = client.get("/exports/clients.csv").headers
        # Le DERNIER segment seulement : un nom qui porterait des barres
        # obliques laisserait chaque navigateur choisir, et ils ne
        # choisissent pas pareil.
        assert entete["content-disposition"] == 'attachment; filename="clients.csv"'

    def test_the_filename_is_overridable(self) -> None:
        @download("/x.csv", filename="rapport-2026.csv")
        def x() -> str:
            return ""

        with TestClient(_app(x)) as client:
            entete = client.get("/x.csv").headers
        assert 'filename="rapport-2026.csv"' in entete["content-disposition"]

    def test_the_csv_type_does_not_depend_on_the_MACHINE(self) -> None:
        """``mimetypes`` lit le REGISTRE sous Windows.

        Mesuré le 2026-09-02 sur une machine où Excel est installé :
        ``mimetypes.guess_type("x.csv")`` rend
        ``application/vnd.ms-excel``. Sur un serveur Linux, le même code
        rendrait ``text/csv`` — donc l'en-tête d'une réponse dépendrait
        des logiciels installés chez le développeur. C'est ce que la
        table des types connus ferme.
        """
        @download("/t.csv")
        def t() -> list[dict]:
            return [{"a": 1}]

        with TestClient(_app(t)) as client:
            assert client.get("/t.csv").headers["content-type"] == (
                "text/csv; charset=utf-8"
            )

    def test_an_explicit_media_type_wins(self) -> None:
        @download("/t.csv", media_type="text/tab-separated-values")
        def t() -> str:
            return "a\tb"

        with TestClient(_app(t)) as client:
            recu = client.get("/t.csv").headers["content-type"]
        # ``startswith`` et pas ``==`` : Starlette ajoute lui-même
        # ``; charset=utf-8`` à tout type ``text/*``. Exiger l'égalité
        # ferait rougir un comportement CORRECT — ce que ce test a fait
        # une première fois.
        assert recu.startswith("text/tab-separated-values")


class TestMarque:
    def test_two_downloads_on_one_function_are_REFUSED(self) -> None:
        """Même refus et même raison que ``@page`` : la marque vit sur
        l'objet fonction, donc la seconde écraserait la première et sa
        route deviendrait un 404 sans un mot."""
        def f() -> str:
            return ""

        download("/a.csv")(f)
        with pytest.raises(DownloadAlreadyMarkedError, match="déjà marquée"):
            download("/b.csv")(f)

    def test_a_path_without_a_leading_slash_is_REFUSED(self) -> None:
        with pytest.raises(ValueError, match="commence par"):
            download("clients.csv")

    def test_re_marking_with_the_SAME_path_is_allowed(self) -> None:
        """Réimporter un module re-décore ; refuser là serait un piège."""
        def f() -> str:
            return ""

        download("/a.csv")(f)
        download("/a.csv")(f)      # ne lève pas


def test_a_download_is_not_a_page() -> None:
    """Les deux marques ne se mélangent pas : un ``@download`` n'entre
    pas dans la table des pages, sinon le pipeline de rendu essaierait
    de lui poser une coque HTML."""
    @download("/f.csv")
    def f() -> str:
        return ""

    app = _app(f)
    assert f in app._downloads
    assert f not in app._pages
