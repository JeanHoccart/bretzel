"""Gate — un bundle d'action posé sur un input CACHÉ a quelqu'un pour le tirer.

Le défaut qu'elle ferme (mesuré le 2026-08-21)
----------------------------------------------
Un composant riche a une racine ``<div>`` : elle ne porte ni ``name`` ni
``value``, donc ``relocate_server_action`` déménage le bundle
``hx-post`` / ``hx-trigger="change"`` sur un ``<input type="hidden">`` —
le seul élément que la FormData trouvera. Ce déménagement crée une dette
que rien ne réclamait : **un input caché ne fire JAMAIS ``change`` tout
seul**, et une écriture programmatique de ``.value`` n'émet aucun
événement. Quelqu'un doit donc le dispatcher.

Onze porteurs le font par le ``bz-effect`` partagé
(:func:`~bretzel.components.base._wiring.change_emit_effect`), trois par
du JS de runtime. **Les cinq pickers ne le faisaient par rien** :
``ui.date_picker``, ``ui.date_range_picker``, ``ui.time_picker``,
``ui.month_picker`` et ``ui.week_picker`` acceptaient un ``on_change=``
serveur, écrivaient la valeur, la portaient dans la form data — et ne
POSTaient jamais. Symptôme rapporté : « la période ne filtre pas ».
Mesuré : 0 requête, aucune erreur, aucun avertissement.

Pourquoi 16 076 tests ne l'ont pas vu
--------------------------------------
Sa jumelle ``test_a_bound_control_transmits_every_value`` vérifie qu'un
contrôle lié transmet sa valeur **à la soumission d'un formulaire** — et
les cinq pickers la passent : dans un ``<form>``, ils marchent. Ce que
personne ne vérifiait, c'est l'AUTRE moitié du même contrat : qu'ils
déclenchent leur propre événement. Porter la valeur et annoncer qu'elle a
changé sont deux promesses distinctes, et le catalogue n'en gardait qu'une.

Le périmètre, et pourquoi il s'arrête là
-----------------------------------------
Balayage des 104 couples (composant, event) : **19 bundles** atterrissent
sur un ``<input type="hidden">``, tous les autres sur un élément qui reçoit
son événement — nativement (``input`` visible, ``textarea``, ``button``),
par bullage (le ``<div>`` de ``file_upload`` au-dessus de son
``<input type=file>``), ou par une CustomEvent que le runtime dispatche sur
cette racine (``open`` / ``close`` / ``upload-*``). L'input caché est le
seul hôte STRUCTURELLEMENT muet du catalogue : c'est là, et seulement là,
qu'un dispatcher doit être prouvé.

Ce qu'elle garde en plus de la primitive
-----------------------------------------
Depuis le 2026-08-21 le dispatcher est ACQUIS dans
:func:`~bretzel.components.base._wiring.hidden_carrier_attrs` — un appelant
doit désormais le REFUSER explicitement. Cette gate reste nécessaire pour
les **quatre porteurs écrits à la main** (calendar, combobox, select,
dropzone), que la primitive ne peut pas atteindre.

Ce qu'elle n'affirme pas
-------------------------
Que le POST parte au bon moment dans un navigateur — seul un probe le dit
(``tests/probes/probe_crm_findings.py``, sections D et E). Elle ferme la
classe : *un porteur muet sans personne pour le faire parler*.
"""

from __future__ import annotations

import functools

import pytest

from bretzel.components.base._wiring import change_emit_effect, trigger_event
from bretzel.components.base.testing import render_isolated
from bretzel.core.tree import Element
from tests.consistency._discovery import (
    runtime_slabs,
    strip_js_comments,
    ui_name_of,
    walk_elements,
    wired_component,
    wired_couples,
)

#: Le plancher du balayage. 19 bundles atterrissent sur un porteur muet
#: au 2026-08-21 ; le seuil laisse partir un composant sans laisser
#: passer un balayage cassé (une construction qui échouerait en masse, ou
#: un ``EVENTS`` qu'on ne lirait plus).
_SILENT_HOSTS_FLOOR = 15

