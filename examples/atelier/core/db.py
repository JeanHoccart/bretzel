"""core/db — infra : la base de l'atelier, son schéma et ses portes.

Feature ``kind="infra"`` : elle ne rend rien et ne porte aucun ``State``.
Elle POSSÈDE le fichier SQLite et expose ``query`` / ``scalar`` /
``execute``. Les features ``*_data`` requêtent par-dessus ; les pages ne
la touchent jamais. Même découpage que ``examples/crm``, et pour la même
raison.

Pourquoi une base et pas une lecture directe
---------------------------------------------
Les transcripts font **516 Mo sur 70 sessions**. Les relire à chaque
affichage rendrait tout écran inutilisable, et surtout : la question
qu'on pose n'est pas « comment s'est passée cette tâche » mais « est-ce
que ça progresse ». Comparer demande de tout avoir sous la main, donc
indexé.

C'est aussi ce qui fait de cette app un instrument utile au framework :
une ``ui.datatable`` en mode callable sur dizaines de milliers de lignes,
qui est le tier que la datatable existe pour servir.

⚠️ Sync, pas ``aiosqlite`` — pour la raison mesurée dans
``examples/crm/core/db.py`` : une zone ``@refreshable`` ne peut pas être
``async``, et dans une app réelle toute lecture vit dans une zone. Deux
couches de données seraient exactement le « se dépanner » que ces
instruments interdisent.

Pas d'état global mutable (anti-règle 2) : ``connect()`` ouvre une
connexion neuve par appel.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from bretzel import Feature
from examples.atelier.core.epoque import JALON

DB_PATH = Path(__file__).with_name("atelier.db")

#: Bumpé quand le schéma change : ``init_db`` reconstruit alors les tables
#: plutôt que de migrer. Une base d'OBSERVATION se rebâtit depuis sa
#: source en quelques minutes — écrire des migrations pour elle serait du
#: travail qui ne mesure rien.
SCHEMA_VERSION = 4

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    cle    TEXT PRIMARY KEY,
    valeur TEXT NOT NULL
);

-- Une session = un fichier de transcript = une fenêtre de travail.
CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT PRIMARY KEY,
    fichier    TEXT NOT NULL,
    debut      TEXT,
    fin        TEXT,
    minutes    REAL    NOT NULL DEFAULT 0,
    taches     INTEGER NOT NULL DEFAULT 0,
    -- Les tours de conversation qui n'ont DÉCLENCHÉ aucun outil : « ok »,
    -- « vas-y », une question à laquelle on répond de mémoire. Ce ne sont
    -- pas des tâches, et les compter comme telles diluait toutes les
    -- moyennes — 345 sur 1 857 avant qu'on les sépare. On les compte ici
    -- plutôt que de les jeter : savoir combien d'échanges il a fallu
    -- pour un travail donné est une information, simplement pas la même.
    echanges   INTEGER NOT NULL DEFAULT 0,
    appels     INTEGER NOT NULL DEFAULT 0,
    erreurs    INTEGER NOT NULL DEFAULT 0,
    jetons_in  INTEGER NOT NULL DEFAULT 0,
    jetons_out INTEGER NOT NULL DEFAULT 0
);

-- Une tâche = un message de l'utilisateur jusqu'à la réponse finale.
-- C'est l'unité de jugement : c'est à cette échelle qu'on demande « est-ce
-- que ça a été fait du premier coup ».
CREATE TABLE IF NOT EXISTS taches (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    ordre      INTEGER NOT NULL,
    debut      TEXT,
    -- ⚠️ Les minutes de TRAVAIL : du premier appel d'outil au dernier.
    -- PAS le temps d'horloge entre la demande et la réponse, qui incluait
    -- le temps où l'utilisateur est parti — mesuré jusqu'à 3 223 minutes,
    -- soit 53 heures, sur une tâche qui a duré un quart d'heure. Une
    -- colonne qui ment de deux ordres de grandeur ne se lit plus, elle
    -- s'ignore.
    minutes    REAL    NOT NULL DEFAULT 0,
    demande    TEXT    NOT NULL DEFAULT '',
    appels     INTEGER NOT NULL DEFAULT 0,
    erreurs    INTEGER NOT NULL DEFAULT 0,
    cycles     INTEGER NOT NULL DEFAULT 0,
    frise      TEXT    NOT NULL DEFAULT '',
    verdict    TEXT    NOT NULL DEFAULT '',
    jetons     INTEGER NOT NULL DEFAULT 0,
    -- Sur QUOI la tâche a travaillé. C'est ce qui sépare « construire le
    -- socle » de « écrire une app », et sans quoi les deux se jugent au
    -- même mètre — ce qui n'a de sens pour aucun des deux.
    perimetre  TEXT    NOT NULL DEFAULT 'autre',
    -- A-t-on LU avant d'écrire ? Le temps 1 de la règle des quatre temps.
    lu_avant   INTEGER NOT NULL DEFAULT 0,
    -- A-t-on demandé la SURFACE (`describe`) avant d'écrire ? C'est la
    -- question « est-ce que je consulte, ou est-ce que j'invente ».
    surface    INTEGER NOT NULL DEFAULT 0,
    -- A-t-on fait juger le CONTRAT d'app (`check --deep`) ? C'est la
    -- question « `Feature()` est-il un atout ou du cosmétique ».
    contrat    INTEGER NOT NULL DEFAULT 0
);

-- Un appel d'outil, avec sa phase. C'est la table de détail : elle porte
-- la frise d'une tâche et le classement par outil.
CREATE TABLE IF NOT EXISTS appels (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    tache_id INTEGER NOT NULL,
    ordre    INTEGER NOT NULL,
    horaire  TEXT,
    outil    TEXT NOT NULL,
    phase    TEXT NOT NULL,
    commande TEXT NOT NULL DEFAULT '',
    erreur   INTEGER NOT NULL DEFAULT 0,
    detail   TEXT NOT NULL DEFAULT '',
    cible    TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_taches_session ON taches(session_id);
CREATE INDEX IF NOT EXISTS idx_taches_verdict ON taches(verdict);
CREATE INDEX IF NOT EXISTS idx_taches_perim   ON taches(perimetre);
CREATE INDEX IF NOT EXISTS idx_appels_tache   ON appels(tache_id, ordre);
CREATE INDEX IF NOT EXISTS idx_appels_outil   ON appels(outil);
CREATE INDEX IF NOT EXISTS idx_appels_phase   ON appels(phase);
"""


