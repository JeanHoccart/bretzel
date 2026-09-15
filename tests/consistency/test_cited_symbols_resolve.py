"""Gate : un symbole cité avec un rôle Sphinx existe vraiment.

Le défaut qu'elle ferme
----------------------
``bretzel/`` porte **40,8 % de prose** (17,7 % de commentaires ``#``,
23,1 % de docstrings, mesuré le 2026-08-16 sur 59 921 lignes). Cette prose
nomme du code en permanence, et rien ne relisait ces noms quand le code
bougeait. Trois morts trouvés le jour de la livraison de cette gate :

- ``:class:`IFrame``` dans ``primitives/iframe/theme.py`` — la classe
  s'appelle ``Iframe`` ;
- ``:func:`_render_with_layouts``` dans ``render/pipeline.py``, dans un
  « Extrait de … le 2026-08-13 » qui désigne une fonction disparue depuis ;
- ``:mod:`bretzel.theme.presets.default``` dans ``primitives/text/theme.py``
  — module jamais livré, ce que ``theme/__init__.py`` admet par ailleurs
  (« filled by presets/default.py **once it ships** »).

Pourquoi le RÔLE et pas le simple ````X````
---------------------------------------------------------------
Parce que le double-backtick est **surchargé**, et c'est mesuré : sur les
11 882 citations ````X```` du paquet, une gate qui exigerait
un symbole Python produirait **1 560 faux positifs** (13 %) — 34 % sont des
identifiants JS du runtime (``_serverSync``, ``setTab``), 34 % sont des
*valeurs* et non des symboles (``change``, ``fixed``, ``soft``, ``left``,
``true``), 17 % des noms de slots ou du DOM. Aucune heuristique ne les
sépare : la distinction est dans l'intention, pas dans la forme.

Et la desserrer ne marche pas non plus. Une résolution par sous-chaîne dans
le corpus ramène le résidu à 0,3 % mais ne mord franchement que sur 24,5 %
des citations — c'est-à-dire une gate décorative, la pathologie exacte que
:mod:`tests.consistency.test_prohibition_gates_declare_a_floor` documente
sans savoir l'attraper.

D'où la convention : **le rôle est le consentement à être vérifié**. On
écrit ``:class:`Component``` quand on nomme un symbole Python et qu'on
accepte que la gate le relise ; on garde ````X```` libre pour tout
le reste. Le marqueur ne décore pas, il déclare.

Portée honnête
--------------
1. On vérifie qu'un nom **existe**, pas que la phrase qui l'entoure est
   vraie. Un paragraphe de mécanisme devenu faux dont tous les symboles
   vivent encore reste invisible ici — il faut le relire. C'est la limite
   structurelle, pas un manque d'effort : seule la classe
   renommage/suppression est mécanisable.
2. Le **genre** du rôle (``:class:`` sur une méthode, ``:func:`` sur une
   classe) n'est contrôlé que pour les symboles **définis localement**.
   Pour un nom importé ou un builtin, on ne connaît pas son genre sans
   l'importer, et importer pour vérifier de la prose coûterait plus que ça
   ne rapporte.
3. Le sens inverse — un symbole cité en ````X```` qui aurait mérité un
   rôle — n'est PAS gaté, par construction (cf. les 1 560 faux positifs
   ci-dessus). C'est le ratchet qui porte la migration, pas une interdiction.
"""

from __future__ import annotations

import ast
import builtins
import functools
import io
import re
import tokenize

import pytest

from tests.consistency._discovery import (
    PACKAGE_FLOOR,
    REPO_ROOT,
    ParsedSource,
    parsed_sources,
)

PACKAGE_ROOT = REPO_ROOT / "bretzel"

#: Les rôles Sphinx qui désignent un symbole Python. ``:ref:`` est exclu —
#: il pointe une ancre de doc, pas du code.
_ROLE = re.compile(r":(?:py:)?(meth|class|func|attr|mod|data|obj|exc):`([^`\n]+)`")

#: Forme « titre explicite » de Sphinx : ``:class:`Titre <la.vraie.cible>```.
#: C'est la CIBLE qui doit résoudre, pas le titre. Oublier ce cas a fait
#: accuser 6 citations parfaitement valides pendant l'écriture de la gate.
_EXPLICIT_TITLE = re.compile(r"<([^>]+)>\s*$")

#: Rôles pour lesquels on ne contrôle que l'existence. ``:obj:`` et
#: ``:exc:`` sont volontairement laches : le premier est le rôle fourre-tout
#: de Sphinx, le second désigne presque toujours une exception stdlib.
_EXISTENCE_ONLY = frozenset({"obj", "exc"})

_BUILTINS = frozenset(dir(builtins))


