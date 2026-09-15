"""Gate : toutes les pages des bancs rendent — en 3 secondes, sans navigateur.

Le défaut qu'elle ferme (2026-08-26)
------------------------------------
``check_sidebars_are_reachable`` (a0cbab3f, le 2026-08-24) refuse une
``ui.sidebar`` ``offcanvas`` / ``overlay`` sans moyen de la rouvrir. La
garde a raison. Ce qu'elle a aussi fait, c'est **500** sur des bancs
écrits avant elle — et personne ne l'a su pendant deux jours :

===========================  ==============================================
banc                          ce qui tombait
===========================  ==============================================
``bench_boost``               ``probe_boost``
``bench_matrix``              ``probe_matrix`` + ``probe_tooltip`` + ``probe_ttid``
``bench_sidebar_collapse``    **rien** — 4 pages mortes, aucun probe pour les charger
===========================  ==============================================

Plus un cas de `-m browser`. Soit **cinq tests rouges et quatre pages
mortes**, pour un seul commit, visibles seulement en lançant les deux
suites lourdes — 11 min et 5 min. Elles ne l'ont pas été.

Pourquoi une gate RAPIDE, et pas « relancer les suites lourdes »
-----------------------------------------------------------------
Un banc qui rend 500 ne mesure plus rien : son probe meurt sur
« bench never came up » et accuse le réseau, pas le rendu. Or ce
diagnostic ne demande **ni navigateur, ni uvicorn** — un ``TestClient``
et le rendu serveur suffisent. 77 pages en 2,8 s, dans le sous-ensemble
rapide, donc le jour même du commit fautif.

Ce qu'elle a trouvé en naissant : les quatre pages de
``bench_sidebar_collapse``, invisibles à tout le reste parce que la
racine de ce banc est un 404 **et** que son probe vit à l'intérieur de
lui (``--probe``), une troisième forme que ``pytest -m probes`` — qui
collecte ``probe_*.py`` — ne ramasse pas.

Ce qu'elle ne fait PAS
-----------------------
Elle ne regarde ni les pixels, ni le JavaScript : c'est le travail des
probes et de ``runtime_js``. Elle répond à **une** question, celle qui
conditionne toutes les autres : est-ce que la page se construit encore ?
Un banc peut donc être vert ici et faux à l'écran.

Elle ne teste pas les applications non-Bretzel : ``bench_oidc_provider``
sert un fournisseur OIDC en Starlette nu, sans page ``@page``. Cette
exclusion est COMPTÉE et assertée ci-dessous — un banc qui sortirait du
balayage sans raison ferait rougir la gate, pas la traverserait en
silence.

⚠️ Cette place a dit « elle ne teste pas non plus les routes paramétrées
(aucune aujourd'hui) » jusqu'au 2026-09-11, et la parenthèse était
fausse : ``bench_tabs_url`` n'a QUE ça — ``/contacts/<id>`` — donc il
était sur le disque, absent du balayage, et jamais rendu depuis sa
création. L'ancienne forme de la gate ne pouvait pas le dire, puisque le
paramétrage VENAIT du balayage : zéro ligne donnait zéro test au lieu
d'un rouge. Les paramètres sont désormais remplacés par ``1``. Le seuil
reste ``< 500`` : un identifiant qui ne résout pas rend 404, ce qui est
une réponse et pas une panne de rendu.

⚠️ Pourquoi un SOUS-PROCESSUS
------------------------------
Importer un banc exécute son module, et un banc est une app entière. La
première version de cette gate importait les bancs DANS le processus
pytest, et ``bench_matrix`` faisait alors ::

    COMPONENTS["button"] = dataclasses.replace(SPEC, zone=bench_zone)

— une réécriture du dict de module d'``examples.playground``. Résultat :
``test_playground_pages_are_reachable`` et
``test_example_pages_render[/sidebar]`` rougissaient, sans rapport
apparent avec quoi que ce soit.

**Ce défaut-là est réparé** (le moteur de matrice a un ``SpecRegistry``
par app depuis le 2026-08-26, et enregistrer deux fois un slug lève).
L'isolation reste, et c'est délibéré : la gate charge 57 modules écrits
pour être lancés en ``__main__``, elle n'a aucun moyen de savoir ce que
le 58ᵉ fera à l'import. Un balayage qui vérifie que rien n'est cassé ne
doit pas pouvoir casser quelque chose. Ça coûte ~1 s.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from tests.consistency._discovery import PROBES_DIR, REPO_ROOT

#: Preuve de morsure par contrôle POSITIF : le balayage voit encore des
#: pages, et il en voit BEAUCOUP. Une gate d'interdiction qui n'a chargé
#: aucun banc passerait sans rien dire.
MUTATION_PROOF = "test_the_sweep_really_loads_pages"

#: 77 pages sur 57 bancs, mesurées le 2026-08-26. Le plancher est bas
#: exprès : il attrape un glob mort ou un import cassé en masse, pas
#: l'ajout ou le retrait d'un banc.
_PAGES_FLOOR = 60

#: 62 bancs le 2026-09-11. Le paramétrage vient de CE glob et de rien
#: d'autre — c'est ce qui le rend identique sur les quatre workers.
_BENCH_FLOOR = 50

#: Le seul banc sans page ``@page`` : il sert le fournisseur OIDC de
#: ``examples/auth`` en Starlette nu. Nommé plutôt que sauté, pour
#: qu'un seizième banc muet ne se glisse pas dans la même ombre.
_NOT_A_BRETZEL_APP = frozenset({"bench_oidc_provider"})


#: Le balayage, tel qu'il tourne DANS l'interpréteur jetable. Il rend
#: ``[[banc, chemin, statut|"ERR: …"], …]`` en JSON sur stdout.
#:
#: Il vit en source ici, et pas dans un fichier à côté, pour une raison :
#: un script d'aide sous ``tests/probes/`` serait ramassé par les globs de
#: ce répertoire, et un script sous ``tests/consistency/`` par ceux de
#: celui-ci. Le garder inline le met hors de portée des deux.
_SWEEP_SOURCE = '''
import importlib, json, pathlib, re, sys
sys.path.insert(0, {root!r})
from starlette.testclient import TestClient

EXCLUDED = {excluded!r}
out = []
for path in sorted(pathlib.Path({probes!r}).glob("bench_*.py")):
    stem = path.stem
    if stem in EXCLUDED:
        continue
    module = importlib.import_module("tests.probes." + stem)
    app = None
    for attr in ("app", "_APP", "APP"):
        app = getattr(module, attr, None)
        if app is not None:
            break
    if app is None or not hasattr(app, "routables"):
        out.append([stem, None, "NO_APP"])
        continue
    with TestClient(app) as client:
        for fn in app.routables:
            meta = getattr(fn, "_bz_page", None)
            if meta is None or "GET" not in meta.methods:
                continue
            # Une route paramétrée se visite avec une valeur quelconque :
            # on mesure que la page se CONSTRUIT, pas qu'une donnée existe.
            # Classes de caractères plutôt que des échappements : ce
            # gabarit est une chaîne NORMALE, donc une accolade
            # échappée par une barre oblique y serait invalide.
            url = re.sub("[{{][^}}]+[}}]", "1", meta.path)
            try:
                out.append([stem, url, client.get(url).status_code])
            except Exception as exc:
                out.append([stem, url,
                            "ERR: " + type(exc).__name__ + ": " + str(exc)[:200]])
print("<<<JSON>>>" + json.dumps(out))
'''


def _sweep() -> list[list]:
    """``[[banc, chemin, statut], …]``, mesuré dans un processus jetable."""
    source = _SWEEP_SOURCE.format(
        root=str(REPO_ROOT), probes=str(PROBES_DIR),
        excluded=sorted(_NOT_A_BRETZEL_APP),
    )
    proc = subprocess.run(
        [sys.executable, "-c", source],
        cwd=REPO_ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=300, check=False,
    )
    marker = "<<<JSON>>>"
    if proc.returncode != 0 or marker not in proc.stdout:
        raise AssertionError(
            "le balayage des bancs n'a pas abouti — la gate ne peut RIEN "
            "affirmer.\n"
            f"  code de sortie : {proc.returncode}\n"
            f"  stdout : {proc.stdout[-1500:]}\n"
            f"  stderr : {proc.stderr[-1500:]}"
        )
    return json.loads(proc.stdout.split(marker, 1)[1].splitlines()[0])


#: Les bancs, lus sur le DISQUE. Le paramétrage ne dépend plus du
#: balayage, et c'est tout le sujet de la réparation du 2026-09-11 : il
#: vivait au niveau module, donc il tournait à la COLLECTE, donc sur les
#: quatre workers à la fois. Quand il échouait chez l'un d'eux, le module
#: levait pendant la collecte, ce worker collectait moins de tests, et
#: xdist rendait « Different tests were collected between gw0 and gwN ».
#: La divergence était le symptôme, à trois rebonds de la panne — et
#: c'est elle qu'on voyait, parce qu'elle fait ERROR sur la suite entière.
#: Mesurée 3 fois sur 6 runs le 2026-08-31, puis 2 fois sur 6 le
#: 2026-09-11, avec deux types d'exception différents.
#:
#: Un glob de fichiers, lui, rend la même liste partout et ne peut pas
#: échouer à moitié. La panne du balayage devient alors un test ROUGE,
#: qui nomme le banc fautif, au lieu d'une erreur de collecte qui ne
#: nomme rien.
BENCHES = tuple(sorted(
    path.stem
    for path in PROBES_DIR.glob("bench_*.py")
    if path.stem not in _NOT_A_BRETZEL_APP
))


@pytest.fixture(scope="session")
def sweep() -> list[list]:
    """Le balayage, UNE fois par session — et seulement s'il sert.

    Portée session et non module : il coûte ~6,5 s de sous-processus.
    Derrière une fixture, un run filtré qui ne sélectionne aucun de ces
    tests ne le paie plus du tout ; avant, il tournait à chaque collecte,
    même pour un ``-k`` qui n'en voulait pas.
    """
    return _sweep()


def test_the_parametrisation_is_not_vacuous() -> None:
    """Le glob qui paramètre doit voir des bancs.

    Sans ce plancher, un glob cassé rendrait `BENCHES` vide : la gate
    collecterait zéro cas et passerait en n'ayant rien vérifié — sans
    même lancer le balayage, donc sans que les autres planchers la
    rattrapent.
    """
    assert len(BENCHES) >= _BENCH_FLOOR, (
        f"seulement {len(BENCHES)} bancs découverts sous {PROBES_DIR} "
        f"(62 le 2026-09-11) — le glob est cassé, et la gate ne "
        f"paramètre plus rien."
    )


def test_the_sweep_really_loads_pages(sweep: list[list]) -> None:
    assert len(sweep) >= _PAGES_FLOOR, (
        f"le balayage ne voit plus que {len(sweep)} pages de banc "
        f"(77 le 2026-08-26) — vérifie que ``PROBES_DIR`` et "
        f"``app.routables`` répondent encore avant de croire que cette "
        f"gate passe. Elle serait verte en n'ayant chargé personne."
    )


def test_every_bench_exposes_an_app(sweep: list[list]) -> None:
    """Un banc qu'on ne sait pas construire sort du balayage — on le dit.

    C'est la version « banc » du saut silencieux que
    ``test_no_gate_swallows_a_component`` interdit sur les composants :
    sans cette assertion, un banc renommé ou cassé à l'import
    disparaîtrait du décompte sans faire rougir personne.
    """
    orphans = [stem for stem, _, status in sweep if status == "NO_APP"]
    assert not orphans, (
        f"ces bancs n'exposent aucune app Bretzel : {orphans}.\n"
        f"  Expose ``app`` au niveau module, ou nomme-le dans "
        f"``_NOT_A_BRETZEL_APP`` AVEC sa raison — pas en le laissant "
        f"tomber du balayage."
    )


@pytest.mark.parametrize("stem", BENCHES)
def test_a_bench_page_renders(stem: str, sweep: list[list]) -> None:
    """Toutes les pages d'UN banc, en un cas.

    Le cas porte le banc et non la page, parce que c'est le banc qui est
    découvrable sans rien exécuter. Le chemin fautif reste nommé dans le
    message — c'est lui qu'on veut lire, pas dans l'identifiant du test.
    """
    rows = [row for row in sweep if row[0] == stem]
    assert rows, (
        f"``{stem}`` est sur le disque mais absent du balayage — il n'a "
        f"donc PAS été chargé, et ce cas passerait en ne vérifiant rien. "
        f"Vérifie qu'il s'importe, ou nomme-le dans "
        f"``_NOT_A_BRETZEL_APP`` avec sa raison."
    )
    for _, path, status in rows:
        if isinstance(status, str) and status.startswith("ERR: "):
            pytest.fail(
                f"``{stem}`` lève en rendant ``{path}`` :\n"
                f"    {status[5:]}\n"
                f"  Ce banc ne mesure plus rien — son probe mourra sur "
                f"« bench never came up » et accusera le réseau.",
                pytrace=False,
            )
        assert isinstance(status, int) and status < 500, (
            f"``{stem}`` rend {status} sur ``{path}``.\n"
            f"  Un banc qui rend 5xx ne mesure plus rien, et son probe "
            f"accusera le démarrage du serveur plutôt que le rendu."
        )
