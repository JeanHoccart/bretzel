"""core/ingest — job : aspirer les transcripts de session dans la base.

Feature ``kind="job"`` : elle ne rend rien, ne répond à aucune requête, et
tourne HORS d'une requête — à la main
(``py -m examples.atelier.core.ingest``) ou au démarrage de l'app si la
base est vide.

Ce qu'elle lit
--------------
``~/.claude/projects/<projet>/*.jsonl`` : une ligne JSON par événement de
session. Ce qui nous intéresse tient en trois formes :

- un ``user`` porteur d'un ``promptSource`` → une DEMANDE, donc le début
  d'une tâche ;
- un ``assistant`` → ses blocs ``tool_use`` (nom, entrée) et son ``usage``
  (jetons) ;
- un ``user`` porteur de blocs ``tool_result`` → le verdict de chaque
  appel, dont son ``is_error``.

⚠️ Ce qu'elle ne fait PAS, et pourquoi c'est écrit
---------------------------------------------------
Elle ne garde **aucun contenu** : ni le texte des réponses, ni la sortie
des commandes, ni le corps des fichiers écrits. Seulement des noms
d'outils, des horaires, des drapeaux d'erreur et la première ligne de
chaque commande. La question posée est « comment le travail se
déroule », pas « qu'est-ce qui a été dit » — et une base qui recopierait
516 Mo de transcripts serait une seconde copie à tenir à jour, pour
répondre moins bien que l'original.

⚠️ Robustesse : un transcript est un fichier vivant
-----------------------------------------------------
La session EN COURS écrit dedans pendant qu'on le lit. Une ligne
tronquée est donc normale, pas une panne : on la saute et on continue.
Le compte de lignes illisibles est rendu, pour qu'il se voie s'il
grossit au lieu de se taire.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from bretzel import Feature
from examples.atelier.core.db import connect, init_db
from examples.atelier.core.perimetre import dominant, scopes_in
from examples.atelier.core.phases import (
    ECRITURE,
    LECTURE,
    phase_of,
    sequence,
    verdict,
    verification_cycles,
)

#: Où Claude Code range les transcripts. Le nom du dossier est le chemin
#: du projet avec les séparateurs remplacés par des tirets.
TRANSCRIPTS = Path.home() / ".claude" / "projects"

#: La première ligne significative d'une commande, tronquée. Assez pour
#: reconnaître le geste, trop peu pour recopier un transcript.
COMMANDE_MAX = 200

#: Idem pour la demande de l'utilisateur : de quoi reconnaître la tâche
#: dans une liste, pas de quoi la relire.
DEMANDE_MAX = 300

#: Les gestes de MÉTHODE qu'on veut voir, reconnus dans une commande. Ce
#: ne sont pas des outils parmi d'autres : chacun répond à une question
#: posée sur la façon de travailler.
#:
#: - ``surface`` : ai-je DEMANDÉ ce qui existe avant d'écrire un ``ui.*``,
#:   ou l'ai-je inventé ? Cette session même a inventé ``ui.table_header``
#:   et ``ui.table_row`` faute de l'avoir fait — deux composants qui
#:   n'existent pas, et c'est ``check`` qui l'a dit, pas moi ;
#: - ``contrat`` : ai-je fait juger la CARTE d'app — donc les
#:   ``Feature()`` et leurs ``uses=`` ? C'est la question « ``Feature()``
#:   est-il un atout de construction, ou du cosmétique qu'on remplit pour
#:   satisfaire une gate ». Un contrat jamais interrogé est du second.
GESTE_SURFACE = re.compile(r"cli\.main\s+describe\b")
GESTE_CONTRAT = re.compile(r"--deep\b")


def project_dir(repo: Path) -> Path:
    """Le dossier de transcripts d'un dépôt.

    ``C:\\Users\\x\\Desktop\\Jean\\bretzel`` →
    ``C--Users-x-Desktop-Jean-bretzel``. On reproduit la règle plutôt que
    de deviner : chercher « le dossier le plus récent » marcherait
    aujourd'hui et rangerait un jour les mesures d'un autre projet.
    """
    slug = str(repo.resolve()).replace(":", "-").replace("\\", "-").replace("/", "-")
    return TRANSCRIPTS / slug


def events(path: Path) -> Iterator[dict[str, Any]]:
    """Les événements d'un transcript, les lignes illisibles sautées."""
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # Une ligne tronquée par une écriture concurrente. Sauter
                # est juste ; lever ferait échouer l'aspiration de la
                # session en cours à chaque fois.
                continue


