"""Gate : chaque bench de ``tests/probes/`` s'importe encore.

Le défaut qu'elle ferme
-----------------------
``tests/probes/bench_*.py`` est le harnais de vérification VISUELLE du
dépôt : des mini-apps qu'on lance pour regarder un composant dans un vrai
navigateur. La discipline du projet en fait un passage **bloquant** avant
de dire « livré » (cf. ``creating-a-component.md`` § 9).

Or ces fichiers ne suivent pas le motif ``test_*.py``, donc **pytest ne
les collecte jamais**. Rien ne les exécute tant qu'un humain ne les lance
pas à la main, un par un. Mesuré le 2026-08-15 : **31 des 40 ne
s'importaient plus**, tous sur ``AttributeError: 'Bretzel' object has no
attribute 'page' / 'layout' / 'refreshable'`` — l'API avait déménagé aux
commits ``afa27bc3`` et ``86efe195``, et personne ne l'avait vu. Neuf
benchs vivants sur quarante, silencieusement.

C'est la forme locale d'un constat déjà écrit dans la mémoire du projet :
« les probes pourrissent en silence ». Cette gate lui donne un chiffre et
un cran d'arrêt.

Pourquoi l'IMPORT et pas plus
------------------------------
Importer un bench exécute son module : construction de l'app,
décorateurs, ``include``. C'est là que 100 % des 31 pannes se
manifestaient. Servir une page vérifierait davantage mais ferait entrer
un round-trip HTTP par bench dans la suite rapide, pour un gain marginal
sur le défaut visé. On garde le test qui attrape la panne réelle au coût
le plus bas.

Sa jumelle ``test_no_phantom_app_attribute`` attrape la même classe par
l'autre bout, en lisant le texte : elle nomme le coupable (``app.page``
n'existe pas) là où celle-ci constate la panne. Les deux servent — un
bench peut mourir d'autre chose qu'un attribut fantôme, et un attribut
fantôme peut vivre ailleurs que dans un bench.

Ce qu'elle ne peut PAS attraper
--------------------------------
Un bench qui s'importe et rend une page FAUSSE. Elle garde la vie du
harnais, pas la justesse de ce qu'il montre — ça, seul l'œil le fait.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

#: Preuve de morsure : le lecteur de lancements de bench.
#:
#: ⚠️ Ce fichier a porté ``MUTATION_NOT_APPLICABLE`` — « pas de détecteur
#: à rendre aveugle » — et c'était vrai tant qu'il ne faisait qu'importer
#: les bancs. Ajouter ``_LAUNCH`` le 2026-08-31 a rendu la déclaration
#: FAUSSE, et c'est ``test_a_not_applicable_claim_is_true`` qui l'a dit,
#: pas moi.
MUTATION_PROOF = "test_the_launch_reader_still_bites"

_PROBES = Path(__file__).resolve().parents[1] / "probes"


def _bench_modules() -> list[str]:
    return sorted(p.stem for p in _PROBES.glob("bench_*.py"))


@pytest.mark.parametrize("name", _bench_modules())
def test_bench_module_imports(name: str) -> None:
    try:
        importlib.import_module(f"tests.probes.{name}")
    except Exception as exc:
        pytest.fail(
            f"tests/probes/{name}.py ne s'importe plus : "
            f"{type(exc).__name__}: {exc}\n\n"
            f"Ces benchs sont le harnais de vérification visuelle et pytest "
            f"ne les collecte pas tout seuls — c'est pour ça que 31 d'entre "
            f"eux sont restés morts sans que personne ne le voie. Répare-le "
            f"ou supprime-le, mais ne le laisse pas semblant d'exister."
        )


def test_sweep_is_not_vacuous() -> None:
    """Plancher : le répertoire est trouvé et contient de vrais benchs.

    Ancré sur la DÉCOUVERTE. Un ``glob`` qui ne rend rien — répertoire
    déplacé, motif renommé — laisserait la paramétrisation vide et la
    gate verte : elle certifierait la santé de zéro fichier.
    """
    modules = _bench_modules()
    assert len(modules) >= 30, (
        f"Seulement {len(modules)} benchs découverts dans {_PROBES} "
        f"(40 au 2026-08-15). Le répertoire a-t-il bougé, ou le motif "
        f"``bench_*.py`` changé ?"
    )


# ───────────────────────────────────────────────────────────────────────
# L'autre moitié : un probe qui LANCE un bench disparu
# ───────────────────────────────────────────────────────────────────────
#
# La gate ci-dessus vérifie que les bancs PRÉSENTS s'importent. Elle est
# structurellement aveugle au défaut inverse : un probe qui lance un banc
# qui n'existe plus. Le fichier absent n'est dans aucun `glob`, donc rien
# ne le cherche.
#
# Mesuré le 2026-08-31 en lançant `-m probes` : **4 rouges sur 5** de
# cette cause exacte. Le 2026-08-30, la suppression de la famille
# `/matrix` a emporté `bench_matrix.py`, `bench_hub.py` et
# `bench_inputs.py` — et a laissé `probe_tooltip`, `probe_ttid`,
# `probe_hub` et `probe_inputs` derrière, qui lancent un `sys.executable`
# sur un chemin inexistant puis attendent trente secondes qu'un serveur
# monte. Ils sont morts depuis, en silence.
#
# `probe_tooltip` est le plus coûteux à perdre : il garde une régression
# RÉPARÉE — un panneau de tooltip téléporté qui se désynchronise de son
# scope après un morph — donc son silence rouvre la porte au bug.

#: Le motif d'un lancement de bench : ``HERE / "bench_x.py"``.
_LAUNCH = re.compile(r'"(bench_[a-z0-9_]+\.py)"')

#: Les orphelins TOLÉRÉS, avec leur raison. Une entrée ici est un choix
#: explicite, pas un oubli — et elle doit mourir dès que le probe est
#: réparé ou supprimé, ce que garde
#: :func:`test_no_tolerated_orphan_has_healed`.
_ORPHANS_KNOWN: dict[str, str] = {
    # VIDE depuis le 2026-08-31 — et c'est l'état normal, pas un oubli.
    # `probe_tooltip` y a vécu quelques heures : son banc était parti
    # avec `/matrix`, et le scénario semblait non repointable (il tenait
    # à des boutons chevron construits à la main dans ce banc). Il l'a
    # été en construisant le manque côté PRODUIT : aucun banc ne montrait
    # un tooltip dans une zone `@refreshable`, alors que c'est la
    # configuration ordinaire d'une barre d'outils. La carte ajoutée à
    # `/tooltip` sert les deux.
    #
    # Ce que la tolérance a coûté pendant qu'elle existait : rien, parce
    # qu'elle était DÉCLARÉE et marquée `xfail(strict=True)`. C'est le
    # point de ce dict — un rouge permanent finit ignoré, une exemption
    # écrite se relit.
}


def _probe_scripts() -> list[Path]:
    return sorted(_PROBES.glob("probe_*.py"))


def _launches() -> list[tuple[str, str]]:
    """``(probe, bench lancé)`` pour tout le répertoire."""
    out: list[tuple[str, str]] = []
    for probe in _probe_scripts():
        # Pas d'``errors="replace"`` : un fichier illisible doit LEVER,
        # pas être avalé en silence — c'est la règle que
        # ``test_no_gate_swallows_a_file`` fait respecter, et elle a
        # attrapé ce fichier le 2026-08-31.
        text = probe.read_text(encoding="utf-8")
        for bench in sorted(set(_LAUNCH.findall(text))):
            out.append((probe.name, bench))
    return out


_LAUNCHES = _launches()


def test_the_launch_sweep_is_not_vacuous() -> None:
    """Plancher sur la DÉCOUVERTE, et sur les DEUX bouts.

    Perdre les probes, ou perdre le motif de lancement, viderait la
    paramétrisation ci-dessous sans rien casser d'autre.
    """
    assert len(_probe_scripts()) >= 45, (
        f"{len(_probe_scripts())} probes découverts — le motif "
        f"``probe_*.py`` ou le répertoire a changé."
    )
    assert len(_LAUNCHES) >= 20, (
        f"seulement {len(_LAUNCHES)} lancement(s) de bench trouvé(s) — "
        f"l'expression `_LAUNCH` ne reconnaît plus la forme, donc cette "
        f"gate passerait en ne vérifiant rien."
    )


@pytest.mark.parametrize(
    ("probe", "bench"), _LAUNCHES, ids=lambda v: v,
)
def test_a_probe_launches_a_bench_that_exists(probe: str, bench: str) -> None:
    """Le banc qu'un probe démarre doit être là."""
    if probe in _ORPHANS_KNOWN:
        pytest.skip(f"orphelin toléré : {_ORPHANS_KNOWN[probe]}")
    assert (_PROBES / bench).is_file(), (
        f"`{probe}` lance `{bench}`, qui n'existe pas.\n"
        f"  Le probe ne rougit pas franchement : il démarre un "
        f"`sys.executable` sur un chemin absent, puis attend trente "
        f"secondes qu'un serveur monte, et meurt sur « bench never came "
        f"up ». Hors d'un `-m probes` complet — donc presque toujours — "
        f"personne ne le voit.\n"
        f"  C'est arrivé quatre fois d'un coup le 2026-08-30, en "
        f"supprimant la famille `/matrix` sans regarder qui lançait ses "
        f"bancs.\n"
        f"  Répare le probe (repointe-le sur un banc vivant) ou "
        f"supprime-le — mais ne le laisse pas faire semblant d'exister."
    )


