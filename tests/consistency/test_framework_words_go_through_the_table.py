"""Un mot que le framework montre à l'écran passe par la table, pas par le code.

Le constat qui a produit cette gate (finding [5] du chantier CRM) : une
moitié des textes visibles de Bretzel étaient des props
(``search_placeholder=``, ``empty_text=``, ``label=``) et l'autre moitié
était **en dur**, sans qu'aucune règle ne dise laquelle serait laquelle.
Un dev français pouvait renommer le vide d'un ``ui.combobox`` mais pas la
croix d'un ``ui.alert``.

Ce que cette gate protège, ce n'est pas « il y a une table » — c'est que
**la table reste la seule porte**. Une phrase écrite en dur ne lève pas,
ne s'affiche nulle part en revue, et ne se voit qu'à l'écran, dans une
langue qu'on ne parle pas.

Pourquoi elle lit l'AST plutôt que le texte
--------------------------------------------
Un ``grep aria_label=`` avait donné 21 sites, et j'ai cru avoir la liste.
L'AST en a trouvé **neuf de plus**, tous écrits ``attrs={"aria-label":
…}`` — la même chose, l'autre forme, invisible à la recherche qu'on fait
quand on cherche la première. L'un d'eux était même en **français** dans
le framework, seul de tout le dépôt.

La règle « il faut une lettre »
--------------------------------
Un littéral sans aucune lettre ne porte aucune langue : ``f"{kind} —
{text}"``, ``" / "``, ``"%"``. Les flaguer ne dirait rien à personne et
pousserait à écrire des séparateurs dans la table.
"""

from __future__ import annotations

import ast
import functools
import re

from bretzel.render.texts import DEFAULT_TEXTS
from tests.consistency._discovery import (
    COMPONENTS_DIR,
    PACKAGE_FLOOR,
    REPO_ROOT,
    parsed_sources,
)

#: 180 fichiers sous ``bretzel/components`` — le même seuil que
#: ``_discovery._SWEEP_FLOOR``, qui borne déjà ce balayage-là.
_COMPONENTS_FLOOR = 180

#: Les kwargs dont la valeur est LUE par un humain ou annoncée par un
#: lecteur d'écran. ``aria_label`` et ``tooltip`` sont les deux formes
#: par lesquelles un composant nomme un contrôle sans texte ; les quatre
#: suivants sont les libellés que les composants se passent entre eux
#: (``_picker_field``, ``show_more``, les graphiques). Mesuré le
#: 2026-08-24 : les six ensemble donnent **zéro** faux positif sur le
#: dépôt, donc les ajouter est gratuit et ferme une porte à l'avance.
_SPOKEN_KWARGS = frozenset({
    "aria_label", "tooltip",
    "placeholder", "label", "clear_label", "trigger_label", "empty_text",
})

#: Les mêmes, écrites en attributs HTML bruts. C'est la forme que le
#: ``grep`` d'origine ne voyait pas.
#:
#: ⚠️ ``title``, ``placeholder`` et ``alt`` sont AUSSI des noms de slot
#: dans les ``theme.py`` — ``{"title": "text-lg font-semibold"}`` est une
#: chaîne de classes, pas une phrase. D'où l'exclusion des thèmes
#: ci-dessous : sans elle la gate remontait 17 faux positifs et se serait
#: fait désarmer pour se taire.
_SPOKEN_ATTRS = frozenset({"aria-label", "alt", "placeholder", "title"})

#: Un ``theme.py`` ne contient QUE des chaînes de classes Tailwind, par
#: construction (``test_theme_docstring_lists_real_slots`` le garde).
_NOT_PROSE = "theme.py"

#: Le nœud de texte du moteur de rendu : ce qui atterrit littéralement
#: entre deux balises. **Les deux orthographes**, et c'est le point :
#: la première version ne connaissait que ``_TextNode``, or 20 des 22
#: modules concernés importent ``Text as TextNode``. Cette branche du
#: détecteur trouvait donc **zéro** contrevenant — elle était vide, et
#: rien ne le disait. Gardée honnête par
#: ``test_both_spellings_of_the_text_node_are_watched``.
_TEXT_NODES = frozenset({"TextNode", "_TextNode"})

_HAS_A_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)


def carries_language(node: ast.expr) -> bool:
    """``True`` si ce littéral porte des MOTS, pas juste de la ponctuation.

    Extrait pour être mutable : c'est la moitié du détecteur qui décide
    des faux positifs, et la muter est la seule façon de vérifier qu'elle
    ne laisse pas tout passer.
    """
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str) and bool(_HAS_A_LETTER.search(node.value))
    if isinstance(node, ast.JoinedStr):
        return any(
            isinstance(p, ast.Constant)
            and isinstance(p.value, str)
            and _HAS_A_LETTER.search(p.value)
            for p in node.values
        )
    # Un choix et un repli comptent autant qu'un littéral nu :
    # ``"Donut" if donut else "Pie"`` et ``s.name or "Series"`` sont
    # exactement la façon dont cinq phrases visibles passaient à travers.
    if isinstance(node, ast.IfExp):
        return carries_language(node.body) or carries_language(node.orelse)
    if isinstance(node, ast.BoolOp):
        return any(carries_language(v) for v in node.values)
    return False