#: Ce qui, dans un ``bz-effect``, dispatche vraiment. **Un seul signe, et
#: c'est délibéré** : ``emitChange`` est un helper de RUNTIME, appelé
#: depuis une méthode de scope, jamais depuis un ``bz-effect`` — l'ajouter
#: élargirait le détecteur sans couvrir un cas réel, et lui ferait accepter
#: un effet qui se contente de nommer le mot.
_DISPATCH_SIGN = "dispatchEvent"

#: Les porteurs dont le dispatcher vit dans le RUNTIME, pas dans un
#: ``bz-effect``. Chaque entrée nomme le slab et le symbole qui tirent
#: l'événement — et les deux sont VÉRIFIÉS (cf.
#: ``test_the_js_dispatchers_still_exist``), pour qu'une exemption ne
#: puisse pas survivre au code qu'elle invoque.
_DISPATCHED_BY_RUNTIME: dict[tuple[str, str], tuple[str, str]] = {
    ("calendar", "change"): ("07_calendar.js", "_syncHiddenAndFireChange"),
    ("slider", "change"): ("06_helpers.js", "emitChange"),
    ("dropzone", "move"): ("19_dnd.js", "emitChange"),
}


@functools.cache
def silent_hosts() -> tuple[tuple[str, str, Element], ...]:
    """``(nom ui, event, élément)`` de chaque bundle posé sur un input caché.

    La population est DÉCOUVERTE en construisant chaque composant public
    avec chacun de ses ``EVENTS`` (le recensement partagé
    :func:`~tests.consistency._discovery.wired_couples`), jamais listée :
    un picker de plus la rejoint tout seul.

    Cachée — quatre tests la lisent, et l'arbre rendu est immuable
    (``Element`` est un dataclass gelé), donc le partage est sans risque.
    """
    found: list[tuple[str, str, Element]] = []
    for cls, event in wired_couples():
        with render_isolated():
            tree = wired_component(cls, event).render()
        for element in walk_elements(tree):
            attrs = element.attrs
            if "hx-post" not in attrs:
                continue
            if element.tag != "input" or attrs.get("type") != "hidden":
                continue
            found.append((ui_name_of(cls), trigger_event(attrs), element))
    return tuple(found)


def _has_effect_dispatcher(element: Element) -> bool:
    return _DISPATCH_SIGN in str(element.attrs.get("bz-effect", ""))


# ───────────────────────────────────────────────────────────────────────
# Le plancher — la population existe encore
# ───────────────────────────────────────────────────────────────────────


def test_the_sweep_is_not_vacuous() -> None:
    hosts = silent_hosts()
    assert len(hosts) >= _SILENT_HOSTS_FLOOR, (
        f"seulement {len(hosts)} bundle(s) d'action sur un input caché — "
        f"il y en avait 19 le 2026-08-21. Soit la relocation a changé de "
        f"cible, soit la construction des composants échoue : dans les "
        f"deux cas cette gate ne garde plus rien."
    )


# ───────────────────────────────────────────────────────────────────────
# L'interdiction — sur CHAQUE porteur découvert
# ───────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "case", silent_hosts(), ids=lambda c: f"{c[0]}.on_{c[1]}"
)
def test_a_silent_carrier_has_a_dispatcher(
    case: tuple[str, str, Element],
) -> None:
    name, event, element = case
    if (name, event) in _DISPATCHED_BY_RUNTIME:
        pytest.skip("dispatché par le runtime — cf. _DISPATCHED_BY_RUNTIME")
    assert _has_effect_dispatcher(element), (
        f"ui.{name}.on_{event} pose son `hx-post` sur un "
        f"<input type=hidden>, qui ne fire JAMAIS `{event}` tout seul : "
        f"le handler serveur ne partira jamais, sans une erreur ni un "
        f"avertissement.\n"
        f"  Le dispatcher est ACQUIS quand le porteur passe par "
        f"`hidden_carrier_attrs` ; ce porteur-ci l'a refusé "
        f"(`dispatch=None`) ou écrit son squelette à la main.\n"
        f"  Si ton dispatch vit dans le runtime, déclare-le dans "
        f"`_DISPATCHED_BY_RUNTIME` avec le slab et le symbole qui le "
        f"tirent."
    )


