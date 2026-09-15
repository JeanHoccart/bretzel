"""Chaque scope de dismiss nomme SON panneau.

``anchored_dismiss_init`` câble Escape + clic-dehors sur un overlay ancré.
Son contrat, énoncé dans sa propre docstring : *« every overlay names its
panel ``bz-ref="bzpanel"`` »*. Le helper passe ``() => $refs.bzpanel`` comme
élément « aussi dedans », parce qu'un panneau téléporté sous ``<body>`` sort
du sous-arbre de la root et compterait sinon comme « dehors ».

Pourquoi ce contrat ne peut PAS rester implicite
-------------------------------------------------
``$refs`` se résout par la **chaîne de prototypes** des scopes
(``03_scope.js``). Un scope de dismiss qui ne définit pas SON ``bzpanel``
n'obtient donc pas ``undefined`` — il obtient **le panneau d'un ancêtre**.
Le dismiss reste câblé, ne lève pas, et vise simplement la mauvaise cible :
échec silencieux au sens strict.

Le bug qui a motivé cette gate (reproduit au navigateur, 2026-07-29)
---------------------------------------------------------------------
Les dropdowns mois/année de ``Calendar`` appellent
``anchored_dismiss_init`` sans nommer leur panneau. Dans un
``date_picker``, ils vivent à l'intérieur du panneau du picker — donc leur
``clickOutside`` traitait **le panneau du picker** comme « dedans ».
Mesuré : un clic sur l'en-tête du calendrier ne fermait pas le dropdown
mois, alors qu'un clic sur ``<body>``, sur un ``<h1>`` ou la touche Escape
le fermaient. Le dismiss marchait, il visait le mauvais élément.

⚠️ Le comptage est par SCOPE, pas par fichier. ``Calendar`` émettait déjà un
``bz-ref="bzpanel"`` (celui de son conteneur) tout en ayant **deux** scopes
de dismiss non couverts — une gate en simple présence l'aurait déclaré
conforme.
"""

from __future__ import annotations

import pytest

from tests.consistency._discovery import public_component_classes, rendered_html_of

# La signature que ``anchored_dismiss_init`` laisse dans le HTML rendu. On
# compte les scopes de dismiss par ce marqueur plutôt que par une lecture
# du source : c'est le RENDU qui compte, y compris pour un composant qui
# appellerait le helper depuis un sous-builder.
_DISMISS_MARKER = "$bz.helpers.clickOutside("
_PANEL_REF = 'bz-ref="bzpanel"'

_CLASSES = public_component_classes()


def _render(cls: type) -> str | None:
    return rendered_html_of(cls)


_RENDERED: dict[str, str] = {}
for _cls in _CLASSES:
    _html = _render(_cls)
    if _html is not None:
        _RENDERED[_cls.__name__] = _html

_DISMISSERS = sorted(
    name for name, html in _RENDERED.items() if _DISMISS_MARKER in html
)


def test_the_gate_has_a_population() -> None:
    """Plancher de non-vacuité.

    Sans lui, un changement de la signature émise par
    ``anchored_dismiss_init`` viderait ``_DISMISSERS`` et la gate passerait
    verte sur zéro composant — le mode d'échec exact d'une gate de ce
    dépôt restée verte des mois en cherchant un préfixe mort.
    """
    assert len(_DISMISSERS) >= 4, (
        f"seuls {len(_DISMISSERS)} composants rendus émettent le marqueur "
        f"de dismiss ({_DISMISSERS}) — 8 modules appellent pourtant "
        f"`anchored_dismiss_init`. Soit le marqueur a changé, soit la "
        f"construction a régressé : la gate ne vérifie plus rien."
    )


@pytest.mark.parametrize("name", _DISMISSERS)
def test_every_dismiss_scope_names_its_own_panel(name: str) -> None:
    html = _RENDERED[name]
    dismiss_scopes = html.count(_DISMISS_MARKER)
    panels = html.count(_PANEL_REF)

    assert panels >= dismiss_scopes, (
        f"{name} : {dismiss_scopes} scope(s) de dismiss pour seulement "
        f"{panels} `bz-ref=\"bzpanel\"`.\n"
        f"  `$refs` se résout par la chaîne de prototypes : un scope de "
        f"dismiss sans SON panneau n'obtient pas `undefined`, il obtient "
        f"le panneau d'un ANCÊTRE. Le clic-dehors vise alors la mauvaise "
        f"cible et l'overlay ne se ferme pas — sans erreur, sans warning.\n"
        f"  Ajoute `\"bz-ref\": \"bzpanel\"` aux attrs du panneau de chaque "
        f"scope qui appelle `anchored_dismiss_init`."
    )
