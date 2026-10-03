"""Gate : une citation d'une section de ``traps.md`` nomme un titre qui existe.

Le fait gardé
-------------
Le code et la doc renvoient au fichier des pièges **par le titre** d'une
section — ``traps.md`` § « Slot Component stocké sans `adopt_slot` ».
Le fichier n'a pas de numérotation, exprès : dix renvois « Trap #22 »
pointaient dans le vide jusqu'au 2026-08-01. Mais un titre se réécrit
aussi, et un renvoi vers un titre disparu est une fausse piste
silencieuse : le lecteur cherche une section qui n'existe pas, ou pire,
croit qu'un piège est documenté alors que plus rien ne le décrit.

Mesuré le 2026-10-03 : ``traps.md`` venait d'être réécrit en liste
compacte (thèmes en ``##``, pièges en ``###``), et **sur 141 citations
``§``, une seule désignait encore un titre** : 120 nommaient un titre
mort (anglais d'avant la traduction, titres fusionnés, récits retirés),
20 n'avaient pas de titre délimitable. Aucune gate ne les voyait :
``test_documented_paths_exist`` vérifie que ``traps.md`` existe, pas que
la section citée y figure. Les citations ont été repointées vers le titre
qui couvre le même piège, ou retirées quand aucun ne le couvre.

Ce que la gate exige
--------------------
Toute occurrence de ``traps.md`` suivie de ``§`` porte un titre **entre
guillemets** — « … », "…" ou *…* — égal, espaces près, à un titre ``##``
ou ``###`` du fichier. Un ``§`` sans guillemets est refusé aussi : un
titre qu'on ne sait pas délimiter n'est pas vérifiable, et c'est la
forme qu'avaient prise vingt des renvois morts (« § PEP 649 »,
« § A11y »).

Le titre peut passer à la ligne : les préfixes de continuation (``#``
Python, ``//`` et `` * `` JS, ``>`` markdown) sont effacés avant la
lecture, le reste de l'espacement est réduit à une espace.

Ce que cette gate ne voit PAS
-----------------------------
- un titre coupé entre deux littéraux de chaîne (``"… « Une colonne "``
  puis ``f"qui défile ÉCRASE ses items »"``) : la couture reste dans le
  texte lu, donc la citation est refusée. C'est voulu — un grep du titre
  ne la trouverait pas non plus — et le remède est de ne pas couper ;
- un second titre enchaîné (``§ « A » et § « B »``) : seul le premier,
  celui qui suit ``traps.md``, est vérifié ;
- un renvoi qui ne passe pas par ``§`` (« le piège X de ``traps.md`` »,
  une liste de titres en italique) : rien ne le distingue d'une phrase
  qui cite le fichier entier.
"""

from __future__ import annotations

import functools
import re
from pathlib import Path

from tests.consistency._discovery import (
    EXAMPLES_FLOOR,
    PACKAGE_DIR,
    PACKAGE_FLOOR,
    REPO_ROOT,
    parsed_sources,
    runtime_sources,
)

_TRAPS = REPO_ROOT / ".claude" / "bretzel" / "traps.md"

#: Les racines Python balayées, avec leur plancher de fichiers.
_PY_ROOTS = (
    (PACKAGE_DIR, PACKAGE_FLOOR),
    (REPO_ROOT / "examples", EXAMPLES_FLOOR),
    (REPO_ROOT / "tests", 200),
)

#: Un titre de thème (``##``) ou de piège (``###``).
_HEADING = re.compile(r"^#{2,3}[ \t]+(.+?)[ \t]*$")
_FENCE = re.compile(r"^[ \t]*(```|~~~)")

#: Une fin de ligne et le préfixe de la suivante : ``#`` (commentaire
#: Python), ``//`` ou `` * `` (commentaire JS), ``>`` (citation
#: markdown). Remplacée par un ``\n`` nu, ce qui garde les numéros de
#: ligne. L'astérisque n'est pris que suivi d'un blanc : ``*Le titre*``
#: en tête de ligne markdown est un italique, pas une continuation.
_CONTINUATION = re.compile(r"\n[ \t]*(?:#+|//+|\*(?=[ \t])|>)?[ \t]*")

#: ``traps.md``, refermé ou non par des backticks / un astérisque, puis ``§``.
_CITATION = re.compile(r"traps\.md[`*]*\s*§")

