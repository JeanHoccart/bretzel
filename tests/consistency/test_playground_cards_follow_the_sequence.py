"""Gate : les cartes d'une page de playground suivent la séquence du gabarit.

Le défaut qu'elle ferme
-----------------------
``playground-pattern.md`` § 3 fixe l'ordre des sept sections, et c'est
un ordre de LECTURE : on montre le composant, puis ses cas limites, puis
on le pilote depuis le serveur, puis depuis le client. Mesuré le
2026-09-06 : **7 pages sur 74** ne le suivaient pas, chacune à sa façon —

    tree        Client playground remonté juste après Reference
    diagram     Client playground AVANT Server events
    calendar    External controls après Client events
    audio       Composability avant Edge cases
    iframe      idem
    meta        idem
    pagination  External controls après Client events

Aucune relecture ne l'attrape : chaque page est cohérente avec
elle-même, et il faut comparer les 74 pour que l'écart apparaisse.
C'est la même maladie que les deux conventions de nommage des helpers,
et elle appelle le même remède — une gate, pas une relecture.

⚠️ **La queue physique est §5 → §7 → §6**, pas la suite numérique : les
contrôles impératifs viennent AVANT les events clients. Le gabarit
l'écrit et le corpus le confirme (17 pages contre 0). C'est l'ordre de
CANON ci-dessous qui fait foi, pas la numérotation des sections.

Ce que la gate NE dit pas
-------------------------
Quelles cartes une page doit porter — c'est
``test_playground_demos_the_api`` et le gabarit qui l'arbitrent. Ici on
ne juge que l'ORDRE de celles qui sont là, et une carte hors catalogue
(``ui.meta`` en a six : Title, MetaTag, Fragment, Interval,
``filter_each``, Verbes clients) est ignorée plutôt que classée de
force.
"""

from __future__ import annotations

import re

import pytest

from tests.consistency._discovery import REPO_ROOT

#: L'ordre de lecture, queue comprise (§5 → §7 → §6).
CANON = (
    "Reference", "Slots", "Edge cases", "Composability", "A11y",
    "Server playground", "Server events", "Client playground",
    "External controls", "Client events",
)

#: Le titre est parfois suivi d'une glose (« External controls — the 3
#: modes »), d'où le préfixe plutôt que l'égalité.
HEADING = re.compile(r'ui\.heading\(\s*"([^"]+)"[^)]*level=2')

PLAYGROUND = REPO_ROOT / "examples" / "playground" / "features"

#: Les pages qui ne sont PAS la page d'un composant, et dont la
#: séquence ne veut donc rien dire. Une liste qui ne fait que rétrécir —
#: et elle est VIDE depuis le 2026-09-07.
#:
#: ``meta.py`` y a figuré une journée, sur un raisonnement trop rapide :
#: elle couvre six marqueurs de framework (Title, MetaTag, Fragment,
#: Interval, ``filter_each``, Verbes clients) dont les cartes
#: s'intercalent, et j'en avais conclu que la séquence ne s'y appliquait
#: pas. Faux : la gate IGNORE les cartes hors catalogue, donc son seul
#: écart était le même que partout ailleurs — Composability avant Edge
#: cases, deux cartes adjacentes. Une exception déclarée sur une lecture
#: à moitié faite reste une exception de trop.
NOT_A_COMPONENT_PAGE: frozenset[str] = frozenset()


def card_sequences() -> list[tuple[str, tuple[str, ...]]]:
    """Les titres canoniques de niveau 2, dans l'ordre du fichier."""
    found = []
    for path in sorted(PLAYGROUND.rglob("*.py")):
        source = path.read_text(encoding="utf-8-sig")
        titles = tuple(
            canon
            for raw in HEADING.findall(source)
            for canon in CANON
            if raw.startswith(canon)
        )
        if len(titles) < 3:
            continue  # pas une page de composant
        found.append((
            str(path.relative_to(PLAYGROUND)).replace("\\", "/"), titles,
        ))
    return found


def out_of_sequence(titles: tuple[str, ...]) -> bool:
    """Le détecteur, isolé : les rangs sont-ils croissants ?"""
    ranks = [CANON.index(t) for t in titles]
    return ranks != sorted(ranks)


# ── Les planchers ─────────────────────────────────────────────────────


def test_the_sweep_finds_the_pages() -> None:
    """Sans lui, un `ui.heading` reformaté viderait le balayage."""
    found = card_sequences()
    assert len(found) >= 60, (
        f"seulement {len(found)} page(s) de composant trouvée(s) sous "
        f"{PLAYGROUND} — il y en avait 74 le 2026-09-06. Le lecteur de "
        f"titres est cassé."
    )


def test_the_reader_sees_the_whole_catalog() -> None:
    """Second plancher : les dix titres sont vus, pas seulement deux.

    Un lecteur qui ne reconnaîtrait que `Reference` rendrait toute
    séquence croissante, donc l'assertion verte partout.
    """
    seen = {t for _page, titles in card_sequences() for t in titles}
    missing = [t for t in CANON if t not in seen]
    assert not missing, (
        f"aucune page ne porte {', '.join(missing)} — le lecteur ne "
        f"reconnaît plus ces titres, et l'ordre qu'il mesure est partiel."
    )


# ── L'assertion ───────────────────────────────────────────────────────


@pytest.mark.parametrize(("page", "titles"), card_sequences(), ids=lambda v: v)
def test_a_page_follows_the_card_sequence(
    page: str, titles: tuple[str, ...]
) -> None:
    if page in NOT_A_COMPONENT_PAGE:
        assert out_of_sequence(titles), (
            f"`{page}` suit désormais la séquence : retire-le de "
            f"NOT_A_COMPONENT_PAGE, une liste d'exceptions qui ment ne "
            f"protège plus rien."
        )
        return
    assert not out_of_sequence(titles), (
        f"`{page}` présente ses cartes dans l'ordre "
        f"{' → '.join(titles)}.\n"
        f"  L'ordre du gabarit est un ordre de LECTURE : on montre le "
        f"composant, puis ses cas limites, puis on le pilote depuis le "
        f"serveur, puis depuis le client.\n"
        f"  Attendu : {' → '.join(CANON)}.\n"
        f"  ⚠️ La queue est §5 → §7 → §6 — les contrôles impératifs "
        f"AVANT les events clients (17 pages contre 0, et le gabarit "
        f"l'écrit)."
    )


# ── La morsure ────────────────────────────────────────────────────────


def test_the_detector_catches_a_shuffled_page() -> None:
    """Mutation : le détecteur voit l'inversion, et rien sur le cas licite."""
    assert not out_of_sequence(CANON)
    assert not out_of_sequence(("Reference", "A11y", "Client events"))
    assert not out_of_sequence(())

    assert out_of_sequence(("Reference", "Composability", "Edge cases"))
    assert out_of_sequence(
        ("Server playground", "Client playground", "Server events")
    )
    assert out_of_sequence(("Client events", "External controls"))
