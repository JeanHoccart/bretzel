"""Gate : un champ que le framework a NOMMÉ pour l'URL le dit dans sa fiche.

Le défaut qu'elle ferme
-----------------------
``class Issues(DatatableState, addressable=True)`` publie cinq
paramètres — ``?tri=&sens=&p=&taille=&q=`` — et **aucun n'est écrit dans
la sous-classe**. Les noms vivent sur les champs du parent
(``field(default="", url="tri")``, ``state/datatable/state.py``), un
fichier qu'un auteur d'app n'a aucune raison d'ouvrir.

Mesuré le 2026-09-06 : la question a été posée, et y répondre a demandé
de lire la source. ``describe`` — l'outil dont c'est exactement le
travail — n'en disait pas un mot : zéro occurrence de ``url`` dans tout
``bretzel/introspect/``.

Ce qu'elle vérifie, et dans quel sens
--------------------------------------
La **source fait foi** : tout ``field(url="…")` écrit dans le framework
doit se retrouver dans la fiche de sa classe. Le sens inverse
(« la fiche n'invente rien ») est porté par la mutation, où un champ
sans ``url=`` doit rester ABSENT — c'est cette moitié-là qui garantit ce
que la fiche promet au lecteur : *un champ absent de cette ligne ne part
jamais dans l'URL*. ``filters`` en dépend, et c'est la décision du
2026-08-29 (un filtre porte la donnée la plus susceptible d'être
personnelle, et l'URL part dans l'historique, les logs et le
``Referer``).

⚠️ Elle lit le MODÈLE (``describe_state``) pour le corpus réel et le
TEXTE (l'émetteur) pour la mutation. La raison est bête et vaut d'être
sue : la seule classe du framework qui porte des ``url=`` est
``DatatableState``, et ``describe DatatableState`` n'a pas de fiche —
elle s'exporte par ``bretzel.components``, un paquet sans table de
classement (cf. ``test_a_public_name_is_never_reported_missing``).
"""

from __future__ import annotations

import ast
import functools

from bretzel.introspect.emit.text import _state_url_lines
from bretzel.introspect.state import describe_state
from tests.consistency._discovery import PACKAGE_DIR, PACKAGE_FLOOR, parsed_sources


@functools.cache
def url_named_in_sources() -> set[tuple[str, str, str]]:
    """``(classe, champ, nom d'URL)`` lus dans les sources du framework.

    Le nommage est un ``field(url="…")`` et rien d'autre : c'est la
    moitié « nommer » de la déclaration, celle qui vit dans le
    framework. La moitié « allumer » (``addressable=True``) appartient
    aux apps, donc elle n'est pas balayée ici.

    Le pré-filtre textuel n'est pas une micro-optimisation gratuite :
    marcher l'AST des 431 fichiers coûte 470 ms, et les deux tests d'ici
    appellent cette fonction — mesuré, ~940 ms sur une suite rapide qui
    en fait 150 000. Dix-huit fichiers portent la chaîne, et le résultat
    est identique (vérifié) : le texte ne peut pas cacher un ``url=``
    que l'AST verrait.
    """
    found: set[tuple[str, str, str]] = set()
    for source in parsed_sources(PACKAGE_DIR, floor=PACKAGE_FLOOR):
        if "url=" not in source.text:
            continue
        for klass in ast.walk(source.tree):
            if not isinstance(klass, ast.ClassDef):
                continue
            for node in klass.body:
                if not isinstance(node, ast.AnnAssign) or node.value is None:
                    continue
                call = node.value
                if not isinstance(call, ast.Call):
                    continue
                if getattr(call.func, "id", None) != "field":
                    continue
                for kw in call.keywords:
                    if kw.arg == "url" and isinstance(kw.value, ast.Constant):
                        found.add((klass.name, node.target.id, kw.value.value))
    return found


