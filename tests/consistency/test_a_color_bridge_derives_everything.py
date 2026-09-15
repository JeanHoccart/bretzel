"""Un pont de couleur ne fige rien : il DÉRIVE ses onze paliers.

Un pont (``.bz-c-primary``, cf. :mod:`bretzel.theme.bridges`) installe
onze variables à partir d'une seule teinte source. Tout son intérêt tient
à ce que les onze soient **calculées** depuis ``--bz-src``,
``--color-surface`` et ``--color-text`` — des variables que le bloc
``.dark`` du thème redéfinit déjà. C'est ce qui fait basculer la rampe
entière en sombre sans une seule classe ``dark:``.

Ce que cette gate empêche, et pourquoi rien d'autre ne l'attraperait
--------------------------------------------------------------------

**Un littéral de couleur dans une formule.** Écrire
``--bz-border: #cbd5e1`` au lieu du ``color-mix`` marche parfaitement en
clair : la page est juste, les tests passent, la revue ne voit qu'une
couleur plausible. Et le mode sombre est cassé pour ce palier-là, en
silence, parce qu'un littéral ne se réévalue pas. C'est le seul mécanisme
identifié qui peut casser le sombre sans rien faire rougir — d'où une
gate plutôt qu'une relecture.

**Un palier qui manque.** Une entrée retirée de :data:`COLOR_STEPS` ne
lève nulle part : le thème qui l'écrit rend ``var(--bz-bg-hover)``
indéfini, donc la propriété est invalide, donc le composant reste
transparent au survol. Muet, et seulement à l'écran.

**Un pont pour une couleur que personne ne peut demander.** Un pont ne
sert que si un composant peut recevoir ce ``color=``. L'inverse est
permis et voulu — le framework livre douze ponts pour 42 couleurs
acceptées, c'est la décision du 2026-08-30 — mais un pont **hors** de
l'ensemble accepté serait du CSS que rien ne peut atteindre.

Ce que la gate ne dit PAS
--------------------------

Elle ne juge ni les pourcentages ni le contraste obtenu. Les deux se
mesurent au navigateur, pas dans une chaîne, et le contraste est un
chantier à lui seul : mesuré le 2026-08-30, ``--bz-text`` sur
``--bz-bg`` descend à **1.90** pour ``warning`` en clair. Ce n'est pas
une régression des ponts — c'est ce que le dépôt rend déjà aujourd'hui,
puisque ``--bz-text`` reproduit exactement ``text-{bg_color}``. La gate
de contraste viendra quand la décision sur ``--bz-text`` sera prise.

⚠️ Un piège rencontré en écrivant la preuve, et qui vaut pour toute
sonde future : **un palier est un JETON, pas une couleur, tant qu'il
n'est pas peint**. ``getComputedStyle(el).getPropertyValue('--bz-bg')``
rend la chaîne substituée, ``currentColor`` compris, non résolu. Il faut
peindre (``background: var(--bz-bg)``) puis lire ``backgroundColor``.
Lu autrement, ``.bz-c-current`` paraît mort alors qu'il marche.
"""

from __future__ import annotations

import re

from bretzel.theme import Theme
from bretzel.theme.bridges import (
    CURRENT_COLOR_IDENTITY_STEPS,
    CURRENT_COLOR_NAME,
    SOURCE_FOREGROUND_VAR,
    SOURCE_VAR,
    STEP_NAMES,
    bridge_class,
    bridged_color_names,
    generate_color_bridges,
)
from bretzel.theme.slots import COLOR_KEYWORDS

_PALETTE = Theme().get_palette()
_CSS = generate_color_bridges(_PALETTE)

#: Une règle de pont, découpée en (nom de classe, corps).
_RULE = re.compile(r"\.(bz-c-[a-z0-9-]+)\s*\{([^}]*)\}", re.S)

#: Une déclaration ``--nom: valeur;`` dans un corps de règle.
_DECL = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;]+);")

