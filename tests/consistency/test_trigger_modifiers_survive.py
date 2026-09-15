"""Un ``debounce=`` ne fait pas disparaître le handler qu'il modifie.

Pourquoi cette gate existe (mesuré le 2026-08-19)
-------------------------------------------------
``action_attrs`` écrit ``hx-trigger`` sous la forme
``"<event> [modificateur] [from:#id]"``, le modificateur venant d'un
``debounce=`` / ``throttle=``. Sept sites de relocation comparaient la
**chaîne entière** au nom d'un event — ``== "change"``,
``in ("focus", "blur")`` — et un huitième y cherchait une **sous-chaîne**
(``"change" in trigger``). Poser un ``debounce=`` faisait donc échouer la
comparaison, et chaque site échouait DIFFÉREMMENT :

- ``ui.combobox(on_change=…, debounce=300)`` — le bundle popé de la
  racine n'était re-stampé nulle part : ``hx-post`` **disparu**, handler
  mort, aucune erreur ;
- ``ui.toggle_group(…)`` — bundle laissé sur la racine, un ``<div>`` qui
  ne fire jamais ``change`` : handler mort aussi ;
- ``ui.file_upload(on_focus=…, debounce=300)`` — idem, sur une racine
  sans ``tabindex`` ;
- Select, Slider et les quatre pickers — le ``debounce=`` demandé
  **silencieusement écrasé** au re-stampage.

Mesuré avant le fix : **3 handlers morts, 7 débounces perdus** sur les
104 couples (composant, event) du catalogue. 16 009 tests étaient verts.

Le fix racine est le lecteur partagé
:func:`~bretzel.components.base._wiring.trigger_event` — l'event est le
PREMIER MOT, jamais la chaîne. Cette gate garde le résultat, pas
l'orthographe : elle construit vraiment chaque composant et lit le HTML.

Ce que la gate n'affirme pas
-----------------------------
Que le handler part au bon moment dans un navigateur — seul un probe le
dit. Elle ferme la classe mesurée : le ``debounce=`` fait DISPARAÎTRE ou
DÉPLACER ce qu'il ne devait que temporiser.
"""

from __future__ import annotations

import re

from bretzel.components.base._wiring import retrigger, trigger_event
from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from tests.consistency._discovery import (
    ui_name_of,
    wired_component,
    wired_couples,
)

#: Un délai qui ne peut pas être celui d'un composant : ``combobox``
#: pose 200 ms de son propre chef pour ``on_search``.
DEBOUNCE_MS = 317

_HX_POST_HOST = re.compile(r"<(\w+)([^>]*\bhx-post=[^>]*)>")


def _wired_hosts(html: str) -> list[tuple[str, str]]:
    """``(tag, hx-trigger)`` de chaque élément qui porte l'action serveur."""
    out = []
    for match in _HX_POST_HOST.finditer(html):
        triggers = re.findall(r'hx-trigger="([^"]*)"', match.group(2))
        out.append((match.group(1), triggers[0] if triggers else ""))
    return out


def _render(cls: type, event: str, **extra: object) -> str:
    """Le HTML du composant avec un handler câblé sur ``event``.

    La construction elle-même vit dans le lecteur partagé
    :func:`~tests.consistency._discovery.wired_component` — avec son
    handler AU NIVEAU MODULE, dont l'absence de ``<locals>`` dans le
    qualname est une condition du socle, et son « aucun rattrapage »
    (un ``except`` ferait sortir en silence le premier composant qui
    casserait, ce que ``test_no_gate_swallows_a_component`` interdit).
    """
    with render_isolated():
        return serialize(wired_component(cls, event, **extra).render())


def posting_couples() -> list[tuple[type, str]]:
    """Les couples (composant, event) qui posent VRAIMENT un ``hx-post``.

    Le recensement complet vient de
    :func:`~tests.consistency._discovery.wired_couples` — partagé pour
    que deux gates qui disent mesurer « les 104 couples » partent bien du
    même endroit. Un event déclaré dans ``EVENTS`` mais qui ne produit
    aucune action serveur (forme client-only) n'a rien à dire ici.
    """
    return [
        (cls, event) for cls, event in wired_couples()
        if "hx-post" in _render(cls, event)
    ]


def offenders() -> list[str]:
    """Les couples qui perdent leur handler, son hôte, ou son modificateur."""
    out: list[str] = []
    for cls, event in posting_couples():
        plain = _render(cls, event)
        slowed = _render(cls, event, debounce=DEBOUNCE_MS)
        name = f"{ui_name_of(cls)}.on_{event}"
        if "hx-post" not in slowed:
            out.append(f"{name} : ``hx-post`` DISPARU avec debounce=")
            continue
        before, after = _wired_hosts(plain), _wired_hosts(slowed)
        if [tag for tag, _ in before] != [tag for tag, _ in after]:
            out.append(
                f"{name} : le handler CHANGE d'hôte avec debounce= "
                f"({[t for t, _ in before]} → {[t for t, _ in after]})"
            )
            continue
        if not any(f"delay:{DEBOUNCE_MS}ms" in trigger for _, trigger in after):
            out.append(
                f"{name} : ``debounce=`` accepté puis PERDU — "
                f"hx-trigger={[t for _, t in after]}"
            )
    return out


def test_the_sweep_is_not_vacuous() -> None:
    """Le plancher lit la découverte de CETTE gate, pas un recomptage.

    Deux façons de vider ce balayage : ne plus trouver de composant, et
    n'en construire aucun (un ``bare_kwargs`` cassé rendrait la gate
    verte en n'ayant rendu personne).
    """
    couples = wired_couples()
    assert len(couples) >= 90, (
        f"seulement {len(couples)} couples (composant, event) posent un "
        f"``hx-post`` (>= 90 attendus, 104 le 2026-08-19) — le balayage "
        f"est cassé, et « aucun debounce ne perd son handler » serait "
        f"affirmé sur presque rien."
    )
    assert len({cls for cls, _ in couples}) >= 30


def test_a_debounce_never_kills_the_handler_it_slows() -> None:
    found = offenders()
    assert not found, (
        "Poser ``debounce=`` sur ces composants ne fait pas que temporiser "
        "l'action — elle disparaît, change d'hôte, ou le délai est ignoré. "
        "La cause est toujours la même : ``hx-trigger`` comparé comme une "
        "CHAÎNE alors qu'il porte ``\"<event> <modificateur>\"``. Passe par "
        "``_wiring.trigger_event`` :\n  " + "\n  ".join(found)
    )


def test_the_detector_still_bites() -> None:
    """Les deux versants, sur les deux lecteurs partagés."""
    # Ce que le bug faisait : la sous-chaîne dit « change » là où l'event
    # n'est pas ``change`` — les deux cas RÉELS du dépôt.
    assert "change" in "month_change"
    assert "change" in "input changed delay:200ms"
    assert trigger_event({"hx-trigger": "month_change"}) == "month_change"
    assert trigger_event({"hx-trigger": "input changed delay:200ms"}) == "input"

    # Le versant licite : un event nu, et un event modifié, donnent le
    # MÊME event — c'est toute la raison d'être du lecteur.
    assert trigger_event({"hx-trigger": "change"}) == "change"
    assert trigger_event({"hx-trigger": "change delay:300ms"}) == "change"
    assert trigger_event({}) == ""

    # ``retrigger`` renomme l'event et GARDE la suite.
    assert retrigger("month_change delay:300ms", "month-change") == (
        "month-change delay:300ms"
    )
    assert retrigger("month_change", "month-change") == "month-change"
