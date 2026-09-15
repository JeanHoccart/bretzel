"""Aucun jeton de build ne part dans le bundle sans avoir été remplacé.

Le fait gardé
--------------
Le runtime ne peut pas importer Python, donc les quelques chaînes que
les deux langages doivent nommer PAREIL — la version de protocole, les
balises ``<bz-envelope>`` / ``<bz-patch>``, la route d'action, la clé
réservée de la barre de navigation — sont écrites en clair dans les
slabs sous la forme ``__NOM__`` et **substituées au build** depuis
``protocol.py`` (:mod:`bretzel.runtime._build`). C'est le mécanisme qui
empêche le JS de redevenir tiers au format de fil.

Il a un mode d'échec, et il est muet : ajouter un ``__NOM__`` dans un
slab **sans** l'ajouter à la table de ``_build``. Le build ne se plaint
pas — il remplace ce qu'il connaît et copie le reste. Le bundle part
alors avec le littéral ``"__NOM__"`` dedans, et le JS travaille avec
cette chaîne comme si c'était une valeur : il arme une clé que
personne ne lit, compare une balise à un nom qui n'existe pas, POSTe
vers une route inventée. Rien ne lève, ni au build, ni au boot, ni au
premier clic.

C'est arrivé au bord près en ajoutant ``__ROUTE_ACTION__`` et
``__NAV_PENDING_KEY__`` le 2026-08-27 : deux jetons, deux lignes à
tenir dans une table que rien ne reliait aux slabs.

Ce que la gate n'affirme PAS
-----------------------------
Que la VALEUR substituée est la bonne — ``__PATCH_TAG__`` remplacé par
la version de protocole passerait ici. Elle ferme la classe « le jeton
n'a été remplacé par rien du tout », qui est celle qui ne se voit
nulle part. La justesse des valeurs se lit dans ``_build._TOKENS``, où
chacune vient de ``protocol.py`` par import.

Elle ne juge pas non plus les slabs : c'est dans ``_src/`` que les
jetons DOIVENT apparaître. Elle ne regarde que ce qui part au
navigateur.
"""

from __future__ import annotations

import re

from bretzel.runtime._build import _TOKENS
from tests.consistency._discovery import REPO_ROOT

#: Preuve de morsure : le contrôle NÉGATIF vit dans
#: ``test_the_detector_still_bites``.
MUTATION_PROOF = "test_the_detector_still_bites"

#: ``__NOM__`` en CAPITALES. La casse est le filtre qui évite le seul
#: faux positif plausible : ``__proto__`` et ses cousins JavaScript sont
#: en minuscules, et un jeton de build de ce dépôt ne l'est jamais.
_LEFTOVER = re.compile(r"__[A-Z][A-Z0-9_]*__")

_BUNDLES = ("runtime.js", "runtime.min.js")


def leftovers_in(source: str) -> set[str]:
    """Les jetons non substitués d'un bundle.

    Extrait plutôt qu'inline pour être MUTABLE : c'est ce détecteur que
    ``test_the_detector_still_bites`` nourrit de sources fabriquées.
    """
    return set(_LEFTOVER.findall(source))


def _bundle_texts() -> dict[str, str]:
    out: dict[str, str] = {}
    for name in _BUNDLES:
        path = REPO_ROOT / "bretzel" / "runtime" / name
        assert path.is_file(), f"{name} est introuvable — le build a-t-il tourné ?"
        out[name] = path.read_text(encoding="utf-8")
    return out


def test_the_sweep_is_not_vacuous() -> None:
    """Plancher ancré sur la DÉCOUVERTE, pas sur la population.

    Deux façons pour cette gate de devenir muette sans le dire : la
    table de substitution vidée (plus rien à remplacer, donc plus rien
    à rater), ou les bundles introuvables (on juge une chaîne vide).
    Les deux sont vérifiées ici, ainsi que le fait que les jetons ont
    la FORME que le détecteur cherche — une table renommée en
    ``{NOM}`` laisserait la regex chercher un motif que plus personne
    n'écrit.
    """
    assert _TOKENS, "la table de substitution de ``_build`` est vide"
    for token in _TOKENS:
        assert _LEFTOVER.fullmatch(token), (
            f"``{token}`` n'a pas la forme ``__NOM__`` que le détecteur "
            f"cherche. La convention a changé sans que la gate suive : "
            f"elle balaierait encore, mais pour rien."
        )

    texts = _bundle_texts()
    assert len(texts) == len(_BUNDLES)
    for name, text in texts.items():
        assert len(text) > 10_000, f"{name} fait {len(text)} octets — bundle tronqué ?"


def test_no_token_survives_substitution() -> None:
    found = {
        name: sorted(left)
        for name, text in _bundle_texts().items()
        if (left := leftovers_in(text))
    }
    assert not found, (
        "Des jetons de build partent au navigateur sans valeur :\n  "
        + "\n  ".join(f"{name} — {', '.join(toks)}" for name, toks in found.items())
        + "\n\nAjoute-les à ``_TOKENS`` dans ``bretzel/runtime/_build.py``, "
        "avec leur valeur prise dans ``protocol.py``. En l'état le JS "
        "traite le littéral comme une valeur : il arme une clé que "
        "personne ne lit, ou compare une balise à un nom qui n'existe "
        "pas. Rien ne lève."
    )


def test_the_detector_still_bites() -> None:
    """Les deux versants, sur des sources FABRIQUÉES."""
    # ── Versant ILLICITE : un jeton oublié est vu ─────────────────────
    assert leftovers_in('const K = "__NAV_PENDING_KEY__";') == {"__NAV_PENDING_KEY__"}
    assert leftovers_in("a = __A__; b = __B_2__;") == {"__A__", "__B_2__"}

    # ── Versant LICITE : ce que le JS écrit légitimement ──────────────
    # C'est le versant qui décide de la casse dans la regex : sans elle
    # la gate rougirait sur tout runtime touchant au prototype, donc
    # elle serait désactivée le jour où quelqu'un en a besoin.
    assert leftovers_in("obj.__proto__ = null;") == set()
    assert leftovers_in("el.__bzTick = 1; f(__dirname);") == set()
    # Un seul souligné de chaque côté n'est pas un jeton.
    assert leftovers_in("const _NAV_ = 1;") == set()

    # ── Et le bundle réel passe bien par ce détecteur ─────────────────
    for text in _bundle_texts().values():
        assert not leftovers_in(text)