class _Universe:
    """Ce que le paquet définit, importe, ou hérite des builtins.

    Trois populations SÉPARÉES, et la séparation est le cœur de la gate :
    seuls les symboles **locaux** ont un genre connu, donc seuls eux
    peuvent se voir reprocher un mauvais rôle. Les fusionner ferait
    exactement l'univers trop permissif qui rend une gate décorative —
    n'importe quel nom finirait par « exister quelque part ».
    """

    def __init__(self) -> None:
        self.classes: dict[str, set[str]] = {}
        self.functions: set[str] = set()
        self.methods: dict[str, set[str]] = {}
        self.class_attrs: set[str] = set()
        self.module_data: set[str] = set()
        self.modules: set[str] = set()
        self.imported: set[str] = set()

    @property
    def local(self) -> set[str]:
        return (
            set(self.classes)
            | self.functions
            | self.class_attrs
            | self.module_data
            | {m.rsplit(".", 1)[-1] for m in self.modules}
        )

    def knows(self, name: str) -> bool:
        return name in self.local or name in self.imported or name in _BUILTINS


def _collect(universe: _Universe, source: ParsedSource) -> None:
    dotted = ".".join(source.path.relative_to(REPO_ROOT).with_suffix("").parts)
    universe.modules.add(dotted)
    if source.path.name == "__init__.py":
        # Un package se cite par son nom de dossier, pas par son ``__init__``.
        universe.modules.add(".".join(source.path.parent.relative_to(REPO_ROOT).parts))

    for node in ast.walk(source.tree):
        if isinstance(node, ast.ClassDef):
            universe.classes.setdefault(node.name, set()).add(dotted)
            members = universe.methods.setdefault(node.name, set())
            for sub in node.body:
                if isinstance(sub, ast.FunctionDef | ast.AsyncFunctionDef):
                    members.add(sub.name)
                    universe.class_attrs.add(sub.name)
                elif isinstance(sub, ast.AnnAssign) and isinstance(sub.target, ast.Name):
                    members.add(sub.target.id)
                    universe.class_attrs.add(sub.target.id)
                elif isinstance(sub, ast.Assign):
                    for target in sub.targets:
                        if isinstance(target, ast.Name):
                            members.add(target.id)
                            universe.class_attrs.add(target.id)
        # Les imports comptent PARTOUT, pas seulement au top-level : un
        # import function-local « casse un cycle » (cf. CLAUDE.md principe 5)
        # lie un nom que la prose du fichier a le droit de citer.
        elif isinstance(node, ast.Import | ast.ImportFrom):
            # Le MODULE d'un ``from x.y import z`` compte autant que ``z`` :
            # la prose cite couramment le chemin complet
            # (``:class:`~contextvars.ContextVar```), donc sans ``contextvars``
            # la tête du chemin reste inconnue et la citation est accusée à
            # tort. Oublier ça a produit 8 faux positifs au premier run.
            for dotted_path in (getattr(node, "module", None), *(a.name for a in node.names)):
                if not dotted_path:
                    continue
                for segment in dotted_path.split("."):
                    universe.imported.add(segment)
            for alias in node.names:
                universe.imported.add(alias.asname or alias.name.split(".")[0])
                universe.imported.add(alias.name.split(".")[-1])

    for node in source.tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            universe.functions.add(node.name)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            universe.module_data.add(node.target.id)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    universe.module_data.add(target.id)


@functools.lru_cache(maxsize=1)
def _universe() -> _Universe:
    universe = _Universe()
    for source in parsed_sources(PACKAGE_ROOT, floor=PACKAGE_FLOOR):
        _collect(universe, source)
    return universe


def _prose_blocks(source: ParsedSource) -> list[tuple[int, str]]:
    """``(ligne, texte)`` pour chaque commentaire et chaque docstring.

    On lit la PROSE, jamais la source brute. Une regex sur le texte entier
    matcherait aussi dans un littéral de chaîne — et le dépôt a déjà payé
    l'inverse de cette erreur : ``test_ring_offset_matches_its_surface``
    rougissait sur le commentaire qui EXPLIQUE la faute qu'elle interdit.
    """
    blocks: list[tuple[int, str]] = []
    for token in tokenize.generate_tokens(io.StringIO(source.text).readline):
        if token.type == tokenize.COMMENT:
            blocks.append((token.start[0], token.string))
    for node in ast.walk(source.tree):
        if isinstance(
            node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        ):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                blocks.append((getattr(node, "lineno", 1), doc))
    return blocks


