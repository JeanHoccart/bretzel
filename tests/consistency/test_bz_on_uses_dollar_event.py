"""Une expression ``bz-on:`` utilise ``$event``, jamais ``event`` nu.

Le runtime compile chaque expression en une fonction dont la signature est
``($scope, $el, $refs, $event, $value, $dispatch, $nextTick)``
(``02_directives.js:52-53``). Il n'y a **pas** de paramètre ``event``. Un
``event`` nu traverse donc le ``with($scope)`` — le trap ``has`` du scope
rend ``false`` sur une clé inconnue (``03_scope.js:48-51``) — et se résout
sur le **``window.event`` global, déprécié**.

Ça *marche* sur les navigateurs actuels. C'est justement le problème : rien
ne signale l'erreur, et le jour où la résolution change (mode strict, autre
moteur, `window.event` retiré) le handler casse sans que personne n'ait
touché au composant.

⚠️ **La subtilité, et la raison d'être de cette gate** : ``event`` est
LÉGITIME ailleurs, à quelques lignes de distance. Un ``hx-trigger="click[…]"``
est évalué par **HTMX**, qui expose bien ``event``. Dans ``table.py`` les
deux constantes sont voisines — ``_ROW_CLICK_GUARD`` (hx-trigger, ``event``
correct) et ``_ROW_CLICK_KEYDOWN`` (bz-on, ``$event`` requis) — et la
contamination s'est faite sur dix lignes. Une gate qui bannirait ``event``
partout casserait le premier ; celle-ci ne regarde que ce qui atterrit
réellement dans un attribut ``bz-on:``.

Elle travaille donc sur le HTML **rendu**, pas sur la source : c'est le seul
endroit où l'on sait dans quel moteur une expression finit.
"""

from __future__ import annotations

import re

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from tests.consistency._discovery import (
    public_component_classes,
    rendered_html_of,
)

# ``event`` en position d'identifiant : pas précédé de ``$`` ni d'un point
# (``$event`` est correct, ``el.event`` serait une propriété).
_BARE_EVENT = re.compile(r"(?<![\w$.])event\b")

_BZ_ON = re.compile(r'bz-on:[\w:\-]+="([^"]*)"')

# Construction minimale par composant : on ne cherche pas à exercer toutes
# les branches, seulement à faire émettre les handlers du chemin nominal.
def item_clicked(key: object) -> None:
    """Handler de test au niveau MODULE.

    Un lambda est refusé par le framework (`HandlerError`) : il résout ses
    handlers via ``sys.modules`` à la requête, ce qu'un lambda ne survit
    pas. Sans handler valide, `Table` n'émet pas son `bz-on:keydown`.
    """


def _table_kwargs() -> dict[str, object]:
    # ``Column`` est un dataclass, PAS un dict — un dict lève dans
    # ``render()`` et le composant se faisait alors skipper en silence :
    # la gate paraissait verte tout en ne regardant jamais Table, le seul
    # composant fautif. Attrapé par mutation-test.
    from bretzel.components.data.table import Column

    return {
        "columns": [Column(key="a", label="A")],
        "rows": [{"a": 1, "id": 1}],
        "row_key": "id",
        "on_item_click": item_clicked,
    }


#: Le seul composant qui demande des kwargs À LUI pour émettre le
#: handler qu'on juge. Tout le reste passe par le bâtisseur PARTAGÉ.
_OWN_KWARGS = ("Table",)

#: Ce que le bâtisseur partagé ne construit pas, avec sa raison. Mesuré
#: le 2026-08-19 en remplaçant l'``except`` par un enregistrement.
#:
#: ⚠️ Avant ce jour, l'``except`` en avalait **six** : Datatable,
#: ToggleButton (qui exigent un contexte que ``CONSTRUCT`` sait fabriquer)
#: et Iframe / Image / MetaTag / Title (qui exigent un mot obligatoire,
#: que ``_BARE_ARGS`` connaît depuis le matin même). La gate paraissait
#: balayer 97 composants ; elle en jugeait 91.
_CANNOT_BUILD: dict[str, str] = {
    "Link": "binding de slot A.2 — déclaré `_needs_context` dans CONSTRUCT",
}


