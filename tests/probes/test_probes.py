"""``pytest -m probes`` — lance les probes Playwright, un par un.

Pourquoi ce fichier existe
---------------------------
``tests/probes/`` est le SEUL étage qui regarde vraiment le rendu depuis
la suppression de ``tests/visual/`` le 2026-08-16. Il n'était collecté
par personne : les scripts s'appellent ``probe_*.py``, pas ``test_*.py``.

Ce que ça coûte a été mesuré le 2026-08-19, en les lançant tous pour la
première fois : **17 rouges sur 52**, accumulés en silence. Deux causes
dominaient, et aucune n'était un bug de composant — un paramètre renommé
(``default_shell(mode=)``, 9 probes morts avant d'ouvrir Chromium) et un
``parents[3]`` d'un niveau de trop vers ``runtime.js`` (7 probes sans
runtime, dont **3 verts à tort**, ce qui est pire que rouge). Les quatre
vrais bugs de framework du lot étaient cachés derrière.

Ce fichier n'ajoute donc aucune assertion : il rend les probes
LANÇABLES d'une commande, et fait de leur code de sortie un test.

Ce qu'il n'est pas
-------------------
Il n'entre PAS dans le run rapide (marqueur ``probes``, désélectionné par
``addopts``) : chacun démarre son propre uvicorn ET son propre Chromium.
Mesuré le 2026-09-13 : le socle d'un probe — import du harnais 2,1 s,
serveur 0,3 s, contexte Chromium 1,25 s, première page ~1,8 s — fait
**5,4 s avant la première assertion**.

⚠️ Ce fichier ne juge que le CODE DE SORTIE, et c'est assumé — mais ça
suppose qu'un probe en produise un. Neuf ne le faisaient pas : ils
imprimaient ``==> SOME CHECKS FAILED`` puis appelaient ``main()`` sans
``sys.exit``, donc sortaient 0. C'est exactement le « vert à tort » que
la section ci-dessus nomme, et il a vécu ici jusqu'au 2026-08-26.
``tests/consistency/test_a_probe_can_actually_fail.py`` le garde désormais.

✅ **Parallélisable depuis le 2026-09-13.** Chaque probe demande un port
LIBRE au système et le passe à son banc en argument
(``tests/probes/_serve.py``) ; deux probes ne peuvent donc plus se marcher
dessus.

⚠️ **Le défaut reste SÉQUENTIEL, et c'est mesuré.** Trois runs le même
jour, sur la même machine :

===============  ==========  ====================================
run              durée       résultat
===============  ==========  ====================================
séquentiel       16 min 54   **84/84**
``-n 2``          8 min 16   83/84 — la rouge passe relancée seule
``-n 4``          8 min 42   69/84, et plus LENT que ``-n 2``
===============  ==========  ====================================

La rouge de ``-n 2`` n'est jamais la même d'un run à l'autre
(``probe_datatable_filter``, puis ``probe_chart_empty``), et le
séquentiel est propre — donc ce n'est pas un probe qui ment, c'est un
plafond de ressources. Même signature que ``-m browser``, et même
arbitrage : *une suite qu'on peut croire vaut son temps*. ``-n 2`` sert à
regarder vite ; il ne sert pas à conclure.

Piste pour le rendre croyable, notée à ``todo.md`` : le cache CSS de dev
ne garde que douze feuilles, et une suite complète en demande plus — un
serveur peut se faire évincer celle qu'il sert encore.

Avant, **60 probes sur 84 codaient leur port en dur**, et dix de ces
ports servaient deux ou trois bancs différents — d'où un ``xdist_group``
qui épinglait les 84 sur un worker unique pour protéger une poignée de
collisions. La ligne d'ici disait « ``:8974`` en sert trois », ce qui
sous-estimait le problème d'un facteur vingt.

⚠️ **Une exception, et elle est structurelle** : ``probe_oauth_door``
garde ses deux ports fixes. Une porte OIDC a une ``redirect_uri``
enregistrée chez le fournisseur et une adresse d'émetteur connue de
l'app — les deux serveurs doivent donc s'accorder AVANT de démarrer, ce
qu'un port tiré au sort ne permet pas sans se passer les deux adresses.
Lui seul reste épinglé, par ``_FIXED_PORT``.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from tests.consistency._discovery import PROBES_DIR, REPO_ROOT

#: Le plus lent mesuré fait 52 s (``probe_mobile_overflow``), la médiane
#: 5,7 s. La marge couvre une machine chargée sans laisser un probe
#: bloqué pendre toute la suite.
TIMEOUT_S = 180

#: 63 probes le 2026-08-26. Le plancher attrape un glob cassé, qui
#: rendrait ``pytest -m probes`` vert en n'ayant rien lancé.
PROBES_FLOOR = 45


#: Les probes dont le BANC a disparu, avec leur raison. Table UNIQUE,
#: lue depuis la gate qui les tolère : deux listes divergeraient, et
#: c'est précisément la copie manuelle qui a tué quatre probes le
#: 2026-08-30.
from tests.consistency.test_probe_benches_still_import import (  # noqa: E402
    _ORPHANS_KNOWN,
)


def probe_scripts() -> list[str]:
    return sorted(p.name for p in PROBES_DIR.glob("probe_*.py"))


#: Les probes qui ne PEUVENT pas prendre un port libre, et pourquoi.
#:
#: Une liste nommée plutôt qu'un marqueur posé au cas par cas : elle se
#: lit d'un coup d'œil, et l'allonger demande d'écrire une raison.
_FIXED_PORT: dict[str, str] = {
    "probe_oauth_door.py": (
        "deux serveurs qui doivent s'accorder AVANT de démarrer — la "
        "`redirect_uri` est enregistrée chez le fournisseur, l'émetteur "
        "est connu de l'app. Un port tiré au sort casserait les deux."
    ),
}


def probe_params() -> list:
    """Les probes, l'orphelin déclaré marqué en échec ATTENDU.

    Pourquoi pas le laisser rouge. Un rouge permanent dans une suite est
    exactement ce qui l'a fait cesser d'être lancée ailleurs : ``-m
    audit`` a vécu rouge et ignoré pendant des semaines. Un ``xfail``
    dit la même chose sans noyer les vrais rouges.

    ``strict=True`` fait l'autre moitié du travail : le jour où le probe
    est réparé, il passe, et un XPASS ÉCHOUE — donc l'exemption ne peut
    pas survivre à sa propre guérison.
    """
    out = []
    for name in probe_scripts():
        marks = []
        if name in _ORPHANS_KNOWN:
            marks.append(pytest.mark.xfail(
                strict=True,
                reason=f"banc supprimé — {_ORPHANS_KNOWN[name][:120]}…",
            ))
        if name in _FIXED_PORT:
            marks.append(pytest.mark.xdist_group("probes_port_fixe"))
        out.append(pytest.param(name, marks=marks) if marks else name)
    return out


def test_the_sweep_is_not_vacuous() -> None:
    found = probe_scripts()
    assert len(found) >= PROBES_FLOOR, (
        f"seulement {len(found)} probes découverts (53 le 2026-08-19) — "
        f"``pytest -m probes`` passerait en n'ayant rien lancé, ce qui est "
        f"exactement l'état qu'il existe pour sortir."
    )


@pytest.mark.probes
@pytest.mark.parametrize("script", probe_params())
def test_probe_passes(script: str) -> None:
    """Le probe rend 0. Sa sortie EST le diagnostic — on la remonte telle
    quelle plutôt que de la résumer."""
    result = subprocess.run(
        [sys.executable, str(PROBES_DIR / script)],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=TIMEOUT_S,
        check=False,
    )
    if result.returncode == 0:
        return
    tail = "\n".join(
        (result.stdout + "\n" + result.stderr).strip().splitlines()[-30:]
    )
    pytest.fail(f"{script} → code {result.returncode}\n{tail}", pytrace=False)