#: Le titre qui suit le ``§`` — borné, pour qu'un guillemet jamais refermé
#: n'avale pas la moitié du fichier.
_TITLE = re.compile(
    r"\s*(?:«\s*(?P<chevrons>[^»]{1,200}?)\s*»"
    r'|"(?P<quotes>[^"]{1,200})"'
    r"|\*(?P<stars>[^*]{1,200})\*)"
)

#: Les citations trouvées par le balayage du 2026-10-03, après réparation :
#: 61 (57 en Python, 2 en JS, 2 en markdown). Le plancher laisse de la
#: marge pour des renvois qui partent, pas pour un lecteur cassé — et
#: ``test_the_sweep_finds_citations_in_every_family`` exige en plus que
#: chaque famille en apporte une.
_CITATIONS_FLOOR = 45


def _flat(heading: str) -> str:
    return " ".join(heading.split())


@functools.lru_cache(maxsize=1)
def live_headings() -> frozenset[str]:
    """Les titres ``##`` et ``###`` de ``traps.md``, hors blocs de code."""
    found: set[str] = set()
    in_fence = False
    for line in _TRAPS.read_text(encoding="utf-8-sig").splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        match = None if in_fence else _HEADING.match(line)
        if match:
            found.add(_flat(match.group(1)))
    return frozenset(found)


def citations(text: str) -> list[tuple[int, str | None]]:
    """``(ligne, titre)`` de chaque citation ``§`` du fichier des pièges.

    ``titre`` vaut ``None`` quand le ``§`` n'est pas suivi d'un titre
    entre guillemets — une citation qu'on ne sait pas vérifier.
    """
    flat = _CONTINUATION.sub("\n", text)
    out: list[tuple[int, str | None]] = []
    for cite in _CITATION.finditer(flat):
        line = flat.count("\n", 0, cite.start()) + 1
        title = _TITLE.match(flat, cite.end())
        if title is None:
            out.append((line, None))
            continue
        raw = title.group("chevrons") or title.group("quotes") or title.group("stars")
        out.append((line, _flat(raw)))
    return out


def offenders(
    texts: list[tuple[str, str]], headings: frozenset[str]
) -> list[str]:
    """Les citations qui ne nomment pas un titre vivant — le détecteur."""
    bad: list[str] = []
    for label, text in texts:
        for line, title in citations(text):
            if title is None:
                bad.append(f"{label}:{line} — § sans titre entre guillemets")
            elif title not in headings:
                bad.append(f"{label}:{line} — « {title} »")
    return bad


def _markdown_files() -> list[Path]:
    """La doc écrite à la main : la racine, le funnel, et les ``.md``
    rangés sous les racines de code (README d'exemple ou de suite)."""
    nested = [
        p
        for root in (PACKAGE_DIR, REPO_ROOT / "examples", REPO_ROOT / "tests")
        for p in root.rglob("*.md")
        if "__pycache__" not in p.parts
    ]
    return sorted(
        [*REPO_ROOT.glob("*.md"), *(REPO_ROOT / ".claude" / "bretzel").glob("*.md"), *nested]
    )


@functools.lru_cache(maxsize=1)
def swept_texts() -> tuple[tuple[str, str, str], ...]:
    """``(famille, étiquette, texte)`` de toute la population balayée.

    Trois familles, trois lecteurs : les ``.py`` par ``parsed_sources``
    (plancher compris), les modules du runtime par ``runtime_sources`` —
    commentaires GARDÉS, ce sont eux qui citent — et la doc markdown. Le
    bundle ``runtime.js`` n'est pas lu : il est construit depuis ``_src/``,
    il ne ferait que doubler chaque citation.
    """
    out: list[tuple[str, str, str]] = []
    for root, floor in _PY_ROOTS:
        for source in parsed_sources(root, floor=floor):
            label = source.path.relative_to(REPO_ROOT).as_posix()
            out.append(("python", label, source.text))
    for name, text in runtime_sources(strip=False).items():
        out.append(("js", f"bretzel/runtime/_src/{name}", text))
    for path in _markdown_files():
        label = path.relative_to(REPO_ROOT).as_posix()
        out.append(("markdown", label, path.read_text(encoding="utf-8-sig")))
    return tuple(out)