#: ⚠️ CE QUE LES ÉCRANS LISENT. Les tables portent tout ce qui a été
#: aspiré ; les vues s'arrêtent au jalon de :mod:`core.epoque`. Une vue
#: et non une clause recopiée : les features de données font vingt-six
#: lectures, donc vingt-six occasions d'oublier la coupure — et une
#: statistique qui inclut en silence des tâches d'avant les instruments
#: est exactement le chiffre faux qu'on cherche à éviter.
#:
#: L'aspiration, elle, écrit dans les TABLES : rien n'est perdu, et
#: reculer le jalon d'un jour se fait sans ré-aspirer 516 Mo.
VUES = f"""
DROP VIEW IF EXISTS taches_epoque;
DROP VIEW IF EXISTS appels_epoque;
DROP VIEW IF EXISTS sessions_epoque;

CREATE VIEW taches_epoque AS
    SELECT * FROM taches WHERE debut >= '{JALON}';

CREATE VIEW appels_epoque AS
    SELECT a.* FROM appels a
    JOIN taches t ON t.id = a.tache_id
    WHERE t.debut >= '{JALON}';

CREATE VIEW sessions_epoque AS
    SELECT * FROM sessions
    WHERE id IN (SELECT session_id FROM taches_epoque);
"""

#: Repartir de zéro, sans toucher au FICHIER. Windows verrouille un
#: fichier ouvert : tant qu'une fenêtre de l'atelier est affichée, un
#: ``unlink`` lève ``WinError 32`` et l'aspiration échoue. Un job qui
#: exige qu'on ferme l'app qu'il alimente ne sert à rien — mesuré le
#: 2026-09-12, deux serveurs ouverts, aucune ré-aspiration possible.
#: Les index tombent avec leur table.
VIDER = """
DROP VIEW IF EXISTS taches_epoque;
DROP VIEW IF EXISTS appels_epoque;
DROP VIEW IF EXISTS sessions_epoque;
DROP TABLE IF EXISTS appels;
DROP TABLE IF EXISTS taches;
DROP TABLE IF EXISTS sessions;
DROP TABLE IF EXISTS meta;
"""


def connect() -> sqlite3.Connection:
    """Une connexion neuve (rows en accès dict-like)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def query(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    """Les lignes d'un SELECT."""
    with connect() as conn:
        return conn.execute(sql, params).fetchall()


def scalar(sql: str, params: tuple = ()) -> Any:
    """La première colonne de la première ligne — ``None`` si rien."""
    with connect() as conn:
        row = conn.execute(sql, params).fetchone()
    return None if row is None else row[0]


def execute(sql: str, params: tuple = ()) -> None:
    """Une écriture."""
    with connect() as conn:
        conn.execute(sql, params)


def init_db(*, reset: bool = False) -> None:
    """Crée le schéma. ``reset`` repart de tables vides.

    La version du schéma est relue à chaque démarrage : une base écrite
    par une version antérieure est jetée plutôt que migrée, parce qu'elle
    se rebâtit depuis les transcripts.
    """
    with connect() as conn:
        if reset:
            conn.executescript(VIDER)
        conn.executescript(SCHEMA)
        conn.executescript(VUES)
        courante = conn.execute(
            "SELECT valeur FROM meta WHERE cle = 'schema_version'"
        ).fetchone()
        if courante is not None and int(courante[0]) != SCHEMA_VERSION:
            conn.executescript(VIDER)
            conn.executescript(SCHEMA)
            conn.executescript(VUES)
        conn.execute(
            "INSERT OR REPLACE INTO meta (cle, valeur) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )


def is_seeded() -> bool:
    """Y a-t-il quelque chose à regarder ?

    L'app doit pouvoir démarrer sur une base VIDE et le dire, plutôt que
    de rendre des écrans creux : le transcript est une source externe,
    elle peut ne pas avoir encore été aspirée.
    """
    return bool(DB_PATH.exists() and (scalar("SELECT COUNT(*) FROM taches") or 0))


feature = Feature(
    name="db",
    kind="infra",
    uses=["epoque"],
    provides=[connect, query, scalar, execute, init_db, is_seeded],
)
