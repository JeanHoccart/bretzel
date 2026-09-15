"""Gate : l'algèbre du foreground est MIROITÉE en JS, à l'identique.

Le foreground d'une couleur n'est pas « noir ou blanc ». Il est dérivé du
fond : une clarté choisie par un seuil de luminance WCAG, puis TEINTÉE de
la teinte du fond pour que la paire reste d'un seul morceau. C'est
``bretzel.theme.palette.resolve_color_pair``, et ça tourne en Python, à la
génération du CSS.

Le theme studio ne parle jamais au serveur — c'est sa raison d'être. Il a
donc besoin du même calcul côté client, et il le REDIT en JavaScript.
C'est le même arbitrage que ``protocol.py`` ↔ ``runtime.js`` : le JS ne
peut pas importer Python, donc il recopie. Et comme là-bas, la copie doit
être gardée, sinon elle dérive.

Ce que le silence coûtait
--------------------------

Sans ce miroir, le studio n'écrivait que ``--color-<nom>`` et laissait
``--color-<nom>-foreground`` à la valeur calculée au démarrage. Choisir du
blanc pour ``primary`` donnait donc du texte blanc sur fond blanc — et
aucun rechargement n'y changeait rien, puisque la page ne renvoie ses
couleurs nulle part. Signalé à l'œil le 2026-08-30.

Ce que cette gate vérifie, et ce qu'elle ne peut pas
-----------------------------------------------------

Elle vérifie que **chaque nombre nommé de l'algèbre apparaît dans le JS**.
Elle ne peut pas exécuter le JS — pas de moteur ici — donc elle ne prouve
pas l'égalité des sorties. Cette preuve-là existe, mais dans un probe
navigateur : ``tests/probes/probe_foreground_mirror.py`` compare les deux
implémentations sur 18 couleurs et exige l'égalité EXACTE de
l'hexadécimal (0 écart le 2026-08-30). Ce que la gate attrape, c'est le mode de dérive réel — un
seuil changé d'un seul côté — et elle l'attrape à la seconde, à chaque
commit.
"""

from __future__ import annotations

import re

import pytest

from bretzel.theme import palette
from examples.playground.features.theme_studio import FOREGROUND_JS

#: Preuve de morsure : l'introspection rend encore des constantes.
MUTATION_PROOF = "test_the_constant_set_is_non_trivial"

#: Combien de nombres l'algèbre porte. Sept le 2026-08-30 : trois
#: coefficients de luminance comptent pour un, plus les six seuils. Le
#: plancher est là pour qu'un renommage qui viderait l'introspection
#: rougisse au lieu de passer à vide.
_FLOOR = 7


def _named_numbers() -> list[tuple[str, float]]:
    """Les constantes de l'algèbre, découvertes par CONVENTION de nom.

    Par introspection et non par liste écrite : un seuil ajouté demain
    est couvert sans toucher ce fichier — la même mécanique que
    ``test_python_js_mirror``.
    """
    out: list[tuple[str, float]] = []
    for name, value in vars(palette).items():
        if not (name.startswith("_LUM_") or name.startswith("_FG_")):
            continue
        if isinstance(value, float):
            out.append((name, value))
        elif isinstance(value, tuple):
            out.extend((f"{name}[{i}]", v) for i, v in enumerate(value))
    return out


_NUMBERS = _named_numbers()


def test_the_constant_set_is_non_trivial() -> None:
    """Plancher sur la DÉCOUVERTE, pas sur le fichier.

    Renommer les constantes hors de la convention viderait
    l'introspection et rendrait le test ci-dessous vert en ne vérifiant
    rien — le mode d'échec exact que cette gate existe pour fermer.
    """
    assert len(_NUMBERS) >= _FLOOR, (
        f"{len(_NUMBERS)} constante(s) découverte(s) dans `palette.py` "
        f"(plancher {_FLOOR}) — la convention de nom `_LUM_*` / `_FG_*` "
        f"a-t-elle changé ? Sans elles, ce fichier ne vérifie plus rien."
    )
    assert len(FOREGROUND_JS) > 500, (
        "`FOREGROUND_JS` est quasi vide : le miroir a disparu."
    )


@pytest.mark.parametrize("name, value", _NUMBERS, ids=lambda v: str(v))
def test_the_foreground_algebra_is_mirrored_in_js(
    name: str, value: float
) -> None:
    """Chaque nombre de Python doit se lire LITTÉRALEMENT dans le JS.

    On cherche le nombre entouré de non-chiffres, sinon ``0.08``
    matcherait dans ``0.089`` et un changement de seuil passerait.
    """
    literal = repr(value)
    pattern = re.compile(rf"(?<![\d.]){re.escape(literal)}(?![\d])")
    assert pattern.search(FOREGROUND_JS), (
        f"`palette.{name}` vaut {literal}, et ce nombre n'apparaît nulle "
        f"part dans le miroir JS du theme studio.\n"
        f"  Les deux implémentations ont divergé : le studio ne rendra "
        f"plus la même paire que le CSS généré, et rien à l'écran ne le "
        f"dira — c'est une teinte légèrement fausse, pas une erreur.\n"
        f"  Répare `FOREGROUND_JS` dans "
        f"`examples/playground/features/theme_studio.py`."
    )


def test_the_studio_writes_the_pair_not_just_the_background() -> None:
    """Le miroir ne sert à rien s'il n'est pas APPELÉ.

    Le versant licite de la preuve : la gate ci-dessus resterait verte
    avec un ``FOREGROUND_JS`` parfait que personne n'invoque — soit
    exactement l'état d'avant le 2026-08-30, où seul ``--color-<nom>``
    était écrit.
    """
    from examples.playground.features.theme_studio import repaint_effect

    effect = repaint_effect()
    assert "window.bzFg(" in effect, (
        "l'effet de repeinte n'appelle pas `window.bzFg` : il n'écrit "
        "donc que le fond, et le foreground reste celui du démarrage."
    )
    assert "-foreground:" in effect, (
        "l'effet n'écrit aucune variable `--color-<nom>-foreground`."
    )
