"""Gate : l'état fermé des overlays est déclaré AVANT le premier paint.

Le bug fermé ici
----------------

Le décor du backdrop (``fixed inset-0 bg-black/50 backdrop-blur-sm``) vient
de Tailwind, qui arrive APRÈS le premier paint — compilé dans le navigateur
en dev, appliqué après coup au sous-arbre inséré par une nav partielle. À
cet instant ``opacity`` et ``visibility``, qui sont dans un
``transition ... 200ms``, animent depuis leur valeur NON-STYLÉE (1 /
visible) vers l'état fermé. Résultat mesuré : un voile flouté plein écran
qui s'efface en 200 ms, sur **toute** page portant un dialog ou un drawer.

Le garde-fou ``html:not(.bz-ready) [bz-data]{visibility:hidden}`` ne
couvre pas ce cas : ``visibility`` est écrasable par un descendant, et le
backdrop calcule explicitement ``visible`` pendant sa transition.

Le correctif tient en deux moitiés qui doivent rester d'accord :
``show_attrs`` pose le marqueur, la feuille anti-flash du shell le cible.
Si l'une bouge sans l'autre, le voile revient — silencieusement, et
seulement à l'œil. D'où cette gate.
"""

from __future__ import annotations

import re

from bretzel.components.base._wiring import show_attrs
from bretzel.render.shell import _ANTI_FLASH_STYLE

# La règle telle qu'elle doit exister dans la feuille inline du shell.
_RULE_RE = re.compile(
    r"\[([a-z-]+)\]\[data-open=\"false\"\]\{[^}]*opacity:0[^}]*visibility:hidden[^}]*\}"
)


def test_shell_declares_the_closed_overlay_state() -> None:
    match = _RULE_RE.search(_ANTI_FLASH_STYLE)
    assert match, (
        "La feuille anti-flash du shell ne déclare plus l'état fermé des "
        "overlays. Sans elle, tout dialog / drawer repeint un voile flouté "
        "plein écran pendant 200 ms à l'arrivée du CSS Tailwind."
    )


def test_marker_matches_the_selector() -> None:
    # Les deux moitiés du correctif, comparées l'une à l'autre.
    selector_attr = _RULE_RE.search(_ANTI_FLASH_STYLE).group(1)
    emitted = show_attrs("open", initial_open=False)
    assert selector_attr in emitted, (
        f"Le shell cible [{selector_attr}] mais show_attrs émet "
        f"{sorted(emitted)}. Les deux moitiés ont divergé : la règle ne "
        "s'applique plus à rien."
    )


def test_rule_does_not_catch_non_overlay_data_open() -> None:
    # Sidebar (rail replié) et Accordion portent aussi ``data-open="false"``
    # SANS le marqueur. Une règle visant ``[data-open=false]`` nu les
    # masquerait purement et simplement.
    # Un ``[data-open="false"]`` NON précédé d'un autre attribut = un
    # sélecteur nu, qui attraperait tout le monde.
    assert not re.search(r'(?<!\])\[data-open="false"\]\{', _ANTI_FLASH_STYLE), (
        "La règle vise data-open nu : elle masquerait la sidebar repliée "
        "et les accordéons fermés, qui portent le même attribut."
    )


def test_closed_state_is_not_important() -> None:
    # ``!important`` gagnerait aussi contre l'utilitaire Tailwind et
    # figerait le fondu de FERMETURE (200 ms) en saut sec.
    rule = _RULE_RE.search(_ANTI_FLASH_STYLE).group(0)
    assert "!important" not in rule, (
        "!important sur l'état fermé écrase l'utilitaire Tailwind et "
        "supprime le fondu de fermeture de l'overlay."
    )


def test_the_detector_still_bites() -> None:
    """Mutation : la règle anti-flash est encore reconnue dans la feuille.

    Elle est ce qui empêche un overlay de PEINDRE avant que le runtime
    ne l'ait fermé. Si la regex cessait de matcher, la gate affirmerait
    « la règle est là » sans jamais l'avoir trouvée.
    """
    found = _RULE_RE.search(
        '[data-bz-overlay][data-open="false"]{opacity:0;visibility:hidden}'
    )
    assert found, "la règle anti-flash n'est plus reconnue"
    assert found.group(1) == "data-bz-overlay"

    for licit in (
        '[data-bz-overlay][data-open="false"]{opacity:0}',
        '[data-open="false"]{opacity:0;visibility:hidden}',
    ):
        assert not _RULE_RE.search(licit), f"{licit!r} : faux positif"
