"""Les events de cycle de vie ne bullent pas — et les deux côtés le disent.

``open`` / ``close`` appartiennent à la racine du composant qui les
émet. Le runtime le fait respecter (``SCOPED_EVENTS`` dans
``_src/02_directives.js``, lu par ``makeDispatch``) ; le socle Python
s'appuie sur le même fait (``_wiring.ROOT_DISPATCHED_EVENTS``, lu par
``relocate_server_action`` pour NE PAS déplacer un bundle ``open`` /
``close`` — il est déjà sur le bon élément).

Deux fichiers, deux langages, **un seul fait**. Le JS ne peut pas
importer le Python : il re-code la liste en dur, donc elle dérive.

Pourquoi ce fait existe (mesuré au navigateur le 2026-08-19)
------------------------------------------------------------
``$dispatch`` construisait TOUT événement avec ``bubbles: true``, et
``on_open=`` / ``on_close=`` posent leur ``hx-trigger`` sur la RACINE du
composant — qui attrapait donc aussi ceux de ses descendants :

- ``ui.select`` dans un ``ui.dialog(on_open=…)`` → ouvrir le panneau
  POSTait le handler DU DIALOG ;
- ``ui.alert(dismissible=True)`` dans un ``ui.dialog(on_close=…)`` →
  congédier l'alerte POSTait le ``on_close`` DU DIALOG.

Huit composants exposent ces events, huit les émettent : n'importe quel
émetteur imbriqué dans n'importe quel écouteur fuyait. Repro et
non-régression : ``tests/probes/probe_overlay_bubble.py``.

Ce que la gate n'affirme pas
-----------------------------
Que le runtime *applique* la règle — ça, c'est le probe navigateur.
Elle ferme la dérive des DEUX LISTES : ajouter un event scopé d'un seul
côté ne lève rien, ne s'affiche pas, et ne se voit pas en revue.
"""

from __future__ import annotations

import re

from bretzel.components.base._wiring import ROOT_DISPATCHED_EVENTS
from tests.consistency._discovery import (
    assert_runtime_sweep_is_not_vacuous,
    runtime_slabs,
    strip_js_comments,
)

#: Preuve de morsure : le contrôle NÉGATIF vit dans
#: ``test_the_detector_still_bites``.
MUTATION_PROOF = "test_the_detector_still_bites"

_DECLARATION = re.compile(
    r"SCOPED_EVENTS\s*=\s*new\s+Set\(\s*\[(?P<body>[^\]]*)\]"
)
_NAME = re.compile(r"""['"]([^'"]+)['"]""")


def scoped_events_in_js(sources: dict[str, str]) -> set[str] | None:
    """L'ensemble déclaré côté JS — ``None`` si la déclaration a disparu.

    Extrait plutôt qu'inline pour être MUTABLE : c'est ce détecteur que
    ``test_the_detector_still_bites`` fabrique une violation pour.
    """
    for source in sources.values():
        match = _DECLARATION.search(strip_js_comments(source))
        if match:
            return set(_NAME.findall(match.group("body")))
    return None


def js_sources() -> dict[str, str]:
    """Les slabs de ``_src/`` — la source qu'on ÉDITE, pas l'artefact.

    ``runtime.js`` est concaténé depuis ceux-ci et sa fraîcheur est
    gardée par ``test_runtime_bundle_is_fresh`` : le lire ici ferait
    juger deux fois la même chose, et la mauvaise fois.
    """
    return {p.name: p.read_text(encoding="utf-8") for p in runtime_slabs()}


def test_the_sweep_is_not_vacuous() -> None:
    """Plancher : les slabs sont là, ET la déclaration a été trouvée."""
    assert_runtime_sweep_is_not_vacuous()
    assert scoped_events_in_js(js_sources()) is not None, (
        "``SCOPED_EVENTS = new Set([…])`` est introuvable dans ``_src/``. "
        "Sans elle, ``makeDispatch`` refait buller ``open``/``close`` et "
        "un overlay imbriqué re-déclenche le handler de son ancêtre — "
        "sans erreur, sans trace, juste un POST de trop."
    )
    assert ROOT_DISPATCHED_EVENTS, "le côté Python est vide"


def test_the_two_sides_declare_the_same_events() -> None:
    in_js = scoped_events_in_js(js_sources())
    assert in_js == set(ROOT_DISPATCHED_EVENTS), (
        f"les deux côtés ne nomment plus les mêmes events de cycle de "
        f"vie : JS={sorted(in_js or ())} vs "
        f"Python={sorted(ROOT_DISPATCHED_EVENTS)}.\n"
        f"  Le JS décide s'il BULLE, le Python décide s'il DÉPLACE le "
        f"bundle d'action. Un event ajouté d'un seul côté donne donc soit "
        f"un handler relogé sur un élément qui ne le fire jamais, soit un "
        f"POST fantôme chez l'ancêtre. Les deux sont silencieux."
    )


def test_the_detector_still_bites() -> None:
    """Les deux versants, sur une source FABRIQUÉE."""
    licit = {"x.js": 'const SCOPED_EVENTS = new Set(["open", "close"]);'}
    assert scoped_events_in_js(licit) == {"open", "close"}

    drifted = {"x.js": 'const SCOPED_EVENTS = new Set(["open"]);'}
    assert scoped_events_in_js(drifted) == {"open"}
    assert scoped_events_in_js(drifted) != set(ROOT_DISPATCHED_EVENTS), (
        "un ensemble AMPUTÉ passe encore pour le bon — la comparaison ne "
        "distingue plus rien."
    )

    # Le versant qui a trouvé les vrais faux positifs du dépôt : une
    # source qui PARLE de la constante sans la déclarer ne doit pas être
    # lue comme une déclaration.
    prose = {"x.js": "// SCOPED_EVENTS = new Set([\"open\", \"close\"]) jadis\nfoo();"}
    assert scoped_events_in_js(prose) is None, (
        "un commentaire est lu comme du code — la gate resterait verte "
        "sur un runtime où la constante a été RETIRÉE, tant que la note "
        "de son retrait reste."
    )
