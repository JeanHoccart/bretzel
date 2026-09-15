"""Gate : la prose de ``bretzel/`` ne nomme plus les directives Alpine.

``test_no_alpine_dialect_survives`` garde ce que le framework **émet** et
ce que le socle **refuse**. Personne ne gardait ce qu'il **raconte** — et
la prose a dérivé pendant tout le rebrand V3 :

- ``state/scopes/client.py`` levait une ``ReactivityError`` dont le
  message conseillait au dev « the runtime emits ``x-text=…`` ». Une
  directive morte, dans une erreur **lue par l'utilisateur** ;
- ``component.py`` documentait ``emit_text_slot`` comme rendant un
  ``<span x-text=…>`` — trois lignes avant d'expliquer correctement que
  la directive est ``bz-text`` ;
- ``reactive_prop.py`` listait ``$store`` parmi les « runtime magic » et
  s'en servait comme exemple canonique d'expression client. ``$store``
  est une magie Alpine : elle n'existe nulle part dans
  ``runtime/_src`` (les vraies sont ``$bz`` / ``$dispatch`` / ``$el`` /
  ``$event`` / ``$refs`` / ``$root``). Une entrée d'allowlist qui
  n'exclut plus rien, exactement la pathologie que l'audit du socle a
  nommée ;
- et trois **titres de pièges vivants** de ``traps.md`` nommaient
  ``x-data``, ce que l'en-tête du funnel demande justement de corriger
  en passant.

Un lecteur — humain ou agent — qui copie une de ces phrases écrit du code
qui ne marche pas, et il n'a aucun moyen de le deviner.

**Portée honnête.** Une mention reste légitime quand elle *raconte* :
« la V3 n'a plus de ``x-cloak`` », « ``$store`` a été retiré le … »,
« matching Alpine's nested-x-data semantics ». Ces cas vivent dans
``_HISTORICAL`` avec leur raison. La gate empêche la réapparition d'un
vocabulaire mort présenté comme vivant, pas le droit de parler du passé.
"""

from __future__ import annotations

import functools
from pathlib import Path

import pytest

#: Preuve de morsure : re-mesure chaque exemption historique : une entrée dont le motif a
#: disparu doit sortir, sinon la table autorise plus que la réalité.
MUTATION_PROOF = "test_historical_entries_are_still_needed"

_BRETZEL = Path(__file__).resolve().parents[2] / "bretzel"

# Les directives et magies du dialecte Alpine. ``x-`` est un préfixe que
# le runtime V3 ne lit nulle part (``02_directives.js`` ne fait de
# ``startsWith`` que sur ``bz-attr:`` et ``bz-on:``).
_DEAD_TOKENS = (
    "x-text", "x-show", "x-model", "x-data", "x-bind",
    "x-for", "x-if", "x-cloak", "x-on:", "$store",
)

# Mentions qui RACONTENT, une par (fichier, token), avec leur raison.
_HISTORICAL: dict[tuple[str, str], str] = {
    ("components/base/attrs.py", "x-show"): (
        "raconte le bug du passthrough : `**{\"x-show\": \"open\"}` partait "
        "dans le DOM, valide et jamais lu. L'exemple EST le propos."
    ),
    ("components/base/component.py", "x-cloak"): (
        "dit que la V3 n'a plus de x-cloak et que c'est le prestamp "
        "`display:none` qui fait le travail."
    ),
    ("components/base/reactive_prop.py", "$store"): (
        "commentaire du 2026-08-01 qui explique le RETRAIT de $store de la "
        "liste des magies — l'entrée n'excluait plus rien."
    ),
    ("render/shell.py", "x-cloak"): (
        "explique que le sélecteur `[bz-data]` + `html.bz-ready` remplace "
        "l'ancien x-cloak."
    ),
    ("runtime/_src/03_scope.js", "x-data"): (
        "comparaison de design assumée : « matching Alpine's nested-x-data "
        "semantics » — on décrit un choix par rapport à un prior art."
    ),
}

_SUFFIXES = (".py", ".js")


@functools.lru_cache(maxsize=1)
def _sources() -> tuple[Path, ...]:
    return tuple(
        p
        for p in sorted(_BRETZEL.rglob("*"))
        if p.suffix in _SUFFIXES
        and "__pycache__" not in p.parts
        # ``runtime.js`` est le BUNDLE : il concatène ``_src/*.js``, donc
        # toute occurrence y est un doublon de sa source.
        and p.name != "runtime.js"
    )


@functools.lru_cache(maxsize=1)
def _hits() -> tuple[tuple[str, str, int, str], ...]:
    """``(chemin relatif, token, ligne, texte)`` pour chaque mention."""
    out: list[tuple[str, str, int, str]] = []
    for path in _sources():
        rel = path.relative_to(_BRETZEL).as_posix()
        for num, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for token in _DEAD_TOKENS:
                if token in line:
                    out.append((rel, token, num, line.strip()))
    return tuple(out)


def test_discovery_non_trivial() -> None:
    """Plancher : la gate lit bien un arbre peuplé."""
    assert len(_sources()) >= 150, (
        f"seulement {len(_sources())} sources balayées sous {_BRETZEL} "
        f"(240+ au 2026-08-01) — le glob est cassé, l'interdiction ne "
        f"porte plus sur rien."
    )


@pytest.mark.parametrize(
    ("rel", "token", "num", "line"),
    _hits(),
    ids=[f"{rel}:{num}:{token}" for rel, token, num, _ in _hits()],
)
def test_no_live_alpine_vocabulary(rel: str, token: str, num: int, line: str) -> None:
    if (rel, token) in _HISTORICAL:
        pytest.skip(f"récit assumé : {_HISTORICAL[(rel, token)]}")
    pytest.fail(
        f"`bretzel/{rel}:{num}` nomme `{token}`, du dialecte Alpine que la "
        f"V3 ne lit nulle part :\n"
        f"    {line[:160]}\n"
        f"  Le runtime ne branche que sur `bz-*` ; les magies réelles sont "
        f"$bz / $dispatch / $el / $event / $refs / $root. Un lecteur qui "
        f"copie cette phrase écrit du code mort — et si c'est un message "
        f"d'erreur, c'est l'utilisateur qu'on envoie dans le mur (c'est "
        f"arrivé : `x-text` conseillé dans une ReactivityError).\n"
        f"  Corrige vers l'équivalent `bz-`, ou — si la phrase RACONTE le "
        f"passé — ajoute (fichier, token) à `_HISTORICAL` AVEC sa raison."
    )


def test_historical_entries_are_still_needed() -> None:
    """Une exception qui ne couvre plus rien doit partir."""
    live = {(rel, token) for rel, token, _, _ in _hits()}
    stale = sorted(key for key in _HISTORICAL if key not in live)
    assert not stale, (
        f"ces entrées de `_HISTORICAL` ne correspondent plus à aucune "
        f"mention : {stale}. Retire-les — une allowlist qui n'excuse plus "
        f"rien est exactement le défaut que cette gate documente."
    )
