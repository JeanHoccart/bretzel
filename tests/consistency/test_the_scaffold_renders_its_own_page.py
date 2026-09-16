"""La page que ``bretzel new`` écrit doit s'AFFICHER, pas seulement s'importer.

Ce que cette gate ferme
-----------------------

Le gabarit du scaffold posait ``on_click=lambda: ui.notification(...)``
sur son unique bouton. Le framework REFUSE les lambdas comme handlers
(``encode_handler_id`` lève ``HandlerError`` : il résout les handlers par
``sys.modules`` au moment de la requête, ce qu'une lambda ne survit pas).
Donc ``pip install bretzel && bretzel new hello && bretzel dev`` rendait
un 500 sur sa page d'accueil — le quickstart du README, de ``RELEASE.md``
et du texte d'annonce.

Rien ne l'a vu. ``tests/unit/cli/test_project.py`` vérifiait que le
projet généré **s'importe** et que son titre est le bon ; la lambda ne
lève qu'au RENDU, à l'intérieur du ``@page``, donc l'import passait.
Mesuré le 2026-09-15, en installant la roue dans un environnement neuf :
premier geste du premier utilisateur, 500.

Ce que la gate vérifie, et dans les deux sens
----------------------------------------------

- **le versant licite** : le scaffold réel rend 200 et son texte est là ;
- **le versant qui mord** : le MÊME harnais, avec le gabarit d'avant
  (une lambda), échoue. Sans lui, la gate serait verte sur un harnais
  qui n'aurait jamais monté la route — c'est exactement ce qui se passe
  si on oublie que les pages sont enregistrées au ``lifespan`` : un
  ``TestClient`` sans gestionnaire de contexte rend 404, pour tout.

La gate exécute un comportement — elle n'a ni motif ni balayage d'AST —
mais elle porte quand même sa preuve de morsure : ici elle vaut plus
qu'un plancher, puisque la population est d'un seul élément.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bretzel.cli.commands.project import create_project

#: Preuve de morsure : le harnais rougit sur le gabarit d'AVANT.
MUTATION_PROOF = "test_the_harness_would_have_caught_the_lambda"

#: Le gabarit tel qu'il était jusqu'au 2026-09-15 — conservé ici, et
#: nulle part ailleurs, pour que la gate puisse prouver qu'elle mord.
LAMBDA_TEMPLATE = '''\
from bretzel import page, ui


@page("/", title="Accueil")
def home() -> None:
    ui.button("Ça marche", on_click=lambda: ui.notification("Oui !"))
'''


def home_page_of(destination: Path, monkeypatch: pytest.MonkeyPatch) -> object:
    """Monter le projet généré et rendre sa page d'accueil.

    Deux détails font toute la valeur du harnais, et les deux ont été
    trouvés en le montant :

    - ``TestClient`` DOIT servir de gestionnaire de contexte. Les pages
      sont enregistrées au ``lifespan`` ; sans lui, tout rend 404 et la
      gate serait verte sur un 404 pris pour un succès.
    - le rapatriement des scripts tiers est débranché. En mode dev il
      part chercher quatre fichiers sur le réseau au premier appel ASGI,
      ce qui n'a rien à voir avec le sujet et rendrait la gate
      dépendante d'unpkg.
    """
    monkeypatch.syspath_prepend(str(destination))
    monkeypatch.setenv("BRETZEL_MODE", "dev")
    monkeypatch.setattr("bretzel.render.ensure_vendored", lambda: True)
    module = importlib.import_module("app.main")
    with TestClient(module.app, raise_server_exceptions=False) as client:
        return client.get("/")


def test_the_generated_page_renders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le versant licite — le premier geste du premier utilisateur."""
    destination = tmp_path / "hello"
    create_project(destination, display_name="Hello")

    response = home_page_of(destination, monkeypatch)

    assert response.status_code == 200, (
        f"la page d'accueil du scaffold rend {response.status_code}. "
        f"C'est le premier écran de quiconque installe Bretzel : "
        f"``pip install bretzel && bretzel new hello && bretzel dev``."
    )
    assert "Welcome to Bretzel" in response.text, (
        "la page rend 200 mais pas son contenu — la route existe et le "
        "corps est vide, ce qui se lit comme un succès."
    )


def test_the_harness_would_have_caught_the_lambda(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le versant qui mord : le gabarit d'avant échoue sur ce harnais.

    Il prouve les deux choses qu'on ne peut pas supposer — que la route
    est bien montée (sinon le contrôle licite serait vert sur un 404) et
    qu'un échec de rendu remonte jusqu'ici plutôt que d'être avalé.
    """
    destination = tmp_path / "avant"
    create_project(destination, display_name="Avant")
    (destination / "app/features/home.py").write_text(
        LAMBDA_TEMPLATE, encoding="utf-8"
    )

    response = home_page_of(destination, monkeypatch)

    assert response.status_code >= 500, (
        "le gabarit à lambda rend "
        f"{response.status_code} : le harnais n'observe pas le rendu, et "
        "le contrôle licite de ce fichier est vert sur rien."
    )


@pytest.fixture(autouse=True)
def forget_scaffold_modules() -> Iterator[None]:
    """Deux projets générés portent le MÊME paquet ``app``.

    Sans cette purge, le second test importerait le module du premier —
    déjà en cache — et vérifierait le mauvais gabarit.
    """
    yield
    for name in tuple(sys.modules):
        if name == "app" or name.startswith("app."):
            sys.modules.pop(name, None)
