"""Règle : un cast qui efface la PROVENANCE d'une valeur d'état.

Le silence qu'elle ferme, rapporté par l'utilisateur le 2026-08-25
--------------------------------------------------------------------
« Je dois rafraîchir la page pour rafraîchir le stepper. » L'écran
d'import du CRM restait bloqué sur son premier panneau : on cliquait
« Vérifier », l'état serveur passait bien à l'étape suivante, le reste de
la zone se re-rendait — et le stepper, lui, ne bougeait pas. Seul un F5
remettait les deux d'accord. Pire : après « Recommencer », l'écran restait
sur le dernier pas pendant que l'état était revenu à zéro.

Une seule ligne en était la cause ::

    ui.stepper(value=int(draft.etape), clickable=False)
                     ^^^^

Le mécanisme
-------------
Un composant à état client (stepper, tabs, accordion, les cinq pickers,
les quatre overlays…) garde sa valeur courante dans un signal JavaScript,
pas dans le DOM. Le morph d'une zone ``@refreshable`` **préserve
délibérément** l'élément existant — c'est ce qui fait qu'un menu ouvert ou
un champ en cours de saisie survivent à un rafraîchissement déclenché
ailleurs sur la page. Le signal, lui, n'est pas relu.

Le composant doit donc dire « ma valeur vient du serveur, ré-adopte-la
après le morph » — le marqueur ``_serverSync`` (cf.
``components/base/_wiring.server_sync_marker``). Et il ne l'émet **que**
s'il peut voir que la valeur vient du serveur : un champ d'état arrive
ESTAMPILLÉ (``_BoundInt`` / ``_BoundStr``…, posés par
``state/scopes/server._stamp``), un littéral ne l'est pas.

``int(draft.etape)`` rend un entier Python ordinaire. L'estampille est
perdue, le composant conclut « valeur du client », et n'émet rien.

⚠️ **Et ce n'est pas rattrapable à l'exécution.** À ce moment-là le
composant ne voit qu'un ``int``, indiscernable d'un ``value=1``
parfaitement légitime — qui, lui, doit justement NE PAS être ré-adopté,
sinon un rafraîchissement voisin renverrait l'utilisateur là où le serveur
croit qu'il en est. La seule place où l'information existe encore est le
**code source**. D'où cette règle, et pas une garde runtime.

Mesuré au navigateur, la même page avec et sans le cast ::

    apres Avancer      panneau 1        panneau 2
    apres Avancer x2   panneau 1        panneau 3
    apres F5           panneau 3        panneau 3
    apres Recommencer  panneau 3        panneau 1

Ce que la règle couvre, et ce qu'elle laisse
----------------------------------------------
Elle vise les **props à double sens** (``ComponentInfo.two_way``,
30 composants) — la population exacte où un signal client détient la
valeur et peut diverger du serveur. Un cast sur un slot de texte
(``ui.badge(label=str(n))``) est inoffensif : il n'y a pas de signal à
ré-adopter, le morph remplace le nœud.

Elle exige que l'argument soit un **accès d'attribut ou d'indice**
(``draft.etape``, ``prefs["x"]``) — donc plausiblement une lecture
d'état. ``int(3)`` est inutile mais sans conséquence, et une règle qui
signale de l'inoffensif finit par ne plus être lue.

Elle voit **trois** formes depuis le 2026-08-30, pas une seule — le
cast, le ``or`` et la f-string. L'inventaire à jour est dans
:func:`stripping_expr`, qui EST le détecteur ; ce qui suit dit ce qui
reste dehors.

⚠️ **Ce paragraphe a décrit l'inverse jusqu'au 2026-09-01.** Il
énumérait « ce qu'elle NE voit pas : une f-string, une arithmétique, un
``state.x or defaut`` » — écrit avant l'élargissement, et laissé tel
quel après, à cinquante lignes d'un ``stripping_expr`` qui les traite.
C'est la forme de docstring la plus coûteuse de ce dépôt : elle se
contredit elle-même dans le même fichier, et la moitié fausse est celle
qu'on lit en premier.

**Ce qui reste DEHORS**, mesuré et volontaire : l'arithmétique. Ses
trois sites du dépôt portent tous sur des littéraux (``'A' * 200``),
donc inoffensifs. Élargir à « toute expression non triviale » serait
maximal et probablement bruyant.

**Le versant licite est payé** : ``bretzel check examples`` rend 12
constats sur 321 fichiers, dont **zéro** de cette règle — les trois
formes surveillées ne produisent aucun faux positif sur le corpus réel.
"""

from __future__ import annotations

import ast

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding

RULE = "etat-perdu-par-un-cast"

#: Les coercions du langage. Toutes rendent un objet NEUF, donc toutes
#: perdent l'estampille — il n'y a pas d'exception à trier.
_CASTS = frozenset({"int", "str", "float", "bool", "list", "tuple", "set", "dict"})


