"""Une config server-owned posée en scope client doit être RE-SEMABLE.

``absorb`` ne réécrit jamais un signal existant (``03_scope.js`` : « NEVER
reset existing values »), et c'est volontaire — sans cette règle, le morph
d'un ``@refreshable`` voisin écraserait la saisie en cours, refermerait un
dropdown, effacerait la page qu'on vient de cliquer. La seule exception est
``_serverSync``, relu par ``resyncScopes`` après chaque swap.

Conséquence : **toute valeur que le serveur fournit et que le client ne
réécrit jamais doit y figurer**, sinon elle reste figée à sa valeur du
PREMIER montage, à vie.

Ce que ça a coûté
------------------
**Huit** composants livrés avec leur configuration gelée, découverts un
par un en 48 h parce que le symptôme est muet — le serveur renvoie la
bonne valeur, le DOM porte le bon attribut, et l'écran ne bouge pas :

===============  ======================================
composant        champs gelés
===============  ======================================
Pagination       ``_total`` ``_maxVisible``
Slider           ``_min`` ``_max`` ``_step`` ``_range``
NumberInput      ``_step``
Accordion        ``_allIds`` ``_collapsible``
Stepper          ``_max``
Tooltip          ``_delay``
Select           ``_options``
Combobox         ``_options`` ``_labels``
===============  ======================================

Les deux derniers sont les plus graves, et c'est la gate qui les a
trouvés : un select dont les options sont rechargées depuis la base à
chaque refresh gardait l'ancienne liste, à vie.

La cause racine n'est PAS un oubli : ``server_sync_marker`` existe et est
appelé à **19 endroits**, mais sa docstring ne parlait que de la valeur
(« the value(s) are server-backed »). Chaque auteur a donc câblé la clé de
valeur et personne n'a eu à se poser la question de la config. Fonction
partagée, appliquée à la main, à moitié.

Pourquoi la gate voisine ne pouvait pas l'attraper
---------------------------------------------------
``test_binding_path_is_re_evaluated`` injecte un ``ClientBinding``
sentinelle et cherche son chemin. ``_total: 16`` est un entier nu : aucun
chemin, aucune détection. Elle garde les BINDINGS gelés ; celle-ci garde
les LITTÉRAUX gelés. Il fallait les deux.

Comment elle décide
--------------------
Sans registre : on rend le composant **deux fois avec des props
différentes** et on regarde quels champs de ``bz-data`` bougent. Un champ
qui varie avec les props est, par construction, fourni par le serveur.
"""

from __future__ import annotations

import html as _html
import inspect
import re

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from tests.consistency._discovery import (
    assert_sweep_is_not_vacuous,
    public_component_classes,
)

_BZ_DATA = re.compile(r'bz-data="([^"]*)"')
_KEY = re.compile(r"(?:^|[,{])\s*(_\w+)\s*:\s*")
_METHOD = re.compile(r"\w+\s*\([^)]*\)\s*\{[^{}]*\}")
_SYNC = re.compile(r"_serverSync:\s*\[([^\]]*)\]")


