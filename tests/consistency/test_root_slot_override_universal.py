"""``slots={"root": …}`` atteint le vrai root de TOUS les composants.

Le contrat (funnel `theme.md` § composition, étape 5) : ``slots=`` est un
kwarg réservé qui remplace/complète un slot du thème. Le socle en est
propriétaire pour ``"root"`` — un composant ne s'en occupe jamais.

Ce que la gate exige, pour chaque composant public :

1. l'override **atteint le DOM** — le marqueur est présent ;
2. **exactement une fois** — pas de doublon entre le socle et un composant
   qui l'appliquerait aussi de son côté ;
3. la composition statique du thème **survit** — un override ne déshabille
   pas le composant, il s'ajoute par-dessus.

Plus : une clé de slot que le composant ne déclare pas **lève**, au lieu
d'être avalée.

Pourquoi (audit du socle 2026-07-29, § « la seule vraie faille de socle »)
--------------------------------------------------------------------------
``slots=`` était absorbé comme kwarg universel (``component.py`` §
universels) mais relu par un **seul** chemin : ``compose_class`` étape 6.
Donc tout composant dont le root est composé par un autre slot — ou qui lit
``theme["slots"]["root"]`` à la main, ce que fait ToggleGroup — perdait
l'override **sans un mot**. Mesuré avant le fix : honoré par Button /
Alert / Select / Tabs / Combobox, **perdu** par Card, Text, Badge, Input,
Heading, Divider, Sidebar, Navbar.

C'est exactement l'histoire de ``classes=`` (gate
``test_reactive_classes_universal``) et de ``style=`` : trois kwargs
universels dont un seul lecteur, réparés au même endroit — le wrap
métaclasse ``_apply_universal_modifiers``, qui possède le **vrai** root
quel que soit le slot qui l'a composé. ``slots={"root"}`` était le dernier
des trois à ne pas avoir été migré.

Les slots NON-root restent dans ``compose_class`` : seul le composant sait
quel élément porte son slot ``"panel"`` ou ``"label"``.
"""

from __future__ import annotations

import re

import pytest

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from tests.audit.test_binding_completeness import CONSTRUCT, _Skip
from tests.consistency._discovery import public_component_classes

_MARKER = "zz-root-override"

# Plancher de non-vacuité. Sous ce seuil, la gate ne vérifie plus rien de
# significatif — un refactor qui casserait la construction ferait tout
# passer en SKIP et la gate resterait verte sur zéro composant. Mesuré à
# l'écriture ; à relever si la couverture s'améliore, jamais à baisser
# sans dire pourquoi.
_FLOOR = 60

# ── Dette : VIDE ──────────────────────────────────────────────────────
# Elle a porté ``{"ToggleButton"}`` le temps du chantier du socle :
# ToggleGroup rebâtissait ses boutons via ``child._render_button(...)``
# au lieu d'appeler leur ``render()``, court-circuitant le wrap métaclasse
# — donc AUCUN kwarg universel de l'enfant n'arrivait, ni ``slots=``, ni
# ``classes=``, ni ``style=``.
#
# Réparé à la racine : les trois passes du wrap vivent maintenant dans
# ``finish_render``, et tout chemin qui rebâtit un enfant y finit. C'est
# ``test_known_debt_is_still_debt`` ci-dessous qui a signalé que l'entrée
# était devenue obsolète — la gate auto-vérifiée a fait exactement son
# travail, à la minute où le fix a atterri.
#
# ⚠️ Ce que ce bug a appris sur les gates : la gate sœur
# ``test_reactive_classes_universal`` ne l'a JAMAIS vu, parce que son
# helper construit ToggleButton **seul**, hors de son parent. Un composant
# dont le bug n'existe qu'en composition est invisible à un harnais qui le
# monte isolément.
_KNOWN_DEBT: set[str] = set()


