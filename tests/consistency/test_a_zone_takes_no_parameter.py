"""Une zone ``@refreshable`` ne prend pas de paramètre, et le
rafraîchissement l'appelle nu — les deux moitiés, ensemble.

Le fait gardé
--------------
``render/partials.py`` re-rend une zone en appelant la poignée **sans
argument**. Le rendu de page, lui, passe par
``RefreshableHandle.__call__(*args, **kwargs)``. Les deux chemins ne
voient donc pas la même signature, et rien ne le disait :

``def zone(x)``
    La page s'affiche parfaitement. Puis la première action qui touche
    un ``deps`` lève ``TypeError`` — **un 500 sur le re-rendu, pas sur
    la page**. Mesuré au code le 2026-09-04 : le décorateur ne
    consultait jamais ``inspect.signature`` (le seul ``inspect`` du
    fichier servait à ``is_async``), et aucune règle de
    ``bretzel/lint/rules/`` ne l'attrapait.

``def zone(x=0)``
    Muet. La page rend ``zone(3)``, chaque rafraîchissement rend
    ``zone(0)``. C'est la moitié que l'énoncé d'origine ratait : il ne
    parlait que du paramètre obligatoire, donc du cas qui LÈVE. Celui
    qui ne lève pas est le plus cher.

Le fond : une zone est re-rendue **hors de son appelant**, donc tout ce
dont elle a besoin doit être joignable depuis elle — un état. Deux pages
qui appelleraient la même zone avec deux arguments partageraient de
toute façon un ``id`` et un ``name`` uniques : le modèle n'a nulle part
où ranger la différence.

Pourquoi les deux moitiés dans la MÊME gate
--------------------------------------------
Le refus n'est juste que **tant que** le rafraîchissement appelle nu. Si
un jour ``partials.py`` transmettait quelque chose, la règle ne serait
pas seulement inutile : elle interdirait la forme devenue correcte. La
gate lit donc l'appel à la source, et rougit si sa raison d'être change.

Ce que cette gate n'affirme PAS
--------------------------------
``*args`` / ``**kwargs`` sont **acceptés**. Rien dans une signature ne
dit ce qu'un ``**kwargs`` porte, donc les refuser reviendrait à juger
sur le nom — et un banc du dépôt s'en sert légitimement
(``tests/unit/components/data/test_datatable.py``) pour bâtir une vraie
zone autour d'un composant paramétré. Une zone variadique appelée AVEC
des arguments depuis une page perd donc toujours ces arguments au
rafraîchissement, en silence. C'est le résidu, il est écrit ici plutôt
que tu, et il n'a aucun porteur dans le dépôt aujourd'hui.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from bretzel.render.decorators.refreshable import refreshable
from tests.consistency._discovery import (
    EXAMPLES_FLOOR,
    REPO_ROOT,
    ParsedSource,
    parsed_sources,
)

#: La preuve de morsure de cette gate, pour la gate-des-gates.
MUTATION_PROOF = "test_the_refusal_bites_on_a_parameterized_zone"

#: Les deux racines qui DÉCLARENT des zones. ``bretzel/`` n'en a aucune
#: — le framework fournit le décorateur, il ne s'en sert pas — donc la
#: balayer ferait un plancher à zéro, c'est-à-dire pas un plancher.
_ROOTS = (
    (REPO_ROOT / "examples", EXAMPLES_FLOOR),
    (REPO_ROOT / "tests", 200),
)

#: Ce que le RECONNAISSEUR doit trouver. Le plancher porte sur la
#: découverte (« combien de ``@refreshable`` le lecteur AST voit-il »),
#: pas sur la population des fautifs : un balayage cassé rend zéro et
#: rougit ici, au lieu d'affirmer « aucune zone paramétrée » sur rien.
#: Mesuré le 2026-09-04 : 222 sous ``examples/``, 89 sous ``tests/``.
_ZONES_FLOOR = 250


def _decorated_zones(source: ParsedSource) -> list[ast.FunctionDef]:
    """Les fonctions décorées ``@refreshable`` d'un fichier.

    Reconnaît les deux écritures — ``@refreshable`` nu et
    ``@refreshable(deps=[...])`` — et les deux accès, ``refreshable`` ou
    ``qqch.refreshable``.
    """
    found: list[ast.FunctionDef] = []
    for node in ast.walk(source.tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for deco in node.decorator_list:
            target = deco.func if isinstance(deco, ast.Call) else deco
            name = getattr(target, "attr", None) or getattr(target, "id", None)
            if name == "refreshable":
                found.append(node)
                break
    return found


def _named_parameters(fn: ast.FunctionDef) -> list[str]:
    """Les paramètres NOMMÉS — variadiques exclus, comme le refus."""
    args = fn.args
    return [a.arg for a in args.posonlyargs + args.args + args.kwonlyargs]


def _all_zones() -> list[tuple[Path, ast.FunctionDef]]:
    out: list[tuple[Path, ast.FunctionDef]] = []
    for root, floor in _ROOTS:
        for source in parsed_sources(root, floor=floor):
            out.extend((source.path, fn) for fn in _decorated_zones(source))
    return out


def test_the_zone_sweep_is_not_vacuous() -> None:
    """Le plancher : le reconnaisseur voit-il encore des zones ?"""
    zones = _all_zones()
    assert len(zones) >= _ZONES_FLOOR, (
        f"seulement {len(zones)} zones ``@refreshable`` trouvées "
        f"(>= {_ZONES_FLOOR} attendues). Ce n'est pas la population qui a "
        f"fondu, c'est le LECTEUR qui est cassé — vérifie "
        f"``_decorated_zones`` avant de croire qu'aucune zone n'est "
        f"paramétrée."
    )


def test_no_zone_of_the_repo_takes_a_parameter() -> None:
    """La population : personne n'écrit la forme refusée."""
    fautifs = [
        f"{path.relative_to(REPO_ROOT)}:{fn.lineno} "
        f"{fn.name}({', '.join(_named_parameters(fn))})"
        for path, fn in _all_zones()
        if _named_parameters(fn)
    ]
    assert not fautifs, (
        "Ces zones déclarent un paramètre, que le rafraîchissement ne peut "
        "pas fournir :\n  " + "\n  ".join(fautifs) + "\n\n"
        "Obligatoire → 500 à la première action qui touche un `deps`. À "
        "valeur par défaut → aucune erreur, mais la zone re-rend autre "
        "chose que ce que la page affichait. Lis un état dans le corps, "
        "ou garde une fonction ordinaire paramétrable que la zone appelle."
    )


