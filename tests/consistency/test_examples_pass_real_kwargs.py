"""Gate : aucune app d'exemple ne passe un kwarg que le composant ignore.

``split_kwargs`` a un **catch-all raw-HTML** : tout kwarg inconnu est
normalisé et émis tel quel comme attribut. C'est ce qui permet
``data_testid=`` ou ``aria_live=`` sans les déclarer — utile. Mais ça veut
dire qu'une **faute de frappe ou un prop supprimé passe en silence**, et
sort dans le DOM comme un attribut inerte que rien ne lit.

Mesuré le 2026-08-01 sur ``examples/`` : **44 kwargs morts, 10 familles**.
Le pire, ``ui.input(label="…")`` sur **22 sites** — dont une majorité dans
le playground, le banc d'essai censé démontrer l'API. Ils rendaient
``<input label="Display name">`` : **aucun libellé affiché**, alors que
l'API prévue est ``ui.form_field(label=…)``. Vérifié par rendu, pas déduit.

**Pourquoi une gate ici et pas un refus dans le socle.** Refuser tout
kwarg inconnu à la construction serait plus fort, mais c'est un choix de
design qui casse l'échappatoire raw-HTML — il est posé dans
``.claude/work/chantier-introspect-2026-08-16.md`` (item 5), à trancher.
En attendant, le playground est le corpus qui exerce toute la surface
publique : le garder honnête suffit à empêcher la récidive là où ça fait
mal.

L'asymétrie qui a rendu ça possible mérite d'être notée : ``accordion.py``
LÈVE un ``TypeError`` explicite pour son ancien ``type="single"``, mais
laissait passer ``variant=`` sans un mot. Le garde-fou existait, il n'avait
été posé que sur un seul renommage.

⚠️ **Ce fichier ne porte plus la RÈGLE — il porte son corpus.** Depuis le
2026-08-16 la règle vit dans :mod:`bretzel.lint.rules.kwargs`, livrée avec
le framework, parce qu'elle a exactement autant de valeur sur l'app d'un
utilisateur que sur ``examples/``. Ce qui reste ici est ce qui ne peut PAS
voyager : **quel corpus** on garde honnête, et **quel plancher** rend
l'interdiction non-vacuoue. C'est le patron pour les dix-sept autres gates
qui lisent ``examples/``.
"""

from __future__ import annotations

import ast
import functools
import pathlib

import pytest

from bretzel.lint import run
from bretzel.lint.rules import kwargs as kwargs_rule
from tests.consistency._discovery import (
    EXAMPLES_FLOOR,
    PROBES_FLOOR,
    parsed_sources,
)

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_EXAMPLES = _ROOT / "examples"
#: ``tests/probes/`` rejoint le corpus le 2026-08-19. Ce n'est pas une
#: extension gratuite : ``bench_batch3.py`` posait ``ui.tabs(variant=…)``
#: et ``ui.toggle_group(variant=…)``, deux props SUPPRIMÉES, ce qui faisait
#: **500** le rendu de la page. Le probe, lui, interprétait le 500 comme
#: « le serveur n'est pas encore là » et mourait sur
#: ``batch3 bench never came up on :8950`` — un message qui accusait le
#: réseau pour un kwarg mort. Personne ne l'a vu pendant des mois : pytest
#: ne collecte pas ce dossier.
_PROBES = _ROOT / "tests" / "probes"
_CORPUS = (_EXAMPLES, _PROBES)

#: Les dix familles mesurées le 2026-08-01, figées comme corpus de
#: non-régression. Vérifié le 2026-08-16 : **les dix sont encore des
#: kwargs morts**, donc chacune reste un cas de test valide. Une entrée qui
#: deviendrait légitime (la prop ajoutée pour de vrai) doit être RETIRÉE
#: d'ici avec sa raison, pas laissée à rougir.
_HISTORICAL: tuple[tuple[str, str], ...] = (
    ("input", "label"),  # 22 sites — le pire, aucun libellé rendu
    ("form", "action"),  # 8 sites
    ("accordion", "variant"),  # 5 sites — prop supprimée
    ("code", "language"),  # 3 sites — c'est `lang=`
    ("dialog", "size"),  # c'est `width=`
    ("drawer", "size"),  # idem
    ("link", "size"),
    ("heading", "align"),
    ("dropdown_item", "external"),
    ("input", "autofocus"),
)


