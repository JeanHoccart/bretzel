"""Un ``bz-data`` doit être un littéral d'objet JS BIEN FORMÉ.

Le scope client d'un composant est parsé par le runtime. S'il ne parse
pas, le composant ne perd pas *une* fonctionnalité : il perd **tout son
scope d'un coup**, en silence côté serveur, contre une seule
``SyntaxError`` dans la console du navigateur.

Ce qui a motivé la gate (2026-08-15)
-------------------------------------
``Sidebar`` épissait son marqueur ``_serverSync`` sans la virgule que le
contrat de :func:`~bretzel.components.base._wiring.server_sync_marker`
laisse à l'appelant (« leading space + trailing comma ») :

.. code-block:: text

    open: true _serverSync: ['open'],, rail_tip: ''
             ↑ virgule manquante        ↑ virgule doublée

Résultat : plus de ``current_path`` (aucune entrée ne se surlignait),
plus de ``open`` (le chevron de repli était mort) et plus de tooltip de
rail — sur toute sidebar dont ``open=`` pointait un champ serveur. Le
HTML restait valide, les tests SSR restaient verts, et aucune des neuf
applications d'``examples/`` ne passait cette forme. Six mois.

Pourquoi le cas ne sortait d'aucun balayage existant
-----------------------------------------------------
``_discovery.bz_data_of`` rend chaque composant avec ses DÉFAUTS, où
``open`` est un littéral : le marqueur n'est pas émis, la faute
n'apparaît pas. La branche fautive n'existe **que** quand une prop est
adossée au serveur. Cette gate rend donc chaque composant une seconde
fois, chaque ``BINDABLE_PROPS`` recevant une valeur ESTAMPILLÉE — c'est
la moitié du balayage qui manquait, pas une vérification plus fine.

Le détail qui décide de tout est dans :func:`_server_backed_value` :
hors requête, lire un champ de ``PageState`` renvoie le scalaire NU, donc
``_value_server_backed`` répond False et la branche reste inatteignable.
La première version de cette gate faisait exactement ça et ne voyait que
les 5 composants qui passent ``enabled=True`` en dur ; c'est le plancher
de non-vacuité qui l'a signalé, pas une relecture.

Ce que la gate NE fait pas
---------------------------
Elle ne parse pas du JavaScript (aucun moteur ici). Elle vérifie la
structure d'un littéral d'objet : délimiteurs équilibrés, aucun segment
vide au premier niveau (la virgule doublée), et au plus un ``:`` de
premier niveau par segment (la virgule manquante, qui colle deux paires
``clé: valeur`` dans le même segment). Les deux formes que la faute
Sidebar produisait sont exactement celles-là ; c'est le résidu d'un
littéral cassé autrement qui n'est pas couvert.
"""

from __future__ import annotations

import html as _html
import re

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from bretzel.state.scopes.server import _stamp
from tests.consistency._discovery import public_component_classes

_CLASSES = public_component_classes()

#: Plancher de non-vacuité — ancré sur la DÉCOUVERTE (combien de scopes
#: adossés au serveur ce balayage voit RÉELLEMENT émettre un marqueur),
#: pas sur la population de composants. Un plancher qui recompterait
#: ``len(_CLASSES)`` resterait vert avec le rendu server-backed débranché.
#: Mesuré le 2026-08-15 : 15 composants émettent un ``_serverSync`` sous
#: ce balayage (Accordion, Carousel, Dialog, Drawer, Dropdown, NumberInput,
#: Popover, Resizable, Sidebar, SignaturePad, Slider, Stepper, Tabs,
#: Tooltip, Tree). Le seuil laisse la marge d'un retrait légitime.
_SERVERSYNC_FLOOR = 10

_OPEN = {"{": "}", "[": "]", "(": ")"}
_CLOSE = {v: k for k, v in _OPEN.items()}


