"""Toute expression cliente émise doit être du JavaScript LEXABLE.

Le prix d'une expression malformée n'est pas local
--------------------------------------------------
Le runtime compile chaque directive en une fonction, au boot, dans une
seule passe. Une source qui ne lexe pas ne casse donc pas *le composant
fautif* : elle jette au démarrage, ``html.bz-ready`` n'arrive jamais, et
**plus aucune directive de la page** ne s'évalue. Un caractère de trop
éteint l'application entière.

Ce qui a motivé la gate (2026-09-06, commit ``2b185874``)
---------------------------------------------------------
Une :class:`~bretzel.state.scopes.client.ClientExpression` de la page
``diagram`` du playground portait un vrai saut de ligne là où il fallait
la séquence d'échappement. Le JS émis était :

.. code-block:: text

    ($bz.state.DiagramClientEvents.default.log || []).join("
    ")

— un littéral de chaîne non terminé. La page entière était morte.

**Rien dans le dépôt ne pouvait le voir.** L'attribut HTML est
parfaitement formé, l'échappement HTML est correct, le SSR rend 200, et
``bretzel check`` juge du Python. Il a fallu un navigateur et la console.

Deux populations, parce qu'une seule ne suffisait pas
-----------------------------------------------------
1. **Le HTML rendu de chaque composant** — les valeurs de ``bz-on:*``,
   ``bz-effect``, ``bz-class``, ``bz-show``, ``bz-attr:*``. C'est ce que
   le framework LUI-MÊME émet.
2. **Les ``ClientExpression(...)`` écrites en Python**, balayées à l'AST
   sur ``bretzel/`` et ``examples/``. Sans elle la gate serait une
   consolation : la faute qui l'a motivée vivait dans du code d'app, que
   le rendu d'un composant n'atteint jamais.

Ce que la gate NE fait pas
---------------------------
Elle ne PARSE pas du JavaScript — aucun moteur ici, et la contrainte
« zéro dépendance » vaut aussi pour les tests. Elle **lexe** : chaînes,
gabarits, littéraux d'expression rationnelle et commentaires reconnus,
puis saut de ligne brut dans une chaîne, chaîne non terminée, et
délimiteurs équilibrés. C'est strictement moins qu'un parseur — ``a +``
passe — et c'est exactement la classe de faute qui a coûté la page.

Deux limites connues, écrites pour que le lecteur suivant ne croie pas
la promesse plutôt que la portée :

- un gabarit dont l'interpolation contient elle-même un accent grave est
  lu à plat ; le catalogue n'en contient aucun ;
- dans une f-string Python, chaque trou est remplacé par un identifiant
  neutre avant lexage — la gate juge donc la CHARPENTE de l'expression,
  pas ce que le trou contient.
"""

from __future__ import annotations

import ast
import html as _html
import re

import pytest

from tests.consistency._discovery import (
    EXAMPLES_FLOOR,
    PACKAGE_DIR,
    PACKAGE_FLOOR,
    REPO_ROOT,
    parsed_sources,
    public_component_classes,
    rendered_html_of,
    ui_name_of,
)

EXAMPLES_DIR = REPO_ROOT / "examples"

#: Le nom ET la valeur d'un attribut ``bz-*`` dans le HTML sérialisé.
_ATTR = re.compile(r'\s(bz-[a-z0-9:_-]+)="([^"]*)"')

#: Les attributs dont la valeur est du CODE. Le reste du vocabulaire
#: ``bz-*`` porte des données (``bz-data``, gaté par
#: ``test_bz_data_literal_is_well_formed``) ou un nom (``bz-id``,
#: ``bz-model``, ``bz-ref``).
_CODE_PREFIXES = ("bz-on:", "bz-attr:")
_CODE_EXACT = frozenset({"bz-effect", "bz-class", "bz-show"})

#: Ce que ``rendered_html_of`` DÉCLARE non constructible sans contexte.
#: Table nommée, pas plafond chiffré : « pas plus d'un » laisserait
#: passer « un qui sort, un qui rentre ».
ABSTENTIONS = {"link": "exige un contexte parent (déclaré dans CONSTRUCT)"}


# ── Le lexeur ─────────────────────────────────────────────────────────

_PAIRS = {"(": ")", "[": "]", "{": "}"}
_CLOSERS = {v: k for k, v in _PAIRS.items()}

#: Un ``/`` qui SUIT l'un de ces caractères continue une valeur : c'est
#: une division. Partout ailleurs il ouvre une expression rationnelle.
#: (``r.height / 2`` contre ``&& /[^0-9]/.test(x)`` — les deux sont dans
#: le catalogue, à deux composants d'écart.)
_VALUE_ENDERS = frozenset("_$)]}'\"`") | frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
)

