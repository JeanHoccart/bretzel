"""Une transition DÉCLARÉE doit pouvoir animer quelque chose.

Le fait gardé
--------------
Un ``transition-opacity`` sur un élément dont l'``opacity`` ne bouge
jamais est du code qui se relit comme correct et ne fait rien. Il ne
casse pas l'écran, il ne lève pas, il ne s'affiche pas en revue — il
promet un fondu et livre une apparition sèche.

Mesuré le 2026-09-01 : **19 éléments** déclaraient une transition
d'opacité, **7 n'atteignaient qu'une seule valeur**. Confirmé au
navigateur le 2026-09-04 (``tests/probes/probe_dead_transition.py``),
frise ``requestAnimationFrame`` armée avant le geste : opacité
constante à 1 sur les sept, 23 à 42 images chacun. La classe était là
depuis toujours.

Les DEUX règles, et pourquoi il en faut deux
---------------------------------------------
**1. Deux valeurs atteignables.** Une utilitaire nue donne la base (100
par défaut), une utilitaire à variante (``hover:``,
``data-[open=false]:``, ``starting:``…) donne l'alternative, un
``bz-class`` ou un ``bz-attr`` sur le même nœud aussi.

**2. Si la visibilité est pilotée par ``display``, il faut de quoi
l'animer.** C'est la moitié qui manquait, et la règle 1 seule ne
l'attrape pas : on peut très bien poser ``starting:opacity-0`` sur un
panneau que le runtime ouvre en écrivant ``style.display`` — deux
valeurs atteignables, et toujours rien à l'écran, parce que
``display`` ne se transitionne pas. Il faut ``transition-discrete``
(``transition-behavior: allow-discrete``) ET ``display`` dans la liste
des propriétés.

Ce que la gate n'affirme PAS
-----------------------------
Que le fondu soit VISIBLE. Elle lit des classes ; qu'elles compilent et
qu'elles animent se mesure au navigateur, et c'est le travail du probe
cité plus haut — qui porte ses propres témoins (``dialog`` et le fond du
``drawer``) pour qu'un banc muet ne se lise pas comme une découverte.

Elle ne couvre que l'``opacity``. Les autres propriétés
transitionnées (``translate``, ``scale``, ``visibility``, les couleurs)
demanderaient chacune leur algèbre d'atteignabilité, et une gate qui
prétend couvrir ce qu'elle ne lit pas est pire que pas de gate.

⚠️ Le piège d'écriture du détecteur, payé en le prototypant
------------------------------------------------------------
Le préfixe de variante contient ``[``, ``]``, ``=`` et ``/`` —
``group-data-[open=false]/sidebar:opacity-0``. Une classe de caractères
énumérée en rate la moitié et rend **16 faux rouges sur 19**. Le motif
juste attrape tout ce qui n'est pas une espace jusqu'au ``:`` final,
et ``test_the_detector_still_bites`` en garde un exemplaire.
"""

from __future__ import annotations

import re

from bretzel.core.tree import Element

from tests.consistency._discovery import (
    public_component_classes,
    rendered_node_of,
    ui_name_of,
    walk_elements,
)

#: Preuve de morsure : le contrôle NÉGATIF vit dans
#: ``test_the_detector_still_bites``.
MUTATION_PROOF = "test_the_detector_still_bites"

#: ``opacity-<n>``, éventuellement préfixée d'une variante et d'un ``!``.
#: Le préfixe est « tout ce qui n'est pas une espace jusqu'au dernier
#: ``:`` » — voir l'avertissement en tête.
_OPACITY = re.compile(r"(?:^|\s)(\S*?:)?!?opacity-(\d+)(?=\s|$)")

#: Déclarer une transition d'opacité : la forme nommée ou l'arbitraire.
_DECLARES = re.compile(r"transition-opacity|transition-\[[^\]]*opacity[^\]]*\]")

#: ``display`` dans la liste arbitraire des propriétés transitionnées.
_TRANSITIONS_DISPLAY = re.compile(r"transition-\[[^\]]*display[^\]]*\]")


def opacity_values(classes: str, other_sources: list[str]) -> set[str]:
    """Les valeurs d'``opacity`` que cet élément peut atteindre."""
    values: set[str] = set()
    has_bare = False
    for prefix, value in _OPACITY.findall(classes):
        values.add(value)
        if not prefix:
            has_bare = True
    if not has_bare:
        # Sans utilitaire nue, la base est celle du navigateur : 1.
        values.add("100")
    for source in other_sources:
        for _prefix, value in _OPACITY.findall(source):
            values.add(value)
    return values


