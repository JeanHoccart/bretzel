"""Marque les tests de ``tests/runtime_js`` — ``browser``, sauf l'audit.

Ces tests montent le harnais d'audit (uvicorn in-process + Chromium
headless), donc l'invocation rapide par défaut doit les sauter — sinon un
``pytest`` nu lance un Chromium par test et se heurte à la même collision
de boucle d'événements sur le thread principal que la suite ``e2e``.

Deux marqueurs, pas un — et c'est le point de ce fichier
-------------------------------------------------------
``-m browser`` désignait **deux intentions** que rien ne séparait à
l'exécution :

- les tests de runtime proprement dits, ~146 cas à ~4 s → **~10 min**,
  ce qu'on veut pouvoir lancer souvent ;
- ``test_component_audit.py``, l'audit visuel permanent : **74 cas**,
  un par composant, chacun montant uvicorn + Chromium et faisant tourner
  le driver d'audit. Mesuré le 2026-08-16, machine au repos : 57 s pour
  ``button``, 50 s pour ``icon_button``, 37 s pour ``badge``, 25 s pour
  ``alert`` — moyenne ~42 s, soit **~52 min** à lui seul.

Une suite d'une heure ne se lance jamais, et une suite qu'on ne lance pas
pourrit : c'est exactement comme ça que 31 benchs sur 40 sont morts sans
que personne le voie (cf. ``test_probe_benches_still_import``). D'où la
scission — le fichier d'audit le demandait déjà dans sa docstring
(« the place to run before shipping a component, not on every save »),
elle n'était simplement pas vraie à l'exécution.

    pytest                # rapide : ni e2e, ni browser, ni audit
    pytest -m browser     # runtime_js sans l'audit  (~10 min)
    pytest -m audit       # l'audit visuel des composants (~52 min)
    pytest -m e2e         # full-stack, tests/e2e/

Un module qui porte ``pytestmark = pytest.mark.audit`` n'est PAS marqué
``browser`` : les deux marqueurs restent disjoints, sinon ``-m browser``
reprendrait l'heure de run qu'on vient d'en sortir.
"""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    for item in items:
        if "tests/runtime_js" not in str(item.fspath).replace("\\", "/"):
            continue
        if item.get_closest_marker("audit") is not None:
            continue
        item.add_marker(pytest.mark.browser)