def _server_backed_value(default):
    """Une valeur ESTAMPILLÉE, du type qui colle au défaut de la prop.

    On appelle ``_stamp`` directement au lieu de lire un champ de
    ``PageState`` : hors requête — et ``render_isolated()`` n'en monte
    pas — une lecture de champ renvoie le scalaire NU, donc
    ``_value_server_backed`` répond False et la branche ``_serverSync``
    n'est jamais atteinte. Mesuré en écrivant cette gate : le plancher
    ci-dessous est ce qui l'a signalé, la première version du balayage ne
    voyait que les 5 composants qui passent ``enabled=True`` en dur.

    ``_stamp`` est exactement ce que la couche de rendu applique à chaque
    lecture de champ (``state/scopes/server.py``) — on court-circuite la
    requête, pas le mécanisme.
    """
    if isinstance(default, bool) or default is None:
        return _stamp(True, "flag")
    if isinstance(default, (int, float)):
        return _stamp(1, "number")
    return _stamp("a", "text")


#: Les couples ``Classe.prop`` que la sonde ne peut PAS construire, avec
#: leur raison. Mesuré le 2026-08-19 en remplaçant l'``except`` par un
#: enregistrement : cinq, et pas un de plus. La table est stricte —
#: un couple qui redevient constructible doit en sortir.
#:
#: ⚠️ Avant ce jour, l'``except`` en avalait **32**. La cause n'était pas
#: le composant, c'était l'appel : le bâtisseur partagé prend
#: ``(classe, NOM DE PROP, valeur)`` et on lui passait ``("slots",
#: kwargs)`` — donc ``Calendar(slots={"value": …})``, refusé par le
#: socle. Les 25 composants qui ont un bâtisseur sortaient du balayage
#: en silence, et la gate paraissait juger 97 composants quand elle
#: n'en jugeait que ceux SANS bâtisseur. Corrigé : 88 couples jugés au
#: lieu de 65.
_CANNOT_PROBE: dict[str, str] = {
    "Link.label": "binding de slot A.2 — limite de framework connue",
    "Link.href": "idem",
    # Même raison que les trois pickers de date : la sonde estampille le
    # DÉFAUT de la prop, qui vaut ``None`` ici — donc un booléen — et la
    # coercition refuse un booléen. Ce n'est pas un défaut du composant :
    # une couleur est une chaîne, et refuser autre chose est ce qu'on
    # veut. ``disabled`` sort pour la raison inverse — c'est un ``bool``,
    # et le socle refuse d'estampiller un booléen comme valeur serveur.
    "ColorPicker.value": "refuse un booléen estampillé (attend str)",
    "MonthPicker.value": "refuse un booléen estampillé (attend str / date)",
    "TimePicker.value": "refuse un booléen estampillé (attend time / str)",
    "WeekPicker.value": "refuse un booléen estampillé (attend date / str)",
}


def _probe(cls: type, prop: str) -> str | None:
    """Le HTML du composant, prop bindable adossée au SERVEUR.

    ``None`` = la sonde n'est pas constructible pour ce couple. C'est
    une abstention, et ``test_the_abstentions_are_declared`` exige
    qu'elle soit dans ``_CANNOT_PROBE`` — sans quoi un composant peut
    sortir du balayage sans que personne ne le sache.
    """
    from tests.audit.test_binding_completeness import CONSTRUCT

    descriptor = getattr(cls, prop, None)
    value = _server_backed_value(getattr(descriptor, "default", None))
    builder = CONSTRUCT.get(cls.__name__)
    try:
        with render_isolated():
            node = (
                builder(cls, prop, value) if builder else cls(**{prop: value})
            ).render()
            return serialize(node)
    except Exception:
        return None


def abstentions() -> dict[str, str]:
    """``Classe.prop -> type d'erreur`` pour ce que la sonde ne bâtit pas."""
    from tests.audit.test_binding_completeness import CONSTRUCT

    out: dict[str, str] = {}
    for cls in _CLASSES:
        for prop in getattr(cls, "BINDABLE_PROPS", ()) or ():
            descriptor = getattr(cls, prop, None)
            value = _server_backed_value(getattr(descriptor, "default", None))
            builder = CONSTRUCT.get(cls.__name__)
            try:
                with render_isolated():
                    (
                        builder(cls, prop, value)
                        if builder
                        else cls(**{prop: value})
                    ).render()
            except Exception as exc:
                out[f"{cls.__name__}.{prop}"] = type(exc).__name__
    return out