#: Un littéral de couleur — ce qui ne se réévalue JAMAIS en sombre.
#:
#: ``currentColor`` et ``transparent`` sont des MOTS-CLÉS et non des
#: littéraux : le premier se résout contre l'élément (c'est le mécanisme
#: même du pont ``current``), le second n'a pas de mode.
_LITERAL = re.compile(
    r"#[0-9a-fA-F]{3,8}\b"
    r"|\brgba?\s*\("
    r"|\bhsla?\s*\("
    r"|\boklch\s*\("
    r"|\b(?:black|white|red|green|blue|gray|grey|silver|navy|teal|olive"
    r"|maroon|purple|fuchsia|lime|aqua|yellow|orange)\b"
)


def rules() -> dict[str, str]:
    """Les règles de pont du CSS généré — la DÉCOUVERTE de la gate."""
    return {name: body for name, body in _RULE.findall(_CSS)}


#: Une référence ``var(--…)``, à retirer AVANT de chercher un littéral.
#:
#: Sans ça la gate accuse ses propres ponts : la palette livrée contient
#: ``black``, ``white``, ``gray``, ``green``… donc ``var(--color-ui-black)``
#: contient le mot ``black`` sans être pour autant un littéral. Mesuré le
#: 2026-08-30, en ouvrant la couverture aux 43 couleurs : 8 faux positifs
#: d'un coup. Une référence ne peut PAS être un littéral — elle se
#: réévalue par construction — donc la retirer est exact, pas prudent.
_VAR_REF = re.compile(r"var\(\s*--[a-z0-9-]+\s*\)")


def frozen_declarations(css: str) -> list[str]:
    """Les déclarations de pont qui portent un littéral de couleur."""
    frozen: list[str] = []
    for name, body in _RULE.findall(css):
        for var, value in _DECL.findall(body):
            if _LITERAL.search(_VAR_REF.sub("", value)):
                frozen.append(f".{name} {{ {var}: {value.strip()} }}")
    return frozen


def test_the_sweep_is_not_vacuous() -> None:
    """Le plancher lit la découverte de CETTE gate.

    Si le générateur cessait d'émettre, ou si le découpage des règles
    cessait de matcher, les trois assertions ci-dessous porteraient sur
    du vide et passeraient au vert. Mesuré le 2026-08-30 : **43 ponts**
    — 11 sémantiques, ``current``, et les 31 couleurs de la palette
    livrée. Le plancher reste à 12 : c'est le compte qui restera quand
    les 31 défauts partiront (phase 5), donc il ne rougira pas ce
    jour-là pour une raison qui n'en est pas une.
    """
    seen = rules()
    assert len(seen) >= 12, (
        f"Le balayage ne reconnaît plus que {len(seen)} pont(s) : "
        f"{sorted(seen)}. Le générateur ou le découpage des règles a cessé "
        "de rendre ce qu'on croit — la gate ne teste plus rien."
    )


#: Les douze paliers, ÉCRITS ICI et pas importés de ``COLOR_STEPS``.
#:
#: La duplication est le point. Un ``attendu`` construit depuis
#: :data:`STEP_NAMES` rétrécit en même temps que le générateur : mesuré
#: le 2026-08-30, retirer ``--bz-bg-hover`` de ``COLOR_STEPS`` laissait
#: cette gate **verte**, alors que tout thème l'écrivant serait devenu
#: transparent au survol. C'est la pathologie que ferme la memory
#: ``gate_floors_must_read_the_gate_source``, vue depuis l'autre bout :
#: une gate qui recompte depuis sa propre source ne vérifie rien.
#:
#: Ajouter un palier ici est donc un geste DÉLIBÉRÉ, et c'est voulu :
#: les thèmes composants s'appuient sur ces noms, ils ne changent pas
#: par inadvertance.
_EXPECTED_STEPS = frozenset({
    "--bz-bg",
    "--bz-bg-hover",
    "--bz-bg-active",
    "--bz-border",
    "--bz-border-hover",
    "--bz-focus",
    "--bz-focus-soft",
    "--bz-solid",
    "--bz-solid-hover",
    "--bz-on-solid",
    "--bz-text-muted",
    "--bz-text",
})


