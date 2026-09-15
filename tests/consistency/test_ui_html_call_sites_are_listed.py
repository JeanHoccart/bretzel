"""Gate : les appels à ``ui.html`` du dépôt sont une liste FERMÉE.

``ui.html`` injecte du balisage verbatim — c'est un puits à XSS, et son
nœud sous-jacent le dit depuis toujours (``core/tree.py`` :
« every occurrence is a candidate XSS sink and **should be auditable** »).
Cette phrase n'était gardée par rien tant que le nœud restait interne ;
en ouvrant la porte au code applicatif, il fallait la rendre vraie.

Le choix de conception qu'elle rend possible : le composant s'appelle
``ui.html`` et pas ``ui.raw_html``. Un nom effrayant n'avertit qu'une
personne, une fois, au moment où elle l'écrit — et il ferait de ce
composant la seule primitive de contenu nommée d'après son risque plutôt
que d'après ce qu'elle affiche (``ui.text``, ``ui.markdown``,
``ui.code``). C'est cette gate qui avertit, à chaque ajout, pour
toujours.

Ce qu'elle fait : figer le couple (fichier, nombre d'appels). Ajouter un
``ui.html`` quelque part la fait rougir, ce qui force la question à être
posée — « pourquoi pas un composant ? », « le contenu est-il littéral ou
assaini ? » — plutôt que subie. Elle ne juge pas le code : elle rend le
choix visible.

L'égalité est stricte dans les deux sens. Retirer un usage sans retirer
son entrée rougit aussi, sinon la liste pourrit et finit par autoriser
plus que la réalité — le défaut même qu'elle corrige. Même contrat que
``test_raw_htmx_stays_in_the_allowlist``, dont elle copie la forme.
"""

from __future__ import annotations

import ast
import functools
import re

from tests.consistency._discovery import (
    EXAMPLES_FLOOR,
    PACKAGE_FLOOR,
    REPO_ROOT,
    parsed_sources,
)

#: Preuve de morsure : contrôle POSITIF — le composant gardé existe et le balayage voit
#: des fichiers.
MUTATION_PROOF = "test_the_sweep_finds_the_component_it_guards"

#: Les racines balayées. ``bretzel/`` est inclus À DESSEIN : un composant
#: du framework qui appellerait ``ui.html`` se tromperait de niveau — il a
#: le nœud ``core.tree.Html`` sous la main, sans passer par la surface
#: publique. Zéro appel attendu là-bas, et c'est une information.
_ROOTS = ("bretzel", "examples")

#: Le plancher de chaque racine — porté par la primitive, pas réécrit.
_ROOT_FLOORS = {"bretzel": PACKAGE_FLOOR, "examples": EXAMPLES_FLOOR}

#: État du 2026-08-14 : fichier (relatif à la racine) → nombre d'appels.
#:
#: Le compte plutôt qu'un simple booléen de présence : sans lui, une
#: deuxième injection dans un fichier déjà listé passerait inaperçue,
#: alors que c'est exactement le glissement à surveiller.
_ALLOWED: dict[str, int] = {
    # Le banc du composant. Tous les contenus sont des littéraux écrits à
    # la main (ou des constantes de ce module) — sauf UN, la prévisualisation
    # du panneau serveur, qui injecte ce que l'utilisateur tape dans le
    # champ. C'est assumé et c'est l'objet de la page : elle démontre
    # précisément le pouvoir qu'on documente. Aucune autre page ne doit
    # copier ce geste.
    #
    # 15 → 13 le 2026-08-14 : deux démos (vidéo, audio, iframe) ont été
    # retirées quand ui.video / ui.audio / ui.iframe ont été livrés. C'est
    # le cas que cette gate ne voit PAS toute seule, et il faut le savoir :
    # elle force la question à l'AJOUT d'un appel, jamais quand un appel
    # devient obsolète parce qu'un composant typé le couvre désormais.
    # Baisser ce nombre est un bon signe, pas une régression.
    #
    # 13 → 16 le 2026-08-30 : la carte *A11y*, qui manquait. Les trois
    # appus sont des littéraux écrits ici, jamais une valeur reçue —
    # deux tableaux (l'un sans structure, l'autre avec ``<th scope>`` et
    # une légende) pour montrer que le framework ne répare rien de ce
    # qu'on lui donne, et un ``tag="ul"`` autour de ``<li>`` pour montrer
    # l'enveloppe qui remplace le parent au lieu de s'y intercaler.
    "examples/playground/features/html.py": 16,
}


