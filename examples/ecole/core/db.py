"""core/db — infra: the SQLite file, the business schema, its indexes,
the seed.

A ``kind="infra"`` feature: it renders nothing and carries no Bretzel
``State``. It OWNS an external resource — the SQLite file — and exposes
the access doors (``query`` / ``scalar`` for reads, ``execute`` for
writes). The ``*_data`` features query on top of it; the pages never
touch it.

**Sync, not ``aiosqlite``**, for the reason measured in ``examples/crm``
and written in its ``core/db.py``: a ``@refreshable`` zone cannot be
``async``, and in an SDUI app every read lives in a zone. Two data layers
— an async one for the handlers, a sync one for the zones — would be
exactly the "working around it" this work forbids.

The schema IS § 5 of the specification
---------------------------------------
Every table comes from a paragraph of the business model, and two shapes
carry cross-cutting rules rather than convenience:

- **RT-2 · nothing that carries history is erased.** ``inscriptions`` is
  a separate table, with a ``debut`` and a ``fin``: a pupil who leaves
  does not disappear, their row receives an end. It is why ``eleves``
  carries NO ``classe_id`` — that would be the same information,
  mutable, and it would overwrite the history at every class change.
- **RT-1 · the current year is the only one written.** Every dated table
  carries its ``annee_id`` (directly, or through its class). It is what
  lets ``features/annees.py``'s guard answer without guessing.

What the schema REFUSES, and which is business
-----------------------------------------------
Three uniqueness constraints are worth rules, because they hold even
when the screen is wrong (RT-8):

- ``classes(annee_id, code)`` — "the same class of another year is
  another class" (§ 4);
- ``creneaux(annee_id, jour, horaire_id, semaine)`` — "one class per
  cell only" (§ 5.4);
- ``heures_exceptionnelles(annee_id, jour, horaire_id)`` — "a calendar
  cell carries one decision only: setting the same cell again replaces"
  (§ 5.4), hence the ``INSERT OR REPLACE`` this uniqueness makes
  possible.

One connection PER THREAD, not per call
----------------------------------------
``connect()`` long opened a fresh connection at every read, in the name
of anti-rule 2 ("zero mutable global state"). Measured on 2026-09-13 on
``/plan/1``: emptying one seat cost **26 connections opened then
closed**, that is 18 ms of the request's ~100 ms, and **52 ``execute``**
where 26 were enough — every opening re-sets its ``PRAGMA
foreign_keys``. Opening a file is not free, and an SDUI app renders
several zones per request: the cost is paid as many times as there are
reads.

So the connection lives in a :class:`threading.local`. That is NOT the
global state the anti-rule forbids: nothing is shared between two
threads, so nothing needs a lock, and the ceiling is ``anyio``'s
threadpool — 40 connections at most, reused.

Two consequences must be held, and they are written on the functions
concerned: a write that raises must ``rollback``, otherwise the
transaction stays open on a connection that no longer dies; and
``init_db`` must close before deleting the file, because Windows refuses
to erase a file that is still open.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

from bretzel import Feature

DB_PATH = Path(__file__).with_name("ecole.db")

#: Bumped when the schema or the seed changes — ``init_db`` then
#: rebuilds the file.
SEED_VERSION = 4


#: Each thread's connection. A ``threading.local`` and not a locked
#: dict: two threads do not see each other, so there is nothing to
#: synchronise in use.
_LOCALE = threading.local()

#: Every open connection, all threads together — the only thing
#: :func:`fermer_les_connexions` can close. A ``set`` under a lock,
#: because that one does cross threads.
_OUVERTES: set[sqlite3.Connection] = set()
_VERROU = threading.Lock()


def connect() -> sqlite3.Connection:
    """THIS thread's connection, opened on first demand.

    ⚠️ ``check_same_thread=False`` does NOT allow sharing: each thread
    keeps its own, and it is the ``threading.local`` that guarantees it.
    The flag only serves :func:`fermer_les_connexions`, which must be
    able to close the other threads' before ``init_db`` erases the file.
    """
    conn: sqlite3.Connection | None = getattr(_LOCALE, "conn", None)
    if conn is None:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        _LOCALE.conn = conn
        with _VERROU:
            _OUVERTES.add(conn)
    return conn


def fermer_les_connexions() -> None:
    """Close every open connection, all threads together.

    Called before deleting the file (``init_db``): under Windows, an
    ``unlink`` on a database still open raises ``PermissionError``.
    """
    with _VERROU:
        connexions = tuple(_OUVERTES)
        _OUVERTES.clear()
    for conn in connexions:
        conn.close()
    _LOCALE.conn = None


def query(sql: str, params: tuple = ()) -> list[dict]:
    """Run a SELECT and return a list of dicts — the READ door."""
    return [dict(r) for r in connect().execute(sql, params)]


def scalar(sql: str, params: tuple = ()) -> Any:
    """The first column of the first row — for the ``COUNT(*)``."""
    row = connect().execute(sql, params).fetchone()
    return row[0] if row is not None else None


#: The verbs for which ``lastrowid`` means something. After an
#: ``UPDATE``, sqlite3 leaves ``lastrowid`` at ``0`` on a fresh
#: connection — never ``None`` — so a ``lastrowid or rowcount`` fallback
#: would always return zero and a successful write would read as
#: "refused". The trap is documented in ``examples/crm/core/db.py``,
#: where it really bit.
_ROWID_VERBS = frozenset({"INSERT", "REPLACE"})


def execute(sql: str, params: tuple = ()) -> int:
    """Run an INSERT / UPDATE / DELETE and commit — the WRITE door.

    Returns the ``lastrowid`` (INSERT) or the number of rows touched.

    ⚠️ **This door does not know RT-1.** It cannot: the year concerned
    depends on the table and sometimes on a join. So the guard is one
    level up, in ``features/annees.py``
    (:func:`~examples.ecole.features.annees.garde_ecriture`), called by
    every business write function. Putting the test here would give the
    illusion of a barrier in the place where it would be easiest to work
    around — an ``executescript`` would do.
    """
    verb = sql.lstrip().split(None, 1)[0].upper()
    conn = connect()
    try:
        cur = conn.execute(sql, params)
    except Exception:
        # ⚠️ The ``rollback`` is what closing did for us when every
        # call opened its own connection. Without it, a write that
        # raises — a uniqueness constraint violated, RT-8 — leaves a
        # transaction open on a connection that now lives to the end of
        # the process: the write lock stays taken and the NEXT request
        # fails, far from the cause.
        conn.rollback()
        raise
    conn.commit()
    return cur.lastrowid if verb in _ROWID_VERBS else cur.rowcount


_SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);

-- ── Structure ────────────────────────────────────────────────────────

CREATE TABLE annees (
    id         INTEGER PRIMARY KEY,
    libelle    TEXT    NOT NULL UNIQUE,   -- « 2026-2027 »
    debut      TEXT    NOT NULL,
    fin        TEXT    NOT NULL,
    en_cours   INTEGER NOT NULL DEFAULT 0,
    -- Le LUNDI de référence de la semaine A. Peut être vide : une année
    -- sans référence rend une alternance indéterminée, et l'écran doit
    -- le dire plutôt que d'inventer (RT-4, RT-5).
    lundi_ref  TEXT
);

CREATE TABLE classes (
    id              INTEGER PRIMARY KEY,
    annee_id        INTEGER NOT NULL REFERENCES annees(id),
    code            TEXT    NOT NULL,     -- « 4e1 », « 2°GT2 »
    libelle         TEXT    NOT NULL,     -- le nom de l'établissement
    -- RT-3 : le cycle est une DONNÉE, jamais une lecture du code. Il est
    -- proposé une fois à la création (``domain.cycle_propose``) et
    -- corrigeable ; tous les écrans lisent cette colonne.
    cycle           TEXT    NOT NULL,
    niveau          TEXT    NOT NULL,
    rang            INTEGER NOT NULL,
    prof_principal  TEXT    NOT NULL DEFAULT '',
    UNIQUE (annee_id, code)
);

CREATE TABLE eleves (
    id           INTEGER PRIMARY KEY,
    nom          TEXT    NOT NULL,
    prenom       TEXT    NOT NULL,
    naissance    TEXT    NOT NULL DEFAULT '',
    -- Le jeu de démonstration porte des INITIALES colorées, pas des
    -- visages (§ 12 du cahier). La colonne reste pour l'import réel.
    photo        TEXT    NOT NULL DEFAULT '',
    amenagement  TEXT    NOT NULL DEFAULT '',   -- PAP / PPS / PAI / PPRE
    vue_fragile  INTEGER NOT NULL DEFAULT 0,
    gaucher      INTEGER NOT NULL DEFAULT 0,
    precisions   TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE inscriptions (
    id           INTEGER PRIMARY KEY,
    eleve_id     INTEGER NOT NULL REFERENCES eleves(id),
    classe_id    INTEGER NOT NULL REFERENCES classes(id),
    debut        TEXT    NOT NULL,
    fin          TEXT,                    -- vide = en cours (RT-2)
    demi_groupe  INTEGER                  -- 1, 2, ou rien
);

-- ── Calendrier ───────────────────────────────────────────────────────

CREATE TABLE horaires (
    id        INTEGER PRIMARY KEY,
    annee_id  INTEGER NOT NULL REFERENCES annees(id),
    rang      INTEGER NOT NULL,           -- 1 à 8
    debut     TEXT    NOT NULL,           -- « 08:15 »
    fin       TEXT    NOT NULL,
    UNIQUE (annee_id, rang)
);

CREATE TABLE creneaux (
    id          INTEGER PRIMARY KEY,
    annee_id    INTEGER NOT NULL REFERENCES annees(id),
    jour        INTEGER NOT NULL,         -- 0 = lundi … 5 = samedi
    horaire_id  INTEGER NOT NULL REFERENCES horaires(id),
    semaine     TEXT    NOT NULL,         -- « A » ou « B »
    classe_id   INTEGER NOT NULL REFERENCES classes(id),
    -- Vide = c'est un COURS. C'est le défaut, et c'est le piège n° 1 :
    -- seuls les mots de ``domain.NATURES`` retirent une heure du cahier
    -- de texte, tout le reste est une salle (EF-B7).
    nature      TEXT    NOT NULL DEFAULT '',
    salle       TEXT    NOT NULL DEFAULT '',
    UNIQUE (annee_id, jour, horaire_id, semaine)
);

CREATE TABLE heures_exceptionnelles (
    id          INTEGER PRIMARY KEY,
    annee_id    INTEGER NOT NULL REFERENCES annees(id),
    jour        TEXT    NOT NULL,         -- une VRAIE date ISO
    horaire_id  INTEGER NOT NULL REFERENCES horaires(id),
    -- Une classe = heure en plus ; rien = annulation (EF-B11).
    classe_id   INTEGER REFERENCES classes(id),
    salle       TEXT    NOT NULL DEFAULT '',
    UNIQUE (annee_id, jour, horaire_id)
);

CREATE TABLE trimestres (
    id        INTEGER PRIMARY KEY,
    annee_id  INTEGER NOT NULL REFERENCES annees(id),
    cycle     TEXT    NOT NULL,
    numero    INTEGER NOT NULL,           -- 1, 2, 3
    -- La FIN seule. Le début est le lendemain du précédent (EF-A3), et
    -- une case vide est normale (RT-4).
    fin       TEXT,
    UNIQUE (annee_id, cycle, numero)
);

CREATE TABLE vacances (
    id        INTEGER PRIMARY KEY,
    annee_id  INTEGER NOT NULL REFERENCES annees(id),
    libelle   TEXT    NOT NULL,
    -- Premier et dernier jour SANS classe (EF-A5). Un jour férié est une
    -- période d'un seul jour : même table, même règle.
    debut     TEXT    NOT NULL,
    fin       TEXT    NOT NULL,
    -- Deux périodes du même nom dans une année sont une faute de saisie,
    -- et c'est cette unicité qui rend l'écran possible : EF-A4 dit que
    -- les quatre vacances de zone B sont PROPOSÉES « remplies ou non »,
    -- donc une proposition se remplit par son NOM — il faut qu'un nom
    -- désigne au plus une ligne.
    UNIQUE (annee_id, libelle)
);

CREATE TABLE grilles_precedentes (
    id        INTEGER PRIMARY KEY,
    annee_id  INTEGER NOT NULL REFERENCES annees(id),
    pose_le   TEXT    NOT NULL,
    contenu   TEXT    NOT NULL            -- la grille entière, en JSON
);

-- ── Évaluation ───────────────────────────────────────────────────────

CREATE TABLE evaluations (
    id           INTEGER PRIMARY KEY,
    classe_id    INTEGER NOT NULL REFERENCES classes(id),
    trimestre    INTEGER NOT NULL,
    nom          TEXT    NOT NULL,
    type         TEXT    NOT NULL,
    date         TEXT    NOT NULL,
    bareme       REAL    NOT NULL,
    coefficient  REAL    NOT NULL,
    reporte_le   TEXT,                    -- École Directe (EF-D7)
    -- Relie les copies d'un même devoir donné dans plusieurs classes
    -- d'un même niveau. Chaque classe garde la SIENNE (EF-D2).
    commune_id   INTEGER
);

CREATE TABLE competences (
    id       INTEGER PRIMARY KEY,
    cycle    TEXT    NOT NULL,
    code     TEXT    NOT NULL,
    libelle  TEXT    NOT NULL,
    rang     INTEGER NOT NULL,
    UNIQUE (cycle, code)
);

CREATE TABLE competences_evaluees (
    id                INTEGER PRIMARY KEY,
    evaluation_id     INTEGER NOT NULL REFERENCES evaluations(id),
    competence_id     INTEGER NOT NULL REFERENCES competences(id),
    points            REAL    NOT NULL,
    -- Précise ce qui a été évalué ; n'est JAMAIS notée à part (EF-D3).
    sous_competence   TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE notes (
    id             INTEGER PRIMARY KEY,
    evaluation_id  INTEGER NOT NULL REFERENCES evaluations(id),
    eleve_id       INTEGER NOT NULL REFERENCES eleves(id),
    -- Soit absent SANS note, soit présent AVEC une note (§ 5.2).
    absent         INTEGER NOT NULL DEFAULT 0,
    valeur         REAL,
    UNIQUE (evaluation_id, eleve_id)
);

CREATE TABLE sous_notes (
    id                      INTEGER PRIMARY KEY,
    note_id                 INTEGER NOT NULL REFERENCES notes(id),
    competence_evaluee_id   INTEGER NOT NULL REFERENCES competences_evaluees(id),
    valeur                  REAL    NOT NULL,
    UNIQUE (note_id, competence_evaluee_id)
);

-- EF-D8 : une note changée APRÈS coup se reporte à la main sur École
-- Directe. La liste survit à la fermeture, et ne s'efface que lorsque le
-- professeur dit l'avoir fait — d'où une TABLE et non un état de session.
CREATE TABLE corrections_a_reporter (
    id             INTEGER PRIMARY KEY,
    evaluation_id  INTEGER NOT NULL REFERENCES evaluations(id),
    eleve_id       INTEGER NOT NULL REFERENCES eleves(id),
    ancienne       REAL,
    nouvelle       REAL,
    cree_le        TEXT    NOT NULL,
    UNIQUE (evaluation_id, eleve_id)
);

-- ── Observation ──────────────────────────────────────────────────────

CREATE TABLE criteres (
    id       INTEGER PRIMARY KEY,
    rang     INTEGER NOT NULL,
    libelle  TEXT    NOT NULL UNIQUE
);

CREATE TABLE niveaux_critere (
    id          INTEGER PRIMARY KEY,
    critere_id  INTEGER NOT NULL REFERENCES criteres(id),
    rang        INTEGER NOT NULL,         -- 1 = le plus favorable
    court       TEXT    NOT NULL,         -- le libellé de la tuile
    long        TEXT    NOT NULL,
    teinte      INTEGER NOT NULL,         -- 1-2 favorable, 3-4 difficulté
    UNIQUE (critere_id, rang)
);

-- EF-E5 : une formulation PAR TRIMESTRE, pour ne pas répéter la même
-- phrase trois fois dans l'année. Semée vide : c'est le lot 6 qui la
-- remplit, en même temps que la rédaction qui la lit.
CREATE TABLE phrases (
    id                 INTEGER PRIMARY KEY,
    niveau_critere_id  INTEGER NOT NULL REFERENCES niveaux_critere(id),
    trimestre          INTEGER NOT NULL,
    texte              TEXT    NOT NULL,
    UNIQUE (niveau_critere_id, trimestre)
);

CREATE TABLE fiches (
    id            INTEGER PRIMARY KEY,
    eleve_id      INTEGER NOT NULL REFERENCES eleves(id),
    classe_id     INTEGER NOT NULL REFERENCES classes(id),
    trimestre     INTEGER NOT NULL,
    appreciation  TEXT    NOT NULL DEFAULT '',
    -- RT-7 / EF-E3 : dès que le professeur écrit son propre texte,
    -- l'application ne le réécrit plus JAMAIS. Ce drapeau est la mémoire
    -- de cette décision ; sans lui, la proposition suivante l'écraserait.
    ecrite_main   INTEGER NOT NULL DEFAULT 0,
    UNIQUE (eleve_id, classe_id, trimestre)
);

CREATE TABLE fiches_niveaux (
    fiche_id           INTEGER NOT NULL REFERENCES fiches(id),
    critere_id         INTEGER NOT NULL REFERENCES criteres(id),
    niveau_critere_id  INTEGER NOT NULL REFERENCES niveaux_critere(id),
    -- Au plus UN niveau par critère (EF-E1), dit par le schéma.
    PRIMARY KEY (fiche_id, critere_id)
);

-- ── Plan de classe ───────────────────────────────────────────────────

CREATE TABLE salles_plan (
    id           INTEGER PRIMARY KEY,
    classe_id    INTEGER NOT NULL REFERENCES classes(id),
    nom          TEXT    NOT NULL,
    ordre        INTEGER NOT NULL,
    demi_groupe  INTEGER,                 -- 1, 2, ou rien (EF-G17)
    -- EF-G14 : le plan se FIGE, et l'état est retenu d'une ouverture à
    -- l'autre — on fige une fois pour l'année, pas à chaque heure.
    fige         INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE places (
    id              INTEGER PRIMARY KEY,
    salle_id        INTEGER NOT NULL REFERENCES salles_plan(id),
    rangee          INTEGER NOT NULL,
    colonne         INTEGER NOT NULL,
    eleve_id        INTEGER REFERENCES eleves(id),
    nouvelle_table  INTEGER NOT NULL DEFAULT 0,
    -- La largeur de l'allée qui PRÉCÈDE la place, en centièmes de place
    -- (0 = pas d'allée, 50 = une demi-place). Le stockage est par place,
    -- le GESTE est par colonne (EF-G4, piège n° 6).
    allee_avant     INTEGER NOT NULL DEFAULT 0,
    UNIQUE (salle_id, rangee, colonne)
);

-- EF-G10 : les contraintes sont attachées à la CLASSE, pas à la salle.
-- Les ressaisir par salle serait une corvée doublée d'un risque de
-- divergence.
CREATE TABLE separations (
    id         INTEGER PRIMARY KEY,
    classe_id  INTEGER NOT NULL REFERENCES classes(id),
    eleve_a    INTEGER NOT NULL REFERENCES eleves(id),
    eleve_b    INTEGER NOT NULL REFERENCES eleves(id)
);

CREATE TABLE devants (
    id         INTEGER PRIMARY KEY,
    classe_id  INTEGER NOT NULL REFERENCES classes(id),
    eleve_id   INTEGER NOT NULL REFERENCES eleves(id),
    UNIQUE (classe_id, eleve_id)
);

CREATE TABLE versions_plan (
    id        INTEGER PRIMARY KEY,
    salle_id  INTEGER NOT NULL REFERENCES salles_plan(id),
    nom       TEXT    NOT NULL,
    cree_le   TEXT    NOT NULL,
    contenu   TEXT    NOT NULL            -- les places figées, en JSON
);

-- EF-G15 : une forme de salle réutilisable, INDÉPENDANTE de toute classe.
CREATE TABLE gabarits_salle (
    id             INTEGER PRIMARY KEY,
    nom            TEXT    NOT NULL UNIQUE,
    rangees        TEXT    NOT NULL,      -- la longueur de chaque rangée, JSON
    allees         TEXT    NOT NULL,      -- les colonnes où passe une allée, JSON
    largeur_allee  INTEGER NOT NULL
);

-- ── Suivi ────────────────────────────────────────────────────────────

CREATE TABLE verifications (
    id         INTEGER PRIMARY KEY,
    eleve_id   INTEGER NOT NULL REFERENCES eleves(id),
    classe_id  INTEGER NOT NULL REFERENCES classes(id),
    motif      TEXT    NOT NULL,
    cree_le    TEXT    NOT NULL,
    -- EF-H3 : rien n'est effacé quand c'est fait, la date est POSÉE.
    -- Trois cahiers incomplets dans le trimestre disent quelque chose
    -- que trois lignes effacées ne diraient plus.
    fait_le    TEXT
);

CREATE TABLE chapitres (
    id      INTEGER PRIMARY KEY,
    niveau  TEXT    NOT NULL,
    titre   TEXT    NOT NULL,
    rang    INTEGER NOT NULL
);

CREATE TABLE seances_chapitre (
    id           INTEGER PRIMARY KEY,
    chapitre_id  INTEGER NOT NULL REFERENCES chapitres(id),
    numero       INTEGER NOT NULL,
    titre        TEXT    NOT NULL
);

CREATE TABLE cahier (
    id             INTEGER PRIMARY KEY,
    classe_id      INTEGER NOT NULL REFERENCES classes(id),
    date           TEXT    NOT NULL,
    chapitre_id    INTEGER REFERENCES chapitres(id),
    seance_numero  INTEGER,
    seance_titre   TEXT    NOT NULL DEFAULT '',
    contenu        TEXT    NOT NULL DEFAULT '',
    travail        TEXT    NOT NULL DEFAULT '',
    reporte_le     TEXT
);

-- EF-M3 : une fiche est rattachée à sa séance par le TITRE, jamais par
-- le numéro. Piège n° 10 : un numéro glisse dès qu'on insère une séance,
-- et toutes les fiches suivantes se retrouvent sur la voisine.
CREATE TABLE fiches_seance (
    id            INTEGER PRIMARY KEY,
    chapitre_id   INTEGER NOT NULL REFERENCES chapitres(id),
    seance_titre  TEXT    NOT NULL,
    resume        TEXT    NOT NULL DEFAULT '',
    UNIQUE (chapitre_id, seance_titre)
);

-- EF-M2 : deux carnets où l'on AJOUTE, chaque note datée. La même séance
-- donnée à la 3e2 puis à la 3e9, ce sont deux observations.
CREATE TABLE notes_fiche (
    id                INTEGER PRIMARY KEY,
    fiche_seance_id   INTEGER NOT NULL REFERENCES fiches_seance(id),
    carnet            TEXT    NOT NULL,   -- « preparer » ou « reflexions »
    texte             TEXT    NOT NULL,
    cree_le           TEXT    NOT NULL
);
"""

