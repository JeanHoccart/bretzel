"""Gate : une classe Tailwind émise existe LITTÉRALEMENT quelque part.

Le compilateur de prod scanne les fichiers **source** : il ne connaît que
les chaînes littérales. Une classe assemblée à l'exécution ::

    f"data-[open=false]:{closed_translate}"   # ← n'existe dans AUCUN fichier

n'atteint jamais ``style.css``. Le HTML émis, lui, est parfaitement
normal — l'attribut `class` porte la bonne classe, elle n'a simplement
aucune règle derrière.

**Pourquoi c'est un mode d'échec vicieux.** En dev,
``@tailwindcss/browser`` scanne le **DOM vivant** et génère la règle à la
volée : tout marche. En prod, le CSS est compilé depuis les sources : la
règle n'existe pas. Ça ne casse donc **qu'en production**, et aucune
suite ne peut le voir — le HTML est identique des deux côtés, seule la
feuille diffère.

Vécu le 2026-08-07. Le tiroir a perdu son animation en passant le
playground en ``mode="prod"`` : ``data-[open=false]:translate-x-full``
n'était nulle part, donc le panneau n'était plus translaté hors écran,
donc il apparaissait d'un coup au lieu de glisser. Rapporté par
l'utilisateur, pas par un test.

**Ce que la gate compare.** Toute classe du `class=` d'une page du
playground doit se retrouver telle quelle dans ``bretzel/**``,
``examples/**`` ou dans l'entrée de thème (la safelist ``@source
inline(...)``, qui est le canal prévu pour les classes que le scanner ne
peut pas deviner). C'est exactement le corpus que voit le compilateur.

``_KNOWN_MISSING`` est la dette CONNUE, à faire fondre — pas une liste de
cas acceptés. L'assert est une égalité stricte **dans les deux sens** :
réparer une classe sans retirer son entrée fait échouer la gate, donc la
liste ne peut pas pourrir. Son contenu du jour est commenté à sa
déclaration, et nulle part ailleurs — un inventaire recopié dans ce
docstring se serait contredit avec lui au premier fix, ce qui est
précisément arrivé le jour de son écriture.
"""

from __future__ import annotations

import html as html_lib
import importlib
import pkgutil
import re
from pathlib import Path

import pytest
from starlette.testclient import TestClient

_ROOT = Path(__file__).resolve().parents[2]

#: ``(?<![\w:-])`` : ne matcher QUE l'attribut `class`, jamais `bz-class`
#: ni `bz-attr:class`, dont la valeur est une EXPRESSION JavaScript. Sans
#: ce garde, la sonde découpait du code en « classes » et rendait 1 149
#: fausses alertes au lieu de 28.
_CLASS_ATTR = re.compile(r'(?<![\w:-])class="([^"]*)"')

#: Dette CONNUE — cf. le docstring. À faire fondre, pas à allonger.
#:
#: Partie de 28 le 2026-08-07, tombée à 5 le jour même :
#:
#: - les 4 translates du tiroir → écrits en entier dans son thème ;
#: - les 16 `grid-cols-N` / `basis-1/N` → `_LAYOUT_CLASSES` dans la
#:   safelist, clôturée sur le domaine ET sur les breakpoints (leur
#:   valeur est un scalaire d'exécution, donc aucun littéral n'est
#:   possible — c'est exactement ce à quoi sert une safelist) ;
#: - les 3 `*-current/*` → la safelist développe désormais `current`
#:   via `resolve_slot_or_keyword`, la MÊME fonction que le rendu.
#:
#: Ce qui reste n'est PAS du Tailwind : cinq classes de charts définies
#: dans un `<style>` inline du composant. Le compilateur n'a donc rien à
#: en faire, et leur présence ici est une limite de la sonde, pas une
#: dette de rendu. Les distinguer proprement (un préfixe réservé qu'on
#: pourrait exclure) fondrait la liste à zéro.
_KNOWN_MISSING = {
    "bz-scatter-series-0", "bz-scatter-series-1",
}

