"""HTML / attribute / JS escaping primitives.

Pure ``str -> str`` transforms with no I/O, no dependencies beyond stdlib.
The only callers expected to bypass these are explicit ``HtmlNode`` escape-hatch
nodes in ``tree.py``.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from typing import Any, Final

# ───────────────────────────────────────────────────────────────────────────
# Body / attribute escaping
# ───────────────────────────────────────────────────────────────────────────

# Order matters : ``&`` first to avoid double-encoding.
#
# Do NOT add a "does this string need escaping at all ?" pre-scan in front
# of the loop — measured slower, not faster, on real render values (cf.
# ``traps.md`` § « le garde `faut-il échapper ?` est une PESSIMISATION »).
_HTML_ESCAPES: tuple[tuple[str, str], ...] = (
    ("&", "&amp;"),
    ("<", "&lt;"),
    (">", "&gt;"),
    ('"', "&quot;"),
    ("'", "&#x27;"),
)


def escape_html(text: str) -> str:
    """Escape a string for use in HTML body content.

    Maps ``< > & " '`` to their entity equivalents. Idempotent **only** in
    the absence of pre-existing entities — applying twice will encode the
    ``&`` of ``&amp;`` again. Callers must not double-escape.
    """
    out = text
    for char, entity in _HTML_ESCAPES:
        out = out.replace(char, entity)
    return out


# La table de :func:`escape_attr`. Elle N'EST PLUS dérivée de
# ``_HTML_ESCAPES`` : une valeur d'attribut et un contenu de corps n'ont
# pas les mêmes caractères dangereux, et les confondre coûtait 6 octets
# par apostrophe sur des pages qui en portent des milliers (cf. la note
# sous :func:`escape_attr`).
#
# Les trois octets de contrôle en queue ne terminent pas la valeur mais
# sont silencieusement repliés dans une valeur quotée, ce qui perd de
# l'information.
#
# ``'``, ``=`` et le backtick ont tous les trois été retirés d'ici — même
# raison, mesurée deux fois. Voir :func:`escape_attr`.
_ATTR_ESCAPES: tuple[tuple[str, str], ...] = (
    ("&", "&amp;"),
    ("<", "&lt;"),
    (">", "&gt;"),
    ('"', "&quot;"),
    ("\t", "&#x9;"),
    ("\n", "&#xA;"),
    ("\r", "&#xD;"),
)


#: Le mémo de :func:`escape_attr`. Mesuré le 2026-08-27 sur le playground :
#: une page appelle la fonction ~4 000 fois pour ~1 150 valeurs
#: **distinctes**, et le corpus se stabilise à ~2 400 valeurs pour TOUT le
#: site — donc 99 % de réutilisation d'une requête à l'autre. Une entrée
#: pèse la valeur et son échappé ; 8 192 entrées de ~80 caractères tiennent
#: dans ~1,5 Mo, plafond atteint et jamais dépassé.
_ATTR_CACHE_SIZE: Final[int] = 8192


@lru_cache(maxsize=_ATTR_CACHE_SIZE)
def escape_attr(value: str) -> str:
    """Escape a string for use in a **double-quoted** HTML attribute.

    It is NOT :func:`escape_html` plus extras — the two tables diverged
    on 2026-08-28. This one folds tab / newline / CR, which a bare
    attribute would read as the end of the value, and it leaves ``'``
    alone.

    **Precondition — the caller MUST wrap the result in DOUBLE quotes.**
    Not either style, not any more : ``'`` is no longer escaped, so a
    value placed between single quotes CAN close its attribute early.
    Every call site does wrap that way (:func:`serialize_attrs` builds
    ``name="…"`` ; the f-strings in ``render/shell.py`` quote inline).
    The quoting is what makes the value safe : per the HTML tokenizer a
    quoted value runs to the next matching quote, and ``"`` is escaped
    here, so nothing inside can end the value early or introduce an
    attribute. Enforced by
    ``tests/consistency/test_escape_attr_result_is_quoted.py``, whose
    source guard now REFUSES a single-quoted call site.

    **Three characters have been dropped from this function, twice, for
    the same reason.** ``=`` → ``&#x3D;`` and backtick → ``&#x60;`` went
    on 2026-07-27 ; ``'`` → ``&#x27;`` went on 2026-08-28. All three
    were defence-in-depth against a caller emitting a BARE attribute —
    a case the precondition already excludes — and all three are
    pervasive in what Bretzel actually emits, at 6 bytes instead of 1.
    Measured on the playground : ``=`` appeared 5 000–7 000 times per
    page (Tailwind ``data-[open=false]:…``, JS ``===``, query strings)
    for 25–35 kB, 6–7 % of every response ; ``'`` 7 900 times on
    /datatable and 14 500 on /combobox (every ``bz-*`` ternary and every
    ``bz-class`` list is made of them) for 2,8–4,7 % raw and up to 8 %
    after gzip.

    If you ever add a call site that emits a bare attribute — or one
    that quotes with ``'`` — escape it THERE. Do not re-broaden this
    function and re-inflate every page.

    **Mémoïsé, et :func:`escape_html` ne l'est pas** — l'asymétrie est
    mesurée, pas esthétique. Une valeur d'attribut est presque toujours
    ÉCRITE PAR LE FRAMEWORK : chaîne de classes Tailwind, expression
    ``bz-*``, rôle ARIA. Les données de l'utilisateur, elles, atterrissent
    dans le corps du document, donc dans :func:`escape_html`. Mesuré le
    2026-08-27 sur une page rendue : ``escape_attr`` fait 99 % de succès
    de cache, ``escape_html`` 266 succès pour 2 471 échecs — le mémoïser
    coûterait sans rien rendre.

    Le mémo est le seul état de ce module, et il n'est pas observable :
    la fonction est pure, ses deux tables sont des ``Final``. Le pari
    n'est pas gratuit pour autant — sur un flux SANS aucune réutilisation
    il coûte **+27 %** (mesuré). C'est ce que garde
    ``tests/consistency/test_escape_attr_cache_still_pays.py`` : si un
    jour des données utilisateur passent en masse par des attributs, le
    taux de succès s'effondre et la gate rougit pour qu'on re-décide.
    """
    out = value
    for char, entity in _ATTR_ESCAPES:
        out = out.replace(char, entity)
    return out


# ───────────────────────────────────────────────────────────────────────────
# JS string-literal escaping (for ``bz-*`` attributes carrying JS code)
# ───────────────────────────────────────────────────────────────────────────

# Backslash MUST be first so subsequent inserted backslashes are not
# re-escaped. ``</`` is split to defeat naive HTML parsers that close the
# enclosing ``<script>`` early.
_JS_ESCAPES: tuple[tuple[str, str], ...] = (
    ("\\", "\\\\"),
    ("'", "\\'"),
    ('"', '\\"'),
    ("\n", "\\n"),
    ("\r", "\\r"),
    ("\t", "\\t"),
    ("\b", "\\b"),
    ("\f", "\\f"),
    ("</", "<\\/"),
)


def escape_js(value: str) -> str:
    """Escape a string for inclusion as a JS string literal.

    Targets the ``bz-*`` attribute use case where the runtime evaluates the
    attribute value as a JS expression. After this function the result is
    safe to wrap in single or double quotes inside a JS context.
    """
    out = value
    for char, entity in _JS_ESCAPES:
        out = out.replace(char, entity)
    return out


def escape_inline_json(payload: str) -> str:
    """Defuse ``</`` in a JSON payload embedded inside an HTML tag.

    ``json.dumps`` output is valid JS but a literal ``</bz-envelope>``
    (or any ``</…``) inside a string value would close the host tag
    early during HTML parsing. ``<\\/`` is the standard JSON-safe
    spelling : identical once parsed, inert for the HTML tokenizer.
    Used by :mod:`bretzel.runtime.envelope` for the ``<bz-envelope>``
    and ``<bz-patch>`` payloads.
    """
    return payload.replace("</", "<\\/")


# ───────────────────────────────────────────────────────────────────────────
# Attribute-dict serialization
# ───────────────────────────────────────────────────────────────────────────


class RawAttrValue(str):
    """Marker subclass of ``str`` that bypasses ``escape_attr``.

    Used for attribute values whose content is a JS expression already
    composed by the framework (typically the ``bz-class`` / ``bz-attr:``
    expressions emitted for the client runtime — il n'y a **pas** de
    directive ``bz-bind``, ce nom figurait ici jusqu'au 2026-08-01). The payload is trusted
    to be syntactically valid for an HTML double-quoted attribute — it
    must not contain literal ``"`` chars or other attribute-breaking
    bytes. The framework controls the call site so this is a safe escape
    hatch ; user code never reaches it.
    """

    __slots__ = ()


#: Attributs qui désignent une RESSOURCE À CHARGER, et pour lesquels une
#: valeur vide n'est jamais une intention — c'est un bug.
#:
#: Un attribut vide est résolu contre l'URL du document : ``<img src="">``
#: fait retélécharger LA PAGE COURANTE en croyant charger une image, et
#: ``<iframe src="">`` la met dans elle-même. Rien ne casse à l'écran, donc
#: ça ne se voit que dans les logs du serveur — c'est comme ça que le bug a
#: été trouvé le 2026-08-14, sur ``ui.video``, par l'utilisateur.
#:
#: ⚠️ ``href`` et ``action`` sont VOLONTAIREMENT absents : ``<a href="">``
#: et ``<form action="">`` pointent sur la page courante, ce qui est un
#: usage légitime et courant. La règle ne vaut que pour les attributs de
#: *chargement*, pas de navigation.
_EMPTY_IS_A_BUG: Final[frozenset[str]] = frozenset(
    {"src", "poster", "srcset", "background", "data", "cite"}
)


def serialize_attrs(attrs: Mapping[str, Any]) -> str:
    """Serialize a mapping of HTML attributes into a leading-space string.

    Behaviour :

    - Empty mapping → empty string (no leading space).
    - ``None`` values are skipped.
    - ``True`` emits a bare attribute (``disabled``).
    - ``False`` is skipped.
    - An **empty string on a resource-loading attribute** (:data:`_EMPTY_IS_A_BUG`)
      is skipped — cf. la note de cette constante. Les autres attributs
      gardent leur chaîne vide, qui y est significative : ``alt=""`` fait
      ignorer une image décorative, ``sandbox=""`` est le bac à sable
      maximal, ``value=""`` est un champ vidé.
    - :class:`RawAttrValue` instances are emitted verbatim (the framework
      escape hatch for already-composed JS expressions).
    - Any other value is converted via ``str(...)`` and run through
      :func:`escape_attr` ; the result is double-quoted.

    Order is preserved from the input mapping (``dict`` is insertion-ordered
    in CPython 3.7+, which we rely on).
    """
    parts: list[str] = []
    for name, value in attrs.items():
        if value is None or value is False:
            continue
        if value == "" and name in _EMPTY_IS_A_BUG:
            continue
        if value is True:
            parts.append(name)
            continue
        if isinstance(value, RawAttrValue):
            parts.append(f'{name}="{value}"')
            continue
        escaped = escape_attr(str(value))
        parts.append(f'{name}="{escaped}"')
    if not parts:
        return ""
    return " " + " ".join(parts)