def _build(cls: type, slots: dict[str, str]):
    """Construit ``cls`` avec ``slots=``, via le registre de construction
    fidèle de l'audit (parents requis, options, valeurs SSR réalistes).

    Les builders ont la signature ``(Cls, prop, value)`` et posent la prop
    eux-mêmes — on leur passe donc ``"slots"`` comme prop, ce qui donne à
    Select ses ``options=`` et à Pagination ses ``total_pages=`` sans les
    dupliquer ici."""
    builder = CONSTRUCT.get(cls.__name__)
    if builder is not None:
        return builder(cls, "slots", slots)
    return cls(slots=slots)


def _render(cls: type, slots: dict[str, str] | None = None) -> str:
    with render_isolated():
        return serialize(_build(cls, slots or {}).render())


def _renderable() -> list[type]:
    """Les composants que la gate exerce réellement (les autres skippent)."""
    out = []
    for cls in public_component_classes():
        try:
            _render(cls, {"root": _MARKER})
        except Exception:
            continue
        out.append(cls)
    return out


@pytest.mark.parametrize("cls", public_component_classes(),
                         ids=lambda c: c.__name__)
def test_root_slot_override_reaches_the_dom(cls: type) -> None:
    try:
        html = _render(cls, {"root": _MARKER})
        static_html = _render(cls)
    except _Skip as exc:
        pytest.skip(str(exc))
    except Exception as exc:
        pytest.skip(f"{cls.__name__} non constructible sans contexte : "
                    f"{type(exc).__name__}: {exc}")

    count = html.count(_MARKER)

    if cls.__name__ in _KNOWN_DEBT:
        pytest.skip(
            f"{cls.__name__} : dette connue — son parent le rebâtit au lieu "
            f"de l'appeler, donc aucun kwarg universel n'arrive (cf. "
            f"_KNOWN_DEBT et test_known_debt_is_still_debt)"
        )

    assert count >= 1, (
        f"{cls.__name__} : `slots={{'root': …}}` n'atteint pas le DOM. "
        f"Le kwarg est réservé et documenté public (theme.md, étape 5 de la "
        f"composition) — le socle (`_apply_universal_modifiers`) doit le "
        f"poser sur le vrai root, quel que soit le slot qui l'a composé. "
        f"Un composant qui lit `theme['slots']['root']` à la main ne doit "
        f"PAS avoir à s'en occuper."
    )
    assert count == 1, (
        f"{cls.__name__} : `slots={{'root': …}}` apparaît {count} fois — "
        f"doublon. Le socle l'applique au wrap ; `compose_class` ne doit "
        f"plus l'appliquer pour le slot 'root' (seulement pour les autres)."
    )

    # La composition statique du thème doit survivre à l'override : on
    # compare la 1re classe composée du rendu sans override.
    m = re.search(r'\sclass="([^"]+)"', static_html)
    if m and m.group(1).strip():
        first_static = m.group(1).split()[0]
        assert first_static in html, (
            f"{cls.__name__} : `slots={{'root': …}}` a effacé la composition "
            f"statique (classe {first_static!r} absente). L'override "
            f"s'ajoute par-dessus le thème, il ne le remplace pas."
        )


def test_non_root_slot_override_reaches_the_dom() -> None:
    """Un slot NON-root composé à la main atteint le DOM lui aussi.

    Le pendant du test principal, et l'autre moitié du contrat. ``root``
    est appliqué post-render par le wrap ; les autres slots ne peuvent pas
    l'être — le socle ne sait pas quel descendant profond porte le slot
    ``"item"`` d'un ToggleGroup.

    Ils sont donc fusionnés en AMONT, dans ``_resolved_theme`` : les 164
    lectures manuelles de ``theme["slots"][X]`` y puisent déjà, contre
    seulement 35 fichiers qui composent via ``compose_class``. Un override
    posé dans le compositeur n'aurait atteint qu'un cinquième du catalogue.

    Mesuré avant le fix : ``ui.toggle_group(slots={"item": …})`` perdu en
    silence.
    """
    from bretzel.components import Select, ToggleButton, ToggleGroup

    with render_isolated():
        with ToggleGroup(value="a", slots={"item": "zz-item"}) as group:
            ToggleButton("a", "A")
            ToggleButton("b", "B")
        html = serialize(group.render())
    assert html.count("zz-item") == 2, (
        "`slots={'item': …}` doit atteindre CHAQUE bouton du groupe "
        f"(trouvé {html.count('zz-item')} fois, attendu 2). ToggleGroup lit "
        "`theme['slots']['item']` à la main — c'est `_resolved_theme` qui "
        "doit lui donner la valeur déjà fusionnée."
    )

    with render_isolated():
        html = serialize(Select(options=["a"], slots={"panel": "zz-panel"}).render())
    assert "zz-panel" in html, "`slots={'panel': …}` n'atteint pas le DOM"