@pytest.mark.parametrize(
    ("signature", "forme"),
    [
        ("(x)", "obligatoire — celle qui lève"),
        ("(x=0)", "à valeur par défaut — celle qui ment"),
        ("(*, x)", "par mot-clé seul"),
        ("(x, *args, **kwargs)", "un nommé au milieu de variadiques"),
    ],
)
def test_the_refusal_bites_on_a_parameterized_zone(
    signature: str, forme: str
) -> None:
    """Le versant ILLICITE, sur des signatures fabriquées."""
    namespace: dict[str, object] = {}
    exec(f"def zone_fabriquee{signature}: pass", namespace)  # noqa: S102

    with pytest.raises(TypeError) as capture:
        refreshable(namespace["zone_fabriquee"])

    message = str(capture.value)
    assert "zone_fabriquee" in message, (
        f"le refus ({forme}) ne nomme pas la zone : {message}"
    )
    assert "x" in message, (
        f"le refus ({forme}) ne nomme pas le paramètre fautif : {message}"
    )


@pytest.mark.parametrize(
    ("signature", "forme"),
    [
        ("()", "la forme normale"),
        ("(**kwargs)", "variadique — indécidable, donc acceptée"),
        ("(*args)", "variadique positionnelle"),
    ],
)
def test_a_zone_without_named_parameters_is_accepted(
    signature: str, forme: str
) -> None:
    """Le versant LICITE — celui qui mesure les faux positifs.

    C'est ce versant qui a trouvé les deux seuls bugs de gate du dépôt :
    qu'un refus rougisse sur un cas fabriqué ne dit rien de son taux de
    faux positifs sur les formes réelles.
    """
    namespace: dict[str, object] = {}
    exec(f"def zone_licite{signature}: pass", namespace)  # noqa: S102

    handle = refreshable(namespace["zone_licite"])
    assert handle.fn is namespace["zone_licite"], (
        f"{forme} : la poignée devrait envelopper la fonction telle quelle."
    )


def test_the_refresh_path_still_calls_the_handle_bare() -> None:
    """La RAISON du refus, lue à la source.

    Si ``partials.py`` se mettait à transmettre quelque chose, le refus
    ci-dessus interdirait la forme devenue correcte. On lit donc l'appel
    plutôt que de supposer qu'il n'a pas bougé.
    """
    chemin = REPO_ROOT / "bretzel" / "render" / "partials.py"
    arbre = ast.parse(chemin.read_text(encoding="utf-8-sig"))

    appels = [
        node
        for node in ast.walk(arbre)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "handle"
    ]
    assert appels, (
        "plus aucun appel ``handle(...)`` dans render/partials.py — soit "
        "le rafraîchissement passe ailleurs, soit la variable a changé de "
        "nom. Dans les deux cas, cette gate ne garde plus rien."
    )
    portants = [n.lineno for n in appels if n.args or n.keywords]
    assert not portants, (
        f"render/partials.py transmet des arguments à la zone (lignes "
        f"{portants}). Si c'est voulu, le refus de "
        f"``_reject_parameters`` n'a plus lieu d'être et doit être levé "
        f"en même temps — c'est lui qui interdit la signature que ce "
        f"chemin sait maintenant remplir."
    )


def test_the_refusal_lives_where_no_path_can_skip_it() -> None:
    """Structurel : le refus est dans ``__init__``, pas dans ``_wrap``.

    Le décorateur n'est pas la seule porte imaginable vers une poignée —
    il est la seule d'AUJOURD'HUI. Poser le garde au constructeur le
    rend inévitable quel que soit le chemin de construction, et c'est
    cette propriété-là qu'on garde, pas l'orthographe de l'appel.
    """
    from bretzel.render.decorators.refreshable import RefreshableHandle

    corps = inspect.getsource(RefreshableHandle.__init__)
    assert "_reject_parameters" in corps, (
        "``RefreshableHandle.__init__`` n'appelle plus ``_reject_"
        "parameters``. S'il a migré dans le décorateur, une poignée "
        "construite directement échapperait au refus — et le mode "
        "d'échec (un 500 au premier rafraîchissement) est justement "
        "celui qu'on ne voit pas en revue."
    )
