"""Deux suppressions concurrentes ne s'annulent plus, sous verrou.

Le commit par champ sauve ce qui se COMBINE : deux requêtes qui écrivent
des champs différents ne s'effacent plus, et un champ ``merge="add"``
additionne. Reste ce qui ne se combine pas — un geste qui calcule à
partir de ce qu'il a lu ::

    store.taches = [t for t in store.taches if t["id"] != cible]

Deux suppressions simultanées lisent la même liste, en retirent chacune
un élément, et la seconde écriture réintroduit celui que la première
venait d'ôter. Aucune opération de magasin ne peut résoudre ça : ce n'est
ni un ajout (``RPUSH``) ni un nombre (un écart). La seule réponse est de
ne pas les laisser se chevaucher.

Le montage est celui des autres courses de ce dossier : **deux threads,
un seul event loop**, donc deux requêtes réellement concurrentes sur le
même worker. Le ``sleep`` dans le handler force le chevauchement au lieu
de l'espérer — sans lui, les deux POST se suivraient et le bug ne se
montrerait qu'une fois sur cent.

Mesuré le 2026-09-05 : sans verrou ``a,c`` (la suppression de « a » est
perdue), avec verrou ``c``.
"""

from __future__ import annotations

import re
import threading
import time

import pytest
from starlette.testclient import TestClient

from bretzel import Bretzel, page, ui
from bretzel.server.handlers import encode_action_id, sign_action
from bretzel.state import SessionState, field

_SECRET = "x" * 32

#: Assez long pour que le chevauchement soit certain, assez court pour
#: rester sous le ``ttl`` du verrou (5 s) — au-delà, un second porteur
#: entrerait et le test mesurerait cette limite-là, pas la protection.
_LENT = 0.15

#: ⚠️ Le versant SANS verrou ne peut pas se contenter d'un ``sleep``.
#:
#: Il l'a fait jusqu'au 2026-09-05, et il rougissait **3 fois sur 6**,
#: seul, sans charge : espérer que deux requêtes se chevauchent est une
#: course, et une course perdue rendait le contrôle rouge alors que rien
#: n'était cassé. Un test instable coûte plus cher que ce qu'il garde —
#: on finit par l'ignorer, puis par ignorer ses voisins.
#:
#: La barrière rend le chevauchement CERTAIN : les deux requêtes lisent,
#: attendent l'autre, puis écrivent. La mise à jour perdue devient un
#: fait, plus un tirage.
#:
#: Elle ne sert QUE au versant sans verrou. Sous verrou elle bloquerait
#: pour de bon — le premier porteur attendrait un second qui attend le
#: verrou — donc ce versant-là garde son ``sleep``.
_BARRIERE = threading.Barrier(2, timeout=5.0)

#: Posé quand les deux requêtes se sont vraiment rejointes. Sans lui, une
#: barrière rompue passerait pour un simple échec d'assertion et le
#: message parlerait de la mise à jour perdue au lieu du harnais.
_CHEVAUCHE = threading.Event()

_app = Bretzel(secret_key=_SECRET, mode="dev")


class Kanban(SessionState):
    taches: list[dict] = field(
        default_factory=lambda: [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    )


def supprimer_sans_verrou(cible: str = "a") -> None:
    store = Kanban()
    lue = list(store.taches)  # la LECTURE, avant le rendez-vous
    try:
        _BARRIERE.wait()
        _CHEVAUCHE.set()
    except threading.BrokenBarrierError:
        # L'autre requête n'est jamais venue — le test le dira lui-même,
        # avec un message qui parle du harnais et pas de la fusion.
        pass
    store.taches = [t for t in lue if t["id"] != cible]


def supprimer_avec_verrou(cible: str = "a") -> None:
    with Kanban.lock() as store:
        time.sleep(_LENT)
        store.taches = [t for t in store.taches if t["id"] != cible]


@page("/")
def home() -> None:
    ui.text("RESTE[" + ",".join(t["id"] for t in Kanban().taches) + "]")


_app.include(home)


def _deux_suppressions(client: TestClient, handler) -> str:
    """Supprimer « a » et « b » EN MÊME TEMPS ; rendre ce qui subsiste."""
    action_id = encode_action_id(handler)
    sig = sign_action(_app.config._action_key, action_id, "")

    def poste(cible: str) -> None:
        client.post(
            f"/_bretzel/action/{action_id}",
            headers={"X-Bz-Sig": sig},
            data={"_args": "", "cible": cible},
        )

    threads = [threading.Thread(target=poste, args=(c,)) for c in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    trouve = re.search(r"RESTE\[([^\]]*)\]", client.get("/").text)
    assert trouve, "la page ne rend plus son marqueur — le montage est cassé"
    return trouve.group(1)


@pytest.fixture
def client():
    with TestClient(_app) as c:
        c.get("/")
        yield c


def test_without_the_lock_one_deletion_is_lost(client) -> None:
    """Le versant qui MORD, et il est la raison d'être du verrou.

    Sans lui, le test d'à côté pourrait passer parce que les requêtes ne
    se chevauchent pas du tout — et on croirait avoir prouvé quelque
    chose.
    """
    _BARRIERE.reset()
    _CHEVAUCHE.clear()
    reste = _deux_suppressions(client, supprimer_sans_verrou)
    assert _CHEVAUCHE.is_set(), (
        "les deux requêtes ne se sont jamais rejointes à la barrière : le "
        "harnais les a sérialisées, donc ce fichier ne mesure PAS ce qu'il "
        "croit. Ce n'est pas la fusion qui est en cause."
    )
    # ⚠️ On affirme QU'UNE suppression est perdue, pas LAQUELLE.
    #
    # Ce test a épinglé ``"a,c"`` jusqu'au 2026-09-05 et rougissait 3 fois
    # sur 6, seul : le survivant dépend de qui écrit en DERNIER, et rien
    # ne l'ordonne. ``"b,c"`` est exactement la même mise à jour perdue,
    # vue de l'autre côté. Épingler le vainqueur d'une course, c'est
    # écrire un test qui échoue sans que rien ne soit cassé — et un test
    # instable finit ignoré, avec ses voisins.
    assert reste in ("a,c", "b,c"), (
        f"reste={reste!r} : sans verrou, exactement UNE des deux "
        f"suppressions doit être perdue (deux éléments restants). "
        f"``'c'`` voudrait dire que les deux ont tenu — la mise à jour "
        f"perdue ne se produit plus et le test suivant ne prouve rien."
    )


def test_with_the_lock_both_deletions_hold(client) -> None:
    client.cookies.clear()  # une session neuve, donc l'état d'origine
    client.get("/")
    assert _deux_suppressions(client, supprimer_avec_verrou) == "c"