def visibility_rides_display(attrs: dict) -> bool:
    """La visibilité de ce nœud passe-t-elle par ``display`` ?

    Deux formes dans ce dépôt, et une seule cause : ``bz-show`` (le
    runtime pose ``display:none``) et le pré-estampage anti-FOUC
    ``style="display:none"`` que les panneaux ancrés portent au rendu.
    """
    if "bz-show" in attrs:
        return True
    return "display:none" in str(attrs.get("style", "")).replace(" ", "")


def carriers() -> list[tuple[str, Element]]:
    """``(composant, élément)`` pour chaque nœud qui DÉCLARE le fondu."""
    found: list[tuple[str, Element]] = []
    for cls in public_component_classes():
        tree = rendered_node_of(cls)
        if tree is None:
            continue
        name = ui_name_of(cls)
        for element in walk_elements(tree):
            if _DECLARES.search(str(element.attrs.get("class", "") or "")):
                found.append((name, element))
    return found


def _other_sources(attrs: dict) -> list[str]:
    return [
        str(v) for k, v in attrs.items() if k.startswith("bz-") or k == "style"
    ]


def display_driven_nodes() -> list[tuple[str, Element]]:
    """Tous les nœuds dont la visibilité passe par ``display``.

    ⚠️ Le corpus ENTIER, pas les seuls porteurs d'un fondu — et c'est
    la correction du 2026-09-04. Le plancher ancré sur les porteurs
    tombait dès qu'on RETIRAIT un fondu (deux champs, décision de
    design), alors que le reconnaisseur allait parfaitement bien : il
    mesurait la population au lieu de la découverte, exactement ce que
    la memory ``gate_floors_must_read_the_gate_source`` interdit. Ici
    le nombre ne dépend que de ``visibility_rides_display``.
    """
    found: list[tuple[str, Element]] = []
    for cls in public_component_classes():
        tree = rendered_node_of(cls)
        if tree is None:
            continue
        name = ui_name_of(cls)
        for element in walk_elements(tree):
            if visibility_rides_display(element.attrs):
                found.append((name, element))
    return found


def test_the_sweep_finds_every_declared_transition() -> None:
    """Plancher ancré sur la DÉCOUVERTE, pas sur la population.

    Recompter les composants ne dirait rien : c'est le DÉTECTEUR qui
    peut se taire — une regex trop stricte, un rendu qui change de
    forme — et il se tairait en rendant une liste vide, soit un vert
    parfait sur zéro lecture.
    """
    found = carriers()
    assert len(found) >= 12, (
        f"le balayage ne trouve plus que {len(found)} porteurs de "
        f"transition d'opacité (>= 12 attendus, 18 le 2026-09-04). Il "
        f"s'est tu — et une gate muette affirme « aucune dérive » sans "
        f"avoir lu."
    )
    # Deux ancres de FORMES différentes : ``dialog`` déclare en
    # arbitraire (``transition-[opacity,scale,visibility]``),
    # ``checkbox`` en nommé (``transition-opacity``). Si l'une des deux
    # disparaît, c'est une famille entière d'écriture qui a cessé
    # d'être vue.
    noms = {name for name, _ in found}
    for anchor in ("dialog", "checkbox"):
        assert anchor in noms, (
            f"``{anchor}`` n'est plus vu comme déclarant une transition "
            f"d'opacité. Il l'est pourtant — donc c'est l'extraction qui "
            f"a cessé de lire cette forme."
        )


def test_a_declared_fade_can_reach_two_opacities() -> None:
    morts = []
    for name, element in carriers():
        attrs = element.attrs
        classes = str(attrs.get("class", "") or "")
        values = opacity_values(classes, _other_sources(attrs))
        if len(values) < 2:
            morts.append(f"{name} <{element.tag}> — n'atteint que {values}")

    assert not morts, (
        "Ces éléments déclarent une transition d'opacité et ne peuvent "
        "atteindre qu'UNE valeur, donc elle n'anime rien :\n  "
        + "\n  ".join(sorted(morts))
        + "\n\nOu bien donnez-leur l'état de départ (``starting:opacity-0`` "
        "pour une apparition, une variante d'état pour un aller-retour), "
        "ou bien retirez la classe. Une transition qui promet sans livrer "
        "se relit comme du code correct."
    )