def test_the_generator_still_declares_every_step() -> None:
    """Le générateur et la liste ci-dessus doivent rester d'accord.

    C'est la moitié qui manquait : sans elle, un palier RETIRÉ du
    générateur passait inaperçu.
    """
    assert set(STEP_NAMES) == _EXPECTED_STEPS, (
        f"Le générateur déclare {sorted(set(STEP_NAMES) ^ _EXPECTED_STEPS)} "
        "de plus ou de moins que le vocabulaire attendu.\n"
        "Un palier retiré ne lève nulle part : le thème qui l'écrit rend "
        "``var(--bz-…)`` indéfini, donc la propriété est invalide, donc le "
        "composant reste transparent. Si l'ajout ou le retrait est voulu, "
        "mets à jour ``_EXPECTED_STEPS`` — et les thèmes qui l'écrivent."
    )


def test_every_bridge_declares_every_step() -> None:
    expected = {SOURCE_VAR, SOURCE_FOREGROUND_VAR, *_EXPECTED_STEPS}
    incomplete: list[str] = []
    for name, body in rules().items():
        declares = {var for var, _v in _DECL.findall(body)}
        if missing := expected - declares:
            incomplete.append(f".{name} : manque {sorted(missing)}")
    assert not incomplete, (
        "Ces ponts n'installent pas tous les paliers :\n  "
        + "\n  ".join(incomplete)
        + "\n\nUn palier absent ne lève nulle part : le thème qui l'écrit "
        "rend ``var(--bz-…)`` indéfini, donc la propriété est invalide, "
        "donc le composant reste transparent. Muet, et seulement à l'écran."
    )


def test_no_bridge_freezes_a_colour() -> None:
    frozen = frozen_declarations(_CSS)
    assert not frozen, (
        "Ces déclarations de pont portent une couleur littérale :\n  "
        + "\n  ".join(frozen)
        + "\n\nUn littéral ne se réévalue pas : le palier reste bloqué sur "
        "sa valeur claire quand ``.dark`` bascule, et RIEN ne le signale — "
        "la page est juste en clair, les tests passent. Dérive depuis "
        "``--bz-src`` / ``--color-surface`` / ``--color-text``, qui sont "
        "déjà redéfinis dans le bloc ``.dark`` du thème."
    )


def test_every_bridged_colour_is_one_a_component_can_ask_for() -> None:
    unknown: list[str] = []
    for color in bridged_color_names(_PALETTE):
        if color in COLOR_KEYWORDS:
            continue
        try:
            _PALETTE.bg_class(color)
        except Exception:  # noqa: BLE001 — le type varie, le fait non
            unknown.append(color)
    assert not unknown, (
        f"Ces couleurs ont un pont mais aucun composant ne peut les "
        f"demander : {unknown}.\nUn pont pour une couleur que "
        "``color=`` refuse est du CSS inatteignable. L'inverse — une "
        "couleur acceptée SANS pont — est voulu : le framework en livre "
        "douze pour 42 acceptées (décision du 2026-08-30)."
    )


def test_the_current_bridge_is_the_one_exception() -> None:
    """``current`` est le seul pont dont la source n'est pas un token.

    Il vaut d'être épinglé : c'est le défaut de ``ui.icon``,
    ``ui.spinner`` et ``ui.breadcrumb``, donc la valeur de ``color=`` la
    plus répandue du framework. S'il disparaissait, la migration
    buterait sur le composant le plus utilisé du catalogue.
    """
    body = rules()[bridge_class(CURRENT_COLOR_NAME)]
    assert "currentColor" in body, (
        "``.bz-c-current`` ne part plus de ``currentColor`` — il ne suit "
        "donc plus la couleur héritée, et ``ui.icon`` perd son défaut."
    )


