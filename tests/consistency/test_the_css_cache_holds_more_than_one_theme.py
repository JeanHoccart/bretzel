"""Deux thèmes ne se reprennent pas la même place — et le cache est BORNÉ.

Ce que cette gate ferme
-----------------------

Le CSS compilé vivait dans ``./.bretzel/style.css``, **une** place, avec
son empreinte dans un fichier voisin. Un dossier ne pouvait donc tenir
qu'un seul thème à la fois : deux apps lancées depuis la même racine —
la disposition normale d'un dépôt d'exemples — invalidaient le cache
l'une de l'autre à chaque démarrage.

Mesuré le 2026-08-27 en alternant ``examples/playground`` et
``examples/crm`` : **recompilation 4 fois sur 4**, ~2 s chacune. Avec
``reload=True``, qui relance le serveur à chaque sauvegarde, l'app passe
son temps à recompiler et paraît bloquée — c'est ce qui a été observé
sur le CRM le jour où il est passé en ``mode="prod"``.

Rien ne cassait, et c'est le point : le CSS rendu était juste. Seul le
temps changeait, donc aucun test de justesse ne pouvait le voir.

Pourquoi compter les COMPILATIONS et pas mesurer le temps
----------------------------------------------------------

Un seuil en secondes ne veut rien dire sur cette machine, qui dérive
d'un facteur 2 à 3 (memory ``inprocess_ab_or_no_measurement``). Le
nombre d'appels au compilateur, lui, est déterministe.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from bretzel.theme import build as build_mod

#: Deux entrées distinctes, minuscules — on teste la POLITIQUE de cache,
#: pas Tailwind. Le compilateur est remplacé par un mouchard.
_ENTREE_A = '@theme { --color-a: #111; }\n.a { color: red; }\n'
_ENTREE_B = '@theme { --color-b: #222; }\n.b { color: blue; }\n'


def compilations(entrees: list[str], *, tmp: Path, monkeypatch) -> int:
    """Le nombre de compilations RÉELLES pour cette suite d'appels.

    Extrait pour être mutable : le versant fautif rejoue la même suite
    avec un cache nommé à l'ancienne, c'est-à-dire une seule place.
    """
    appels = [0]

    def faux_compile(theme_css, *, output_path, binary=None, minify=True, **kw):
        appels[0] += 1
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(f"/* {theme_css[:20]} */", encoding="utf-8")

        class _R:
            bytes_written = 1
        return _R()

    monkeypatch.setattr(build_mod, "compile_with_lightning", faux_compile)
    monkeypatch.setattr(build_mod, "find_lightning_binary", lambda: tmp / "faux")
    monkeypatch.setattr(build_mod, "_cache_dir", lambda: tmp)
    # This gate exercises cache placement. Other xdist workers can touch
    # scanned source files while it runs, which legitimately changes the
    # production cache key but must not turn this policy test flaky.
    monkeypatch.setattr(build_mod, "_content_fingerprint", lambda roots: "stable")
    for entree in entrees:
        build_mod.get_or_build_css(entree)
    return appels[0]


def test_the_probe_compiles_when_the_cache_is_cold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le plancher : sans lui, une gate qui compte zéro serait verte
    parce que le mouchard n'est jamais atteint."""
    assert compilations([_ENTREE_A], tmp=tmp_path, monkeypatch=monkeypatch) == 1


def test_the_same_theme_compiles_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Redemander la même entrée relit le cache."""
    n = compilations([_ENTREE_A] * 4, tmp=tmp_path, monkeypatch=monkeypatch)
    assert n == 1, f"{n} compilations pour une seule entrée demandée 4 fois"


def test_two_themes_do_not_evict_each_other(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L'interdiction : c'est LE cas des deux apps d'un même dépôt.

    A, B, puis retour à A et à B : quatre demandes, deux entrées
    distinctes, donc deux compilations et pas quatre.
    """
    n = compilations(
        [_ENTREE_A, _ENTREE_B, _ENTREE_A, _ENTREE_B, _ENTREE_A],
        tmp=tmp_path, monkeypatch=monkeypatch,
    )
    assert n == 2, (
        f"{n} compilations pour 2 entrées distinctes — les thèmes "
        "s'évincent, le cache ne tient qu'une place."
    )