def test_root_and_non_root_do_not_double_apply() -> None:
    """Les deux chemins coexistent sans se marcher dessus.

    ``root`` passe par le wrap post-render, les autres par le thème
    résolu. Si ``root`` était AUSSI fusionné dans le thème, il
    s'appliquerait deux fois — c'est la régression que ce test fige."""
    from bretzel.components import ToggleButton, ToggleGroup

    with render_isolated():
        with ToggleGroup(
            value="a", slots={"root": "zz-root", "item": "zz-item"}
        ) as group:
            ToggleButton("a", "A")
        html = serialize(group.render())
    assert html.count("zz-root") == 1, (
        f"`slots={{'root'}}` appliqué {html.count('zz-root')} fois — le wrap "
        f"et le thème résolu le posent tous les deux."
    )
    assert html.count("zz-item") == 1


def test_unknown_slot_key_croaks_at_construction() -> None:
    """Une clé qu'aucun slot du thème ne porte ne peut RIEN faire — elle
    doit lever, pas être avalée. C'est la même classe de défaut que celle
    que cette gate ferme : un override public qui ne fait rien en silence.

    À la CONSTRUCTION, pas au render : un composant bâti puis écarté par une
    branche conditionnelle ne serait jamais rendu, et le typo ne remonterait
    jamais. C'est aussi le contrat de ``ComponentUsageError`` (« raised at
    instantiation time ») que les 15 autres sites du dépôt respectent."""
    from bretzel.components import Card

    with pytest.raises(ComponentUsageError) as exc, render_isolated():
        Card(slots={"pannel": "p-4"})  # jamais rendu

    msg = str(exc.value)
    assert "pannel" in msg, "le message doit nommer la clé fautive"
    assert "root" in msg, (
        "le message doit lister les slots disponibles pour que l'auteur "
        "corrige sans aller lire le thème"
    )


def test_known_debt_is_still_debt() -> None:
    """Re-mesure l'exemption à chaque run. Le jour où le parent appelle le
    ``render()`` de son enfant, ce test rougit et l'entrée de ``_KNOWN_DEBT``
    doit partir — une allowlist qu'on ne re-vérifie pas est une gate qui a
    déjà perdu (audit du socle, § pathologies de gate)."""
    for name in _KNOWN_DEBT:
        cls = next(
            (c for c in public_component_classes() if c.__name__ == name), None
        )
        assert cls is not None, (
            f"{name} est dans _KNOWN_DEBT mais n'est plus un composant "
            f"public — retire l'entrée."
        )
        html = _render(cls, {"root": _MARKER})
        assert _MARKER not in html, (
            f"{name} honore maintenant `slots={{'root': …}}` — la dette est "
            f"réparée. Retire-le de _KNOWN_DEBT pour que la gate le protège."
        )


def test_gate_is_not_vacuous() -> None:
    """Sans plancher, un refactor qui casserait la construction ferait tout
    passer en SKIP et cette gate resterait verte sur zéro vérification —
    la pathologie relevée sur 4 gates par l'audit du socle."""
    covered = _renderable()
    assert len(covered) >= _FLOOR, (
        f"la gate n'exerce plus que {len(covered)} composants (plancher "
        f"{_FLOOR}) sur {len(public_component_classes())} publics. Soit la "
        f"construction a régressé, soit CONSTRUCT a besoin d'une entrée — "
        f"ne baisse pas le plancher pour faire passer la gate."
    )
