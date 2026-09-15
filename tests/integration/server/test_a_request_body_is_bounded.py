"""Le corps d'une requête est BORNÉ, déversé sur disque, et jamais avalé.

Trois trous, un seul endroit
-----------------------------

``_read_full_body`` concaténait ce qui arrivait **jusqu'à ce que le
client s'arrête**. Aucun plafond : un seul POST faisait donc allouer au
worker autant de mémoire que l'expéditeur voulait, et
``_MAX_PART_BYTES`` n'y changeait rien — il s'applique à une PART, et
seulement une fois le corps entier déjà en mémoire.

Le tampon était en plus une liste d'octets, ce qui **annulait d'avance**
le déversement sur disque que Starlette fait pour les parts fichier : on
avait tout matérialisé avant qu'il ne le voie. Un dépôt de 30 Mio coûtait
30 Mio de RAM, dix simultanés 300.

Et quand le parse échouait, le ``except Exception`` rendait un
formulaire **vide, sans un mot**. Le handler tournait alors sur des
champs blancs et les écrivait dans l'état : la panne ne se lisait pas
comme une panne, mais comme une **saisie** — un formulaire qui s'efface
tout seul, ce qui est le pire des deux et le plus difficile à
diagnostiquer.

Ce que ce fichier mesure
-------------------------

Le plafond mord (413, et le handler ne tourne pas), le corps se relit
intégralement quand il a été déversé — le rejeu part maintenant en
PLUSIEURS messages ASGI, donc un consommateur qui s'arrêterait au
premier verrait un corps tronqué —, et un formulaire illisible refuse
l'action au lieu de l'exécuter à blanc.

⚠️ Les plafonds sont abaissés par ``monkeypatch`` : fabriquer 32 Mio à
chaque exécution coûterait plus cher que tout le reste de la suite.
``test_the_real_ceilings_are_sane`` regarde donc les vraies valeurs à
part — sans lui, cette suite resterait verte avec un plafond réglé à
zéro.
"""

from __future__ import annotations

import asyncio
import tempfile
from typing import Any

import pytest
from starlette.testclient import TestClient

from bretzel import Bretzel, page, ui
from bretzel.server.handlers import encode_action_id, sign_action
from bretzel.server.middleware import render_context as rc

_SECRET = "x" * 32

_app = Bretzel(secret_key=_SECRET, mode="dev")

#: Ce que le handler a vu. Une liste de module plutôt qu'un état : on
#: mesure ici s'il a TOURNÉ, pas ce qu'il a persisté.
RECU: list[str] = []


def enregistrer(valeur: str = "") -> None:
    RECU.append(valeur)


@page("/")
def accueil() -> None:
    ui.text("ok")


_app.include(accueil)


@pytest.fixture(scope="module")
def client():
    with TestClient(_app) as c:
        yield c


@pytest.fixture(autouse=True)
def trace_vierge():
    RECU.clear()
    yield


def _poster(client: TestClient, *, headers: dict[str, str] | None = None, **kwargs: Any):
    action_id = encode_action_id(enregistrer)
    sig = sign_action(_app.config._action_key, action_id, "")
    return client.post(
        f"/_bretzel/action/{action_id}",
        headers={"X-Bz-Sig": sig, **(headers or {})},
        **kwargs,
    )


# ───────────────────────────────────────────────────────────────────────────
# Le plafond
# ───────────────────────────────────────────────────────────────────────────


def test_the_real_ceilings_are_sane() -> None:
    """Les VRAIES valeurs, que les tests d'à côté abaissent.

    Sans ce test, un plafond réglé à zéro — ou remonté à l'infini —
    laisserait toute la suite verte : les autres cas posent la leur.
    """
    assert rc._MAX_BODY_BYTES >= 1024 * 1024, (
        "un plafond sous le mégaoctet refuserait des formulaires légitimes "
        "(un signature_pad en base64 les frôle déjà)."
    )
    assert rc._SPOOL_THRESHOLD_BYTES < rc._MAX_BODY_BYTES, (
        "un seuil de déversement au-dessus du plafond ne déverse jamais : "
        "tout resterait en mémoire, ce que le seuil existe pour éviter."
    )


def test_an_oversized_body_is_refused_and_the_handler_never_runs(
    client, monkeypatch
) -> None:
    monkeypatch.setattr(rc, "_MAX_BODY_BYTES", 1024)
    reponse = _poster(client, data={"_args": "", "valeur": "z" * 4096})
    assert reponse.status_code == 413
    # Le point qui compte : refuser tôt, c'est refuser AVANT le handler.
    assert RECU == []


def test_a_normal_action_still_goes_through(client) -> None:
    """La moitié licite — un plafond qui refuse tout ne protège rien."""
    assert _poster(client, data={"_args": "", "valeur": "bonjour"}).status_code in (
        200,
        204,
    )
    assert RECU == ["bonjour"]


