"""Gate — une balise changée ne traîne pas les attributs de l'ancienne.

Le défaut qu'elle ferme (finding [6], mesuré le 2026-08-23)
------------------------------------------------------------
``tag=`` est un kwarg **universel** : n'importe quel composant peut voir
sa balise remplacée. Mais chaque composant déclare ses props contre sa
``DEFAULT_TAG``, et plusieurs ont un défaut non-``None`` qui sort donc
toujours — ``Button.type`` vaut ``"button"``, ``Image.alt`` est
obligatoire. Quand la balise change, ces attributs restaient là.

Trouvé en instruisant « il manque un lien-bouton » : l'échappatoire
``ui.button(tag="a", attrs={"href": …})`` marchait déjà — habillage
complet, ancre correcte — mais rendait ``<a type="button">``. Sur un
``<a>``, ``type`` désigne le **type MIME de la cible**. Le HTML n'était
pas invalide, il était faux, et silencieusement.

Le balayage a trouvé **quatre** composants dans ce cas, trois avec le
même ``type="button"`` : ``ui.button``, ``ui.icon_button``,
``ui.dropdown_item``, ``ui.sidebar_footer_item``, plus ``ui.image`` et
son ``alt``. Aucun ne l'avait vu, parce qu'aucun test ne change de
balise.

Où le correctif est posé — et pourquoi à DEUX endroits
--------------------------------------------------------
Au point d'assemblage d'abord : ``Component._drop_attrs_the_tag_cannot_carry``,
appelé en fin d'``emit_attrs``. C'est le seul endroit où la balise et le
sac d'attributs se rencontrent pour tout le catalogue, donc un composant
neuf est couvert sans rien faire.

Mais deux composants écrivent leur attribut **après** ``emit_attrs``
(``menu_item`` pose son ``type``, ``image`` son ``alt``), donc hors de
portée. Ils portent leur propre garde, et c'est exactement pour ça que
cette gate lit le **rendu** plutôt que le helper : elle ne suppose pas
que tout le monde passe par le choke point.

⚠️ Ce que l'appelant a écrit lui-même est épargné —
``attrs={"type": "text/html"}`` sur un ``<a>`` est un vrai type MIME, et
l'échappatoire brute a le dernier mot partout ailleurs.

Ce qu'elle n'affirme PAS
-------------------------
Que la balise choisie soit la bonne, ni que le composant reste
utilisable sous une autre balise (``ui.button(tag="section")`` perd le
clavier). Elle ferme une classe étroite : *un attribut qui ment sur ce
qu'il désigne*.
"""

from __future__ import annotations

import re

from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from tests.consistency._discovery import (
    bare_kwargs,
    public_component_classes,
    ui_name_of,
)

#: Les attributs dont le SENS est lié à une balise, avec les balises où
#: ils en ont un. Le miroir de ``Component._TAG_BOUND_ATTRS`` — écrit ici
#: à la main **exprès** : une gate qui importerait la table du framework
#: resterait verte si on la vidait.
_BOUND: dict[str, frozenset[str]] = {
    "type": frozenset({"button", "input", "ol", "link", "script", "style"}),
    "href": frozenset({"a", "link", "area", "base"}),
    "src": frozenset(
        {
            "img", "script", "iframe", "video", "audio", "source",
            "embed", "track", "input",
        }
    ),
    "alt": frozenset({"img", "area", "input"}),
    "for": frozenset({"label", "output"}),
    "target": frozenset({"a", "area", "form", "base"}),
}

#: La balise de sonde. Neutre par construction : ``<section>`` ne porte
#: aucun des attributs ci-dessus, donc tout ce qui reste est de trop.
_PROBE_TAG = "section"

#: **Les abstentions, NOMMÉES** — pas un plafond chiffré (cf. ``gates.md``).
#: Deux natures, et la distinction compte :
#:
#: - trois composants REFUSENT ``tag=`` par conception, chacun avec son
#:   message écrit. Ils sont hors population, définitivement ;
#: - deux exigent un argument que ``bare_kwargs`` ne fournit pas. C'est
#:   une limite du bâtisseur partagé, pas une propriété du composant :
#:   si ``bare_kwargs`` apprend à les construire, ils rentrent et il
#:   faudra retirer l'entrée — ce que ``test_the_abstentions_are_declared``
#:   exige.
_REFUSES_A_TAG = {
    "fragment": "pas d'élément enveloppant — rien à quoi attacher un attribut",
    "meta_tag": "n'accepte que name / property / http_equiv / content",
    "title": "le <title> ne porte aucun attribut que Bretzel utilise",
}
_NEEDS_MORE_THAN_BARE = {
    # `datatable` est SORTI de cette liste le 2026-09-07 : en déclarant
    # son `item_click`, il est entré dans le recensement de
    # `wired_couples`, et `bare_kwargs` a appris à le bâtir (état
    # sonde, une colonne, deux lignes). Il n'y a plus de raison de
    # s'en abstenir.
    "toggle_button": "exige un `value` positionnel",
}

#: ``(?:="…")?`` est load-bearing : un attribut BOOLÉEN s'écrit nu
#: (``<audio controls>``), et une racine qui en porte un ne matchait pas.
#: Trois composants — audio, video, interval — sortaient alors du
#: balayage **en se confondant avec un refus de construction**. C'est
#: ``test_the_abstentions_are_declared`` qui l'a dit, pas moi.
_ROOT = re.compile(r'<([\w-]+)((?:\s+[a-zA-Z][\w:.-]*(?:="[^"]*")?)*)\s*/?>')
_ATTR = re.compile(r'(?:^|\s)([a-zA-Z][\w:.-]*)(?:="[^"]*")?')


