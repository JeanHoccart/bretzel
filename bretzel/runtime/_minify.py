r"""Retire les commentaires et l'indentation d'un bundle JS. Rien d'autre.

Pourquoi un minifieur maison, et pourquoi si peu ambitieux
-----------------------------------------------------------

Le charter interdit npm en production ; un minifieur du monde JS
demanderait soit npm, soit un binaire de plus à télécharger. Or la
mesure du 2026-08-27 dit que l'ambition ne sert à rien ici : sur
``runtime.js``, **retirer les seuls commentaires et l'indentation**
donne 286 758 → 107 395 octets, et 90 563 → **31 581 octets gzippés**
(−65 %). Le renommage des variables locales, lui, se paie en risque et
ne rendrait que quelques kilo-octets une fois gzippé — gzip encode déjà
un identifiant répété en une référence.

Donc : on ne fusionne PAS les lignes, on ne réécrit aucun identifiant,
on ne touche à aucun opérateur. Chaque ligne du bundle reste une ligne,
ce qui rend l'insertion automatique de point-virgule (ASI) rigoureusement
inchangée — le mode d'échec classique d'un minifieur naïf.

Le seul vrai piège : ``/``
--------------------------

Un ``//`` n'est un commentaire que s'il n'est pas dans une chaîne, un
gabarit, ou une **expression régulière littérale** — et le bundle en
porte 43. ``x.replace(/\/\//g, '')`` doit survivre intact. Le scanner
suit donc l'état lexical, et décide « littéral régulier ou division »
sur le dernier lexème significatif, l'heuristique standard.

Vérifié par exécution, pas par relecture :
``tests/runtime_js/test_the_minified_runtime_boots.py`` charge le bundle
minifié dans un vrai navigateur et exige que le runtime démarre.
"""

from __future__ import annotations

from typing import Final

#: Après ces caractères, un ``/`` ouvre une expression régulière — jamais
#: une division. ``)`` et ``}`` en sont volontairement absents : ils
#: terminent bien plus souvent une valeur (``(a + b) / 2``) qu'un
#: ``if (x) {} /re/.test(y)``, qui ne s'écrit pas.
_REGEX_CAN_FOLLOW: Final[frozenset[str]] = frozenset("(,=:[!&|?{};+-*%~^<>\n")

#: Les mots-clés après lesquels un ``/`` ouvre une expression régulière.
_REGEX_AFTER_WORD: Final[frozenset[str]] = frozenset(
    {
        "return", "typeof", "instanceof", "in", "of", "new", "delete",
        "void", "throw", "case", "do", "else", "yield", "await",
    }
)

_IDENT_CHARS: Final[str] = (
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$"
)


def _skip_string(src: str, i: int) -> int:
    """Index juste après la chaîne ouverte en ``i`` (``'`` ou ``\"``)."""
    quote = src[i]
    j = i + 1
    while j < len(src):
        if src[j] == "\\":
            j += 2
            continue
        if src[j] == quote:
            return j + 1
        j += 1
    return len(src)


def _skip_template(src: str, i: int) -> int:
    """Index juste après le gabarit ouvert en ``i``.

    Descend dans chaque ``${…}`` : une substitution peut contenir des
    chaînes, des gabarits, des accolades — et un ``//`` qui n'est pas un
    commentaire.
    """
    j = i + 1
    while j < len(src):
        c = src[j]
        if c == "\\":
            j += 2
            continue
        if c == "`":
            return j + 1
        if c == "$" and j + 1 < len(src) and src[j + 1] == "{":
            depth = 1
            j += 2
            while j < len(src) and depth:
                d = src[j]
                if d in "\"'":
                    j = _skip_string(src, j)
                    continue
                if d == "`":
                    j = _skip_template(src, j)
                    continue
                if d == "{":
                    depth += 1
                elif d == "}":
                    depth -= 1
                j += 1
            continue
        j += 1
    return len(src)


def _skip_regex(src: str, i: int) -> int:
    """Index juste après le littéral régulier ouvert en ``i``.

    Les classes ``[...]`` sont suivies parce qu'un ``/`` y est littéral :
    ``/[/]/`` est un motif valide.
    """
    j = i + 1
    in_class = False
    while j < len(src):
        c = src[j]
        if c == "\\":
            j += 2
            continue
        if c == "[":
            in_class = True
        elif c == "]":
            in_class = False
        elif c == "/" and not in_class:
            j += 1
            while j < len(src) and src[j] in "dgimsuvy":
                j += 1
            return j
        elif c == "\n":
            # Un littéral régulier ne franchit pas la ligne : c'était une
            # division. On rend la main juste après le ``/`` d'ouverture.
            return i + 1
        j += 1
    return len(src)


def _regex_may_start(out: list[str]) -> bool:
    """``/`` ouvre-t-il une expression régulière, vu ce qui précède ?"""
    text = "".join(out[-64:])
    stripped = text.rstrip(" \t\r\n")
    if not stripped:
        return True
    last = stripped[-1]
    if last in _REGEX_CAN_FOLLOW:
        return True
    if last in _IDENT_CHARS:
        word = ""
        k = len(stripped) - 1
        while k >= 0 and stripped[k] in _IDENT_CHARS:
            word = stripped[k] + word
            k -= 1
        return word in _REGEX_AFTER_WORD
    return False


def strip_comments(src: str) -> str:
    """``src`` sans ses commentaires — chaînes, gabarits et regex intacts.

    Un commentaire de bloc devient une ESPACE, pas un saut de ligne :
    rendre les lignes qu'il occupait pourrait couper une expression en
    deux et laisser l'ASI insérer un point-virgule.
    """
    out: list[str] = []
    i = 0
    n = len(src)
    while i < n:
        c = src[i]
        if c in "\"'":
            j = _skip_string(src, i)
            out.append(src[i:j])
            i = j
            continue
        if c == "`":
            j = _skip_template(src, i)
            out.append(src[i:j])
            i = j
            continue
        if c == "/" and i + 1 < n:
            nxt = src[i + 1]
            if nxt == "/":
                j = src.find("\n", i)
                i = n if j < 0 else j
                continue
            if nxt == "*":
                j = src.find("*/", i + 2)
                out.append(" ")
                i = n if j < 0 else j + 2
                continue
            if _regex_may_start(out):
                j = _skip_regex(src, i)
                out.append(src[i:j])
                i = j
                continue
        out.append(c)
        i += 1
    return "".join(out)


def minify(src: str) -> str:
    """Le bundle sans commentaires, sans indentation, sans lignes vides.

    Les lignes ne sont jamais fusionnées : l'ASI voit exactement les
    mêmes fins de ligne qu'avant.
    """
    lines = (line.strip() for line in strip_comments(src).splitlines())
    return "\n".join(line for line in lines if line) + "\n"