@functools.lru_cache(maxsize=2)
def _call_count(root: pathlib.Path, floor: int) -> int:
    """Le nombre d'appels ``ui.*`` sous ``root``."""
    return sum(
        1
        for source in parsed_sources(root, floor=floor)
        for node in ast.walk(source.tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "ui"
    )


def test_discovery_non_trivial() -> None:
    """Plancher : la gate voit bien un corpus d'appels ``ui.*``.

    Sans lui, un renommage du namespace ou un glob cassé rendrait
    l'interdiction verte sur zéro appel. **Un plancher par racine** : un
    seul total laisserait ``tests/probes/`` (409 appels) disparaître
    derrière ``examples/`` (13 622) sans faire bouger le chiffre.
    """
    in_examples = _call_count(_EXAMPLES, EXAMPLES_FLOOR)
    assert in_examples >= 1500, (
        f"seulement {in_examples} appels `ui.*` trouvés sous {_EXAMPLES} "
        f"(13 622 au 2026-08-19) — la découverte est cassée, la gate ne "
        f"garde plus rien."
    )
    in_probes = _call_count(_PROBES, PROBES_FLOOR)
    assert in_probes >= 250, (
        f"seulement {in_probes} appels `ui.*` trouvés sous {_PROBES} "
        f"(409 au 2026-08-19) — les bancs sortiraient du corpus sans que "
        f"le plancher d'`examples/` ne bouge d'un pouce."
    )


def test_the_rule_still_catches_the_2026_08_01_population(tmp_path: pathlib.Path) -> None:
    """La règle déléguée attrape encore les dix familles historiques.

    C'est ce qui remplace « la gate contenait le code, donc je sais ce
    qu'elle teste ». Déléguer la règle sans figer sa population, ce serait
    échanger une duplication contre une confiance aveugle : rien
    n'empêcherait `bretzel.lint` de se raffiner jusqu'à ne plus voir le
    motif pour lequel cette gate a été écrite.
    """
    body = "from bretzel import ui\n\ndef page():\n" + "".join(
        f"    ui.{comp}({kw}='x')\n" for comp, kw in _HISTORICAL
    )
    (tmp_path / "regression.py").write_text(body, encoding="utf-8")

    caught = {
        (comp, kw)
        for comp, kw in _HISTORICAL
        for finding in run([tmp_path], rules=(kwargs_rule.RULE,)).findings
        if f"ui.{comp}({kw}=" in finding.message
    }
    missed = sorted(set(_HISTORICAL) - caught)
    assert not missed, (
        f"la règle `{kwargs_rule.RULE}` ne voit plus {missed}. Soit la prop "
        f"est devenue légitime — retire-la de `_HISTORICAL` avec sa raison — "
        f"soit la règle s'est affaiblie et le motif du 2026-08-01 peut "
        f"revenir sans bruit."
    )


def test_no_dead_kwarg_in_examples() -> None:
    report = run(list(_CORPUS), rules=(kwargs_rule.RULE,))
    assert report.files_scanned > 0, f"aucun fichier balayé sous {_CORPUS}"
    if not report.findings:
        return

    lines = "\n".join(f"    {f.format(root=_ROOT)}" for f in report.findings)
    pytest.fail(
        f"{len(report.findings)} kwarg(s) qu'aucun composant ne lit :\n{lines}\n\n"
        f"  `split_kwargs` a un catch-all raw-HTML : le kwarg ne lève pas, "
        f"il sort dans le DOM comme attribut INERTE. C'est comme ça que 22 "
        f'`ui.input(label=…)` du playground ont rendu `<input label="…">` '
        f"sans afficher aucun libellé.\n"
        f"  Corrige le nom (`lang=` pas `language=`, `width=` pas `size=` "
        f"sur les overlays), utilise le bon composant "
        f"(`ui.form_field(label=…)` enveloppe l'input), ou passe par "
        f"`attrs={{...}}` si tu veux vraiment un attribut HTML brut."
    )
