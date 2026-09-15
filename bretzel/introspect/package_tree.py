"""L'ARBRE des dossiers — le framework décrit son propre rangement.

⚠️ **À ne pas confondre avec ``packages.py``, son voisin de dossier**,
qui traite d'un tout autre sujet : les composants publiés par des
paquets TIERS installés. Ici il s'agit de l'arbre de Bretzel lui-même.
Les deux noms se ressemblent assez pour qu'on écrase l'un en croyant
créer l'autre — c'est arrivé le 2026-09-02, et ce sont les 216 rouges
de la suite qui l'ont dit, pas la relecture.

``describe_module`` lit une table écrite à la main : sept modules
classés symbole par symbole. C'est précis, et c'est **aveugle au reste**
— ``bretzel.components.inputs`` est un vrai paquet, avec une vraie
docstring, et l'introspection répondait « n'existe pas ».

Mesuré le 2026-09-02 : **117 dossiers sous ``bretzel/``, 117 ont une
docstring de paquet, zéro manquant.** La matière pour se décrire existe
donc déjà en entier — personne ne la lisait.

Ce module la lit. Il ne classe rien et n'invente rien : il marche
l'arbre, prend la docstring que le dossier porte déjà, et rend la
hiérarchie. Le classement par besoin de ``modules.py`` reste posé
PAR-DESSUS, sur les sept modules qui l'ont — les deux se complètent, ils
ne se remplacent pas.

Pourquoi ça ne peut pas pourrir
--------------------------------
Parce que la source est le dossier lui-même. Une liste écrite à la main
dérive dès qu'on ajoute un paquet sans y penser ; ici, un paquet neuf
apparaît tout seul, et sa docstring est ce que son auteur a écrit en le
créant. La seule chose à garder est qu'il en ait une —
``test_every_package_describes_itself`` s'en charge.

C'est la même leçon que le skill ``bretzel-api`` supprimé le
2026-08-01 : un catalogue recopié à la main dérive plus vite qu'il ne
sert. La différence entre les deux, c'est de savoir QUI est la source.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

#: La racine du paquet installé. Lue depuis ce fichier plutôt que par
#: ``importlib`` : on veut l'ARBRE DE FICHIERS, pas ce que Python a bien
#: voulu importer — un paquet cassé doit apparaître, pas disparaître.
_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True, slots=True)
class SymbolLine:
    """Un symbole public d'un module, et sa première ligne.

    Pas une fiche : le détail complet d'un composant vit dans
    ``describe_ui_symbol``, qui lit la classe RÉELLE (params, slots,
    events). Ici on ne veut que « ce qui est là, et à quoi ça sert »,
    lu à l'AST — donc sans importer quoi que ce soit.
    """

    name: str
    kind: str          # "fonction" | "classe"
    summary: str


@dataclass(frozen=True, slots=True)
class ModuleInfo:
    """Un module ``.py``, sa raison d'être, et ce qu'il expose."""

    name: str
    summary: str
    symbols: tuple[SymbolLine, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class PackageNode:
    """Un paquet, sa raison d'être, et ce qu'il contient."""

    #: Le chemin pointé, ``bretzel.components.inputs``.
    name: str
    #: La PREMIÈRE ligne de sa docstring — ce qu'il fait, en une phrase.
    summary: str
    #: Sa docstring entière, pour qui veut le détail.
    doc: str
    #: Ses sous-paquets, triés.
    children: tuple[PackageNode, ...] = field(default_factory=tuple)
    #: Les modules ``.py`` qu'il porte en propre (hors ``__init__``),
    #: avec leur première ligne ET leurs symboles publics. Un module
    #: privé (``_x.py``) en fait partie : il compte dans le rangement
    #: même s'il n'est pas de l'API.
    modules: tuple[ModuleInfo, ...] = field(default_factory=tuple)

    @property
    def depth(self) -> int:
        return self.name.count(".")


def _docstring_of(path: Path) -> str:
    """La docstring d'un fichier, ou ``""``.

    ⚠️ ``utf-8-sig`` et pas ``utf-8`` : ``bretzel/render/__init__.py`` a
    porté un BOM que le second laisse en tête de chaîne et qu'``ast``
    refuse — un fichier sur 344 sortait ainsi du balayage de sept gates,
    pendant des mois. Le lecteur partagé de ``tests/consistency`` porte
    la même correction, pour la même raison.
    """
    try:
        arbre = ast.parse(path.read_text(encoding="utf-8-sig"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return ""
    return ast.get_docstring(arbre) or ""


def _first_line(doc: str) -> str:
    """Le premier PARAGRAPHE, lignes recollées — pas la première ligne.

    ⚠️ **La différence n'est pas cosmétique, elle est mesurée.** Prendre
    la première *ligne* coupait **68 résumés sur 592 (11 %)** en plein
    milieu d'une phrase, parce que l'auteur avait replié sa phrase à 79
    colonnes :

        Stable 8-char hex digest used to compress IDs (and other stable

    Le lecteur ne voyait pas une phrase courte, il voyait une phrase
    fausse — et rien à l'écran ne disait qu'il en manquait la moitié.

    Le paragraphe les répare **toutes les 68, sans rien coûter** : la
    longueur médiane est la même (59 caractères), parce que la grande
    majorité des résumés tiennent déjà sur une ligne. Seuls 9 dépassent
    200 caractères.

    On s'arrête au premier saut de ligne VIDE : la suite d'une docstring
    est le détail, et le résumé doit rester un résumé.
    """
    bloc: list[str] = []
    for ligne in doc.strip().splitlines():
        if not ligne.strip():
            break
        bloc.append(ligne.strip())
    return " ".join(bloc)


def _is_package(path: Path) -> bool:
    return path.is_dir() and (path / "__init__.py").exists()


def _module_info(path: Path) -> ModuleInfo:
    """Le module, sa phrase, et ses symboles publics de premier niveau.

    Pourquoi on descend jusque-là (2026-09-02)
    ------------------------------------------
    Parce que le niveau au-dessus est souvent VIDE. Mesuré : **73 des
    117 docstrings de paquet sont des talons** de la forme
    « icon_button component. », pendant que le module juste en dessous
    dit « IconButton — square button whose only content is an icon ».

    Le contenu existe, il est un cran plus bas : **608 symboles publics,
    592 documentés — 97 %**. Descendre coûte donc moins
    cher que de réécrire 73 docstrings de dossier — et donne du texte
    que quelqu'un a écrit en pensant à ce qu'il faisait, pas pour
    remplir une case.

    ⚠️ Lu à l'AST, donc SANS importer. Un module qui casse à l'import
    reste décrit — et c'est voulu : la doc d'un dépôt doit survivre à un
    fichier en travaux.
    """
    doc_module = _docstring_of(path)
    symboles: list[SymbolLine] = []
    try:
        arbre = ast.parse(path.read_text(encoding="utf-8-sig"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        arbre = None
    if arbre is not None:
        for n in arbre.body:
            if isinstance(n, ast.ClassDef):
                kind = "classe"
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kind = "fonction"
            else:
                continue
            if n.name.startswith("_"):
                continue
            symboles.append(SymbolLine(
                name=n.name, kind=kind,
                summary=_first_line(ast.get_docstring(n) or ""),
            ))
    return ModuleInfo(
        name=path.stem, summary=_first_line(doc_module),
        symbols=tuple(symboles),
    )


@cache
def describe_package(name: str = "bretzel") -> PackageNode:
    """L'arbre à partir de ``name``, docstrings comprises.

    ``name`` est un chemin pointé (``bretzel.components.inputs``). Lève
    ``ValueError`` s'il ne désigne pas un paquet — et le message dit ce
    qui EXISTE au niveau demandé, parce qu'une erreur de frappe sur un
    nom de dossier est le cas courant.

    Mémoïsée, et il a fallu la mesurer pour le voir
    ------------------------------------------------
    Marcher l'arbre parse **344 fichiers à l'AST**, ce qui coûtait
    **740 ms À CHAQUE APPEL**. Les huit autres lecteurs de ce paquet
    portent un ``@cache`` depuis toujours ; celui-ci ne l'avait pas, et
    c'était le plus cher de tous — 150 fois ``index()``, qui met 4,7 ms.

    La page ``/tree`` de ``examples/docs`` l'appelait DEUX fois par
    requête (ici, puis via :func:`package_names`) : **1 340 ms** pour
    une page, contre 132 ms pour ``/components``.

    Sûr parce que le résultat est immuable : ``PackageNode`` est un
    ``frozen`` dont tous les champs sont des chaînes ou des tuples de
    ``frozen``. Aucun appelant ne peut donc corrompre l'entrée en cache.

    ⚠️ La source est le SYSTÈME DE FICHIERS, pas un objet Python : un
    dossier ajouté pendant la vie du process n'apparaît pas. En dev ça
    ne se voit pas — ``mode="dev"`` redémarre le process au moindre
    fichier touché — et un script qui fabriquerait des paquets à la
    volée appelle ``describe_package.cache_clear()``, comme le fait
    ``third_party_components``.
    """
    parts = name.split(".")
    if parts[0] != "bretzel":
        raise ValueError(
            f"describe_package({name!r}) : les paquets décrits ici vivent "
            f"sous ``bretzel``. Pour un symbole, c'est "
            f"``describe_ui_symbol``."
        )
    path = _ROOT.joinpath(*parts[1:])
    if not _is_package(path):
        voisins = sorted(
            p.name for p in path.parent.iterdir() if _is_package(p)
        ) if path.parent.is_dir() else []
        raise ValueError(
            f"``{name}`` n'est pas un paquet. Au même niveau : "
            f"{', '.join(voisins) or '(rien)'}."
        )
    return _build(name, path)


def _build(name: str, path: Path) -> PackageNode:
    doc = _docstring_of(path / "__init__.py")
    enfants = tuple(
        _build(f"{name}.{p.name}", p)
        for p in sorted(path.iterdir())
        if _is_package(p) and p.name != "__pycache__"
    )
    modules = tuple(
        _module_info(p)
        for p in sorted(path.glob("*.py"))
        if p.name != "__init__.py"
    )
    return PackageNode(
        name=name, summary=_first_line(doc), doc=doc,
        children=enfants, modules=modules,
    )


def walk(node: PackageNode) -> list[PackageNode]:
    """Le nœud et toute sa descendance, en profondeur d'abord."""
    out = [node]
    for enfant in node.children:
        out.extend(walk(enfant))
    return out


def package_names(root: str = "bretzel") -> tuple[str, ...]:
    """Tous les paquets sous ``root``, chemins pointés, triés."""
    return tuple(n.name for n in walk(describe_package(root)))


def render_tree(node: PackageNode, *, max_depth: int | None = None) -> str:
    """L'arbre en texte — ce que ``bretzel describe <paquet>`` affiche.

    ``max_depth`` compte À PARTIR du nœud demandé, pas de la racine :
    ``describe bretzel --depth 1`` montre les grands blocs,
    ``describe bretzel.components --depth 1`` montre ses groupes.
    """
    lignes: list[str] = []
    base = node.depth

    def _ecrire(n: PackageNode) -> None:
        relative = n.depth - base
        if max_depth is not None and relative > max_depth:
            return
        indent = "  " * relative
        resume = f"  — {n.summary}" if n.summary else ""
        lignes.append(f"{indent}{n.name.split('.')[-1]}/{resume}")
        for enfant in n.children:
            _ecrire(enfant)

    _ecrire(node)
    return "\n".join(lignes)


def render_package(node: PackageNode) -> str:
    """La fiche d'un paquet — sa raison d'être, son arbre, ses modules.

    Volontairement PLUS COURTE qu'une fiche de symbole : on vient ici
    pour savoir « qu'y a-t-il là-dedans », pas pour lire une signature.
    Le détail d'un symbole reste ``describe <nom>``.
    """
    lignes = [f"## {node.name}", ""]
    if node.doc:
        # La docstring entière, indentée — c'est ce que l'auteur du
        # paquet a écrit, et le reformuler ferait diverger les deux.
        for ligne in node.doc.strip().splitlines():
            lignes.append(f"  {ligne}" if ligne.strip() else "")
        lignes.append("")

    if node.children:
        lignes.append(f"  Sous-paquets ({len(node.children)})")
        for enfant in node.children:
            court = enfant.name.split(".")[-1]
            resume = f"  — {enfant.summary}" if enfant.summary else ""
            lignes.append(f"    {court}/{resume}")
        lignes.append("")

    if node.modules:
        lignes.append(f"  Modules ({len(node.modules)})")
        for mod in node.modules:
            lignes.append(f"    {mod.name:<24}{mod.summary}")
            for sym in mod.symbols:
                lignes.append(f"      {sym.name:<22}{sym.summary}")
        lignes.append("")

    total = len(walk(node))
    if total > 1:
        lignes.append(f"  {total} paquets en tout sous ce nœud.")
    return "\n".join(lignes)
