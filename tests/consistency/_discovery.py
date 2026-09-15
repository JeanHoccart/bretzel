"""Shared introspection helpers for the consistency gates.

Single source for "what are the public components?" so every gate scans
the same live surface — and a new ``ui.foo = Foo`` is picked up by all of
them at once, with no per-test edit.
"""

from __future__ import annotations

import ast
import dataclasses
import functools
import html as _html
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from bretzel.components import _UI
from bretzel.components.base.component import Component
from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from bretzel.core.tree import Element, FragmentNode

REPO_ROOT = Path(__file__).resolve().parents[2]
#: La racine du paquet. ``PACKAGE_FLOOR`` la mesurait déjà sans que la
#: constante existe — chaque gate qui balaie tout le framework la
#: recomposait donc chez elle.
PACKAGE_DIR = REPO_ROOT / "bretzel"
COMPONENTS_DIR = REPO_ROOT / "bretzel" / "components"
RUNTIME_SRC_DIR = REPO_ROOT / "bretzel" / "runtime" / "_src"
PROBES_DIR = REPO_ROOT / "tests" / "probes"


@functools.lru_cache(maxsize=1)
def tailwind_corpus() -> str:
    """Exactement ce que le compilateur Tailwind de PROD scanne.

    Les sources (``bretzel/**``, ``examples/**``) **plus** l'entrée de
    thème, dont la directive ``@source inline(...)`` est le canal prévu
    pour les classes qu'aucun littéral ne peut porter (celles qu'un
    render assemble depuis une valeur d'exécution).

    Partagé par les deux gates qui cherchent une classe morte —
    ``test_emitted_classes_exist_in_source`` (balayage du playground) et
    ``test_responsive_classes_are_safelisted`` (props gradués). Écrit une
    fois : les deux doivent regarder le MÊME corpus, sinon l'une déclare
    absente une classe que l'autre trouve, et on passe une soirée à
    chercher laquelle a raison.
    """
    from starlette.testclient import TestClient

    from examples.playground.main import app

    parts: list[str] = []
    for pattern in ("bretzel/**/*.py", "examples/**/*.py", "bretzel/**/*.js"):
        for path in REPO_ROOT.glob(pattern):
            if "__pycache__" in str(path) or "archive" in str(path):
                continue
            parts.append(path.read_text(encoding="utf8", errors="replace"))
    with TestClient(app):
        parts.append(getattr(app, "_theme_css_content", "") or "")
    return "\n".join(parts)

# Plancher de non-vacuité partagé. 220 fichiers mesurés le 2026-07-29 ; le
# seuil laisse de la marge pour une réorganisation sans laisser passer un
# balayage cassé.
_SWEEP_FLOOR = 180


@functools.lru_cache(maxsize=1)
def _component_sources() -> tuple[Path, ...]:
    # Caché : le rglob coûte ~42 ms et l'arborescence ne bouge pas pendant
    # une session de tests. Le docstring d'``assert_sweep_is_not_vacuous``
    # invite TOUTE gate d'interdiction à appeler ceci — 24 en sont encore
    # dépourvues aujourd'hui, donc le nombre d'appelants va croître.
    return tuple(
        p for p in COMPONENTS_DIR.rglob("*.py") if "__pycache__" not in p.parts
    )


def component_sources() -> list[Path]:
    """Tous les modules de composant, ``__pycache__`` exclu."""
    return list(_component_sources())


def assert_sweep_is_not_vacuous() -> None:
    """À appeler par toute gate d'INTERDICTION qui balaie les composants.

    Une gate qui affirme « zéro contrevenant » passe exactement aussi bien
    quand elle n'a lu aucun fichier — chemin déplacé, arborescence renommée,
    motif devenu introuvable. Ce n'est pas théorique dans ce dépôt : une gate
    y est restée verte des mois en cherchant le préfixe ``x-bz-prop:``, mort
    depuis le rebrand ``bz-``, donc en ne matchant plus aucun attribut.
    """
    visited = component_sources()
    assert len(visited) >= _SWEEP_FLOOR, (
        f"le balayage ne visite plus que {len(visited)} fichiers sous "
        f"{COMPONENTS_DIR} (220 mesurés le 2026-07-29) — vérifie le chemin "
        f"avant de croire qu'une gate d'interdiction passe."
    )


