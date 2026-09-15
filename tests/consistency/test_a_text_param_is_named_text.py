"""Gate : le paramètre de texte libre s'appelle ``text``, pas ``content``.

Le défaut qu'elle ferme
-----------------------
Quatre contre quatre, pour la même chose — mesuré le 2026-09-06 ::

    text      code, markdown, title, tooltip
    content   heading, html, meta_tag, text

Et le couple le plus coûteux était le plus visible : ``ui.text`` prenait
``content=`` pendant que ``ui.title`` prenait ``text=``. Exactement à
l'envers de ce qu'on suppose en lisant le nom du composant.

Arbitré en faveur de ``text``, avec **une** exception déclarée.

L'exception, et pourquoi elle n'est pas un compromis
----------------------------------------------------
``ui.meta_tag(content=…)`` garde son nom parce que ce n'est pas un choix
de style : c'est le nom de l'attribut HTML qu'il émet,
``<meta name="…" content="…">``. Le renommer ferait diverger l'API du
balisage qu'elle produit — le contraire de ce que cette gate cherche.

C'est la même logique que ``ui.image(alt=)`` ou ``ui.iframe(title=)`` :
quand le HTML a déjà nommé la chose, on ne la renomme pas.

Ce que la gate NE dit pas
-------------------------
Qu'un composant DOIT avoir un paramètre de texte. Elle interdit un nom,
elle n'en impose aucun.
"""

from __future__ import annotations

import inspect

import pytest

from tests.consistency._discovery import public_component_classes, ui_name_of

#: Le seul composant qui garde ``content`` — et il ne le garde pas par
#: habitude : c'est l'attribut HTML qu'il écrit.
MIRRORS_AN_HTML_ATTRIBUTE = frozenset({"meta_tag"})

BANNED = "content"


def components() -> list[tuple[str, tuple[str, ...]]]:
    return [
        (ui_name_of(cls), tuple(inspect.signature(cls.__init__).parameters))
        for cls in sorted(public_component_classes(), key=ui_name_of)
    ]


# ── Les planchers ─────────────────────────────────────────────────────


def test_the_sweep_reads_the_catalog() -> None:
    found = components()
    assert len(found) >= 90, (
        f"seulement {len(found)} composant(s) public(s) lu(s) — il y en "
        f"avait 105 le 2026-09-06. Le balayage est cassé."
    )


def test_the_reader_sees_the_text_params() -> None:
    """Second plancher : le nom retenu EXISTE dans le corpus.

    Une gate qui interdit un nom sans vérifier que le nom de
    remplacement est employé resterait verte sur un catalogue qui les
    aurait tous perdus.
    """
    carriers = [name for name, params in components() if "text" in params]
    assert len(carriers) >= 5, (
        f"seulement {len(carriers)} composant(s) exposent `text=` : "
        f"{carriers}. Le nom retenu a disparu du catalogue."
    )


# ── L'assertion ───────────────────────────────────────────────────────


@pytest.mark.parametrize(("name", "params"), components(), ids=lambda v: v)
def test_no_component_exposes_content(
    name: str, params: tuple[str, ...]
) -> None:
    if name in MIRRORS_AN_HTML_ATTRIBUTE:
        assert BANNED in params, (
            f"`ui.{name}` n'expose plus `content=` : retire-le de "
            f"MIRRORS_AN_HTML_ATTRIBUTE. Une liste d'exceptions qui ment "
            f"ne protège plus rien."
        )
        return
    assert BANNED not in params, (
        f"`ui.{name}` expose `{BANNED}=`.\n"
        f"  Le paramètre de texte libre du catalogue s'appelle `text` "
        f"depuis le 2026-09-06 — il était écrit des deux façons, quatre "
        f"contre quatre, et `ui.text(content=)` face à `ui.title(text=)` "
        f"était exactement à l'envers.\n"
        f"  La seule exception est `ui.meta_tag`, dont le `content` est "
        f"l'attribut HTML qu'il émet."
    )


# ── La morsure ────────────────────────────────────────────────────────


def test_the_detector_catches_a_content_param() -> None:
    """Mutation : fabriquée en mémoire, les deux versants."""
    fautif = ("self", "content", "size")
    licite = ("self", "text", "size")

    assert BANNED in fautif
    assert BANNED not in licite
    # Et le détecteur ne confond pas un nom qui CONTIENT le mot.
    assert BANNED not in ("self", "content_type", "empty_content")
