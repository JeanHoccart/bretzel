"""Le port d'un banc — libre, jamais écrit en dur.

Pourquoi ce fichier existe
---------------------------

``-m probes`` tournait **strictement séquentiel**, et ça coûtait 17 min
pour 84 probes. La raison n'était pas le navigateur : c'était que **60
probes sur 84 codaient leur port en dur**, et que dix de ces ports
servaient deux ou trois bancs différents. Deux probes lancés en même
temps sur ``:8973`` se marchent dessus, donc un ``xdist_group`` épinglait
les 84 sur un worker unique pour protéger une poignée de collisions.

Mesuré le 2026-09-13, avant : le socle d'un probe — import du harnais
2,1 s, serveur 0,3 s, contexte Chromium 1,25 s, première page ~1,8 s —
fait **5,4 s avant la première assertion**. Multiplié par 84 et pris en
série, c'est 7,5 min des 17 passés à se mettre en place.

Ce que ça remplace
-------------------

Chaque probe portait la même dizaine de lignes : une constante ``BASE``
avec un port littéral, un ``wait_server()`` qui sonde ce port, un
``subprocess.Popen`` du banc, un ``kill`` dans un ``finally``. C'est le
même genre de recopie que ``bretzel/probe/`` a supprimé ailleurs, et
``test_probe_boilerplate_only_shrinks`` en tient le compte.

⚠️ **Le port est choisi par le PARENT, pas par le banc.** L'inverse — le
banc prend un port libre et l'annonce sur sa sortie — oblige le parent à
lire un flux qu'il veut par ailleurs jeter (les bancs sont lancés en
``DEVNULL`` pour que leur journal ne noie pas le diagnostic du probe).
Choisir avant de lancer garde le parent maître de ce qu'il attend.

⚠️ **Une fenêtre de course subsiste**, et elle est assumée : entre le
moment où l'on referme la socket d'essai et celui où uvicorn se lie, un
autre processus peut prendre le port. C'est la même fenêtre que
``tests/audit/harness._find_free_port``, elle vaut quelques
millisecondes, et l'alternative — un registre de ports partagé entre
workers — coûterait plus cher que ce qu'elle protège. Un port FIXE, lui,
est une collision certaine dès qu'on parallélise.
"""

from __future__ import annotations

import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent


def free_port() -> int:
    """Un port libre, demandé au système plutôt que deviné."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def bench_port(default: int) -> int:
    """Le port qu'un banc doit servir : celui du parent, sinon le sien.

    Le défaut historique est gardé pour que ``py tests/probes/bench_x.py``
    lancé à la main réponde toujours à l'adresse que sa docstring annonce.
    Sous un probe, l'argument gagne — et c'est lui qui rend deux bancs
    simultanés possibles.

    ⚠️ **L'argument doit RESSEMBLER à un port**, et ce n'est pas de la
    prudence gratuite : un banc peut être IMPORTÉ au lieu d'être lancé —
    ``test_a_bench_never_steals_a_page`` les importe tous pour vérifier
    qu'aucun ne vole une page du playground — et il hérite alors de
    l'``argv`` du processus hôte, qui n'a aucune raison d'être un nombre.
    Un ``int(sys.argv[1])`` nu levait là-dessus (mesuré le 2026-09-13 :
    ``invalid literal for int(): 'C:\\Users\\…\\bretzel'``), et le
    diagnostic arrivait sous la forme d'une gate sans rapport.
    """
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
        if 1 <= port <= 65535:
            return port
    return default


@contextmanager
def bench(script: str, *, timeout: float = 20.0) -> Iterator[str]:
    """Lance un banc sur un port libre et rend son URL de base.

    Le banc est tué à la sortie, y compris si le probe lève : c'est ce
    ``finally`` que chaque probe réécrivait, et l'oublier laisse un
    uvicorn vivant qui fera échouer le probe SUIVANT sur le même port —
    un mode d'échec qui se lit comme un défaut du composant.
    """
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    server = subprocess.Popen(
        [sys.executable, str(HERE / script), str(port)],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if server.poll() is not None:
                raise RuntimeError(
                    f"{script} s'est arrêté avant de servir (code "
                    f"{server.returncode}). Relance-le à la main pour voir "
                    f"son erreur : py tests/probes/{script}"
                )
            try:
                with urllib.request.urlopen(base + "/", timeout=1):
                    break
            except OSError:
                time.sleep(0.15)
        else:
            raise RuntimeError(f"{script} n'a pas répondu sur {base} en {timeout}s")
        yield base
    finally:
        server.kill()
        server.wait(timeout=5)


# ───────────────────────────────────────────────────────────────────────────
# Les scripts tiers, rapatriés
# ───────────────────────────────────────────────────────────────────────────


def use_local_tailwind() -> bool:
    """Rapatrier les quatre scripts tiers, une fois par machine.

    Pourquoi un banc s'en soucie
    -----------------------------
    En mode dev, le compilateur Tailwind travaille DANS la page et vient
    de chez unpkg — 276 Ko et deux allers-retours par chargement. Pour un
    humain qui développe c'est un bon compromis ; **pour une suite, c'en
    est un mauvais** : les 84 probes tournent en dev, donc leur fiabilité
    dépendait d'un tiers. Mesuré le 2026-09-13 en coupant unpkg : l'encre
    d'un bouton passe de ``oklab(…)`` à ``rgb(0, 0, 0)`` et le document
    perd une feuille de style — exactement ce qu'avait rapporté
    ``probe_datatable_filter`` au milieu d'un run complet, et la raison
    pour laquelle la rouge se déplaçait d'un probe à l'autre sans jamais
    parler du code.

    ⚠️ **Ce n'est PAS un mécanisme de test.** ``bretzel.render.vendor``
    existait déjà et faisait ce travail pour les trois autres scripts ;
    la première version de cette fonction montait un serveur local et
    réécrivait une constante du framework — un doublon, écrit faute
    d'avoir cherché. Le compilateur y est entré comme quatrième asset, et
    un banc n'a plus qu'à demander le rapatriement.

    Rend ``True`` si tout est local. **Ne lève jamais** : sans réseau, le
    repli CDN reste le comportement du framework, et un banc ne doit pas
    refuser de démarrer parce qu'un cache manque.
    """
    from bretzel.render import vendor

    assets = vendor.downloadable_assets()
    if all(vendor.vendored_is_available(a) for a in assets):
        return True
    try:
        vendor.download_all()
    except Exception:
        return False
    return all(vendor.vendored_is_available(a) for a in assets)


def absolutise_vendor(html: str) -> str:
    """Rendre une coque utilisable depuis une page ``file://``.

    Neuf probes n'ouvrent pas un serveur : ils écrivent un HTML et le
    chargent en ``file://``. Ils passent déjà htmx, idiomorph et iconify
    en URL absolue pour cette raison — une route relative ne désigne rien
    hors d'une origine HTTP.

    Le compilateur Tailwind, lui, est injecté par la coque elle-même, donc
    aucun ``js_urls=`` ne le couvre. Depuis qu'il est rapatriable
    (2026-09-13) sa route est relative, et ces neuf pages se retrouvaient
    **sans compilateur** : aucune feuille, tout en ``rgba(0, 0, 0, 0)``,
    et des constats qui accusaient les couleurs d'un composant.

    On pointe le fichier du cache plutôt que le CDN : une page de test n'a
    pas plus de raison qu'une autre d'aller chercher 276 Ko chez un tiers.

    ⚠️ **Le fournisseur d'icônes, lui, est RETIRÉ, pas réécrit.** Il
    désigne une route vivante (``/_bretzel/icons``), pas un fichier : sans
    serveur il n'y a rien à viser, et le laisser en place fait échouer
    chaque glyphe en silence — mesuré sur ``probe_sidebar``, le lien
    existe et le glyphe est absent. Retiré, le composant retombe sur ses
    propres hôtes, ce que ces neuf pages faisaient déjà avant. C'est le
    seul endroit du dépôt où un tiers reste, et c'est parce qu'il n'y a
    pas de nôtre à proposer.
    """
    from bretzel.render import vendor
    from bretzel.runtime.protocol import ROUTE_ICONS

    html = re.sub(
        r"<script>window\.IconifyProviders=[^<]*</script>", "", html, count=1
    )
    assert ROUTE_ICONS not in html, (
        f"le fournisseur d'icônes survit dans une page `file://` : "
        f"{ROUTE_ICONS} y désigne un chemin de disque inexistant, donc "
        f"aucun glyphe ne rendra. La forme du <script> a dû changer — "
        f"reprends le motif ci-dessus."
    )

    for asset in vendor.downloadable_assets():
        if not vendor.vendored_is_available(asset):
            continue
        html = html.replace(
            vendor.route_for(asset),
            vendor.vendored_local_path(asset).resolve().as_uri(),
        )
    return html
