"""Le garde-fou du reload `Screen` survit-il au chargement qu'il garde ?

Le bug qu'elle ferme, mesuré le 2026-08-16 sur ``examples/todo``
-----------------------------------------------------------------
``Screen().is_mobile`` est un ``if`` **serveur** : il lit le cookie
``bz_screen`` posé au chargement précédent (``render/screen.py``). Le serveur
ne peut donc jamais connaître le viewport courant — la seule correction est le
reload pré-paint émis par ``render/shell.py::_screen_boot_script``.

Ce reload portait un garde-fou **booléen jamais effacé** :

    if (!sessionStorage.getItem('bz:screen-synced')) { setItem(…, '1'); reload() }

Posé une fois pour toute la vie de l'onglet. La PREMIÈRE correction le
consomme ; toutes les suivantes sont avalées en silence — le cookie est bien
réécrit, mais la peinture périmée reste à l'écran. L'utilisateur devait taper
**deux F5** pour passer de la vue téléphone à la vue PC, et deux dans l'autre
sens.

La propriété protégée
---------------------
Le drapeau ne doit décrire QUE le chargement en cours. Trois choses, ensemble :

1. il est lu **et effacé** avant toute sortie anticipée ;
2. il n'est **écrit qu'une fois**, et cette écriture vit **après** toutes les
   sorties — donc uniquement sur le chemin qui recharge ;
3. il ne supprime le reload que quand il est **présent** (polarité).

Il ne peut alors supprimer que le reload que le script s'est lui-même infligé —

* bascule légitime → le drapeau est propre, la correction part, un seul F5 ;
  le suivant repart d'un drapeau propre, donc les corrections sont ILLIMITÉES ;
* oscillation pathologique (une bascule de layout qui ajoute/retire la
  scrollbar déplace le viewport d'environ 15 px, donc ``max-width`` peut
  rebasculer quand la fenêtre est posée pile sur le seuil) → le chargement
  forcé retrouve le drapeau ET un désaccord : il abandonne au lieu de boucler.

⚠️ Pourquoi les points 2 et 3 et pas seulement le 1
---------------------------------------------------
Une première version de cette gate ne portait que le point 1. Elle est restée
**verte** sur trois mutations, dont deux remettent le bug utilisateur mot pour
mot — vérifié en mutant `shell.py`, pas déduit :

| mutation | gate v1 | comportement réel |
|---|---|---|
| ré-armer le drapeau sur le chemin d'accord | **VERTE** | deux F5 par bascule |
| ré-écrire le drapeau juste après l'avoir lu | **VERTE** | deux F5 par bascule |
| inverser la polarité (`if(!g)return`) | **VERTE** | la correction ne part jamais |

C'est `project_measured_deps_are_not_signals` en vrai : elle protégeait
l'ORTHOGRAPHE de la correction historique, pas la propriété. L'écriture était
le seul verbe non borné du script — le point 2 est ce qui ferme les deux
premières lignes, le point 3 la troisième.

Deux formulations plus simples du garde-fou lui-même ont été essayées et
rejetées pendant la conception, elles sont ici parce qu'elles semblent
correctes :

* **drapeau keyé par la forme du viewport, accumulé** — borne le nombre de
  reloads à 4 (mobile × touch), donc réintroduit exactement le même bug une
  fois chaque forme visitée une fois ;
* **quota de N reloads par fenêtre de temps** — un test automatisé (ou un dev
  qui redimensionne vite) bascule plus vite que la fenêtre et se fait bloquer.

⚠️ Ce que cette gate ne peut PAS prouver : que le navigateur se comporte comme
la lecture du texte le suggère. Aucun moteur JS ne tourne dans le sous-ensemble
rapide. La preuve comportementale est dans
``tests/runtime_js/test_screen_switch_costs_one_reload.py`` — mais elle est
marquée ``browser``, donc HORS du sous-ensemble par défaut. C'est ce qui rend
ce fichier-ci load-bearing : c'est le seul des deux qui tourne toujours.
"""

from __future__ import annotations

import re
from pathlib import Path

from bretzel.render.shell import (
    _SCREEN_SYNC_KEY,
    _screen_boot_script,
    _screen_sync_script,
)
from bretzel.runtime.protocol import SCREEN_SYNC_FN

#: Preuve de morsure : contrôle POSITIF — le fragment jugé est encore présent dans le
#: script de boot.
MUTATION_PROOF = "test_the_gate_finds_the_flag_it_judges"

