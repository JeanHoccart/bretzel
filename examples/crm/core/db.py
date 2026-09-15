"""core/db — infra : le fichier SQLite, son schéma, ses index et son seed.

Feature ``kind="infra"`` : elle ne rend rien et ne porte aucun ``State``
Bretzel — elle POSSÈDE une ressource externe (le fichier SQLite) et expose
les portes d'accès (``query`` / ``scalar`` en lecture, ``execute`` en
écriture). Les features ``*_data`` requêtent par-dessus ; les pages ne la
touchent jamais.

Cet exemple utilise ``sqlite3`` et des fonctions synchrones. Ce choix
n'est pas une limite de ``@refreshable`` : le framework prend aussi en
charge les corps de zone asynchrones.

**Volumes.** ~262 000 lignes semées une fois (voir ``seed.py``), pas 20 : en
dessous, la datatable en mode callable n'a aucune raison d'exister et aucune
mise en page n'est contrainte.

**Les comptes utilisateurs vivent dans la même base**, table ``users``. Le
framework ne modélise pas d'utilisateur au-delà de son identifiant — il ne
sait que « telle requête appartient à X », dans un cookie signé — donc le
profil, le rôle et le mot de passe sont à l'app. ``owner`` y est la clé de
jointure avec la donnée : c'est le nom qu'on lit dans ``accounts.owner``.

Pas d'état global mutable (anti-règle 2) : ``connect()`` ouvre une connexion
neuve par appel.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from bretzel import Feature

DB_PATH = Path(__file__).with_name("crm.db")

#: Bumpé quand le schéma ou le seed change — ``init_db`` reconstruit alors le
#: fichier. Sans ce marqueur, semer 262 000 lignes à chaque démarrage rendrait
#: ``reload=True`` inutilisable.
SEED_VERSION = 7


def connect() -> sqlite3.Connection:
    """Une connexion neuve au fichier SQLite (rows en accès dict-like)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def owner_scope(owner: str | None, clause: str) -> tuple[str, tuple]:
    """``(fragment SQL, paramètres)`` pour cadrer une lecture — ou rien.

    Onze lectures du CRM portaient les deux mêmes lignes, dont la seconde
    était **identique au caractère près** partout. Ce qui varie — le
    qualifieur de colonne, le ``AND`` ou le ``WHERE`` — reste écrit EN
    CLAIR au call-site, exprès : le cadrage doit se voir dans la requête
    qu'on relit, pas se cacher derrière un nom de fonction.

    ``owner=None`` veut dire **tous les propriétaires**, et c'est un
    privilège (``access.visible_owner``). ``""`` ne matche personne.
    """
    return ("", ()) if owner is None else (clause, (owner,))


def query(sql: str, params: tuple = ()) -> list[dict]:
    """Exécute un SELECT et renvoie une liste de dicts — la porte de LECTURE."""
    conn = connect()
    try:
        return [dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


def scalar(sql: str, params: tuple = ()) -> Any:
    """La première colonne de la première ligne — pour les ``COUNT(*)``.

    Une porte à part plutôt qu'un ``query(...)[0]["count"]`` recopié partout :
    le mode callable de la datatable réclame un total à CHAQUE rendu, et c'est
    l'endroit où un ``dict`` construit pour un entier se verrait.
    """
    conn = connect()
    try:
        row = conn.execute(sql, params).fetchone()
        return row[0] if row is not None else None
    finally:
        conn.close()


#: Les verbes SQL pour lesquels ``lastrowid`` veut dire quelque chose.
_ROWID_VERBS = frozenset({"INSERT", "REPLACE"})


def execute(sql: str, params: tuple = ()) -> int:
    """Exécute un INSERT / UPDATE / DELETE, commit, et renvoie le
    ``lastrowid`` (INSERT) ou le nombre de lignes touchées — la porte
    d'ÉCRITURE.

    ⚠️ **Le verbe est lu explicitement**, et c'est un correctif. Le code
    disait ``lastrowid if lastrowid is not None else rowcount``, ce qui
    paraît raisonnable et ne l'est pas : après un ``UPDATE``, sqlite3
    laisse ``lastrowid`` à ``0`` sur une connexion neuve — jamais
    ``None``. Donc un ``UPDATE`` rendait toujours ``0``, et la première
    fonction à s'en servir pour dire « refusé » (``update_contact``)
    refusait aussi ce qu'elle venait d'écrire. Le bug était latent depuis
    la tranche 1 : personne ne lisait le retour d'un ``UPDATE``.

    Note réactivité : une écriture DB ne touche AUCUN ``State`` typé, donc le
    moteur de re-render ne la « voit » pas. Les repos bumpent après coup un
    jeton de révision ``AppState`` — c'est LUI que les zones
    ``@refreshable(deps=[…Rev])`` observent.
    """
    verb = sql.lstrip().split(None, 1)[0].upper()
    conn = connect()
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid if verb in _ROWID_VERBS else cur.rowcount
    finally:
        conn.close()


_SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value INTEGER);