@functools.lru_cache(maxsize=1)
def _citations() -> tuple[tuple[str, int, str, str], ...]:
    """``(fichier, ligne, rôle, cible)`` pour chaque citation à rôle."""
    found: list[tuple[str, int, str, str]] = []
    for source in parsed_sources(PACKAGE_ROOT, floor=PACKAGE_FLOOR):
        rel = source.path.relative_to(REPO_ROOT).as_posix()
        for lineno, prose in _prose_blocks(source):
            for role, raw in _ROLE.findall(prose):
                explicit = _EXPLICIT_TITLE.search(raw)
                target = (explicit.group(1) if explicit else raw).strip()
                found.append((rel, lineno, role, target))
    return tuple(found)


def _is_own_package(dotted: str) -> bool:
    """Le chemin désigne-t-il ``bretzel`` lui-même ?"""
    return dotted == "bretzel" or dotted.startswith("bretzel.")


def _resolve(role: str, target: str) -> str | None:
    """``None`` si la citation résout ; sinon la raison, formulée pour agir."""
    universe = _universe()
    # ``~`` = « n'affiche que le dernier segment », purement cosmétique.
    # Les parenthèses d'un appel ne font pas partie du nom.
    clean = target.lstrip("~").split("(")[0].strip()
    if not clean:
        return "citation vide"

    if role == "mod":
        bare = clean.lstrip(".")            # ``:mod:`._svg``` = module relatif
        if bare in universe.modules or any(
            m.endswith("." + bare) for m in universe.modules
        ):
            return None
        if _is_own_package(bare):
            # Pas d'échappatoire « externe » pour notre propre paquet : on
            # le connaît exhaustivement, donc un ``bretzel.x.y`` introuvable
            # est introuvable. Sans cette garde, ``bretzel`` étant importé
            # partout, TOUTE citation ``bretzel.…`` passerait — et la gate
            # perdrait ``:mod:`bretzel.theme.presets.default```, un module
            # jamais livré.
            return f"aucun module `{bare}` sous bretzel/"
        if universe.knows(bare.rsplit(".", 1)[-1]) or bare.split(".")[0] in universe.imported:
            return None                     # module externe, importé quelque part
        return f"aucun module `{bare}` sous bretzel/"

    parts = clean.split(".")
    last, owner = parts[-1], (parts[-2] if len(parts) >= 2 else None)

    # Un nom externe (importé ou builtin) existe mais son GENRE nous est
    # inconnu : on s'arrête à l'existence. Le test d'appartenance passe par
    # la tête du chemin pointé — ``contextvars.ContextVar`` est connu dès
    # que ``contextvars`` l'est. Même garde que ci-dessus : notre propre
    # paquet ne s'échappe pas par là.
    if not _is_own_package(clean) and (
        parts[0] in universe.imported or parts[0] in _BUILTINS
    ):
        return None
    if role in _EXISTENCE_ONLY:
        return None if universe.knows(last) else f"symbole inconnu : `{last}`"

    # Chemin pointé dont le propriétaire est une classe LOCALE : on peut
    # vérifier le membre, et c'est là que la gate mord le plus fort.
    if owner and owner in universe.classes:
        if last in universe.methods.get(owner, set()):
            if role == "class":
                return (
                    f"`{owner}.{last}` est un membre de classe, pas une classe "
                    f"— utilise :meth:` ` (méthode) ou :attr:` ` (attribut)"
                )
            return None
        return f"la classe `{owner}` n'a pas de membre `{last}`"

    if role == "class":
        if last in universe.classes:
            return None
        if last in universe.functions:
            return f"`{last}` est une fonction — utilise :func:`{last}`"
        if last in universe.class_attrs or last in universe.module_data:
            return f"`{last}` n'est pas une classe — utilise :data:` ` ou :attr:` `"
        return f"aucune classe `{last}` dans bretzel/"

    if role == "func":
        # ``module_data`` couvre les alias : ``check_protocol_compat =
        # check_compat`` est une fonction pour qui la lit, pas une donnée.
        if last in universe.functions or last in universe.module_data:
            return None
        if last in universe.classes:
            return f"`{last}` est une classe — utilise :class:`{last}`"
        if last in universe.class_attrs:
            return f"`{last}` est un membre de classe — utilise :meth:` `"
        return f"aucune fonction `{last}` dans bretzel/"

    if role == "meth":
        if last in universe.class_attrs:
            return None
        if last in universe.functions:
            return f"`{last}` est une fonction top-level — utilise :func:`{last}`"
        return f"aucune méthode `{last}` dans bretzel/"

    # ``:attr:`` / ``:data:``
    if last in universe.class_attrs or last in universe.module_data:
        return None
    return f"aucun attribut ni constante `{last}` dans bretzel/"


# ---------------------------------------------------------------- planchers

