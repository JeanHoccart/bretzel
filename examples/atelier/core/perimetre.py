"""core/perimetre — logic : sur QUOI une tâche a travaillé.

Feature ``kind="logic"`` : pas d'état, pas de ressource, une question.

Pourquoi c'est la mesure qui manquait
--------------------------------------
La première version jugeait toutes les tâches au même mètre. Signalé par
l'utilisateur le 2026-09-12 : « c'est normal qu'on prenne du temps à
créer/modifier le framework, moi ce que je veux évaluer c'est ta
performance sur les APPS ».

Il a raison, et le mélange rendait le chiffre inutilisable dans les deux
sens : construire une couche du socle demande de lire le socle entier et
de le vérifier souvent — c'est du travail sain qui compte comme de
l'aller-retour. À l'inverse, une app écrite avec le framework ne devrait
presque rien exiger : la surface se DEMANDE (`describe`), le contrat se
DÉCLARE (`Feature`), et le lint juge avant de lancer quoi que ce soit. Si
une tâche d'app coûte quinze cycles, c'est le framework qui ne tient pas
sa promesse — ou moi qui ne m'en sers pas.

C'est cette distinction-là qu'on veut voir, et elle n'existait pas.

Le périmètre d'une tâche
-------------------------
Celui de ses ÉCRITURES, pas de ses lectures : lire le socle pour écrire
une app est normal, et compter les lectures ferait passer toute tâche
d'app pour du travail de framework. Sans écriture, on retombe sur les
lectures — une tâche qui n'a fait que lire a quand même un sujet.

⚠️ Deux choses ne sont PAS un sujet, et les compter comme tel a été
mesuré faux le 2026-09-12 :

- **ce qu'une commande CHERCHE**. Le motif d'un ``grep`` est une
  aiguille, pas une cible : ``grep -rln "examples/ecole" .`` balaie le
  dépôt entier. Sans cette distinction, la tâche qui a SUPPRIMÉ une app
  était rangée DANS cette app — c'est la ligne « non je préfère crm »,
  qui a fait poser la question ;
- **le brouillon**. Écrire un script jetable dans le scratchpad est un
  MOYEN de travailler sur autre chose. Il l'emportait quand même, par
  simple nombre : **178 tâches sur 276** rangées « brouillon » avaient un
  vrai sujet dans leurs propres écritures (79 le socle, 62 les suites,
  26 la doc). Il ne gagne donc plus que s'il est seul — et il reste
  visible dans ce cas, parce qu'une tâche qui n'a touché QUE des
  jetables n'a effectivement pas livré ailleurs.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from bretzel import Feature

FRAMEWORK = "framework"
TESTS = "tests"
DOC = "doc"
BROUILLON = "brouillon"
AUTRE = "autre"

#: Le préfixe d'une app : ``app:crm``, ``app:atelier``. Gardé lisible
#: plutôt que codé, parce qu'il s'affiche tel quel dans un filtre.
APP = "app:"

LIBELLES = {
    FRAMEWORK: "le socle — `bretzel/`",
    TESTS: "les suites et les gates",
    DOC: "la référence et le suivi",
    BROUILLON: "le bac à sable, hors dépôt",
    AUTRE: "non attribué",
}

#: Ce qui suit la racine du dépôt dans un chemin absolu. On coupe DESSUS
#: plutôt que de chercher un segment nommé : le dossier du dépôt s'appelle
#: lui-même ``bretzel``, donc chercher « bretzel » dans un chemin absolu
#: attrape la racine et range toute l'arborescence en framework. Mesuré :
#: la première version rendait 6 728 écritures « framework » sur 5 580
#: appels d'écriture, ce qui était impossible et aurait dû se voir.
RACINE = re.compile(r"^.*?[/\\]bretzel[/\\]", re.IGNORECASE)

#: Un chemin de brouillon : le scratchpad de session, un temporaire. Ils
#: ne sont pas dans le dépôt et ne disent rien du travail livré.
HORS_DEPOT = re.compile(r"(?:^|[/\\])(?:Temp|tmp|scratchpad|AppData)(?:[/\\]|$)",
                        re.IGNORECASE)


def relative(path: str) -> str:
    """Le chemin ramené à la racine du dépôt, séparateurs normalisés."""
    cleaned = path.strip().strip("'\"").replace("\\", "/")
    sans_racine = RACINE.sub("", cleaned.replace("/", "\\")).replace("\\", "/")
    return sans_racine.lstrip("./")


def scope_of(path: str) -> str:
    """Le périmètre d'UN chemin — ``""`` si le chemin ne dit rien.

    La chaîne vide et non ``AUTRE`` : un appel sans chemin ne doit pas
    peser dans le vote du périmètre dominant. Les confondre ferait gagner
    « autre » sur toute tâche qui lance beaucoup de commandes.
    """
    if not path:
        return ""
    if HORS_DEPOT.search(path):
        return BROUILLON
    rel = relative(path)
    if not rel or ("/" not in rel and "." not in rel):
        return ""
    segments = rel.split("/")
    tete = segments[0]
    if tete == "examples" and len(segments) > 1:
        return f"{APP}{segments[1]}"
    if tete == "bretzel":
        return FRAMEWORK
    if tete == "tests":
        return TESTS
    if tete in (".claude", "docs") or rel.endswith(".md"):
        return DOC
    return ""


#: Ce qu'une commande CHERCHE : le nom de l'outil de recherche, ses
#: drapeaux, puis le motif. On coupe le motif — et lui seul, le reste de
#: la commande garde ses vraies cibles (``--include``, le dossier
#: balayé).
AIGUILLE = re.compile(
    r"\b(?:grep|egrep|fgrep|rg|findstr|Select-String)\b"
    r"(?:\s+-{1,2}[\w-]+(?:=\S+)?)*"
    r"\s+(?P<motif>'[^']*'|\"[^\"]*\"|\S+)"
)


def sans_aiguilles(command: str) -> str:
    """La commande sans les motifs de recherche qu'elle porte."""
    return AIGUILLE.sub(
        lambda m: m.group(0)[: m.start("motif") - m.start(0)], command
    )