def public_component_classes() -> list[type]:
    """Every ``Component`` subclass exposed on the ``ui`` namespace, by name."""
    found: dict[str, type] = {}
    for value in vars(_UI).values():
        if (
            isinstance(value, type)
            and issubclass(value, Component)
            and value is not Component
        ):
            found[value.__name__] = value
    return [found[name] for name in sorted(found)]


def public_component_names() -> list[str]:
    return [cls.__name__ for cls in public_component_classes()]


@functools.lru_cache(maxsize=1)
def _ui_names_by_class() -> dict[type, str]:
    return {
        value: name
        for name, value in vars(_UI).items()
        if not name.startswith("_") and isinstance(value, type)
    }


def ui_name_of(cls: type) -> str:
    """Le nom ``ui.*`` sous lequel une classe est exposée.

    **Lève** si la classe n'est pas exposée, au lieu de retomber sur un
    ``cls.__name__.lower()`` : ce repli rendrait ``bottombaritem`` pour
    ``BottomBarItem``, et 34 des 96 composants ont un nom ``ui`` que la
    minuscule naïve rate (``icon_button``, ``date_picker``,
    ``pie_chart``…). Une gate qui l'accepterait s'affaiblirait EN SILENCE.

    Promue ici le 2026-08-16 : la même boucle vivait en trois exemplaires
    (deux dans ``tests/``, une neuve dans la gate d'introspection), et
    :func:`public_component_classes` balayait déjà ``vars(_UI)`` en JETANT
    le nom.
    """
    try:
        return _ui_names_by_class()[cls]
    except KeyError:
        raise AssertionError(
            f"{cls.__name__} n'est exposé sous aucun nom de ``ui`` — une "
            f"gate qui l'accepterait ne testerait pas ce qu'elle croit."
        ) from None


@functools.lru_cache(maxsize=1)
def _runtime_slabs() -> tuple[Path, ...]:
    return tuple(sorted(RUNTIME_SRC_DIR.glob("[0-9]*_*.js")))


def runtime_slabs() -> list[Path]:
    """Les modules sources du runtime, dans l'ordre de concaténation.

    Trois gates écrivaient ce chemin et ce glob à la main. Ce n'est pas
    de la cosmétique : le jour où ``_src/`` bouge, chaque copie devient
    silencieusement vacuoise — la pathologie que
    :func:`assert_sweep_is_not_vacuous` documente pour les composants,
    et qui vaut mot pour mot ici.
    """
    return list(_runtime_slabs())


#: Commentaires JS. Promus ici depuis
#: ``test_bridge_error_kinds_are_emitted.py`` le 2026-08-15, quand une
#: DEUXIÈME gate en a eu besoin et les a recopiés à l'identique.
_JS_LINE_COMMENT = re.compile(r"//.*$", re.MULTILINE)
_JS_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def strip_js_comments(source: str) -> str:
    """Ôter les commentaires d'une source JS avant de la balayer.

    Une gate qui cherche du vocabulaire dans ``_src/`` doit lire le CODE,
    pas la prose : ces fichiers commentent abondamment les mécanismes
    qu'ils implémentent, y compris ceux qu'on vient de RETIRER — sans le
    strip, une gate lit la note d'un retrait comme une occurrence vivante.

    ⚠️ **Approximation connue, volontairement gardée** : un ``//`` dans un
    littéral de chaîne (``"http://…"``) est traité comme un début de
    commentaire. Vérifié le 2026-08-15 : aucun des 22 modules de ``_src/``
    n'en contient. Le jour où c'est faux, le fix est ici — et c'est
    précisément la raison de la promotion : il y avait deux copies
    identiques de ce défaut, dont une inlinée, donc invisible au grep qui
    aurait trouvé l'autre.
    """
    return _JS_LINE_COMMENT.sub("", _JS_BLOCK_COMMENT.sub("", source))


def runtime_sources(*, strip: bool = True) -> dict[str, str]:
    """``{nom de slab: source}`` — une seule lecture, un seul encodage.

    NEUF gates appelaient :func:`runtime_slabs` puis relisaient le texte
    elles-mêmes, et elles avaient DÉJÀ divergé sur l'encodage : ``utf8``
    dans trois, ``utf-8`` dans cinq, ``utf-8-sig`` dans une. C'est mot
    pour mot la panne que :func:`parsed_sources` existe pour fermer côté
    Python — un BOM avait sorti ``bretzel/render/__init__.py`` de sept
    balayages pendant des mois, en silence.

    ``strip=True`` par défaut parce que six des neuf réappliquaient
    :func:`strip_js_comments` au point d'appel : une gate qui balaie
    ``_src/`` cherche du CODE, la prose est l'exception.

    Promu le 2026-08-29, quand une dixième en a eu besoin. Migrer les
    neuf autres est une passe à part.
    """
    return {
        p.name: (strip_js_comments(text) if strip else text)
        for p in runtime_slabs()
        for text in (p.read_text(encoding="utf-8"),)
    }


