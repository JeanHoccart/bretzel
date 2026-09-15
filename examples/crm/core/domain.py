"""core/domain — le vocabulaire métier, en pur Python.

Ni feature ni état : des constantes, comme ``core/theme.py``. Le seed les
écrit dans la base, les écrans les relisent pour peindre badges et filtres.
Les avoir à un seul endroit est ce qui garantit qu'un filtre de datatable
propose exactement les valeurs qui existent en base — le domaine d'un filtre
en mode callable doit être DÉCLARÉ, le composant ne détient aucune ligne
pour le dériver.
"""

from __future__ import annotations

from datetime import date

#: « Aujourd'hui » du jeu de données. Une date FIGÉE, pas ``date.today()`` :
#: un seed relatif à l'horloge rend la base non reproductible et fait dériver
#: les échéances du pipeline d'un jour par jour.
TODAY = date(2026, 8, 19)

#: L'écart entre deux rangs de kanban voisins. Le semis l'applique, et le
#: réordonnancement s'en resert quand il renumérote une étape : insérer entre
#: deux cartes prend le milieu de leurs rangs, et sur des entiers consécutifs
#: il n'y a pas de milieu.
POSITION_STEP = 64

# ── Étapes du pipeline (écran 1) ─────────────────────────────────────
# (clé, libellé, couleur sémantique). L'ordre EST celui des colonnes.
STAGES: tuple[tuple[str, str, str], ...] = (
    ("lead",      "Piste",        "muted"),
    ("qualified", "Qualifié",     "info"),
    ("proposal",  "Proposition",  "primary"),
    ("negotiation", "Négociation", "warning"),
    ("won",       "Gagné",        "success"),
    ("lost",      "Perdu",        "error"),
)
STAGE_KEYS: tuple[str, ...] = tuple(k for k, _l, _c in STAGES)
STAGE_LABEL: dict[str, str] = {k: lbl for k, lbl, _c in STAGES}
STAGE_COLOR: dict[str, str] = {k: c for k, _l, c in STAGES}

#: Les colonnes du kanban : « gagné » et « perdu » sortent du tableau — un
#: pipeline montre ce qui est encore en jeu.
OPEN_STAGES: tuple[str, ...] = ("lead", "qualified", "proposal", "negotiation")

# ── Statuts de contact (écrans 3 et 4) ───────────────────────────────
CONTACT_STATUS: dict[str, tuple[str, str]] = {
    "active":   ("Actif",     "success"),
    "lead":     ("Prospect",  "warning"),
    "dormant":  ("Dormant",   "muted"),
    "churned":  ("Perdu",     "error"),
}
STATUS_KEYS: tuple[str, ...] = tuple(CONTACT_STATUS)

# ── Comptes (écran 2) ────────────────────────────────────────────────
INDUSTRIES: tuple[str, ...] = (
    "Industrie", "Santé", "Finance", "Logistique", "Distribution",
    "Énergie", "Éducation", "Bâtiment", "Média", "Agroalimentaire",
)
COUNTRIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("France",   ("Paris", "Lyon", "Lille", "Nantes", "Toulouse", "Bordeaux")),
    ("Belgique", ("Bruxelles", "Anvers", "Gand", "Liège")),
    ("Suisse",   ("Genève", "Zurich", "Lausanne")),
    ("Canada",   ("Montréal", "Québec", "Ottawa")),
)
COUNTRY_KEYS: tuple[str, ...] = tuple(c for c, _villes in COUNTRIES)
SIZES: tuple[str, ...] = ("TPE", "PME", "ETI", "Grand compte")

# ── Le calendrier, en français ───────────────────────────────────────
#: Les quatre composants de dates (`calendar`, `date_picker`,
#: `date_range_picker`, `month_picker`) rendent leurs mois et leurs jours en
#: ANGLAIS par défaut, et n'ont pas de notion de locale — seulement ces deux
#: props. Une app française doit donc les porter, et les repasser à CHAQUE
#: composant de date qu'elle monte.
MONTHS_FR: list[str] = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]
#: ⚠️ Ordre **DIMANCHE-premier**, quel que soit le ``weekstart`` demandé :
#: la liste est indexée par ``Date.getDay()`` et c'est le composant qui la
#: fait tourner (``rotate_weekday_names``, documenté sur
#: ``DEFAULT_WEEKDAY_NAMES_SUN_FIRST``). Écrite lundi-première — le réflexe
#: français — elle décale toutes les colonnes d'un jour, sans rien casser
#: qui se voie autrement qu'en lisant l'en-tête.
WEEKDAYS_FR: list[str] = ["Di", "Lu", "Ma", "Me", "Je", "Ve", "Sa"]
#: L'abrégé de l'axe d'un graphique temporel, où « Septembre » ne tient pas.
MONTHS_FR_SHORT: list[str] = [
    "janv.", "févr.", "mars", "avr.", "mai", "juin",
    "juil.", "août", "sept.", "oct.", "nov.", "déc.",
]

# ── Qui travaille ici ────────────────────────────────────────────────
OWNERS: tuple[str, ...] = (
    "Aïcha Benali", "Marc Dubois", "Sofia Rossi", "Léa Martin",
    "Tom Nguyen", "Clara Weiss",
)