#: Les chemins qu'une commande cite. Assez large pour attraper un
#: ``sed -n 1,50p examples/crm/main.py`` comme un ``Write`` absolu.
CHEMINS = re.compile(r"[\w./\\:-]*[/\\][\w./\\-]+\.\w+|examples[/\\][\w-]+")


def scopes_in(command: str) -> list[str]:
    """Tous les périmètres qu'une commande touche, doublons compris.

    Les doublons comptent : une commande qui nomme trois fichiers d'app
    pèse plus qu'une qui en nomme un, et c'est ce qu'on veut.
    """
    cible = sans_aiguilles(command)
    return [s for s in (scope_of(m) for m in CHEMINS.findall(cible)) if s]


def dominant(scopes: Iterable[str]) -> str:
    """Le périmètre qui l'emporte — ``AUTRE`` si rien ne se dégage.

    Le plus fréquent, sans seuil : une tâche qui touche le socle ET une
    app est rangée du côté où elle a le plus écrit, et c'est le bon
    arbitrage pour la question posée. La frise, elle, garde le détail.

    ⚠️ Une exception, et une seule : le brouillon ne participe pas au
    vote. C'est un moyen, pas un sujet — un script jetable écrit pour
    mesurer le socle parle du socle. Il ne sort que s'il est le seul
    candidat, et ce cas-là dit quelque chose de vrai.
    """
    compte = Counter(s for s in scopes if s)
    if not compte:
        return AUTRE
    sujets = [(s, n) for s, n in compte.items() if s != BROUILLON]
    if sujets:
        return max(sujets, key=lambda item: item[1])[0]
    return BROUILLON


def is_app(perimetre: str) -> bool:
    """Est-ce une tâche d'APPLICATION ? C'est la question de l'utilisateur."""
    return perimetre.startswith(APP)


def label(perimetre: str) -> str:
    """Le périmètre en toutes lettres — pour une LIGNE, pas une cellule.

    ``le socle — bretzel/``, ``les suites et les gates``. C'est ce qu'on
    veut quand une ligne entière lui est consacrée, comme sur l'écran des
    phases.
    """
    if is_app(perimetre):
        return f"app {perimetre[len(APP):]}"
    return LIBELLES.get(perimetre, perimetre)


def short(perimetre: str) -> str:
    """Le périmètre en un mot — pour une CELLULE.

    ⚠️ Les deux existent parce qu'ils ne servent pas au même endroit, et
    confondre les deux se voit : « le bac à sable, hors dépôt » dans un
    badge de tableau se replie sur deux lignes et rend les rangées
    inégales — mesuré à l'écran, des hauteurs de 50 à 100 px sur la même
    table.
    """
    return perimetre[len(APP):] if is_app(perimetre) else perimetre


feature = Feature(
    name="perimetre",
    kind="logic",
    provides=[scope_of, scopes_in, dominant, is_app, label, short],
)
