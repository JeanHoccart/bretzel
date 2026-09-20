"""L'atelier ne compte que le travail fait avec l'outillage complet.

Pourquoi une coupure, et pourquoi une GATE
-------------------------------------------
Décidé par l'utilisateur le 2026-09-12 : « comme la version aboutie de
describe, check, probe date de pas longtemps, les vieux sujets sont un
peu obsolètes ». L'app juge une tâche sur des gestes — demander la
surface, faire juger le contrat, vérifier en une fois — que les tâches
d'avant le 10 septembre ne pouvaient pas faire : les instruments
n'existaient pas.

La coupure vit dans des VUES SQL, et c'est ce choix que ce fichier
protège. Les deux features de données font vingt-sept lectures ; une
seule qui s'adresserait à la table plutôt qu'à la vue ramènerait des
tâches d'avant dans une moyenne, sans rien casser et sans rien dire.
C'est exactement la dérive silencieuse qu'une gate existe pour
attraper.

Les deux versants, comme toujours : la règle mord (une tâche d'avant est
invisible) ET elle ne mord pas trop (une tâche d'après est bien là, avec
ses appels).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from bretzel.components import Query
from examples.atelier.core import db
from examples.atelier.core.era import MILESTONE, is_judgeable
from examples.atelier.features import tasks_data, tools_data

#: Les fichiers où toute lecture de la base a lieu. Les pages ne
#: requêtent jamais — c'est le découpage de l'app, et s'il change, le
#: plancher ci-dessous le dira en ne trouvant plus assez de lectures.
SOURCES = (
    Path(tasks_data.__file__),
    Path(tools_data.__file__),
)

#: ``FROM x`` / ``JOIN x`` — ce qu'une requête lit.
LECTURE = re.compile(r"\b(?:FROM|JOIN)\s+(\w+)")

#: En dessous, la gate ne lit plus ce qu'elle croit lire : soit les
#: requêtes ont déménagé, soit le motif ne les reconnaît plus. Mesuré à
#: 27 le 2026-09-12.
LECTURES_MINIMUM = 20


def toutes_les_lectures() -> list[tuple[str, str]]:
    """``(fichier, table lue)`` pour chaque requête des features data."""
    trouvees = []
    for source in SOURCES:
        texte = source.read_text(encoding="utf-8")
        trouvees += [(source.name, m) for m in LECTURE.findall(texte)]
    return trouvees


def test_le_plancher_de_la_gate():
    """Elle voit bien toutes les requêtes — sinon elle ne prouve rien."""
    lectures = toutes_les_lectures()
    assert len(lectures) >= LECTURES_MINIMUM, lectures


def test_aucune_lecture_ne_court_circuite_le_jalon():
    """Tout passe par une vue. Une table nue rendrait la coupure fausse."""
    nues = [
        (fichier, table)
        for fichier, table in toutes_les_lectures()
        if table in {"tasks", "calls", "sessions"}
    ]
    assert not nues, f"lectures hors vue : {nues}"


@pytest.fixture
def base(tmp_path, monkeypatch):
    """Une base à part, avec une tâche d'avant le jalon et une d'après.

    ⚠️ ``DB_PATH`` est monkeypatché et pas la connexion : c'est
    ``connect()`` qui le lit à chaque appel, donc la vraie base de
    l'atelier n'est jamais touchée par ce test.
    """
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "atelier.db")
    db.init_db(reset=True)
    with db.connect() as conn:
        for session, debut, cycles in (
            ("vieille", "2026-08-01T09:00:00.000Z", 9),
            ("recente", "2026-09-11T09:00:00.000Z", 1),
        ):
            conn.execute(
                "INSERT INTO sessions (id, file, started, ended, tasks) "
                "VALUES (?, ?, ?, ?, 1)",
                (session, f"{session}.jsonl", debut, debut),
            )
            cur = conn.execute(
                "INSERT INTO tasks (session_id, rank, started, request, "
                "calls, cycles, verdict, scope, surface) "
                "VALUES (?, 1, ?, ?, 1, ?, 'corrected', 'app:crm', 1)",
                (session, debut, f"demande {session}", cycles),
            )
            conn.execute(
                "INSERT INTO calls (task_id, rank, at, tool, phase) "
                "VALUES (?, 1, ?, 'Bash', 'writing')",
                (cur.lastrowid, debut),
            )
    return tmp_path


def test_une_tache_d_avant_le_jalon_ne_compte_pas(base):
    """Le versant qui mord — c'est la demande de l'utilisateur."""
    assert tasks_data.summary()["tasks"] == 1
    lignes, total = tasks_data.load_tasks(Query())
    assert total == 1
    assert [ligne["session_id"] for ligne in lignes] == ["recente"]
    # Et la moyenne ne traîne plus les neuf cycles de la vieille.
    assert tasks_data.summary()["mean_cycles"] == 1.0


def test_les_appels_et_les_sessions_suivent_leur_tache(base):
    """La coupure vaut pour les trois vues, pas seulement les tâches.

    Sans ça, l'écran des outils compterait les appels d'une tâche que
    l'écran des tâches n'affiche pas — deux chiffres qui se contredisent
    sur la même page.
    """
    assert sum(p["calls"] for p in tasks_data.by_phase()) == 1
    assert [s["id"] for s in tools_data.session_profile()] == ["recente"]
    assert tasks_data.summary()["sessions"] == 1


def test_la_tache_d_avant_reste_dans_la_table(base):
    """Rien n'est supprimé : c'est la LECTURE qui s'arrête, pas l'aspiration.

    Le versant licite, et il compte : une gate verte parce que la base
    est vide ne dirait rien. Reculer le jalon doit suffire à tout
    revoir, sans ré-aspirer 516 Mo de transcripts.
    """
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM calls").fetchone()[0] == 2


def test_la_porte_python_dit_la_meme_chose_que_les_vues():
    """Deux expressions d'une règle qui doivent rester d'accord."""
    assert not is_judgeable("2026-09-09T23:59:59.000Z")
    assert is_judgeable(f"{MILESTONE}T00:00:00.000Z")
    assert not is_judgeable(None)