def words_in(tree: ast.Module, *, rel: str = "", attrs: bool = True) -> list[str]:
    """Le détecteur, sur UN arbre.

    Extrait de la boucle de balayage pour que la preuve de morsure
    l'exerce vraiment — un test qui appelle seulement
    :func:`carries_language` juge la moitié du détecteur et rate
    exactement ce qui distingue ``aria_label="Remove"`` (une phrase) de
    ``aria_label=text("badge.remove")`` (une clé).

    Il regarde **un cran** derrière le puits : une constante de module
    passée par son nom est jugée sur sa valeur. C'est la forme par
    laquelle trois phrases visibles ont échappé à la première version —
    ``placeholder=_FILTER_SEARCH_PLACEHOLDER`` n'est pas un littéral,
    donc la gate restait verte en affirmant que la table était la seule
    porte.

    ⚠️ Ce qu'il ne voit PAS, et il faut le savoir : une valeur qui
    traverse le PARAMÈTRE d'une fonction d'aide. Suivre ça demanderait
    un vrai flot de données ; ce qui garde ce reste-là, c'est le
    balayage de prose anglaise fait à la main le 2026-08-24, pas cette
    gate.
    """
    named = {
        node.targets[0].id: node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
    }

    def speaks(value: ast.expr) -> bool:
        if isinstance(value, ast.Name):
            bound = named.get(value.id)
            return bound is not None and carries_language(bound)
        return carries_language(value)

    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg in _SPOKEN_KWARGS and speaks(kw.value):
                    out.append(f"{rel}:{node.lineno} {kw.arg}={ast.unparse(kw.value)}")
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name in _TEXT_NODES and node.args and speaks(node.args[0]):
                out.append(
                    f"{rel}:{node.lineno} {name}({ast.unparse(node.args[0])})"
                )
        elif attrs and isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=False):
                if (
                    isinstance(key, ast.Constant)
                    and key.value in _SPOKEN_ATTRS
                    and speaks(value)
                ):
                    out.append(f"{rel}:{node.lineno} {key.value!r}: {ast.unparse(value)}")
    return out


def hardcoded_words() -> list[str]:
    """Tout littéral porteur de mots posé directement sur un puits visible."""
    out: list[str] = []
    for source in parsed_sources(COMPONENTS_DIR, floor=_COMPONENTS_FLOOR):
        out += words_in(
            source.tree,
            rel=source.path.relative_to(REPO_ROOT).as_posix(),
            attrs=source.path.name != _NOT_PROSE,
        )
    return sorted(out)