#: …sauf quand le mot qui précède est un mot-clé : ``return /x/`` ouvre
#: bien une rationnelle, alors que son dernier caractère est une lettre.
_KEYWORDS = frozenset(
    {
        "return", "typeof", "instanceof", "in", "of", "case", "do", "else",
        "new", "delete", "void", "throw", "yield", "await",
    }
)

_TRAILING_WORD = re.compile(r"[A-Za-z_$][\w$]*$")


def _opens_a_regex(src: str, i: int) -> bool:
    """``src[i] == '/'`` ouvre-t-il une rationnelle plutôt qu'une division ?"""
    before = src[:i].rstrip()
    if not before:
        return True
    word = _TRAILING_WORD.search(before)
    if word is not None:
        return word.group(0) in _KEYWORDS
    return before[-1] not in _VALUE_ENDERS


def js_faults(src: str) -> list[str]:
    """Les fautes de LEXAGE d'une expression cliente — vide si elle passe.

    Renvoie à la PREMIÈRE faute fatale : au-delà, le flux est décalé et
    tout ce qu'on dirait de plus serait du bruit.
    """
    stack: list[tuple[str, int]] = []
    i, n = 0, len(src)
    while i < n:
        ch = src[i]

        # ── commentaires ────────────────────────────────────────────
        if ch == "/" and i + 1 < n and src[i + 1] == "/":
            end = src.find("\n", i)
            i = n if end == -1 else end
            continue
        if ch == "/" and i + 1 < n and src[i + 1] == "*":
            end = src.find("*/", i + 2)
            if end == -1:
                return ["commentaire de bloc non fermé"]
            i = end + 2
            continue

        # ── expression rationnelle ──────────────────────────────────
        if ch == "/" and _opens_a_regex(src, i):
            j, in_class = i + 1, False
            while j < n:
                c = src[j]
                if c == "\\":
                    j += 2
                    continue
                if c in "\n\r":
                    return [
                        "saut de ligne brut dans une expression "
                        "rationnelle — elle n'est pas terminée"
                    ]
                if c == "[":
                    in_class = True
                elif c == "]":
                    in_class = False
                elif c == "/" and not in_class:
                    break
                j += 1
            else:
                return [f"expression rationnelle non terminée (col. {i})"]
            i = j + 1
            while i < n and src[i].isalpha():  # les drapeaux
                i += 1
            continue

        # ── chaînes et gabarits ─────────────────────────────────────
        if ch in "'\"`":
            j = i + 1
            while j < n:
                c = src[j]
                if c == "\\":
                    j += 2
                    continue
                if c in "\n\r" and ch != "`":
                    return [
                        f"saut de ligne BRUT dans un littéral de chaîne "
                        f"(col. {j}) — la chaîne n'est jamais terminée, "
                        f"donc le runtime ne démarre pas. Il faut la "
                        f"séquence d'échappement, pas une vraie fin de "
                        f"ligne."
                    ]
                if c == ch:
                    break
                j += 1
            else:
                return [f"littéral de chaîne non terminé (ouvert col. {i})"]
            i = j + 1
            continue

        # ── délimiteurs ─────────────────────────────────────────────
        if ch in _PAIRS:
            stack.append((ch, i))
        elif ch in _CLOSERS:
            if not stack or stack[-1][0] != _CLOSERS[ch]:
                opened = stack[-1][0] if stack else "rien"
                return [
                    f"`{ch}` col. {i} ferme `{opened}` — délimiteurs "
                    f"croisés ou fermeture en trop"
                ]
            stack.pop()
        i += 1

    if stack:
        return [
            "délimiteur(s) jamais refermé(s) : "
            + ", ".join(f"`{c}` col. {pos}" for c, pos in stack)
        ]
    return []


# ── Population 1 : le HTML rendu de chaque composant ──────────────────


def _is_code_attr(name: str) -> bool:
    return name in _CODE_EXACT or name.startswith(_CODE_PREFIXES)


def emitted_expressions() -> dict[str, list[tuple[str, str]]]:
    """``{composant: [(attribut, expression déséchappée), …]}``.

    Le HTML est RENDU, pas grepé : c'est la chaîne que le navigateur
    reçoit qui doit lexer, pas le littéral Python qui la concatène.
    """
    out: dict[str, list[tuple[str, str]]] = {}
    for cls in public_component_classes():
        html = rendered_html_of(cls)
        if html is None:
            continue
        out[ui_name_of(cls)] = [
            (name, _html.unescape(raw))
            for name, raw in _ATTR.findall(html)
            if _is_code_attr(name)
        ]
    return out


