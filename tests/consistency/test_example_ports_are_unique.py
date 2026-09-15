"""Chaque exemple a UN port, le même des deux côtés, et le 8000 est libre.

Un exemple déclare son port à **deux endroits** — `app.run(port=…)` dans
son `main.py`, et l'entrée `launch.json` que le harnais lit pour ouvrir un
preview. Rien ne les relie : ils se contredisent en silence, et le
symptôme arrive tard et de travers (« le preview affiche une autre app »,
« le port est déjà pris »).

Ce que ça a coûté (2026-08-16)
-------------------------------
Le harnais a refusé de démarrer — *port 8000 in use* — parce que
`launch.json` réclamait le 8000 pour le playground, celui-là même que
l'utilisateur lance à la main. Et en renumérotant, deux docstrings
d'en-tête annonçaient encore un port faux **depuis la renumérotation
PRÉCÉDENTE** : `docs` disait 8002 alors qu'il écoutait 8005,
`screen_demo` disait 8005 pour 8011. Elles n'avaient jamais été suivies,
parce que rien ne les suit.

Trois invariants, et le troisième est le moins évident
-------------------------------------------------------
1. `main.py` et `launch.json` déclarent le MÊME port ;
2. les ports sont deux à deux distincts — deux exemples lancés ensemble
   est le cas NORMAL, pas l'exception ;
3. **le 8000 reste libre.** C'est le port que l'utilisateur occupe à la
   main ; le réclamer dans `launch.json` fait échouer le harnais au lieu
   de l'app, ce qui envoie chercher le problème du mauvais côté.

Et la docstring d'en-tête compte
---------------------------------
Elle est ce qu'on lit avant de lancer. Une docstring qui nomme un autre
port que `app.run` est un piège pur : on ouvre l'URL annoncée, on tombe
sur rien, on cherche un bug d'app. La gate lit donc aussi les mentions
``port 80xx`` du fichier.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_LAUNCH = _ROOT / ".claude" / "launch.json"

#: Réservé à ce que l'utilisateur lance lui-même. Cf. la docstring.
_RESERVED = 8000

#: Plancher de DÉCOUVERTE : combien de configurations le fichier expose.
#: Ancré sur la lecture, pas sur le nombre de dossiers d'``examples/`` —
#: un ``launch.json`` vidé ou renommé rendrait la gate verte en ne
#: vérifiant rien. Mesuré le 2026-08-16 : 15 ; 7 depuis le 2026-09-07,
#: l'élagage des exemples ayant retiré onze apps et leurs entrées.
_CONFIG_FLOOR = 5

_RUN_PORT = re.compile(r"app\.run\(port=(\d+)")
_MENTION = re.compile(r"\bport (80\d\d)\b")


def _configs() -> list[tuple[str, int]]:
    if not _LAUNCH.exists():
        return []
    data = json.loads(_LAUNCH.read_text(encoding="utf-8"))
    return [
        (e["name"], e["port"])
        for e in data.get("configurations", [])
        if "name" in e and "port" in e
    ]


_CONFIGS = _configs()


def test_the_sweep_is_not_vacuous() -> None:
    assert len(_CONFIGS) >= _CONFIG_FLOOR, (
        f"``launch.json`` n'expose que {len(_CONFIGS)} configurations "
        f"(plancher {_CONFIG_FLOOR}) — le fichier a été vidé, renommé ou "
        f"sa forme a changé, et la gate ne vérifie plus rien."
    )


def test_ports_are_pairwise_distinct() -> None:
    seen: dict[int, list[str]] = {}
    for name, port in _CONFIGS:
        seen.setdefault(port, []).append(name)
    clashes = {p: n for p, n in seen.items() if len(n) > 1}
    assert not clashes, (
        f"Deux exemples se disputent un port : {clashes}. Les lancer "
        f"ensemble est le cas normal — le second échouerait au démarrage."
    )


def test_port_8000_stays_free() -> None:
    squatters = [n for n, p in _CONFIGS if p == _RESERVED]
    assert not squatters, (
        f"{squatters} réclament le {_RESERVED}, réservé à ce que "
        f"l'utilisateur lance à la main. Le harnais échoue alors au "
        f"démarrage (« port in use »), ce qui envoie chercher le problème "
        f"du côté de l'app au lieu de la configuration."
    )


@pytest.mark.parametrize(
    "name,port", _CONFIGS, ids=[n for n, _ in _CONFIGS]
)
def test_main_agrees_with_launch_json(name: str, port: int) -> None:
    main = _ROOT / "examples" / name / "main.py"
    assert main.exists(), f"``launch.json`` référence {name}, absent d'examples/"
    src = main.read_text(encoding="utf-8")

    found = _RUN_PORT.search(src)
    assert found, f"{name}/main.py n'appelle pas ``app.run(port=…)``"
    assert int(found.group(1)) == port, (
        f"{name} écoute sur {found.group(1)} mais ``launch.json`` ouvre le "
        f"preview sur {port} — le preview affichera une autre app, ou rien."
    )

    stale = [m for m in _MENTION.findall(src) if int(m) != port]
    assert not stale, (
        f"{name}/main.py annonce ``port {stale[0]}`` dans son texte alors "
        f"qu'il écoute sur {port}. La docstring d'en-tête est ce qu'on lit "
        f"AVANT de lancer : un port faux envoie ouvrir une URL morte et "
        f"chercher un bug d'app. (Mesuré le 2026-08-16 : deux exemples "
        f"mentaient ainsi depuis la renumérotation précédente.)"
    )


def test_the_detector_still_bites() -> None:
    """Mutation : le port d'un exemple est encore lu, des deux façons.

    ``_RUN_PORT`` lit ce que le ``main.py`` fait vraiment,
    ``_MENTION`` ce que la prose annonce. Les deux doivent mordre :
    c'est leur DÉSACCORD que la gate cherche.
    """
    assert _RUN_PORT.search("app.run(port=8012)").group(1) == "8012"
    assert not _RUN_PORT.search("app.run(host='0.0.0.0')"), "faux positif"
    assert _MENTION.search("sert sur le port 8012 en dev").group(1) == "8012"
    assert not _MENTION.search("le port 9000"), "faux positif"
