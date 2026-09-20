"""Unit tests for ``PWA`` — la déclaration d'installabilité."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from bretzel import PWA, Bretzel, PWAIcon, page, ui
from bretzel.server.pwa import MANIFEST_ROUTE


def _app(pwa=None):
    app = Bretzel(secret_key="x" * 32, mode="dev", pwa=pwa)

    @page("/")
    def home() -> None:
        ui.text("salut")

    app.include(home)
    return app


class TestManifeste:
    def test_the_short_name_falls_back_to_the_name(self) -> None:
        assert PWA(name="Tracker").as_manifest()["short_name"] == "Tracker"

    def test_absent_keys_are_OMITTED_not_null(self) -> None:
        """``null`` est ignoré par la spec mais SIGNALÉ par les outils de
        diagnostic — et un rapport plein de faux avertissements ne se lit
        plus."""
        manifeste = PWA(name="T").as_manifest()
        assert "theme_color" not in manifeste
        assert "icons" not in manifeste
        assert None not in manifeste.values()

    def test_standalone_is_the_default(self) -> None:
        # ``browser`` annulerait la raison d'être : une fenêtre propre.
        assert PWA(name="T").as_manifest()["display"] == "standalone"

    def test_ONE_path_is_enough(self) -> None:
        """L'étage 1 : un chemin, et le framework fait le reste.

        ⚠️ La première version de cette API n'avait QUE l'étage 2, et
        elle CALQUAIT la spec — on y écrivait ``192`` deux fois, dans le
        nom du fichier et dans l'argument. Calquer une spec 1:1 donne
        une API de spec.
        """
        icones = PWA(name="T", icon="/logo.png").as_manifest()["icons"]
        assert icones == [{"src": "/logo.png", "sizes": "any",
                           "type": "image/png"}]

    def test_maskable_is_an_OPT_IN(self) -> None:
        """Déclarer ``maskable`` sur un dessin sans marge fait couper
        DEDANS. Ce n'est donc pas un défaut."""
        sans = PWA(name="T", icon="/l.png").as_manifest()["icons"][0]
        avec = PWA(name="T", icon="/l.png",
                   maskable=True).as_manifest()["icons"][0]
        assert "purpose" not in sans
        assert avec["purpose"] == "maskable"

    def test_a_square_size_is_written_ONCE(self) -> None:
        # ``PWAIcon("/i-192.png", 192)`` et pas ``"192x192"``.
        assert PWAIcon("/i.png", 192).as_dict()["sizes"] == "192x192"

    def test_a_multi_size_string_still_passes(self) -> None:
        """Ce qu'un entier ne peut pas dire : une image qui vaut à
        plusieurs tailles."""
        assert PWAIcon("/i.ico", "48x48 96x96").as_dict()["sizes"] == (
            "48x48 96x96"
        )

    def test_the_two_TIERS_cannot_be_mixed(self) -> None:
        """Les laisser coexister obligerait à inventer une règle de
        priorité que personne ne devinerait."""
        with pytest.raises(ValueError, match="both given"):
            PWA(name="T", icon="/a.png", icons=(PWAIcon("/b.png", 192),))

    def test_the_png_type_is_derived(self) -> None:
        icone = PWAIcon("/i.png", "192x192").as_dict()
        assert icone["type"] == "image/png"

    def test_maskable_travels(self) -> None:
        """Sans ``purpose``, Android pose l'icône telle quelle dans un
        carré blanc au lieu de la rogner en cercle. Ça se voit."""
        icone = PWAIcon("/i.png", "192x192", purpose="maskable").as_dict()
        assert icone["purpose"] == "maskable"

    def test_an_accented_name_is_not_escaped(self) -> None:
        assert "Métrologie" in PWA(name="Métrologie").as_json()


class TestRefus:
    def test_an_empty_name_is_REFUSED(self) -> None:
        with pytest.raises(ValueError, match="is empty"):
            PWA(name="   ")

    def test_a_relative_start_url_is_REFUSED(self) -> None:
        """Relatif, il se résoudrait contre l'emplacement du manifeste et
        ouvrirait une page que personne n'a choisie."""
        with pytest.raises(ValueError, match="begins with"):
            PWA(name="T", start_url="accueil")


class TestRoute:
    def test_no_pwa_means_NO_route_and_no_link(self) -> None:
        """Une app qui ne demande rien ne porte pas le vocabulaire."""
        with TestClient(_app(None)) as client:
            assert client.get(MANIFEST_ROUTE).status_code == 404
            assert 'rel="manifest"' not in client.get("/").text

    def test_the_manifest_is_served_with_the_SPEC_media_type(self) -> None:
        """``application/json`` ferait refuser le manifeste par les outils
        de diagnostic, sans qu'aucune erreur ne le dise."""
        with TestClient(_app(PWA(name="T"))) as client:
            reponse = client.get(MANIFEST_ROUTE)
        assert reponse.status_code == 200
        assert reponse.headers["content-type"].startswith(
            "application/manifest+json"
        )
        assert json.loads(reponse.text)["name"] == "T"

    def test_the_document_LINKS_it(self) -> None:
        # Servir le fichier ne suffit pas : aucun navigateur ne le cherche
        # de lui-même.
        with TestClient(_app(PWA(name="T"))) as client:
            html = client.get("/").text
        assert f'<link rel="manifest" href="{MANIFEST_ROUTE}"/>' in html

    def test_the_theme_colour_reaches_the_head(self) -> None:
        with TestClient(_app(PWA(name="T", theme_color="#0f172a"))) as client:
            html = client.get("/").text
        assert '<meta name="theme-color" content="#0f172a"/>' in html

    def test_the_manifest_url_cannot_diverge_from_the_declaration(self) -> None:
        """La propriété se DÉRIVE de ``pwa`` : les deux ne peuvent pas se
        contredire, là où un champ aurait pu rester posé après le retrait
        du ``pwa`` et faire lier un manifeste servi par personne."""
        assert _app(None).config._manifest_url is None
        assert _app(PWA(name="T")).config._manifest_url == MANIFEST_ROUTE
