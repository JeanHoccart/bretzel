"""Gate : ce que le preflight Tailwind v3 donnait gratuitement est restauré.

Deux comportements que la v3 offrait sans rien demander, que la v4 a
retirés, et que Bretzel n'a jamais eus puisqu'il n'a tourné que sur v4
(``v4.0.0`` → ``v4.3.2``) :

- le survol **inconditionnel** — la v4 enveloppe chaque ``hover:`` dans
  ``@media (hover: hover)``, donc rien ne s'applique sur un appareil sans
  pointeur survolant ;
- le **curseur main sur les boutons** — le ``@layer base`` généré ne
  contient plus aucune déclaration ``cursor``.

Les deux se réparent dans le CSS de thème, pas dans les composants. Une
ligne chacun, mais elles portent tout le catalogue : si l'une saute, la
panne est totale, silencieuse, et **invisible sur une machine à souris** —
donc invisible en CI. D'où cette gate. Mécanisme, mesures et date : cf.
``.claude/bretzel/traps.md``.

Portée honnête : cette gate vérifie que les règles sont ÉMISES, pas que le
compilateur les honore encore. Un bump de Tailwind qui changerait
l'échappatoire la garderait verte pendant que le bug revient. Un vrai
gate de compilation coûterait le binaire de 112 Mo en CI ; le compromis est
assumé, pas oublié.

Ce que cette gate NE remplace pas : ``test_hover_only_controls_reachable``.
Dé-gater fait EXISTER la règle ; ça ne fait pas produire un survol à un
doigt. ``hover:`` reste un enrichissement, jamais un porteur d'affordance.
"""

from __future__ import annotations

import re

import pytest

from bretzel.render.shell import _strip_tailwind_import
from bretzel.theme import Theme, strip_safelist

# La redéfinition, à la lettre. ``&:hover`` nu = la sémantique v3.
_HOVER_OVERRIDE = "@custom-variant hover (&:hover);"


@pytest.fixture(scope="module")
def theme_css() -> str:
    # ``Theme()`` = le thème par défaut réellement livré (palette résolue +
    # ScrollbarConfig), pas un sosie reconstruit à la main.
    return Theme().generate_css()


# ───────────────────────────────────────────────────────────────────────────
# Survol inconditionnel
# ───────────────────────────────────────────────────────────────────────────


def test_theme_css_redefines_the_hover_variant(theme_css: str) -> None:
    assert _HOVER_OVERRIDE in theme_css, (
        "Le CSS de thème ne redéfinit plus la variante hover. Tailwind v4 "
        "va donc remettre chaque `hover:` derrière `@media (hover: hover)`, "
        "et tout le survol du design system disparaît sur tactile."
    )


def test_hover_override_survives_the_dev_mutations(theme_css: str) -> None:
    # Le chemin dev mutile le CSS avant de l'injecter : la safelist part
    # (inutile au compilateur navigateur) et la directive ``@import`` part
    # (le CDN importe tailwindcss lui-même). La redéfinition doit traverser
    # les deux — sinon elle ne protège que la prod, c'est-à-dire pas la
    # machine sur laquelle on développe.
    delivered = _strip_tailwind_import(strip_safelist(theme_css))
    assert _HOVER_OVERRIDE in delivered, (
        "La redéfinition de hover n'arrive pas jusqu'au bloc "
        '<style type="text/tailwindcss"> du mode dev.'
    )


def test_hover_override_is_not_itself_gated(theme_css: str) -> None:
    # ``@custom-variant hover (@media (any-hover: hover) { &:hover })``
    # paraît plus prudent et ne corrige RIEN sur le cas mesuré : ce Chrome
    # répond ``false`` à ``any-hover`` comme à ``hover``. Toute media query
    # ici ramène le bug.
    gated = [
        line
        for line in theme_css.splitlines()
        if "@custom-variant hover" in line and "@media" in line
    ]
    assert not gated, (
        f"La variante hover est redéfinie derrière une media query : {gated}. "
        "Sur l'appareil qui a motivé ce correctif, `any-hover` et `hover` "
        "répondent toutes deux false — la gate reste fermée."
    )


# ───────────────────────────────────────────────────────────────────────────
# Curseur des boutons
# ───────────────────────────────────────────────────────────────────────────


_CURSOR_RULE_RE = re.compile(
    r"@layer base\s*\{[^{]*\{[^}]*cursor:\s*pointer[^}]*\}", re.S
)


def test_theme_css_restores_the_button_cursor(theme_css: str) -> None:
    assert _CURSOR_RULE_RE.search(theme_css), (
        "Le CSS de thème ne déclare plus le curseur main des boutons. Les "
        "boutons du catalogue repassent à la flèche — v4 a retiré la règle "
        "de preflight qui la donnait, et aucun thème de bouton ne porte la "
        "classe."
    )


def test_button_cursor_rule_lives_in_the_base_layer(theme_css: str) -> None:
    # Hors ``@layer``, la règle battrait TOUS les utilitaires ``cursor-*``
    # (v4 classe le CSS non-layered au-dessus des layers) : Slider perdrait
    # son ``cursor-grab``, Combobox son ``cursor-text``, Card son
    # ``aria-disabled:cursor-default``. Dans ``base``, les utilitaires
    # gagnent — exactement le comportement du preflight v3.
    block = _CURSOR_RULE_RE.search(theme_css)
    assert block and block.group(0).startswith("@layer base"), (
        "La règle de curseur n'est plus dans @layer base : elle écrase "
        "maintenant tout utilitaire cursor-* du catalogue."
    )


def test_button_cursor_spares_disabled_controls(theme_css: str) -> None:
    # Un contrôle désactivé doit garder ``cursor-not-allowed`` (cf.
    # ``test_disabled_affordance``). La garde se vérifie sélecteur PAR
    # sélecteur : chercher ``aria-disabled`` n'importe où dans la règle
    # laisserait passer sa disparition d'un seul des deux (mutation
    # testée — elle passait).
    rule = _CURSOR_RULE_RE.search(theme_css).group(0)
    selectors = [
        s.strip()
        for s in rule[rule.index("{") + 1 : rule.rindex("{")].split(",")
        if s.strip()
    ]
    assert selectors, "La règle de curseur n'a plus de sélecteur lisible."

    for selector in selectors:
        assert ':not([aria-disabled="true"])' in selector, (
            f"Le sélecteur {selector!r} ne protège plus aria-disabled : un "
            "contrôle à rôle désactivé affiche la main au lieu de "
            "not-allowed. Les contrôles role-based se désactivent par "
            "aria-disabled, pas par l'attribut natif."
        )
    native = [s for s in selectors if s.startswith("button")]
    assert native and all(":not(:disabled)" in s for s in native), (
        f"Le sélecteur natif {native!r} ne protège plus :disabled — "
        "<button disabled> repasse à la main."
    )


def test_the_sweep_is_not_vacuous(theme_css: str) -> None:
    """Plancher : le CSS jugé est bien celui d'un thème réel.

    Ici la population n'est pas une liste de fichiers mais UNE chaîne :
    celle que ``Theme().generate_css()`` produit. Un thème qui rendrait
    une feuille vide ferait échouer les ``in``, mais pas les
    interdictions — et c'est celles-là qui passeraient sur du vide.
    """
    assert len(theme_css) >= 5000, (
        f"la feuille de thème ne fait plus que {len(theme_css)} caractères "
        f"(23 086 le 2026-08-19) — ce n'est plus un thème réel qu'on juge."
    )