def test_the_gate_still_bites_on_a_single_slot_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le versant qui MORD : avec l'ancien nommage, ça repasse à 4.

    On remet le cache à UNE place — le fichier ne porte plus
    l'empreinte — et on rejoue l'alternance. Sans ce bras, la gate
    serait verte pour une raison qu'on n'a pas vérifiée.
    """
    appels = [0]

    def faux_compile(theme_css, *, output_path, binary=None, minify=True, **kw):
        appels[0] += 1
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("x", encoding="utf-8")

        class _R:
            bytes_written = 1
        return _R()

    def ancien_get(theme_css, *, rebuild=False, allow_download=False):
        css = tmp_path / "style.css"
        stamp = tmp_path / "style.css.sha256"
        digest = build_mod._theme_digest(theme_css)
        if css.is_file() and stamp.is_file():
            if stamp.read_text(encoding="utf-8").strip() == digest:
                return css.read_text(encoding="utf-8")
        faux_compile(theme_css, output_path=css)
        stamp.write_text(digest, encoding="utf-8")
        return css.read_text(encoding="utf-8")

    for entree in (_ENTREE_A, _ENTREE_B, _ENTREE_A, _ENTREE_B, _ENTREE_A):
        ancien_get(entree)
    assert appels[0] == 5, (
        f"l'ancien cache n'a compilé que {appels[0]} fois — la gate ne "
        "prouve donc pas ce qu'elle croit."
    )


# ───────────────────────────────────────────────────────────────────────
# L'éviction — le versant que la gate ne couvrait pas
# ───────────────────────────────────────────────────────────────────────
#
# Tenir plus d'un thème était la moitié du problème ; les tenir TOUS en
# était l'autre. La clé inclut l'empreinte des sources balayées, donc
# chaque édition d'un ``theme.py`` du framework crée une entrée neuve, et
# rien n'évinçait : 470 fichiers pour 298 Mo mesurés le 2026-08-30 après
# deux jours de travail sur les thèmes. Personne ne le voit — le dossier
# est ignoré par git et jamais ouvert.


def _cache_files(tmp: Path) -> list[Path]:
    return sorted((tmp / "css").glob("*.css"))


def test_the_cache_stays_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L'interdiction : au-delà du plafond, les vieilles entrées tombent."""
    entrees = [
        f"@theme {{ --color-x{i}: #{i:06d}; }}"
        for i in range(build_mod.CACHE_KEEP + 8)
    ]
    compilations(entrees, tmp=tmp_path, monkeypatch=monkeypatch)
    restants = _cache_files(tmp_path)
    assert len(restants) <= build_mod.CACHE_KEEP, (
        f"{len(restants)} feuilles en cache pour un plafond de "
        f"{build_mod.CACHE_KEEP} — rien n'évince, et le dossier grossit "
        f"sans fin."
    )