#: **Exemptées, pas endettées** — et la différence a coûté une fausse
#: dette pendant des semaines. ``ui.code`` surligne avec Pygments, dont
#: les classes de jetons (``kc`` = mot-clé constant, ``nf`` = nom de
#: fonction, ``s1``/``s2`` = chaînes…) sont stylées par la feuille que
#: ``render/shell.py`` injecte — ``HtmlFormatter.get_style_defs('.bz-code')``.
#: Tailwind n'a donc rien à en faire, et leur absence du corpus est
#: CORRECTE. Trois d'entre elles vivaient dans ``_KNOWN_MISSING`` comme
#: une dette à fondre, ce qu'elles ne seront jamais.
#:
#: L'exemption se MÉRITE : ``test_the_pygments_tokens_are_really_styled``
#: exige que la feuille de surlignage définisse chacune. Sans ça, ce bloc
#: deviendrait le tapis sous lequel on pousse une vraie classe manquante.
#: ⚠️ ``nb`` (``Name.Builtin``) a rejoint la liste le 2026-09-10, et il
#: y manquait depuis toujours : un ``nb`` littéral traînait dans
#: ``examples/mad`` — variable française pour « nombre » — et
#: satisfaisait le corpus PAR ACCIDENT. L'app retirée, le jeton est
#: apparu. C'est le cas d'école d'une gate verte pour la mauvaise
#: raison : elle mesurait la présence d'une chaîne, pas la nature de
#: la classe.
#: ⚠️ ``nt`` (``Name.Tag``) a rejoint la liste le 2026-09-20, pour la
#: MÊME raison et par la même porte : le corpus le contenait grâce à un
#: ``voisine(nt)`` de ``lint/rules/sizes.py``, coupé en jeton par la
#: parenthèse. La traduction du message en anglais a retiré l'accident,
#: et le jeton est apparu. Deux fois le même mécanisme : la gate mesure
#: une chaîne, et une chaîne de prose peut la satisfaire.
_PYGMENTS_TOKENS = {
    "c1", "kc", "kd", "mf", "nb", "nd", "nf", "nt", "nv", "s1", "s2", "sb",
    "sd",
}


#: Ce qui peut faire partie d'un candidat Tailwind. Sert de FRONTIÈRE :
#: une classe collée à l'un de ces caractères n'est pas la classe, c'est
#: un autre mot qui la contient.
_TOKEN_CHAR = r"[A-Za-z0-9_\-:/.%!&>#\[\]]"


#: Une classe entièrement faite de caractères de candidat : elle est
#: alors un JETON du corpus, donc décidable par appartenance à un
#: ensemble. Celles qui portent autre chose (le ``=`` de
#: ``data-[open=false]:w-0``) retombent sur le regex.
_TOKEN_ONLY = re.compile(rf"{_TOKEN_CHAR}+")


def corpus_tokens(haystack: str) -> frozenset[str]:
    """Tous les jetons du corpus, découpés UNE fois.

    ⚠️ C'est ce qui rend la gate tenable. La première version cherchait
    chaque classe par un ``re.search`` avec deux lookarounds sur les
    **6 Mo** du corpus : mesuré en A/B alterné dans le même process,
    **1,71 ms → 109,5 ms par classe**, soit ×64, et 1 242 classes émises
    — 136 s par balayage, deux balayages par run. Ce seul fichier est
    passé à **358 s** dans une suite que le charter documente à 3–7 min.

    Précompiler le motif n'y changeait rien (109,6 contre 109,5) : le
    coût est le balayage des 6 Mo, pas la compilation. Le découpage, lui,
    coûte **0,36 s** pour 41 863 jetons distincts, et rend le prédicat
    O(1).
    """
    return frozenset(_TOKEN_ONLY.findall(haystack))