def assert_runtime_sweep_is_not_vacuous() -> None:
    """Le pendant de :func:`assert_sweep_is_not_vacuous`, côté runtime."""
    slabs = runtime_slabs()
    # 19 modules mesurés le 2026-08-03. Le plancher est serré à dessein :
    # à 15 il aurait fallu en perdre quatre avant que quiconque s'en
    # aperçoive, et un balayage amputé est exactement ce que ce garde-fou
    # existe pour attraper.
    assert len(slabs) >= 18, (
        f"le balayage ne visite plus que {len(slabs)} modules sous "
        f"{RUNTIME_SRC_DIR} (19 mesurés le 2026-08-03) — vérifie le chemin "
        f"avant de croire qu'une gate runtime passe."
    )


@functools.cache

def theme_slot_strings(source: str) -> list[tuple[str, str]]:
    """``(clé, chaîne de classes)`` pour chaque entrée de dict littérale
    d'un ``theme.py``.

    En AST, pas en regex, pour DEUX raisons, chacune mesurée :

    1. Une string Python implicitement concaténée sur plusieurs lignes (la
       forme de TOUS les thèmes du dépôt) demanderait un quantificateur
       imbriqué côté regex, qui part en backtracking catastrophique dès
       qu'une entrée ne matche pas — la gate passait de 0,1 s à plus de
       2 minutes.
    2. Une regex sur la source brute lit aussi les COMMENTAIRES. Écrit le
       2026-08-15 : ``test_ring_offset_matches_its_surface`` rougissait sur
       le commentaire qui EXPLIQUE la faute qu'elle interdit, dans le
       fichier même où elle venait d'être corrigée.

    Promu ici depuis ``test_hover_only_controls_reachable.py`` le
    2026-08-15, quand une DEUXIÈME gate en a eu besoin — même geste que
    ``strip_js_comments`` juste au-dessus.
    """
    out: list[tuple[str, str]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values, strict=False):
            if (
                isinstance(key, ast.Constant)
                and isinstance(key.value, str)
                and isinstance(value, ast.Constant)
                and isinstance(value.value, str)
            ):
                out.append((key.value, value.value))
    return out

_ATTR_VALUE = re.compile(r'=\s*"[^"]*"')


def in_text_content(html: str, needle: str) -> bool:
    """``needle`` est-il du CONTENU du DOM, et non une valeur d'attribut ?

    Le discriminant dont toute gate a besoin dès qu'elle demande « est-ce
    que ça s'AFFICHE ? ». Sans lui, ``input.placeholder`` — qui n'est
    qu'un attribut — passe pour un slot de contenu, et une gate se met à
    exiger d'un attribut HTML qu'il porte du balisage.

    Approximation assumée : on neutralise toute valeur d'attribut par un
    remplacement de motif, donc un ``>`` DANS une valeur d'attribut n'est
    pas géré. Suffisant ici — les deux appelantes cherchent une sentinelle
    qu'elles ont elles-mêmes injectée.

    Promue ici le 2026-08-18, quand la gate des échappatoires `render=` a
    eu besoin du même test que celle du contrat de slot textuel.
    """
    return needle in _ATTR_VALUE.sub("=''", html)


#: Le mot OBLIGATOIRE que quatre composants exigent pour se construire —
#: toujours pour une raison d'accessibilité ou de validité HTML, jamais
#: pour une raison de comportement. Mesuré le 2026-08-19 : sans cette
#: table, ces quatre-là sortaient EN SILENCE du balayage des gates
#: auto-découvrantes.
#:
def _datatable_bare_args() -> dict[str, object]:
    """Les trois arguments obligatoires de ``ui.datatable``.

    Importés à l'appel — ``tests.audit`` porte déjà la sous-classe
    d'état sonde et la colonne, et les redéfinir ici en ferait une
    seconde version qui dériverait.
    """
    from tests.audit.test_binding_completeness import (
        _dt_column,
        _DatatableProbe,
    )

    return {
        "state": _DatatableProbe,
        "columns": [_dt_column("name", label="Name")],
        "rows": [{"name": "a"}, {"name": "b"}],
        "search": False,
    }


