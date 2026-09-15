"""Responsive prop values — one ``{breakpoint: value}`` dialect, one parser.

A *graded* layout prop (how many columns, how much gap, which axis) can
take a different value per screen width ::

    ui.grid(cols={"base": 1, "md": 3})
    ui.flex(direction={"base": "col", "md": "row"}, gap={"base": "sm", "md": "lg"})

The dict is read « ``base`` applies everywhere, each breakpoint overrides
from that width up » — i.e. Tailwind's mobile-first ladder, spelled in
Python. :func:`responsive_classes` is the ONLY thing that turns it into
classes ; a component never prefixes breakpoints by hand.

**Which props may take a dict.** Only the *graded* ones — those with more
than two useful steps. Anything binary (shown / hidden, sidebar / topbar)
is a **structural** choice and belongs to ``if Screen().is_mobile:`` in
the dev's own layout, not to a prop. That boundary is why Bretzel has no
``visible_from=`` : it would be a second way to say what ``Screen``
already says. Cf. ``.claude/work/todo.md`` § *A-ter*.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.theme.tokens import BREAKPOINTS

# Keys meaning « no prefix — applies at every width ». ``base`` is the
# canonical spelling ; the rest are tolerated aliases (``xs`` reads as
# "smallest", and Tailwind has no ``xs:`` variant to collide with).
BASE_KEYS = frozenset({"base", "xs", "", "default"})

# Tailwind's default breakpoint ladder — RÉ-EXPORTÉE depuis
# ``theme.tokens``, qui la possède. Une clé hors de cet ensemble
# émettrait un préfixe que Tailwind ne génère jamais (un no-op
# silencieux) : on refuse plutôt que d'expédier des classes mortes.
# La safelist doit clôturer sur le même ensemble, d'où la source unique
# dans la couche theme — cf. le commentaire là-bas.

_ALLOWED = "base, " + ", ".join(BREAKPOINTS)


def responsive_classes(value: Any, resolve: Callable[[Any], str]) -> str:
    """Resolve ``value`` to a class string, honouring a breakpoint dict.

    ``resolve`` maps ONE scalar value to its class string (a theme-table
    lookup, an f-string, whatever the component uses) and stays unaware of
    breakpoints. A scalar passes straight through it ; a dict resolves each
    entry and prefixes every token of the result — a multi-class entry like
    ``"gap-x-4 gap-y-2"`` becomes ``"md:gap-x-4 md:gap-y-2"``, not the
    broken ``"md:gap-x-4 gap-y-2"``.

    Entries resolving to an empty string are dropped. Class ORDER carries
    no meaning here : Tailwind emits its media queries in ladder order in
    the stylesheet, so dict insertion order cannot change the outcome.
    """
    if not isinstance(value, dict):
        return resolve(value) or ""

    parts: list[str] = []
    for breakpoint_, raw in value.items():
        if breakpoint_ not in BASE_KEYS and breakpoint_ not in BREAKPOINTS:
            raise ComponentUsageError(
                f"unknown breakpoint {breakpoint_!r} in a responsive value — "
                f"it would emit a prefix Tailwind never generates. "
                f"Allowed: {_ALLOWED}."
            )
        resolved = resolve(raw)
        if not resolved:
            continue
        if breakpoint_ in BASE_KEYS:
            parts.append(resolved)
        else:
            parts.append(" ".join(f"{breakpoint_}:{tok}" for tok in resolved.split()))
    return " ".join(parts)


def looks_like_a_breakpoint_dict(value: Any) -> bool:
    """Ce dict est-il une échelle de paliers, ou de la DONNÉE ?

    La question se pose parce que le socle refuse désormais un dict de
    paliers sur un prop non gradué (:meth:`Component._reject_stray_breakpoints`),
    et qu'il doit le faire sans jamais se tromper sur un prop qui prend
    légitimement un dict — les lignes d'un tableau, une carte de
    valeurs, un attribut composé.

    D'où le discriminant : **toutes** les clés sont des paliers connus.
    ``{"base": …, "md": …}`` ne peut pas être autre chose ;
    ``{"id": 1, "nom": "x"}`` n'est jamais confondu. Un dict vide n'est
    pas une échelle non plus — il ne dit rien, et le refuser
    n'apprendrait rien à personne.

    ⚠️ Le versant coûteux est le LICITE : une gate qui rougit sur du
    code juste se fait débrancher. C'est pourquoi le test n'est pas
    « c'est un dict » mais « c'est un dict de paliers ».
    """
    return (
        isinstance(value, dict)
        and bool(value)
        and all(k in BASE_KEYS or k in BREAKPOINTS for k in value)
    )


def reject_stray_breakpoints(
    owner: str, prop: str, value: Any, responsive_props: frozenset[str]
) -> None:
    """Un dict de paliers sur un prop qui n'est pas gradué : on le DIT.

    Sans ce refus, le dict continue jusqu'à un lookup de table de thème
    et meurt trois frames plus bas sur ::

        TypeError: cannot use 'dict' as a dict key (unhashable type: 'dict')

    — qui ne nomme ni le composant, ni le prop, ni le fait qu'un dict de
    paliers n'a pas sa place là. Mesuré le 2026-09-04 : **80 couples
    ``Classe.prop``** mouraient comme ça, recensés un par un dans
    ``tests/consistency/_not_graded.txt`` parce qu'on ne savait pas les
    réparer d'un coup.

    Le framework avait pourtant DÉJÀ la bonne forme d'erreur —
    ``ui.card(size=…)`` répond « ce composant ne lit pas ``size`` »,
    clair et actionnable. Ce qui manquait n'était pas le message, c'était
    qu'il soit ATTEINT : l'ancien garde ``reject_responsive`` existait
    mais n'était câblé que sur ``flex`` et ``carousel``, deux composants
    sur une centaine, une ligne à la main par prop. Appelé depuis le
    socle avec la déclaration ``RESPONSIVE_PROPS``, il devient universel
    sans une ligne par prop, et sans rien à oublier sur un composant
    neuf.

    ⚠️ Le discriminant est :func:`looks_like_a_breakpoint_dict`, pas
    « c'est un dict » : plusieurs props prennent légitimement un dict de
    DONNÉES, et un garde qui les refuserait serait débranché dans la
    semaine.
    """
    if prop in responsive_props or not looks_like_a_breakpoint_dict(value):
        return
    gradues = sorted(responsive_props)
    ce_qui_marche = (
        "Sur ce composant, "
        + ", ".join(f"``{p}``" for p in gradues)
        + (" le prend." if len(gradues) == 1 else " le prennent.")
        if gradues
        else "Aucun prop de ce composant n'est gradué."
    )
    raise ComponentUsageError(
        f"{owner}({prop}=…) : ``{prop}`` ne prend pas de dict de paliers. "
        f"{ce_qui_marche} Un choix qui n'est pas une GRADUATION est "
        f"structurel — branchez-le dans votre mise en page avec "
        f"``if Screen().is_mobile:``, qui dit la même chose sans une "
        f"seconde manière de le dire."
    )
