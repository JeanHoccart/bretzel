"""Gate : ``render()`` ne doit JAMAIS laisser d'enfant orphelin à la racine.

Le mécanisme (jumeau de ``test_slot_never_orphans``). Un Component
s'auto-enregistre chez le parent actif dès sa **construction** — c'est son
seul signal de « qui me possède ». ``test_slot_never_orphans`` couvre la
variante « l'utilisateur passe un Component en slot » (``ui.badge(label=
ui.text(...))``) et mesure l'orphelinage **à la construction**.

Cette gate couvre l'AUTRE variante, celle qui lui échappait :

    # dans Foo.render()
    children=(Icon("x", size="sm").render(),)   # ← Icon construit ICI

Construire un Component **pendant** ``render()`` l'auto-enregistre aussi au
parent actif. Tant que le composant rend en place, ça passe inaperçu ; mais
dès qu'il rend détaché (``serialize_html``, snapshot d'inspection, tout
sous-arbre extrait), l'enfant interne n'a plus de parent immédiat et
**retombe sur la racine du contexte** — il apparaît une 2ᵉ fois, orphelin.

La recette standard est ``Component._detach_from_parent(child)`` AVANT
``child.render()`` — ``badge`` / ``combobox`` / ``select`` la suivent. Le
bug a échappé au gate slot parce que celui-ci ne mesure QUE la construction
utilisateur : il ne rend jamais le composant dans un contexte où un enfant
construit par le framework fuirait.

Pourquoi cette gate (2026-07-18). ``Banner`` (le × de fermeture) et ``Tree``
(chevrons + icône de nœud) construisaient leur Icon en inline sans détacher.
Le × parasite était visible à l'œil dans le playground (bloc « Emitted HTML »
= un banner rendu détaché) mais aucun test ne l'attrapait : le gate slot ne
teste pas le render-time, et le SSR TestClient sérialise sans regarder la
racine du contexte. Cf. traps.md § « Icon construit dans render() sans
detach » + « Slot Component stocké sans adopt_slot ».
"""

from __future__ import annotations

import datetime as _dt
import inspect

import pytest

from bretzel.components.base.component import Component
from bretzel.components.base.testing import render_isolated
from tests.audit.test_binding_completeness import CONSTRUCT, _Skip
from tests.consistency._discovery import public_component_classes

#: Pas de détecteur à rendre aveugle — cf.
#: ``test_a_prohibition_gate_is_mutation_tested``.
MUTATION_NOT_APPLICABLE = (
    "rend chaque composant et compare l'arbre produit à ses enfants "
    "déclarés — une comparaison structurelle, sans motif textuel"
)

# ⚠️ La construction DOIT exercer le chemin qui construit les enfants
# internes (× de fermeture, chevrons, icônes de nœud) — sinon la gate est
# vacante (un ``Banner()`` sans ``dismissible`` ne construit aucun × : le
# bug passe). Cf. memory « visual harness solo-mount blindspot ». D'où :
# (1) des flags de feature activés depuis la SIGNATURE, (2) des builders
# riches pour les cas STRUCTURELS (icône par enfant).

# Args requis quand ``Cls()`` ne suffit pas — dérivés des signatures.
_MINIMAL = {
    "MetaTag": lambda C: C(content="x"),
    "Title": lambda C: C("x"),
}

# Flags qui, présents dans la signature, matérialisent un enfant construit
# DANS render() (le vrai chemin à risque). Signature-driven, pas une liste
# de composants : un nouveau ``ui.foo(dismissible=…)`` est couvert d'office.
_FEATURE_KWARGS = {
    "dismissible": True,
    "clearable": True,
    "loading": True,
    "icon": "x",
    "icon_left": "x",
    "icon_right": "x",
}


def _rich_tree(C):
    # Le leak du Tree vit dans les nœuds (chevrons + icône), pas dans la
    # racine vide → il faut des TreeNode porteurs d'icône.
    from bretzel.components.data.tree.tree import TreeNode

    with C() as t, TreeNode("a", label="root", icon="folder"):
        TreeNode("b", label="child", icon="file")
    return t


# Builders STRUCTURELS (icône construite par enfant / au render). Priment
# sur la construction signature-driven.
_RICH = {
    "Tree": _rich_tree,
    "Select": lambda C: C(options=[("a", "A")], clearable=True),
    "Combobox": lambda C: C(options=[("a", "A")], clearable=True),
}


def _feature_kwargs(cls: type) -> dict:
    try:
        params = inspect.signature(cls.__init__).parameters
    except (TypeError, ValueError):
        return {}
    return {k: v for k, v in _FEATURE_KWARGS.items() if k in params}


def _first_bindable(cls: type) -> str | None:
    props = getattr(cls, "BINDABLE_PROPS", None) or ()
    return props[0] if props else None


def _build(cls: type):
    """Un exemplaire renderable de *cls* qui exerce ses chemins d'icône,
    ou lève ``_Skip`` / ``TypeError``.

    Ordre : builder structurel riche → args requis → builder CONSTRUCT
    (échafaudages de contexte Navbar/Sidebar/ToggleGroup, qui rendent le
    ROOT → toute fuite interne y remonte) → ``Cls(**feature_kwargs)``.
    """
    name = cls.__name__
    if name in _RICH:
        return _RICH[name](cls)
    if name in _MINIMAL:
        return _MINIMAL[name](cls)
    builder = CONSTRUCT.get(name)
    if builder is not None:
        prop = _first_bindable(cls) or "value"
        value: object = _dt.date(2024, 1, 1) if "date" in name.lower() else "x"
        return builder(cls, prop, value)
    return cls(**_feature_kwargs(cls))


_CASES = public_component_classes()


@pytest.mark.parametrize("cls", _CASES, ids=[c.__name__ for c in _CASES])
def test_render_leaks_no_root_orphan(cls: type) -> None:
    with render_isolated() as ctx:
        try:
            comp = _build(cls)
        except _Skip as exc:
            pytest.skip(f"construction contextuelle non couverte : {exc}")
        except TypeError as exc:
            pytest.skip(f"construction fidèle non câblée : {exc}")

        # On rend le composant DÉTACHÉ (comme serialize_html / un snapshot
        # d'inspection). Tout enfant construit pendant render() sans detach
        # retombe alors sur ``root_children`` — c'est la fuite qu'on gate.
        Component._detach_from_parent(comp)
        before = len(ctx.root_children)
        try:
            comp.render()
        except Exception as exc:
            pytest.skip(f"render non exerçable en isolation : {exc}")
        leaked = ctx.root_children[before:]

    assert not leaked, (
        f"{cls.__name__}.render() a laissé {len(leaked)} enfant(s) orphelin(s) "
        f"à la racine : {[type(c).__name__ for c in leaked]}. Un Component "
        f"construit dans render() s'auto-enregistre au parent actif et fuit "
        f"quand le composant est détaché. Fix : "
        f"`Component._detach_from_parent(child)` AVANT `child.render()` "
        f"(cf. badge/combobox/select ; traps.md § « Icon construit dans "
        f"render() sans detach »)."
    )


def test_gate_is_not_vacuous() -> None:
    covered = 0
    for cls in _CASES:
        with render_isolated():
            try:
                _build(cls)
            except Exception:
                continue
            covered += 1
    assert covered >= 25, (
        f"seulement {covered} composants réellement construits — un refactor "
        f"a-t-il cassé la construction par défaut / les builders CONSTRUCT ?"
    )
