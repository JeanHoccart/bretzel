"""Gate : le marqueur qui sépare SEMER de POUSSER tient des deux côtés.

Ce qu'elle garde
-----------------
Un ``<bz-patch>`` porte deux intentions opposées et le runtime doit les
distinguer :

- **semer** (navigation partielle) — le serveur ré-émet *toutes* les
  instances de ``ClientState`` de la page, avec SES valeurs. Il ne peut
  pas connaître celles du navigateur : un ``ClientState`` est
  client-owned. Elles ne doivent donc que **créer ce qui manque** ;
- **pousser** (réponse d'action) — le serveur a délibérément muté un
  champ. Il gagne.

Le marqueur est la présence de ``config`` dans la charge utile, et il
n'est pas décoratif : ``build_patch`` ne l'émet que sous
``include_unchanged=True``, c'est-à-dire exactement le chemin de seed.
Le bridge branche dessus (``const isSeed = !!payload.config``).

Le défaut que ça ferme, rapporté par l'utilisateur le 2026-08-25
------------------------------------------------------------------
« Dès que je rentre sur la page paramètres, il switch en système. » Le
bridge appliquait les deux chemins par le même ``$bz._store.set``, donc
chaque navigation remplaçait le thème choisi par le défaut du serveur —
et comme ``set`` notifie la persistance, le défaut partait dans
``localStorage`` avant qu'``adoptConfig`` n'aille y relire le snapshot.
La préférence était **détruite**, pas masquée.

Pourquoi une gate STATIQUE alors qu'un probe navigateur existe
----------------------------------------------------------------
``tests/runtime_js/test_a_partial_nav_never_clobbers_client_state.py``
mesure le RÉSULTAT, et c'est la preuve qui compte — mais il est lourd
(uvicorn + Chromium) et ne tourne que sous ``-m browser``. Celle-ci
tourne à chaque ``pytest`` nu et garde ce qu'un test de résultat ne peut
pas voir : que les deux bouts parlent encore du même marqueur. Un
``config`` renommé côté Python laisserait ``!!payload.config`` toujours
faux — donc le bridge repasserait en écrasement, et le probe navigateur
serait le seul à le dire, une fois par semaine.
"""

from __future__ import annotations

import re
from pathlib import Path

from bretzel.runtime.envelope import build_patch
from bretzel.state import field
from bretzel.state.scopes.client import ClientState

_SRC = Path(__file__).resolve().parents[2] / "bretzel" / "runtime" / "_src"
_BRIDGE = _SRC / "05_bridge.js"
_STORE = _SRC / "00_index.js"


class Reglages(ClientState, persist="local"):
    theme: str = field(default='systeme')
    taille: str = field(default='md')


# ── Le versant Python : qui porte le marqueur ─────────────────────────

def test_the_seed_path_carries_the_marker() -> None:
    payload = build_patch([Reglages()], include_unchanged=True)
    assert payload["patches"], (
        "le seed n'émet aucune instance — la gate ne compare plus rien."
    )
    assert payload.get("config"), (
        "le patch de seed ne porte plus ``config``, qui est le SEUL "
        "marqueur dont dispose le bridge pour ne pas écraser l'état "
        "vivant du navigateur."
    )


def test_the_action_path_does_not() -> None:
    state = Reglages()
    state.theme = "sombre"  # l'affectation marque l'instance sale
    payload = build_patch([state])
    assert payload["patches"], (
        "l'instance sale n'est pas émise — le test ne prouverait rien "
        "sur l'absence de ``config``."
    )
    assert "config" not in payload, (
        "une réponse d'action porte maintenant ``config``, donc le bridge "
        "la prendra pour un seed et n'appliquera PLUS la mutation que le "
        "serveur a délibérément faite."
    )


# ── Le versant JavaScript : qui lit le marqueur ───────────────────────
#
# Les quatre prédicats sont des FONCTIONS et non des ``assert`` en ligne :
# c'est ce qui permet au test de mutation, plus bas, de les attaquer sur
# des sources fabriquées plutôt que de refabriquer un dépôt.


def branches_on_the_marker(source: str) -> bool:
    return bool(re.search(r"isSeed\s*=\s*!!\s*payload\.config", source))


def uses_both_paths(source: str) -> bool:
    return "$bz._store.seed(" in source and "$bz._store.set(" in source


def defines_seed(source: str) -> bool:
    # Une sous-chaine et pas une expression : la signature est ECRITE
    # ainsi dans le seul fichier concerne, et une tolerance aux espaces
    # n'achete rien ici.
    return "seed(path, value) {" in source