#: Mémoïsés : purs, sans argument, et appelés six fois entre les
#: tests de ce fichier — 850 ms mesurés le 2026-08-24.
@functools.lru_cache(maxsize=1)
def keys_called() -> frozenset[str]:
    """Les clés littérales passées à ``text()`` / ``plural()`` / ``template()``.

    On balaie le **premier argument** — sa valeur, ou les littéraux de
    son expression quand c'est un choix (``text("a.x" if flag else
    "a.y")``, quatre sites réels). Pas le reste de l'appel : ``text("k",
    types=accept)`` ne doit pas faire passer ``accept`` pour une clé.

    Sert de contrôle POSITIF au plancher : c'est la preuve que le
    marcheur d'AST reconnaît encore les appels réels.
    """
    called: set[str] = set()
    for source in parsed_sources(REPO_ROOT / "bretzel", floor=PACKAGE_FLOOR):
        for node in ast.walk(source.tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name in ("text", "plural", "template") and node.args:
                called |= _literal_keys(node.args[0])
    return frozenset(called)


def _literal_keys(node: ast.expr) -> set[str]:
    """La ou les clés qu'écrit cette expression, si elle les écrit.

    Un littéral, ou les deux branches d'un choix (``text("a.x" if flag
    else "a.y")``, quatre sites réels). **Pas** les morceaux d'une
    f-string : ``text(f"{key}_one")`` — l'implémentation de ``plural``
    elle-même — donnerait ``"_one"``, qui n'est la clé de rien.
    """
    if isinstance(node, ast.Constant):
        return {node.value} if isinstance(node.value, str) else set()
    if isinstance(node, ast.IfExp):
        return _literal_keys(node.body) | _literal_keys(node.orelse)
    return set()


@functools.lru_cache(maxsize=1)
def keys_referenced() -> frozenset[str]:
    """Toute clé de la table CITÉE quelque part sous ``bretzel/``.

    Plus large que :func:`keys_called`, et c'est voulu : une clé peut
    voyager par une variable avant d'atteindre ``text()`` — les deux
    flèches du carrousel vivent dans un tuple de configuration, et
    ``plural`` reçoit un préfixe dont le suffixe est calculé. Un
    balayage qui n'accepterait que l'appel direct accuserait ces
    entrées-là d'être mortes, et la seule issue serait de le désarmer.

    La règle honnête : une clé que **personne ne nomme** sous
    ``bretzel/`` est morte. Une clé nommée est au moins référencée.
    """
    referenced: set[str] = set()
    for source in parsed_sources(REPO_ROOT / "bretzel", floor=PACKAGE_FLOOR):
        for node in ast.walk(source.tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value in DEFAULT_TEXTS
            ):
                referenced.add(node.value)
    return frozenset(referenced)


def resolvable(used: str) -> set[str]:
    """Les clés de la table qu'un littéral trouvé dans le code atteint.

    ``plural("datatable.results", n)`` n'écrit ni ``…_one`` ni
    ``…_other`` : le suffixe est calculé. Sans cette dérivation, la
    vérification des clés mortes accuserait quatre entrées bien vivantes.
    """
    if used in DEFAULT_TEXTS:
        return {used}
    return {k for k in (f"{used}_one", f"{used}_other") if k in DEFAULT_TEXTS}


# ── (1) Plancher — ancré sur la DÉCOUVERTE de cette gate ───────────────

def test_the_sweep_reads_the_components_and_finds_the_table_in_use() -> None:
    sources = parsed_sources(COMPONENTS_DIR, floor=_COMPONENTS_FLOOR)
    assert len(sources) >= _COMPONENTS_FLOOR

    # Contrôle POSITIF : le balayage doit RECONNAÎTRE les appels réels.
    # Un plancher qui ne compte que des fichiers reste vert quand le
    # marcheur d'AST est débranché (memory
    # ``gate_floors_must_read_the_gate_source``).
    called = keys_called()
    assert len(called) >= 40, (
        f"le balayage ne voit plus que {len(called)} clés de texte appelées "
        f"dans bretzel/ — le marcheur d'AST ne trouve plus les appels, "
        f"donc l'interdiction ci-dessous ne juge rien."
    )


# ── (2) L'interdiction ─────────────────────────────────────────────────

def test_no_component_hardcodes_a_visible_word() -> None:
    offenders = hardcoded_words()
    assert not offenders, (
        f"{len(offenders)} mot(s) visible(s) écrits en dur dans un "
        f"composant — une app ne peut ni les traduire ni les corriger :\n  "
        + "\n  ".join(offenders)
        + "\n\nPose la phrase dans bretzel/render/texts.py::DEFAULT_TEXTS "
          "et appelle text() sur sa clé ici."
    )


def test_every_key_the_code_asks_for_exists_in_the_table() -> None:
    missing = sorted(k for k in keys_called() if not resolvable(k))
    assert not missing, (
        f"{len(missing)} clé(s) appelée(s) mais absente(s) de "
        f"DEFAULT_TEXTS : {missing}. text() lève à l'exécution, donc sur "
        f"la page qui l'affiche — pas ici, où ça se répare."
    )


def test_the_table_has_no_dead_entry() -> None:
    reached = set(keys_referenced())
    for called in keys_called():
        reached |= resolvable(called)
    dead = sorted(set(DEFAULT_TEXTS) - reached)
    assert not dead, (
        f"{len(dead)} entrée(s) de DEFAULT_TEXTS que plus personne "
        f"n'appelle : {dead}. Une table de traduction qui garde ses morts "
        f"fait traduire des phrases qui ne s'affichent nulle part."
    )


def test_a_default_is_never_resolved_at_import() -> None:
    """``reactive_prop(default=text(...))`` figerait l'anglais.

    Le défaut d'une prop est évalué au chargement du module, donc avant
    qu'une app ait déclaré sa langue. Le piège est réel : ``empty_text``
    du ``ui.combobox`` portait ``default="No results"`` et c'est
    exactement pour ça qu'il a fallu le passer à ``None``.
    """
    frozen: list[str] = []
    for source in parsed_sources(COMPONENTS_DIR, floor=_COMPONENTS_FLOOR):
        rel = source.path.relative_to(REPO_ROOT).as_posix()
        for node in ast.walk(source.tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if getattr(func, "id", getattr(func, "attr", "")) != "reactive_prop":
                continue
            for kw in node.keywords:
                if kw.arg != "default":
                    continue
                for sub in ast.walk(kw.value):
                    inner = getattr(sub, "func", None)
                    if inner is not None and getattr(
                        inner, "id", getattr(inner, "attr", "")
                    ) in ("text", "plural"):
                        frozen.append(f"{rel}:{node.lineno}")
    assert not frozen, (
        "text() dans un default de reactive_prop : la valeur est résolue "
        "à l'import, donc en anglais quoi que l'app déclare. Mets "
        f"default=None et résous au rendu. Sites : {frozen}"
    )


# ── (3) La mutation, dans les DEUX sens ────────────────────────────────

def test_the_detector_still_bites_and_spares_its_licit_twin() -> None:
    # Le versant qui MORD : des mots, sous les trois formes.
    for broken in (
        'x = f(aria_label="Dismiss alert")',
        'x = f(tooltip="Clear filters")',
        'x = {"aria-label": "Remove"}',
        'x = _TextNode(f"Max size: {n} MB")',
        'x = _TextNode("Multiple files allowed")',
    ):
        assert words_in(ast.parse(broken)), broken

    # Le versant qui ÉPARGNE — c'est celui qui trouve les faux positifs.
    # La clé passée à text() est elle-même un littéral porteur de
    # lettres : un détecteur qui regarderait « tout littéral du fichier »
    # au lieu de « le littéral POSÉ sur le puits » les flaguerait toutes,
    # et la seule issue serait de le désarmer.
    for licit in (
        'x = f(aria_label=text("alert.dismiss"))',
        'x = f(tooltip=text("datatable.clear_filters"))',
        'x = {"aria-label": text("badge.remove")}',
        'x = {"aria-label": f"{kind} - {label}"}',
        'x = _TextNode(" / ")',
        'x = f(tooltip=None)',
        'x = {"aria-label": "%"}',
        'x = _TextNode(label)',
    ):
        assert not words_in(ast.parse(licit)), licit

    # Et le versant des thèmes : un slot nommé ``title`` porte des
    # classes, pas une phrase — il ne doit mordre QUE hors theme.py.
    slot = 'x = {"title": "text-lg font-semibold"}'
    assert words_in(ast.parse(slot), attrs=True), slot
    assert not words_in(ast.parse(slot), attrs=False), slot

    # Le cran de résolution : une constante de module cachait trois
    # phrases visibles à la première version de cette gate.
    hidden = '\n'.join(['LABEL = "Drop files here"', "x = f(placeholder=LABEL)"])
    assert words_in(ast.parse(hidden)), hidden
    # Et ses jumeaux licites — une constante qui n'est PAS de la prose ne
    # doit rien déclencher, sinon tout nom de champ la ferait rougir, et
    # une clé rangée dans une constante non plus.
    field = '\n'.join(['_FIELD = "bz_dt_filter"', "x = f(name=_FIELD)"])
    assert not words_in(ast.parse(field)), field
    routed = '\n'.join([
        'KEY = "datatable.filter_placeholder"',
        "x = f(placeholder=text(KEY))",
    ])
    assert not words_in(ast.parse(routed)), routed

    # Le choix et le repli : cinq phrases visibles passaient par là.
    for shaped in (
        'x = _TextNode("Donut chart" if donut else "Pie chart")',
        'x = _TextNode(s.name or "Series")',
        'x = {"aria-label": name if name else "Accueil"}',
    ):
        assert words_in(ast.parse(shaped)), shaped
    for shaped_ok in (
        'x = _TextNode(text("chart.donut") if donut else text("chart.pie"))',
        'x = _TextNode(s.name or text("chart.series"))',
    ):
        assert not words_in(ast.parse(shaped_ok)), shaped_ok


def test_both_spellings_of_the_text_node_are_watched() -> None:
    """La branche ``TextNode`` doit VOIR quelque chose sur le vrai corpus.

    Elle était vide sans que rien ne le dise : le détecteur ne connaissait
    que ``_TextNode`` alors que 20 des 22 modules concernés importent
    ``Text as TextNode``. Une branche qui ne s'exerce jamais affirme
    « zéro contrevenant » en n'ayant rien lu — le pire vert, et celui que
    les quatre gardiennes de gates existent pour empêcher.

    On ne compte donc pas des contrevenants (il n'y en a plus) mais des
    APPELS : la forme que le détecteur doit savoir reconnaître.
    """
    seen: dict[str, int] = dict.fromkeys(_TEXT_NODES, 0)
    for source in parsed_sources(COMPONENTS_DIR, floor=_COMPONENTS_FLOOR):
        for node in ast.walk(source.tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name in seen:
                seen[name] += 1
    unseen = sorted(k for k, n in seen.items() if n == 0)
    assert not unseen, (
        f"aucun appel {unseen} dans les composants — soit l'orthographe a "
        f"changé, soit cette branche du détecteur ne juge plus rien. "
        f"Comptes : {seen}"
    )