def _two_way(ui_name: str) -> frozenset[str]:
    """Les props à double sens de ``ui.<ui_name>``, ou l'ensemble vide.

    Lu sur l'introspection plutôt que recopié : la liste est dérivée de
    ``reactive_prop(writes=True)``, donc une prop qui devient bidirection-
    nelle entre ici et le socle ne peut pas sortir de la règle en silence.
    """
    from bretzel.introspect import ComponentInfo, describe_ui_symbol, ui_symbol_names

    if ui_name not in ui_symbol_names():
        return frozenset()
    info = describe_ui_symbol(ui_name)
    if not isinstance(info, ComponentInfo):
        return frozenset()
    return frozenset(info.two_way)


def _reads_state(node: ast.expr) -> bool:
    """``node`` ressemble-t-il à une lecture d'état — ``a.b`` ou ``a["b"]`` ?

    Heuristique assumée, la même que depuis l'origine : c'est ce qui
    empêche ``int(3)`` de compter. Le lint n'a pas le typage, il a la
    forme.
    """
    return isinstance(node, ast.Attribute | ast.Subscript)


def _first_state_read(node: ast.expr) -> ast.expr | None:
    """La première lecture d'état sous ``node``, ou ``None``."""
    return next(
        (sub for sub in ast.walk(node) if _reads_state(sub)),  # type: ignore[misc]
        None,
    )


def stripping_expr(value: ast.expr) -> tuple[str, str] | None:
    """``(forme, source de la lecture)`` si ``value`` efface la provenance.

    Isolé du balayage pour que la preuve de morsure l'attaque directement,
    sur des expressions fabriquées, plutôt que sur un faux dépôt.

    **Trois formes, élargies le 2026-08-30** — le cast n'était que la
    première trouvée, pas la seule qui efface :

    - ``CAST(state.x)`` — rend un ``int`` / ``str`` nu. La forme d'origine,
      quatre sites mesurés, tous corrigés ;
    - ``state.x or defaut`` — **la plus traître**, et c'est pourquoi elle
      entre : ``a or b`` rend l'opérande TELLE QUELLE, donc l'estampille
      survit quand la valeur est vraie et disparaît quand elle est
      fausse. Le composant se resynchronise une fois sur deux, selon la
      donnée — et un banc qui n'essaie que le cas rempli le déclare bon ;
    - ``f"{state.x}"`` — efface toujours, comme le cast. Zéro site mesuré
      aujourd'hui, incluse parce qu'elle est du même ordre et gratuite.

    ⚠️ Ce qui reste DEHORS, et volontairement : l'arithmétique. Balayée
    sur les 18 apps le 2026-08-25, ses trois sites portent tous sur des
    littéraux (``'A' * 200``) — inoffensifs. Élargir à « toute expression
    non triviale » serait maximal et probablement bruyant ; la mesure du
    versant licite est ce qui a trouvé les deux seuls bugs de gate de ce
    dépôt.
    """
    if isinstance(value, ast.Call):
        if not (isinstance(value.func, ast.Name) and value.func.id in _CASTS):
            return None
        if len(value.args) != 1 or value.keywords:
            return None
        if not _reads_state(value.args[0]):
            return None
        return f"{value.func.id}(…)", ast.unparse(value.args[0])

    if isinstance(value, ast.BoolOp):
        lu = _first_state_read(value)
        if lu is None:
            return None
        mot = "or" if isinstance(value.op, ast.Or) else "and"
        return f"… {mot} …", ast.unparse(lu)

    if isinstance(value, ast.JoinedStr):
        lu = _first_state_read(value)
        if lu is None:
            return None
        return 'f"…"', ast.unparse(lu)

    return None


def check(module: Module) -> list[Finding]:
    """Les casts posés sur une prop à double sens."""
    findings: list[Finding] = []
    for node in ast.walk(module.tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "ui"
        ):
            continue
        props = _two_way(func.attr)
        if not props:
            continue
        for keyword in node.keywords:
            if keyword.arg not in props:
                continue
            efface = stripping_expr(keyword.value)
            if efface is None:
                continue
            forme, inner = efface
            # ``or`` n'efface que par INTERMITTENCE : l'opérande est rendue
            # telle quelle, donc l'estampille survit quand la valeur est
            # vraie. C'est ce qui le rend plus dangereux qu'un cast, pas
            # moins — le message doit le dire, sinon on lit « parfois ça
            # marche » comme « ce n'est pas grave ».
            quand = (
                " — et seulement quand la valeur est fausse, donc le "
                "composant se resynchronise une fois sur deux selon la "
                "donnée"
                if forme.endswith("or …") else ""
            )
            findings.append(
                Finding(
                    rule=RULE,
                    path=module.path,
                    line=node.lineno,
                    message=(
                        f"`ui.{func.attr}({keyword.arg}={forme})` : "
                        f"l'expression efface la provenance de `{inner}`{quand}, "
                        f"donc le composant "
                        f"ne saura pas que la valeur vient du serveur et ne la "
                        f"ré-adoptera pas après un rafraîchissement."
                    ),
                    hint=(
                        f"Passe la valeur nue : `{keyword.arg}={inner}`. Si un "
                        f"formatage est nécessaire, il va dans l'état (un "
                        f"validateur, un champ calculé), pas au point d'appel."
                    ),
                )
            )
    return findings
