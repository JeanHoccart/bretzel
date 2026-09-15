"""Gate : « pris », dans une liste multi, ne se dit pas qu'en couleur.

Les deux pickers marquaient une option prise avec ``option_selected``
seul — ``font-semibold text-{color}``. Trois raisons pour lesquelles ça
ne suffit pas, et la troisième est celle qui l'a fait remarquer :

1. **``option_active`` est accentué aussi** (``bg-{color}/10
   text-{color}``, posé au survol et à la navigation clavier). Survolé
   et pris se ressemblent, donc l'accent ne dit plus lequel des deux.
2. **Un filtre s'ouvre avec TOUT pris.** « Rien de décoché » est la même
   vue que « rien de filtré », donc le panneau de filtre du datatable
   s'ouvre sur une liste uniformément bleue : l'œil n'y lit aucune
   sélection, alors que TOUT est sélectionné.
3. **La couleur seule n'est pas une affordance accessible** — c'est le
   critère WCAG 1.4.1, et il vaut ici même si ``aria-selected`` couvre le
   lecteur d'écran : la personne qui voit mal les contrastes n'utilise
   pas forcément un lecteur d'écran.

Ce que la gate exige : dans une liste MULTI, chaque option porte un
enfant dont la visibilité est pilotée par le prédicat de sélection
(``bz-show="_isPicked(…)"``). C'est décidable en SSR, et c'est la forme
— pas la couleur — qui est protégée.

⚠️ Elle ne s'applique PAS au mode simple, et c'est délibéré : le
déclencheur y affiche déjà l'étiquette prise, et la liste n'a qu'une
seule ligne accentuée à un instant donné.
"""

from __future__ import annotations

import pytest

from bretzel import ui
from bretzel.components.base.testing import render_isolated
from bretzel.core.tree import Element
from tests.consistency._discovery import walk_elements

#: Preuve de morsure : contrôle NÉGATIF — le mode simple ne doit PAS porter la marque, ce
#: qui prouve que la marque cherchée existe bien dans l'autre mode.
MUTATION_PROOF = "test_single_mode_stays_bare"

# (id, builder). Les deux pickers à panneau — leurs thèmes promettent
# explicitement de « se lire comme une famille », donc l'affordance doit
# exister des deux côtés ou la promesse est fausse.
_MULTI_PICKERS = [
    ("combobox", lambda: ui.combobox(["a", "b"], value=["a"], multiple=True)),
    ("select", lambda: ui.select(["a", "b"], value=["a"], multiple=True)),
]

_SINGLE_PICKERS = [
    ("combobox", lambda: ui.combobox(["a", "b"], value="a")),
    ("select", lambda: ui.select(["a", "b"], value="a")),
]


def _options(root: Element) -> list[Element]:
    return [
        n for n in walk_elements(root)
        if (getattr(n, "attrs", {}) or {}).get("role") == "option"
    ]


def _picked_gated_children(option: Element) -> list[Element]:
    """Les enfants de l'option que le prédicat de sélection montre/cache."""
    return [
        child for child in (option.children or ())
        if "_isPicked" in str(
            (getattr(child, "attrs", {}) or {}).get("bz-show", "")
        )
    ]


@pytest.mark.parametrize(
    "name,build", _MULTI_PICKERS, ids=[c[0] for c in _MULTI_PICKERS]
)
def test_multi_option_marks_picked_with_more_than_colour(name, build) -> None:
    with render_isolated():
        rendered = build().render()
    options = _options(rendered)
    assert options, f"{name} : aucune option rendue — la sonde est aveugle"
    for option in options:
        value = (option.attrs or {}).get("data-value")
        assert _picked_gated_children(option), (
            f"{name} : l'option {value!r} ne marque « pris » QUE par la "
            f"couleur (`option_selected`). `option_active` est accentué "
            f"lui aussi, donc survolé et pris se ressemblent — et un "
            f"panneau ouvert avec TOUT pris (le cas normal d'un filtre de "
            f"colonne) se lit comme une liste sans sélection. Ajoute un "
            f"enfant gaté sur le prédicat : "
            f"`_picker.option_check(picked_js=\"_isPicked(…)\", …)`."
        )


@pytest.mark.parametrize(
    "name,build", _MULTI_PICKERS, ids=[c[0] for c in _MULTI_PICKERS]
)
def test_the_mark_is_pre_stamped_for_its_ssr_state(name, build) -> None:
    """Pas de clignotement avant le boot du runtime.

    ``bz-show`` ne s'évalue qu'une fois le runtime démarré : sans
    pré-stamp, TOUTES les coches peignent visibles au premier paint puis
    disparaissent. C'est la moitié du contrat qu'un test « la coche
    existe » laisserait passer.
    """
    with render_isolated():
        rendered = build().render()
    for option in _options(rendered):
        value = str((option.attrs or {}).get("data-value"))
        for mark in _picked_gated_children(option):
            hidden = "display:none" in str(
                (mark.attrs or {}).get("style", "")
            ).replace(" ", "")
            # ``value=["a"]`` : seule "a" est prise au SSR.
            assert hidden == (value != "a"), (
                f"{name} : la coche de {value!r} peint dans le mauvais état "
                f"avant le boot (pré-stamp {'posé' if hidden else 'absent'}). "
                f"Cf. `stamp_display_none`."
            )


@pytest.mark.parametrize(
    "name,build", _SINGLE_PICKERS, ids=[c[0] for c in _SINGLE_PICKERS]
)
def test_single_mode_stays_bare(name, build) -> None:
    """La coche est une affordance de LISTE MULTIPLE.

    En mode simple le déclencheur porte déjà l'étiquette prise, et une
    seule ligne est accentuée à la fois. Ce test dit que le plancher
    ci-dessus n'a pas été appliqué en gros sabot aux deux modes.
    """
    with render_isolated():
        rendered = build().render()
    options = _options(rendered)
    assert options, f"{name} : aucune option rendue"
    assert not any(_picked_gated_children(o) for o in options), (
        f"{name} : le mode simple a hérité de la coche du mode multi."
    )