#: The indexes the screens ask for. This app is at 473 pupils, not
#: 50 000 accounts: none of these indexes buys a millisecond today. They
#: are there for the FOREIGN KEYS followed in both directions — a pupil
#: to their classes, a class to its pupils — because SQLite creates none
#: on its own, and a read by an unindexed foreign key is a scan.
_INDEXES = """
CREATE INDEX idx_classes_annee    ON classes(annee_id, rang);
CREATE INDEX idx_inscr_classe     ON inscriptions(classe_id, fin);
CREATE INDEX idx_inscr_eleve      ON inscriptions(eleve_id, debut);
CREATE INDEX idx_eleves_nom       ON eleves(nom COLLATE NOCASE, prenom COLLATE NOCASE);
CREATE INDEX idx_creneaux_grille  ON creneaux(annee_id, semaine, jour);
CREATE INDEX idx_creneaux_classe  ON creneaux(classe_id);
CREATE INDEX idx_hexc_jour        ON heures_exceptionnelles(annee_id, jour);
CREATE INDEX idx_vacances_annee   ON vacances(annee_id, debut);
CREATE INDEX idx_eval_classe      ON evaluations(classe_id, trimestre, date);
CREATE INDEX idx_notes_eval       ON notes(evaluation_id);
CREATE INDEX idx_notes_eleve      ON notes(eleve_id);
CREATE INDEX idx_fiches_classe    ON fiches(classe_id, trimestre);
CREATE INDEX idx_places_salle     ON places(salle_id, rangee, colonne);
CREATE INDEX idx_salles_classe    ON salles_plan(classe_id, ordre);
CREATE INDEX idx_verif_classe     ON verifications(classe_id, fait_le);
CREATE INDEX idx_verif_eleve      ON verifications(eleve_id, fait_le);
CREATE INDEX idx_cahier_classe    ON cahier(classe_id, date);
CREATE INDEX idx_seances_chap     ON seances_chapitre(chapitre_id, numero);
"""