def test_current_hands_its_text_step_straight_through() -> None:
    """``--bz-text`` de ``current`` est la source TELLE QUELLE.

    Le pont pose ``--bz-src: currentColor``, puis fait passer cette source
    dans les onze formules comme n'importe quelle couleur nommée. Pour
    ``--bz-text``, la formule est un ``color-mix`` à 55 % vers le texte de
    page : une icône par défaut ne prenait donc PAS la couleur de son
    parent, elle en prenait 55 % tirés vers le noir de la page.

    **Pourquoi personne ne l'avait vu.** Sur un fond neutre, la couleur
    héritée EST celle du texte de page — le mélange devient l'identité et
    le défaut est parfaitement invisible. Il n'apparaît que sur un APLAT,
    là où le parent impose une autre couleur. Mesuré le 2026-09-09 sur un
    bouton primaire d'``examples/kanban`` : libellé ``rgb(19 22 22)``,
    icône ``rgb(17 22 31)``.

    C'est aussi ce que la docstring d'``icon/theme.py`` promet depuis
    toujours — « the icon inherits its parent's text colour ». Une
    affirmation de doc n'est pas une gate ; celle-ci en est une.
    """
    # ⚠️ Le palier est nommé ICI, pas lu depuis la constante que la gate
    # surveille. Boucler sur ``CURRENT_COLOR_IDENTITY_STEPS`` rendait ce
    # test VACANT : vider la constante le laissait vert, puisqu'il n'avait
    # plus rien à parcourir. Mesuré par mutation le 2026-09-09 — c'est
    # exactement le mode d'échec que ``gates.md`` nomme, un plancher qui
    # recompte depuis sa propre source.
    assert "--bz-text" in CURRENT_COLOR_IDENTITY_STEPS, (
        "``--bz-text`` a quitté ``CURRENT_COLOR_IDENTITY_STEPS`` : le pont "
        "`current` va de nouveau dériver la couleur du texte."
    )
    body = rules()[bridge_class(CURRENT_COLOR_NAME)]
    valeur = dict(_DECL.findall(body)).get("--bz-text", "").strip()
    assert valeur == f"var({SOURCE_VAR})", (
        f"--bz-text du pont `current` vaut {valeur!r} au lieu de la source "
        f"telle quelle. Une icône posée sur un aplat sortira d'une autre "
        f"couleur que le mot qu'elle accompagne — et ça ne se verra sur "
        f"AUCUN fond neutre."
    )


def test_a_named_colour_keeps_its_calibrated_mix() -> None:
    """Le versant LICITE de l'exception ci-dessus, et il coûte cher.

    Le ``--bz-text`` d'une couleur nommée est un mélange calibré pour
    tenir une barre de contraste contre le fond de page (cf.
    ``readable_step_pct``). Rendre TOUS les paliers identitaires
    « réparerait » ``current`` en donnant du texte accentué illisible sur
    les onze autres ponts.
    """
    body = rules()[bridge_class("primary")]
    valeur = dict(_DECL.findall(body)).get("--bz-text", "").strip()
    assert "color-mix" in valeur, (
        f"--bz-text de `primary` ne mélange plus : {valeur!r}. "
        f"L'exception de `current` a débordé sur les couleurs nommées."
    )
    assert f"var({SOURCE_VAR})" in valeur, (
        f"--bz-text de `primary` ne part plus de la source : {valeur!r}"
    )


def test_the_detector_still_bites() -> None:
    """Mutation, dans les deux sens.

    Le versant qui MORD confirme qu'on attrape la faute réelle ; le
    versant qui ÉPARGNE est celui qui trouve les faux positifs.
    """
    # ── il mord ────────────────────────────────────────────────────
    fabricated = ".bz-c-faux {\n  --bz-border: #cbd5e1;\n}"
    assert frozen_declarations(fabricated), "un hex doit être vu"
    assert frozen_declarations(".bz-c-faux {\n  --bz-bg: rgb(1 2 3);\n}")
    assert frozen_declarations(".bz-c-faux {\n  --bz-solid: white;\n}")

    # ── il épargne ─────────────────────────────────────────────────
    # les deux mots-clés du vocabulaire, qui ne sont PAS des littéraux
    assert not frozen_declarations(".bz-c-faux {\n  --bz-src: currentColor;\n}")
    assert not frozen_declarations(
        ".bz-c-faux {\n  --bz-focus: color-mix(in oklab, var(--bz-src) 40%, transparent);\n}"
    )
    # une formule normale, celle que le générateur écrit vraiment
    assert not frozen_declarations(
        ".bz-c-faux {\n  --bz-bg: color-mix(in oklab, var(--bz-src) 10%, var(--color-surface));\n}"
    )
    # un nom de couleur EN SOUS-CHAÎNE d'un token n'est pas un littéral
    assert not frozen_declarations(
        ".bz-c-faux {\n  --bz-solid: var(--color-ui-blueberry);\n}"
    ), "``blue`` dans ``blueberry`` ne doit pas matcher"