#: ⚠️ Volontairement séparé de ``CONSTRUCT`` (tests/audit), qui répond à
#: une AUTRE question : « comment poser un binding sur la prop ``p`` ».
#: Les fusionner a fait rougir deux gates de slot le 2026-08-19 — un
#: bâtisseur qui ignore ``p`` pour satisfaire la construction nue fait
#: croire aux gates de binding que la prop a été appliquée.
_BARE_ARGS: dict[str, dict[str, object]] = {
    "Image": {"alt": "probe"},
    "Iframe": {"title": "probe"},
    "MetaTag": {"name": "probe", "content": "probe"},
    "Title": {"text": "Probe"},
    # Datatable est arrivé ici le 2026-09-07, en déclarant son
    # ``item_click`` : déclarer un event le fait entrer dans le
    # recensement de ``wired_couples``, donc dans les gates qui bâtissent
    # une instance CÂBLÉE — et il exige `state`, `columns` et `rows`.
    # Bâti dans sa forme NON interactive (``search=False``) : une
    # interactive refuse légitimement de se construire hors d'une zone
    # ``@refreshable``. Même forme que son entrée de ``CONSTRUCT``, et
    # c'est voulu que les deux tables se ressemblent sans fusionner —
    # elles répondent à deux questions (cf. le commentaire au-dessus).
    "Datatable": _datatable_bare_args,
}


def bare_kwargs(cls: type) -> dict[str, object]:
    """Le mot obligatoire de ce composant, s'il en exige un.

    Exposé pour les gates qui ont besoin de l'INSTANCE et pas du HTML
    (poser un attribut post-hoc, comparer deux constructions). Elles
    peuvent alors bâtir elles-mêmes sans re-deviner ce que le socle
    exige — c'est cette redevinette qui faisait sortir Image, Iframe,
    MetaTag et Title du balayage de plusieurs gates.
    """
    args = _BARE_ARGS.get(cls.__name__, {})
    return dict(args() if callable(args) else args)


def walk_elements(node: Any) -> Iterator[Element]:
    """Tous les ``Element`` d'un arbre de rendu, racine comprise.

    Promu ici le 2026-08-21, après une TROISIÈME copie. Les deux
    précédentes (``test_declared_event_is_reachable``,
    ``test_picked_is_not_colour_only``) descendaient sur
    ``hasattr(child, "tag")`` — donc elles **sautaient silencieusement
    tout sous-arbre emballé dans un** :class:`~bretzel.core.tree.FragmentNode`,
    qui porte des enfants sans porter de tag. Un composant qui groupe ses
    nœuds sortait de leur balayage sans que rien ne le dise : la forme
    exacte de trou que ``test_no_gate_swallows_a_component`` interdit
    ailleurs.

    C'est la raison d'être de ce module : un lecteur partagé se corrige
    une fois pour tout le monde.
    """
    if isinstance(node, Element):
        yield node
        for child in node.children:
            yield from walk_elements(child)
    elif isinstance(node, FragmentNode):
        for child in node.children:
            yield from walk_elements(child)


def _server_handler() -> None:  # pragma: no cover — jamais appelé, câblé
    """Handler serveur factice — AU NIVEAU MODULE à dessein.

    Un ``def`` imbriqué dans un test porte ``<locals>`` dans son qualname
    et le socle le REJETTE (``HandlerError``) — cf. ``traps.md``
    § « Closure capturée ». Une gate s'y est déjà fait prendre avec cinq
    faux échecs ; le piège se paie une fois, ici, plutôt qu'à chaque gate
    qui a besoin d'un ``on_<event>=`` callable.
    """


def wired_component(cls: type, event: str, **extra: Any) -> Component:
    """Le composant construit avec un handler SERVEUR sur ``event``.

    Le socle exige parfois un argument positionnel — c'est ``bare_kwargs``
    qui le sait. **Aucun rattrapage** : les 97 composants publics se
    construisent tous ainsi, mesuré sur les 104 couples (composant,
    event) le 2026-08-19. Un ``except`` ici ferait sortir en silence le
    premier qui casserait, ce que ``test_no_gate_swallows_a_component``
    interdit.

    À appeler DANS un ``render_isolated()`` — le rendu de l'instance
    dépend du contexte de requête que ce gestionnaire ouvre.
    """
    return cls(**bare_kwargs(cls), **{f"on_{event}": _server_handler}, **extra)