def test_the_trap_headings_are_read() -> None:
    """Le plancher du référentiel : sans titres lus, TOUT serait refusé —
    ou, si le lecteur rendait n'importe quoi, rien ne le serait."""
    headings = live_headings()
    assert len(headings) >= 35, (
        f"seulement {len(headings)} titres lus dans {_TRAPS.name} (48 le "
        f"2026-10-03) — le lecteur de titres est cassé."
    )
    # Le contrôle POSITIF : un thème et un piège, tels qu'écrits.
    assert "Composants" in headings
    assert "Slot Component stocké sans `adopt_slot`" in headings


def test_the_sweep_finds_citations_in_every_family() -> None:
    """Le plancher de la découverte, et par famille de source.

    Une famille dont le lecteur casse ne ferait que baisser un total resté
    au-dessus du plancher : chacune doit donc apporter au moins une
    citation, sans quoi son balayage est débranché sans le dire.
    """
    found: dict[str, list[str]] = {"python": [], "js": [], "markdown": []}
    for family, label, text in swept_texts():
        found[family].extend(f"{label}:{line}" for line, _title in citations(text))
    counts = {family: len(cites) for family, cites in found.items()}
    every = [cite for cites in found.values() for cite in cites]
    assert len(every) >= _CITATIONS_FLOOR, (
        f"seulement {len(every)} citations de `traps.md` trouvées (>= "
        f"{_CITATIONS_FLOOR} attendues) : {counts}. C'est le balayage ou "
        f"`_CITATION` qui est cassé, pas la doc qui s'est vidée."
    )
    silent = sorted(family for family, cites in found.items() if not cites)
    assert not silent, (
        f"aucune citation trouvée dans la famille {silent} — son lecteur "
        f"ne rend plus rien : {counts}."
    )


def test_every_traps_citation_names_a_live_heading() -> None:
    """L'interdiction : aucun renvoi vers un titre qui n'existe pas."""
    texts = [(label, text) for _family, label, text in swept_texts()]
    bad = offenders(texts, live_headings())
    assert not bad, (
        f"{len(bad)} citation(s) de `traps.md` ne nomment aucun titre "
        f"vivant :\n  " + "\n  ".join(bad) + "\n\n"
        "Repointe vers le titre `##`/`###` qui couvre le MÊME piège, "
        "recopié tel quel ; si aucun ne le couvre, retire le renvoi en "
        "gardant l'explication locale. N'invente pas de section dans "
        "traps.md pour faire taire la gate. Un titre ne se coupe pas entre "
        "deux littéraux de chaîne."
    )


def test_the_detector_still_bites() -> None:
    """Mutation, sur les deux versants : une citation fabriquée morte est
    refusée, une juste — même coupée sur deux lignes de commentaire — passe.

    Le préfixe est assemblé par concaténation pour que le balayage de CE
    fichier ne lise pas les exemples fabriqués comme de vraies citations.
    """
    traps = "traps" + ".md"
    cite = f"{traps} §"
    headings = live_headings()

    morte = f"# cf. {cite} « Un piège qui n'a jamais existé »\n"
    sans_guillemets = f"# cf. {cite} PEP 649.\n"
    coupee = f'f"cf. {cite} « Slot Component stocké " f"sans `adopt_slot` »"\n'
    for fabrique, forme in (
        (morte, "un titre absent de traps.md"),
        (sans_guillemets, "un § sans titre entre guillemets"),
        (coupee, "un titre coupé entre deux littéraux"),
    ):
        assert offenders([("x.py", fabrique)], headings), (
            f"le détecteur laisse passer {forme} : {fabrique!r}"
        )

    justes = (
        f'# cf. {cite} "Slot Component stocké sans `adopt_slot`".\n',
        f"    # cf. ``{traps}`` § « Slot Component stocké\n    # sans `adopt_slot` ».\n",
        f'  // cf. {cite} "Une valeur de scope calculée\n  // doit rester calculable".\n',
        f' * cf. {cite} "Une valeur de scope\n * calculée doit rester calculable").\n',
        f"Voir (`{traps}` §\n  *Le code applicatif synchrone peut être concurrent*).\n",
        f"    docstring : {cite}\n    « Composants ».\n",
    )
    for juste in justes:
        assert not offenders([("x", juste)], headings), (
            f"faux positif sur une citation juste : {juste!r} — le "
            f"détecteur refuserait un renvoi correct, donc la gate rougirait "
            f"pour rien et on finirait par la contourner."
        )
