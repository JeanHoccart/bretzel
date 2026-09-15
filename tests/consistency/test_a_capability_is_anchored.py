"""Gate : la liste des capacités est ANCRÉE dans le code, ou elle ment.

Ce qu'elle garde
-----------------
``bretzel/introspect/capabilities.py`` est une liste **écrite à la
main** — la seule du paquet ``introspect``, et c'est assumé : une
capacité traverse cinq dossiers, donc aucun lecteur d'arbre ne peut la
déduire.

C'est aussi exactement la forme qui a fait supprimer le skill
``bretzel-api`` le 2026-08-01 : un catalogue recopié qui nommait deux
composants inexistants et en omettait six. La différence n'est pas le
soin qu'on y met — c'est l'ancrage.

Les quatre choses vérifiées ici
--------------------------------
1. **Les symboles d'entrée existent.** Import + ``getattr``. Un symbole
   renommé fait rougir la capacité qui le cite, et pas une autre.
2. **L'extrait parse.** Un exemple qui ne compile pas est pire que pas
   d'exemple : on le recopie.
3. **L'extrait EMPLOIE ce qu'il annonce.** Sans ça, une capacité peut
   nommer ``bretzel.download`` et montrer du code qui parle d'autre
   chose — la dérive la plus vicieuse, parce que les deux moitiés sont
   vraies séparément.
4. **Aucun symbole d'entrée n'est revendiqué deux fois.** C'est le
   détecteur de doublon : deux capacités qui entrent par le même
   symbole sont la même capacité, écrite deux fois.
5. **Le chapitre déclaré est une route qui EXISTE**, et le nombre de
   capacités sans chapitre ne remonte jamais.

La règle qu'elle fait respecter : un index LISTE, un chapitre ENSEIGNE
--------------------------------------------------------------------
Posée le 2026-09-03. Il y avait quatre surfaces qui répondaient à
« qu'est-ce que Bretzel sait faire » — la liste des capacités, l'arbre
des paquets, le catalogue ``ui.*``, la cheat-sheet — et rien ne disait
laquelle fait autorité, ni où écrire en ajoutant un sujet.

⚠️ **Mesuré avant de décider, et la première mesure était fausse.** Elle
disait que ``ui.heading`` apparaît dans 22 chapitres sur 22 : vrai, et
sans intérêt, puisque les chapitres sont ÉCRITS en Bretzel. En ne
regardant que ce dont ils *parlent* — les chaînes de ``ui.code`` et de
``ui.text`` — trois paires seulement partagent quatre symboles, et ce
sont ``Bretzel``, ``page``, ``ui.button``, dont tout extrait a besoin.

Les chapitres ne se dupliquent donc PAS. Ce qui manquait n'était pas un
dédoublonnage, c'était une règle : l'index renvoie, le chapitre
enseigne, et chaque capacité dit lequel.
"""

from __future__ import annotations

import ast
import collections
import importlib
import pathlib

import pytest

from bretzel.introspect.capabilities import CAPABILITIES, Capability

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

#: Preuve de morsure : contrôle POSITIF — le résolveur trouve encore de
#: vrais symboles, et sait dire non à un faux.
MUTATION_PROOF = "test_the_resolver_tells_a_real_symbol_from_a_fake_one"

#: Le compte au gel. Plancher, pas plafond : la liste doit grandir. Il
#: est là pour qu'un fichier vidé ne rende pas les trois autres tests
#: verts en ne regardant rien.
_CAPABILITIES_AT_FREEZE = 19

#: Les capacités sans chapitre qui les enseigne. **Cliquet : ce nombre
#: ne remonte pas.** Il valait 8 à la pose, le 2026-09-03 ; les sept
#: chapitres manquants ont été écrits le jour même et il tombe à ZÉRO.
#:
#: Sept chapitres pour huit capacités : `/lists` en couvre deux, la
#: liste et le tableau étant le même besoin à deux échelles.
#:
#: À zéro, il change de nature — ce n'est plus un cliquet sur une dette,
#: c'est une EXIGENCE : toute capacité neuve vient avec son chapitre.
_WITHOUT_CHAPTER_AT_FREEZE = 0

#: Là où vivent les chapitres. La gate lit leurs routes RÉELLES plutôt
#: que d'en tenir une liste : une route renommée doit faire rougir la
#: capacité qui la cite, pas passer inaperçue.
_DOCS = REPO_ROOT / "examples" / "docs" / "features"