def marqueur(conn: sqlite3.Connection, cle: str) -> str | None:
    """A value from the ``meta`` table, or ``None`` on a blank file."""
    try:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = ?", (cle,)
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    return row[0] if row else None


def init_db(*, force: bool = False) -> bool:
    """(Re)create schema + indexes + seed if needed. True if seeded.

    ⚠️ **Two markers, not one**, and the second is specific to this app:
    the seed's version AND the school year. The seeded set is built
    AROUND today's date — the current year must contain today, otherwise
    the week's grid opens on holidays and the lesson log proposes
    nothing. A database seeded in June and opened in September would show
    the previous year as "current". The ``rentree`` marker makes it
    rebuild itself, once a year.
    """
    from examples.ecole.core.seed import RENTREE, build_seed

    conn = connect()
    a_jour = (
        marqueur(conn, "seed_version") == str(SEED_VERSION)
        and marqueur(conn, "rentree") == str(RENTREE)
    )
    if a_jour and not force:
        return False

    # The file is about to disappear from under the open connections: we
    # close them first. Under Windows, ``unlink`` would raise.
    fermer_les_connexions()
    DB_PATH.unlink(missing_ok=True)
    conn = connect()
    try:
        # WAL: concurrent reads during a write. An SDUI app renders
        # several zones per request, and every thread keeps its own
        # open.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)
        for table, rows in build_seed():
            if not rows:
                continue
            placeholders = ",".join("?" * len(rows[0]))
            conn.executemany(
                f"INSERT INTO {table} VALUES ({placeholders})", rows
            )
        # Indexes placed AFTER the insertion: building them first would
        # make every row pay a tree rebalance.
        conn.executescript(_INDEXES)
        conn.executemany(
            "INSERT INTO meta (key, value) VALUES (?, ?)",
            (("seed_version", str(SEED_VERSION)), ("rentree", str(RENTREE))),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return True


feature = Feature(
    name="db", kind="infra",
    provides=[connect, fermer_les_connexions, query, scalar, execute,
              init_db],
)
