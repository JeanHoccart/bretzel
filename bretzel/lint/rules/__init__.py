"""Les règles — chacune pure, chacune énumérable.

Une règle a la signature ``check(module) -> list[Finding]``. Elle ne
connaît ni corpus, ni plancher, ni code de sortie : elle constate sur UN
module et rend des :class:`~bretzel.lint.report.Finding`.

**Le registre est une liste, pas un système de plugins.** Le charter exclut
un plugin system avant stabilisation du core, et un jeu de règles
non-énumérable empêcherait ``check`` de dire ce qu'il sait vérifier — ce
qui est précisément la question qu'on pose à un outil de ce genre.
"""

from __future__ import annotations

from collections.abc import Callable

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding
from bretzel.lint.rules import (
    handlers,
    injection,
    kwargs,
    lifespan,
    loop_state,
    nested_link,
    nested_page,
    partial_sizes,
    provenance,
    shape,
    shared_counter,
    sizes,
    specificity,
    tailwind,
    theme,
    transport,
    variant,
    zone_deps,
)

Rule = Callable[[Module], list[Finding]]

#: Les règles statiques — AST seul, **rien n'est exécuté**. C'est ce qui
#: permet de les lancer sur le code d'un tiers sans conséquence.
#:
#: L'ordre est celui de la **discrétion de l'échec**, du plus silencieux au
#: plus bruyant, parce que c'est l'ordre dans lequel on veut les lire :
#: un état construit dans un corps
#: `async def` marche en mémoire et LÈVE le jour où `redis_url` est
#: posé — muet aussi, mais d'un silence à retardement : ce n'est pas le
#: code qui se tait, c'est le dev qui ne montre pas la panne ; une
#: classe Tailwind assemblée ne
#: casse qu'en prod avec un HTML identique ; un nom de thème inconnu ne
#: change RIEN nulle part (même pas en prod : il n'y a pas d'attribut à
#: voir, pas de classe à chercher, le rendu est celui du thème livré) ; une
#: valeur hors table retire une classe et laisse le composant à l'écran,
#: nu — et une surcharge de thème qui garde le nom en changeant la FORME
#: fait exactement ça, mesuré : le palier perd tous ses jetons et le
#: composant rend à la taille de son contenu (son autre sens, lui, lève
#: au rendu, ce qui le range juste après) ; un cast sur une valeur d'état ne retire rien non plus et laisse le
#: composant afficher le MAUVAIS état, que seul un rechargement corrige ;
#: une classe qui double une prop n'en retire aucune — les DEUX sont dans
#: le HTML, et c'est l'ordre de la feuille Tailwind qui tranche, donc même
#: la relecture des classes ne voit rien ; des tailles mélangées ne
#: retirent RIEN non plus — la page est juste, deux
#: champs voisins n'ont simplement pas la même hauteur, et il faut
#: regarder l'écran pour le voir ; un kwarg inconnu part en attribut
#: inerte ; un `hx-` à la main fait une
#: requête refusée ; un `ui.html` non littéral est un choix à rendre
#: visible ; un lambda lève au rendu.
STATIC: dict[str, Rule] = {
    loop_state.RULE: loop_state.check,
    shared_counter.RULE: shared_counter.check,
    tailwind.RULE: tailwind.check,
    theme.RULE: theme.check,
    variant.RULE: variant.check,
    shape.RULE: shape.check,
    nested_page.RULE: nested_page.check,
    lifespan.RULE: lifespan.check,
    provenance.RULE: provenance.check,
    specificity.RULE: specificity.check,
    partial_sizes.RULE: partial_sizes.check,
    sizes.RULE: sizes.check,
    zone_deps.RULE: zone_deps.check,
    nested_link.RULE: nested_link.check,
    kwargs.RULE: kwargs.check,
    transport.RULE: transport.check,
    injection.RULE: injection.check,
    handlers.RULE: handlers.check,
}

__all__ = ("STATIC", "Rule")
