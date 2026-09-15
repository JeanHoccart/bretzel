"""Couche 7 — le framework juge le code écrit contre lui.

Pendant de :mod:`bretzel.introspect` : celui-là **décrit**, celui-ci
**constate**. La distinction n'est pas cosmétique — elle décide de ce qui
peut être extrait. ``describe`` reflète le code installé, donc il doit
voyager à sa version exacte, sinon il ment ; ``lint`` porte des *règles*,
un savoir qui ne dépend d'aucune version, et c'est la moitié qu'on peut
sortir du dépôt public un jour. Le contrat ``lint-stays-extractable`` du
fichier ``.importlinter`` en fait une garantie mécanique plutôt qu'une
intention : aucun module du framework hors ``cli`` n'a le droit d'importer
ce paquet.

**Deux étages, par sûreté et non par confort** :

- :func:`run` — statique. AST seul, **rien de l'app n'est exécuté**. C'est
  le défaut, et c'est ce qui permet de le lancer sur le code d'un tiers.
- :func:`run_deep` — importe l'application pour interroger sa carte
  (routables non déclarés, dérive de contrat). Bien plus puissant, mais
  ça **exécute le code de l'utilisateur** : ça ne peut pas être le
  défaut, et ça ne prend pas des chemins mais une cible ``module:attribut``
  — les questions qu'il pose n'ont pas de réponse dans un fichier isolé.
"""

from __future__ import annotations

import inspect
from functools import cache
from pathlib import Path
from types import MappingProxyType

from bretzel.lint.corpus import bound as corpus_bound
from bretzel.lint.corpus import modules
from bretzel.lint.deep import lint_app, run_deep
from bretzel.lint.report import Finding, Report
from bretzel.lint.rules import STATIC

__all__ = (
    "Finding",
    "Report",
    "available_rules",
    "lint_app",
    "rule_summaries",
    "run",
    "run_deep",
)


def available_rules() -> tuple[str, ...]:
    """Ce que l'outil sait vérifier. Énumérable à dessein : un `check` qui
    ne peut pas dire ce qu'il couvre ne se laisse pas juger."""
    return tuple(sorted(STATIC))


@cache
def rule_summaries() -> MappingProxyType[str, str]:
    """Ce que chaque règle refuse, en une phrase — la SIENNE.

    Le pendant lisible d':func:`available_rules` : celui-là dit ce qui
    est couvert, celui-ci dit contre quoi. Ajouté le 2026-09-06 pour la
    doc vivante, qui listait douze noms nus faute de pouvoir atteindre
    la phrase.

    **Lue sur le module qui porte la règle, jamais recopiée ici.** Un
    résumé écrit à la main dérive plus vite qu'il ne sert — ce dépôt a
    supprimé un skill entier pour cette raison — et il n'y a aucune
    raison d'entretenir une deuxième version d'une phrase qui existe
    déjà en tête du fichier.

    Le préfixe ``Règle :`` tombe : c'est une convention d'en-tête de
    module, pas une partie du sens. Ce qui reste se lit derrière « elle
    refuse … ».
    """
    return MappingProxyType({
        slug: _stated_by(fn) for slug, fn in sorted(STATIC.items())
    })


def _stated_by(check: object) -> str:
    """La première ligne non vide du module d'une règle, nettoyée.

    Le balisage reStructuredText tombe aussi. Une phrase publique est
    faite pour être AFFICHÉE — dans un terminal, dans une page — et
    ``des ``doubles backticks`` et des **étoiles**`` s'y lisent tels
    quels. Le double backtick devient simple, qui est la convention de
    l'interface ; les étoiles disparaissent.
    """
    doc = (inspect.getdoc(inspect.getmodule(check)) or "").strip()
    ligne = next((li for li in doc.splitlines() if li.strip()), "")
    ligne = ligne.strip().removeprefix("Règle :").strip().rstrip(".")
    return ligne.replace("``", "`").replace("**", "")


def run(
    paths: list[Path] | tuple[Path, ...],
    *,
    rules: tuple[str, ...] | None = None,
) -> Report:
    """Passe les règles statiques sur les fichiers Python sous ``paths``.

    ``rules`` restreint le passage à un sous-ensemble nommé. C'est ce
    dont une gate a besoin : elle possède **une** interdiction et son
    corpus, et n'a pas à rougir parce qu'une règle voisine a trouvé
    autre chose. Un nom inconnu lève plutôt que d'être ignoré — une
    sélection qui se vide en silence rendrait un rapport vert.
    """
    if rules is not None:
        unknown = sorted(set(rules) - set(STATIC))
        if unknown:
            raise KeyError(
                f"règle(s) inconnue(s) : {unknown}. Disponibles : {list(available_rules())}."
            )
    selected = {name: check for name, check in STATIC.items() if rules is None or name in rules}
    found = modules(paths)
    report = Report(files_scanned=len(found), rules_run=tuple(sorted(selected)))
    # Le corpus est exposé pour la durée du passage : une règle qui constate
    # sur un module peut avoir besoin de savoir ce qu'un AUTRE fichier
    # déclare (cf. ``corpus.bound``). Lié ici et nulle part ailleurs, donc
    # la portée est exactement celle de l'appel.
    with corpus_bound(found):
        for module in found:
            for check in selected.values():
                report.findings.extend(check(module))
    report.findings.sort(key=lambda f: (f.path.as_posix(), f.line, f.rule))
    return report
