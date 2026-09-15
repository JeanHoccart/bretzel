r"""Gate : la PROSE d'``examples/`` ne décrit pas Bretzel en vocabulaire Alpine.

Le fait gardé
--------------
Bretzel a eu Alpine.js, puis un moteur maison. Le rebrand a renommé les
attributs — ``x-text`` → ``bz-text``, ``@click`` → ``bz-on:click`` — et
``bretzel/components/base/attrs.py`` REFUSE désormais un kwarg qui porte
l'ancien préfixe. Le code ne peut donc plus dériver.

La prose, si. Elle a dérivé, et elle est restée fausse longtemps : le
2026-09-05, la docstring de ``examples/counter/counter.py`` racontait
encore « Click → Alpine mutates the reactive store → the bound
``x-text`` span re-evaluates », alors que la page émet ``bz-on:click``
et ``bz-text`` (vérifié en rendant la page). Neuf autres fichiers
disaient de même — **19 occurrences en tout** : deux playgrounds
attribuaient à un ``x-init`` la synchronisation que font en vrai
``bz-model`` / ``bz-data`` / ``bz-effect``, trois nommaient
``x-effect`` ce que le rendu écrit ``bz-effect``, et cinq annonçaient
un ``x-cloak`` que la V3 n'émet plus du tout — le FOUC passe par un
``style="display:none"`` pré-estampillé (``Component._cloak_show``).

⚠️ **Quatre de ces dix fichiers, et 8 des 19 occurrences, ont été
trouvés par cette gate** — pas par le grep qui a ouvert la tâche : il
cherchait ``x-text|x-data|x-show|x-model``, et la famille ``x-`` en
compte vingt. C'est l'argument de la gate en une ligne : une liste
écrite à la main garde le passé.

Pourquoi ça coûte plus qu'une faute d'orthographe
--------------------------------------------------
``examples/`` est ce qu'on lit pour apprendre le framework, et une IA
comme un débutant recopient ce qu'ils y lisent. Le mode d'échec est
alors le pire de tous : le kwarg recopié est REFUSÉ à l'appel (bien),
mais l'attente qu'il a créée — « je peux écrire des directives Alpine »
— survit au refus. Et une docstring qui nomme un mécanisme inexistant
est indistinguable, en lecture, d'une qui décrit le vrai.

Pourquoi une gate plutôt qu'une correction
-------------------------------------------
Règle 8 de ``CLAUDE.md``. La correction de 2026-09-05 est la DEUXIÈME :
le rebrand lui-même avait déjà nettoyé ce vocabulaire, et il est revenu.
``test_components_emit_only_runtime_directives`` garde le vocabulaire
que les composants ÉMETTENT ; personne ne gardait celui qu'ils
RACONTENT.

Ce que cette gate n'affirme PAS
--------------------------------
1. Elle balaie ``examples/`` seulement. ``bretzel/`` mentionne Alpine
   légitimement — le message d'erreur d'``attrs.py`` nomme la directive
   qu'il refuse, et deux commentaires du socle disent « la V3 n'a plus
   de ``x-cloak`` ». Ces phrases sont vraies et utiles là où elles sont.
2. Elle ne couvre pas la famille ``@<event>`` (``@click``, ``@change``).
   C'est la MÊME dérive — le 2026-09-05, treize fichiers de
   ``examples/playground/`` décrivaient encore leur « Emitted HTML »
   avec ``@change=`` là où le rendu porte ``bz-on:change`` — mais la
   corriger dépassait le périmètre demandé, et un ``@`` seul est
   ambigu : ``examples/docs/features/traps.py`` cite ``@click`` pour
   dire de ne PAS l'écrire. Le reste est dans ``.claude/work/todo.md``,
   et l'élargissement de ce motif est ce qui clôt la classe.
3. Elle juge des OCTETS, pas du sens. Une phrase qui dirait « Bretzel
   n'utilise pas Alpine » rougirait aussi. C'est assumé : le dépôt n'en
   a plus une seule après le nettoyage, et une allowlist qui les
   autoriserait pourrirait plus vite qu'elle ne servirait.
"""

from __future__ import annotations

import re

import pytest

