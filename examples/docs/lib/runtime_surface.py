"""Introspection du RUNTIME CLIENT — quatre surfaces lues en direct.

Les chapitres existants introspectent du **Python** (une classe d'état,
une signature, l'algèbre d'un ``ClientBinding``). Le runtime, lui, est du
**JavaScript** : ``bretzel/runtime/_src/*.js``. Ce module lit ces sources
pour que la page ``/runtime`` ne recopie rien à la main.

Quatre surfaces :

- :func:`describe_directives` — les directives ``bz-*`` ;
- :func:`describe_magics` — les variables injectées dans une expression ;
- :func:`describe_runtime_api` — la surface de l'objet global ``$bz`` ;
- :func:`describe_runtime_modules` — les modules du bundle.

**Ce que ``implemented`` dit, et ce qu'il ne dit pas.** Le vocabulaire des
directives est déclaré côté Python (:mod:`bretzel.runtime.protocol`, un
``BZ_<NOM>_PREFIX`` par directive) et rebranché à la main côté JS — le
runtime ne peut pas importer Python. L'énumération partant du Python, on
ne peut détecter qu'un seul sens : **déclarée mais jamais branchée**. Le
sens inverse (du JS qui lit un jeton que Python n'émet plus) demanderait
de partir du JS et n'est pas fait ici.

Ce sens-là est déjà gaté au commit par
``tests/consistency/test_python_js_mirror.py``, qui découvre les mêmes
constantes par introspection et exige leur présence dans le bundle. La
page n'est donc pas le seul filet — elle affiche la même vérité, un cran
plus strict : commentaires ôtés (le bundle contient la prose qui
*documente* les directives, y compris celles qu'on retirerait), et par
module source plutôt que sur le bundle concaténé.

Approximation connue : un jeton présent en marqueur plutôt qu'en câblage
(``createComment("bz-if")``) compte comme branché. Le mécanisme voit du
vocabulaire, pas de la sémantique.

**Note de chantier.** Ce module vit à côté de ``introspect.py`` plutôt que
dedans, le temps que le chantier « surface d'API » en cours cesse d'y
travailler. Rien ne justifie deux modules à terme : quand les deux
branches se rejoignent, le contenu d'ici se replie dans ``introspect.py``
et ``runtime_blocks.py`` dans ``blocks.py``.

⚠️ **Les quatre surfaces ne sont pas encore enregistrées** dans le
registre ``SURFACES`` de ``tests/consistency/test_docs_coverage.py`` (même
raison : le fichier est édité en parallèle). Tant que ce n'est pas fait,
un ``CATEGORY_UNCLASSIFIED`` ne fait rougir personne et une regex qui
cesserait de matcher viderait sa table en silence. Les quatre dataclasses
satisfont déjà le protocole ``Classified`` — c'est quatre entrées à
poser, pas du code à écrire.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import bretzel.runtime as _runtime

from bretzel.introspect import CATEGORY_UNCLASSIFIED

_RUNTIME_DIR = Path(_runtime.__file__).resolve().parent
_SRC = _RUNTIME_DIR / "_src"
_PROTOCOL = _RUNTIME_DIR / "protocol.py"

#: Numéro à partir duquel un module du bundle n'est plus le socle mais le
#: moteur d'un composant. Dérivé du préfixe du fichier, donc un module 22+
#: se classe tout seul.
_CORE_MAX = 6


# ── Lecture des sources ────────────────────────────────────────────────

#: Commentaires JS. Troisième copie dans le dépôt : la canonique est
#: ``tests/consistency/_discovery.py:strip_js_comments`` (promue le
#: 2026-08-15). ``examples/`` n'importe jamais ``tests/`` — d'où la copie,
#: alignée à l'identique plutôt que réécrite. Elle porte la même
#: approximation assumée : un ``//`` dans un littéral (``"http://…"``)
#: passe pour un commentaire ; aucun des modules de ``_src/`` n'en
#: contient. Un vrai foyer partagé reste à choisir.
_JS_LINE_COMMENT = re.compile(r"//.*$", re.MULTILINE)
_JS_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def strip_js_comments(source: str) -> str:
    """Le JS privé de ses commentaires.

    Indispensable : l'en-tête de ``02_directives.js`` *documente* les 13
    directives en prose. Balayer le fichier brut trouverait donc la
    documentation, et une directive documentée mais jamais branchée
    passerait pour implémentée — le faux positif exact que cette page
    existe pour rendre impossible.
    """
    return _JS_LINE_COMMENT.sub("", _JS_BLOCK_COMMENT.sub("", source))


@dataclass(frozen=True)
class _Source:
    name: str    # "02_directives.js"
    raw: str     # le fichier tel quel (l'en-tête est un commentaire)
    code: str    # commentaires ôtés


@lru_cache(maxsize=None)
def read_sources() -> tuple[_Source, ...]:
    """Les modules de ``_src/``, lus UNE fois, dans l'ordre du bundle.

    Le glob vit ici et nulle part ailleurs dans le module : écrit deux
    fois, il devient deux façons de devenir silencieusement vide le jour
    où ``_src/`` bouge. (Le dépôt a déjà son helper pour ça —
    ``_discovery.runtime_slabs`` — mais il vit sous ``tests/``, que
    ``examples/`` n'importe pas.)
    """
    return tuple(
        _Source(name=path.name,
                raw=(text := path.read_text(encoding="utf-8")),
                code=strip_js_comments(text))
        for path in sorted(_SRC.glob("[0-9]*_*.js"))
    )


def by_category(ops: list, order: dict[str, int]) -> tuple:
    """Trier par (rang de catégorie, nom) — les catégories arrivent donc
    contiguës, ce dont les mirrors dépendent pour grouper d'un
    ``itertools.groupby`` sans re-trier."""
    return tuple(sorted(ops, key=lambda o: (order.get(o.category, 9), o.name)))


# ── 1. Directives ──────────────────────────────────────────────────────

_DIRECTIVE_DISPLAY: dict[str, tuple[str, str, str]] = {
    # nom → (catégorie, syntaxe, ce qu'elle garantit)
    "bz-data": (
        "structure du DOM",
        'bz-data="{ open: false }"',
        "Ouvre un scope local, keyé par bz-id — il SURVIT au morph d'un "
        "refresh serveur. Dans une méthode du scope, écrire this.champ.",
    ),
    "bz-if": (
        "structure du DOM",
        'bz-if="expr"',
        "Monte / démonte réellement le sous-arbre. Chaque montage repart "
        "d'un arbre frais.",
    ),
    "bz-for": (
        "structure du DOM",
        'bz-for="v in liste :key=v.id :flip"',
        "Itération keyée sur un <template> à racine unique. :key réutilise "
        "les nœuds ; :flip anime le reflow des lignes qui survivent.",
    ),
    "bz-teleport": (
        "structure du DOM",
        'bz-teleport="body"',
        "Projette le contenu ailleurs dans le DOM ; le scope reste résolu "
        "à l'endroit d'origine. Re-projette si la source a changé.",
    ),
    "bz-text": (
        "affichage réactif",
        'bz-text="expr"',
        "textContent suit la valeur. Affichage seul.",
    ),
    "bz-show": (
        "affichage réactif",
        'bz-show="expr"',
        "Bascule display. L'élément reste monté (et reste donc dans le "
        "DOM pour le focus, la mesure, les tests).",
    ),
    "bz-class": (
        "affichage réactif",
        'bz-class="{ actif: open }"',
        "Ajoute / retire des classes par truthiness. Le class= statique "
        "rendu par le serveur est une baseline jamais retirable.",
    ),
    "bz-attr:": (
        "affichage réactif",
        'bz-attr:aria-expanded="open"',
        "Attribut réactif une-voie. false/null/undefined retirent "
        "l'attribut ; sur un champ de formulaire natif, la propriété est "
        "mise à jour aussi (sinon un morph viderait la saisie).",
    ),
    "bz-model": (
        "saisie deux-voies",
        'bz-model="$bz.state.Form.default.email"',
        "Liaison deux-voies, contrôles de formulaire uniquement.",
    ),
    "bz-on:": (
        "geste utilisateur",
        'bz-on:click="open = !open"',
        "Écoute un événement. Un élément marqué aria-disabled ne DÉMARRE "
        "aucune interaction : les événements d'activation sont ignorés, "
        "les autres passent (fermer reste possible).",
    ),
    "bz-init": (
        "cycle de vie du nœud",
        'bz-init="setup()"',
        "Une seule fois, au premier montage du nœud — et pas rejoué par "
        "un re-bind après morph.",
    ),
    "bz-effect": (
        "cycle de vie du nœud",
        'bz-effect="void geom"',
        "Effet réactif continu : re-joué à chaque mutation d'un signal lu.",
    ),
    "bz-ref": (
        "cycle de vie du nœud",
        'bz-ref="track"',
        "Nomme le nœud dans $refs. Enregistré sur tout l'arbre AVANT le "
        "moindre binding, pour qu'un bz-init parent voie un ref enfant.",
    ),
}

_DIRECTIVE_ORDER = {
    "structure du DOM": 0,
    "affichage réactif": 1,
    "saisie deux-voies": 2,
    "geste utilisateur": 3,
    "cycle de vie du nœud": 4,
}


@dataclass(frozen=True)
class DirectiveOp:
    name: str            # "bz-show", "bz-on:"
    category: str
    syntax: str
    doc: str             # la garantie, en français — glose éditoriale
    constant: str        # la constante Python qui la déclare
    protocol_note: str   # le commentaire porté par cette constante
    implemented: bool    # un module de _src/ la branche (commentaires ôtés)


_PROTOCOL_COMMENT = re.compile(
    r'^(?:BZ_\w+_PREFIX)\s*:.*?=\s*"(?P<value>[^"]+)"\s*(?:#\s*(?P<note>.*))?$',
    re.MULTILINE,
)


@lru_cache(maxsize=None)
def protocol_notes() -> dict[str, str]:
    """``valeur → commentaire`` lu dans ``protocol.py``.

    Le commentaire de fin de ligne EST la définition que le socle donne
    de sa propre directive. On l'affiche telle quelle, à côté de la glose
    éditoriale, plutôt que de la laisser recouvrir en silence par une
    seconde formulation qui pourrait la contredire.
    """
    source = _PROTOCOL.read_text(encoding="utf-8")
    return {
        m.group("value"): (m.group("note") or "").strip()
        for m in _PROTOCOL_COMMENT.finditer(source)
    }


@lru_cache(maxsize=None)
def describe_directives() -> tuple[DirectiveOp, ...]:
    """Les directives ``bz-*``, énumérées depuis l'API publique du socle.

    Une entrée absente de :data:`_DIRECTIVE_DISPLAY` sort en
    ``CATEGORY_UNCLASSIFIED`` : elle s'affiche quand même (rien n'est
    perdu) et, une fois la surface enregistrée dans le registre de
    ``test_docs_coverage.py``, elle fera rougir la gate — pour qu'un
    humain la classe exprès plutôt que par défaut.

    ``implemented`` est cherché dans TOUS les modules de ``_src/``, pas
    dans le seul moteur de directives : ``bz-data`` est matérialisé par
    ``03_scope.js``, et déplacer un autre câblage d'un module à l'autre
    est un refactor légitime qui ne doit pas déclencher une fausse
    alerte.
    """
    notes = protocol_notes()
    sources = read_sources()
    ops: list[DirectiveOp] = []
    for const in dir(_runtime):
        if not (const.startswith("BZ_") and const.endswith("_PREFIX")):
            continue
        value = getattr(_runtime, const)
        category, syntax, doc = _DIRECTIVE_DISPLAY.get(
            value, (CATEGORY_UNCLASSIFIED, f'{value}="…"', "")
        )
        ops.append(DirectiveOp(
            name=value,
            category=category,
            syntax=syntax,
            doc=doc,
            constant=const,
            protocol_note=notes.get(value, ""),
            implemented=any(f'"{value}"' in s.code for s in sources),
        ))
    return by_category(ops, _DIRECTIVE_ORDER)


_ORDER_RE = re.compile(r'const ORDER = \[(?P<body>[^\]]*)\]')


@lru_cache(maxsize=None)
def binding_order() -> tuple[str, ...]:
    """L'ordre dans lequel les directives d'un MÊME élément sont câblées,
    lu dans le moteur. Il n'est pas cosmétique : ``ref`` d'abord (un
    voisin peut le lire), ``init`` en dernier (le nœud est entièrement
    câblé quand il tourne)."""
    for source in read_sources():
        match = _ORDER_RE.search(source.code)
        if match:
            return tuple(re.findall(r'"([^"]+)"', match.group("body")))
    return ()


# ── 2. Magics d'expression ─────────────────────────────────────────────

_MAGIC_DISPLAY: dict[str, tuple[str, str]] = {
    "$scope": ("portée", "Le scope bz-data courant. Il est aussi sur la "
                         "chaîne de portée, donc un nom nu le lit."),
    "$el": ("le nœud", "L'élément qui porte la directive."),
    "$refs": ("le nœud", "Les nœuds nommés par bz-ref dans ce scope."),
    "$event": ("l'événement", "L'événement DOM — dans un bz-on: seulement."),
    "$value": ("l'événement", "La valeur écrite — dans un bz-model seulement."),
    "$dispatch": ("agir", "$dispatch(nom, detail) — un CustomEvent qui "
                          "remonte depuis $el."),
    "$nextTick": ("agir", "$nextTick(fn) — après le flush des signaux, "
                          "donc après que le DOM ait été réécrit."),
}

_MAGIC_ORDER = {"portée": 0, "le nœud": 1, "l'événement": 2, "agir": 3}

_NEW_FUNCTION = re.compile(r"new Function\((?P<args>[^)]*)\)")


@dataclass(frozen=True)
class MagicOp:
    name: str
    category: str
    doc: str


@lru_cache(maxsize=None)
def describe_magics() -> tuple[MagicOp, ...]:
    """Les variables injectées dans toute expression ``bz-*``.

    Lues à leur source exacte : la liste d'arguments du ``new Function``
    que le compilateur d'expressions construit. Ajouter un magic au
    moteur l'ajoute ici — il n'y a pas d'autre endroit où la liste
    existe.
    """
    names: list[str] = []
    for source in read_sources():
        match = _NEW_FUNCTION.search(source.code)
        if match:
            names = re.findall(r'"(\$[A-Za-z]\w*)"', match.group("args"))
            break
    ops = [
        MagicOp(n, *_MAGIC_DISPLAY.get(n, (CATEGORY_UNCLASSIFIED, "")))
        for n in names
    ]
    return by_category(ops, _MAGIC_ORDER)


# ── 3. Surface $bz ─────────────────────────────────────────────────────

_API_DISPLAY: dict[str, tuple[str, str]] = {
    "signal": ("réactivité",
               "signal(init) → {get, set, peek, subscribe}. get() abonne "
               "l'effet courant, peek() lit sans abonner, set() ne "
               "déclenche rien si la valeur est identique."),
    "effect": ("réactivité",
               "effect(fn) → {dispose}. Tourne tout de suite, re-tourne "
               "quand un signal lu change. Les écritures d'un même tick "
               "sont fusionnées en une seule re-exécution."),
    "computed": ("réactivité",
                 "computed(fn) → {get, peek, dispose}. Dérivation "
                 "mémoïsée, recalculée quand une dépendance bouge."),
    "state": ("état & transport",
              "$bz.state.<Classe>.<clé>.<champ> — le signal d'un champ "
              "d'état client, matérialisé au boot depuis l'enveloppe."),
    "notify": ("état & transport",
               "Pousse un toast dans la pile de notifications."),
    "pending": ("état & transport",
                "pending(élément|action_id, délai_ms) → le signal « une "
                "action est en vol ». Un élément remonte au porteur de "
                "son hx-post ; une chaîne adresse l'action depuis "
                "ailleurs dans la page. Le délai est ce qui évite le "
                "flash sur les allers-retours courts. Côté Python : "
                "``ui.pending()``."),
    "version": ("état & transport",
                "La version de protocole du bundle."),
    "helpers": ("helpers partagés",
                "Les briques partagées des overlays et de la famille "
                "pointer-drag."),
    "num": ("helpers partagés",
            "Primitives numériques pures : précision impliquée par un pas."),
    "multiSelect": ("helpers partagés",
                    "L'algèbre d'appartenance d'une sélection multiple, "
                    "partagée par Select et Combobox."),
    "dnd": ("moteur de geste",
            "Le moteur de glisser-déposer en Pointer Events, partagé par "
            "draggable et dropzone."),
    "verbs": ("helpers partagés",
              "La moitié cliente des VERBES (``bretzel.copy`` …) : une "
              "action du navigateur déclenchée depuis un ``on_*=``. "
              "Seule ``copy`` y vit — ``print`` et ``fullscreen`` "
              "tiennent en une expression que Python écrit en toutes "
              "lettres. Elle porte le repli hors contexte sécurisé, "
              "sans lequel un outil interne servi en ``http://`` sur "
              "une IP locale ne copierait rien, en silence."),
    "locale": ("helpers partagés",
               "Les noms de mois et de jours, dérivés de ``<html lang>`` "
               "par ``Intl``. Python ne peut pas les produire : son "
               "module ``locale`` est un état global au processus."),
}

_API_ORDER = {
    "réactivité": 0,
    "état & transport": 1,
    "helpers partagés": 2,
    "moteur de geste": 3,
    "scope de composant": 4,
    "interne": 5,
}

#: Les clés qui signent un objet « fabrique de scope de composant ». Le
#: classement est MÉCANIQUE : un composant de plus se range tout seul,
#: alors qu'une forme d'API vraiment neuve tombe en non classé.
#: ``makeScope`` est absorbé par ``\w+Scope`` — ne pas le rajouter.
_SCOPE_KEYS = re.compile(r"\b(?:scope|single|multi|common|\w+Scope)\s*[:(]")

#: Candidat « clé d'objet littéral » : un nom en début de ligne indentée,
#: suivi de ``:`` (paire) ou de ``(`` (méthode raccourcie).
_MEMBER = re.compile(r"^(?P<indent> {2,8})(?P<name>\w+)\s*[:(]", re.MULTILINE)


def top_level_keys(body: str) -> tuple[str, ...]:
    """Les clés de PREMIER niveau d'un objet littéral.

    Filtrées par l'indentation minimale rencontrée, et pas par une borne
    fixe : une borne laissait passer les mots-clés du corps des méthodes
    (``if (``, ``queueMicrotask(`` sont indiscernables d'une méthode
    raccourcie pour une regex), et ``$bz.helpers`` sortait avec douze
    membres dont deux inventés.
    """
    if not body.lstrip().startswith("{"):
        return ()   # une fonction ou un scalaire n'a pas de clés — sans ce
                    # garde, le corps d'un ``$bz.notify = function …`` rendait
                    # son premier ``if`` comme un membre de l'API
    candidates = [(m.group("indent"), m.group("name"))
                  for m in _MEMBER.finditer(body)]
    if not candidates:
        return ()
    top = min(len(indent) for indent, _ in candidates)
    return tuple(dict.fromkeys(
        name for indent, name in candidates if len(indent) == top
    ))

_ASSIGN = re.compile(r"(?:window\.)?\$bz\.(?P<name>[A-Za-z_]\w*)\s*=")


@dataclass(frozen=True)
class RuntimeApiOp:
    name: str
    category: str
    module: str
    doc: str
    members: tuple[str, ...]   # les clés de premier niveau, lues en direct

    @property
    def public(self) -> bool:
        return not self.name.startswith("_")


@lru_cache(maxsize=None)
def describe_runtime_api() -> tuple[RuntimeApiOp, ...]:
    """Tout ce que les modules posent sur l'objet global ``$bz``.

    Le préfixe ``_`` fait foi : il classe en « interne » sans qu'on ait à
    tenir une liste (le framework en pose beaucoup, et ce n'est pas une
    décision à prendre à chaque fois). Un nom PUBLIC, lui, doit être
    classé — soit par sa forme (une fabrique de scope se reconnaît), soit
    à la main dans :data:`_API_DISPLAY`.

    ``members`` est lu, jamais écrit à la main : une entrée comme
    ``$bz.helpers`` a dix clés, et les énumérer en prose faisait de la
    onzième un mensonge silencieux.
    """
    ops: list[RuntimeApiOp] = []
    seen: set[str] = set()
    for source in read_sources():
        matches = list(_ASSIGN.finditer(source.code))
        for index, match in enumerate(matches):
            name = match.group("name")
            if name in seen:
                continue
            seen.add(name)
            # Le corps s'arrête à l'assignation SUIVANTE : une fenêtre de
            # taille fixe débordait sur le voisin, et un futur
            # ``$bz.router = makeRouter()`` posé dans un module de
            # composant héritait du ``scope:`` d'à côté — classé « fabrique
            # de scope » avec une doc affirmativement fausse, au lieu de
            # s'arrêter en non classé.
            end = (matches[index + 1].start() if index + 1 < len(matches)
                   else len(source.code))
            body = source.code[match.end():end]
            members = top_level_keys(body)
            if name.startswith("_"):
                category, doc = "interne", ""
            elif name in _API_DISPLAY:
                category, doc = _API_DISPLAY[name]
            elif _SCOPE_KEYS.search(body):
                category = "scope de composant"
                doc = "Fabrique de scope, spreadée dans le bz-data du composant."
            else:
                category, doc = CATEGORY_UNCLASSIFIED, ""
            ops.append(RuntimeApiOp(
                name=name, category=category, module=source.name,
                doc=doc, members=members if not name.startswith("_") else (),
            ))
    return by_category(ops, _API_ORDER)


# ── 4. Modules du bundle ───────────────────────────────────────────────

_HEADER = re.compile(r"^/\*\s*\S+\s+—\s*(?P<title>.*?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class RuntimeModuleOp:
    name: str
    category: str
    title: str
    lines: int


@lru_cache(maxsize=None)
def describe_runtime_modules() -> tuple[RuntimeModuleOp, ...]:
    """Les modules concaténés dans ``runtime.js``, dans l'ordre de
    chargement (le préfixe numérique EST l'ordre topologique : signaux
    avant directives avant scope).

    Le titre vient de la première ligne d'en-tête — donc du texte BRUT,
    l'en-tête étant un commentaire — et la catégorie du numéro. Un module
    ajouté apparaît ici, classé, sans édition.
    """
    ops: list[RuntimeModuleOp] = []
    for source in read_sources():
        header = _HEADER.search(source.raw)
        title = header.group("title").rstrip("*/ ").strip() if header else ""
        ops.append(RuntimeModuleOp(
            name=source.name,
            category=("socle" if int(source.name[:2]) <= _CORE_MAX
                      else "moteur de composant"),
            title=title,
            lines=len(source.raw.splitlines()),
        ))
    return tuple(ops)


@lru_cache(maxsize=None)
def bundle_facts() -> dict[str, int]:
    """Les chiffres du bundle, mesurés — pas annoncés. (Le budget de
    taille que la docstring du build promettait était faux d'un facteur
    2 avant d'être retiré ; on affiche donc ce qu'on mesure.)"""
    core = [m for m in describe_runtime_modules() if m.category == "socle"]
    return {
        "modules": len(describe_runtime_modules()),
        "core_modules": len(core),
        "core_lines": sum(m.lines for m in core),
        "bundle_bytes": (_RUNTIME_DIR / "runtime.js").stat().st_size,
    }
