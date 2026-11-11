"""Text comparison helpers.

:func:`fold` is the ONE form a search compares — on the server here, in
the browser through its twin ``$bz.fold`` (``runtime/_src/locale.js``),
which must give the same string: the combobox and ``filter_each`` bake the
folded text of their options on the server and fold what the user types in
the browser. A recipe of its own in one place makes the same search find a
name in one component and not in another.
"""

from __future__ import annotations

import unicodedata

__all__ = ["fold"]


def fold(text: str) -> str:
    """Case- and accent-insensitive form of ``text``, for comparison only.

    Lowercase, NFKD (an accented letter splits into its base and a mark; a
    ligature or a superscript into plain letters), drop every mark
    (Unicode category M — the same set as JavaScript's ``\\p{M}``),
    lowercase again (NFKD can yield capitals: a black-letter H gives
    « H »), and spell « ß » « ss » and the final sigma the medial one —
    what ``casefold`` adds that matters, and that ``toLowerCase`` cannot
    do. Never shown to anyone: the rendered
    text keeps its accents.
    """
    lowered = text.lower()
    if lowered.isascii():
        # NFKD is the identity on ASCII, which carries no mark: the walk
        # below cannot change a thing.
        return lowered
    decomposed = unicodedata.normalize("NFKD", lowered)
    bare = "".join(c for c in decomposed if not unicodedata.category(c).startswith("M"))
    # The final sigma (U+03C2) becomes the medial one (U+03C3).
    return bare.lower().replace("ß", "ss").replace("\u03c2", "\u03c3")