def _scopes_of(cls: type) -> list[str]:
    """Tous les ``bz-data`` du sous-arbre rendu, prop bindable adossée au
    serveur. Liste vide si le composant n'a pas de prop bindable, ou si
    aucune de ses sondes ne se construit — les abstentions sont
    déclarées, pas subies (cf. ``_CANNOT_PROBE``)."""
    out: list[str] = []
    for prop in getattr(cls, "BINDABLE_PROPS", ()) or ():
        html = _probe(cls, prop)
        if html is None:
            continue
        out.extend(
            _html.unescape(m.group(1))
            for m in re.finditer(r'\sbz-data="([^"]*)"', html)
        )
    return out


def _top_level_segments(literal: str) -> list[str] | None:
    """Découpe un littéral ``{ … }`` sur ses virgules de PREMIER niveau.

    ``None`` si les délimiteurs ne s'équilibrent pas ou si l'entrée n'est
    pas un objet — deux cas qui sont eux-mêmes des défauts, remontés par
    l'appelant."""
    body = literal.strip()
    if not (body.startswith("{") and body.endswith("}")):
        return None
    body = body[1:-1]
    stack: list[str] = []
    quote: str | None = None
    segments: list[str] = []
    current: list[str] = []
    i = 0
    while i < len(body):
        ch = body[i]
        if quote is not None:
            if ch == "\\":
                current.append(ch)
                i += 1
                if i < len(body):
                    current.append(body[i])
                i += 1
                continue
            if ch == quote:
                quote = None
        elif ch in ("'", '"', "`"):
            quote = ch
        elif ch in _OPEN:
            stack.append(ch)
        elif ch in _CLOSE:
            if not stack or stack[-1] != _CLOSE[ch]:
                return None
            stack.pop()
        elif ch == "," and not stack:
            segments.append("".join(current))
            current = []
            i += 1
            continue
        current.append(ch)
        i += 1
    if stack or quote is not None:
        return None
    segments.append("".join(current))
    return segments


def _top_level_colons(segment: str) -> int:
    """Compte les ``:`` hors chaîne et hors délimiteur imbriqué. Un
    ternaire (``a ? b : c``) en produirait un faux — d'où le garde sur
    ``?`` chez l'appelant."""
    stack, quote, count, i = 0, None, 0, 0
    while i < len(segment):
        ch = segment[i]
        if quote is not None:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in ("'", '"', "`"):
            quote = ch
        elif ch in _OPEN:
            stack += 1
        elif ch in _CLOSE:
            stack -= 1
        elif ch == ":" and stack == 0:
            count += 1
        i += 1
    return count


def _faults(literal: str) -> list[str]:
    # Tous les scopes ne sont pas des littéraux : ``FileUpload`` émet un
    # APPEL (``$bz.fileUpload.makeScope({...})``), forme légitime que le
    # runtime évalue telle quelle. On ne peut pas y découper des segments,
    # mais l'équilibre des délimiteurs reste vérifiable — et c'est ce que
    # ``_top_level_segments`` renvoie ``None`` pour signaler, sans pouvoir
    # distinguer « déséquilibré » de « pas un objet ». D'où le test
    # d'équilibre séparé.
    if not literal.strip().startswith("{"):
        return (
            []
            if _top_level_segments("{" + literal + "}") is not None
            else ["délimiteurs déséquilibrés"]
        )
    segments = _top_level_segments(literal)
    if segments is None:
        return ["délimiteurs déséquilibrés"]
    problems: list[str] = []
    for pos, seg in enumerate(segments):
        if not seg.strip():
            # Une virgule FINALE (``{a: 1,}``) est du JS valide, et
            # plusieurs composants la produisent en concaténant leurs
            # fragments — ce n'est pas une faute. Une virgule INTERNE
            # doublée (``],, rail_tip``) en est une : c'est la moitié
            # visible de la faute Sidebar.
            if pos < len(segments) - 1:
                problems.append("segment VIDE — virgule doublée")
            continue
        # Un ternaire porte un ``:`` qui n'est pas un séparateur de paire.
        if "?" in seg:
            continue
        if _top_level_colons(seg) > 1:
            problems.append(
                f"deux paires clé:valeur dans un seul segment — virgule "
                f"manquante : {seg.strip()[:90]!r}"
            )
    return problems


