"""Les thèmes n'écrivent pas de couleur Tailwind EN DUR.

Bretzel ne fait pas son mode sombre avec la variante ``dark:`` — mesuré :
**zéro** thème de composant en porte une. Il le fait avec des **tokens
sémantiques** (``bg-interface``, ``text-text``, ``bg-background``,
``bg-{bg_color}``) dont la VALEUR change quand la palette bascule. Un
composant qui n'utilise que ces tokens suit les deux modes gratuitement,
sans une ligne de CSS conditionnel.

Le corollaire est le vrai risque : **une couleur de la palette fixe de
Tailwind** (``bg-white``, ``text-gray-700``, ``bg-slate-900``) ne bascule
pas. Elle est correcte dans un mode et fausse dans l'autre — et le défaut
ne se voit que si quelqu'un ouvre la page dans le mode qu'il ne teste
jamais. C'est le mode d'échec le plus cher : invisible à l'auteur.

``_ALLOWED`` liste les cinq usages LÉGITIMES mesurés le 2026-07-28, chacun
argumenté. Ils ont un point commun : la couleur n'est jamais posée sur la
surface de la PAGE, mais sur un voile ou sur un fond de marque — deux
contextes qui ne bougent pas avec le mode.

L'assert est une égalité stricte : retirer un usage sans retirer son entrée
fait échouer la gate, donc la liste ne peut pas pourrir.
"""

from __future__ import annotations

import ast
import re

import pytest

from tests.consistency._discovery import ParsedSource, theme_sources

_THEMES = theme_sources()

_TAILWIND_PALETTE = (
    "white|black|slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|"
    "green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose"
)
_HARDCODED = re.compile(
    rf"\b(?:bg|text|border|ring|fill|stroke|from|to|via)-"
    rf"(?:{_TAILWIND_PALETTE})"
    rf"(?:-\d{{2,3}})?(?:/\d{{1,3}})?\b"
)

# Les usages légitimes, un par un, avec leur raison.
_ALLOWED: dict[str, set[str]] = {
    # Voile modal : un noir semi-transparent EST la bonne réponse dans les
    # deux modes — c'est un assombrissement, pas une surface.
    "dialog": {"bg-black/50"},
    "drawer": {"bg-black/50"},
    # Même voile, même raison : le mode ``collapsible="overlay"`` de la
    # sidebar est un panneau modal de téléphone, et son fond assombri est
    # un assombrissement, pas une surface. Ajouté le 2026-08-15 avec ce
    # mode ; il réutilise le voile de ``drawer`` mot pour mot.
    "sidebar": {"bg-black/50"},
    # Assombrissement au survol du x d'un badge SOLIDE : il est posé sur le
    # fond de marque du badge (``bg-{bg_color}``), pas sur la page.
    "badge": {"bg-black/10"},
    # Surface d'un MÉDIA, pas de la page — la catégorie s'élargit d'un
    # cran ici, et c'est assumé. Les bandes de letterboxing sont noires
    # chez tous les lecteurs, dans les deux modes, parce que la vidéo est
    # étalonnée contre du noir. Un token sémantique donnerait des bandes
    # gris clair autour d'une image sombre en mode clair : pas « adapté
    # au thème », juste faux.
    "video": {"bg-black"},
    # Bouton du switch, sur une piste colorée : blanc dans les deux modes,
    # comme iOS / Material.
    "switch": {"bg-white"},
    # Texte du x de suppression sur son fond d'erreur (``active:bg-error``).
    "file_upload": {"text-white"},
}


def _hardcoded_in(source: str) -> set[str]:
    """Les couleurs figées présentes dans les CHAÎNES du thème.

    En AST : un commentaire qui mentionne ``bg-white`` pour expliquer
    pourquoi on ne l'utilise PAS ne doit pas déclencher la gate.
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found |= set(_HARDCODED.findall(node.value))
    return found


@pytest.mark.parametrize("source", _THEMES, ids=lambda s: s.path.parent.name)
def test_theme_uses_semantic_colours(source: ParsedSource) -> None:
    name = source.path.parent.name
    found = _hardcoded_in(source.text)
    allowed = _ALLOWED.get(name, set())
    assert found == allowed, (
        f"{name} : couleurs Tailwind en dur = {sorted(found)}, "
        f"attendu = {sorted(allowed)}.\n"
        f"  - EN TROP : une couleur de la palette FIXE ne bascule pas avec "
        f"le mode sombre. Elle sera juste dans un mode et fausse dans "
        f"l'autre, et ça ne se verra que dans le mode que tu ne testes "
        f"pas. Utilise un token sémantique — `bg-interface`, `text-text`, "
        f"`bg-background`, `bg-{{bg_color}}` — dont la VALEUR suit la "
        f"palette.\n"
        f"  - MANQUANT : tu viens de le retirer, retire aussi son entrée de "
        f"`_ALLOWED`.\n"
        f"  Si l'usage est légitime (voile, fond de marque), ajoute-le à "
        f"`_ALLOWED` AVEC sa raison — les cinq qui y sont en ont une."
    )


def test_no_component_theme_uses_the_dark_variant() -> None:
    """Le mode sombre passe par la palette, pas par ``dark:``.

    Épingle le mécanisme : si un thème se met à écrire ``dark:``, c'est
    qu'il a renoncé aux tokens sémantiques — et il faudra alors maintenir
    deux jeux de classes au lieu d'un.
    """
    offenders = [
        s.path.parent.name for s in _THEMES
        if "dark:" in "".join(
            n.value for n in ast.walk(s.tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        )
    ]
    assert not offenders, (
        f"{offenders} utilisent la variante `dark:`. Bretzel bascule la "
        f"PALETTE, pas les classes : un token sémantique suit le mode tout "
        f"seul. Deux jeux de classes = deux fois plus à tenir juste."
    )


def test_the_sweep_is_not_vacuous() -> None:
    """Plancher : les thèmes balayés existent encore.

    « Aucune couleur Tailwind en dur » est vrai sur zéro thème. Le
    plancher chiffré vit dans ``theme_sources()`` ; celui-ci vérifie que
    CETTE gate en reçoit bien le résultat.
    """
    assert len(_THEMES) >= 60, (
        f"seulement {len(_THEMES)} thèmes de composant balayés (72 le "
        f"2026-08-19) — le balayage partagé ne rend plus rien ici."
    )


def test_the_detector_still_bites() -> None:
    """Mutation : une couleur Tailwind FIXE est encore reconnue.

    Une palette fixe ne bascule pas avec le mode sombre : elle est juste
    dans un mode et fausse dans l'autre, et ça ne se voit que dans le
    mode qu'on ne teste pas. Si la regex cessait de matcher,
    l'interdiction passerait sur les 72 thèmes sans rien regarder.
    """
    for offending in ("bg-slate-800", "text-white", "ring-red-500/40", "border-zinc-200"):
        assert _HARDCODED.search(offending), f"{offending!r} devrait mordre"
    for licit in ("bg-interface", "text-text", "bg-{bg_color}", "ring-primary/40"):
        assert not _HARDCODED.search(licit), f"{licit!r} : faux positif"
