"""Un ``<input type="file" multiple>`` livre TOUS ses fichiers au handler.

Le défaut, trouvé en joignant des pièces au fil de l'atelier du cockpit
(2026-09-27) : le formulaire multipart était lu dans un ``dict``, qui
garde une valeur par nom — la dernière. Or un champ fichier multiple
envoie une part par fichier sous UN seul nom : on en choisissait trois,
le handler en recevait un, et les deux autres disparaissaient sans un
mot.

Les deux versants : plusieurs fichiers arrivent en liste, et un seul
fichier reste un fichier — sans quoi chaque handler de dépôt simple
existant (``def importer(fichier)`` qui lit ``fichier.file``) casserait.
Un champ texte répété reste « le dernier gagne », comme dans la branche
urlencoded : ce test le garde aussi, pour qu'un correctif trop large ne
change pas le type d'un champ que personne n'a déclaré multiple.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from starlette.testclient import TestClient

from bretzel import Bretzel, page, ui
from bretzel.server.handlers import FIELDS_TOKEN, encode_action_id, sign_action
from tests._session import session_of

_SECRET = "y" * 32

_app = Bretzel(secret_key=_SECRET, mode="dev")

#: What the handler saw, per call.
RECU: list[Any] = []


def deposer(pieces: Any = None, note: str = "") -> None:
    if isinstance(pieces, list):
        RECU.append(([p.filename for p in pieces], note))
    else:
        RECU.append((getattr(pieces, "filename", None), note))


@page("/")
def accueil() -> None:
    # Le vrai champ : depuis le 2026-10-27, un fichier n'est pris que dans
    # un champ que le jeton du formulaire déclare.
    with ui.form(on_submit=deposer):
        ui.file_upload(name="pieces", multiple=True)
        ui.input(name="note")


_app.include(accueil)


@pytest.fixture(scope="module")
def client():
    with TestClient(_app) as c:
        yield c


@pytest.fixture(autouse=True)
def trace_vierge():
    RECU.clear()
    yield


def _poster(client: TestClient, **kwargs: Any):
    """Le POST du formulaire de la page, son jeton compris."""
    action_id = encode_action_id(deposer)
    sig = sign_action(_app.config._action_key, action_id, "", session_id=session_of(client))
    jeton = re.search(rf'name="{FIELDS_TOKEN}" value="([^"]+)"',
                      client.get("/").text).group(1)
    kwargs["data"] = {**kwargs.get("data", {}), FIELDS_TOKEN: jeton}
    return client.post(f"/_bretzel/action/{action_id}",
                       headers={"X-Bz-Sig": sig}, **kwargs)


def test_several_files_arrive_as_a_list(client) -> None:
    reponse = _poster(client, data={"_args": ""}, files=[
        ("pieces", ("maquette.png", b"png", "image/png")),
        ("pieces", ("devis.pdf", b"pdf", "application/pdf")),
        ("pieces", ("taches.csv", b"a,b", "text/csv")),
    ])
    assert reponse.status_code in (200, 204), reponse.text
    assert RECU == [(["maquette.png", "devis.pdf", "taches.csv"], "")], (
        "le handler n'a pas reçu tous les fichiers du champ multiple."
    )


def test_one_file_stays_a_file(client) -> None:
    _poster(client, data={"_args": ""},
            files=[("pieces", ("seul.png", b"png", "image/png"))])
    assert RECU == [("seul.png", "")]


def test_a_repeated_text_field_keeps_the_last(client) -> None:
    _poster(client, data={"_args": "", "note": ["premiere", "derniere"]},
            files=[("pieces", ("seul.png", b"png", "image/png"))])
    assert RECU == [("seul.png", "derniere")]
