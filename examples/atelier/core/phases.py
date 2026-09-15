"""core/phases — logic : à quelle PHASE de travail appartient un appel.

Feature ``kind="logic"`` : elle ne rend rien, ne touche aucune ressource,
et ne porte aucun état. Elle répond à une question et une seule — « cet
appel d'outil, c'est de la lecture, de l'écriture, de la vérification ou
de la livraison ? » — et c'est de cette réponse que tout le reste de
l'atelier découle.

Pourquoi les phases sont le cœur
---------------------------------
Compter les appels dit qu'une tâche a coûté cher. Il ne dit pas POURQUOI.
La suite des phases, elle, se lit d'un coup d'œil :

    LLLL ÉÉÉÉ VV ÉÉ VV                    → sain
    L É V É V É V É V É V É V É V         → l'aller-retour incessant

Les deux tâches peuvent avoir le même nombre d'appels. Seule la seconde
montre quelqu'un qui code par tâtonnement, écrit trois lignes, relance la
suite, relit le rouge, récrit trois lignes. C'est exactement ce que
l'utilisateur a demandé de voir.

⚠️ Le classement est HEURISTIQUE, et il le reste
------------------------------------------------
Un appel ``Bash`` peut tout faire : ``cat`` lit, ``pytest`` vérifie, un
``python - <<EOF`` écrit un fichier. On lit donc la COMMANDE, pas
seulement le nom de l'outil — et il restera des cas ambigus, rangés en
``AUTRE`` plutôt que devinés. Une phase inventée ferait mentir la frise,
et la frise est tout ce qu'on regarde.

Le compte de `AUTRE` est affiché : s'il grossit, c'est l'heuristique qu'il
faut corriger, pas la mesure qu'il faut croire.
"""

from __future__ import annotations

import re

from bretzel import Feature

#: Les quatre phases, dans l'ordre où une tâche saine les traverse. La
#: cinquième — ``AUTRE`` — n'est pas une phase de travail : c'est l'aveu
#: que l'heuristique n'a pas su.
LECTURE = "lecture"
ECRITURE = "ecriture"
VERIFICATION = "verification"
LIVRAISON = "livraison"
AUTRE = "autre"

PHASES = (LECTURE, ECRITURE, VERIFICATION, LIVRAISON, AUTRE)

#: Ce que chaque phase veut dire, en une ligne — pour l'écran, pas pour le
#: code. Les libellés vivent ici parce que c'est ici qu'on les décide.
LIBELLES = {
    LECTURE: "lire et comprendre",
    ECRITURE: "produire du code",
    VERIFICATION: "juger ce qui est écrit",
    LIVRAISON: "commiter",
    AUTRE: "non classé — l'heuristique n'a pas su",
}

#: La lettre de chaque phase, et sa couleur. Les deux vivent ICI parce
#: qu'elles sont lues à trois endroits — la frise de la liste, celle de
#: la fiche, et la légende. Trois copies finiraient par ne plus dire la
#: même chose, et une légende qui ment sur ses propres couleurs est pire
#: qu'une absence de légende.
LETTRES = {
    LECTURE: "L", ECRITURE: "É", VERIFICATION: "V",
    LIVRAISON: "C", AUTRE: "·",
}

COULEURS = {
    LECTURE: "info",
    ECRITURE: "primary",
    VERIFICATION: "warning",
    LIVRAISON: "success",
    AUTRE: "muted",
}

#: ``L`` → ``info``. La frise est stockée en LETTRES — c'est une chaîne,
#: pas une liste de phases — donc la peindre demande le chemin retour.
COULEUR_PAR_LETTRE = {
    lettre: COULEURS[phase] for phase, lettre in LETTRES.items()
}

#: Les outils dont le NOM suffit à trancher. Les autres passent par la
#: lecture de leur commande.
PAR_OUTIL = {
    "Read": LECTURE,
    "Grep": LECTURE,
    "Glob": LECTURE,
    "NotebookRead": LECTURE,
    "WebFetch": LECTURE,
    "WebSearch": LECTURE,
    "Write": ECRITURE,
    "Edit": ECRITURE,
    "NotebookEdit": ECRITURE,
}

#: Ce qui PRÉCÈDE le vrai verbe et le cache : un `cd` de positionnement,
#: un `export` d'encodage, une variable de chemin. Mesuré à la première
#: aspiration : **24 % des appels finissaient en « non classé »**, presque
#: tous pour cette raison — la commande disait
#: ``export PYTHONIOENCODING=utf-8; py -m pytest …`` et l'heuristique
#: lisait le ``export``. Un quart d'appels non classés rend la frise
#: incroyable, donc inutile.
PREAMBULE = re.compile(
    r"^\s*(?:"
    r"cd\s+[^&;|]+(?:&&|;)"          # cd … && …
    r"|export\s+\w+=[^;]*;"          # export VAR=… ;
    r"|\w+=(?:\"[^\"]*\"|'[^']*'|[^\s;]+)\s*(?:;|&&)?"  # VAR=… ;
    r")\s*"
)


def strip_prelude(command: str) -> str:
    """La commande sans ce qui la précède — appliqué jusqu'à point fixe.

    Une commande de ce dépôt en empile souvent deux (``cd`` puis
    ``export``), donc un seul passage ne suffit pas.
    """
    previous = None
    while previous != command:
        previous = command
        command = PREAMBULE.sub("", command, count=1)
    return command