# ── Qui a le droit de voir quoi (écran 0 : la connexion) ─────────────
#: Les deux rôles. ``commercial`` ne voit QUE son portefeuille ;
#: ``directeur`` voit tout et peut se mettre à la place de n'importe qui.
#:
#: Deux et pas trois : un rôle de plus se justifie par un écran qui le
#: réclame, et aucun ne le fait. C'est la même règle que pour les quatre
#: composants non arbitrés.
ROLES: dict[str, str] = {
    "commercial": "Commercial",
    "directeur": "Direction",
}

#: La seule route publique. Ici et pas dans la feature : le middleware de
#: ``main`` la lit aussi, et une CHAÎNE dans un ``provides`` se classe par
#: son ``__name__``, qu'elle n'a pas (leçon de la tranche 2). Une seule
#: source, sinon la garde et la page dérivent — et une garde qui dérive
#: laisse passer, ou enferme tout le monde dehors.
LOGIN_PATH = "/connexion"

#: Le mot de passe de TOUS les comptes de démonstration. En clair ici, haché
#: en base — c'est un jeu d'essai, et le cacher ne protégerait rien tout en
#: rendant l'app inutilisable.
DEMO_PASSWORD = "bretzel"


def login_for(name: str) -> str:
    """``« Aïcha Benali »`` → ``« a.benali »``. Sans accent : un login se tape.

    Ici et pas dans ``core/seed.py`` : c'est une RÈGLE de nommage, lue par
    le semis ET par la page de connexion. L'y laisser faisait dépendre une
    page de la fabrique de données de démonstration.
    """
    import unicodedata

    first, _, last = name.partition(" ")
    plain = unicodedata.normalize("NFD", f"{first[:1]}.{last}")
    return "".join(c for c in plain if not unicodedata.combining(c)).lower()

# ── Import (écran 9) ─────────────────────────────────────────────────
#: Les colonnes d'un CSV de comptes, dans l'ordre. Ici et pas dans la feature
#: ``import_data`` : deux features les lisent, et un ``provides`` classe ses
#: entrées par ``__name__`` — qu'un tuple n'a pas (leçon de la tranche 2, où
#: la carte de l'app affichait un nœud nommé « int »). Le vocabulaire n'est
#: pas une surface de feature, c'est du domaine.
IMPORT_COLUMNS: tuple[str, ...] = (
    "name", "industry", "country", "city", "size", "arr", "owner",
)
#: Le plafond d'un import. Au-delà, l'aperçu n'est plus un aperçu et la
#: transaction devient un verrou long sur une base que les autres écrans
#: lisent.
IMPORT_MAX_ROWS = 500
IMPORT_EXAMPLE_CSV = (
    "name,industry,country,city,size,arr,owner\n"
    "Nouvelle Enseigne SAS,Distribution,France,Lyon,PME,42000,Marc Dubois\n"
    "Atelier du Nord,Industrie,Belgique,Gand,TPE,9000,Sofia Rossi\n"
)

# ── Activités (écran 4) ──────────────────────────────────────────────
ACTIVITY_KINDS: dict[str, tuple[str, str, str]] = {
    "call":    ("Appel",    "phone",       "info"),
    "email":   ("Email",    "mail",        "primary"),
    "meeting": ("Réunion",  "users",       "success"),
    "note":    ("Note",     "sticky-note", "muted"),
    "task":    ("Tâche",    "check-check", "warning"),
}
ACTIVITY_KEYS: tuple[str, ...] = tuple(ACTIVITY_KINDS)


def activity_badge(kind: str) -> tuple[str, str, str]:
    """``(libellé, icône, couleur)`` d'un type d'activité, repli compris.

    Le pendant de :func:`status_badge` pour l'autre vocabulaire que deux
    écrans peignent — même raison : un type inédit en base doit s'afficher
    pareil partout.
    """
    return ACTIVITY_KINDS.get(kind, (kind, "circle", "muted"))


def status_badge(status: str) -> tuple[str, str]:
    """``(libellé, couleur)`` d'un statut de contact, repli compris.

    Trois écrans peignent ce badge ; le repli sur un statut inconnu doit être
    le même partout, sinon une valeur inédite en base s'affiche autrement
    selon la page qui la montre.
    """
    return CONTACT_STATUS.get(status, (status, "muted"))


def initials(first: str, last: str) -> str:
    """Les initiales d'un contact — utilisées par les avatars des écrans 3/4."""
    return ((first[:1] or "?") + (last[:1] or "")).upper()


def euros(amount: int) -> str:
    """``120000`` → ``« 120 k€ »``. Une colonne de montants doit tenir dans
    une carte de kanban de 260 px, pas afficher neuf chiffres.

    Le palier « Md€ » n'est pas décoratif : l'ARR cumulé des 50 000 comptes
    vaut 20 milliards, et sans lui l'en-tête affichait « 20139.2 M€ ».
    """
    if amount >= 1_000_000_000:
        return f"{amount / 1_000_000_000:.1f} Md€".replace(".0 ", " ")
    if amount >= 1_000_000:
        return f"{amount / 1_000_000:.1f} M€".replace(".0 ", " ")
    if amount >= 1_000:
        return f"{amount // 1_000} k€"
    return f"{amount} €"