_SCOPES = {cls.__name__: _scopes_of(cls) for cls in _CLASSES}


def test_server_backed_sweep_is_not_vacuous() -> None:
    """Le balayage doit RÉELLEMENT atteindre la branche ``_serverSync``.

    Sans ce plancher, un ``except Exception: continue`` qui avalerait
    toutes les constructions rendrait la gate verte et muette — le mode
    d'échec que ``project_gate_floors_must_read_the_gate_source`` décrit.
    """
    carriers = [
        name
        for name, scopes in _SCOPES.items()
        if any("_serverSync" in s for s in scopes)
    ]
    assert len(carriers) >= _SERVERSYNC_FLOOR, (
        f"Seuls {len(carriers)} composants émettent un ``_serverSync`` sous "
        f"ce balayage (plancher {_SERVERSYNC_FLOOR}) : {sorted(carriers)}. "
        "Soit la construction server-backed a cessé de marcher, soit le "
        "marqueur a changé de nom — dans les deux cas la gate ne teste "
        "plus rien."
    )


def test_the_abstentions_are_declared() -> None:
    """Ce que la sonde ne bâtit pas est NOMMÉ, pas compté.

    Un plafond chiffré dirait « pas plus de cinq » ; une table dit
    LESQUELS. La différence compte le jour où un couple sort du balayage
    pendant qu'un autre y rentre : le compte ne bouge pas, la table si.
    """
    measured = abstentions()
    surprise = sorted(set(measured) - set(_CANNOT_PROBE))
    assert not surprise, (
        f"Ces couples ne se construisent plus sous la sonde server-backed, "
        f"et personne ne l'avait déclaré : "
        f"{ {k: measured[k] for k in surprise} }.\n"
        f"  Ils sortent donc du balayage EN SILENCE : la gate affirme "
        f"« aucun littéral mal formé » sans les avoir regardés.\n"
        f"  Répare la construction, ou ajoute l'entrée à `_CANNOT_PROBE` "
        f"AVEC sa raison."
    )
    stale = sorted(set(_CANNOT_PROBE) - set(measured))
    assert not stale, (
        f"{stale} se construi(sen)t de nouveau — retire l'entrée de "
        f"`_CANNOT_PROBE`. Une table qui garde des noms périmés autorise "
        f"plus que la réalité."
    )


@pytest.mark.parametrize("name", sorted(_SCOPES))
def test_bz_data_literal_is_well_formed(name: str) -> None:
    for literal in _SCOPES[name]:
        problems = _faults(literal)
        assert not problems, (
            f"{name} émet un ``bz-data`` malformé — le runtime perdra TOUT "
            f"le scope, pas seulement la prop fautive.\n"
            f"  littéral : {literal}\n"
            f"  fautes   : {problems}"
        )


def test_the_detector_still_bites() -> None:
    """Mutation : un littéral de scope mal formé est encore reconnu.

    Un ``bz-data`` déséquilibré ou à deux-points multiples ne lève pas :
    il s'évalue mal, en silence, dans le navigateur. Si ``_faults``
    cessait de voir la faute, la gate passerait sur les 36 scopes réels.
    """
    assert _faults("{open: false, val: 1: 2}"), (
        "deux paires dans un segment — la virgule manquante devrait mordre"
    )
    assert _faults("{open: false"), "un délimiteur déséquilibré devrait mordre"
    assert not _faults("{open: false, val: ''}"), "un littéral sain : faux positif"
    assert not _faults("$bz.fileUpload.makeScope({files: []})"), (
        "la forme APPEL est légitime — faux positif"
    )