# ───────────────────────────────────────────────────────────────────────────
# Le formulaire illisible
# ───────────────────────────────────────────────────────────────────────────


def test_an_unreadable_form_refuses_the_action(client) -> None:
    """Refuser, plutôt que d'exécuter le handler sur du vide.

    Le corps annonce du multipart et n'en est pas : Starlette lève. Avant,
    ça rendait ``{}`` en silence et le handler écrivait des champs blancs
    dans l'état — une panne qui se lit comme une saisie.
    """
    reponse = _poster(
        client,
        content=b"pas du tout du multipart",
        headers={"content-type": "multipart/form-data; boundary=xyz"},
    )
    assert reponse.status_code == 500
    assert "n'a pas été exécutée" in reponse.text
    assert RECU == []


# ───────────────────────────────────────────────────────────────────────────
# Le tampon lui-même : borné, déversé, relisible en entier
# ───────────────────────────────────────────────────────────────────────────


def _recevoir(morceaux: list[bytes]):
    """Un ``receive`` ASGI qui rend ``morceaux``, puis se tait."""
    restants = list(morceaux)

    async def receive() -> dict[str, Any]:
        if restants:
            return {
                "type": "http.request",
                "body": restants.pop(0),
                "more_body": bool(restants),
            }
        return {"type": "http.disconnect"}

    return receive


async def _drainer(replay) -> bytes:
    """Tout ce qu'un consommateur en aval lirait, jusqu'au bout."""
    morceaux: list[bytes] = []
    while True:
        message = await replay()
        if message["type"] != "http.request":
            break
        morceaux.append(message["body"])
        if not message.get("more_body", False):
            break
    return b"".join(morceaux)


def test_a_spilled_body_is_replayed_whole(monkeypatch) -> None:
    """Le corps déversé sur disque revient à l'octet près, en morceaux.

    Deux réglages minuscules pour forcer les deux chemins qu'un corps
    normal ne prend jamais : le basculement sur fichier, et un rejeu en
    plusieurs messages ASGI. Un consommateur qui s'arrêterait au premier
    message verrait un corps tronqué — c'est le risque exact que la
    découpe introduit.
    """
    monkeypatch.setattr(rc, "_SPOOL_THRESHOLD_BYTES", 8)
    monkeypatch.setattr(rc, "_REPLAY_CHUNK_BYTES", 16)
    corps = b"".join(bytes([i % 256]) * 37 for i in range(20))

    tampon = asyncio.run(rc._buffer_body(_recevoir([corps[:100], corps[100:]])))
    try:
        assert not tampon.too_large
        assert tampon.size == len(corps)
        assert isinstance(tampon.spool, tempfile.SpooledTemporaryFile)
        # Deux relectures INDÉPENDANTES : le parse d'abord, la route
        # ensuite. Un curseur partagé rendrait la seconde vide.
        assert asyncio.run(_drainer(rc._replay_receive(tampon))) == corps
        assert asyncio.run(_drainer(rc._replay_receive(tampon))) == corps
    finally:
        tampon.close()


def test_the_buffer_stops_at_the_ceiling(monkeypatch) -> None:
    """On cesse de LIRE au plafond — pas seulement de garder.

    Finir d'écouter un corps qu'on va refuser reviendrait à le laisser
    coûter ce qu'il voulait, ce qui est précisément la faille.
    """
    monkeypatch.setattr(rc, "_MAX_BODY_BYTES", 64)
    tampon = asyncio.run(rc._buffer_body(_recevoir([b"a" * 32, b"b" * 4096])))
    try:
        assert tampon.too_large
        assert tampon.size <= 64
    finally:
        tampon.close()


def test_the_buffer_is_closed_after_the_request(client, monkeypatch) -> None:
    """Un tampon non fermé, c'est un fichier temporaire par requête.

    Le seuil est mis à zéro pour que TOUT bascule sur disque : c'est là
    que l'oubli coûte, et c'est le seul état où on peut le constater.
    """
    monkeypatch.setattr(rc, "_SPOOL_THRESHOLD_BYTES", 0)
    ouverts: list[Any] = []
    vrai = tempfile.SpooledTemporaryFile

    def tracer(*args: Any, **kwargs: Any) -> Any:
        spool = vrai(*args, **kwargs)
        ouverts.append(spool)
        return spool

    monkeypatch.setattr(rc.tempfile, "SpooledTemporaryFile", tracer)
    assert _poster(client, data={"_args": "", "valeur": "x"}).status_code in (
        200,
        204,
    )
    assert ouverts, "aucun tampon créé — le test ne mesure rien."
    assert all(spool.closed for spool in ouverts)
