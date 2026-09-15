"""Drift gate — a component that uses ``truncate`` must own a width bound.

Bretzel's badge shipped ``truncate`` on its label with no ``min-w-0`` and no
``max-w`` anywhere in its theme — so the class was DEAD (an inline-flex pill
just grows; the ellipsis never fires). ``truncate`` only bites when SOMETHING
constrains the width : ``min-w-0`` (lets a flex child shrink below content) or
a ``max-w-…`` cap. The width can live on a sibling/parent slot, so this gate
works per-THEME-FILE, not per-string : if a component's theme uses
``truncate`` at all, that file must also carry a width mechanism somewhere —
the exact signal that separated the broken badge (truncate, zero width bound)
from the working idiom (sidebar/select/tree, which pair it with ``min-w-0``).

Exempt : the ``text`` primitive, whose ``truncate=`` is an opt-in prop where
the caller owns the surrounding width.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from tests.consistency._discovery import component_sources

#: Preuve de morsure : contrôle POSITIF — l'extraction de classes trouve encore des
#: propriétaires de ``truncate``.
MUTATION_PROOF = "test_the_gate_finds_truncate_owners"

_COMPONENTS = Path(__file__).resolve().parents[2] / "bretzel" / "components"
_EXEMPT = {"primitives/text"}          # opt-in truncate= prop, caller-owned

# A "class string" token looks like a Tailwind utility (lowercase, may carry
# :/-[]().%#{} — the braces are Bretzel's ``{bg_color}`` placeholders). This
# filters out prose/docstrings that merely mention the word.
_CLASS_TOK = re.compile(r"^[a-z0-9][\w:/\[\](){}.%#,!-]*$")

# Tokens that give ``truncate`` a width to bite against.
_WIDTH_PREFIXES = ("max-w-", "w-full", "w-[", "basis-")


def _class_strings(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            toks = node.value.split()
            if toks and all(_CLASS_TOK.match(t) for t in toks):
                out.append(node.value)
    return out


def _rel(path: Path) -> str:
    return path.relative_to(_COMPONENTS).parent.as_posix()


def test_the_gate_finds_truncate_owners() -> None:
    """Plancher de non-vacuité. Le test ci-dessous est une INTERDICTION —
    « aucun ``truncate`` sans borne de largeur ». Il passe aussi bien quand
    plus AUCUN composant n'utilise ``truncate`` : ni le ``rglob``, ni
    l'extraction AST des chaînes de classes, ni le tokenizer ne signalent
    leur propre panne. On vérifie donc qu'il y a encore des propriétaires à
    surveiller."""
    owners = 0
    for py in component_sources():
        toks = {t for s in _class_strings(py) for t in s.split()}
        if "truncate" in toks:
            owners += 1
    assert owners >= 5, (
        f"seulement {owners} fichiers portent un `truncate` dans une chaîne "
        f"de classes (13 fichiers le mentionnaient le 2026-07-29) — soit "
        f"l'extraction AST ne rend plus rien, soit le motif a changé. La "
        f"gate ne vérifie plus grand-chose."
    )


def test_truncate_owner_has_a_width_bound() -> None:
    offenders: list[str] = []
    seen_dirs: set[Path] = set()
    for py in component_sources():
        d = py.parent
        if _rel(py) in _EXEMPT:
            continue
        # aggregate all class strings in the component directory (theme.py +
        # the component module) — width + truncate may sit in different files.
        if d in seen_dirs:
            continue
        seen_dirs.add(d)
        strings: list[str] = []
        for f in d.glob("*.py"):
            strings += _class_strings(f)
        toks = {t for s in strings for t in s.split()}
        if "truncate" not in toks:
            continue
        has_width = "min-w-0" in toks or any(
            t.startswith(_WIDTH_PREFIXES) for t in toks)
        if not has_width:
            offenders.append(_rel(py))
    assert not offenders, (
        "these components use `truncate` with no `min-w-0`/`max-w-*` width "
        "bound → dead CSS (the element grows, no ellipsis): "
        f"{sorted(set(offenders))}"
    )


def test_truncate_does_not_clip_its_own_glyphs() -> None:
    """``truncate`` et ``leading-none`` ne cohabitent pas dans une chaîne.

    Second piège du même utilitaire, sur l'AUTRE axe. ``truncate`` implique
    ``overflow: hidden`` ; avec ``leading-none`` (``line-height: 1``), la
    boîte de ligne vaut exactement la taille de police alors que les glyphes
    en demandent ~1,2em — les jambages de « g » / « p » sont donc **coupés**.

    Mesuré (2026-08-08, navigateur) sur la page de banc de ``bottom_bar``
    avant correction : **102 labels sur 102** avec ``scrollHeight`` 13 pour
    ``clientHeight`` 11. Invisible à l'œil sur une capture pleine page,
    invisible aussi au probe de containment écrit pour l'occasion — il ne
    lisait que ``scrollWidth``. Un défaut de clipping se mesure sur les DEUX
    axes.

    ``leading-tight`` (1,25) laisse la place aux jambages. Le plancher de
    non-vacuité est celui du fichier (``test_the_gate_finds_truncate_owners``).
    """
    offenders: list[str] = []
    for py in component_sources():
        for s in _class_strings(py):
            toks = s.split()
            if "truncate" in toks and "leading-none" in toks:
                offenders.append(f"{_rel(py)} → {s[:60]}…")
    assert not offenders, (
        "ces chaînes posent `truncate` ET `leading-none` sur le même "
        f"élément : {offenders}\n"
        "  `truncate` implique `overflow:hidden` et `leading-none` donne une "
        "boîte de ligne égale à la police — les jambages sont rognés, sur "
        "CHAQUE label, sans que rien ne déborde en largeur. Utilise "
        "`leading-tight`."
    )