def _read_value(src: str, start: int) -> str:
    """La valeur d'un champ, du ``:`` jusqu'à la virgule de MÊME niveau.

    Un simple ``[^,}]+`` ne suffit pas et l'erreur est silencieuse : une
    valeur de liste (``_options: ["a", "b"]``) contient des virgules, donc
    elle se faisait tronquer à ``["a"`` — identique entre deux rendus de
    tailles différentes. La gate voyait « ça ne bouge pas » et laissait
    passer TOUTE config en liste (``_options``, ``_labels``, ``_allIds``),
    c'est-à-dire précisément les champs qu'elle était censée couvrir en
    plus. Mesuré avant correction : Select 2 options vs 4 → aucun champ
    détecté comme variable.
    """
    depth, i, n = 0, start, len(src)
    quote = ""
    while i < n:
        ch = src[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch in "[{(":
            depth += 1
        elif ch in "]})":
            if depth == 0:
                break
            depth -= 1
        elif ch == "," and depth == 0:
            break
        i += 1
    return src[start:i].strip()

# Tampons CLIENT : ils varient à l'initialisation (ils sont semés depuis la
# valeur) mais le client en est propriétaire ensuite. Les re-semer à chaque
# swap écraserait une frappe, un drag ou une navigation clavier en cours —
# c'est le sinistre que la règle « NEVER reset » existe pour éviter.
#
# Cette liste est une DÉCISION par champ, pas une déduction du préfixe : le
# ``_`` ne distingue pas config et tampon, les deux le portent.
#
# ⚠️ Mesuré le 2026-08-03 : **aucune de ces entrées n'est exercée
# aujourd'hui**. Retirer n'importe laquelle laisse la gate verte, parce que
# la perturbation ne touche pas ``value`` (son défaut est ``None`` sur les
# composants concernés) et que ces tampons n'en dérivent qu'à
# l'initialisation. Elles sont donc PROSPECTIVES : le jour où la
# perturbation s'élargira à ``value``, ``_draft`` passera de ``"0"`` à
# ``"3"`` et la gate crierait à tort sans elles.
#
# C'est dit parce qu'une allowlist qui n'exempte rien est un passif : elle
# donne l'illusion d'un filet et pourrait masquer un vrai gel plus tard.
# Avant d'y ajouter une entrée, vérifie qu'elle ROUGIT sans — sinon tu
# documentes du décor.
_CLIENT_OWNED = {
    "_draft": "le texte en cours de frappe dans NumberInput",
    "_focused": "le focus est un fait du navigateur, pas du serveur",
    "_precCache": "cache de précision, dérivé, jamais autoritaire",
    "_highlight": "l'item survolé au clavier dans Select / Combobox",
    "_dragging": "un drag en cours sur Slider",
    "_hovered": "le pouce survolé sur Slider",
    "_track": "référence DOM mesurée côté client",
    "_carrier": "référence DOM, résolue au montage",
    "_el": "référence DOM de la dropzone FileUpload",
    "_closeOnPick": "TODO vérifier : config ou préférence client ?",
}


def _perturbed_kwargs(cls: type) -> tuple[dict, dict]:
    """Deux jeux de props qui DIFFÈRENT, dérivés des defaults.

    Type-dirigé plutôt que registre : un composant neuf est couvert sans
    qu'on touche à ce fichier.

    Deux familles perturbées :

    - les **scalaires**, depuis le default de chaque ``reactive_prop`` ;
    - ``options=``, détecté sur la signature du constructeur, parce que
      c'est lui qui alimente ``_options`` / ``_labels`` (Select, Combobox,
      ToggleGroup, Radio) — la config la plus volumineuse du dépôt, et
      celle qui bouge le plus souvent en vrai (une liste rechargée depuis
      la base à chaque refresh).

    Reste hors d'atteinte : la config dérivée des ENFANTS (``_allIds`` de
    l'Accordéon, ``_max`` du Stepper) — il faudrait instancier des enfants
    d'un type que seul le composant connaît. Les deux ont été vérifiés et
    corrigés à la main le 2026-08-03 ; un futur champ de cette forme devra
    l'être aussi.
    """
    a, b = {}, {}
    try:
        params = inspect.signature(cls.__init__).parameters
    except (TypeError, ValueError):
        params = {}
    if "options" in params:
        a["options"] = [("a", "A"), ("b", "B")]
        b["options"] = [("a", "A"), ("b", "B"), ("c", "C"), ("d", "D")]
    # Une prop SCELLÉE n'est pas de la surface : la classe la refuse à
    # l'appel, et ``bretzel.introspect`` la retire déjà de sa fiche. La
    # perturber faisait lever la sonde, qui se déclarait alors « abstention »
    # — un composant entier sorti du balayage pour une prop qu'il n'expose
    # pas. Découvert le 2026-08-23 en livrant ``ui.pane`` (``wrap`` scellé,
    # défaut booléen donc perturbé) ; ``ui.vstack`` y échappait par accident,
    # son ``direction`` scellé étant une chaîne, que la sonde ne perturbe pas.
    sealed = set(getattr(cls, "SEALED_PROPS", ()))
    for name, rp in (getattr(cls, "__reactive_props__", {}) or {}).items():
        if name in sealed:
            continue
        default = getattr(rp, "default", None)
        if isinstance(default, bool):
            a[name], b[name] = False, True
        elif isinstance(default, int):
            a[name], b[name] = default, default + 3
        elif isinstance(default, float):
            a[name], b[name] = default, default + 3.0
    return a, b


def _scopes(html: str) -> list[tuple[dict[str, str], set[str]]]:
    """Par ``bz-data`` : ses champs ``_*`` et ses clés re-semées."""
    out = []
    for raw in _BZ_DATA.findall(html):
        literal = _html.unescape(raw)
        sync = _SYNC.search(literal)
        synced = {
            k.strip().strip("'\"")
            for k in (sync.group(1).split(",") if sync else [])
            if k.strip()
        }
        bodies_stripped = _METHOD.sub("", literal)
        fields = {
            m.group(1): _read_value(bodies_stripped, m.end())
            for m in _KEY.finditer(bodies_stripped)
            if m.group(1) != "_serverSync"
        }
        out.append((fields, synced))
    return out


def _frozen_config(cls: type) -> list[str]:
    """Les champs ``_*`` qui varient avec les props sans être re-semés."""
    ka, kb = _perturbed_kwargs(cls)
    if not ka:
        return []
    try:
        with render_isolated():
            ha = serialize(cls(**ka).render())
        with render_isolated():
            hb = serialize(cls(**kb).render())
    except Exception:
        return []

    sa, sb = _scopes(ha), _scopes(hb)
    if len(sa) != len(sb):
        return []

    frozen: list[str] = []
    for (fa, synced), (fb, _) in zip(sa, sb):
        for key, va in fa.items():
            if key in _CLIENT_OWNED or key not in fb:
                continue
            if va != fb[key] and key not in synced:
                frozen.append(f"{key} ({va} → {fb[key]})")
    return frozen


@pytest.mark.parametrize("cls", public_component_classes(),
                         ids=lambda c: c.__name__)
def test_server_config_in_scope_is_resynced(cls: type) -> None:
    frozen = _frozen_config(cls)
    assert not frozen, (
        f"{cls.__name__} : {frozen} varie(nt) avec les props mais "
        f"n'est/ne sont pas dans `_serverSync` — donc figé(s) à la valeur "
        f"du PREMIER montage, à vie.\n\n"
        f"`absorb` ne réécrit jamais un signal existant (03_scope.js). Le "
        f"serveur aura beau renvoyer la bonne valeur et le morph poser le "
        f"bon attribut, le scope gardera l'ancienne : l'écran ne bougera "
        f"pas tant qu'on ne recharge pas la page.\n\n"
        f"Fix : ajouter la clé au `server_sync_marker(...)` du builder, SANS "
        f"la gater sur `_value_server_backed()` — le serveur est toujours "
        f"propriétaire de la configuration. La VALEUR, elle, reste gatée.\n\n"
        f"Si le champ est en réalité un tampon CLIENT (une frappe, un drag, "
        f"un focus), inscris-le dans `_CLIENT_OWNED` avec sa raison — c'est "
        f"une décision par champ, le préfixe `_` ne la donne pas."
    )


def test_the_sweep_actually_perturbs_something() -> None:
    """Plancher de non-vacuité (règle 8 du CLAUDE.md).

    « Aucune config gelée » passe exactement aussi bien quand rien n'a été
    perturbé — plus de props scalaires, rendu vide, ``bz-data`` renommé. On
    exige donc de VOIR des champs ``_*`` bouger, et de les voir sur les
    composants dont le gel a motivé la gate.
    """
    assert_sweep_is_not_vacuous()

    moved: dict[str, set[str]] = {}
    for cls in public_component_classes():
        ka, kb = _perturbed_kwargs(cls)
        if not ka:
            continue
        try:
            with render_isolated():
                ha = serialize(cls(**ka).render())
            with render_isolated():
                hb = serialize(cls(**kb).render())
        except Exception:
            # Abstention : le composant refuse d'être monté seul avec ces
            # kwargs. Elle est DÉCLARÉE dans ``_CANNOT_PERTURB`` — sinon
            # un composant sortirait d'ici sans que rien ne le dise.
            continue
        sa, sb = _scopes(ha), _scopes(hb)
        if len(sa) != len(sb):
            continue
        for (fa, _s), (fb, _) in zip(sa, sb):
            for key, va in fa.items():
                if key in fb and va != fb[key]:
                    moved.setdefault(cls.__name__, set()).add(key)

    assert len(moved) >= _MOVED_FLOOR, (
        f"seulement {len(moved)} composants voient un champ `_*` bouger "
        f"(plancher {_MOVED_FLOOR}) — la perturbation ne mord plus, "
        f"vérifie `_perturbed_kwargs` avant de croire la gate."
    )
    # Les composants dont le gel a motivé la gate DOIVENT rester perturbés :
    # s'ils sortent de la population, c'est le détecteur qu'il faut réparer.
    expected = {"Pagination", "Slider", "NumberInput", "Tooltip"}
    assert expected <= set(moved), (
        f"les composants témoins ne sont plus perturbés : manque "
        f"{sorted(expected - set(moved))}. Vu : {sorted(moved)}."
    )


# Mesuré le 2026-08-03. Angle mort assumé : les props STRUCTURELLES
# (``options=``, enfants) ne sont pas perturbées, donc ``_options`` /
# ``_labels`` / ``_allIds`` échappent au balayage automatique — ils ont été
# vérifiés à la main et corrigés, mais un nouveau champ de ce type devra
# l'être aussi. Perturber une structure génériquement demanderait le
# registre que cette gate évite justement.
_MOVED_FLOOR = 4


#: Les composants perturbables que la sonde ne monte pas, avec leur
#: raison. Mesuré le 2026-08-19 en remplaçant l'``except`` par un
#: enregistrement : un seul sur 64 candidats.
_CANNOT_PERTURB: dict[str, str] = {
    "ToggleButton": "ne se rend que dans le ``with`` d'un ToggleGroup",
}


def perturbation_abstentions() -> dict[str, str]:
    """``Classe -> type d'erreur`` pour ce que la perturbation ne monte pas."""
    out: dict[str, str] = {}
    for cls in public_component_classes():
        ka, kb = _perturbed_kwargs(cls)
        if not ka:
            continue
        try:
            with render_isolated():
                serialize(cls(**ka).render())
            with render_isolated():
                serialize(cls(**kb).render())
        except Exception as exc:
            out[cls.__name__] = type(exc).__name__
    return out


def test_the_abstentions_are_declared() -> None:
    """Ce que la perturbation ne monte pas est NOMMÉ, pas compté.

    Le plancher au-dessus compte les composants dont un champ BOUGE ; il
    ne dit rien de ceux qui ne se montent pas du tout. Un composant qui
    cesse de se construire ferait donc baisser le compte sans jamais
    être nommé — et le plancher a de la marge, donc rien ne rougirait.
    """
    measured = perturbation_abstentions()
    surprise = sorted(set(measured) - set(_CANNOT_PERTURB))
    assert not surprise, (
        f"{ {k: measured[k] for k in surprise} } ne se monte(nt) plus sous "
        f"la perturbation : ils sortent du balayage EN SILENCE, et la gate "
        f"affirme « la config serveur se resynchronise » sans les avoir vus."
    )
    stale = sorted(set(_CANNOT_PERTURB) - set(measured))
    assert not stale, (
        f"{stale} se monte(nt) de nouveau — retire l'entrée."
    )


def test_the_detector_still_bites() -> None:
    """Mutation : les champs de scope et le marqueur sont encore lus.

    La gate perturbe deux configs et compare les champs ``_*`` qui
    bougent. Si l'une des deux regex cessait de matcher, elle comparerait
    des ensembles vides — et un champ figé passerait pour resynchronisé.
    """
    assert _KEY.search("{_debounce: 300, _throttle: 0}").group(1) == "_debounce"
    assert not _KEY.search("{open: false}"), "faux positif"
    assert _SYNC.search("_serverSync: ['val','open']").group(1) == "'val','open'"
    assert not _SYNC.search("serverSync: []"), "faux positif"
