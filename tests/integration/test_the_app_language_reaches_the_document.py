"""``Bretzel(lang="fr")`` arrive jusqu'à ``<html lang="fr">``.

Ce que ce fichier garde, c'est un chaînon qui a été **cassé pendant toute
la vie du projet sans que rien ne le dise** : ``render/shell.py`` porte un
paramètre ``lang`` depuis le premier jour, et personne ne le passait. Le
pipeline appelait le shell sans lui, donc toute page Bretzel expédiait
``<html lang="en">`` — apps françaises comprises, avec le défaut
d'accessibilité que ça implique (un lecteur d'écran choisit sa voix
là-dessus, et le navigateur sa coupure de mots).

Le mode de panne est instructif : **le paramètre existait, sa valeur par
défaut était juste pour l'anglais, et le test unitaire de
``default_shell`` passait** — parce qu'il appelait la fonction
directement. Rien ne testait le CHEMIN. C'est pour ça que ce test-ci part
d'un ``Bretzel(...)`` et lit le document rendu, plutôt que d'appeler le
shell : le seul endroit où le chaînon peut se rompre est entre les deux.

Le versant navigateur — que ``Intl`` nomme réellement les mois dans cette
langue — est dans ``tests/probes/probe_locale.py``. Ici on ne mesure que
ce qui est déterministe côté Python.
"""

from __future__ import annotations

import re
import sys
import types

import pytest
from fastapi.testclient import TestClient

from bretzel import Bretzel, page, ui
from bretzel.render.texts import TextsError
from bretzel.server.config import ConfigError

_HTML_TAG = re.compile(r"<html[^>]*>")


def app_saying(**config) -> Bretzel:
    """Une app d'une page, montée sous un nom de module unique.

    ``include`` prend des MODULES ; fabriquer le module ici garde le banc
    à un seul fichier au lieu d'en semer dans ``examples/``.
    """
    module = types.ModuleType(f"lang_probe_{len(sys.modules)}")

    @page("/")
    def home() -> None:
        ui.alert("bonjour", dismissible=True)

    module.home = home
    sys.modules[module.__name__] = module

    app = Bretzel(secret_key="x" * 32, **config)
    app.include(module)
    return app


def document_of(app: Bretzel) -> str:
    # Le ``with`` n'est pas décoratif : sans le cycle de vie, aucune page
    # n'est enregistrée et la requête rend 404.
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200, response.status_code
    return response.text


# ── Le chaînon ────────────────────────────────────────────────────────

def test_the_default_is_english() -> None:
    assert _HTML_TAG.search(document_of(app_saying())).group() == '<html lang="en">'


@pytest.mark.parametrize("tag", ["fr", "fr-CA", "pt-BR", "zh-Hant"])
def test_the_declared_language_reaches_the_html_tag(tag: str) -> None:
    document = document_of(app_saying(lang=tag))
    assert _HTML_TAG.search(document).group() == f'<html lang="{tag}">'


def test_a_malformed_tag_raises_at_startup() -> None:
    """``Intl`` lève sur une étiquette invalide — donc dans le navigateur,
    donc en silence côté serveur. Le refus doit tomber au démarrage."""
    for bad in ("français", "", "f", "en_US"):
        with pytest.raises(ConfigError, match="BCP-47"):
            Bretzel(secret_key="x" * 32, lang=bad)


# ── Les mots du framework ─────────────────────────────────────────────

def test_a_framework_word_follows_the_texts_table() -> None:
    english = document_of(app_saying())
    assert 'aria-label="Dismiss alert"' in english

    french = document_of(app_saying(
        lang="fr", texts={"alert.dismiss": "Fermer cette alerte"},
    ))
    assert 'aria-label="Dismiss alert"' not in french
    assert "Fermer cette alerte" in french


def test_an_unknown_text_key_raises_at_startup() -> None:
    """Pas à la page qui l'affiche : une faute de frappe dans un dict de
    traduction ne se manifeste que par une phrase restée en anglais, que
    l'auteur de la traduction ne relira jamais."""
    with pytest.raises(TextsError, match="inconnue"):
        Bretzel(secret_key="x" * 32, texts={"alert.dismis": "Fermer"})


def test_two_apps_do_not_share_a_table() -> None:
    """La table voyage par le contexte de rendu, donc par requête. Deux
    apps dans le même processus — le cas de toute la suite — ne doivent
    pas se contaminer."""
    french = app_saying(lang="fr", texts={"alert.dismiss": "Fermer"})
    english = app_saying()
    assert "Fermer" in document_of(french)
    assert 'aria-label="Dismiss alert"' in document_of(english)
    # Et dans cet ordre-là aussi : un cache global se verrait ici.
    assert "Fermer" in document_of(french)
