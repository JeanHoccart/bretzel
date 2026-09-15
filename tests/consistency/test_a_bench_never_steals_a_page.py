"""Gate : importer un bench ne VOLE pas une page à une autre app.

Le défaut qu'elle ferme, et il a coûté un mois de « flake »
------------------------------------------------------------
``@page(path)`` **marque l'objet fonction** (``fn._bz_page = PageMeta``).
Décorer la MÊME fonction une seconde fois écrase donc la première marque,
et la première route disparaît — en 404, sans un mot, dans une app qu'on
n'est même pas en train de lire.

Mesuré le 2026-08-29. Deux bancs faisaient ::

    bench_page = page("/", layout=shell)(sidebar_feat.page)   # bench_sidebar_mount
    app.include(page("/")(datatable_solo.page))               # bench_datatable_solo

sur les deux fonctions que ``examples/playground/app/routes.py`` montait
déjà en ``/sidebar`` et ``/datatable_solo``. **Importer l'un de ces
fichiers suffisait à rendre les deux pages introuvables dans le
playground**, dans le même process, quel que soit l'ordre :

    import tests.probes.bench_sidebar_mount
    /sidebar         404
    /datatable_solo  404
    /button          200

C'est la cause — unique — des deux rouges catalogués « la suite rapide
dépend de l'ORDRE » depuis le 2026-08-27, et de leur allure de flake :
sous ``xdist``, seul le worker qui hérite d'un de ces fichiers perd les
pages ; en séquentiel, l'ordre d'import les épargnait. Le diagnostic
d'origine parlait d'un « pollueur à trouver par bissection » — la
bissection séquentielle ne pouvait rien voir, puisque séquentiellement
tout passe.

Ce qu'elle garde, et pourquoi elle double le socle
---------------------------------------------------
``page()`` REFUSE désormais la double marque
(:class:`PageAlreadyMarkedError`), donc le défaut ne peut plus être
introduit en silence. Cette gate garde la PROPRIÉTÉ plutôt que le
mécanisme : si un jour la marque cesse de vivre sur la fonction, ou si
le refus est assoupli pour un cas légitime, ce qui compte reste « la
table de routes du playground ne bouge pas parce qu'on a importé un
banc ».

Pourquoi un SOUS-PROCESS, et pas une mesure en place
-----------------------------------------------------
Première version de cette gate : lire la table de routes, importer les
bancs, relire la table. **Faux vert, prouvé par mutation** — elle passait
avec le défaut réintroduit. Les routes sont enregistrées au premier
DÉMARRAGE de l'app et n'en bougent plus : une fois ``/sidebar`` montée,
aucune remarque ultérieure ne peut la retirer. Le défaut n'existe que
dans l'ordre inverse — bancs importés d'abord, app démarrée ensuite — et
cet ordre-là, une session pytest l'a ou ne l'a pas selon le worker.

D'où le sous-process : il impose l'ordre au lieu de l'espérer. C'est
aussi le seul moyen d'être indépendant de ce que la session a déjà
importé.

Le plancher nomme les deux pages qui ont réellement cassé : sans lui,
renommer une feature rendrait la gate verte sur un ensemble vide.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

NL = chr(10)

_ROOT = Path(__file__).resolve().parents[2]
_BENCHES = sorted((_ROOT / "tests" / "probes").glob("bench_*.py"))

#: Les deux pages que le défaut a réellement fait disparaître. Nommées, et
#: pas déduites : c'est le plancher de la gate.
_VICTIMES = ("/sidebar", "/datatable")

#: Importe TOUS les bancs, PUIS démarre le playground, PUIS rend la table
#: de routes. L'ordre est le sujet — cf. le docstring.
_SCRIPT = """
import importlib, json, pathlib, sys
racine = pathlib.Path(sys.argv[1])
for f in sorted((racine / "tests" / "probes").glob("bench_*.py")):
    importlib.import_module("tests.probes." + f.stem)
from starlette.testclient import TestClient
from examples.playground.main import app
with TestClient(app):
    chemins = sorted(
        r.path for r in app.fastapi.routes if isinstance(getattr(r, "path", None), str)
    )