def test_a_fade_over_a_display_flip_carries_what_it_needs() -> None:
    """La moitié que la règle d'atteignabilité ne voit pas."""
    incomplets = []
    vus: set[str] = set()
    for name, element in carriers():
        attrs = element.attrs
        if not visibility_rides_display(attrs):
            continue
        vus.add(name)
        classes = str(attrs.get("class", "") or "")
        manque = []
        if "transition-discrete" not in classes:
            manque.append("``transition-discrete``")
        if not _TRANSITIONS_DISPLAY.search(classes):
            manque.append("``display`` dans la liste des propriétés")
        if manque:
            incomplets.append(
                f"{name} <{element.tag}> — il manque {' et '.join(manque)}"
            )

    # Le plancher LOCAL, et il ne compte pas ``vus`` : combien de
    # composants portent un fondu est une décision de DESIGN qui bouge
    # (les deux champs en ont perdu un le 2026-09-04, puis repris un
    # plus court). Ce qui doit rester stable, c'est le RECONNAISSEUR.
    pilotes = display_driven_nodes()
    assert len(pilotes) >= 25, (
        f"``visibility_rides_display`` ne reconnaît plus que "
        f"{len(pilotes)} nœuds (>= 25 attendus, 40 le 2026-09-04). Il "
        f"s'est tu — et ce test rendrait alors un vert sur zéro élément "
        f"examiné."
    )
    assert vus, (
        f"aucun porteur de fondu n'est piloté par ``display`` — le "
        f"croisement des deux lectures ne donne plus rien, alors que "
        f"{len(pilotes)} nœuds le sont."
    )

    assert not incomplets, (
        "Ces éléments fondent par-dessus un changement de ``display``, "
        "qui ne se transitionne pas :\n  "
        + "\n  ".join(sorted(incomplets))
        + "\n\nIl faut les deux : ``transition-discrete`` "
        "(``transition-behavior: allow-discrete``) pour que ``display`` "
        "attende la fin du fondu, et ``display`` dans la liste des "
        "propriétés. Sans eux l'élément apparaît d'un coup à opacité "
        "pleine — mesuré, cf. ``probe_dead_transition``."
    )


def test_the_tooltip_budget_matches_its_fade() -> None:
    """Le seul composant dont deux attentes s'AJOUTENT.

    Le tooltip attend son délai, PUIS fond. Ce qui se ressent est la
    somme — 300 ms du survol au texte lisible — et elle est répartie
    entre un nombre Python (``DEFAULT_DELAY_MS``) et une classe
    Tailwind (``duration-75``). Deux moitiés dans deux langages, qu'un
    seul changement peut désaccorder en silence : passer la classe à
    ``duration-150`` rallongerait le total à 375 sans qu'aucun test ne
    bouge, et personne ne relit un nombre pour vérifier une classe.
    """
    from bretzel.components.overlay.tooltip.tooltip import Tooltip
    from bretzel.components.overlay.tooltip.theme import TOOLTIP_THEME

    panel = TOOLTIP_THEME["slots"]["panel"]
    durations = re.findall(r"(?:^|\s)duration-(\d+)(?=\s|$)", panel)
    assert durations == [str(Tooltip.FADE_MS)], (
        f"le thème du tooltip déclare {durations or 'aucune durée'} et "
        f"``Tooltip.FADE_MS`` vaut {Tooltip.FADE_MS}. Les deux moitiés "
        f"du budget ont divergé : le total ressenti n'est plus "
        f"{Tooltip.REVEAL_BUDGET_MS} ms."
    )
    assert (
        Tooltip.DEFAULT_DELAY_MS + Tooltip.FADE_MS == Tooltip.REVEAL_BUDGET_MS
    ), "le délai par défaut n'est plus dérivé du budget"


def test_the_detector_still_bites() -> None:
    """Les deux versants, sur des classes FABRIQUÉES."""

    # ── Versant ILLICITE : les formes qui ont vraiment existé ─────────
    # La forme exacte que portaient les sept : elle n'atteint que la base.
    assert opacity_values("transition-opacity duration-150", []) == {"100"}
    assert visibility_rides_display({"style": "display:none"})
    assert visibility_rides_display({"bz-show": "open"})

    # ── Versant LICITE, et c'est lui qui coûte cher ───────────────────
    # Le préfixe de variante à crochets : une classe de caractères
    # énumérée le ratait et rendait 16 faux rouges sur 19.
    assert opacity_values(
        "group-data-[open=false]/sidebar:opacity-0 transition-opacity", []
    ) == {"0", "100"}, (
        "le détecteur ne lit plus les variantes à crochets — il "
        "rougirait sur des composants parfaitement sains, et c'est "
        "comme ça qu'une gate se fait débrancher."
    )
    # ``starting:`` est la forme livrée le 2026-09-04.
    assert opacity_values("starting:opacity-0", []) == {"0", "100"}
    # Une opacité nue REMPLACE la base, elle ne s'y ajoute pas.
    assert opacity_values("opacity-70", []) == {"70"}
    assert opacity_values("opacity-70 hover:opacity-100", []) == {"70", "100"}
    # Un nœud sans pilotage par ``display`` n'a rien à déclarer de plus.
    assert not visibility_rides_display({"class": "opacity-0", "style": "z-index:1"})
    # ``display:flex`` n'est pas un masquage.
    assert not visibility_rides_display({"style": "display:flex"})
