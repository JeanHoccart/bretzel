"""Gate : un plafond de largeur sur une RACINE connaît son conteneur.

Le défaut, rapporté par l'utilisateur le 2026-08-25
----------------------------------------------------
Sur l'écran Paramètres du CRM, le `ui.toggle_group` « Densité » sortait
de sa colonne et se posait sur le `ui.select` voisin — « Aérée » coupé.
Mesuré dans une cellule de grille de 240 px : **255,9 px** avec trois
libellés courts, **299,3 px** avec des libellés normaux. Sa racine valait
`w-fit`, c'est-à-dire « je fais la taille de mon contenu », et **rien ne
la plafonnait**.

La mesure a trouvé une seconde instance que personne n'avait vue, et son
mécanisme est plus retors : `ui.badge` avait bien un plafond —
`max-w-[16rem]` — mais **fixe**. Un plafond fixe ne connaît pas son
conteneur : dans une colonne plus étroite que lui, il ne borne rien.
Mesuré, la même cellule de 240 px : **256 px rendus, 17 px dehors**.

Ce que la gate exige
---------------------
Qu'une racine qui déclare un plafond en déclare un **relatif au
conteneur** — `max-w-full`, ou une valeur arbitraire qui contient `100%`.
Un plafond fixe peut l'accompagner (« au plus 16rem, et jamais plus que
ma colonne »), il ne peut pas être seul.

Six des sept racines à plafond du catalogue écrivaient déjà `max-w-full`
au moment de l'écriture : la convention existait, `badge` était la seule
à y échapper, et c'est très exactement celle qui débordait.

⚠️ Et **une seule classe**, pas deux
--------------------------------------
`max-w-full max-w-[16rem]` posent toutes deux `max-width` sur le même
élément : le vainqueur est décidé par l'ordre de la FEUILLE compilée, pas
par l'ordre des classes. On ne peut donc pas empiler les deux moitiés —
il faut une valeur qui les combine, `max-w-[min(16rem,100%)]`, ce que la
seconde moitié de cette gate vérifie.

Ce qu'elle ne juge PAS
-----------------------
Les autres slots. Un panneau flottant (`dropdown`, `popover`, le panneau
d'un picker) est hors du flux : un plafond fixe y est correct, il ne peut
pousser aucun voisin. La population est donc « racines », pas « slots ».

Elle ne juge pas non plus les racines SANS plafond. Mesuré au navigateur
dans une cellule de 240 px, les quatre autres racines `w-fit` du
catalogue — `dropdown`, `popover`, `tooltip`, `link` — tiennent
parfaitement : leur largeur est celle de leur déclencheur, qui se borne
lui-même. Exiger un plafond d'elles serait du travail sans défaut à
réparer.

Le versant navigateur — que le composant reste VRAIMENT dans sa colonne —
ne peut pas se mesurer ici ; il l'a été à la main sur un banc à 240 px, et
les chiffres ci-dessus en viennent.
"""

from __future__ import annotations

import re

import pytest

from tests.consistency._discovery import public_component_classes, ui_name_of

#: Tout plafond de largeur, quelle que soit sa forme.
_CEILING = re.compile(r"(?:^|\s)(max-w-\S+)")

#: Ceux qui connaissent leur conteneur. ``max-w-full`` est la forme
#: courante ; une valeur arbitraire qui contient ``100%`` en est une aussi
#: (``max-w-[min(16rem,100%)]``), et c'est la seule façon d'écrire « au
#: plus X, et jamais plus que ma colonne » en UNE classe.
_RELATIVE = re.compile(r"^max-w-(?:full|\[[^\]]*100%[^\]]*\])$")

#: Sept racines à plafond mesurées le 2026-08-25 : badge, calendar,
#: iframe, image, table, toggle_group, video. Le seuil laisse de la marge
#: sans laisser passer une découverte cassée.
_ROOTS_FLOOR = 6


def root_class(cls: type) -> str:
    theme = getattr(cls, "THEME", None)
    if not isinstance(theme, dict):
        return ""
    root = theme.get("slots", {}).get("root")
    return root if isinstance(root, str) else ""


def ceilings(root: str) -> list[str]:
    """Les plafonds déclarés par cette racine. Le DÉTECTEUR, isolé pour
    que la preuve de morsure l'attaque sur des chaînes fabriquées."""
    return _CEILING.findall(root)