from tests.consistency._discovery import (
    EXAMPLES_FLOOR,
    REPO_ROOT,
    ParsedSource,
    parsed_sources,
)

#: Preuve de morsure : les deux versants sont fabriqués en mémoire.
MUTATION_PROOF = "test_the_detector_catches_a_dead_spelling"

_EXAMPLES = REPO_ROOT / "examples"

#: Le vocabulaire du moteur abandonné. Le nom du moteur, plus la famille
#: ``x-`` complète : le dépôt en a porté cinq (``x-text``, ``x-init``,
#: ``x-show``, ``x-cloak``, ``x-data``), et lister seulement ceux qu'on
#: vient de corriger ferait une gate qui garde le passé.
#:
#: ``(?<![\w-])`` / ``(?![\w-])`` et non ``\b`` : la convention de ce
#: répertoire, parce que ``\b`` est vrai après un tiret — c'est ce qui a
#: fait lire ``h-40`` dans ``max-h-40`` à une autre gate. Ici sans ces
#: gardes, ``space-x-2`` et ``translate-x-1/2`` — du Tailwind présent
#: partout dans ``examples/`` — seraient des contrevenants.
_DEAD = re.compile(
    r"(?<![\w-])(?:"
    r"alpine"
    r"|x-(?:text|html|data|show|if|for|model|modelable|init|effect"
    r"|bind|on|cloak|ref|id|transition|teleport|ignore|intersect"
    r"|mask|trap)"
    r")(?![\w-])",
    re.IGNORECASE,
)

#: L'ancre de non-vacuité : ce que la prose d'``examples/`` dit du
#: vocabulaire VIVANT. Le plancher porte là plutôt que sur le nombre de
#: contrevenants — celui-ci vaut zéro quand tout va bien, donc il ne
#: distingue pas « personne ne dérive » de « je ne lis rien ».
#: Mesuré le 2026-09-05 : 270 occurrences dans 363 fichiers.
_ALIVE = re.compile(
    r"(?<![\w-])bz-(?:text|show|model|data|init|effect|class|on:|attr:|ref|id)"
)
_ALIVE_FLOOR = 150


def _sources() -> list[ParsedSource]:
    """Tous les ``.py`` d'``examples/``, lus en ``utf-8-sig``.

    ``parsed_sources`` plutôt qu'un ``rglob`` maison : il LÈVE sur un
    fichier illisible au lieu de le sauter, et il porte déjà le plancher
    de fichiers.
    """
    return parsed_sources(_EXAMPLES, floor=EXAMPLES_FLOOR)


def _hits(text: str) -> list[tuple[int, str]]:
    """``(ligne, mot)`` pour chaque mention du moteur mort."""
    return [
        (text.count("\n", 0, m.start()) + 1, m.group(0))
        for m in _DEAD.finditer(text)
    ]


def test_the_prose_sweep_is_not_vacuous() -> None:
    """Le plancher : la DÉCOUVERTE parle encore.

    Deux ancres, parce qu'une seule ne sépare pas les deux pannes : le
    nombre de fichiers (porté par ``parsed_sources``) dit que le chemin
    tient, le nombre de mentions ``bz-*`` dit que c'est bien de la prose
    technique qu'on lit — et pas, par exemple, des fichiers vidés de
    leurs docstrings par un outil.
    """
    sources = _sources()
    alive = sum(len(_ALIVE.findall(s.text)) for s in sources)
    assert alive >= _ALIVE_FLOOR, (
        f"seulement {alive} mentions du vocabulaire ``bz-*`` trouvées dans "
        f"les {len(sources)} fichiers d'``examples/`` (>= {_ALIVE_FLOOR} "
        f"attendues, 270 le 2026-09-05). Ce n'est pas la prose qui a "
        f"fondu, c'est le LECTEUR — vérifie-le avant de croire "
        f"qu'``examples/`` ne parle plus d'Alpine."
    )