def test_the_launch_reader_still_bites() -> None:
    """Les deux versants du lecteur de lancements.

    Il cherche une FORME entre guillemets, donc il peut cesser de voir
    sans que rien ne rougisse.
    """
    assert _LAUNCH.findall('[sys.executable, str(HERE / "bench_hub.py")]') == [
        "bench_hub.py"
    ]
    # Le versant qui ÉPARGNE : une PROSE qui nomme un bench n'est pas un
    # lancement. Les docstrings des probes en citent régulièrement pour
    # dire « voir aussi » ; les exiger sur le disque rougirait sur des
    # probes corrects.
    assert _LAUNCH.findall("cf. le bench_matrix.py de l'epoque") == []
    assert _LAUNCH.findall("lance bench_x.py sans guillemets") == []


def test_no_tolerated_orphan_has_healed() -> None:
    """Une tolérance qui n'excuse plus rien doit partir.

    Deux façons de mourir, et les deux comptent : le probe a été
    supprimé, ou son banc est revenu. Dans les deux cas l'entrée
    couvrirait un fantôme, et une table d'exemptions qui garde des noms
    réparés finit par excuser le cas suivant sans que personne ne le
    décide.
    """
    disparus = sorted(
        p for p in _ORPHANS_KNOWN if not (_PROBES / p).is_file()
    )
    assert not disparus, (
        f"{disparus} ne sont plus dans `tests/probes/` — retire-les de "
        f"`_ORPHANS_KNOWN`."
    )
    gueris = sorted(
        p for p, _ in _LAUNCHES
        if p in _ORPHANS_KNOWN and all(
            (_PROBES / b).is_file() for q, b in _LAUNCHES if q == p
        )
    )
    assert not gueris, (
        f"{gueris} lancent de nouveau un banc qui existe : la tolérance "
        f"n'a plus d'objet, retire-la pour que la gate les garde comme "
        f"les autres."
    )