def wired_couples() -> list[tuple[type, str]]:
    """Les couples (composant, event) que le catalogue DÉCLARE.

    La population dont sortent les 104 couples de référence. Chaque gate
    filtre ensuite ce qui l'intéresse (celles-ci posent un ``hx-post``,
    celles-là atterrissent sur un input caché) — mais elles partent
    toutes du même recensement, sinon leurs planchers dérivent l'un de
    l'autre en prétendant mesurer la même chose.
    """
    return [
        (cls, event)
        for cls in public_component_classes()
        for event in getattr(cls, "EVENTS", ())
    ]


def rendered_html_of(
    cls: type, *, prop: str | None = None, value: Any = None
) -> str | None:
    """Le HTML d'un composant, bâti par la table PARTAGÉE ``CONSTRUCT``.

    ``None`` a **un seul** sens : la table DÉCLARE que ce composant a
    besoin d'un contexte qu'un banc ne peut pas fabriquer
    (``_needs_context``, qui lève ``_Skip``). Toute autre erreur de
    construction **remonte** — c'est elle qui empêche un composant de
    sortir du balayage d'une gate sans que personne ne le sache.

    ``CONSTRUCT`` est la table partagée « comment bâtir un composant qui
    exige des arguments ». Sans elle, un ``except TypeError`` renvoie
    ``None`` pour NavbarItem / SidebarItem / ToggleButton — mesuré : 28
    porteurs de scope vus au lieu de 31 — et une gate qui s'appuie
    dessus accuse un scope orphelin là où c'est sa propre construction
    qui a échoué.

``prop`` / ``value`` posent une SONDE sur une prop — ``src="/x"``,
    ``size="lg"``, ``icon="check"``. C'est le même protocole que
    ``CONSTRUCT`` (classe, nom de prop, valeur), donc un composant qui
    exige un contexte reste construit correctement au lieu d'échouer et
    de sortir du balayage. Sans ``prop``, la construction est nue.

    ⚠️ L'``except Exception: return None`` qui vivait ici jusqu'au
    2026-08-19 était la version « composant » du saut silencieux que
    ``test_no_gate_swallows_a_file`` interdit sur les FICHIERS depuis le
    2026-08-15. Il cachait quatre composants — Image, Iframe, MetaTag,
    Title — invisibles aux trois gates qui appellent ici. Le remède est
    le même : compléter la table, puis laisser lever.
    """
    element = rendered_node_of(cls, prop=prop, value=value)
    return None if element is None else serialize(element)


def rendered_node_of(
    cls: type, *, prop: str | None = None, value: Any = None
) -> Element | None:
    """L'ARBRE d'un composant, même construction que le HTML.

    Extrait de :func:`rendered_html_of` le 2026-09-04 : une gate qui a
    besoin des ATTRIBUTS (classes, ``bz-*``, ``style``) les
    re-extrairait sinon d'une chaîne HTML à la regex, ou — pire —
    reconstruirait le composant à sa façon et sortirait du balayage les
    quatre que la table sait bâtir. C'est le point de ``gates.md`` :
    on ne redevine jamais comment construire un composant.

    ``None`` a le même sens unique qu'au-dessus : la table DÉCLARE que
    ce composant exige un contexte qu'un banc ne peut pas fabriquer.
    """
    # Import différé : ``tests.audit`` tire le harness Playwright, que les
    # gates rapides n'ont aucune raison de charger à l'import du module.
    from tests.audit.test_binding_completeness import CONSTRUCT, _Skip

    builder = CONSTRUCT.get(cls.__name__)
    bare = _BARE_ARGS.get(cls.__name__, {})
    try:
        with render_isolated():
            if builder:
                node = builder(cls, prop or "slots", value if prop else {})
            else:
                node = cls(**bare, **({prop: value} if prop else {}))
            return node.render()
    except _Skip:
        return None