def first_line(text: str) -> str:
    """La première ligne non vide, tronquée — le geste, pas son contenu."""
    for raw in text.splitlines():
        cleaned = raw.strip()
        if cleaned and not cleaned.startswith("#"):
            return cleaned[:COMMANDE_MAX]
    return text.strip()[:COMMANDE_MAX]


def command_of(tool: str, payload: Any) -> str:
    """Ce qui a été lancé, EN ENTIER — pour le classement.

    Un ``Bash`` porte sa commande, un ``Read`` son chemin, un ``Grep`` son
    motif. Le reste n'a rien de citable et rend une chaîne vide plutôt
    qu'un ``repr`` de dictionnaire, qui ne se lit pas.

    ⚠️ Non tronqué : c'est :func:`phases.phase_of` qui le lit, et le verbe
    qui décide arrive souvent après un préambule. Le LIBELLÉ affiché,
    lui, passe par :func:`first_line` — deux besoins, deux chaînes.
    """
    if not isinstance(payload, dict):
        return ""
    for key in ("command", "file_path", "pattern", "skill", "path"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def target_of(tool: str, payload: Any) -> str:
    """Ce que l'appel TOUCHE — pour le périmètre, pas pour l'affichage.

    Même règle que celle de :func:`perimetre.sans_aiguilles`, appliquée à
    la forme OUTIL d'une recherche : le ``pattern`` d'un ``Grep`` est une
    aiguille, son ``path`` est la botte de foin. :func:`command_of` rend
    le motif — c'est ce qu'on veut LIRE dans la frise, et exactement ce
    qu'il ne faut pas compter comme périmètre.

    Mesuré le 2026-09-12 : les 205 appels ``Grep`` de la base ne
    pesaient rien du tout dans le vote (leur motif ne ressemble à un
    chemin que par accident), alors que leur ``path`` dit précisément où
    on cherchait.
    """
    if not isinstance(payload, dict):
        return ""
    if tool == "Grep":
        chemin = payload.get("path")
        return chemin if isinstance(chemin, str) else ""
    return command_of(tool, payload)


def text_of(content: Any) -> str:
    """Le texte d'un message, que son contenu soit une chaîne ou des blocs."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    morceaux = [
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return "\n".join(m for m in morceaux if m)


def is_real_prompt(event: dict[str, Any]) -> bool:
    """Est-ce une DEMANDE de l'utilisateur, et pas un résultat d'outil ?

    ⚠️ La distinction est la charnière de tout le découpage. Un ``user``
    du transcript est aussi bien « écris-moi ceci » qu'un ``tool_result``
    renvoyé par le harnais. Confondre les deux découperait une tâche à
    chaque commande lancée, et toutes les mesures de rythme deviendraient
    des mesures de rien.
    """
    if event.get("type") != "user":
        return False
    content = (event.get("message") or {}).get("content")
    if isinstance(content, list) and any(
        isinstance(b, dict) and b.get("type") == "tool_result" for b in content
    ):
        return False
    return bool(text_of(content).strip())


def minutes_between(debut: str | None, fin: str | None) -> float:
    """Les minutes entre deux horodatages ISO — ``0`` si l'un manque."""
    if not debut or not fin:
        return 0.0
    from datetime import datetime

    try:
        a = datetime.fromisoformat(debut.replace("Z", "+00:00"))
        b = datetime.fromisoformat(fin.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    return round(max((b - a).total_seconds(), 0.0) / 60.0, 2)


def methode(appels: list[dict[str, Any]]) -> dict[str, Any]:
    """Ce que le DÉROULÉ d'une tâche dit de la méthode suivie.

    Quatre mesures, et toutes se lisent dans l'ORDRE des appels — c'est
    ce qui les rend utiles plutôt que décoratives :

    - **le périmètre** : celui des ÉCRITURES, pas des lectures. Lire le
      socle pour écrire une app est normal ; compter ces lectures ferait
      passer toute tâche d'app pour du travail de framework, et le
      chiffre demandé serait faux dans les deux sens. L'unité du vote est
      l'APPEL, pas la mention : un même appel qui nomme douze fois la
      même app compte pour une voix. Sans ça, un ``py - <<PY`` qui
      réécrit un paragraphe de CLAUDE.md citant ``examples/ecole`` douze
      fois emportait toute la tâche — mesuré le 2026-09-12 sur celle qui
      a SUPPRIMÉ cette app ;
    - **lu avant d'écrire** : y a-t-il eu au moins une lecture AVANT la
      première écriture ? C'est le temps 1 de la règle des quatre temps,
      et son absence explique la plupart des cycles en trop ;
    - **la surface** : ``describe`` avant la première écriture. Après,
      c'est de la vérification — utile, mais ce n'est plus la même
      question ;
    - **le contrat** : ``check --deep``, qui arbitre la carte d'app.
    """
    premiere_ecriture = next(
        (i for i, a in enumerate(appels) if a["phase"] == ECRITURE), None
    )
    avant = appels if premiere_ecriture is None else appels[:premiere_ecriture]
    ecritures = [s for a in appels if a["phase"] == ECRITURE for s in set(a["touches"])]
    toutes = [s for a in appels for s in set(a["touches"])]
    return {
        "perimetre": dominant(ecritures or toutes),
        "lu_avant": int(any(a["phase"] == LECTURE for a in avant)),
        "surface": int(any(GESTE_SURFACE.search(a["entiere"]) for a in avant)),
        "contrat": int(any(GESTE_CONTRAT.search(a["entiere"]) for a in appels)),
    }


def ingest_file(conn: Any, path: Path) -> dict[str, int]:
    """Aspirer UN transcript. Rend ce qui a été vu, pour le rapport."""
    session_id = path.stem
    conn.execute("DELETE FROM appels WHERE tache_id IN "
                 "(SELECT id FROM taches WHERE session_id = ?)", (session_id,))
    conn.execute("DELETE FROM taches WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    taches: list[dict[str, Any]] = []
    courante: dict[str, Any] | None = None
    # ``tool_use_id`` → l'appel en attente de son verdict. Le résultat
    # arrive dans un message SUIVANT, donc on ne peut pas les apparier au
    # fil de l'eau sans cette table.
    en_vol: dict[str, dict[str, Any]] = {}
    jetons_in = jetons_out = 0
    debut = fin = None

    for event in events(path):
        horaire = event.get("timestamp")
        if horaire:
            debut = debut or horaire
            fin = horaire

        if is_real_prompt(event):
            courante = {
                "ordre": len(taches) + 1,
                "debut": horaire,
                "fin": horaire,
                "demande": text_of((event.get("message") or {}).get("content"))
                .strip()[:DEMANDE_MAX],
                "appels": [],
                "jetons": 0,
            }
            taches.append(courante)
            continue

        message = event.get("message") or {}

        if event.get("type") == "assistant":
            usage = message.get("usage") or {}
            jetons_in += int(usage.get("input_tokens") or 0)
            sortie = int(usage.get("output_tokens") or 0)
            jetons_out += sortie
            if courante is not None:
                courante["jetons"] += sortie
                if horaire:
                    courante["fin"] = horaire
            for block in message.get("content") or []:
                if not (isinstance(block, dict) and block.get("type") == "tool_use"):
                    continue
                if courante is None:
                    continue
                outil = block.get("name") or "?"
                entiere = command_of(outil, block.get("input"))
                touches = scopes_in(target_of(outil, block.get("input")))
                appel = {
                    "horaire": horaire,
                    "outil": outil,
                    "phase": phase_of(outil, entiere),
                    "commande": first_line(entiere),
                    "erreur": 0,
                    "detail": "",
                    "cible": dominant(touches),
                    "touches": touches,
                    "entiere": entiere,
                }
                courante["appels"].append(appel)
                identifiant = block.get("id")
                if identifiant:
                    en_vol[identifiant] = appel
            continue

        # Un résultat d'outil : il porte le verdict de l'appel.
        for block in message.get("content") or []:
            if not (isinstance(block, dict) and block.get("type") == "tool_result"):
                continue
            appel = en_vol.pop(block.get("tool_use_id") or "", None)
            if appel is None or not block.get("is_error"):
                continue
            appel["erreur"] = 1
            appel["detail"] = first_line(text_of(block.get("content")))
        if courante is not None and horaire:
            courante["fin"] = horaire

    total_appels = total_erreurs = echanges = 0
    for tache in taches:
        # ⚠️ Un tour qui n'a déclenché AUCUN outil n'est pas une tâche :
        # c'est « ok », « vas-y », ou une question à laquelle on répond
        # de mémoire. Les garder faisait 345 lignes sur 1 857 à zéro
        # cycle et zéro appel, qui tiraient toutes les moyennes vers le
        # bas sans décrire le moindre travail. On les COMPTE — combien
        # d'échanges il a fallu est une information — sans en faire des
        # tâches.
        if not tache["appels"]:
            echanges += 1
            continue
        suite = [a["phase"] for a in tache["appels"]]
        erreurs = sum(a["erreur"] for a in tache["appels"])
        cycles = verification_cycles(suite)
        mesures = methode(tache["appels"])
        total_appels += len(tache["appels"])
        total_erreurs += erreurs
        # Le temps de TRAVAIL : du premier appel au dernier. Le temps
        # d'horloge depuis la demande incluait l'absence de
        # l'utilisateur.
        horaires = [a["horaire"] for a in tache["appels"] if a["horaire"]]
        travail = minutes_between(horaires[0], horaires[-1]) if horaires else 0.0
        cursor = conn.execute(
            "INSERT INTO taches (session_id, ordre, debut, minutes, demande, "
            "appels, erreurs, cycles, frise, verdict, jetons, perimetre, "
            "lu_avant, surface, contrat) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id, tache["ordre"], tache["debut"], travail,
                tache["demande"], len(tache["appels"]), erreurs, cycles,
                sequence(suite), verdict(cycles, erreurs),
                tache["jetons"], mesures["perimetre"], mesures["lu_avant"],
                mesures["surface"], mesures["contrat"],
            ),
        )
        tache_id = cursor.lastrowid
        conn.executemany(
            "INSERT INTO appels (tache_id, ordre, horaire, outil, phase, "
            "commande, erreur, detail, cible) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (tache_id, i + 1, a["horaire"], a["outil"], a["phase"],
                 a["commande"], a["erreur"], a["detail"], a["cible"])
                for i, a in enumerate(tache["appels"])
            ],
        )

    conn.execute(
        "INSERT INTO sessions (id, fichier, debut, fin, minutes, taches, "
        "echanges, appels, erreurs, jetons_in, jetons_out) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (session_id, path.name, debut, fin, minutes_between(debut, fin),
         len(taches) - echanges, echanges, total_appels, total_erreurs,
         jetons_in, jetons_out),
    )
    return {
        "taches": len(taches) - echanges,
        "echanges": echanges,
        "appels": total_appels,
        "erreurs": total_erreurs,
    }


def ingest_all(repo: Path | None = None, *, reset: bool = True) -> dict[str, int]:
    """Aspirer tous les transcripts du dépôt. Rend le total vu."""
    repo = repo or Path(__file__).resolve().parents[3]
    source = project_dir(repo)
    init_db(reset=reset)
    total = {"sessions": 0, "taches": 0, "echanges": 0, "appels": 0,
             "erreurs": 0}
    if not source.is_dir():
        return total
    with connect() as conn:
        for path in sorted(source.glob("*.jsonl")):
            vu = ingest_file(conn, path)
            total["sessions"] += 1
            for key in ("taches", "echanges", "appels", "erreurs"):
                total[key] += vu[key]
    return total


def main() -> int:
    """``py -m examples.atelier.core.ingest``."""
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    total = ingest_all()
    print(
        f"{total['sessions']} sessions, {total['taches']} tâches, "
        f"{total['appels']} appels, {total['erreurs']} erreurs "
        f"({total['echanges']} échanges sans outil, écartés)."
    )
    return 0


feature = Feature(
    name="ingest",
    kind="job",
    uses=["db", "phases", "perimetre"],
    provides=[ingest_all, ingest_file, methode],
)


if __name__ == "__main__":
    raise SystemExit(main())