def state_classes() -> dict[str, type]:
    """Les classes d'état vivantes, par nom — toute la descendance.

    ``import bretzel`` monte la surface publique, donc les états que le
    framework possède sont construits. Une classe trouvée dans les
    sources mais absente d'ici fait rougir : c'est le lien qui empêche
    la gate d'affirmer sur une énumération vide.
    """
    import bretzel  # noqa: F401  — construit les classes avant de les lire
    from bretzel.state import ClientState, ServerState

    def descendants(cls: type) -> list[type]:
        return [cls, *(d for sub in cls.__subclasses__() for d in descendants(sub))]

    # ⚠️ Filtré au FRAMEWORK, et la table est indexée par nom nu : sans
    # ce filtre, un état d'``examples/`` ou d'un autre test portant le
    # même nom de classe répondrait à sa place. Les homonymes existent
    # dans ce dépôt (``EmptyState``, ``FilterState``…), et sous ``-n 4``
    # le gagnant dépend de ce que le worker a importé — la dépendance à
    # l'ordre que ce répertoire a déjà payée une fois.
    return {
        cls.__name__: cls
        for base in (ServerState, ClientState)
        for cls in descendants(base)
        if cls.__module__.startswith("bretzel.")
    }


def fields_missing_from_their_fiche() -> list[str]:
    found = url_named_in_sources()
    classes = state_classes()
    missing: list[str] = []
    for class_name, champ, param in sorted(found):
        cls = classes.get(class_name)
        if cls is None:
            missing.append(f"{class_name} (classe introuvable à l'exécution)")
            continue
        if (champ, param) not in describe_state(cls).url_named:
            missing.append(f"{class_name}.{champ} → {param}")
    return missing


def test_the_sweep_reads_something() -> None:
    """Plancher — et il est ANCRÉ sur la découverte, pas sur un recompte.

    Cinq champs nommés le 2026-09-06, tous sur ``DatatableState``. Le
    seuil borne, il ne fige pas : un sixième champ nommé ne doit pas
    faire rougir, une lecture débranchée si.
    """
    assert len(url_named_in_sources()) >= 5, (
        "aucun champ ne porte plus de ``field(url=…)`` — soit le nommage "
        "a changé de forme, soit la lecture AST est cassée. Dans les deux "
        "cas cette gate n'affirme plus rien."
    )


def test_every_named_field_appears_in_its_state_fiche() -> None:
    assert not fields_missing_from_their_fiche(), (
        f"ces champs portent un nom d'URL que leur fiche tait : "
        f"{fields_missing_from_their_fiche()}. Un lecteur ne peut alors "
        f"le trouver qu'en ouvrant la source de la classe PARENTE."
    )


def test_the_fiche_catches_a_named_field_and_spares_an_unnamed_one() -> None:
    """La mutation, dans les deux sens — sur le TEXTE, pas le modèle.

    Le versant qui épargne est celui qui compte : c'est lui qui prouve la
    phrase que la fiche imprime (« un champ absent de cette ligne ne part
    JAMAIS dans l'URL »). Sans lui, un émetteur qui listerait tous les
    champs passerait le premier versant sans rien dire de faux, et
    mentirait sur ``filters``.
    """
    from bretzel.state import PageState, field

    class Nomme(PageState):
        tri: str = field(default="", url="tri")
        secret: str = field(default="")

    ligne = "\n".join(_state_url_lines(describe_state(Nomme)))
    assert "tri→tri" in ligne
    assert "secret" not in ligne
    assert "éteint" in ligne, "nommé sans ``addressable=True`` = éteint"

    class Publie(PageState, addressable=True):
        tri: str = field(default="", url="tri")
        secret: str = field(default="")

    publiee = "\n".join(_state_url_lines(describe_state(Publie)))
    assert "tri→tri" in publiee and "éteint" not in publiee
    assert "secret" not in publiee

    class Muet(PageState):
        rien: str = field(default="")

    assert _state_url_lines(describe_state(Muet)) == [], (
        "un état sans adressage n'écrit pas de ligne — un « Adressable — » "
        "se lirait comme une lecture ratée."
    )
