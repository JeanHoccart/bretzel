"""core/db — infra : le fichier SQLite, le schéma métier, ses index, le seed.

Feature ``kind="infra"`` : elle ne rend rien et ne porte aucun ``State``
Bretzel. Elle POSSÈDE une ressource externe — le fichier SQLite — et
expose les portes d'accès (``query`` / ``scalar`` en lecture, ``execute``
en écriture). Les features ``*_data`` requêtent par-dessus ; les pages ne
la touchent jamais.

**Sync, pas ``aiosqlite``**, pour la raison mesurée dans ``examples/crm``
et écrite dans son ``core/db.py`` : une zone ``@refreshable`` ne peut pas
être ``async``, et dans une app SDUI toute lecture vit dans une zone.
Deux couches de données — une async pour les handlers, une sync pour les
zones — serait exactement le « se dépanner » que ce chantier interdit.

Le schéma EST le § 5 du cahier
------------------------------
Chaque table vient d'un paragraphe du modèle métier, et deux formes
portent des règles transverses plutôt que du confort :

- **RT-2 · rien ne s'efface qui porte de l'histoire.** ``inscriptions``
  est une table à part, avec un ``debut`` et un ``fin`` : un élève qui
  part ne disparaît pas, sa ligne reçoit une fin. C'est la raison pour
  laquelle ``eleves`` ne porte AUCUN ``classe_id`` — ce serait la même
  information, mutable, et elle écraserait l'histoire à chaque
  changement de classe.
- **RT-1 · l'année en cours est la seule qu'on écrit.** Toute table
  datée porte son ``annee_id`` (directement, ou par sa classe). C'est ce
  qui permet à la garde de ``features/annees.py`` de répondre sans
  deviner.

Ce que le schéma REFUSE, et qui est du métier
---------------------------------------------
Trois contraintes d'unicité valent des règles, parce qu'elles tiennent
même quand l'écran se trompe (RT-8) :

- ``classes(annee_id, code)`` — « la même classe d'une autre année est
  une autre classe » (§ 4) ;
- ``creneaux(annee_id, jour, horaire_id, semaine)`` — « une seule classe
  par case » (§ 5.4) ;
- ``heures_exceptionnelles(annee_id, jour, horaire_id)`` — « une case du
  calendrier ne porte qu'une décision : reposer la même case remplace »
  (§ 5.4), d'où le ``INSERT OR REPLACE`` que cette unicité rend possible.

Une connexion PAR THREAD, pas par appel
---------------------------------------
``connect()`` a longtemps ouvert une connexion neuve à chaque lecture,
au nom de l'anti-règle 2 (« zéro état global mutable »). Mesuré le
2026-09-13 sur ``/plan/1`` : vider une place coûtait **26 connexions
ouvertes puis refermées**, soit 18 ms des ~100 ms de la requête, et
**52 ``execute``** là où 26 suffisaient — chaque ouverture repose son
``PRAGMA foreign_keys``. Ouvrir un fichier n'est pas gratuit, et une
app SDUI rend plusieurs zones par requête : le coût se paie autant de
fois qu'il y a de lectures.

La connexion vit donc dans un :class:`threading.local`. Ce n'est PAS
l'état global que l'anti-règle interdit : rien n'est partagé entre
deux threads, donc rien n'a besoin de verrou, et le plafond est celui
du threadpool d'``anyio`` — 40 connexions au plus, réutilisées.

Deux conséquences qu'il faut tenir, et elles sont écrites sur les
fonctions concernées : une écriture qui lève doit ``rollback``, sinon
la transaction reste ouverte sur une connexion qui, elle, ne meurt
plus ; et ``init_db`` doit fermer avant de supprimer le fichier, parce
que Windows refuse d'effacer un fichier encore ouvert.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

from bretzel import Feature

DB_PATH = Path(__file__).with_name("ecole.db")

#: Bumpé quand le schéma ou le seed change — ``init_db`` reconstruit
#: alors le fichier.
SEED_VERSION = 4


#: La connexion de chaque thread. Un ``threading.local`` et pas un dict
#: verrouillé : deux threads ne se voient pas, donc il n'y a rien à
#: synchroniser à l'usage.
_LOCALE = threading.local()

#: Toutes les connexions ouvertes, tous threads confondus — la seule
#: chose que :func:`fermer_les_connexions` peut fermer. Un ``set`` sous
#: verrou, parce que celui-là, lui, traverse les threads.
_OUVERTES: set[sqlite3.Connection] = set()
_VERROU = threading.Lock()


def connect() -> sqlite3.Connection:
    """La connexion de CE thread, ouverte à la première demande.

    ⚠️ ``check_same_thread=False`` n'autorise PAS le partage : chaque
    thread garde la sienne, et c'est le ``threading.local`` qui le
    garantit. Le drapeau ne sert qu'à :func:`fermer_les_connexions`,
    qui doit pouvoir refermer celles des autres threads avant que
    ``init_db`` n'efface le fichier.
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
    """Referme toutes les connexions ouvertes, tous threads confondus.

    Appelée avant de supprimer le fichier (``init_db``) : sous Windows,
    un ``unlink`` sur une base encore ouverte lève ``PermissionError``.
    """
    with _VERROU:
        connexions = tuple(_OUVERTES)
        _OUVERTES.clear()
    for conn in connexions:
        conn.close()
    _LOCALE.conn = None