def is_literally_present(
    cls: str, haystack: str, tokens: frozenset[str] | None = None
) -> bool:
    """La classe existe-t-elle **en tant que telle** dans le corpus ?

    Une simple sous-chaîne ne suffit pas, et ce n'était pas théorique :
    la classe Pygments ``kc`` était réputée présente parce qu'un exemple
    écrivait le mot « pkce ». Le compilateur Tailwind, lui, découpe des
    candidats sur des frontières — il n'aurait jamais généré ``kc``.
    Une gate plus laxiste que l'outil qu'elle simule rend un vert qui ne
    veut rien dire.

    Mesuré le 2026-08-24 : **9 classes sur 1 242** ne tenaient que par
    cet accident (les onze jetons Pygments, moins ceux déjà déclarés).

    ``tokens`` est le découpage de :func:`corpus_tokens`. Quand il est
    fourni ET que la classe n'est faite que de caractères de candidat,
    l'appartenance à l'ensemble est **exactement** le prédicat des deux
    lookarounds — une suite maximale de ces caractères est bornée par
    des caractères qui n'en sont pas. Sinon on retombe sur le regex,
    dont c'est alors le seul appel.
    """
    if tokens is not None and _TOKEN_ONLY.fullmatch(cls):
        return cls in tokens
    return re.search(
        rf"(?<!{_TOKEN_CHAR}){re.escape(cls)}(?!{_TOKEN_CHAR})", haystack
    ) is not None


def _sources() -> str:
    """Le corpus que le compilateur scanne, concaténé."""
    parts: list[str] = []
    for pattern in ("bretzel/**/*.py", "examples/**/*.py", "bretzel/**/*.js"):
        for path in _ROOT.glob(pattern):
            if "__pycache__" in str(path) or "archive" in str(path):
                continue
            parts.append(path.read_text(encoding="utf-8-sig"))
    return "\n".join(parts)


def _playground_paths() -> list[str]:
    import examples.playground.features as features

    paths: set[str] = set()
    for mod_info in pkgutil.iter_modules(features.__path__):
        module = importlib.import_module(
            f"examples.playground.features.{mod_info.name}"
        )
        path = getattr(module, "PATH", None)
        if isinstance(path, str):
            paths.add(path)
    return sorted(paths)


@pytest.fixture(scope="module")
def emitted() -> dict[str, str]:
    """``{classe: le premier chemin qui l'émet}`` sur tout le playground."""
    from examples.playground.main import app

    seen: dict[str, str] = {}
    with TestClient(app) as client:
        for path in _playground_paths():
            body = client.get(
                path, headers={"Accept-Encoding": "identity"}
            ).text
            for match in _CLASS_ATTR.finditer(body):
                # Le HTML échappe `&`, `'`, `>` — or les classes
                # arbitraires en contiennent (`[&>tbody>tr:hover]:…`,
                # `before:content-['']`). Comparer sans dé-échapper
                # produisait 15 fausses alertes.
                for token in html_lib.unescape(match.group(1)).split():
                    seen.setdefault(token, path)
    return seen


@pytest.fixture(scope="module")
def haystack() -> str:
    """Sources + entrée de thème (la safelist en fait partie)."""
    from examples.playground.main import app

    with TestClient(app):
        theme_css = getattr(app, "_theme_css_content", "") or ""
    return _sources() + "\n" + theme_css


#: Une classe qui porte SA PROPRE règle dans le CSS de thème.
#:
#: Troisième catégorie, à côté de la dette et des jetons Pygments — et
#: la seule des trois qui se VÉRIFIE au lieu de se déclarer. Une classe
#: écrite comme sélecteur (``.bz-c-info { … }``) part telle quelle dans
#: la feuille : Tailwind n'a rien à en générer, donc son absence du
#: corpus est correcte, exactement comme pour Pygments.
#:
#: Pourquoi ce n'est pas une exemption de plus : si le générateur cesse
#: d'émettre la règle, le test redevient rouge tout seul. Une liste
#: écrite à la main, elle, aurait couvert le trou.
#:
#: ⚠️ Le découpage en jetons ne peut pas trouver ces classes : ``.`` est
#: un caractère de candidat (``bz-c-info`` vit dans le jeton
#: ``.bz-c-info``, point compris), donc l'appartenance échoue même quand
#: la chaîne est là. C'est correct pour ce que la gate simule — le
#: scanner de Tailwind ferait pareil — et sans objet pour une règle
#: qu'on écrit soi-même.
def _has_its_own_rule(cls: str, theme_css: str) -> bool:
    return re.search(rf"\.{re.escape(cls)}\s*\{{", theme_css) is not None