EMITTED = emitted_expressions()


# ── Population 2 : les ``ClientExpression(...)`` du code Python ───────

#: Le trou d'une f-string, remplacé avant lexage. Un identifiant neutre :
#: il occupe une position de VALEUR, ce qu'est toujours une
#: interpolation dans ces expressions (un chemin de store, un littéral
#: JSON, une sous-expression déjà parenthésée par l'algèbre).
_HOLE = "_bz"


def _static_source(node: ast.Call) -> str | None:
    """La source JS d'un appel ``ClientExpression(...)``, ou ``None``.

    Une f-string est rendue lexable en substituant ``_bz`` à chaque
    trou : la charpente (chaînes, délimiteurs) est celle du code émis,
    et c'est elle qu'on juge. Un argument entièrement dynamique
    (variable, appel) sort du balayage — il n'est pas statiquement
    connaissable, et ``test_the_python_sweep_is_not_vacuous`` borne ce
    que ça laisse.
    """
    if not node.args:
        return None
    arg = node.args[0]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    if isinstance(arg, ast.JoinedStr):
        return "".join(
            piece.value
            if isinstance(piece, ast.Constant) and isinstance(piece.value, str)
            else _HOLE
            for piece in arg.values
        )
    return None


def authored_expressions() -> list[tuple[str, int, str]]:
    """``(fichier, ligne, source)`` de chaque ``ClientExpression(...)``
    dont l'argument est statiquement lisible."""
    out: list[tuple[str, int, str]] = []
    for root, floor in (
        (PACKAGE_DIR, PACKAGE_FLOOR),
        (EXAMPLES_DIR, EXAMPLES_FLOOR),
    ):
        for source in parsed_sources(root, floor=floor):
            for node in ast.walk(source.tree):
                if not (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "ClientExpression"
                ):
                    continue
                src = _static_source(node)
                if src is not None:
                    out.append(
                        (
                            str(source.path.relative_to(REPO_ROOT)),
                            node.lineno,
                            src,
                        )
                    )
    return out


AUTHORED = authored_expressions()


# ── Les planchers ─────────────────────────────────────────────────────
#
# Chacun lit la DÉCOUVERTE de cette gate, pas une source fraîche : un
# plancher qui recompterait depuis son propre balayage resterait vert
# avec l'extraction débranchée.


def test_the_render_sweep_is_not_vacuous() -> None:
    total = sum(len(v) for v in EMITTED.values())
    assert len(EMITTED) >= 90, (
        f"seuls {len(EMITTED)} composants se rendent — le bâtisseur "
        f"partagé a cessé de construire ce qu'il construisait."
    )
    assert total >= 400, (
        f"seulement {total} expressions extraites du HTML rendu (563 le "
        f"2026-09-06) — l'extraction ne voit plus ce qu'elle jugeait."
    )


def test_every_watched_family_is_actually_seen() -> None:
    """Les CINQ familles surveillées portent réellement des expressions.

    Une gate qui code en dur des noms d'attributs peut devenir muette
    sans rougir : le jour où ``bz-effect`` est renommé, la branche qui le
    cherche trouve zéro contrevenant, ce qui se lit exactement comme
    « tout est propre ». Le plancher au-dessus ne le verrait pas — il
    compte la population lue, pas ce que le détecteur y reconnaît.
    """
    seen = dict.fromkeys((*_CODE_EXACT, *_CODE_PREFIXES), 0)
    for pairs in EMITTED.values():
        for name, _ in pairs:
            key = next((p for p in _CODE_PREFIXES if name.startswith(p)), name)
            seen[key] = seen.get(key, 0) + 1
    empty = sorted(k for k, count in seen.items() if count == 0)
    assert not empty, (
        f"{empty} : aucune expression trouvée sous ce(s) attribut(s). "
        f"Soit la directive a été renommée et la gate est devenue "
        f"aveugle dessus, soit plus aucun composant ne l'émet — et "
        f"quelqu'un doit trancher plutôt que la laisser pourrir."
    )


def test_the_python_sweep_is_not_vacuous() -> None:
    assert len(AUTHORED) >= 80, (
        f"seulement {len(AUTHORED)} ``ClientExpression(...)`` lisibles "
        f"statiquement (96 le 2026-09-06) — c'est la moitié du balayage "
        f"qui atteint le code d'APP, celle où vivait la faute d'origine."
    )
    assert any("examples" in path for path, _, _ in AUTHORED), (
        "aucune expression d'``examples/`` dans le balayage — la gate ne "
        "regarde plus que le framework, donc plus la population qui l'a "
        "motivée."
    )


