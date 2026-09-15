"""L'échelle de taille, et la lecture d'une table ``sizes``.

Pourquoi ce module existe
--------------------------

L'échelle ``xs|sm|md|lg|xl`` est la grammaire des contrôles : ``bretzel describe``
l'annonce comme un **enum fermé** sur Button, Input, Select, Badge, Avatar,
Icon, Spinner, Progress… Elle était pourtant recopiée **cinq fois dans
``tests/`` et zéro fois dans ``bretzel/``** (mesuré le 2026-08-16) —
``test_size_enum_is_complete``, ``test_size_reaches_slots``,
``test_sizes_are_distinct``, ``test_playground_demos_the_api``,
``probes/bench_switch``. Un enum déclaré fermé qui n'existe nulle part dans
le code n'est pas fermé : c'est une convention, et une convention ne peut
rien refuser.

⚠️ Ce que l'échelle n'est PAS
------------------------------

Ce n'est pas « toutes les valeurs qu'un composant accepte ». Trois familles
vont au-delà, et c'est **voulu** :

- ``Text`` et ``Heading`` portent l'échelle **typographique** (``xs`` à
  ``8xl``, mesuré) — un titre n'a pas la taille d'un bouton, et
  ``bretzel describe`` le dit : « ne pas confondre » ;
- ``Avatar`` étend à ``2xl`` (visuel portrait) ;
- ``Icon`` de même.

:data:`SIZE_SCALE` est donc **le socle commun**, et il sert deux rôles : le
palier minimal qu'une table de contrôle doit couvrir, et — c'est le second
usage, moins évident — le **marqueur** qui dit si une table est indexée par
taille ou par slot.

Les deux imbrications de ``sizes``, et pourquoi il faut les départager
-----------------------------------------------------------------------

Sur les 44 tables ``sizes`` du catalogue, **33 sont imbriquées**, et deux
imbrications OPPOSÉES coexistent ::

    Checkbox    sizes = {"sm": {"root": …, "label": …}}     ← clés = TAILLES
    DatePicker  sizes = {"input_field": {"sm": …, "md": …}} ← clés = SLOTS

Structurellement indiscernables : dans les deux cas un dict de dicts. Le
seul signal disponible est le **contenu** des clés, d'où
:func:`size_vocabulary`, qui regarde à quel étage l'échelle apparaît.

Confondre les deux n'est pas théorique : une première version de la règle
de lint ``valeur-hors-table`` a signalé ``ui.date_picker(size="sm")``, qui
est parfaitement correct — le composant résout ses tailles lui-même dans
son ``render``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

#: Les cinq paliers de contrôle. **Source unique** — tout ce qui a besoin
#: de savoir « est-ce un nom de taille ? » se compose là-dessus.
SIZE_SCALE: Final[tuple[str, ...]] = ("xs", "sm", "md", "lg", "xl")

_SCALE: Final[frozenset[str]] = frozenset(SIZE_SCALE)


def is_size_keyed(table: Mapping[str, Any]) -> bool:
    """La table est-elle indexée par TAILLE (et non par slot) ?

    Le test est l'intersection avec :data:`SIZE_SCALE`, et non « les
    valeurs sont-elles des chaînes » : ``Checkbox`` est indexé par taille
    ET imbriqué, ``Button`` est indexé par taille et plat. La forme des
    valeurs ne dit donc rien de l'indexation.
    """
    return bool(_SCALE & set(table))


def size_vocabulary(theme: Mapping[str, Any] | None) -> frozenset[str]:
    """Les valeurs que ``size=`` peut prendre pour ce thème de composant.

    Absorbe les deux imbrications :

    - table indexée par taille → ses propres clés, **entières** (donc
      ``2xl``..``8xl`` inclus pour ``Text`` / ``Heading`` / ``Avatar``) ;
    - table indexée par slot → l'union des clés du second étage qui
      portent l'échelle.

    Rend un ensemble **vide** quand il n'y a pas de table du tout — le
    composant consomme alors ``size=`` autrement (``radio_group``), et un
    consommateur ne doit surtout pas conclure « aucune valeur n'est
    valide ». Le vide veut dire « je ne sais pas », pas « rien ».
    """
    table = (theme or {}).get("sizes")
    if not isinstance(table, Mapping) or not table:
        return frozenset()
    if is_size_keyed(table):
        return frozenset(table)
    found: set[str] = set()
    for row in table.values():
        if isinstance(row, Mapping) and is_size_keyed(row):
            found |= _SCALE & set(row)
    return frozenset(found)


#: La taille d'``ui.icon`` qui va avec un libellé d'une taille donnée :
#: **le cran juste au-dessus**, sur l'échelle d'``Icon``.
#:
#: Pourquoi un cran, et pas la même taille
#: ---------------------------------------
#:
#: ``<iconify-icon>`` se dimensionne en ``1em`` — sa taille EST sa
#: ``font-size``. À taille égale, un glyphe paraît donc plus petit que le
#: texte : il n'a pas de hampe, pas de jambage, rien qui accroche la
#: ligne de base. Le thème d'``Icon`` le dit déjà pour son défaut
#: (``"md": "text-lg",  # slightly bigger than text for readability``) —
#: cette table ne fait que généraliser cette intention aux libellés qui
#: ne font PAS 16 px.
#:
#: Le défaut d'``Icon`` était calibré contre un corps de page (18/16 =
#: 1,125). Les items ont des libellés de 12 à 14 px, et l'utiliser tel
#: quel y donnait jusqu'à 1,50 (``breadcrumb_item``, mesuré le
#: 2026-08-18).
#:
#: L'échelle d'``Icon`` est trouée (``sm`` = 14 px puis ``md`` = 18 px,
#: rien à 16) : « le cran au-dessus » se lit donc sur SA table, pas sur
#: celle de Tailwind. Cinq des huit composants-items la respectaient
#: déjà avant que la règle soit écrite.
#:
#: ⚠️ Une taille d'icône qui n'est PAS un cran au-dessus doit être
#: DÉCLARÉE avec sa raison — ``bottom_bar_item`` monte à 24 px parce que
#: c'est une cible tactile, pas un ornement de ligne de texte. Gaté par
#: ``tests/consistency/test_icon_follows_its_label.py``.
ICON_SIZE_ABOVE: Final[Mapping[str, str]] = {
    "text-[10px]": "xs",   # 10 px → 12
    "text-xs": "sm",       # 12 px → 14
    "text-sm": "md",       # 14 px → 18
    "text-base": "md",     # 16 px → 18
    "text-lg": "lg",       # 18 px → 24
    "text-xl": "lg",       # 20 px → 24
}


def icon_size_for(label_class: str) -> str | None:
    """La taille d'icône qui va avec ce libellé — ``None`` si sa classe
    de texte n'est pas dans :data:`ICON_SIZE_ABOVE`.

    ``label_class`` est la chaîne de classes composée du libellé ; on y
    cherche le token ``text-*`` de TAILLE. Les autres ``text-*`` (une
    couleur, ``text-left``) ne sont pas dans la table, donc ignorés — ce
    qui est exactement pourquoi la table liste les tailles au lieu de
    matcher un préfixe.
    """
    for token in label_class.split():
        size = ICON_SIZE_ABOVE.get(token)
        if size is not None:
            return size
    return None


__all__ = (
    "ICON_SIZE_ABOVE",
    "SIZE_SCALE",
    "icon_size_for",
    "is_size_keyed",
    "size_vocabulary",
)
