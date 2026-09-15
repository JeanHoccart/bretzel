"""Gate : les réponses sont compressées — sauf le flux SSE, jamais.

Le HTML de Bretzel est répétitif par construction : la même chaîne de
classes Tailwind sur chaque instance d'un composant, la même expression
``bz-*`` sur chaque contrôle du même genre. Mesuré le 2026-08-07 sur
``/datatable`` du playground : **9 085 attributs ``class`` pour 328
chaînes distinctes** (97 % de doublons), et ``class=`` + ``bz-*`` font à
eux deux ~80 % des octets de n'importe quelle page.

Résultat : **1 334 Ko → 91 Ko**, pour 5,9 ms de CPU contre 113 ms de
rendu. Rien ne l'était avant — l'en-tête ``Content-Encoding`` était
purement absent.

**Le second test est celui qui compte.** Compresser le flux SSE ne le
ralentirait pas : il le CASSERAIT, en silence.
``GZipResponder.apply_compression`` ne vide le tampon zlib qu'au dernier
chunk (``if not more_body: close()``), et une réponse ``text/event-stream``
n'a pas de dernier chunk. Chaque événement resterait donc retenu dans le
tampon, indéfiniment. Pas d'erreur, pas de trace : le realtime
s'arrêterait, c'est tout.

Starlette 1.3 l'exclut déjà, **par type de contenu**
(``DEFAULT_EXCLUDED_CONTENT_TYPES``) — ce qui vaut mieux qu'une
exclusion par chemin, puisque ça couvre aussi un flux SSE qu'une app
exposerait ailleurs. Un middleware maison a d'ailleurs été écrit ici
puis SUPPRIMÉ le jour même, une fois la mesure faite : il redisait ce
que la dépendance garantissait déjà.

Mais on en DÉPEND. Un défaut de dépendance qui change de version en
version sans qu'on le sache est précisément ce qu'une gate est là pour
attraper — d'où ce fichier, qui teste la garantie plutôt que de la
supposer.
"""

from __future__ import annotations

import asyncio

import pytest
from starlette.testclient import TestClient

from starlette.middleware.gzip import GZipMiddleware


@pytest.fixture(scope="module")
def client():
    from examples.playground.main import app

    with TestClient(app) as c:
        yield c


# ── 1. Les pages sont compressées ─────────────────────────────────────


def test_a_page_ships_compressed(client) -> None:
    r = client.get("/datatable", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers.get("content-encoding") == "gzip", (
        "la réponse part en clair. Le HTML de ce framework est répétitif "
        "par construction, donc il tombe d'un facteur ~15 : ne pas le "
        "compresser multiplie par 15 ce qui passe sur le fil, pour "
        "économiser 6 ms de CPU."
    )
    wire = int(r.headers["content-length"])
    plain = len(r.text.encode())
    assert plain / wire > 5, (
        f"{plain} octets rendus pour {wire} sur le fil — soit "
        f"{plain / wire:.1f}×. Sur une page de ce dépôt on attend plutôt "
        f"15× ; un ratio faible veut dire que la compression s'applique "
        f"à autre chose que le HTML attendu."
    )


def test_a_client_that_does_not_ask_gets_plain_bytes(client) -> None:
    """``Accept-Encoding: identity`` doit rester servi tel quel."""
    r = client.get("/datatable", headers={"Accept-Encoding": "identity"})
    assert r.headers.get("content-encoding") is None


def test_a_tiny_response_is_left_alone(client) -> None:
    """Sous le seuil, l'en-tête et le tampon coûtent plus qu'ils ne rendent."""
    r = client.get("/_bretzel/does-not-exist",
                   headers={"Accept-Encoding": "gzip"})
    if len(r.content) < 500:
        assert r.headers.get("content-encoding") is None


# ── 2. Le flux SSE n'est JAMAIS compressé ─────────────────────────────
#
# Testé sur le MIDDLEWARE et non sur une requête réelle : une réponse
# ``text/event-stream`` ne se termine jamais, donc `TestClient` reste
# bloqué à la sortie du contexte de stream (constaté : le test pendait
# jusqu'au timeout). L'invariant, lui, est une décision de routage —
# décidable sans ouvrir de flux, et c'est exactement ce qu'on veut
# épingler.


class _Recorder:
    """Une app ASGI minimale, du type de contenu qu'on lui demande."""

    def __init__(self, content_type: bytes) -> None:
        self.called = False
        self.content_type = content_type

    async def __call__(self, scope, receive, send) -> None:
        self.called = True
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", self.content_type)]})
        # Répété : au-dessus du seuil, et surtout assez compressible pour
        # que l'absence de compression se voie dans la taille.
        await send({"type": "http.response.body",
                    "body": b": bretzel-sse-open\n\n" * 40,
                    "more_body": False})


async def _drive(mw, path: str) -> list:
    sent: list = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        sent.append(msg)

    await mw({"type": "http", "path": path, "method": "GET",
              "headers": [(b"accept-encoding", b"gzip")]}, receive, send)
    return sent


def test_the_sse_path_bypasses_compression_entirely() -> None:
    """L'invariant coûteux — et il appartient à une DÉPENDANCE.

    ``GZipResponder.apply_compression`` ne vide son tampon zlib qu'au
    dernier chunk (``if not more_body: close()``). Un flux SSE n'a pas de
    dernier chunk : chaque événement resterait retenu, indéfiniment,
    sans erreur ni trace. Le realtime s'arrêterait, c'est tout.

    Starlette nous protège via ``DEFAULT_EXCLUDED_CONTENT_TYPES``. On le
    vérifie au lieu de le croire : c'est un défaut de bibliothèque, donc
    il peut bouger sans que ce dépôt en soit averti.
    """
    inner = _Recorder(b"text/event-stream")
    mw = GZipMiddleware(inner, minimum_size=0, compresslevel=6)
    sent = asyncio.run(_drive(mw, "/_bretzel/sse"))

    assert inner.called
    start = next(m for m in sent if m["type"] == "http.response.start")
    encodings = [v for k, v in start["headers"]
                 if k.lower() == b"content-encoding"]
    assert not encodings, (
        f"le flux SSE part avec {encodings} — il doit rester en clair."
    )
    body = b"".join(m.get("body", b"") for m in sent
                    if m["type"] == "http.response.body")
    assert body.startswith(b": "), body[:16]
    # ``1f 8b`` est le nombre magique d'un flux gzip — s'il apparait
    # ici, l'evenement est parti compresse (donc, en pratique, pas
    # parti du tout).
    assert not body.startswith(bytes([0x1F, 0x8B])), (
        "en-tete gzip sur un flux SSE"
    )


def test_a_normal_path_does_go_through_compression() -> None:
    """La contre-épreuve : sans elle, un middleware qui ne compresse
    RIEN passerait le test ci-dessus."""
    inner = _Recorder(b"text/html; charset=utf-8")
    mw = GZipMiddleware(inner, minimum_size=0, compresslevel=6)
    sent = asyncio.run(_drive(mw, "/une-page"))
    start = next(m for m in sent if m["type"] == "http.response.start")
    encodings = [v for k, v in start["headers"]
                 if k.lower() == b"content-encoding"]
    assert encodings == [b"gzip"], (
        f"un chemin ordinaire n'est PAS compressé (encodings={encodings}) — "
        f"la gate SSE ci-dessus ne prouverait alors plus rien."
    )