def is_relative(ceiling: str) -> bool:
    return bool(_RELATIVE.match(ceiling))


def roots_with_a_ceiling() -> list[tuple[str, str]]:
    return sorted(
        (ui_name_of(cls), root_class(cls))
        for cls in public_component_classes()
        if ceilings(root_class(cls))
    )


_POPULATION = roots_with_a_ceiling()


# ── Plancher ──────────────────────────────────────────────────────────

def test_the_sweep_finds_the_roots_with_a_ceiling() -> None:
    assert len(_POPULATION) >= _ROOTS_FLOOR, (
        f"seulement {len(_POPULATION)} racines à plafond trouvées "
        f"({[n for n, _ in _POPULATION]}) — sept mesurées le 2026-08-25. "
        f"Vérifie la découverte avant de croire que cette gate passe."
    )


# ── L'interdiction ────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "name,root", _POPULATION, ids=[n for n, _ in _POPULATION]
)
def test_the_ceiling_knows_its_container(name: str, root: str) -> None:
    found = ceilings(root)
    assert any(is_relative(c) for c in found), (
        f"la racine de ui.{name} déclare {found} — que des plafonds FIXES.\n"
        f"Un plafond fixe ne connaît pas son conteneur : dans une colonne "
        f"plus étroite que lui, il ne borne rien et le composant se pose "
        f"sur son voisin. Mesuré sur ui.badge : 256 px dans une cellule de "
        f"240, soit 17 px dehors.\n"
        f"Écris `max-w-full`, ou `max-w-[min(<fixe>,100%)]` si tu veux "
        f"garder les deux limites."
    )


@pytest.mark.parametrize(
    "name,root", _POPULATION, ids=[n for n, _ in _POPULATION]
)
def test_a_root_declares_only_one_ceiling(name: str, root: str) -> None:
    """Deux ``max-w-*`` sur le même élément posent deux fois la même
    propriété : le vainqueur dépend de l'ordre de la FEUILLE compilée, pas
    de celui des classes. C'est l'écriture qu'on tente naturellement pour
    combiner un plafond fixe et un plafond relatif, et elle est
    indéterminée."""
    found = ceilings(root)
    assert len(found) == 1, (
        f"la racine de ui.{name} déclare {len(found)} plafonds : {found}. "
        f"Ils posent tous `max-width` — lequel gagne dépend de l'ordre de "
        f"la feuille Tailwind, pas du tien. Combine-les en une seule "
        f"valeur : `max-w-[min(16rem,100%)]`."
    )


# ── Preuve que le détecteur mord, dans les DEUX sens ──────────────────

def test_the_detector_bites_on_a_fixed_ceiling() -> None:
    """Le versant ILLICITE — l'écriture exacte que ``badge`` portait."""
    fautif = "inline-flex w-fit items-center gap-1 max-w-[16rem] rounded-md"
    assert ceilings(fautif) == ["max-w-[16rem]"]
    assert not any(is_relative(c) for c in ceilings(fautif))


def test_the_detector_stays_quiet_on_the_licit_forms() -> None:
    """Le versant LICITE, et c'est lui qui a trouvé les deux seuls bugs de
    gate du dépôt : un détecteur qui rougit sur un cas correct est aussi
    cassé qu'un détecteur aveugle.

    Trois écritures correctes, et une quatrième qui n'a PAS de plafond du
    tout — elle doit sortir de la population, pas la faire rougir.
    """
    assert is_relative("max-w-full")
    assert is_relative("max-w-[min(16rem,100%)]")
    assert is_relative("max-w-[calc(100%-2rem)]")
    # Sans plafond → hors population, donc jamais jugée.
    assert ceilings("relative inline-flex w-fit h-fit") == []


def test_the_detector_does_not_confuse_min_width() -> None:
    """``min-w-0`` contient ``w-`` et ne doit pas passer pour un plafond.

    Ce n'est pas théorique : ``min-w-0`` est posé sur la MÊME racine que
    des plafonds dans plusieurs thèmes, et une expression trop large ferait
    compter deux plafonds là où il n'y en a qu'un — donc rougir sur du
    correct par la seconde moitié de cette gate.
    """
    assert ceilings("inline-flex min-w-0 max-w-full items-center") == [
        "max-w-full"
    ]