def seed_gives_up(source: str) -> bool:
    """``seed`` renonce-t-elle quand le champ porte DÉJÀ une valeur ?

    C'est tout ce qui la distingue de ``set``. Une version qui écrirait
    quand même compilerait, passerait les trois prédicats ci-dessus, et
    rouvrirait le bug entier.
    """
    if not defines_seed(source):
        return False
    body = source[source.index("seed(path, value)"):]
    cut = body.find(chr(10) + "    },")
    body = body[: cut if cut > 0 else len(body)]
    return "return" in body and "peek()" in body and "undefined" in body


def bridge_source() -> str:
    return _BRIDGE.read_text(encoding="utf-8")


def store_source() -> str:
    return _STORE.read_text(encoding="utf-8")


def test_the_bridge_branches_on_the_marker() -> None:
    assert branches_on_the_marker(bridge_source()), (
        "le bridge ne dérive plus son mode de ``payload.config``. Les "
        "deux bouts doivent nommer le même marqueur : côté Python c'est "
        "``build_patch`` qui l'émet sous ``include_unchanged=True``."
    )


def test_the_bridge_seeds_on_one_path_and_sets_on_the_other() -> None:
    """Les DEUX branches, pas seulement celle qui répare.

    Ne garder que ``seed`` laisserait passer un bridge qui ne pousse plus
    jamais une mutation d'action — le défaut symétrique, et invisible
    tant qu'aucune app ne mute un ``ClientState`` depuis un handler.
    """
    assert uses_both_paths(bridge_source()), (
        "le bridge n'appelle plus les deux chemins : ``seed`` pour la "
        "navigation partielle, ``set`` pour une réponse d'action."
    )


def test_the_store_actually_defines_seed() -> None:
    """Le pont entre les deux fichiers — un appel à une méthode qui
    n'existe pas lèverait à l'exécution, sur le chemin de navigation, donc
    seulement en vrai navigateur."""
    assert defines_seed(store_source()), (
        f"``seed(path, value)`` a disparu de {_STORE.name} alors que le "
        f"bridge l'appelle."
    )


def test_seed_leaves_an_existing_value_alone() -> None:
    assert seed_gives_up(store_source()), (
        "``seed`` n'a plus sa sortie anticipée sur une valeur présente, "
        "ou ne teste plus la VALEUR (``peek() !== undefined``) mais la "
        "seule existence du signal — ``get()`` en auto-crée un vide, "
        "donc un champ jamais semé serait pris pour un champ rempli."
    )


# ── Preuve que les détecteurs mordent, dans les DEUX sens ─────────────

_SEED_OK = """
    set(path, value) { flat.set(path, value); },
    seed(path, value) {
      if (flat.has(path) && flat.get(path).peek() !== undefined) return;
      this.set(path, value);
    },
    fieldsOf(x) {}
"""

#: Le mutant le plus crédible : ``seed`` existe, s'appelle bien, et
#: écrit quand même. C'est ce qu'on écrit en « simplifiant ».
_SEED_WRITES_ANYWAY = """
    set(path, value) { flat.set(path, value); },
    seed(path, value) {
      this.set(path, value);
    },
    fieldsOf(x) {}
"""

#: Le second mutant : teste l'EXISTENCE du signal au lieu de sa valeur.
#: Il paraît équivalent et ne l'est pas — ``get()`` auto-crée un signal
#: vide, donc un champ jamais semé n'en recevrait jamais son défaut.
_SEED_TESTS_EXISTENCE = """
    set(path, value) { flat.set(path, value); },
    seed(path, value) {
      if (flat.has(path)) return;
      this.set(path, value);
    },
    fieldsOf(x) {}
"""

_BRIDGE_OK = """
  const isSeed = !!payload.config;
  if (isSeed) $bz._store.seed(path, v); else $bz._store.set(path, v);
"""

_BRIDGE_ALWAYS_SETS = """
  $bz._store.set(path, v);
"""

_BRIDGE_NEVER_PUSHES = """
  const isSeed = !!payload.config;
  $bz._store.seed(path, v);
"""


def test_the_detectors_bite_on_fabricated_sources() -> None:
    """Le versant ILLICITE — chaque mutant est vu par SON prédicat."""
    assert not seed_gives_up(_SEED_WRITES_ANYWAY)
    assert not seed_gives_up(_SEED_TESTS_EXISTENCE)
    assert not branches_on_the_marker(_BRIDGE_ALWAYS_SETS)
    assert not uses_both_paths(_BRIDGE_ALWAYS_SETS)
    assert not uses_both_paths(_BRIDGE_NEVER_PUSHES)


def test_the_detectors_stay_quiet_on_licit_sources() -> None:
    """Le versant LICITE, et c'est lui qui a trouvé les deux seuls bugs
    de gate du dépôt : un détecteur qui rougit sur un cas correct est
    aussi cassé qu'un détecteur aveugle."""
    assert defines_seed(_SEED_OK)
    assert seed_gives_up(_SEED_OK)
    assert branches_on_the_marker(_BRIDGE_OK)
    assert uses_both_paths(_BRIDGE_OK)