def test_the_bound_is_not_a_purge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le versant LICITE : borner ne veut pas dire vider.

    Une éviction trop zélée — garder une seule entrée, par exemple —
    satisferait l'interdiction ci-dessus tout en ramenant exactement le
    défaut que le reste de ce fichier interdit : deux apps qui se
    recompilent l'une l'autre.
    """
    n = compilations(
        [_ENTREE_A, _ENTREE_B] * 3, tmp=tmp_path, monkeypatch=monkeypatch
    )
    assert n == 2, f"{n} compilations : l'éviction a vidé ce qu'elle borne"
    assert len(_cache_files(tmp_path)) == 2


def test_pruning_keeps_the_newest_and_drops_the_rest(
    tmp_path: Path
) -> None:
    """La POLITIQUE, sur des dates posees a la main.

    Le premier essai de ce test passait par ``compilations`` et ne mordait
    PAS : il posait ``CACHE_KEEP`` entrees pour un plafond de
    ``CACHE_KEEP``, donc rien n'etait jamais evince, et debrancher
    l'eviction le laissait vert. Deux lecons, toutes deux payees ici :
    deborder le plafond n'est pas optionnel, et les dates doivent etre
    POSEES — sur une meme seconde, l'ordre de tri est arbitraire.
    """
    css_dir = tmp_path / "css"
    css_dir.mkdir()
    base = 1_700_000_000
    fichiers = []
    for i in range(build_mod.CACHE_KEEP + 5):
        f = css_dir / f"{i:016x}.css"
        f.write_text(f"/* {i} */", encoding="utf-8")
        os.utime(f, (base + i, base + i))
        fichiers.append(f)

    supprimes = build_mod._prune_css_cache(css_dir)
    assert supprimes == 5, f"{supprimes} supprimes, 5 attendus"
    restants = {f.name for f in css_dir.glob("*.css")}
    assert restants == {f.name for f in fichiers[5:]}, (
        "ce ne sont pas les plus recents qui ont survecu"
    )


def test_a_cache_hit_refreshes_the_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ce qui fait de l'eviction un LRU et non un FIFO.

    Sans ce ``touch``, la feuille servie tous les jours porterait la date
    de sa compilation et tomberait avant une variation compilee une fois
    et jamais relue. Le symptome serait une recompilation de 3 s au
    demarrage de l'app la plus utilisee, sans raison visible.

    Teste ici plutot que via l'eviction : c'est la SEULE facon de le
    verifier sans dependre de la resolution des dates du systeme.
    """
    compilations([_ENTREE_A], tmp=tmp_path, monkeypatch=monkeypatch)
    (entree,) = _cache_files(tmp_path)
    vieux = 1_700_000_000
    os.utime(entree, (vieux, vieux))

    compilations([_ENTREE_A], tmp=tmp_path, monkeypatch=monkeypatch)
    assert entree.stat().st_mtime > vieux, (
        "relire une feuille du cache ne rafraichit pas sa date : "
        "l'eviction est un FIFO, pas un LRU."
    )


# ───────────────────────────────────────────────────────────────────────
# La déduplication — douze places doivent tenir douze thèmes DIFFÉRENTS
# ───────────────────────────────────────────────────────────────────────


def _sheets(tmp: Path) -> list[Path]:
    return sorted((tmp / "css").glob("*.css"))


def _pointers(tmp: Path) -> list[Path]:
    return sorted((tmp / "css").glob("*.key"))


def test_two_keys_with_the_same_output_share_one_sheet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L'interdiction, sur le cas RÉEL.

    La clé inclut l'empreinte des sources balayées — il le faut — mais la
    réciproque est fausse : toucher un ``theme.py`` sans changer une
    seule classe donne une clé neuve pour une sortie identique. Mesuré le
    2026-08-31 sur le vrai cache : **6 des 7 feuilles étaient octet pour
    octet identiques**, donc douze places n'en tenaient que deux utiles.

    Le mouchard de ``compilations`` rend ``/* <20 premiers caractères> */``
    : deux entrées qui ne diffèrent qu'APRÈS le vingtième caractère
    compilent donc vers le même octet, exactement comme deux thèmes
    identiques dont seule une source balayée a bougé.
    """
    prefixe = "@theme { --color-a: #111; }"
    jumelles = [prefixe + f"\n/* source {i} */\n" for i in range(6)]
    n = compilations(jumelles, tmp=tmp_path, monkeypatch=monkeypatch)

    assert n == 6, f"{n} compilations pour 6 clés distinctes — attendu 6"
    assert len(_sheets(tmp_path)) == 1, (
        f"{len(_sheets(tmp_path))} feuilles sur le disque pour un seul "
        f"contenu compilé : le cache stocke des doublons, donc il "
        f"annonce {build_mod.CACHE_KEEP} places et en tient moins."
    )
    assert len(_pointers(tmp_path)) == 6, (
        "les six clés doivent rester distinctes — dédupliquer le "
        "CONTENU ne doit pas fusionner les clés, sinon la seconde app "
        "recompilerait."
    )


def test_the_deduplication_never_serves_the_wrong_sheet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le versant LICITE, et c'est le seul qui compte vraiment.

    Dédupliquer, c'est décider que deux choses sont la même. Se tromper
    ici servirait le thème d'une autre app — un défaut bien pire que la
    place perdue qu'on répare. On vérifie donc que deux entrées aux
    sorties DIFFÉRENTES gardent chacune la sienne, et que chaque clé
    relit bien son propre contenu.
    """
    compilations([_ENTREE_A, _ENTREE_B], tmp=tmp_path, monkeypatch=monkeypatch)
    assert len(_sheets(tmp_path)) == 2, "deux contenus, deux feuilles"

    monkeypatch.setattr(build_mod, "_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(
        build_mod, "find_lightning_binary", lambda: tmp_path / "faux"
    )
    for entree in (_ENTREE_A, _ENTREE_B):
        rendu = build_mod.get_or_build_css(entree)
        assert entree[:20] in rendu, (
            f"le cache rend {rendu!r} pour une entrée qui commence par "
            f"{entree[:20]!r} — une clé lit la feuille d'une autre."
        )


