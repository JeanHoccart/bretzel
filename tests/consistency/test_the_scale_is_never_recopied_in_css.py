"""L'échelle est livrée, elle ne se recopie pas en CSS.

Ce que cette gate ferme
-----------------------

``Theme`` porte la base de l'échelle depuis le 2026-09-13 — ``spacing=``
et ``text=`` — et les valeurs livrées sont DÉJÀ celles d'un outil, donc
une app n'a en général rien à déclarer du tout. Avant, le framework ne la
portait pas, et deux apps ont écrit la même correction chacune de son
côté : ``examples/kanban`` en retaillant onze composants un par un (351
lignes), ``examples/ecole`` en injectant un bloc ``@theme { --spacing: … }``
par la porte ``css=``.

Les deux formes échouent de la même façon, et c'est ce qui les rend
gatables ensemble : **elles marchent**. La page est juste, la suite est
verte, et la seule chose qui se dégrade est qu'une troisième app
recopiera. La première forme a un défaut mesuré en plus — une liste de
composants écrite à la main est une liste de composants qu'on a pensé à
citer, et les onze oubliés ont mis quatre hauteurs de champ texte sur un
même écran.

Pourquoi l'interdiction porte sur ``@theme``
--------------------------------------------

Écrire ``--spacing`` n'est pas fautif en soi : le theme studio du
playground injecte le jeton dans une feuille ``<style>`` depuis le
navigateur, pour montrer le réglage en direct — il n'y a pas
d'aller-retour serveur, donc ``Theme`` ne peut rien y faire. Ce qui est
fautif est de REDÉCLARER le jeton dans un bloc ``@theme``, parce que c'est
exactement ce que le paramètre fait maintenant, en une ligne et sans
contourner la validation.

D'où un détecteur sur la CONJONCTION (``@theme`` + un jeton d'échelle) et
non sur le jeton seul. Un détecteur trop large aurait rougi sur un export
correct du studio, ce qui est le pire des deux échecs — celui qui pousse à
débrancher la règle.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import pytest

from bretzel.theme import DEFAULT_SPACING_PX, TEXT_SLOT_NAMES, Theme
from tests.consistency._discovery import (
    EXAMPLES_FLOOR,
    REPO_ROOT,
    ParsedSource,
    code_string_literals,
    parsed_sources,
)

EXAMPLES_DIR: Final[Path] = REPO_ROOT / "examples"

#: Preuve de morsure : le seul DÉTECTEUR de ce fichier, sur ses deux
#: versants. Le reste cherche des sous-chaînes connues ; celui-ci cherche
#: une FORME, donc il peut cesser de voir sans que rien ne rougisse.
MUTATION_PROOF = "test_the_scale_token_reader_still_bites"

#: Les jetons qui portent l'échelle, c'est-à-dire ceux que ``spacing=`` et
#: ``text=`` émettent. Dérivés de la source du framework et non recopiés :
#: un palier ajouté à :data:`TEXT_SLOT_NAMES` entre ici sans qu'on y
#: touche, et c'est ce qui empêche la gate de juger une liste périmée.
SCALE_TOKENS: Final[tuple[str, ...]] = (
    "--spacing",
    *(f"--text-{slot}" for slot in TEXT_SLOT_NAMES),
)


def declares_scale_in_at_theme(text: str) -> list[str]:
    """Les jetons d'échelle qu'un bloc ``@theme`` de ce texte redéclare.

    Rend la liste plutôt qu'un booléen : le message d'échec doit nommer ce
    qui a été recopié, sinon il envoie relire 300 lignes.
    """
    if "@theme" not in text:
        return []
    return [token for token in SCALE_TOKENS if re.search(rf"{token}\s*:", text)]


def test_the_sweep_is_not_vacuous() -> None:
    """Plancher sur la DÉCOUVERTE des sources, pas sur leur contenu.

    Sans lui, un chemin faux ferait affirmer « aucune app ne recopie
    l'échelle » en n'ayant lu aucune app.
    """
    assert len(parsed_sources(EXAMPLES_DIR, floor=EXAMPLES_FLOOR)) >= EXAMPLES_FLOOR


@pytest.mark.parametrize(
    "source",
    parsed_sources(EXAMPLES_DIR, floor=EXAMPLES_FLOOR),
    ids=lambda s: str(s.path.relative_to(REPO_ROOT)).replace("\\", "/"),
)
def test_no_app_redeclares_the_scale_in_css(source: ParsedSource) -> None:
    """Aucune app ne redéclare un jeton d'échelle dans un ``@theme``.

    Lit les littéraux que le code FABRIQUE et non le texte brut : une
    docstring qui explique le retrait — celle de ce fichier en est une — ne
    doit pas compter comme une occurrence vivante. C'est le contrat de
    ``code_string_literals``, et c'est mesuré ailleurs dans ce dépôt (deux
    commentaires faisaient remonter un symbole que personne n'écrit).
    """
    for node in code_string_literals(source.tree):
        if not isinstance(node.value, str):
            continue
        copied = declares_scale_in_at_theme(node.value)
        assert not copied, (
            f"{source.path.relative_to(REPO_ROOT)}:{node.lineno} redéclare "
            f"{copied} dans un bloc `@theme`.\n"
            f"  C'est la correction de densité que deux apps ont écrite à la "
            f"main avant que le framework la porte. Le défaut livré est "
            f"maintenant celui d'un outil, donc il n'y a probablement RIEN à "
            f"écrire ; et pour une autre échelle, les paramètres sont "
            f"`Theme(spacing=…, text={{…}})` — validés, et visibles de "
            f"`bretzel describe Theme`."
        )


def test_the_default_theme_actually_carries_the_scale() -> None:
    """Le versant POSITIF : le thème LIVRÉ pose les deux jetons.

    Une gate qui n'interdirait que la copie resterait verte le jour où le
    framework cesserait d'émettre quoi que ce soit — les apps n'écriraient
    plus rien à la main ET n'obtiendraient plus rien, ce qui est le silence
    que tout ce chantier ferme. C'est le thème NU qu'on interroge : une app
    ne demande plus la densité, elle la reçoit.
    """
    css = Theme().generate_css()
    assert "--spacing: " in css, (
        "le thème livré n'émet plus `--spacing` : toutes les apps sont "
        "retombées à l'échelle d'un document, sans rien dire."
    )
    missing = [
        f"--text-{slot}"
        for slot in Theme()._text
        if f"--text-{slot}: " not in css
    ]
    assert not missing, f"paliers de texte déclarés mais non émis : {missing}"


def test_the_scale_is_carried_by_tokens_not_by_components() -> None:
    """L'échelle vit dans les JETONS, pas dans une liste de composants.

    C'est la forme qui a échoué : une table écrite à la main laisse au
    défaut ceux qu'on n'a pas cités — onze sur vingt-deux, mesuré sur
    ``examples/ecole``, soit quatre hauteurs de champ sur un écran. Le
    thème livré ne doit donc nommer aucun composant pour sa densité : si
    une entrée apparaît dans ``_components``, c'est que la liste est
    revenue.
    """
    assert Theme()._components == {}, (
        "le thème livré nomme des composants. L'échelle se déplace par sa "
        "BASE — `spacing` et `text` — précisément pour que la couverture "
        "cesse d'être une liste qu'on peut oublier d'allonger."
    )


def test_the_pitch_in_pixels_matches_the_css() -> None:
    """Le nombre servi à Python et la longueur servie au CSS s'accordent.

    Deux autorités sur la même grandeur ne se composent pas : une app qui
    compose une géométrie en Python (la hauteur d'un bloc de N heures) lit
    :data:`DEFAULT_SPACING_PX`, le navigateur lit ``--spacing``. Si les deux
    divergent, la grille se décale d'un cran par heure et rien ne le dit.
    """
    css_value = Theme()._spacing
    assert css_value is not None
    rem = float(css_value.removesuffix("rem"))
    assert rem * 16 == DEFAULT_SPACING_PX, (
        f"`--spacing: {css_value}` vaut {rem * 16} px mais "
        f"`DEFAULT_SPACING_PX` dit {DEFAULT_SPACING_PX}. Une app qui calcule "
        f"une géométrie en Python se décalera d'un cran par cran."
    )


def test_the_scale_token_reader_still_bites() -> None:
    """Les deux versants du détecteur.

    Versant qui MORD : la forme exacte qu'``examples/ecole`` portait.
    Versant qui ÉPARGNE : le studio, qui injecte le même jeton dans une
    feuille ``<style>`` sans bloc ``@theme`` — un réglage en direct n'a pas
    d'aller-retour serveur, donc il ne peut pas passer par ``Theme``.
    """
    coupable = "@theme {\n  --spacing: 0.1875rem;\n  --text-sm: 13px;\n}"
    assert declares_scale_in_at_theme(coupable) == ["--spacing", "--text-sm"], (
        "le détecteur ne reconnaît plus un bloc @theme qui redéclare "
        "l'échelle."
    )
    licite = "':root{' + v + '--spacing:' + p + 'rem;}'"
    assert not declares_scale_in_at_theme(licite), (
        "le détecteur prend l'injection en direct du studio pour une copie "
        "de thème."
    )
    assert not declares_scale_in_at_theme("@theme { --radius-box: 1rem; }"), (
        "le détecteur prend un jeton de FORME pour un jeton d'échelle."
    )