def query(sql: str, params: tuple = ()) -> list[dict]:
    """Exécute un SELECT et renvoie une liste de dicts — porte de LECTURE."""
    return [dict(r) for r in connect().execute(sql, params)]


def scalar(sql: str, params: tuple = ()) -> Any:
    """La première colonne de la première ligne — pour les ``COUNT(*)``."""
    row = connect().execute(sql, params).fetchone()
    return row[0] if row is not None else None


#: Les verbes pour lesquels ``lastrowid`` veut dire quelque chose. Après
#: un ``UPDATE``, sqlite3 laisse ``lastrowid`` à ``0`` sur une connexion
#: neuve — jamais ``None`` — donc un repli ``lastrowid or rowcount``
#: rendrait toujours zéro et une écriture réussie se lirait « refusée ».
#: Le piège est documenté dans ``examples/crm/core/db.py``, où il a
#: réellement mordu.
_ROWID_VERBS = frozenset({"INSERT", "REPLACE"})


def execute(sql: str, params: tuple = ()) -> int:
    """Exécute un INSERT / UPDATE / DELETE et commit — porte d'ÉCRITURE.

    Renvoie le ``lastrowid`` (INSERT) ou le nombre de lignes touchées.

    ⚠️ **Cette porte ne connaît pas RT-1.** Elle ne peut pas : l'année
    concernée dépend de la table et parfois d'une jointure. La garde est
    donc un cran au-dessus, dans ``features/annees.py``
    (:func:`~examples.ecole.features.annees.garde_ecriture`), appelée par
    chaque fonction d'écriture métier. Mettre le test ici donnerait
    l'illusion d'une barrière à l'endroit où elle serait le plus facile à
    contourner — un ``executescript`` suffirait.
    """
    verb = sql.lstrip().split(None, 1)[0].upper()
    conn = connect()
    try:
        cur = conn.execute(sql, params)
    except Exception:
        # ⚠️ Le ``rollback`` est ce que la fermeture faisait pour nous
        # quand chaque appel ouvrait sa connexion. Sans lui, une
        # écriture qui lève — une contrainte d'unicité violée, RT-8 —
        # laisse une transaction ouverte sur une connexion qui vit
        # jusqu'à la fin du process : le verrou d'écriture reste pris et
        # la requête SUIVANTE échoue, loin de la cause.
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

#: Les index que les écrans réclament. Cette app est à 473 élèves, pas à
#: 50 000 comptes : aucun de ces index n'achète une milliseconde
#: aujourd'hui. Ils sont là pour les CLÉS ÉTRANGÈRES qu'on suit dans les
#: deux sens — un élève vers ses classes, une classe vers ses élèves —
#: parce que SQLite n'en crée aucun tout seul, et qu'une lecture par clé
#: étrangère non indexée est un scan.
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
    """Une valeur de la table ``meta``, ou ``None`` sur un fichier vierge."""
    try:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = ?", (cle,)
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    return row[0] if row else None


def init_db(*, force: bool = False) -> bool:
    """(Re)crée schéma + index + seed si nécessaire. Vrai si semé.

    ⚠️ **Deux marqueurs, pas un**, et le second est propre à cette app :
    la version du seed ET l'année de la rentrée. Le jeu semé est bâti
    AUTOUR de la date du jour — l'année en cours doit contenir
    aujourd'hui, sinon la grille de la semaine s'ouvre sur des vacances
    et le cahier de texte ne propose rien. Une base semée en juin et
    ouverte en septembre montrerait l'année précédente comme « en
    cours ». Le marqueur ``rentree`` la fait se refaire toute seule, une
    fois par an.
    """
    from examples.ecole.core.seed import RENTREE, build_seed

    conn = connect()
    a_jour = (
        marqueur(conn, "seed_version") == str(SEED_VERSION)
        and marqueur(conn, "rentree") == str(RENTREE)
    )
    if a_jour and not force:
        return False

    # Le fichier va disparaître sous les connexions ouvertes : on les
    # ferme d'abord. Sous Windows, ``unlink`` lèverait.
    fermer_les_connexions()
    DB_PATH.unlink(missing_ok=True)
    conn = connect()
    try:
        # WAL : lectures concurrentes pendant une écriture. Une app SDUI
        # rend plusieurs zones par requête, et chaque thread garde la
        # sienne ouverte.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)
        for table, rows in build_seed():
            if not rows:
                continue
            placeholders = ",".join("?" * len(rows[0]))
            conn.executemany(
                f"INSERT INTO {table} VALUES ({placeholders})", rows
            )
        # Index posés APRÈS l'insertion : les construire d'abord ferait
        # payer un rééquilibrage d'arbre à chaque ligne.
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