CREATE TABLE users (
    id            INTEGER PRIMARY KEY,
    login         TEXT    NOT NULL UNIQUE,
    display_name  TEXT    NOT NULL,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL,
    owner         TEXT    NOT NULL
);

CREATE TABLE accounts (
    id         INTEGER PRIMARY KEY,
    name       TEXT    NOT NULL,
    industry   TEXT    NOT NULL,
    country    TEXT    NOT NULL,
    city       TEXT    NOT NULL,
    size       TEXT    NOT NULL,
    arr        INTEGER NOT NULL,
    owner      TEXT    NOT NULL,
    created_at TEXT    NOT NULL
);

CREATE TABLE contacts (
    id         INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    first_name TEXT    NOT NULL,
    last_name  TEXT    NOT NULL,
    email      TEXT    NOT NULL,
    phone      TEXT    NOT NULL,
    title      TEXT    NOT NULL,
    status     TEXT    NOT NULL,
    -- Dénormalisé depuis ``accounts.owner``, comme ``activities`` porte
    -- déjà son ``account_id``. ⚠️ Ce n'est PAS du confort : cadrer les
    -- contacts par ``a.owner`` force la jointure dans le COUNT ET dans
    -- le SELECT, et SQLite se met alors à conduire depuis ``accounts``
    -- puis à trier les survivants. Mesuré sur la page 1 de l'écran 3 :
    -- **4,8 ms → 100,5 ms**. Avec la colonne ici et son index :
    -- **0,08 ms**. Le semis la remplit depuis le compte, donc les deux
    -- ne peuvent pas diverger.
    owner      TEXT    NOT NULL,
    created_at TEXT    NOT NULL
);

CREATE TABLE deals (
    id         INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    name       TEXT    NOT NULL,
    stage      TEXT    NOT NULL,
    amount     INTEGER NOT NULL,
    owner      TEXT    NOT NULL,
    close_date TEXT    NOT NULL,
    position   INTEGER NOT NULL,
    created_at TEXT    NOT NULL
);

CREATE TABLE activities (
    id         INTEGER PRIMARY KEY,
    contact_id INTEGER NOT NULL REFERENCES contacts(id),
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    kind       TEXT    NOT NULL,
    subject    TEXT    NOT NULL,
    at         TEXT    NOT NULL,
    owner      TEXT    NOT NULL
);

CREATE TABLE notes (
    id         INTEGER PRIMARY KEY,
    contact_id INTEGER NOT NULL REFERENCES contacts(id),
    body       TEXT    NOT NULL,
    author     TEXT    NOT NULL,
    at         TEXT    NOT NULL
);
"""

#: Les index que les écrans réclament réellement, mesurés avec
#: ``EXPLAIN QUERY PLAN`` plutôt que devinés.
#:
#: **Un index par colonne triable de la datatable des comptes.** Sans eux,
#: ``ORDER BY city`` planifie ``SCAN accounts`` + ``USE TEMP B-TREE`` : 50 000
#: lignes triées pour en rendre 25, mesuré à 12-16 ms par clic de tri contre
#: 0,3 ms avec. La liste doit rester égale à ``SORTABLE`` dans
#: ``accounts_data`` — une colonne triable sans index est un scan silencieux.
#:
#: **``activities(at, kind, owner)``** sert l'écran 6, qui lit toujours par
#: fenêtre de dates : l'index par contact ne peut pas servir un ``BETWEEN``
#: sur ``at``, il est ordonné par ``contact_id`` d'abord. Les trois colonnes,
#: pas deux — l'écran offre un filtre par propriétaire, et sans lui dans
#: l'index les trois zones perdent la couverture : 1,6 ms mesurés contre
#: 24 ms.
#:
#: **Les trois index ``COLLATE NOCASE``** sont ceux de la recherche globale,
#: et ils ne font pas doublon avec leurs jumeaux binaires. ``LIKE`` est
#: insensible à la casse par défaut dans SQLite (``case_sensitive_like``
#: OFF), donc l'optimisation qui transforme ``LIKE 'mot%'`` en plage d'index
#: exige un index NOCASE — un index BINARY ne peut pas la servir, et le plan
#: retombe en ``SCAN``. Mesuré : la recherche de contacts passe de **898 ms
#: à 43,7 ms**, celle des comptes de 7,65 ms à 0,05 ms. Les index binaires
#: restent, eux, pour les ``ORDER BY``, qui sont bien binaires.
#:
#: **``contacts(status, last_name, first_name)`` est composite**, et l'ordre
#: des trois colonnes est le point : filtrer par statut puis trier par nom
#: utilisait ``idx_contacts_status`` et retriait 30 000 lignes en mémoire —
#: 147 ms. Le composite couvre le filtre ET l'ordre : 0,2 ms.
#:
#: **Les sept index préfixés par ``owner``** datent de l'arrivée des
#: comptes, et ils réparent une régression que le cadrage avait
#: introduite : dès qu'un prédicat ``owner = ?`` se pose à côté d'un
#: ``ORDER BY`` ou d'un ``LIKE``, l'index mono-colonne ne peut plus
#: servir les deux, et le plan retombe en tri temporaire ou en scan.
#: Mesuré, cadré, avant → après :
#:
#: - liste des contacts, page 1 : 100,5 ms → 0,08 ms ;
#: - recherche de contacts par préfixe : 93,7 ms → 6,1 ms ;
#: - recherche de comptes par préfixe : 5,0 ms → 0,62 ms ;
#: - datatable des comptes triée par nom : 9,04 ms → 0,08 ms.
#:
#: Le préfixe ``owner`` vient EN PREMIER dans chacun : c'est l'égalité,
#: et un index ne sert un ``ORDER BY`` que si les colonnes d'égalité le
#: précèdent. Les jumeaux non cadrés restent — la direction les utilise.
_INDEXES = """
CREATE INDEX idx_accounts_name      ON accounts(name);
CREATE INDEX idx_accounts_arr       ON accounts(arr);
CREATE INDEX idx_accounts_industry  ON accounts(industry);
CREATE INDEX idx_accounts_country   ON accounts(country);
CREATE INDEX idx_accounts_city      ON accounts(city);
CREATE INDEX idx_accounts_size      ON accounts(size);
CREATE INDEX idx_accounts_owner     ON accounts(owner);
CREATE INDEX idx_accounts_created   ON accounts(created_at);
CREATE INDEX idx_contacts_account   ON contacts(account_id);
CREATE INDEX idx_contacts_last      ON contacts(last_name, first_name);
CREATE INDEX idx_contacts_status    ON contacts(status, last_name, first_name);
CREATE INDEX idx_deals_stage        ON deals(stage, position);
CREATE INDEX idx_deals_owner        ON deals(owner, stage, position);
CREATE INDEX idx_deals_account      ON deals(account_id);
CREATE INDEX idx_activities_contact ON activities(contact_id, at);
CREATE INDEX idx_activities_at      ON activities(at, kind, owner);
CREATE INDEX idx_notes_contact      ON notes(contact_id, at);