#: Préfiltre. Le substrat ``"html"`` seul est BEAUCOUP trop large — il
#: apparaît dans un dixième du Python du dépôt (docstrings,
#: ``serialize_html``, ``text/html``…), ce qui faisait AST-parser 110
#: fichiers pour en trouver 1. Mesuré : 455 ms → 73 ms, résultat
#: identique.
#:
#: Le motif tolère un blanc entre le point et le nom, parce que le
#: prédicat AST plus bas matche n'importe quel ``ast.Attribute`` nommé
#: ``html`` — or un appel coupé en deux lignes après le point est du
#: Python légal qu'un substrat nu raterait. On resserre donc le parse
#: SANS ajouter de moyen d'aveugler la gate, ce que son plancher nomme
#: précisément comme le risque à garder.
_CALL_RX = re.compile(r"\.\s*html\b")


@functools.lru_cache(maxsize=1)
def _call_sites() -> dict[str, int]:
    """``{chemin relatif: nombre d'appels à ui.html}``.

    On lit l'AST et pas le texte : ce fichier-ci, les docstrings du
    composant et sa doc parlent tous de ``ui.html`` en prose. Les compter
    comme des appels rendrait la gate ininterprétable — c'est la majorité
    des occurrences textuelles.

    ``utf-8-sig`` + remontée des illisibles : un ``except: continue``
    transformerait la gate en gate partielle sans que personne ne
    l'apprenne (``bretzel/render/__init__.py`` porte un BOM, cf.
    ``.claude/work/todo.md``).
    """
    found: dict[str, int] = {}
    for root in _ROOTS:
        for source in parsed_sources(REPO_ROOT / root, floor=_ROOT_FLOORS[root]):
            path, text, tree = source.path, source.text, source.tree
            if not _CALL_RX.search(text):
                continue
            count = 0
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                # ``ui.html(...)`` — un attribut ``html`` sur un nom
                # quelconque. On ne se fie pas au nom du receveur : le
                # namespace est parfois réimporté sous un alias.
                if isinstance(func, ast.Attribute) and func.attr == "html":
                    count += 1
            if count:
                found[path.relative_to(REPO_ROOT).as_posix()] = count
    return found


def test_ui_html_call_sites_match_the_list() -> None:
    found = _call_sites()

    # ``found == _ALLOWED`` dit exactement ce que disaient les deux
    # compréhensions d'inclusion qui vivaient ici — et que le message
    # d'erreur n'utilisait même pas, puisqu'il imprime les deux dicts.
    assert found == _ALLOWED, (
        "Les appels à ui.html ont bougé.\n\n"
        f"  Trouvés  : {found}\n"
        f"  Attendus : {_ALLOWED}\n\n"
        "ui.html injecte du balisage VERBATIM — chaque appel est un puits "
        "à XSS potentiel, et c'est cette liste qui les rend auditables "
        "(le nom du composant, lui, ne prévient personne).\n\n"
        "Si tu ajoutes un appel : le contenu est-il un littéral que tu as "
        "écrit, ou une valeur passée par un assainisseur juste avant ? "
        "S'il vient d'un utilisateur, c'est ui.markdown qu'il te faut (il "
        "échappe le HTML embarqué). Si la réponse tient, inscris la ligne "
        "ici AVEC sa raison.\n\n"
        "Si tu en retires un : retire aussi son entrée, sinon la liste "
        "autorise plus que la réalité."
    )


def test_the_sweep_finds_the_component_it_guards() -> None:
    """Plancher de non-vacuité — ancré sur la DÉCOUVERTE.

    L'assertion du dessus compare deux dicts : elle passerait tout aussi
    bien si le balayage ne trouvait plus rien ET que la liste était vide.
    Deux façons d'y arriver sans le vouloir — ``ui.html`` renommé, ou le
    préfiltre ``"html" not in text`` rendu faux par un renommage. On
    vérifie donc que la chose gardée existe toujours, et que le balayage
    voit bien des fichiers.
    """
    from bretzel.components import ui

    assert hasattr(ui, "html"), (
        "``ui.html`` n'existe plus — soit il a été renommé (et cette gate "
        "garde un fantôme), soit il a été retiré (et elle doit l'être "
        "aussi). Dans les deux cas elle ne garde plus rien."
    )
    scanned = sum(
        len(parsed_sources(REPO_ROOT / root, floor=_ROOT_FLOORS[root]))
        for root in _ROOTS
    )
    assert scanned > 200, (
        f"Le balayage ne voit que {scanned} fichiers Python sous {_ROOTS} — "
        "les racines ont bougé, et la liste ci-dessus ne prouve plus rien."
    )
