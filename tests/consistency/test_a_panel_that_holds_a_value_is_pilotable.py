"""Gate : un panneau ancré qui porte une valeur s'ouvre ET s'écrit.

Ce qu'elle garde
-----------------
Certains composants sont DEUX natures à la fois : un panneau ancré —
comme ``dialog`` — et un champ qui porte une valeur — comme ``input``.
Les deux familles ont chacune leur vocabulaire impératif, fixé depuis
longtemps :

    panneau   open / close / toggle
    valeur    set / clear / focus / blur

Rien n'obligeait leur intersection à avoir les deux, et **elle ne les
avait pas**. Mesuré le 2026-09-02 : 22 composants exposaient une surface
impérative, et **les six pickers étaient le seul groupe entier du
catalogue à n'en avoir aucune** — pas de ``.open()``, pas de ``.set()``,
rien. Le ``calendar`` qu'ils embarquent avait pourtant la sienne
complète : la mécanique existait et s'arrêtait à leur frontière.

Réparé le 2026-09-03 sur les six pickers, puis sur ``combobox`` et
``select`` — les huit composants de cette forme portent désormais la
MÊME surface. Équiper les uns sans les autres aurait fait deux
conventions pour une seule nature, ce que le principe 4 refuse.

Reste ``calendar``, et c'est une exception LÉGITIME, pas une dette : son
panneau n'est pas un survol, **c'est le composant lui-même**. Il est
toujours affiché ; ``.open()`` n'y désignerait rien. (Les ``open`` qu'on
trouve dans sa source appartiennent à ses menus déroulants de mois et
d'année, pas à lui.)

⚠️ Ce que cette gate ne peut PAS faire, et pourquoi la population est
écrite
-------------------------------------------------------------------
Détecter « panneau ancré » par les helpers ``anchored_*`` rate
``month_picker`` et ``week_picker`` : les leurs vivent dans
``_picker_field.render_calendar_field``, pas dans leur module. Un
détecteur qui les avalerait en silence serait pire qu'une liste — c'est
précisément l'angle mort qui a laissé le trou d'origine invisible (la
gate des chevrons, elle aussi, ne voyait pas les pickers).

La population est donc NOMMÉE, et le plancher vérifie que chaque nom
existe encore et porte bien une valeur.
"""

from __future__ import annotations

from bretzel.introspect import describe_components

#: Preuve de morsure : contrôle POSITIF — la lecture de la surface voit
#: encore de vraies méthodes, et sait distinguer les deux moitiés.
MUTATION_PROOF = "test_the_surface_sweep_is_not_vacuous"

#: Les composants qui sont un panneau ancré ET un porteur de valeur.
_PANNEAU_ET_VALEUR: tuple[str, ...] = (
    "calendar",
    "color_picker",
    "combobox",
    "date_picker",
    "date_range_picker",
    "month_picker",
    "select",
    "time_picker",
    "week_picker",
)

#: Le vocabulaire des panneaux, et celui des porteurs de valeur.
_OUVERTURE = ("open", "close", "toggle")
_VALEUR = ("set", "clear", "focus", "blur")

#: Ceux qui n'ont PAS la moitié panneau. **Cliquet : ce nombre ne
#: remonte pas.** UN seul, et c'est une exception motivée : ``calendar``
#: EST son panneau, toujours affiché — ``.open()`` n'y désignerait rien.
#: Tout composant neuf de cette forme naît avec les sept.
_SANS_OUVERTURE_AT_FREEZE = 1


def _surfaces() -> dict[str, tuple[str, ...]]:
    # ⚠️ `describe_components` rend AUSSI des `HelperInfo` (les
    # fabriques comme `ui.column`), qui n'ont pas de surface impérative.
    # Filtrer par attribut plutôt que par type : c'est ce que la donnée
    # dit d'elle-même.
    return {
        info.ui_name: tuple(info.imperative)
        for info in describe_components()
        if hasattr(info, "imperative")
    }


def test_the_surface_sweep_is_not_vacuous() -> None:
    """Plancher, ancré sur la DÉCOUVERTE de cette gate.

    Sans lui, un lecteur qui rendrait des tuples vides ferait passer les
    deux exigences en ne voyant rien — et le versant LICITE (``input``
    n'a que la moitié valeur, ``dialog`` que la moitié panneau) est
    celui qui attrape un lecteur qui rendrait tout.
    """
    surfaces = _surfaces()
    assert len(surfaces) >= 60, (
        f"seulement {len(surfaces)} composants lus — le balayage de la "
        f"surface est probablement cassé (111 au gel)."
    )
    manquants = [n for n in _PANNEAU_ET_VALEUR if n not in surfaces]
    assert not manquants, (
        f"composant(s) nommé(s) par cette gate et introuvable(s) : "
        f"{manquants} — renommés ou supprimés."
    )
    assert set(surfaces["dialog"]) == set(_OUVERTURE), (
        f"`dialog` doit porter la moitié PANNEAU et rien d'autre — "
        f"vu : {surfaces['dialog']}"
    )
    assert set(surfaces["input"]) == set(_VALEUR), (
        f"`input` doit porter la moitié VALEUR et rien d'autre — "
        f"vu : {surfaces['input']}"
    )


def test_a_value_panel_can_be_written() -> None:
    """La moitié VALEUR est due à tous, sans exception.

    C'est la moitié qui manquait aux six pickers : ils portaient une
    valeur que rien ne pouvait poser ni vider depuis le code.
    """
    surfaces = _surfaces()
    incomplets = sorted(
        (nom, sorted(set(_VALEUR) - set(surfaces.get(nom, ()))))
        for nom in _PANNEAU_ET_VALEUR
        if not set(_VALEUR) <= set(surfaces.get(nom, ()))
    )
    assert not incomplets, (
        f"composant(s) qui portent une valeur sans pouvoir l'écrire : "
        f"{incomplets}.\n"
        f"  `install_value_commands` de `base/_wiring` pose les quatre "
        f"méthodes ; ne les réécris pas à la main."
    )


def test_the_unopenable_debt_only_shrinks() -> None:
    """Cliquet sur ceux qui n'ont pas encore la moitié PANNEAU.

    ⚠️ Elle ne demande pas d'équiper les deux qui restent — c'est une
    décision d'API, pas un fix. Elle refuse le troisième.
    """
    surfaces = _surfaces()
    sans = sorted(
        nom for nom in _PANNEAU_ET_VALEUR
        if not set(_OUVERTURE) <= set(surfaces.get(nom, ()))
    )
    assert len(sans) <= _SANS_OUVERTURE_AT_FREEZE, (
        f"{len(sans)} panneaux à valeur sans `.open()` / `.close()` / "
        f"`.toggle()`, contre {_SANS_OUVERTURE_AT_FREEZE} au gel : "
        f"{sans}.\n"
        f"  Un composant NEUF de cette forme naît avec les sept — "
        f"`install_open_close_toggle` + `install_value_commands`, plus "
        f"les récepteurs `imperative_listeners(\"open\")` sur sa racine, "
        f"sans quoi les méthodes émettent un événement que personne "
        f"n'écoute."
    )
