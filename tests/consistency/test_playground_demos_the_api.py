"""Le playground démontre la surface publique de chaque composant.

Le playground EST le banc d'essai : c'est là qu'on ouvre une page pour
juger si un composant marche. Un paramètre qui n'y est jamais passé n'est
donc jamais regardé — ni par un humain, ni par personne. C'est exactement
comme ça que `upload_url=` a pu pointer des mois vers une route
inexistante : la carte existait, le paramètre était écrit, mais rien ne
l'exerçait.

Cette gate dérive la surface **du code** — signature du constructeur,
`variants` et `sizes` du thème — et vérifie que la page du composant la
démontre. Aucun manifeste à tenir : un paramètre ajouté demain fait
échouer la gate tant qu'il n'est pas démontré.

**Ce qui compte comme démontré** : le paramètre apparaît en ``nom=`` dans
la page, OU c'est le premier paramètre positionnel et la page appelle le
composant avec un argument positionnel (``ui.button("Save")`` démontre
bien ``label``).

**Les sous-composants** (AccordionItem, SidebarItem, Tab…) n'ont pas de
page à eux : ils sont cherchés dans TOUT le playground, puisqu'ils
s'exercent depuis la page de leur parent.

``_BASELINE`` est la dette CONNUE, à faire fondre — pas une liste de cas
acceptés. L'assert est une égalité stricte : démontrer un paramètre sans
retirer son entrée fait échouer la gate, donc la liste ne peut pas
pourrir.
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path
from typing import NamedTuple

import pytest

from bretzel.components.base import SIZE_SCALE
from tests.consistency._discovery import parsed_sources, public_component_classes

#: Preuve de morsure : re-mesure chaque exemption : une entree dont le composant ou le
#: parametre n'existe plus doit SORTIR, sinon la baseline couvre un
#: fantome et laisse passer le vrai cas.
MUTATION_PROOF = "test_the_baseline_has_no_ghost"

_FEATURES = (
    Path(__file__).resolve().parents[2] / "examples" / "playground" / "features"
)

# Absorbés par ``**kwargs`` du socle ou fournis par le with-block : ils ne
# font pas partie de la surface qu'une page doit démontrer.
_NOT_API = {"self", "kwargs", "args", "children"}

#: Plancher du balayage du playground — **96 fichiers** mesurés le
#: 2026-08-30, contre 200 la veille : la famille ``/matrix`` (65
#: fichiers) et ``datatable_solo`` ont été supprimées. Le seuil garde la
#: même marge relative — il doit rougir si le chemin casse, pas si on
#: réorganise.
_FEATURES_FLOOR = 80


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _sources() -> tuple[dict[Path, str], dict[Path, ast.Module]]:
    """``({chemin: texte}, {chemin: arbre})`` — UNE lecture, deux vues.

    Le texte était lu ici en ``utf8`` nu, puis re-parsé plus bas dans un
    ``try/except SyntaxError: continue``. Deux défauts en un : un BOM
    rendait le parse impossible, et l'échec faisait sortir le fichier du
    balayage sans un mot. La primitive partagée lit en ``utf-8-sig`` et
    LÈVE — et rendre les deux vues d'un coup supprime la seconde lecture,
    qui était l'occasion de diverger sur l'encodage.
    """
    read = parsed_sources(_FEATURES, floor=_FEATURES_FLOOR)
    return ({s.path: s.text for s in read}, {s.path: s.tree for s in read})


_SRC, _TREES = _sources()
_ALL = "\n".join(_SRC.values())

#: Tous les ``nom=`` d'un fichier, lus en AST. C'est le repli quand un
#: appel splatte un dict et ne montre donc aucun nom au call-site.
#:
#: ⚠️ En AST et **jamais en texte**. La version textuelle a été prise
#: en défaut par mutation le 2026-09-07 : retirer
#: ``on_focus=log_focus`` de la page ``color_picker`` laissait la gate
#: VERTE, parce que la regex trouvait ``on_focus=`` dans une PHRASE
#: explicative — « un ``on_focus=`` partirait … ». Une gate qu'une
#: phrase satisfait ne garde rien, et c'est la règle 3.3 du gabarit
#: (« chaque event a un contrôle vivant ») qu'elle était censée tenir.
def _names_passed(tree: ast.Module) -> frozenset[str]:
    """Les noms de props qu'un fichier passe, sous les DEUX formes.

    1. ``ui.X(prop=…)`` — le kwarg explicite ;
    2. ``kwargs["prop"] = …`` puis ``ui.X(**kwargs)`` — la forme que le
       gabarit PRESCRIT pour le *Server playground* (``build_preview``
       traduit les props en dict, § 6). Sans elle le repli déclarerait
       non démontré tout ce que les pages à dict passent, soit huit
       props mesurées le 2026-09-07.

    Les deux se lisent en AST. Une clé de dict est une chaîne, mais une
    chaîne EN POSITION DE CLÉ — ce n'est pas la même chose que la
    chercher dans le texte du fichier, où une phrase la fournit.
    """
    noms: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            noms.update(k.arg for k in node.keywords if k.arg)
        elif isinstance(node, ast.Assign):
            for cible in node.targets:
                if (isinstance(cible, ast.Subscript)
                        and isinstance(cible.slice, ast.Constant)
                        and isinstance(cible.slice.value, str)):
                    noms.add(cible.slice.value)
        elif isinstance(node, ast.Dict):
            noms.update(
                k.value for k in node.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            )
    return frozenset(noms)


_FILE_KWARGS: dict[Path, frozenset[str]] = {
    path: _names_passed(tree) for path, tree in _TREES.items()
}


def _page_of(cls: type) -> str | None:
    """La page dédiée du composant, ou ``None`` s'il n'en a pas."""
    stem = _snake(cls.__name__)
    single = _FEATURES / f"{stem}.py"
    if single.exists():
        return _SRC[single]
    folder = _FEATURES / stem
    if folder.is_dir():
        return "\n".join(v for k, v in _SRC.items() if folder in k.parents)
    return None


class _Usage(NamedTuple):
    """Ce que le playground passe RÉELLEMENT à ``ui.<composant>(...)``."""

    kwargs: frozenset[str]      # les ``nom=`` explicites, tous call-sites confondus
    positional: bool            # au moins un appel avec un 1er argument positionnel
    opaque: frozenset[str]      # les ``nom=`` du FICHIER, quand un appel splatte


def _usages() -> dict[str, _Usage]:
    """Relève les appels ``ui.X(...)`` du playground, en AST.

    Le repli textuel d'origine cherchait un ``nom=`` dans TOUT l'arbre : un
    kwarg écrit pour un composant en créditait donc un autre. Mesuré le
    2026-08-09 — démontrer ``bottom_bar_item(badge=…)`` a fait passer au vert
    la dette de ``NavbarItem`` et ``SidebarItem``, dont aucun call-site ne
    passe ``badge=``. Restreindre au FICHIER ne suffisait pas : une même page
    monte souvent plusieurs composants de la même famille.

    ⚠️ D'où ``opaque`` : un appel qui splatte un dict (``ui.X(**kwargs)``,
    ce que fait chaque *Server playground* du gabarit) ne montre aucun nom en
    AST. Pour ces composants-là on RETOMBE sur le texte du fichier appelant —
    tolérant, mais sans franchir la frontière du fichier.
    """
    out: dict[str, dict] = {}
    for path, tree in _TREES.items():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if not (isinstance(fn, ast.Attribute)
                    and isinstance(fn.value, ast.Name) and fn.value.id == "ui"):
                continue
            entry = out.setdefault(
                fn.attr, {"kwargs": set(), "positional": False, "files": set()},
            )
            entry["kwargs"].update(k.arg for k in node.keywords if k.arg)
            entry["positional"] |= bool(node.args)
            if any(k.arg is None for k in node.keywords):
                entry["files"].add(path)
    return {
        name: _Usage(
            kwargs=frozenset(e["kwargs"]),
            positional=e["positional"],
            opaque=frozenset().union(
                *(_FILE_KWARGS[f] for f in e["files"])
            ) if e["files"] else frozenset(),
        )
        for name, e in out.items()
    }


_USAGE = _usages()


def _undemoed_params(cls: type) -> list[str]:
    usage = _USAGE.get(_snake(cls.__name__))
    if usage is None:                       # jamais monté → tout est manquant
        usage = _Usage(frozenset(), False, frozenset())
    try:
        params = list(inspect.signature(cls.__init__).parameters.items())
    except (TypeError, ValueError):  # pragma: no cover - socle sans __init__
        return []
    missing: list[str] = []
    index = 0
    for name, param in params:
        if name in _NOT_API:
            continue
        # Repli pour un appel qui splatte : les noms ne sont pas
        # lisibles au call-site, on retombe sur TOUS les ``nom=`` du
        # fichier — en AST, jamais en texte (cf. ``_FILE_KWARGS``).
        demoed = name in usage.kwargs or name in usage.opaque
        if not demoed:
            first_positional = (
                index == 0 and param.kind is param.POSITIONAL_OR_KEYWORD
            )
            if not (first_positional and usage.positional):
                missing.append(name)
        index += 1
    return missing


def _undemoed_theme_keys(cls: type, group: str) -> list[str]:
    src = _page_of(cls) or _ALL
    table = (getattr(cls, "THEME", {}) or {}).get(group) or {}
    keys = list(table) if group == "variants" else [
        k for k in table if k in (*SIZE_SCALE, "2xl")
    ]
    return [k for k in keys if f'"{k}"' not in src]


# ── La dette connue, à faire fondre ──────────────────────────────────
#
# 49 paramètres sur 559 (91,2 % démontrés), mesurés le 2026-08-09 —
# en comptant les kwargs RÉELLEMENT passés, cf. la note dans `_BASELINE`.
# Beaucoup sont des props de configuration silencieuses (``name=`` pour la
# soumission de formulaire) ou des variantes de format — pas des trous
# béants, mais chacun est un bout d'API que personne ne regarde jamais.
_BASELINE: dict[str, set[str]] = {
    # ⚠️ Cette liste a GRANDI le 2026-08-09, et c'est une bonne nouvelle : elle
    # ne contenait 9 entrées que parce que la mesure était fausse. Le repli des
    # composants sans page dédiée cherchait un ``nom=`` dans TOUT l'arbre du
    # playground, donc un kwarg écrit pour un composant en créditait un autre.
    # Elle compte maintenant les kwargs réellement passés à ``ui.X(...)``, en
    # AST, call-site par call-site. Rien n'a régressé : de la dette cachée est
    # devenue visible.
    #
    # Le déclencheur, pour mémoire : démontrer ``bottom_bar_item(badge=…)`` a
    # fait passer au vert les entrées de ``NavbarItem`` et ``SidebarItem``,
    # dont AUCUN des 20 call-sites ne passe ``badge=``.
    #
    # Ce que la mesure révèle, et qui est le vrai sujet : **la famille sidebar
    # n'a pas de page de banc**. Elle n'existe dans le playground que via le
    # shell, qui la monte avec trois kwargs. Ses quatre sous-composants pèsent
    # 20 des 49 paramètres non démontrés.
    "Calendar": {"name", "required"},
    "DropdownItem": {"icon_right", "shortcut"},
    "HStack": {"align", "gap"},
    # ``autocomplete`` est parti le 2026-09-07 : le repli le voit
    # enfin, il est passé par ``kwargs["autocomplete"]``. ``min`` /
    # ``max`` / ``step`` restent une abstention DÉCLARÉE par la page :
    # ils ne valent que pour ``type="number"``.
    "Input": {"max", "min", "step"},
    # Vidés le 2026-09-07 : le repli en AST voit enfin ce que les pages
    # passent par ``kwargs["…"]``, la forme que le gabarit prescrit.
    "LineChart": set(),
    "NavbarItem": {"active", "badge", "color", "disabled", "icon", "on_click"},
    "Outlet": {"id"},
    "Radio": {"color", "name", "on_change", "required", "size"},
    "ScatterChart": set(),
    # Abstention DÉCLARÉE par la page elle-même : « AUCUNE source.
    # Pas “un chemin absent” — pas de src du tout », parce qu'un
    # .mp4 dans le dépôt pèserait. La page démontre justement ce
    # que le composant fait SANS source. Le repli textuel la
    # créditait par la prose ; le repli AST ne le fait plus, donc
    # l'abstention doit être écrite.
    "Video": {"src"},
    # Dette SOLDÉE le 2026-08-15 par l'arrivée d'une page de banc pour la
    # famille sidebar (``examples/playground/features/sidebar.py``). Ces
    # quatre entrées existaient parce que la sidebar était la seule nav
    # sans page de playground — ce que ``todo.md`` notait par ailleurs.
    # Les quatre lignes sont retirées, pas vidées : une entrée vide
    # laisserait croire à une dette encore ouverte.
    "Slider": {"name"},
    "ToggleButton": {"label"},
    "VStack": {"align", "gap"},
}


@pytest.mark.parametrize(
    "cls", public_component_classes(), ids=lambda c: c.__name__
)
def test_playground_demos_every_constructor_param(cls: type) -> None:
    missing = set(_undemoed_params(cls))
    expected = _BASELINE.get(cls.__name__, set())
    assert missing == expected, (
        f"{cls.__name__} : paramètres jamais démontrés dans le playground = "
        f"{sorted(missing)}, dette attendue = {sorted(expected)}.\n"
        f"  - EN TROP : ce paramètre n'est passé nulle part, donc personne "
        f"ne l'a jamais vu marcher. Ajoute-le à sa page.\n"
        f"  - MANQUANT : tu viens de le démontrer — retire-le de "
        f"`_BASELINE` pour que la dette reste juste.\n"
        f"  Le playground est le banc d'essai : ce qui n'y est pas exercé "
        f"n'est validé par personne."
    )


@pytest.mark.parametrize(
    "cls", public_component_classes(), ids=lambda c: c.__name__
)
def test_playground_demos_every_variant(cls: type) -> None:
    missing = _undemoed_theme_keys(cls, "variants")
    assert not missing, (
        f"{cls.__name__} : variantes déclarées au thème mais jamais "
        f"démontrées = {missing}. Un variant qu'on ne voit pas est un "
        f"variant qu'on ne sait pas cassé."
    )


@pytest.mark.parametrize(
    "cls", public_component_classes(), ids=lambda c: c.__name__
)
def test_playground_demos_every_size(cls: type) -> None:
    missing = _undemoed_theme_keys(cls, "sizes")
    assert not missing, (
        f"{cls.__name__} : paliers de taille jamais démontrés = {missing}. "
        f"C'est là que se cachent les enfants figés (le glyphe qui ne suit "
        f"pas son conteneur) — invisibles à un seul palier."
    )


def test_the_baseline_has_no_ghost() -> None:
    """Une entrée de dette qui ne correspond à aucun composant vivant."""
    known = {c.__name__ for c in public_component_classes()}
    ghosts = sorted(set(_BASELINE) - known)
    assert not ghosts, (
        f"`_BASELINE` cite des composants qui n'existent plus : {ghosts}."
    )