def _root_of(html: str) -> tuple[str, list[str]] | None:
    """``(balise, noms d'attributs)`` de l'élément racine.

    Parse les attributs plutôt que de chercher le motif dans la chaîne
    entière : la première écriture de ce détecteur cherchait ``type=``
    au regex dans tout le tag ouvrant, et voyait un faux positif sur
    ``ui.radio_group`` — dont un ``bz-on:`` contient
    ``input[type="radio"]`` dans son EXPRESSION JS.
    """
    m = _ROOT.match(html)
    if m is None:
        return None
    return m.group(1), _ATTR.findall(m.group(2))


def _probe(cls: type) -> tuple[str, list[str]] | None:
    """Rendre ``cls`` sous la balise de sonde. ``None`` si elle REFUSE.

    Le ``None`` ne dit qu'une chose : le composant n'accepte pas
    ``tag=``. Une racine illisible LÈVE au lieu de se taire — sinon un
    parseur cassé se déguiserait en abstention, et la table des
    abstentions absorberait la panne.
    """
    try:
        with render_isolated():
            html = serialize(cls(**bare_kwargs(cls), tag=_PROBE_TAG).render())
    except TypeError:
        return None
    parsed = _root_of(html)
    if parsed is None:
        raise AssertionError(
            f"racine illisible pour ui.{ui_name_of(cls)} : {html[:120]!r}. "
            f"Le parseur de ce fichier est cassé — corrige-le, ne déclare "
            f"pas une abstention."
        )
    return parsed


def stale_attrs() -> list[str]:
    """Les couples (composant, attribut) que la nouvelle balise ne porte pas."""
    found: list[str] = []
    for cls in public_component_classes():
        probed = _probe(cls)
        if probed is None:
            continue
        tag, names = probed
        for name in names:
            if name in _BOUND and tag not in _BOUND[name]:
                found.append(f"ui.{ui_name_of(cls)} → <{tag} {name}=…>")
    return sorted(found)


def abstentions() -> list[str]:
    return sorted(
        ui_name_of(cls) for cls in public_component_classes() if _probe(cls) is None
    )


def test_the_sweep_is_not_vacuous() -> None:
    """① Le plancher, lu sur LA découverte de cette gate."""
    probed = [c for c in public_component_classes() if _probe(c) is not None]
    assert len(probed) >= 90, (
        f"seulement {len(probed)} composants rendus sous `tag=` "
        f"(92 le 2026-08-23) : la gate jugerait sur un échantillon."
    )


def test_the_abstentions_are_declared() -> None:
    """Aucun composant n'échappe au balayage en silence.

    Refuse les DEUX écarts — un composant qui sort sans être nommé, et
    une entrée qui n'y tombe plus (sinon la table pourrit et couvrira
    un vrai trou).
    """
    declared = set(_REFUSES_A_TAG) | set(_NEEDS_MORE_THAN_BARE)
    measured = set(abstentions())
    assert measured == declared, (
        f"les abstentions ont bougé.\n"
        f"  non déclarées : {sorted(measured - declared)}\n"
        f"  déclarées mais absentes : {sorted(declared - measured)}\n"
        f"Nomme-les avec leur raison, ou retire l'entrée périmée."
    )


def test_a_changed_tag_drops_what_it_cannot_carry() -> None:
    """② L'interdiction."""
    offenders = stale_attrs()
    assert not offenders, (
        "un composant garde un attribut lié à son ancienne balise :\n  "
        + "\n  ".join(offenders)
        + f"\n\nSur un <{_PROBE_TAG}>, ces attributs ne désignent rien — "
        "ou pire, autre chose (`type` sur un `<a>` est un type MIME). "
        "Si l'attribut sort d'`emit_attrs`, le garde-fou central "
        "`Component._drop_attrs_the_tag_cannot_carry` s'en charge : "
        "vérifie que la table le connaît. S'il est posé APRÈS dans un "
        "`render()` maison, garde-le derrière un test sur `self._tag` "
        "(cf. `menu_item` et `image`)."
    )


def test_the_detector_still_bites() -> None:
    """③ La mutation, dans les DEUX sens.

    Le versant licite est celui qui a payé : la première écriture de ce
    détecteur cherchait le motif dans le tag ouvrant entier, et
    accusait ``ui.radio_group`` pour un ``input[type="radio"]`` écrit
    dans une expression JS. Un faux positif sur un composant réel, sur
    quatre trouvailles.
    """
    # Ce qui DOIT mordre.
    assert _root_of('<a type="button" href="/x">') == ("a", ["type", "href"])
    assert _root_of('<section alt="x">') == ("section", ["alt"])
    # Ce qui doit être ÉPARGNÉ — l'attribut est dans une VALEUR.
    tag, names = _root_of(
        '<div bz-on:set="$el.querySelector(\'[type=x]\')">'
    )
    assert names == ["bz-on:set"], f"lu dans une valeur : {names}"
    # Et les balises légitimes ne sont pas des contrevenants.
    for tag, name in (("button", "type"), ("a", "href"), ("img", "alt"),
                      ("label", "for"), ("iframe", "src")):
        assert tag in _BOUND[name], f"<{tag} {name}=> est licite"