print(json.dumps(chemins))
"""


def _paths_after_importing_every_bench() -> list[str]:
    import json

    out = subprocess.run(
        [sys.executable, "-c", _SCRIPT, str(_ROOT)],
        cwd=_ROOT, capture_output=True, text=True, timeout=300,
    )
    assert out.returncode == 0, (
        "le sous-process n'a pas pu construire le playground apres avoir "
        "importe les bancs :" + NL + out.stderr[-2000:]
    )
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_the_sweep_is_not_vacuous() -> None:
    """Plancher : les bancs existent et sont assez nombreux pour compter."""
    assert len(_BENCHES) >= 40, (
        f"{len(_BENCHES)} bench(s) trouve(s) — le balayage ne mesure plus "
        "rien. Le motif de nom a-t-il change ?"
    )


def test_no_bench_steals_a_playground_page() -> None:
    chemins = _paths_after_importing_every_bench()
    # 90 routes mesurées le 2026-08-30 : le playground en avait 146
    # la veille, dont 56 pour la seule famille ``/matrix``,
    # supprimée. Le plancher garde sa marge — il doit rougir si le
    # sous-process ne démarre pas, pas si on retire des pages.
    assert len(chemins) >= 80, (
        f"{len(chemins)} routes seulement — le playground n'a pas demarre "
        "correctement dans le sous-process, la gate ne mesure rien."
    )
    volees = [p for p in _VICTIMES if p not in chemins]
    detail = (
        "Ces pages du playground ont DISPARU une fois les bancs de "
        f"``tests/probes/`` importes : {volees}." + NL
        + "  Un banc decore une fonction de page que le playground monte "
        "deja. La marque ``@page`` vit sur l'objet fonction et n'est LUE "
        "qu'au demarrage : la derniere decoration gagne, quel que soit "
        "l'ordre d'import." + NL
        + "  Ecris ``page('/')(lambda: mod.page())`` — une fonction par route."
    )
    assert not volees, detail



def test_the_detector_still_bites() -> None:
    """La preuve fabriquée : le detecteur voit un vol, et pas un montage sain.

    La violation est jouee POUR DE VRAI dans un sous-process jetable —
    deux ``@page`` sur la meme fonction, dans l'ordre qui casse — puis on
    verifie que la table de routes perd bien la premiere. Le jumeau
    licite, lui, passe par une ``lambda`` : c'est la forme prescrite par
    le message d'erreur, et elle doit rester muette.

    ⚠️ Ce test existe parce que la PREMIERE version de cette gate etait un
    faux vert : elle lisait la table, importait les bancs, la relisait —
    et passait avec le defaut reintroduit, puisque des routes deja
    enregistrees ne se retirent jamais. Seule une mutation l'a montre.
    """
    gabarit = """
import json, sys
from bretzel import Bretzel, page, ui
from starlette.testclient import TestClient

def vue() -> None:
    ui.text("bonjour")

page("/premiere")(vue)
CIBLE  # la seconde marque, licite ou non

app = Bretzel(secret_key="z" * 32, mode="dev")
app.include(__name__)
with TestClient(app):
    print(json.dumps(sorted(
        r.path for r in app.fastapi.routes
        if isinstance(getattr(r, "path", None), str))))
"""

    def routes(cible: str) -> tuple[int, list[str], str]:
        import json

        out = subprocess.run(
            [sys.executable, "-c", gabarit.replace("CIBLE", cible)],
            cwd=_ROOT, capture_output=True, text=True, timeout=120,
        )
        if out.returncode != 0:
            return out.returncode, [], out.stderr
        return 0, json.loads(out.stdout.strip().splitlines()[-1]), ""

    # LE VOL — la meme fonction remarquee. Le socle le refuse a la
    # decoration, donc le sous-process meurt : c'est la morsure.
    code, chemins, err = routes('page("/seconde")(vue)')
    assert code != 0, (
        "remarquer la MEME fonction pour une seconde route n'a rien "
        f"declenche — le refus du socle a saute. Routes vues : {chemins}"
    )
    assert "PageAlreadyMarkedError" in err, (
        "le sous-process a bien echoue, mais pas sur le refus attendu :"
        + NL + err[-1500:]
    )

    # LE JUMEAU LICITE — deux fonctions, deux routes, aucune plainte.
    # ⚠️ LIEE a un nom top-level : ``include(__name__)`` rate le namespace
    # du module, donc une marque posee sur une expression jetee n'est
    # jamais vue. Mesure faite ici meme, la premiere version de ce test
    # ne montait que ``/premiere``.
    code, chemins, err = routes('autre = page("/seconde")(lambda: vue())')
    assert code == 0, "la forme prescrite est refusee :" + NL + err[-1500:]
    assert {"/premiere", "/seconde"} <= set(chemins), (
        f"les deux routes devraient coexister, vu : {chemins}"
    )
