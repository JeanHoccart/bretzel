"""L'API du kanban écrit sur le tableau du visiteur — celui qu'il regarde.

La démo : le visiteur ouvre le bouton API du bandeau, copie la commande
``curl``, la lance, et la carte apparaît sur SON tableau. Ce fichier
rejoue ce trajet sans navigateur : la clé est lue dans la page rendue,
comme le visiteur la lit, puis un second client — le terminal — s'en sert.
"""

from __future__ import annotations

import html
import re

from starlette.testclient import TestClient

from examples.kanban.main import app


def cle_affichee(page: str) -> str:
    """La clé de la commande ``curl`` du dialogue API, telle qu'affichée."""
    texte = html.unescape(re.sub(r"<[^>]+>", "", page))
    trouvee = re.search(r"Bearer (\S+?)\"", texte)
    assert trouvee, "la page n'affiche aucune commande curl avec une clé"
    assert "Invoke-RestMethod" in texte, "la page n'affiche pas la commande PowerShell"
    return trouvee.group(1)


def titres(client: TestClient) -> list[str]:
    return [carte["titre"] for carte in client.get("/api/cartes").json()]


def test_the_command_on_screen_writes_on_the_visitors_board() -> None:
    with TestClient(app) as navigateur, TestClient(app) as terminal:
        cle = cle_affichee(navigateur.get("/").text)
        reponse = terminal.post(
            "/api/cartes",
            json={"titre": "Hello from curl"},
            headers={"Authorization": f"Bearer {cle}"},
        )
        assert reponse.status_code == 201, reponse.text
        assert "Hello from curl" in titres(navigateur)
        assert "Hello from curl" in navigateur.get("/").text


def test_a_card_moves_and_an_unknown_one_is_404() -> None:
    with TestClient(app) as navigateur, TestClient(app) as terminal:
        cle = cle_affichee(navigateur.get("/").text)
        entete = {"Authorization": f"Bearer {cle}"}
        cree = terminal.post("/api/cartes", json={"titre": "À déplacer"}, headers=entete)
        ident = cree.json()["id"]
        deplacee = terminal.patch(f"/api/cartes/{ident}", json={"colonne": "fini"}, headers=entete)
        assert deplacee.json()["colonne"] == "fini"
        inconnue = terminal.patch("/api/cartes/c999", json={"colonne": "fini"}, headers=entete)
        assert inconnue.status_code == 404


def test_without_the_key_the_visitors_board_is_untouched() -> None:
    with TestClient(app) as navigateur, TestClient(app) as inconnu:
        navigateur.get("/")
        inconnu.post(
            "/api/cartes",
            json={"titre": "Carte d'un inconnu"},
            headers={"Authorization": "Bearer pas-une-cle"},
        )
        assert "Carte d'un inconnu" not in titres(navigateur)
