"""Gate — le panneau de rail de la sidebar est visuellement un tooltip.

Ce qu'elle garde
-----------------
``ui.sidebar`` en mode rail replié montre le libellé de l'entrée survolée
dans un panneau flottant. Ce panneau n'EST pas un :class:`Tooltip` : la
sidebar en rend **un seul**, qu'elle déplace sur l'entrée survolée, au
lieu d'un ``ui.tooltip`` par entrée. C'est un choix de poids, et il est
mesuré — 20 entrées coûtent **38 ko** de panneaux pré-rendus (≈1,9 ko
l'unité) pour une affordance qui n'en montre jamais qu'un.

Le prix de ce choix, c'est que la surface du tooltip est écrite DEUX
fois : dans ``TOOLTIP_THEME["slots"]["panel"]`` et dans
``SIDEBAR_THEME["slots"]["rail_tip"]``. Rien ne les tenait ensemble, et
elles avaient dérivé — constaté le 2026-08-25 par l'utilisateur, sur une
capture de deux tooltips côte à côte :

- le panneau du rail n'avait **aucune flèche**, là où tout ``ui.tooltip``
  en porte une ;
- son texte tirait sur ``text-background`` (248,250,252) contre
  ``text-text-foreground`` (244,245,245) pour le vrai.

Cette gate dit : *deux panneaux qui doivent se ressembler et qui sont
écrits deux fois se comparent mécaniquement.* Un token de surface retiré
d'un côté et pas de l'autre la fait rougir.

Ce qu'elle ne garde PAS
------------------------
Elle compare des CLASSES, pas des pixels. Elle ne peut pas voir un écart
de rendu que les deux thèmes écriraient pareil — c'est le mode d'échec
de ``test_form_controls_share_one_height``, qui a dû aller au navigateur
pour 2 px que les classes ne montraient pas. Ici l'écart était bien dans
les classes, donc une gate statique le tient.
"""

from __future__ import annotations

from bretzel.components.navigation.sidebar.theme import SIDEBAR_THEME
from bretzel.components.overlay.tooltip.theme import TOOLTIP_THEME

#: Le vocabulaire comparé : ce qui fait qu'un panneau se LIT comme un
#: tooltip. Volontairement pas « toutes les classes » — ``z-40`` contre
#: ``z-50``, ``absolute`` contre ``fixed``, les variantes de visibilité
#: du rail : ces écarts-là sont structurels et légitimes, les inclure
#: rendrait la gate ininterprétable et donc désactivée à la première
#: rougeur.
_SURFACE_PREFIXES: tuple[str, ...] = (
    "bg-", "text-", "font-", "leading-", "px-", "py-", "rounded-",
    "shadow-", "max-w-", "break-",
)

#: La forme de la flèche, même logique. Sa POSITION n'y est pas : le
#: tooltip porte les quatre côtés en ``group-data-[side=…]`` parce qu'il
#: peut basculer, le rail n'en porte qu'un — une nav latérale vit à
#: gauche (``Sidebar._CUT["side"]``) et le panneau s'ancre sur
#: ``aside.right + 8``, donc il est toujours à droite de l'entrée.
_ARROW_PREFIXES: tuple[str, ...] = ("h-", "w-", "rotate-", "bg-")

#: Les divergences ASSUMÉES, avec leur raison. Une divergence non écrite
#: est indiscernable d'une dérive — c'est exactement ce qui a laissé
#: passer celle du 2026-08-25.
_ACCEPTED: dict[str, str] = {
    "whitespace-nowrap": (
        "un libellé d'entrée de rail est court ; le replier sur deux "
        "lignes à côté d'une icône de 40 px se lit mal"
    ),
}


def surface(classes: str, prefixes: tuple[str, ...]) -> set[str]:
    """Les tokens de surface d'une chaîne de classes.

    Extrait — donc mutable par ``test_the_comparison_still_bites``. Les
    variantes (``group-data-[…]:``, ``hover:``…) sont écartées : elles
    portent un ÉTAT, pas la surface au repos.
    """
    return {
        tok
        for tok in classes.split()
        if ":" not in tok and tok.startswith(prefixes)
    }


def panel_tokens() -> set[str]:
    return surface(TOOLTIP_THEME["slots"]["panel"], _SURFACE_PREFIXES)


def rail_tokens() -> set[str]:
    return surface(SIDEBAR_THEME["slots"]["rail_tip"], _SURFACE_PREFIXES)


def _resolved(token: str) -> str:
    """``bg-{bg_color}`` du tooltip vaut ``bg-text`` : sa couleur par
    défaut est ``color="text"`` (``Tooltip.color``), et le rail l'écrit
    en dur puisqu'il n'a pas de prop ``color``."""
    return token.replace("{bg_color}", "text").replace(
        "{fg_color}", "text-foreground"
    )


# ───────────────────────────────────────────────────────────────────────
# ① Planchers — la gate compare vraiment quelque chose
# ───────────────────────────────────────────────────────────────────────


