"""Gate : l'identité de page part avec CHAQUE action, téléportée ou non.

L'état de scope ``page`` est retrouvé par ``page_id``. Le serveur le lit
dans l'en-tête ``X-Bretzel-Page-ID`` et, à défaut, **en forge un neuf**
(``render_context.py`` : ``read_header(...) or ctx.page_uuid``). Pas
d'erreur, pas de trace : l'action s'exécute sur un état vierge, écrit
dedans, et le suivant repart de zéro à son tour.

Jusqu'au 2026-08-07, cet en-tête ne voyageait QUE par le ``hx-headers``
du conteneur ``#bz-page-<uuid>``, dont HTMX hérite en remontant le DOM.
Or un panneau d'overlay est **téléporté dans ``<body>``** — donc hors de
ce conteneur. Tout handler serveur déclaré dedans (une entrée de
dropdown, un bouton de dialog ou de drawer, un pied de popover) partait
sans identité de page et perdait l'état, silencieusement.

Mesuré au navigateur sur ``/datatable_solo`` (page supprimée du
playground le 2026-08-30 ; ce fichier tire désormais sur
``/datatable``, qui porte la même envelope — l'identité de page
n'est propre à aucune page) : trois « Open » depuis le
menu d'une ligne laissaient le journal à **une** entrée, la dernière —
tandis que les mêmes trois ouvertures par clic de ligne (non téléporté)
en comptaient bien trois. ::

    open_detail (clic de ligne) page-id=e854cfa4…
    open_detail (menu ⋯)        page-id=None

Le pont portait déjà la ligne qui pose l'en-tête
(``if ($bz._pageId) …``), mais **rien n'affectait ``$bz._pageId``** :
elle était morte depuis toujours. Le fix la nourrit depuis l'envelope,
seul canal autorisé (anti-règle 3 : le runtime lit ce que le serveur lui
donne, il ne code rien en dur).

Ce fichier vérifie les deux moitiés du chemin — le serveur émet, le
runtime lit — parce qu'une seule des deux ne prouve rien : c'est
précisément d'avoir la moitié cliente sans la moitié serveur qui a fait
vivre le bug.
"""

from __future__ import annotations

import json
import re

import pytest
from starlette.testclient import TestClient

from bretzel.runtime.protocol import ENVELOPE_TAG_NAME, HEADER_PAGE_ID


@pytest.fixture(scope="module")
def client():
    from examples.playground.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def html(client) -> str:
    return client.get("/datatable",
                      headers={"Accept-Encoding": "identity"}).text


def _envelope(html: str) -> dict:
    match = re.search(
        rf"<{ENVELOPE_TAG_NAME}>(.*?)</{ENVELOPE_TAG_NAME}>", html, re.S
    )
    assert match, f"aucune <{ENVELOPE_TAG_NAME}> dans la page"
    return json.loads(match.group(1).replace(r"<", "<"))


# ── Côté serveur : l'envelope porte l'identité ────────────────────────


def test_the_envelope_carries_a_page_id(html: str) -> None:
    envelope = _envelope(html)
    assert envelope.get("page_id"), (
        "l'envelope ne porte pas de `page_id`. C'est le SEUL canal par "
        "lequel le runtime peut l'apprendre : sans lui, `$bz._pageId` "
        "reste nul, le pont ne pose pas `X-Bretzel-Page-ID`, et toute "
        "action partie d'un panneau téléporté (dropdown, dialog, drawer, "
        "popover) s'exécute sur un état de page VIERGE, sans erreur."
    )


def test_the_envelope_agrees_with_the_page_container(html: str) -> None:
    """Les deux doivent désigner la MÊME page.

    Deux identités valides mais différentes seraient pires qu'une
    absente : les actions se scinderaient en deux états selon qu'elles
    partent d'un panneau téléporté ou non, et le symptôme aurait l'air
    intermittent.
    """
    envelope_id = _envelope(html)["page_id"]
    container = re.search(r'id="bz-page-([0-9a-f]+)"', html)
    assert container, "pas de conteneur #bz-page-<uuid> dans la page"
    assert envelope_id == container.group(1), (
        f"envelope={envelope_id} mais conteneur={container.group(1)}"
    )

    # ⚠️ Le JSON d'``hx-headers`` vit dans un attribut à DOUBLES quotes
    # depuis le 2026-08-28, donc ses guillemets intérieurs sont pliés en
    # ``&quot;``. C'est la forme sur le FIL — celle que le parseur HTML
    # rend à htmx — et c'est justement ce que ce test garde.
    header = re.search(
        rf'hx-headers="{{&quot;{HEADER_PAGE_ID}&quot;: '
        rf'&quot;([0-9a-f]+)&quot;}}"',
        html,
    )
    assert header, f"pas de hx-headers portant {HEADER_PAGE_ID}"
    assert header.group(1) == envelope_id


def test_two_renders_are_two_pages(client) -> None:
    """Non-vacuité, et contrat : un id constant ferait passer les tests
    ci-dessus tout en collant deux onglets sur le même état de page."""
    first = _envelope(client.get("/datatable").text)["page_id"]
    second = _envelope(client.get("/datatable").text)["page_id"]
    assert first != second, first


# ── Côté client : le runtime le lit, le pont le pose ──────────────────
#
# Sur la SOURCE du runtime plutôt qu'au navigateur : ces deux lignes sont
# le contrat, et la suite navigateur tourne à part — donc un `pytest`
# courant ne les verrait pas. Le bug vécu était exactement la moitié
# manquante d'une paire, ce qui est décidable en lisant les deux.


def _runtime_src(name: str) -> str:
    from pathlib import Path

    import bretzel.runtime as rt

    return (Path(rt.__file__).parent / "_src" / name).read_text(encoding="utf8")


def test_the_runtime_reads_the_page_id_off_the_envelope() -> None:
    src = _runtime_src("00_index.js")
    assert re.search(r"\$bz\._pageId\s*=\s*config\.page_id", src), (
        "le boot ne lit pas `page_id` dans l'envelope — `$bz._pageId` "
        "reste nul et la ligne du pont ne fait rien. C'est l'état dans "
        "lequel le framework a vécu jusqu'au 2026-08-07."
    )


def test_the_bridge_puts_it_on_every_request() -> None:
    src = _runtime_src("05_bridge.js")
    assert HEADER_PAGE_ID in src, (
        f"le pont ne pose plus {HEADER_PAGE_ID}. L'en-tête est le seul "
        f"chemin qui survit à la téléportation d'un panneau hors du "
        f"conteneur de page."
    )