def test_an_orphan_pointer_recompiles_instead_of_crashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Une feuille évincée sous un pointeur encore là.

    C'est l'état NORMAL après une éviction — les pointeurs ne sont pas
    élagués — donc ce n'est pas un cas tordu, c'est le cas courant. Il
    doit se comporter comme une absence de cache, pas lever.
    """
    compilations([_ENTREE_A], tmp=tmp_path, monkeypatch=monkeypatch)
    (feuille,) = _sheets(tmp_path)
    feuille.unlink()

    n = compilations([_ENTREE_A], tmp=tmp_path, monkeypatch=monkeypatch)
    assert n == 1, "un pointeur orphelin doit provoquer une recompilation"
    assert len(_sheets(tmp_path)) == 1


def test_two_compilations_never_share_a_scratch_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le nom provisoire est unique par APPEL, pas par clé.

    Ce qu'il en coûtait. Le fichier provisoire était nommé d'après la clé
    du cache, donc deux processus compilant le MÊME thème se le
    partageaient : le premier le renommait vers son nom définitif, le
    second lisait un chemin disparu et mourait sur ``FileNotFoundError``
    — au démarrage de l'app, dans ``_register_routes``.

    Or « deux apps qui démarrent ensemble depuis la même racine » est
    exactement la situation pour laquelle ce cache tient plusieurs
    places. Mesuré le 2026-08-31 avec quatre processus concurrents :
    **3 échecs sur 4** avant, **0 sur 4** après.

    Vérifié ici de façon déterministe plutôt qu'en lançant des
    processus : la course est une question de NOMMAGE, et deux noms
    identiques se constatent sans concurrence. C'est aussi ce qui rend
    ce test rapide et non intermittent — un test de course qui dépend du
    hasard ne garde rien.
    """
    vus: list[Path] = []

    def faux_compile(theme_css, *, output_path, binary=None, minify=True, **kw):
        vus.append(Path(output_path))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("/* x */", encoding="utf-8")

        class _R:
            bytes_written = 1
        return _R()

    monkeypatch.setattr(build_mod, "compile_with_lightning", faux_compile)
    monkeypatch.setattr(build_mod, "find_lightning_binary", lambda: tmp_path / "faux")
    monkeypatch.setattr(build_mod, "_cache_dir", lambda: tmp_path)

    # ``rebuild=True`` force la recompilation : c'est le seul moyen
    # d'obtenir deux passages dans le chemin de compilation pour une
    # seule clé, ce qui EST le cas de la course.
    build_mod.get_or_build_css(_ENTREE_A, rebuild=True)
    build_mod.get_or_build_css(_ENTREE_A, rebuild=True)

    assert len(vus) == 2, f"{len(vus)} compilation(s), 2 attendues"
    assert vus[0] != vus[1], (
        f"les deux compilations ont écrit dans le MÊME fichier "
        f"provisoire ({vus[0].name}). Deux processus qui compilent le "
        f"même thème en même temps se le prendraient : le premier le "
        f"renomme, le second lit un chemin disparu et l'app ne démarre "
        f"pas."
    )
