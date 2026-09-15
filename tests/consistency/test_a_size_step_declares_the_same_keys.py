"""Tous les paliers d'une table ``sizes`` déclarent les MÊMES clés.

Le défaut que ça ferme, mesuré le 2026-08-25 sur `ui.calendar`
------------------------------------------------------------------
Le rendu lit une taille par ``size_map.get("<clé>", "")``. Une clé
présente à quatre paliers et absente au cinquième rend donc la **chaîne
vide** — pas une erreur, pas un warning, juste un élément qui retombe sur
sa taille intrinsèque. Et « intrinsèque » veut dire *décidée par le
contenu* : c'est exactement la panne qu'on venait de réparer.

L'histoire, parce qu'elle explique la forme de cette gate : le slot
``root`` de `ui.calendar` valait ``w-fit``, donc la largeur du calendrier
était ``max(en-tête, grille)`` — et le libellé du mois est du texte de
largeur variable. Mesuré à ``md`` en français : **278 px en « août »,
292,8 px en « septembre », et la flèche « mois suivant » se déplaçait de
14,8 px**. On clique sur la cible, elle se dérobe. La réparation déclare
une largeur par palier ; un palier qui l'oublierait ramènerait le défaut
sur ce seul palier, ce qui est pire — personne ne teste les cinq.

Ce que cette gate N'EST PAS
----------------------------
Elle ne juge pas les VALEURS. « ``xs`` est-il plus petit que ``sm`` » est
la question de ``test_sizes_are_distinct`` ; « la table couvre-t-elle les
cinq paliers » celle de ``test_size_enum_is_complete`` ; « le palier
atteint-il les slots » celle de ``test_size_reaches_slots``. Ici on ne
demande qu'une chose, et elle est purement mécanique : **les paliers
d'une même table parlent du même vocabulaire.**

Le versant navigateur — que la largeur ne bouge réellement pas d'un mois
à l'autre — est dans ``tests/probes/probe_calendar_width.py`` (cinq
paliers × deux langues). Une gate ne peut pas mesurer des pixels.
"""

from __future__ import annotations

import pytest

from tests.consistency._discovery import public_component_classes

#: 33 composants ont une table dont les paliers sont des dictionnaires
#: (mesuré le 2026-08-25). Le seuil laisse de la marge sans laisser
#: passer un balayage casse.
_TABLES_FLOOR = 25


def size_tables() -> list[tuple[str, dict[str, dict]]]:
    """(nom du composant, paliers) pour toute table à paliers-dict.

    Une table dont les paliers sont des CHAÎNES (``{"md": "h-10 w-10"}``,
    le cas d'``ui.icon_button``) n'a pas de vocabulaire à comparer : il
    n'y a qu'une valeur par palier. On ne garde que les tables dont les
    paliers sont des dictionnaires de clés nommées, et il en faut au
    moins deux pour qu'une comparaison ait un sens.
    """
    out: list[tuple[str, dict[str, dict]]] = []
    for cls in public_component_classes():
        theme = getattr(cls, "THEME", None)
        if not isinstance(theme, dict):
            continue
        sizes = theme.get("sizes")
        if not isinstance(sizes, dict):
            continue
        steps = {k: v for k, v in sizes.items() if isinstance(v, dict)}
        if len(steps) >= 2:
            out.append((cls.__name__, steps))
    return out


def uneven_steps(steps: dict[str, dict]) -> list[str]:
    """Les paliers auxquels il manque une clé que les autres déclarent.

    Extrait pour être mutable : c'est le détecteur, et une gate dont le
    detecteur vit inline dans le test ne se prouve pas.
    """
    vocabulary: set[str] = set().union(*(set(v) for v in steps.values()))
    return [
        f"{step} (manque {sorted(vocabulary - set(tokens))})"
        for step, tokens in steps.items()
        if vocabulary - set(tokens)
    ]


_TABLES = size_tables()
_IDS = [name for name, _ in _TABLES]


# ── (1) Plancher — ancré sur la DÉCOUVERTE de cette gate ───────────────

def test_the_sweep_finds_the_size_tables() -> None:
    assert len(_TABLES) >= _TABLES_FLOOR, (
        f"le balayage ne trouve plus que {len(_TABLES)} tables de tailles "
        f"à paliers-dict (>= {_TABLES_FLOOR} attendues) — vérifie la lecture "
        f"du thème avant de croire que l'interdiction ci-dessous passe."
    )
    # Contrôle POSITIF : le calendrier est l'usager qui a produit cette
    # gate. S'il sort du balayage, elle ne garde plus rien de ce qu'elle
    # a été écrite pour garder.
    assert "Calendar" in _IDS, (
        f"Calendar n'est plus dans le balayage : {sorted(_IDS)[:10]}…"
    )


# ── (2) L'interdiction ─────────────────────────────────────────────────

@pytest.mark.parametrize("name,steps", _TABLES, ids=_IDS)
def test_every_step_speaks_the_same_vocabulary(name: str, steps: dict) -> None:
    uneven = uneven_steps(steps)
    assert not uneven, (
        f"{name} : des paliers de sa table ``sizes`` ne déclarent pas les "
        f"mêmes clés — {'; '.join(uneven)}.\n\n"
        f"Le rendu lit ``size_map.get(\"<clé>\", \"\")`` : la clé manquante "
        f"rend la chaîne VIDE, donc l'élément retombe sur sa taille "
        f"intrinsèque — décidée par son contenu — à ce seul palier. "
        f"Aucune erreur, et personne ne teste les cinq."
    )


def test_the_calendar_declares_a_width_at_every_step() -> None:
    """Le cas qui a produit la gate, nommé pour qu'il ne se perde pas.

    Sans ``root`` dans la table, le calendrier n'a plus de largeur
    déclarée et la reprend de son contenu : le libellé du mois décide,
    et la flèche « mois suivant » se déplace de 14,8 px entre « août »
    et « septembre ».
    """
    steps = dict(_TABLES)["Calendar"]
    without = sorted(step for step, tokens in steps.items() if not tokens.get("root"))
    assert not without, (
        f"des paliers de ui.calendar ne déclarent aucune largeur : {without}. "
        f"Cf. tests/probes/probe_calendar_width.py."
    )


# ── (3) La mutation, dans les DEUX sens ────────────────────────────────

def test_the_detector_catches_a_hole_and_spares_a_full_table() -> None:
    # Le versant qui MORD : une clé qui manque à un seul palier.
    broken = {
        "sm": {"root": "w-62", "day_cell": "w-8"},
        "md": {"day_cell": "w-9"},
    }
    assert uneven_steps(broken) == ["md (manque ['root'])"], uneven_steps(broken)

    # Le versant qui ÉPARGNE — c'est celui qui trouve les faux positifs.
    # Des VALEURS différentes sont le sujet même d'une table de tailles :
    # seule l'absence d'une clé compte.
    full = {
        "sm": {"root": "w-62", "day_cell": "w-8"},
        "md": {"root": "w-69", "day_cell": "w-9"},
    }
    assert not uneven_steps(full), uneven_steps(full)

    # Un palier vide des DEUX côtés n'est pas un trou : il n'y a pas de
    # vocabulaire à trahir.
    assert not uneven_steps({"sm": {}, "md": {}})
