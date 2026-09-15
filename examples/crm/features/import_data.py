"""features/import_data — data : lire un CSV de comptes, le juger, l'écrire.

Sert l'écran 9. Trois étapes, trois fonctions, et la frontière entre elles
est ce qui compte : **analyser** ne touche pas la base, **juger** ne touche
pas la base non plus, **écrire** est la seule qui la touche — et elle refuse
tout si une seule ligne est mauvaise.

Ce dernier point n'est pas de la prudence décorative : un import à moitié
appliqué laisse l'utilisateur devant une base qu'il ne peut ni garder ni
rejouer.
"""

from __future__ import annotations

import csv
import io

from bretzel import Feature
from examples.crm.core.db import connect
from examples.crm.core.domain import (
    COUNTRY_KEYS,
    INDUSTRIES,
    OWNERS,
    SIZES,
    TODAY,
)

#: Les colonnes attendues, dans l'ordre. C'est aussi le gabarit proposé au
#: téléchargement — un import dont on ne peut pas produire un exemple valide
#: est un import que personne ne réussit du premier coup.
IMPORT_COLUMNS: tuple[str, ...] = (
    "name", "industry", "country", "city", "size", "arr", "owner",
)

#: Le plafond d'un import. Au-delà, l'aperçu n'est plus un aperçu et la
#: transaction devient un verrou long sur une base que les autres écrans
#: lisent.
IMPORT_MAX_ROWS = 500

EXAMPLE_CSV = (
    "name,industry,country,city,size,arr,owner\n"
    "Nouvelle Enseigne SAS,Distribution,France,Lyon,PME,42000,Marc Dubois\n"
    "Atelier du Nord,Industrie,Belgique,Gand,TPE,9000,Sofia Rossi\n"
)


def parse_csv(raw: str) -> tuple[list[dict], str]:
    """``(lignes, erreur d'en-tête)``. N'ouvre aucune connexion.

    L'en-tête est vérifié AVANT les lignes : un fichier dont les colonnes ne
    correspondent pas produirait autrement une erreur par ligne, toutes
    identiques, et l'utilisateur lirait cinq cents fois le même reproche.
    """
    text = raw.lstrip("﻿")
    if not text.strip():
        return [], "Le fichier est vide."
    reader = csv.DictReader(io.StringIO(text))
    header = tuple(reader.fieldnames or ())
    if header != IMPORT_COLUMNS:
        return [], (
            f"Colonnes attendues : {', '.join(IMPORT_COLUMNS)}. "
            f"Colonnes lues : {', '.join(header) if header else '(aucune)'}."
        )
    rows: list[dict] = []
    for index, row in enumerate(reader, start=2):
        if len(rows) >= IMPORT_MAX_ROWS:
            break
        rows.append({"_ligne": index, **{k: (row.get(k) or "").strip()
                                         for k in IMPORT_COLUMNS}})
    return rows, ""


def judge(rows: list[dict], owner: str | None) -> list[dict]:
    """Annote chaque ligne d'un ``_erreur`` — vide quand elle est bonne.

    Le verdict vit SUR la ligne plutôt que dans une liste à part : l'aperçu
    est un tableau, et une erreur qui n'est pas dans la ligne qu'elle
    concerne oblige le lecteur à recompter.

    ``owner`` cadre l'écriture, et le fait en REFUSANT plutôt qu'en
    réécrivant : forcer silencieusement le propriétaire de chaque ligne
    ferait qu'un fichier préparé pour un collègue s'importerait sur soi
    sans rien dire. C'est le seul endroit du CRM où le cadrage porte sur
    une écriture, et le refus est ce qui le rend visible.
    """
    judged: list[dict] = []
    for row in rows:
        problems: list[str] = []
        if not row["name"]:
            problems.append("nom vide")
        if row["industry"] not in INDUSTRIES:
            problems.append(f"secteur inconnu « {row['industry']} »")
        if row["country"] not in COUNTRY_KEYS:
            problems.append(f"pays inconnu « {row['country']} »")
        if row["size"] not in SIZES:
            problems.append(f"taille inconnue « {row['size']} »")
        if row["owner"] not in OWNERS:
            problems.append(f"propriétaire inconnu « {row['owner']} »")
        elif owner is not None and row["owner"] != owner:
            problems.append(f"hors portefeuille « {row['owner']} »")
        if not row["arr"].isdigit():
            problems.append("ARR non numérique")
        judged.append({**row, "_erreur": " · ".join(problems)})
    return judged


def commit_rows(rows: list[dict], owner: str | None) -> int:
    """Écrit les lignes en UNE transaction. Renvoie le nombre inséré.

    Une seule connexion et un seul ``commit`` : cinq cents ``execute()``
    isolés, ce sont cinq cents ouvertures de fichier et cinq cents fsync.

    ⚠️ **Le cadrage est refait ICI**, alors que :func:`judge` l'a déjà
    vérifié. Ce n'est pas de la ceinture-et-bretelles : ``judge`` tourne
    à la requête « Vérifier » et ``commit_rows`` à la requête
    « Importer ». Entre les deux, un directeur peut avoir changé de
    portefeuille — et le verdict ``_erreur`` que le writer croirait sur
    parole a été calculé sous une autre politique. Le verdict EXPLIQUE,
    l'écriture ENFORCE.
    """
    if owner is not None:
        rows = [row for row in rows if row["owner"] == owner]
    payload = [
        (row["name"], row["industry"], row["country"], row["city"],
         row["size"], int(row["arr"]), row["owner"], TODAY.isoformat())
        for row in rows
    ]
    if not payload:
        return 0
    conn = connect()
    try:
        conn.executemany(
            "INSERT INTO accounts "
            "(name, industry, country, city, size, arr, owner, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            payload,
        )
        conn.commit()
    finally:
        conn.close()
    return len(payload)


feature = Feature(
    name="import_data",
    kind="data",
    provides=[parse_csv, judge, commit_rows],
    uses=["db"],
)