def _resolve(chemin: str) -> object:
    """Le symbole désigné, ou ``AttributeError`` / ``ImportError``.

    ⚠️ Trois formes coexistent dans la liste, et une capacité n'a pas à
    savoir laquelle elle emploie : ``bretzel.auth`` est un MODULE,
    ``bretzel.download`` un attribut du paquet, et ``bretzel.ui.link``
    un attribut D'UN ATTRIBUT — ``ui`` est un espace de noms, pas un
    module, donc aucun découpage en deux ne le trouve.

    D'où : on importe le plus long préfixe importable, puis on descend
    en ``getattr``. La première version coupait en deux et s'est fait
    prendre par ``bretzel.ui.link`` au premier passage de la gate.
    """
    parts = chemin.split(".")
    objet = None
    reste = list(parts)
    for coupe in range(len(parts), 0, -1):
        try:
            objet = importlib.import_module(".".join(parts[:coupe]))
        except ImportError:
            continue
        reste = parts[coupe:]
        break
    if objet is None:
        raise ImportError(f"aucun préfixe importable dans {chemin!r}")
    for attribut in reste:
        objet = getattr(objet, attribut)
    return objet


def test_the_resolver_tells_a_real_symbol_from_a_fake_one() -> None:
    """Plancher, ancré sur la DÉCOUVERTE de cette gate.

    Sans lui, un résolveur qui rendrait ``None`` pour tout ferait passer
    l'ancrage au vert en ne vérifiant rien.
    """
    assert len(CAPABILITIES) >= _CAPABILITIES_AT_FREEZE, (
        f"{len(CAPABILITIES)} capacités contre {_CAPABILITIES_AT_FREEZE} "
        f"au gel — la liste ne rétrécit pas. Si une capacité disparaît "
        f"vraiment, baisse ce plancher DANS le même commit."
    )
    assert _resolve("bretzel.download") is not None
    assert _resolve("bretzel.auth") is not None
    with pytest.raises((AttributeError, ImportError)):
        _resolve("bretzel.ce_symbole_n_existe_pas")


@pytest.mark.parametrize("cap", CAPABILITIES, ids=lambda c: c.name)
def test_a_capability_is_anchored(cap: Capability) -> None:
    """Ses symboles d'entrée existent, et son extrait les emploie."""
    assert cap.entry, f"« {cap.name} » n'entre par aucun symbole."
    for chemin in cap.entry:
        try:
            _resolve(chemin)
        except (AttributeError, ImportError) as exc:
            pytest.fail(
                f"« {cap.name} » entre par ``{chemin}``, qui ne résout "
                f"pas ({type(exc).__name__}).\n"
                f"  Le symbole a été renommé ou supprimé : corrige la "
                f"capacité, ou retire-la si elle n'existe plus."
            )

    try:
        arbre = ast.parse(cap.snippet)
    except SyntaxError as exc:
        pytest.fail(
            f"l'extrait de « {cap.name} » ne parse pas ({exc}).\n"
            f"  Un exemple qui ne compile pas est pire que pas "
            f"d'exemple : on le recopie."
        )

    employes = {
        n.id for n in ast.walk(arbre) if isinstance(n, ast.Name)
    } | {
        n.attr for n in ast.walk(arbre) if isinstance(n, ast.Attribute)
    } | {
        n.arg for n in ast.walk(arbre) if isinstance(n, ast.arg)
    }
    # Le nom NU du symbole : un extrait écrit ``download(...)``, pas
    # ``bretzel.download(...)`` — c'est ce qu'on tape vraiment.
    annonces = {chemin.rsplit(".", 1)[-1] for chemin in cap.entry}
    vus = annonces & employes
    assert vus, (
        f"l'extrait de « {cap.name} » n'emploie AUCUN des symboles "
        f"qu'elle annonce ({sorted(annonces)}).\n"
        f"  Les deux moitiés peuvent être vraies séparément et la "
        f"capacité fausse quand même : c'est la dérive que cette gate "
        f"existe pour attraper."
    )


def test_no_two_capabilities_claim_the_same_entry() -> None:
    """Le détecteur de doublon — c'est pour ça que la liste est ancrée.

    Deux capacités qui entrent par le même symbole sont la même
    capacité, écrite deux fois. Le cas se produit quand on documente une
    variante (« exporter un CSV depuis un tableau ») comme si c'était un
    mécanisme neuf.
    """
    proprietaire: dict[str, list[str]] = collections.defaultdict(list)
    for cap in CAPABILITIES:
        for chemin in cap.entry:
            proprietaire[chemin].append(cap.name)
    partages = {c: n for c, n in proprietaire.items() if len(n) > 1}
    assert not partages, (
        f"symbole(s) revendiqué(s) par plusieurs capacités : {partages}.\n"
        f"  Soit c'est la même capacité écrite deux fois, soit l'une "
        f"des deux entre en réalité par un autre symbole."
    )