def test_no_example_describes_bretzel_in_alpine() -> None:
    """La population : personne ne raconte le moteur mort."""
    fautifs = [
        f"{source.path.relative_to(REPO_ROOT)}:{line} — « {mot} »"
        for source in _sources()
        for line, mot in _hits(source.text)
    ]
    assert not fautifs, (
        "Ces lignes d'``examples/`` décrivent Bretzel avec le vocabulaire "
        "d'Alpine, que le framework a abandonné en V3 :\n  "
        + "\n  ".join(fautifs)
        + "\n\nLis ce que le composant émet VRAIMENT avant de corriger — "
        "``x-`` → ``bz-`` mécaniquement se trompe : ``x-init`` désignait "
        "ici une synchronisation que font ``bz-model``, ``bz-data`` et "
        "``bz-effect``, et ``x-cloak`` n'a plus d'équivalent du tout. "
        "Rends le composant (``serialize_html``) et lis les attributs."
    )


@pytest.mark.parametrize(
    ("prose", "forme"),
    [
        ('emits ``<span x-text="$bz.state.x">``', "la faute réelle de counter.py"),
        ("Click → Alpine mutates the store", "le nom du moteur"),
        ("the wrapper's ``x-init`` watchers push", "celle des deux pickers"),
        ("emits ``x-show`` + ``x-cloak``", "celle de todo/"),
        ("un ``:class`` Alpine.js refusé", "le nom suivi d'un point"),
        ('x-data="{open: false}"', "le scope"),
        ("écrit un x-on:click à la main", "l'événement"),
        ("ALPINE mutates", "en capitales"),
    ],
)
def test_the_detector_catches_a_dead_spelling(prose: str, forme: str) -> None:
    """Le versant ILLICITE, sur de la prose fabriquée."""
    assert _hits(prose), f"{forme} : le détecteur ne voit plus « {prose} »"


@pytest.mark.parametrize(
    ("prose", "forme"),
    [
        ('emits ``<span bz-text="$bz.state.x">``', "le vocabulaire vivant"),
        ("bz-on:click, bz-show, bz-model, bz-init, bz-effect", "cinq directives"),
        ('classes="w-full max-w-xs space-x-2 translate-x-1/2"', "du Tailwind"),
        ("mx-auto px-4 -mx-2 divide-x-2", "des utilitaires en -x-"),
        (":class:`ClientBinding` — le rôle Sphinx", "un rôle Sphinx"),
        ('hx-post="/action" hx-swap="outerHTML"', "de l'HTMX brut"),
        ("le x_axis du graphe, en snake_case", "un identifiant Python"),
        ("box-shadow: 0 0 0 2px", "du CSS"),
        ("les alpinestars du catalogue", "le nom en sous-chaîne d'un mot"),
        ("f(x) - g(x) pour tout x", "de l'arithmétique"),
    ],
)
def test_the_detector_spares_a_living_spelling(prose: str, forme: str) -> None:
    r"""Le versant LICITE — celui qui mesure les faux positifs.

    C'est ce versant qui a trouvé les deux seuls bugs de gate du dépôt :
    qu'un motif rougisse sur un cas fabriqué ne dit rien de son taux de
    faux positifs sur les formes réelles. Ici il porte tout le poids —
    ``examples/`` est plein de ``space-x-2`` et de ``-mx-2``, que la
    version sans ``(?<![\w-])`` réclamerait par centaines.
    """
    assert not _hits(prose), (
        f"{forme} : le détecteur crie sur une forme légitime — « {prose} »"
    )


def test_the_socle_still_refuses_the_dead_prefixes() -> None:
    """La RAISON du refus, lue à la source.

    La prose est bannie parce que le vocabulaire est mort — pas
    l'inverse. Si ``attrs.py`` réacceptait un jour un préfixe ``x-``,
    cette gate interdirait un mot redevenu juste. On lit donc le refus
    plutôt que de supposer qu'il n'a pas bougé.
    """
    from bretzel.components.base.attrs import _DEAD_ALPINE_PREFIXES

    assert "x-" in _DEAD_ALPINE_PREFIXES, (
        "``attrs.py`` ne refuse plus le préfixe ``x-``. Soit c'est un "
        "bug du socle, soit Alpine est revenu — dans les deux cas, "
        "l'interdiction de prose ci-dessus doit être rejugée, pas "
        "maintenue par inertie."
    )