def test_the_abstentions_are_declared() -> None:
    """Ni un composant qui sort du balayage en silence, ni une entrée qui
    pourrit parce qu'il y est rentré."""
    measured = {
        ui_name_of(c)
        for c in public_component_classes()
        if rendered_html_of(c) is None
    }
    assert measured == set(ABSTENTIONS), (
        f"abstentions mesurées {sorted(measured)}, déclarées "
        f"{sorted(ABSTENTIONS)}. Un composant qui cesse de se construire "
        f"sort du balayage sans rien casser."
    )


# ── L'interdiction ────────────────────────────────────────────────────


@pytest.mark.parametrize("name", sorted(EMITTED))
def test_emitted_expressions_lex_as_javascript(name: str) -> None:
    for attr, expr in EMITTED[name]:
        faults = js_faults(expr)
        assert not faults, (
            f"``{name}`` émet un ``{attr}`` que le runtime ne peut pas "
            f"compiler.\n"
            f"  expression : {expr!r}\n"
            f"  fautes     : {faults}\n"
            f"  ⚠️ Le prix n'est PAS local : la compilation des directives "
            f"jette au boot, ``html.bz-ready`` n'arrive jamais, et plus "
            f"aucune directive de la page ne s'évalue."
        )


def test_authored_client_expressions_lex_as_javascript() -> None:
    offenders = [
        (path, line, src, faults)
        for path, line, src in AUTHORED
        if (faults := js_faults(src))
    ]
    assert not offenders, (
        "\n".join(
            f"{path}:{line} — {faults}\n    {src!r}"
            for path, line, src, faults in offenders
        )
        + "\n\nUne ``ClientExpression`` malformée éteint la page ENTIÈRE : "
        "le runtime compile toutes les directives au boot, en une passe."
    )


# ── La preuve de morsure, dans les DEUX sens ──────────────────────────


def test_the_lexer_catches_the_real_fault() -> None:
    """La faute exacte du 2026-09-06, reconstruite.

    Le versant qui mord. Sans lui, un lexeur devenu aveugle passerait
    les centaines d'expressions du corpus par arithmétique.
    """
    broken = '($bz.state.X.default.log || []).join("\n")'
    faults = js_faults(broken)
    assert faults and "saut de ligne BRUT" in faults[0], faults


@pytest.mark.parametrize(
    ("src", "why"),
    [
        ('a + "', "chaîne non terminée en fin d'expression"),
        ("f(a", "parenthèse jamais refermée"),
        ("[a, b))", "fermeture en trop"),
        ("(a]", "délimiteurs croisés"),
        ("'x\ny'", "saut de ligne brut, guillemets simples"),
        ("x && /abc", "rationnelle non terminée"),
        ("`gabarit", "gabarit non terminé"),
    ],
    ids=lambda v: v[:24],
)
def test_the_lexer_bites_on_fabricated_faults(src: str, why: str) -> None:
    assert js_faults(src), f"{src!r} ({why}) devrait mordre"


@pytest.mark.parametrize(
    ("src", "why"),
    [
        ("$event.preventDefault()", "un appel nu"),
        ("open ? 'a' : 'b'", "un ternaire"),
        ("r.top + r.height / 2", "une DIVISION, pas une rationnelle"),
        (
            "$event.data != null && /[^0-9.-]/.test($event.data)",
            "une rationnelle à classe de caractères, après un opérateur",
        ),
        (
            r"/^\d{4}-\d{2}-\d{2}$/.test(_val)",
            "une rationnelle en tête d'expression",
        ),
        ("'il n\\'y a rien'", "une apostrophe ÉCHAPPÉE dans une chaîne"),
        ("`ligne\nsuivante`", "un gabarit — le saut de ligne y est LÉGAL"),
        ('x === "a(b"', "un délimiteur orphelin DANS une chaîne"),
        ("(r => { rail_tip_y = r.top })(rect)", "une IIFE fléchée"),
        ("a / b / c", "deux divisions de suite"),
    ],
    ids=lambda v: v[:26],
)
def test_the_lexer_spares_the_licit_twin(src: str, why: str) -> None:
    """Le versant qui ÉPARGNE — il compte autant que celui qui mord.

    Un détecteur qui rougirait sur tout passerait le test du dessus sans
    rien prouver. Et c'est ce versant qui trouve ce qu'on ne cherchait
    pas : les deux seuls bugs de gate trouvés en remboursant la dette du
    2026-08-19 sont venus de là.
    """
    assert not js_faults(src), f"{src!r} ({why}) est LICITE — faux positif"