def _routes_des_chapitres() -> set[str]:
    """Les routes réellement montées par ``examples/docs``.

    Lues à l'AST sur deux formes, parce que les deux coexistent : une
    constante ``PATH = "/theme"`` (14 chapitres) et un littéral passé
    directement à ``@page("/how")`` (les autres). Tenir une liste à la
    main ici recréerait exactement le problème que cette gate existe
    pour empêcher.
    """
    routes: set[str] = set()
    for fichier in _DOCS.glob("*.py"):
        arbre = ast.parse(fichier.read_text(encoding="utf-8-sig"))
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Assign) and any(
                isinstance(c, ast.Name) and c.id == "PATH"
                for c in noeud.targets
            ):
                valeur = getattr(noeud.value, "value", None)
                if isinstance(valeur, str):
                    routes.add(valeur)
            if isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
                routes.update(_routes_du_decorateur(noeud))
    return routes


def _routes_du_decorateur(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Les routes d'un ``@page("…")`` — lues à l'AST, pas au texte.

    ⚠️ La première version cherchait le motif ``@page("…")`` dans le
    TEXTE du fichier. Elle attrapait donc aussi les ``@page("/tarifs")``
    écrits DANS une chaîne — l'exemple pédagogique de ``structure.py`` —
    et la gate acceptait ``chapter="/tarifs"`` alors que cette route
    rend 404. Un lecteur de code doit lire du CODE.
    """
    trouvees: set[str] = set()
    for deco in fn.decorator_list:
        if not isinstance(deco, ast.Call):
            continue
        nom = deco.func.id if isinstance(deco.func, ast.Name) else None
        if nom != "page" or not deco.args:
            continue
        premier = deco.args[0]
        if isinstance(premier, ast.Constant) and isinstance(premier.value, str):
            trouvees.add(premier.value)
        elif isinstance(premier, ast.Name) and premier.id == "PATH":
            pass  # déjà pris par la lecture de la constante
    return trouvees


def test_the_chapter_reader_sees_the_real_routes() -> None:
    """Plancher : le lecteur de routes lit vraiment quelque chose.

    Sans lui, un lecteur qui rendrait un ensemble vide ferait rougir
    toutes les capacités d'un coup, et on chercherait le bug du mauvais
    côté.
    """
    routes = _routes_des_chapitres()
    assert len(routes) >= 14, (
        f"seulement {len(routes)} routes lues dans examples/docs — le "
        f"lecteur AST est probablement cassé (14 chapitres portaient un "
        f"``PATH`` au gel, plus ceux qui écrivent la route dans "
        f"``@page``)."
    )
    assert "/theme" in routes and "/how" in routes, (
        f"les DEUX formes doivent être lues : PATH = … et @page(…). "
        f"Vues : {sorted(routes)}"
    )


def test_a_declared_chapter_exists() -> None:
    """Un chapitre cité doit être une route montée."""
    routes = _routes_des_chapitres()
    fantomes = sorted(
        (cap.name, cap.chapter)
        for cap in CAPABILITIES
        if cap.chapter and cap.chapter not in routes
    )
    assert not fantomes, (
        f"capacité(s) qui renvoient vers un chapitre inexistant : "
        f"{fantomes}.\n"
        f"  Routes réelles : {sorted(routes)}\n"
        f"  Soit le chapitre a été renommé, soit il n'a jamais existé."
    )


def test_the_chapterless_debt_only_shrinks() -> None:
    """Cliquet sur les capacités que rien n'enseigne.

    C'est la moitié APPLICABLE de la règle « un index liste, un chapitre
    enseigne » : sans elle, on ajouterait des lignes à l'index sans
    jamais écrire ce qui va avec, et l'index redeviendrait le catalogue
    que personne ne peut apprendre.

    ⚠️ Elle ne demande pas d'écrire les huit chapitres manquants. Elle
    refuse le neuvième trou.
    """
    orphelines = sorted(cap.name for cap in CAPABILITIES if not cap.chapter)
    assert len(orphelines) <= _WITHOUT_CHAPTER_AT_FREEZE, (
        f"{len(orphelines)} capacités sans chapitre, contre "
        f"{_WITHOUT_CHAPTER_AT_FREEZE} au gel — le cliquet ne remonte "
        f"pas.\n"
        f"  Une capacité neuve doit soit pointer un chapitre existant, "
        f"soit venir avec le sien.\n"
        f"  Sans chapitre : {orphelines}"
    )