#: Ratchet. 766 citations à rôle sur 228 fichiers, mesurées le 2026-08-16.
#: Le seuil ne descend pas tout seul : la migration ````X```` → rôle le
#: fait monter, et une baisse veut dire qu'on a supprimé de la prose
#: vérifiée — ce qui peut être légitime, mais doit être une décision
#: écrite, pas un effet de bord. Si tu en convertis, monte ce chiffre dans
#: le même commit.
#:
#: 767 → 766 le 2026-08-16, premier jour de la gate : la citation
#: ``:mod:`bretzel.theme.presets.default``` de ``primitives/text/theme.py``
#: a été retirée plutôt que corrigée, faute de module à désigner — il n'a
#: jamais été écrit. Aucun rôle ne pouvait la rendre vraie.
_RATCHET = 766


def test_discovery_is_not_vacuous() -> None:
    """Plancher ancré sur la DÉCOUVERTE, pas sur la population.

    Un plancher qui recompterait « combien de fichiers sous ``bretzel/`` »
    resterait vert avec l'extraction débranchée — c'est ``parsed_sources``
    qui garde ça. Ici on exige que la regex de rôle ait effectivement
    parlé : si ``_ROLE`` cesse de matcher, ou si ``_prose_blocks`` cesse de
    rendre des blocs, ce test tombe AVANT que l'interdiction ne devienne
    verte sur zéro citation.
    """
    citations = _citations()
    files = {rel for rel, _, _, _ in citations}
    assert len(citations) >= _RATCHET, (
        f"seulement {len(citations)} citations à rôle extraites "
        f"({_RATCHET} attendues au minimum) — soit la convention recule, soit "
        f"l'extraction a cassé. Vérifie `_ROLE` et `_prose_blocks` avant "
        f"de baisser ce plancher."
    )
    assert len(files) >= 200, (
        f"les citations ne viennent plus que de {len(files)} fichiers "
        f"(228 le 2026-08-16) — un balayage concentré sur une poignée de "
        f"fichiers ne garde plus le paquet."
    )


def test_the_universe_is_populated() -> None:
    """Le pendant : une gate d'existence dont l'univers est vide dirait
    « tout est mort » ; un univers construit à moitié dirait « tout va
    bien » sur les moitiés manquantes. On ancre les deux."""
    universe = _universe()
    # Mesurés le 2026-08-16 : 202 classes, 440 fonctions top-level, 469
    # modules. Les seuils laissent de la marge pour une réorganisation sans
    # laisser passer une collecte amputée. ⚠️ Ils sont MESURÉS, pas devinés :
    # la première version portait « >= 250 classes » sorti de nulle part, et
    # rougissait sur un univers parfaitement sain.
    assert len(universe.classes) >= 180, (
        f"seulement {len(universe.classes)} classes collectées (202 le "
        f"2026-08-16) — la construction de l'univers a cassé."
    )
    assert len(universe.functions) >= 380, (
        f"seulement {len(universe.functions)} fonctions top-level collectées "
        f"(440 le 2026-08-16)."
    )
    assert len(universe.modules) >= 400, (
        f"seulement {len(universe.modules)} modules collectés (469 le "
        f"2026-08-16)."
    )


@pytest.mark.parametrize(
    ("rel", "lineno", "role", "target"),
    _citations(),
    ids=[f"{rel}:{ln}:{role}:{t}" for rel, ln, role, t in _citations()],
)
def test_cited_symbol_resolves(rel: str, lineno: int, role: str, target: str) -> None:
    problem = _resolve(role, target)
    assert problem is None, (
        f"{rel}:{lineno} — :{role}:`{target}` ne résout pas.\n"
        f"  {problem}\n"
        f"  Un rôle Sphinx est une affirmation vérifiable : en l'écrivant, "
        f"la prose accepte d'être relue par cette gate. Corrige le nom, "
        f"corrige le rôle, ou repasse en ``{target}`` si ce n'est pas un "
        f"symbole Python de ce paquet."
    )


def test_the_detector_still_bites() -> None:
    """Mutation : un rôle Sphinx est encore extrait de la prose.

    C'est la gate qui garde « un symbole cité existe ». Si l'extraction
    cessait de matcher, elle vérifierait zéro citation tout en restant
    verte — et la prose pourrait nommer n'importe quoi.
    """
    found = _ROLE.search("cf. :class:`bretzel.components.Component` pour le détail")
    assert found, "l'extraction du rôle ne matche plus"
    assert found.group(1) == "class"
    assert found.group(2) == "bretzel.components.Component"
    assert not _ROLE.search("cf. ``Component`` en double backtick"), "faux positif"
    assert _EXPLICIT_TITLE.search("le socle <bretzel.core.Node>").group(1) == (
        "bretzel.core.Node"
    )