def _rendered_html(cls: type) -> str | None:
    """Le HTML du composant — ``None`` s'il est DÉCLARÉ non constructible.

    Le bâtisseur partagé (``rendered_html_of``) sait déjà quel composant
    exige un mot obligatoire et lequel exige un contexte. Reconstruire
    ce savoir ici, c'est ce qui faisait sortir six composants du balayage
    en silence.
    """
    if cls.__name__ in _OWN_KWARGS:
        with render_isolated():
            return serialize(cls(**_table_kwargs()).render())
    return rendered_html_of(cls)


@pytest.mark.parametrize(
    "cls", public_component_classes(), ids=lambda c: c.__name__
)
def test_bz_on_expression_uses_dollar_event(cls: type) -> None:
    html = _rendered_html(cls)
    if html is None:
        pytest.skip(f"{cls.__name__} ne se construit pas sans contexte")
    offenders = [
        expr for expr in _BZ_ON.findall(html) if _BARE_EVENT.search(expr)
    ]
    assert not offenders, (
        f"{cls.__name__} : expression `bz-on:` utilisant `event` nu — "
        f"{offenders}.\n"
        f"  Le runtime ne fournit que `$event` ; un `event` nu se résout "
        f"sur le `window.event` global déprécié, donc ça marche par "
        f"accident.\n"
        f"  ⚠️ `event` reste correct dans un `hx-trigger=\"click[…]\"`, "
        f"évalué par HTMX — c'est de là que vient la confusion. Ici, "
        f"remplace par `$event`."
    )


def test_the_gate_sees_enough() -> None:
    """Garde-fou : si presque tout est skippé, la gate ne garde rien."""
    rendered = [
        cls for cls in public_component_classes()
        if _rendered_html(cls) is not None
    ]
    assert len(rendered) >= 90, (
        f"Seuls {len(rendered)} composants se rendent (96 le 2026-08-19) — "
        f"la gate est devenue quasi aveugle. Le bâtisseur partagé a cessé "
        f"de construire ce qu'il construisait."
    )


def test_the_abstentions_are_declared() -> None:
    """Ce que le balayage ne bâtit pas est NOMMÉ, pas compté.

    Un plafond chiffré dirait « pas plus d'un » ; une table dit LEQUEL.
    La différence compte le jour où un composant sort du balayage
    pendant qu'un autre y rentre : le compte ne bouge pas, la table si.
    """
    missing = {
        cls.__name__ for cls in public_component_classes()
        if _rendered_html(cls) is None
    }
    surprise = sorted(missing - set(_CANNOT_BUILD))
    assert not surprise, (
        f"{surprise} ne se construi(sen)t plus, et personne ne l'avait "
        f"déclaré : ils sortent du balayage EN SILENCE, et la gate affirme "
        f"« aucun handler au dialecte mort » sans les avoir regardés."
    )
    stale = sorted(set(_CANNOT_BUILD) - missing)
    assert not stale, (
        f"{stale} se construi(sen)t de nouveau — retire l'entrée de "
        f"`_CANNOT_BUILD`."
    )


def test_the_gate_would_catch_a_bare_event() -> None:
    """La détection elle-même, sur les deux formes voisines.

    Épingle la distinction qui a produit le bug : la même sous-chaîne est
    fautive dans un `bz-on:` et correcte dans un `hx-trigger`.
    """
    assert _BARE_EVENT.search("event.target === $el")
    assert _BARE_EVENT.search("(event.key === 'Enter')")
    assert not _BARE_EVENT.search("$event.target === $el")
    assert not _BARE_EVENT.search("$event.preventDefault()")
