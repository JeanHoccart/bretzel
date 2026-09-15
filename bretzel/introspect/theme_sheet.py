"""La fiche de THÈME d'un composant — ce que `describe X --theme` rend.

Pourquoi elle existe
--------------------
La fiche normale nomme les clés qu'on a le droit d'écrire dans
``Theme(components={…})``, et s'arrête juste avant la question qu'on se
pose vraiment. Mesuré le 2026-09-10 en écrivant le preset du kanban :
**une dizaine de ``theme.py`` ouverts à la main** pendant que ``describe``
tournait.

Les deux lignes qu'il rendait pour ``button`` et pour ``select`` étaient
IDENTIQUES alors que les deux formes sont incompatibles — ``button``
attend ``"md": "h-10 px-4"``, ``select`` attend ``"md": {"trigger": …}``
— et ``input`` ne montrait nulle part ``icon_pad_left``, qui vit DANS un
palier sans être un slot.

Les trois manques, et ce que chacun coûte
------------------------------------------
1. **la FORME** (chaîne ou dict de sous-clés). Indevinable, et c'est elle
   qui décide si l'override est lu : un dict écrit là où le thème livre
   une chaîne fait perdre TOUS les jetons du palier — le composant rend
   nu, en 200, sans erreur ; l'inverse lève un ``AttributeError`` au
   rendu qui ne nomme ni le thème, ni le composant, ni la clé ;
2. **la valeur courante** — sans elle on ne sait pas ce qu'on remplace ;
3. **les sous-clés d'un palier**, absentes des deux listes.

Ce qu'elle refuse de faire
---------------------------
Vomir la table. ``select`` a 18 slots, ``datatable`` bien plus, et 70 855
caractères de classes Tailwind sur le catalogue : une sortie qui les
imprime toutes ne se lit plus, donc ne répond plus. La fiche montre donc
UN palier en entier — celui que le composant prend par DÉFAUT, lu dans
sa signature — et se contente de nommer les autres.

C'est lu dans ``cls.THEME``, donc ça ne peut pas dériver : même argument
que ``bretzel describe``.
"""

from __future__ import annotations

from typing import Any

#: Le paramètre qui choisit dans un groupe, quand il y en a un. Un groupe
#: absent de cette table n'a pas de « palier par défaut » — ``slots`` n'est
#: pas un choix, c'est la liste des morceaux du composant.
GROUP_TO_PARAM = {
    "sizes": "size",
    "variants": "variant",
    "shapes": "shape",
    "tones": "tone",
}

#: Au-delà, on nomme sans montrer. Une ligne de plus ne coûte rien ; dix
#: écrans de classes Tailwind coûtent la lecture entière.
_MAX_NAMED = 24


def _shape_of(value: Any) -> str:
    return "dict" if isinstance(value, dict) else "str"


def _value_lines(value: Any) -> list[str]:
    """Ce que vaut UN palier, montré en entier.

    Un dict s'ouvre sur ses sous-clés — c'est précisément ce qu'aucune
    liste ne montrait, et ``icon_pad_left`` en est l'exemple : il vit dans
    un palier de ``sizes`` sans être un slot.
    """
    if not isinstance(value, dict):
        return [f"      {value}"]
    # Largeur CALCULÉE, pas fixe : `select` porte un `header_btn_primary`
    # de 18 caractères, et une colonne de 16 collait le nom à sa valeur.
    width = max(len(str(sub)) for sub in value) + 2
    return [
        f"      {sub!s:<{width}}{sub_value}" for sub, sub_value in value.items()
    ]


def _default_key(cls: Any, group: str, table: dict) -> str | None:
    """Le palier que le composant prend sans qu'on lui demande.

    Lu sur la PROP RÉACTIVE et pas dans la signature : ``__init__`` rend
    ``None`` pour ``size=`` sur tout le catalogue — c'est le descripteur
    qui porte le vrai défaut (``'md'``). Chercher dans la signature
    donnait donc « aucun palier par défaut » partout, et la fiche taisait
    exactement ce que l'item réclamait : les sous-clés d'un palier.

    Vérifié présent dans la table avant d'être rendu : un défaut qui ne
    désigne aucune clé ne doit pas faire imprimer une valeur au hasard.
    """
    param = GROUP_TO_PARAM.get(group)
    if param is None:
        return None
    descriptor = getattr(cls, "__reactive_props__", {}).get(param)
    default = getattr(descriptor, "default", None) if descriptor else None
    if default is None:
        import inspect

        try:
            parameter = inspect.signature(cls.__init__).parameters.get(param)
        except (TypeError, ValueError):
            return None
        default = None if parameter is None else parameter.default
    key = str(default) if default is not None else None
    return key if key in {str(k) for k in table} else None


def theme_sheet(ui_name: str) -> str:
    """La fiche de thème de ``ui_name``, en texte.

    Lève :class:`KeyError` si le nom n'est pas un composant, avec la même
    phrase que ``describe`` — un utilisateur qui se trompe de nom doit
    lire la même chose des deux côtés.
    """
    from bretzel.components import ui as ui_module

    cls = getattr(ui_module, ui_name, None)
    if not isinstance(cls, type):
        raise KeyError(f"`ui.{ui_name}` n'existe pas.")
    theme = getattr(cls, "THEME", None)
    theme_key = getattr(cls, "THEME_KEY", "") or ""
    if not isinstance(theme, dict) or not theme_key:
        raise KeyError(f"`ui.{ui_name}` ne porte pas de thème.")

    out = [
        f"Thème de ui.{ui_name} — Theme(components={{{theme_key!r}: {{…}}}})",
        "",
    ]
    for group, table in theme.items():
        if not isinstance(table, dict):
            out += [f"  {group}", f"    (valeur unique) {table}", ""]
            continue

        keys = [str(k) for k in table]
        forms = {_shape_of(v) for v in table.values()}
        forme = forms.pop() if len(forms) == 1 else "mixte"
        out.append(f"  {group}  —  {len(keys)} clés, forme « {forme} »")

        shown = _default_key(cls, group, table)
        if shown is not None:
            param = GROUP_TO_PARAM[group]
            out.append(f"    {shown}  (le défaut de {param}=) :")
            out += _value_lines(table[shown])
            autres = [k for k in keys if k != shown]
            if autres:
                out.append(f"    les autres : {', '.join(autres)}")
        elif len(keys) <= _MAX_NAMED:
            out.append(f"    {', '.join(keys)}")
        else:
            out.append(f"    {', '.join(keys[:_MAX_NAMED])}, … (+{len(keys) - _MAX_NAMED})")
        out.append("")

    out += [
        "⚠️ La FORME décide si ta surcharge est LUE.",
        "   Un dict là où le thème livre une chaîne fait perdre tous les",
        "   jetons du palier — le composant rend nu, en 200, sans erreur.",
        "   Une chaîne là où il livre un dict lève au rendu.",
        "   Une clé NEUVE, elle, est la façon supportée d'étendre le thème.",
    ]
    return "\n".join(out)