def test_both_panels_were_found() -> None:
    """Un slot renommé viderait la comparaison sans la faire rougir."""
    assert "panel" in TOOLTIP_THEME["slots"], (
        "`TOOLTIP_THEME` n'a plus de slot `panel` — la comparaison "
        "ci-dessous porterait sur la chaîne vide, donc sur rien."
    )
    for slot in ("rail_tip", "rail_tip_arrow"):
        assert slot in SIDEBAR_THEME["slots"], (
            f"`SIDEBAR_THEME` n'a plus de slot `{slot}`. Si le panneau de "
            f"rail a été remplacé par un vrai `ui.tooltip`, cette gate n'a "
            f"plus lieu d'être — supprime-la plutôt que de la laisser "
            f"verte à vide."
        )


def test_the_extraction_is_not_vacuous() -> None:
    """Le plancher lit la découverte de CETTE gate, pas une source
    fraîche — cf. la memory ``gate_floors_must_read_the_gate_source``."""
    found = panel_tokens()
    assert len(found) >= 8, (
        f"seulement {len(found)} token(s) de surface extrait(s) du panneau "
        f"de tooltip : {sorted(found)}. Le vocabulaire de "
        f"`_SURFACE_PREFIXES` ne matche plus le thème, et l'égalité "
        f"ci-dessous serait vraie par vacuité."
    )


# ───────────────────────────────────────────────────────────────────────
# ② L'interdiction
# ───────────────────────────────────────────────────────────────────────


def test_the_rail_panel_wears_the_tooltip_surface() -> None:
    attendu = {_resolved(t) for t in panel_tokens()}
    manquants = attendu - rail_tokens()
    assert not manquants, (
        f"le panneau de rail de la sidebar a perdu {sorted(manquants)}, "
        f"que porte `TOOLTIP_THEME['slots']['panel']`. Les deux se lisent "
        f"côte à côte dans la même app — un rail replié montre le sien à "
        f"l'endroit exact où un `ui.tooltip` montrerait l'autre. Réaligne "
        f"`SIDEBAR_THEME['slots']['rail_tip']`, ou déclare la divergence "
        f"dans `_ACCEPTED` avec sa raison."
    )


def test_the_rail_panel_adds_nothing_undeclared() -> None:
    """L'autre sens : un token que le rail ajoute et que le tooltip n'a
    pas est une divergence aussi, et elle doit être ÉCRITE."""
    attendu = {_resolved(t) for t in panel_tokens()}
    en_trop = rail_tokens() - attendu - set(_ACCEPTED)
    assert not en_trop, (
        f"le panneau de rail porte {sorted(en_trop)} en plus du panneau de "
        f"tooltip. Si c'est voulu, ajoute-le à `_ACCEPTED` avec la raison "
        f"— une divergence non écrite est indiscernable d'une dérive, et "
        f"c'est exactement ce qui a laissé passer l'absence de flèche "
        f"jusqu'au 2026-08-25."
    )


def test_the_rail_panel_has_an_arrow() -> None:
    """La flèche est ce que l'utilisateur a vu manquer en premier."""
    attendu = {
        _resolved(t)
        for t in surface(TOOLTIP_THEME["slots"]["arrow"], _ARROW_PREFIXES)
    }
    manquants = attendu - surface(
        SIDEBAR_THEME["slots"]["rail_tip_arrow"], _ARROW_PREFIXES
    )
    assert not manquants, (
        f"la flèche du panneau de rail a perdu {sorted(manquants)} par "
        f"rapport à celle de `ui.tooltip`. C'est la différence que "
        f"l'utilisateur a vue le 2026-08-25 : le panneau du rail n'en "
        f"avait aucune."
    )


# ───────────────────────────────────────────────────────────────────────
# ③ La mutation — dans les DEUX sens
# ───────────────────────────────────────────────────────────────────────


def test_the_comparison_still_bites() -> None:
    """Le versant qui mord, et le versant licite.

    Le second n'est pas décoratif : si l'extraction ramassait aussi les
    tokens à variante, le rail et le tooltip divergeraient sur des
    dizaines de classes d'état et la gate serait rouge en permanence,
    donc désactivée.
    """
    tooltip_like = "px-2.5 py-1.5 rounded-lg bg-text shadow-md"
    # Mord : un token de surface retiré est vu comme manquant.
    assert surface(tooltip_like, _SURFACE_PREFIXES) - surface(
        "px-2.5 py-1.5 rounded-lg bg-text", _SURFACE_PREFIXES
    ) == {"shadow-md"}
    # Épargne : une variante d'état n'est PAS une divergence de surface.
    assert surface(
        tooltip_like + " group-data-[side=top]:bg-red-500 hover:px-8",
        _SURFACE_PREFIXES,
    ) == surface(tooltip_like, _SURFACE_PREFIXES)
    # Épargne : un token hors vocabulaire (position, z-index) non plus.
    assert surface(tooltip_like + " fixed z-50", _SURFACE_PREFIXES) == surface(
        tooltip_like + " absolute z-40", _SURFACE_PREFIXES
    )
