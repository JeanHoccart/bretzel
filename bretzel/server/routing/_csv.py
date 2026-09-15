"""L'écriture CSV, partagée par les deux chemins de téléchargement.

Extrait de ``routing/datatable.py`` le 2026-09-02, quand ``@download``
est devenu le second consommateur. Le contenu ne change pas : ce sont
les deux corrections que l'implémentation V1 avait déjà identifiées et
qu'on rate facilement — le BOM UTF-8, et le fait de laisser
``csv.writer`` décider quand citer.

Pourquoi c'est ici et pas dans ``core`` : ça ne sert qu'à répondre à une
requête. Le monter plus bas dans le DAG ferait porter au socle un
format de sortie HTTP.
"""

from __future__ import annotations

import csv
import io
from typing import Any

#: Excel sous Windows lit un CSV UTF-8 sans BOM dans la page de codes du
#: système, donc chaque nom accentué arrive en mojibake. Un caractère le
#: répare, et c'est le bug le plus rapporté de tous les exports CSV
#: jamais écrits.
BOM = "﻿"


def to_csv(rows: Any, columns: list[list[str]], read: Any) -> str:
    """Texte RFC 4180 : une ligne d'en-têtes, puis un enregistrement par ligne.

    ``csv.writer`` porte les règles de citation (citer seulement quand la
    valeur contient un délimiteur, un guillemet ou un saut de ligne ;
    doubler un guillemet interne) — c'est très exactement là que les
    exports écrits à la main se trompent.

    ``read`` est la fonction de lecture d'une cellule. Elle est passée
    plutôt qu'importée pour que ce module ne dépende pas des composants :
    ``datatable`` lui donne son ``read_cell`` (qui gère objets, dicts et
    attributs), ``@download`` lui donne un accès de dict.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow([label or key for key, label in columns])
    for row in rows:
        writer.writerow([
            "" if (value := read(row, key)) is None else str(value)
            for key, _label in columns
        ])
    return BOM + buffer.getvalue()


def columns_of(rows: Any) -> list[list[str]]:
    """Les colonnes DÉDUITES d'une liste de dicts — clé et libellé égaux.

    ⚠️ L'ordre vient du PREMIER enregistrement, et l'union des clés n'est
    pas prise : deux dicts aux clés différentes donneraient un tableau à
    trous dont personne ne saurait dire quelle ligne manque quoi. Une
    forme hétérogène demande des colonnes explicites — c'est ce que
    ``ui.datatable`` fournit de son côté.
    """
    premier = next(iter(rows), None)
    if premier is None:
        return []
    if not isinstance(premier, dict):
        raise TypeError(
            "@download : une liste a été rendue mais son premier élément "
            f"n'est pas un dict ({type(premier).__name__}). Rends une "
            "liste de dicts pour un CSV, ou construis toi-même la "
            "``Response`` si la forme est autre."
        )
    return [[str(cle), str(cle)] for cle in premier]