@pytest.fixture(scope="module")
def missing(emitted, haystack) -> set[str]:
    """Les classes absentes du corpus — calculées UNE fois.

    Les deux bras de la gate ont besoin du même ensemble ; sans fixture
    partagée, le balayage était fait deux fois par run.
    """
    tokens = corpus_tokens(haystack)
    return {
        cls for cls in emitted
        if not is_literally_present(cls, haystack, tokens)
        and not _has_its_own_rule(cls, haystack)
    }


def test_every_emitted_class_is_literal_somewhere(emitted, missing) -> None:
    unexpected = missing - _KNOWN_MISSING - _PYGMENTS_TOKENS
    assert not unexpected, (
        f"{len(unexpected)} classe(s) émise(s) n'existent LITTÉRALEMENT "
        f"dans aucune source, donc elles ne seront pas dans le "
        f"`style.css` compilé — elles n'ont aucun effet en production, "
        f"alors qu'elles marchent en dev (le compilateur navigateur "
        f"scanne le DOM vivant). "
        + ", ".join(f"{c} (vue sur {emitted[c]})" for c in sorted(unexpected))
        + ". Le remède : écrire la classe ENTIÈRE dans le thème plutôt "
        "que de l'assembler en f-string, ou la déclarer dans la "
        "safelist `@source inline(...)` si elle dépend vraiment d'une "
        "valeur d'exécution."
    )


def test_the_known_debt_has_not_been_silently_paid(missing) -> None:
    """Égalité stricte dans l'autre sens : une classe réparée doit sortir
    de la liste, sinon celle-ci pourrit et masque la suivante."""
    healed = _KNOWN_MISSING - missing
    assert not healed, (
        f"ces classes ne manquent plus — retire-les de `_KNOWN_MISSING` : "
        f"{sorted(healed)}"
    )


def test_the_pygments_tokens_are_really_styled() -> None:
    """L'exemption se mérite : la feuille de surlignage les définit-elle ?

    Sans ce contrôle, ``_PYGMENTS_TOKENS`` serait un tapis — on y
    pousserait une vraie classe manquante et la gate resterait verte.
    """
    from bretzel.render.shell import _PYGMENTS_STYLE

    absent = sorted(
        token for token in _PYGMENTS_TOKENS
        if f".bz-code .{token}" not in _PYGMENTS_STYLE
    )
    assert not absent, (
        f"ces jetons sont exemptés parce qu'ils seraient stylés par la "
        f"feuille Pygments — or elle ne les définit pas : {absent}. Soit "
        "ce ne sont pas des jetons Pygments, soit ils n'ont aucun style : "
        "dans les deux cas l'exemption ne tient plus."
    )


def test_the_two_paths_agree(emitted, haystack) -> None:
    """Le raccourci par jetons rend-il le MÊME verdict que le regex ?

    C'est la seule chose qui autorise l'optimisation.

    Comparé sur un sous-ensemble CHOISI, pas sur les 1 242 classes : le
    regex coûte 110 ms pièce, donc tout comparer réintroduirait
    exactement les 136 s qu'on vient de retirer — la vérification
    coûterait plus que le défaut qu'elle garde. Le sous-ensemble porte
    les trois populations où une divergence pourrait se cacher :

    1. **les treize classes déclarées** (``_PYGMENTS_TOKENS`` +
       ``_KNOWN_MISSING``) — ce sont exactement celles où sous-chaîne et
       frontière divergent, donc le cœur du sujet ;
    2. un échantillon déterministe du reste, pour ne pas ne regarder que
       les cas particuliers.

    ⚠️ L'échantillon ne se tire **pas** de la fixture ``missing`` : elle
    est calculée PAR le chemin rapide, donc une mutation qui le rendrait
    laxiste retirerait du même coup ses victimes de l'échantillon. Vérifié
    le 2026-08-24 — dans cette forme-là, remettre la recherche par
    sous-chaîne laissait les huit tests verts.

    Ce qui est volontairement HORS de l'échantillon : les classes qui ne
    sont pas faites que de caractères de candidat (le ``=`` de
    ``data-[open=false]:w-0``). Elles prennent le repli sur regex dans
    les deux appels, donc les comparer serait comparer une fonction à
    elle-même — 480 classes pour zéro information.
    """
    tokens = corpus_tokens(haystack)
    fast = sorted(c for c in emitted if _TOKEN_ONLY.fullmatch(c))
    declared = {c for c in _PYGMENTS_TOKENS | _KNOWN_MISSING if _TOKEN_ONLY.fullmatch(c)}
    sample = sorted(declared | set(fast[::20]))
    divergent = [
        cls for cls in sample
        if is_literally_present(cls, haystack, tokens)
        != is_literally_present(cls, haystack)
    ]
    assert not divergent, (
        "le raccourci par ensemble de jetons ne dit pas la même chose que "
        f"le balayage par regex : {sorted(divergent)[:5]}"
    )
    assert len(sample) >= 40, (
        f"seulement {len(sample)} classes comparées — l'échantillon ne "
        "couvre plus ses trois populations."
    )