def bz_data_of(cls: type) -> str | None:
    """Le ``bz-data`` rendu par un composant, déséchappé — ``None`` s'il
    n'en émet pas (ou s'il est DÉCLARÉ non constructible).

    Rendu pour de vrai plutôt que grep sur la source : c'est la chaîne
    que le navigateur recevra qui compte, pas le littéral Python qui la
    concatène. Le sous-arbre ENTIER est fouillé, pas seulement la root —
    un scope peut vivre sur un panneau téléporté.
    """
    html = rendered_html_of(cls)
    if html is None:
        return None
    match = re.search(r'\sbz-data="([^"]*)"', html)
    return _html.unescape(match.group(1)) if match else None


# ───────────────────────────────────────────────────────────────────────────
# Lire et parser un arbre de sources — sans jamais sauter en silence
# ───────────────────────────────────────────────────────────────────────────
#
# Le motif que ceci remplace vivait dans sept gates, à l'identique :
#
#     try:
#         tree = ast.parse(path.read_text(encoding="utf-8"))
#     except (SyntaxError, UnicodeDecodeError):
#         continue          # ← le fichier sort du balayage, sans un mot
#
# Ce n'était pas théorique. ``bretzel/render/__init__.py`` portait un BOM
# UTF-8 que ``encoding="utf-8"`` laisse en tête de chaîne et qu'``ast.parse``
# refuse : ce fichier était donc HORS du balayage de toutes ces gates, et
# aucune ne le disait. Un fichier sur 344, pendant des mois.
#
# Un saut silencieux est la même maladie qu'une gate vacuous : le plancher
# vérifie « le balayage a parlé », jamais « le balayage a tout lu ». D'où
# les trois propriétés ci-dessous, qui ne sont pas des options :
#
# 1. ``utf-8-sig`` — le BOM est absorbé, pas subi ;
# 2. un fichier illisible ou non-parsable **LÈVE**, il ne disparaît pas ;
# 3. le résultat est mémoïsé par racine — six gates payaient leur propre
#    ``rglob`` sur ``bretzel/``, ~0,16 s chacune.


@dataclasses.dataclass(frozen=True)
class ParsedSource:
    """Un fichier source lu ET parsé. Les deux, parce que les gates ont
    besoin des deux et que les relire séparément, c'est deux occasions de
    diverger sur l'encodage."""

    path: Path
    text: str
    tree: ast.Module


@functools.lru_cache(maxsize=8)
def _parsed_sources(root: Path) -> tuple[ParsedSource, ...]:
    assert root.is_dir(), f"racine de balayage introuvable : {root}"
    out: list[ParsedSource] = []
    failures: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
            tree = ast.parse(text)
        except (SyntaxError, UnicodeDecodeError, OSError) as exc:
            failures.append(f"{path.relative_to(REPO_ROOT)} — {type(exc).__name__}: {exc}")
            continue
        out.append(ParsedSource(path=path, text=text, tree=tree))

    assert not failures, (
        "Des fichiers n'ont pas pu être lus ou parsés, donc TOUTE gate qui "
        "balaie cette racine les ignorerait :\n  " + "\n  ".join(failures) +
        "\n\nC'est remonté plutôt que sauté, exprès : c'est un BOM UTF-8 "
        "silencieux sur bretzel/render/__init__.py qui a fait sortir ce "
        "fichier du balayage de sept gates pendant des mois. Répare le "
        "fichier — ne rétablis pas le saut."
    )
    return tuple(out)


#: Planchers par racine, écrits ici pour que les gates ne les inventent
#: pas chacune dans leur coin (mesuré le 2026-08-15 : 359 fichiers sous
#: ``bretzel/``, 322 sous ``examples/``). Le seuil laisse de la marge pour
#: une réorganisation sans laisser passer un balayage cassé.
PACKAGE_FLOOR = 300
EXAMPLES_FLOOR = 150
#: ``tests/probes/`` : 97 fichiers le 2026-08-19 (52 probes + 45 bancs).
#: Ce dossier n'est PAS collecté par pytest — c'est justement ce qui
#: le fait pourrir, donc son plancher compte double.
PROBES_FLOOR = 80


@functools.lru_cache(maxsize=8)
def _index(root: Path) -> dict[Path, ParsedSource]:
    return {s.path: s for s in _parsed_sources(root)}