#: ⚠️ L'ORDRE COMPTE : `git commit` gagne sur `git add`, et `pytest` sur
#: un `cd` qui le précède. On teste donc de la phase la plus spécifique à
#: la plus générale, et le premier motif qui mord décide.
#:
#: Chaque motif est ancré sur un MOT (``\b``) : sans ça, `check` mordrait
#: sur `checkout` et rangerait un `git checkout` en vérification.
MOTIFS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (LIVRAISON, re.compile(r"\bgit\s+(commit|push|tag|revert)\b")),
    (
        VERIFICATION,
        re.compile(
            r"\bpytest\b|\bruff\s+check\b|\blint-imports\b|\bimportlinter\b"
            r"|\bmypy\b|cli\.main\s+check\b|cli\.main\s+probe\b"
            r"|\bprobe_\w+\.py\b"
        ),
    ),
    # `describe` est de la LECTURE et non de la vérification : il répond à
    # « qu'est-ce qui existe », pas à « est-ce que c'est juste ». Les
    # ranger ensemble effacerait justement la distinction qu'on mesure.
    (LECTURE, re.compile(r"cli\.main\s+describe\b|\bgit\s+(log|show|diff|status)\b")),
    (
        LECTURE,
        re.compile(
            r"^\s*(cat|sed|head|tail|less|grep|rg|ls|find|wc|du|tree)\b"
            r"|\|\s*(grep|rg|head|tail|wc)\b"
        ),
    ),
    # Un heredoc Python, un `>` ou un `tee` : c'est une ÉCRITURE de
    # fichier déguisée en commande shell. Le mode d'échec sans cette
    # ligne est silencieux — toute la production passerait en `AUTRE`.
    (ECRITURE, re.compile(r"<<\s*'?\w+'?\s*$|>\s*[\w./-]+\.\w+|\btee\b|\bsed\s+-i\b")),
    (LIVRAISON, re.compile(r"\bgit\s+(add|mv|rm|stash)\b")),
    # ⚠️ Un `py -c` est ambigu par nature — il lit aussi bien qu'il écrit.
    # On tranche sur ce qu'il FAIT : une écriture de fichier se voit
    # (`write_text`, `open(..., "w")`), tout le reste est de
    # l'inspection. Deviner « lecture » sans cette distinction rangerait
    # en lecture les scripts d'édition, qui sont la façon dont ce dépôt
    # écrit la plupart de ses fichiers.
    (ECRITURE, re.compile(r"\bwrite_text\b|\bopen\([^)]*[\"']w[\"']|\bdump\(")),
    (LECTURE, re.compile(r"\bpy(thon)?\b\s+-c\b|\bpython\b\s+-\s*$|\bread_text\b")),
)


def phase_of(tool: str, command: str = "") -> str:
    """La phase d'un appel — son outil, et sa commande si c'est un shell.

    ``command`` est la commande COMPLÈTE, pas son libellé : le verbe qui
    décide arrive souvent après un préambule, et parfois à la deuxième
    ligne d'une chaîne. Le libellé court, lui, sert à l'affichage et se
    calcule ailleurs.
    """
    direct = PAR_OUTIL.get(tool)
    if direct is not None:
        return direct
    if not command:
        return AUTRE
    # La commande ENTIÈRE, pas sa première ligne : le verbe qui compte
    # arrive souvent après un `cd` ou un `export`, et parfois à la
    # deuxième ligne d'une chaîne.
    utile = strip_prelude(" ".join(command.split()))
    for phase, motif in MOTIFS:
        if motif.search(utile):
            return phase
    return AUTRE


def sequence(phases: list[str]) -> str:
    """La frise, compressée : les répétitions se réduisent à une lettre.

    ``[lecture, lecture, lecture, ecriture]`` → ``"L É"``. Ce qu'on veut
    voir n'est pas combien d'appels, c'est combien de FOIS on change de
    phase — et une frise de 600 lettres ne se lit plus.
    """
    out: list[str] = []
    for phase in phases:
        lettre = LETTRES.get(phase, "·")
        if not out or out[-1] != lettre:
            out.append(lettre)
    return " ".join(out)


def verification_cycles(phases: list[str]) -> int:
    """Combien de FOIS on est entré en vérification dans cette tâche.

    C'est la mesure de la règle que l'utilisateur a posée : on code tout,
    on vérifie, on corrige, on vérifie une dernière fois. **Deux cycles,
    pas plus.** Trois veut dire qu'on a recommencé ; dix, qu'on a codé
    par tâtonnement en se servant de la suite de tests comme d'un
    compilateur.

    Compté sur les BLOCS et pas sur les appels : lancer trois suites de
    suite est UN cycle de vérification, pas trois.
    """
    cycles = 0
    dedans = False
    for phase in phases:
        if phase == VERIFICATION and not dedans:
            cycles += 1
            dedans = True
        elif phase in (ECRITURE, LECTURE):
            dedans = False
    return cycles


#: Le plafond que l'utilisateur a posé le 2026-09-12 : « tu codes tout, tu
#: fais le check, tu corriges, et un seul dernier — deux checks globaux,
#: pas plus, pas d'aller-retour incessant ». Il vit ici plutôt que dans
#: l'écran : c'est une règle du dépôt, pas un détail d'affichage.
CYCLES_MAX = 2


def verdict(cycles: int, erreurs: int) -> str:
    """Le jugement d'une tâche, en un mot — ce que la liste trie dessus."""
    if cycles > CYCLES_MAX:
        return "aller-retour"
    if erreurs:
        return "corrigé"
    return "du premier coup"


feature = Feature(
    name="phases",
    kind="logic",
    provides=[phase_of, sequence, verification_cycles, verdict,
              strip_prelude],
)