CREATE INDEX idx_accounts_name_ci   ON accounts(name COLLATE NOCASE);
CREATE INDEX idx_contacts_last_ci   ON contacts(last_name COLLATE NOCASE);
CREATE INDEX idx_contacts_email_ci  ON contacts(email COLLATE NOCASE);

CREATE INDEX idx_accounts_own_name  ON accounts(owner, name);
CREATE INDEX idx_accounts_own_arr   ON accounts(owner, arr);
CREATE INDEX idx_accounts_own_ci    ON accounts(owner, name COLLATE NOCASE);
CREATE INDEX idx_contacts_own       ON contacts(owner, last_name, first_name);
CREATE INDEX idx_contacts_own_stat  ON contacts(owner, status, last_name,
                                                first_name);
CREATE INDEX idx_contacts_own_last  ON contacts(owner, last_name COLLATE NOCASE);
CREATE INDEX idx_contacts_own_mail  ON contacts(owner, email COLLATE NOCASE);
"""


def seeded_version(conn: sqlite3.Connection) -> int | None:
    """La version du seed en place, ou ``None`` si le fichier n'en a pas."""
    try:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = 'seed_version'"
        ).fetchone()
    except sqlite3.OperationalError:
        return None                      # pas de table meta = fichier vierge
    return row[0] if row else None


def init_db(*, force: bool = False) -> bool:
    """(Re)crée schéma + index + seed si nécessaire. Renvoie True si semé.

    Idempotent et déterministe : le même ``SEED_VERSION`` laisse le fichier
    intact, y compris les écritures faites depuis l'app. C'est la différence
    avec ``examples/mad``, qui repose son seed à chaque démarrage : à 262 000
    lignes ce n'est plus gratuit, et un pipeline qu'on vient de réordonner
    reviendrait à sa place à chaque ``reload``.
    """
    conn = connect()
    try:
        if not force and seeded_version(conn) == SEED_VERSION:
            return False
    finally:
        conn.close()

    from examples.crm.core.seed import build_seed

    DB_PATH.unlink(missing_ok=True)
    conn = connect()
    try:
        # WAL : lectures concurrentes pendant une écriture. Une app SDUI rend
        # plusieurs zones par requête, chacune ouvrant sa connexion.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)
        for table, rows in build_seed():
            placeholders = ",".join("?" * len(rows[0]))
            conn.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)
        # Index posés APRÈS l'insertion : les construire d'abord ferait payer
        # un rééquilibrage d'arbre à chacune des 262 000 lignes.
        conn.executescript(_INDEXES)
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('seed_version', ?)",
            (SEED_VERSION,),
        )
        conn.commit()
    finally:
        conn.close()
    return True


feature = Feature(
    name="db", kind="infra",
    provides=[connect, query, scalar, execute, owner_scope, init_db],
)