def test_the_substring_accident_is_closed() -> None:
    """La mutation, figée : le détecteur distingue-t-il le mot de son morceau ?"""
    assert is_literally_present("kc", 'classes="kc"')
    assert is_literally_present("h-24", "flex h-24 gap-2")
    assert is_literally_present("data-[open=false]:w-0", '"data-[open=false]:w-0"')
    # Les accidents : un mot QUI CONTIENT la classe n'est pas la classe.
    assert not is_literally_present("kc", '{"detail": "pkce"}')
    assert not is_literally_present("h-24", "min-h-24")
    assert not is_literally_present("s1", "bz-s1x")


def test_the_drawer_slides(emitted, haystack) -> None:
    """Le cas qui a produit cette gate, épinglé nommément.

    Une classe de translate absente ne casse rien de visible côté HTML :
    le tiroir s'ouvre, il n'est simplement plus animé. C'est le genre de
    régression qu'on ne remarque qu'à l'œil, des semaines plus tard.
    """
    sides = [c for c in emitted if c.startswith("data-[open=false]:")
             and "translate" in c]
    assert sides, "aucune classe de translate de tiroir n'est émise"
    for cls in sides:
        assert cls in haystack, (
            f"{cls} n'existe dans aucune source : le tiroir n'aura pas de "
            f"translate en prod, donc pas d'animation. Elle doit être "
            f"écrite en entier dans `drawer/theme.py` (clé `closed`), pas "
            f"assemblée dans `drawer.py`."
        )


def test_the_probe_is_not_vacuous(emitted) -> None:
    assert len(emitted) >= 500, len(emitted)


def test_a_class_with_its_own_rule_is_recognised() -> None:
    """Mutation du troisième bras, dans les deux sens."""
    assert _has_its_own_rule("bz-c-info", ".bz-c-info {\n  --bz-src: red;\n}")
    assert _has_its_own_rule("bz-c-info", ".bz-c-info{--bz-src:red}")
    # une MENTION n'est pas une règle : la classe doit être un sélecteur
    assert not _has_its_own_rule("bz-c-info", "/* bz-c-info existe */")
    assert not _has_its_own_rule("bz-c-info", '<span class="bz-c-info">')
    # et un préfixe partagé ne suffit pas
    assert not _has_its_own_rule("bz-c-in", ".bz-c-info { --bz-src: red; }")


def test_the_detector_still_bites() -> None:
    """Mutation : un ``class=`` du HTML rendu est encore extrait.

    La gate confronte les classes ÉMISES au corpus que Tailwind scanne.
    Si l'extraction cessait de matcher, elle comparerait un ensemble vide
    — et une classe assemblée à l'exécution, invisible au compilateur de
    prod, passerait pour couverte.
    """
    found = _CLASS_ATTR.search('<div class="flex gap-2">')
    assert found and found.group(1) == "flex gap-2"
    for licit in ('<div data-class="x">', '<div bz-class="y">'):
        assert not _CLASS_ATTR.search(licit), f"{licit!r} : faux positif"