def code_string_literals(tree: ast.AST) -> Iterator[ast.Constant]:
    """Les littéraux de chaîne que le programme FABRIQUE — prose exclue.

    Une gate qui cherche du vocabulaire dans du Python (une clé de fil,
    un fragment de JavaScript, un nom de directive) doit lire ce que le
    code PRODUIT, pas ce qu'il raconte. Les commentaires disparaissent
    tout seuls — l'AST ne les garde pas — mais les docstrings, si : ce
    sont de vraies ``ast.Constant``, et une gate naïve lit alors la note
    d'un retrait comme une occurrence vivante. C'est mesuré dans ce
    dépôt : le balayage textuel de ``bretzel/**.py`` remonte un
    ``$bz.resolve`` que personne n'a jamais écrit, uniquement parce que
    deux commentaires expliquent qu'il n'existe pas.

    La règle appliquée est plus large et plus simple que « sauter les
    docstrings » : **une chaîne NUE en instruction est jetée par
    l'interpréteur**, docstring ou pas, donc elle ne peut atteindre
    aucun DOM. On ne descend simplement pas dedans.

    Deux gates recodaient ce filtre à l'identique — ``test_serversync_key``
    et ``test_bz_globals_emitted_by_python_exist_in_js`` — d'où sa place
    ici (cf. ``.claude/bretzel/gates.md`` § lecteurs partagés).
    """
    stack: list[ast.AST] = [tree]
    while stack:
        node = stack.pop()
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node
        stack.extend(ast.iter_child_nodes(node))


def source_of(path: Path) -> ParsedSource:
    """Le fichier LU ET PARSÉ, pris dans le balayage mémoïsé de sa racine.

    Beaucoup de gates parcourent une liste de chemins puis relisent
    chacun pour elles seules — 18 le faisaient encore le 2026-08-19,
    après que ``parsed_sources`` eut été livrée. Elles n'avaient pas
    tort de garder leur ``parametrize`` sur des ``Path`` : c'est ce qui
    donne des ids lisibles. Il leur manquait juste de quoi ALLER
    CHERCHER le texte au lieu de le relire.

    La racine est déduite du chemin (``bretzel``, ``examples``…), donc
    l'appelant n'a rien à déclarer. Un fichier absent du balayage LÈVE —
    même discipline que ``parsed_sources`` : un fichier qui disparaît
    d'un balayage doit le dire.
    """
    root = REPO_ROOT / path.resolve().relative_to(REPO_ROOT).parts[0]
    index = _index(root)
    source = index.get(path.resolve())
    assert source is not None, (
        f"{path} n'est pas dans le balayage de {root} — soit il n'existe "
        f"plus, soit il est hors de cette racine. Une gate qui le lisait "
        f"quand même jugerait un fichier que le reste du dépôt ignore."
    )
    return source


#: 72 ``theme.py`` sous ``bretzel/components`` le 2026-08-19. Le seuil
#: laisse de la marge pour une réorganisation sans laisser passer un
#: balayage mort.
THEMES_FLOOR = 60


def theme_sources(*, floor: int = THEMES_FLOOR) -> list[ParsedSource]:
    """Les ``theme.py`` de composant, lus et parsés — une seule fois.

    Cinq gates recalculaient chacune ``sorted(components.rglob("theme.py"))``
    puis relisaient chaque fichier pour elles seules (mesuré le
    2026-08-19). Elles jugent le MÊME corpus : le lire cinq fois, c'est
    cinq occasions de diverger sur l'encodage, et cinq planchers à écrire
    à la main au lieu d'un.
    """
    sources = [s for s in parsed_sources(COMPONENTS_DIR, floor=PACKAGE_FLOOR // 2)
               if s.path.name == "theme.py"]
    assert len(sources) >= floor, (
        f"seulement {len(sources)} thèmes de composant trouvés (>= {floor} "
        f"attendus) — le balayage est cassé, et toute gate qui affirme "
        f"« aucun thème ne fait X » l'affirmerait sur rien."
    )
    return sources


def parsed_sources(root: Path, *, floor: int) -> list[ParsedSource]:
    """Tous les ``.py`` sous ``root``, lus et parsés, avec plancher.

    ``floor`` est le nombre minimal de fichiers attendus : c'est le
    plancher de non-vacuité, exigé ici plutôt que laissé à la discrétion
    de chaque appelant. Une gate qui balaie zéro fichier affirme « zéro
    contrevenant » en n'ayant rien lu, et c'est le pire vert.
    """
    sources = _parsed_sources(root)
    assert len(sources) >= floor, (
        f"le balayage de {root} ne visite plus que {len(sources)} fichiers "
        f"(>= {floor} attendus) — vérifie le chemin avant de croire qu'une "
        f"gate d'interdiction passe."
    )
    return list(sources)