#: Le booteur tel qu'il part dans le ``<head>``. Il ne porte QUE la décision
#: (que faire d'une peinture périmée) ; la mesure du viewport vit dans
#: ``_screen_sync_script``, dont le ``return`` fausserait les positions ci-bas.
_SCRIPT = _screen_boot_script()

_RUNTIME_JS = Path(__file__).resolve().parents[2] / "bretzel" / "runtime" / "runtime.js"

_READ = f"sessionStorage.getItem('{_SCREEN_SYNC_KEY}')"
_CONSUME = f"sessionStorage.removeItem('{_SCREEN_SYNC_KEY}')"
_WRITE = f"sessionStorage.setItem('{_SCREEN_SYNC_KEY}'"
_RELOAD = "location.reload()"


def _flag_var() -> str | None:
    """Nom de la variable qui porte le drapeau lu.

    Dérivé de la source — le script est minifié à la main, donc un renommage
    doit faire rougir la gate au lieu de la vider."""
    match = re.search(rf"var (\w+)={re.escape(_READ)}", _SCRIPT)
    return match.group(1) if match else None


def test_the_gate_finds_the_flag_it_judges() -> None:
    """Plancher de non-vacuité.

    Tout le reste du fichier juge des positions et des comptes autour de la
    LECTURE du drapeau. Si la lecture disparaît, `g` vaut ``undefined``,
    ``if(g)return`` ne se déclenche jamais et la borne anti-boucle s'évapore —
    sans qu'aucun compte ne bouge. C'est le seul fragment que les autres
    assertions ne recoupent pas, donc le seul à mériter un plancher."""
    assert _READ in _SCRIPT, (
        f"le script de boot ne lit plus `{_SCREEN_SYNC_KEY}`.\n"
        f"  Sans lecture, la variable de garde est `undefined`, le `return` "
        f"d'abandon ne part jamais et une oscillation boucle à l'infini.\n"
        f"  Si le mécanisme a été retiré pour de bon, supprimer ce fichier — "
        f"pas le laisser vert sur un sujet disparu."
    )
    assert _flag_var() is not None, (
        "la lecture du drapeau n'est plus affectée à une variable : la gate "
        "ne peut plus vérifier la polarité du garde-fou."
    )


def test_the_flag_is_consumed_before_any_early_exit() -> None:
    """Propriété 1. Un drapeau qui survit à son chargement est le bug de
    2026-08-16 : il n'autorise qu'une correction par onglet."""
    consume = _SCRIPT.index(_CONSUME)
    first_exit = _SCRIPT.index("return")

    assert consume < first_exit, (
        f"le drapeau `{_SCREEN_SYNC_KEY}` est effacé APRÈS la première sortie "
        f"anticipée du script (position {consume} contre {first_exit}).\n"
        f"  Cette sortie est le cas NORMAL — le cookie était déjà bon. Si "
        f"l'effacement est derrière elle, le drapeau survit au chargement "
        f"qu'il gardait et bloque la correction suivante : deux F5 pour "
        f"changer de layout, dans les deux sens.\n"
        f"  Lire et effacer d'abord, décider ensuite."
    )


def test_the_flag_is_consumed_unconditionally() -> None:
    """Corollaire de la propriété 1 : une seule consommation, pas une par
    branche. Effacer dans chaque branche « marcherait » aussi, mais la
    propriété tiendrait par énumération de cas — donc tomberait à la
    prochaine branche ajoutée."""
    assert _SCRIPT.count(_CONSUME) == 1, (
        f"{_SCRIPT.count(_CONSUME)} effacements du drapeau. Un seul, en tête, "
        f"sur le chemin que TOUS les chargements empruntent."
    )


def test_the_flag_is_armed_only_on_the_path_that_reloads() -> None:
    """Propriété 2 — et la seule qui attrape les deux réécritures du bug.

    Le drapeau doit être écrit exactement une fois, après toutes les sorties
    anticipées. Une écriture ailleurs — sur le chemin d'accord, ou juste après
    la lecture — le ré-arme pour un chargement qui n'est pas le nôtre : la
    correction suivante se croit forcée par nous et abandonne. Deux F5, à
    nouveau, sans qu'aucun autre compte de ce fichier ne bouge."""
    assert _SCRIPT.count(_WRITE) == 1, (
        f"{_SCRIPT.count(_WRITE)} écritures du drapeau dans le script. Une "
        f"seule, sur le chemin qui recharge — chaque écriture supplémentaire "
        f"arme le garde-fou pour un chargement que le script n'a pas provoqué, "
        f"et ré-ouvre le bug des deux F5."
    )
    last_exit = _SCRIPT.rindex("return")
    assert _SCRIPT.index(_WRITE) > last_exit, (
        f"le drapeau est armé AVANT la dernière sortie anticipée (position "
        f"{_SCRIPT.index(_WRITE)} contre {last_exit}) : il est donc posé sur "
        f"des chargements qui ne rechargent pas.\n"
        f"  Un drapeau posé sans reload correspondant fait abandonner la "
        f"correction suivante — exactement le symptôme de 2026-08-16."
    )