# ───────────────────────────────────────────────────────────────────────
# Les exemptions ne pourrissent pas
# ───────────────────────────────────────────────────────────────────────


def test_the_js_dispatchers_still_exist() -> None:
    """Une exemption nomme un slab et un symbole ; les deux doivent vivre.

    Lu à travers :func:`strip_js_comments` — sans quoi un symbole survivant
    dans le COMMENTAIRE de son propre retrait garderait l'exemption verte
    pendant que le dispatcher a disparu. C'est le mode d'échec pour lequel
    ce lecteur a été promu.
    """
    wanted = {slab for slab, _ in _DISPATCHED_BY_RUNTIME.values()}
    code = {
        path.name: strip_js_comments(path.read_text(encoding="utf8"))
        for path in runtime_slabs()
        if path.name in wanted
    }
    for (name, event), (slab, symbol) in _DISPATCHED_BY_RUNTIME.items():
        assert slab in code, (
            f"ui.{name}.on_{event} est exempté au nom de `{slab}`, qui "
            f"n'existe plus dans `bretzel/runtime/_src/`."
        )
        assert symbol in code[slab], (
            f"ui.{name}.on_{event} est exempté parce que `{slab}` "
            f"dispatche via `{symbol}` — ce symbole a disparu du CODE du "
            f"slab. Soit le dispatch a déménagé (mets l'entrée à jour), "
            f"soit il n'existe plus et le composant est INERTE."
        )


def test_the_runtime_debt_only_lists_real_carriers() -> None:
    """Une exemption dont le porteur n'existe plus est une exemption morte."""
    live = {(name, event) for name, event, _ in silent_hosts()}
    ghosts = sorted(_DISPATCHED_BY_RUNTIME.keys() - live)
    assert not ghosts, (
        f"_DISPATCHED_BY_RUNTIME exempte des couples qui ne posent plus "
        f"d'action sur un input caché : {ghosts}. Retire-les — une "
        f"exemption qui ne protège plus rien cache le jour où elle "
        f"protégerait le mauvais."
    )


# ───────────────────────────────────────────────────────────────────────
# La preuve que le détecteur mord
# ───────────────────────────────────────────────────────────────────────


def test_the_detector_still_bites() -> None:
    """Trois cas fabriqués : le vrai porteur, le muet, et le faux ami.

    Le contrôle POSITIF compte autant que la violation : un détecteur qui
    accepte le dispatcher réel n'est pas aveugle, et c'est ce qui a
    manqué aux trois gates que ce dépôt a livrées vertes-sur-rien.
    """
    wired = Element(
        tag="input",
        attrs={
            "type": "hidden",
            "hx-post": "/x",
            "bz-effect": change_emit_effect("val"),
        },
    )
    assert _has_effect_dispatcher(wired), (
        "le détecteur ne reconnaît plus `change_emit_effect` — il est "
        "aveugle, et la gate resterait verte sur un catalogue entier de "
        "porteurs muets."
    )

    mute = Element(tag="input", attrs={"type": "hidden", "hx-post": "/x"})
    assert not _has_effect_dispatcher(mute)

    # Le faux ami : un ``bz-effect`` qui existe mais ne dispatche rien —
    # exactement la forme des cinq pickers AVANT le 2026-08-21, dont le
    # wrapper portait un effet (le miroir vers ``<bz-calendar>``) sans
    # aucun dispatch.
    decoy = Element(
        tag="input",
        attrs={
            "type": "hidden",
            "hx-post": "/x",
            "bz-effect": "(() => { const cal = $el.querySelector('x'); })()",
        },
    )
    assert not _has_effect_dispatcher(decoy), (
        "le détecteur accepte un `bz-effect` qui ne dispatche rien — il "
        "vérifie la PRÉSENCE d'un effet au lieu de son contenu."
    )


def test_the_shared_dispatcher_really_dispatches() -> None:
    """Le contrôle positif sur la primitive elle-même."""
    body = change_emit_effect("val")
    assert "dispatchEvent" in body and "'change'" in body, (
        f"`change_emit_effect` ne dispatche plus de `change` : {body!r}"
    )
