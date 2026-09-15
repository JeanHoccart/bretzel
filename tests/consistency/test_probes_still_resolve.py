"""Gate : chaque probe de ``tests/probes/`` désigne encore du code vivant.

La jumelle de :mod:`tests.consistency.test_probe_benches_still_import`, sur
l'autre moitié du répertoire. Celle-là garde les 42 ``bench_*.py`` (des
mini-apps Bretzel) en les IMPORTANT ; celle-ci garde les 52
``probe_*.py`` — les scripts Playwright qui pilotent ces benchs — **sans
rien exécuter**.

Pourquoi cette moitié n'était gardée par rien
----------------------------------------------
Le répertoire n'est pas collecté par pytest : aucun fichier ne s'appelle
``test_*.py``. La gate des benchs est née le 2026-08-15 sur un constat
mesuré — **31 des 40 benchs ne s'importaient plus**, tous sur la même API
déménagée, morts depuis des mois sans que personne le voie. Les probes ont
exactement la même exposition et n'ont pas eu leur gate ce jour-là.

Depuis le 2026-08-16, ``probes/`` est le SEUL étage de vérif visuelle du
dépôt (``tests/visual/`` a été supprimé). Ce que ces scripts cessent de
pouvoir montrer, plus rien ne le montre.

Pourquoi STATIQUE, là où la gate des benchs importe
----------------------------------------------------
Un bench est une app : l'importer la construit, sans effet de bord. Un
probe est un **script** : quatre d'entre eux
(``probe_tipiso``, ``probe_ttid``, ``probe_combobox_width``,
``probe_datatable_filter``) exécutent leur corps au chargement — ils
lancent un serveur, un Chromium, et ``probe_tipiso`` finit sur un
``sys.exit`` qui tuerait le process pytest. Les importer était donc exclu.

On vérifie à la place, en lisant l'AST : le fichier parse, et **chaque
symbole qu'il importe de ``bretzel.*`` existe encore**. C'est précisément
la panne qui a tué les 31 benchs — une API qui déménage — attrapée sans
démarrer quoi que ce soit.

Ce qu'elle ne peut PAS attraper
--------------------------------
1. Un probe qui s'importe mais mesure la MAUVAISE chose, ou qui asserte
   l'inverse du fix qu'il est censé garder. Aucune lecture statique ne le
   voit ; seul le lancer le dit.
2. Un attribut qui n'existe qu'à l'exécution (``app.page`` sur un objet
   ``Bretzel``) — c'est le domaine de sa cousine
   ``test_no_phantom_app_attribute``, qui attrape cette classe par le texte.
3. Le bench que le probe pilote : un probe peut viser un port ou un bench
   disparu. Non gaté — l'appariement réel n'est pas déductible du nom (10
   probes sont **autonomes**, ils rendent le composant eux-mêmes via
   ``render_isolated`` et n'ont aucun bench).
"""

from __future__ import annotations

import ast
import functools
import importlib
from pathlib import Path

import pytest

#: Preuve de morsure : contre-cas — un probe qui LANCE quelque chose a l'import doit etre
#: refuse, ce qui prouve que le detecteur regarde bien le corps du module
#: et pas seulement ses imports.
MUTATION_PROOF = "test_no_probe_runs_on_import"

_PROBES = Path(__file__).resolve().parents[1] / "probes"


@functools.lru_cache(maxsize=1)
def _probe_files() -> tuple[Path, ...]:
    return tuple(sorted(_PROBES.glob("probe_*.py")))


@functools.lru_cache(maxsize=1)
def _framework_imports() -> tuple[tuple[str, str, str], ...]:
    """``(probe, module bretzel, symbole)`` pour chaque import de framework.

    Lu à l'AST, jamais exécuté : ces fichiers lancent des navigateurs.
    """
    found: list[tuple[str, str, str]] = []
    for path in _probe_files():
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            module = node.module or ""
            if not module.startswith("bretzel"):
                continue
            for alias in node.names:
                if alias.name != "*":
                    found.append((path.name, module, alias.name))
    return tuple(found)


def test_discovery_is_not_vacuous() -> None:
    """Plancher, ancré sur la DÉCOUVERTE.

    Deux crans : le ``glob`` trouve des probes, ET l'extraction d'imports
    en tire quelque chose. Sans le second, un jour où ``ast.ImportFrom``
    cesserait de matcher (imports réécrits, répertoire déplacé), la
    paramétrisation serait vide et la gate certifierait la santé de zéro
    fichier — le pire vert.
    """
    probes = _probe_files()
    assert len(probes) >= 45, (
        f"seulement {len(probes)} probes découverts dans {_PROBES} "
        f"(52 le 2026-08-16) — le répertoire a-t-il bougé, ou le motif "
        f"``probe_*.py`` changé ?"
    )
    imports = _framework_imports()
    assert len(imports) >= 70, (
        f"seulement {len(imports)} imports de framework extraits des "
        f"{len(probes)} probes (102 le 2026-08-16) — l'extraction AST a "
        f"cassé, la gate ne vérifie plus rien."
    )


@pytest.mark.parametrize(
    ("probe", "module", "symbol"),
    _framework_imports(),
    ids=[f"{p}:{m}.{s}" for p, m, s in _framework_imports()],
)
def test_probe_imports_live_symbols(probe: str, module: str, symbol: str) -> None:
    try:
        mod = importlib.import_module(module)
    # Large A DESSEIN : on rapporte l'echec d'import, on ne le trie pas.
    except Exception as exc:
        pytest.fail(
            f"tests/probes/{probe} importe `{module}`, qui ne se charge "
            f"plus : {type(exc).__name__}: {exc}"
        )
    assert hasattr(mod, symbol), (
        f"tests/probes/{probe} importe `{symbol}` depuis `{module}` — "
        f"le symbole n'existe plus.\n\n"
        f"  Ces probes sont le seul étage de vérif visuelle depuis la "
        f"suppression de la suite visual, et pytest ne les collecte pas : "
        f"c'est exactement comme ça que 31 benchs sur 40 sont restés morts "
        f"des mois. Répare le probe ou supprime-le, mais ne le laisse pas "
        f"faire semblant d'exister."
    )


def test_no_probe_runs_on_import() -> None:
    """Un probe ne démarre pas un navigateur quand un outil le lit.

    48 des 52 gardent leur corps sous ``if __name__ == "__main__"``. Les
    quatre qui s'exécutent au chargement portent à la place un refus
    d'import explicite — c'est ce que cette gate exige : l'une OU l'autre
    forme, jamais rien.

    Le défaut est réel : ``probe_tipiso`` finit sur ``sys.exit``, donc
    l'importer ne lance pas seulement un Chromium, ça termine le process
    qui l'a lu.
    """
    naked = [
        p.name
        for p in _probe_files()
        if 'if __name__ == "__main__"' not in (text := p.read_text(encoding="utf-8-sig"))
        and 'if __name__ != "__main__"' not in text
    ]
    assert not naked, (
        f"ces probes s'exécutent au chargement sans le dire : {naked}\n"
        f"  Mets leur corps sous `if __name__ == \"__main__\":`, ou "
        f"ajoute en tête un `if __name__ != \"__main__\": raise "
        f"RuntimeError(...)` comme les quatre qui le font déjà.\n"
        f"  Sinon, n'importe quel balayage du dépôt démarre un serveur et "
        f"un navigateur — et pour l'un d'eux, tue le process appelant."
    )