def test_the_guard_gives_up_when_the_flag_is_PRESENT() -> None:
    """Propriété 3 — la polarité.

    Inversée, le script abandonne quand le drapeau est ABSENT : la correction
    ne part alors jamais et la vue reste périmée indéfiniment. Aucun compte ni
    aucune position ne bouge, d'où cette assertion dédiée."""
    flag = _flag_var()
    assert flag is not None  # garanti par le plancher
    assert f"if({flag})return" in _SCRIPT, (
        f"le garde-fou ne se lit pas `if({flag})return` : sa polarité a été "
        f"inversée, ou il a changé de forme.\n"
        f"  Il doit abandonner quand le drapeau est PRÉSENT (le chargement "
        f"forcé par le script est encore faux → oscillation). Inversé, il "
        f"abandonne quand le drapeau est absent, c'est-à-dire toujours : plus "
        f"aucune correction ne part."
    )


def test_the_sync_function_has_exactly_one_definition_and_two_callers() -> None:
    """La fonction de mesure est partagée — donc elle est un point de dérive.

    Elle est définie une fois (script pré-paint) et appelée depuis DEUX
    endroits : le booteur ci-dessus (chargement dur) et ``05_bridge.js`` (nav
    boostée). Si le runtime cessait de l'appeler, une nav boostée qui traverse
    le seuil repeindrait l'ancien layout indéfiniment — sans erreur, sans test
    rouge ailleurs. C'est le mode d'échec le plus silencieux de tout ce
    dossier, parce que rien ne le signale à l'écran sauf le mauvais layout.

    Le NOM lui-même est déjà miroité par ``test_python_js_mirror`` (il vit dans
    ``protocol.py``) : ici on vérifie l'USAGE, qu'un miroir de chaîne ne dit
    pas — une constante peut être présente dans le bundle et n'être jamais
    appelée."""
    assert f"window.{SCREEN_SYNC_FN}=function(" in _screen_sync_script(768), (
        f"le script pré-paint ne définit plus `window.{SCREEN_SYNC_FN}` : le "
        f"runtime l'appelle par ce nom, l'appel deviendrait un no-op silencieux."
    )
    assert f"window.{SCREEN_SYNC_FN}()" in _SCRIPT, (
        f"le booteur n'appelle plus `{SCREEN_SYNC_FN}()` — il ne mesure donc "
        f"plus rien et ne peut plus corriger une peinture périmée."
    )

    runtime = _RUNTIME_JS.read_text(encoding="utf-8")
    assert f"window.{SCREEN_SYNC_FN}()" in runtime, (
        f"`runtime.js` n'appelle plus `{SCREEN_SYNC_FN}()`.\n"
        f"  Sans cet appel, une navigation boostée qui traverse le seuil "
        f"mobile garde l'ancien layout : `hx-boost` ne remplace que "
        f"`[data-bz-outlet]`, or le `if Screen().is_mobile` vit au-dessus. "
        f"Aucune erreur, aucun autre test rouge — juste la mauvaise nav.\n"
        f"  Si le bundle est simplement périmé : `py -m bretzel.runtime._build`."
    )


def test_the_reload_is_reachable_only_through_the_guard() -> None:
    """Le reload ne doit pas exister AILLEURS que derrière le drapeau.

    Un second ``location.reload()`` non gardé — ajouté « juste pour le premier
    hit », par exemple — rendrait la borne anti-boucle décorative."""
    assert _SCRIPT.count(_RELOAD) == 1, (
        f"{_SCRIPT.count(_RELOAD)} appels à `{_RELOAD}` dans le script de "
        f"boot. Le drapeau ne borne que celui qu'il précède ; un second appel "
        f"rend la borne fausse et rouvre le risque de boucle."
    )
    assert _SCRIPT.index(_WRITE) < _SCRIPT.index(_RELOAD), (
        "le drapeau est armé APRÈS le reload — donc jamais : la navigation "
        "part avant l'écriture. Le chargement suivant ne verra rien et "
        "rechargera à son tour."
    )
