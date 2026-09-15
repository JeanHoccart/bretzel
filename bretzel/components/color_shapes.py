"""Ce que les thèmes composants savent et que le scanner Tailwind ignore.

Deux collectes, une seule raison d'être : une classe qui n'apparaît
littéralement dans aucun fichier source n'atteint jamais le ``style.css``
compilé. Un gabarit couleur n'est comblé qu'au render ; une classe
graduée (``md:gap-6``) n'est préfixée qu'au render. Dans les deux cas le
compilateur de prod ne peut pas deviner, et dans les deux cas le bug ne
se voit **qu'en production**.

Pourquoi ce module existe
-------------------------

⚠️ **La moitié COULEUR de ce module n'existe plus depuis la phase 3 du
chantier des jetons (2026-08-30).** Aucun thème n'écrit plus de trou :
ils lisent des PALIERS (``ring-(--bz-focus)``), qui sont des classes
complètes que le compilateur voit. ``dynamic_color_shapes()`` a été
supprimée avec eux, et son dernier reste — le ramasseur ``_walk``, resté
seul à référencer un ``SHAPE_TOKEN_RE`` déjà parti — l'a suivie le
2026-09-07. Le nom du fichier est donc plus large que son contenu : il
ne reste que la moitié GRADUÉE (``dynamic_responsive_classes``), qui,
elle, sert toujours.

Ce qu'il faisait, et pourquoi il a existé : les thèmes écrivaient leurs
classes avec un trou — la moitié d'un nom de classe, comblée au render
contre la couleur résolue du composant (cf.
``resolve_slot``, déposé depuis). Conséquence : la classe finale
n'apparaissait **dans aucun fichier source**, donc le compilateur ne
pouvait pas la générer, donc il fallait en calculer la CLÔTURE — chaque
forme × chaque couleur. 3 791 classes, 80 % de la feuille compilée.

En dev ça ne se voit pas — ``@tailwindcss/browser`` scanne le DOM vivant,
donc il voit les classes déjà résolues. En prod le binaire Tailwind ne
scanne que les sources : sans aide, il ne génère aucune de ces règles et
tout l'état interactif du design system (anneaux de focus, teintes de
hover, états cochés / sélectionnés) sort du CSS compilé.

L'aide, c'est la directive ``@source inline(...)`` produite par
:func:`bretzel.theme.tailwind.generate_safelist_comment`. Elle était
maintenue **à la main** — 5 gabarits + 7 opacités — pendant que les thèmes
en utilisaient 57. D'où 49 formes absentes du ``style.css`` de prod.

Ce module supprime la classe de bug : la safelist est désormais *dérivée*
des thèmes eux-mêmes, donc elle ne peut plus diverger d'eux. La gate
``tests/consistency/test_no_colour_class_is_assembled_by_hand.py`` couvre le
risque résiduel (une forme construite en code de render plutôt que dans un
dict ``THEME``, que l'introspection ne verrait pas).

Sens de la dépendance : ``theme`` est dans le socle et n'a pas le droit
d'importer ``components`` (contrat import-linter *base-independent-of-app*).
C'est donc ``components`` qui expose ses gabarits, et l'assemblage au
démarrage (``server.lifecycle``) qui les passe au générateur.
"""

from __future__ import annotations

from typing import Any

from bretzel.components.base.component import Component


def _component_classes() -> set[type]:
    """Toute sous-classe vivante de :class:`Component`, récursivement.

    Volontairement plus large que le namespace ``ui`` : des composants
    internes (leaves d'un container, sous-parties de calendrier…) portent
    leur propre ``THEME`` sans être exposés.

    Portée réelle : les classes **déjà importées** au moment de l'appel.
    ``components/__init__`` importe le catalogue du framework en bloc,
    donc la couverture y est complète (la gate le vérifie). Un composant
    utilisateur défini après le démarrage — dans un corps de fonction,
    dans un module importé paresseusement au premier render — arrive
    trop tard : ses couleurs n'atterriront pas dans la safelist.

    Pas de registre global (anti-règle 2) : on lit les classes vivantes
    au moment de l'appel, après que les imports aient eu lieu.
    """
    found: set[type] = set()
    stack: list[type] = list(Component.__subclasses__())
    while stack:
        cls = stack.pop()
        if cls in found:
            continue
        found.add(cls)
        stack.extend(cls.__subclasses__())
    return found


def dynamic_responsive_classes() -> tuple[str, ...]:
    """Les classes qu'un prop gradué peut ressortir préfixées d'un breakpoint.

    Retourne les tokens NUS (``"gap-6"``, ``"flex-row"``, ``"hidden"``) ;
    c'est :func:`~bretzel.theme.tailwind.generate_safelist_comment` qui
    les croise avec ``BREAKPOINTS``. Le partage du travail suit celui des
    couleurs : ``components`` déclare, ``theme`` clôture — le socle n'a
    pas le droit d'importer les composants (contrat import-linter
    *base-independent-of-app*).

    La source est ``RESPONSIVE_THEME_KEYS``, une déclaration et non de
    l'introspection : le préfixage se décide dans ``render()``, que la
    safelist ne peut pas exécuter. Une table déclarée mais absente du
    ``THEME`` est ignorée en silence — la gate
    ``test_responsive_classes_are_safelisted`` refuse ce cas, ici ce
    n'est pas le bon endroit pour lever (on tourne au démarrage du
    serveur).

    Les classes assemblées à partir d'un SCALAIRE (``grid-cols-N``,
    ``basis-1/N``) ne passent pas par là : leur domaine n'est pas
    énumérable depuis un thème, il est clôturé à la main dans
    ``_LAYOUT_CLASSES``.
    """
    tokens: set[str] = set()
    for cls in _component_classes():
        keys = cls.__dict__.get("RESPONSIVE_THEME_KEYS") or ()
        if not keys:
            continue
        # Remontée explicite de la MRO plutôt qu'un ``cls.THEME`` : la
        # déclaration peut vivre sur une sous-classe qui HÉRITE son thème
        # (VStack / HStack héritent celui de Flex), donc lire le seul
        # ``__dict__`` de la classe raterait la table. Et l'accès par
        # attribut est refusé ici par ``test_theme_reads_are_resolved``,
        # qui garde un contrat de RENDER (passer par
        # ``_resolved_theme()`` pour qu'un ``Theme(components=…)`` de
        # l'app s'applique) — inapplicable à une introspection de classe,
        # sans instance ni contexte.
        theme: dict[str, Any] = next(
            (
                found
                for base in cls.__mro__
                if (found := base.__dict__.get("THEME"))
            ),
            {},
        )
        for key in keys:
            table = theme.get(key)
            if not isinstance(table, dict):
                continue
            for value in table.values():
                if isinstance(value, str):
                    tokens.update(value.split())
    return tuple(sorted(tokens))


__all__ = ["dynamic_responsive_classes"]
