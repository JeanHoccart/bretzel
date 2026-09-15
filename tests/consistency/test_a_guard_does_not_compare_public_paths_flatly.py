"""Une garde qui lit ``app.public_paths`` appelle ``is_public_asset_path``.

Le piège
---------
:attr:`Bretzel.public_paths` rend un ``frozenset`` qui **mélange deux
natures** : des chemins réels (les routes des portes ``@auth.door``,
``runtime.js``, les deux feuilles) et un MOTIF de route,
``/_bretzel/vendor/{filename}``, monté avec un paramètre. Le motif n'est
égal à aucun chemin reçu.

Une garde qui écrit ``request.url.path in PUBLIC`` refuse donc toujours
les trois scripts tiers, les redirige vers la page de connexion, et le
navigateur reçoit du HTML là où il attend du JavaScript. Le symptôme est
``Unexpected token '<'`` en boucle, htmx jamais chargé, **plus aucun
POST** : l'app paraît morte, sans une seule erreur serveur.

Et il ne se déclenche **que si ``.bretzel/vendor/`` existe**. Sans cache
vendorisé, ``url_for`` sert les CDN et cette route n'est jamais demandée.
Le symptôme apparaît donc le jour où quelqu'un lance la vendorisation,
des semaines après que la garde a été écrite, sur une machine et pas sur
une autre. Mesuré dans les deux sens le 2026-08-27 sur
``examples/auth`` : cache déplacé → probe vert, cache remis → probe
rouge.

Deux sites l'ont eu — ``examples/crm`` (réparé le 2026-08-24 en passant
la route vendor publique) puis ``examples/auth`` — donc c'est une
classe, pas un accident. :func:`bretzel.runtime.is_public_asset_path`
est le remède, et sa docstring le dit déjà ; ce qui manquait, c'est
quelque chose qui le fasse respecter.

Ce que la gate n'affirme PAS
-----------------------------
Que la garde est correcte : elle ne lit pas sa logique, seulement que
les deux noms cohabitent dans le module. Un module qui appellerait
l'helper sur un autre chemin que celui qu'il teste passerait. C'est
assumé — la forme fautive réelle est l'OUBLI pur, pas un appel de
travers, et un lecteur de flot de contrôle coûterait plus cher que ce
qu'il attraperait.

Elle ne juge pas non plus ``bretzel/`` : le framework ne s'auto-garde
pas, ce sont les apps qui écrivent des gardes.

La marche d'après (dans ``work/todo.md``) : ``public_paths`` ne devrait
peut-être pas mélanger motifs et chemins dans un même ensemble. Tant
qu'il le fait, cette gate est le filet.
"""

from __future__ import annotations

import ast

from tests.consistency._discovery import EXAMPLES_FLOOR, REPO_ROOT, parsed_sources

#: Preuve de morsure : le contrôle NÉGATIF vit dans
#: ``test_the_detector_still_bites``.
MUTATION_PROOF = "test_the_detector_still_bites"


def reads_public_paths(tree: ast.AST) -> bool:
    """Le module lit-il ``<quelque chose>.public_paths`` ?

    Un accès d'ATTRIBUT, pas une chaîne : le nom peut apparaître dans
    une docstring qui explique le piège — c'est même le cas ici — sans
    qu'aucune garde ne soit en jeu.
    """
    return any(
        isinstance(node, ast.Attribute) and node.attr == "public_paths"
        for node in ast.walk(tree)
    )


def calls_the_helper(tree: ast.AST) -> bool:
    """Le module nomme-t-il ``is_public_asset_path`` comme du CODE ?"""
    return any(
        isinstance(node, ast.Name) and node.id == "is_public_asset_path"
        for node in ast.walk(tree)
    )


def _guards() -> dict[str, tuple[bool, bool]]:
    """``chemin → (lit public_paths, appelle l'helper)`` sur ``examples/``."""
    out: dict[str, tuple[bool, bool]] = {}
    for source in parsed_sources(REPO_ROOT / "examples", floor=EXAMPLES_FLOOR):
        if reads_public_paths(source.tree):
            rel = str(source.path.relative_to(REPO_ROOT))
            out[rel] = (True, calls_the_helper(source.tree))
    return out


def test_the_sweep_is_not_vacuous() -> None:
    """Plancher ancré sur la DÉCOUVERTE.

    La population est petite — **une** app monte une garde aujourd'hui —
    donc recompter les fichiers d'``examples/`` ne dirait rien : c'est
    le DÉTECTEUR qui peut se taire, en cessant de reconnaître la forme
    d'accès. S'il ne trouve plus aucun lecteur de ``public_paths``, la
    gate est verte pour n'avoir rien vu, et c'est ce vert-là qu'on
    refuse.
    """
    guards = _guards()
    assert guards, (
        "aucun module d'``examples/`` ne lit ``app.public_paths``. Soit "
        "la dernière garde a disparu — auquel cas cette gate n'a plus "
        "d'objet et doit être supprimée, pas laissée verte — soit "
        "``reads_public_paths`` a cessé de reconnaître la forme d'accès."
    )


def test_every_guard_uses_the_helper() -> None:
    flat = sorted(path for path, (_, helper) in _guards().items() if not helper)
    assert not flat, (
        "Ces gardes lisent ``app.public_paths`` sans appeler "
        "``is_public_asset_path`` :\n  " + "\n  ".join(flat)
        + "\n\n``public_paths`` contient ``/_bretzel/vendor/{filename}``, un "
        "MOTIF de route : une comparaison à plat le refuse toujours, la "
        "garde redirige les scripts tiers vers la page de connexion, et "
        "htmx ne charge jamais. Aucun POST ne part et rien n'est "
        "journalisé. ⚠️ Invisible tant que ``.bretzel/vendor/`` n'existe "
        "pas — donc ça ne se verra pas en revue, ni sur une machine "
        "neuve."
    )


def test_the_detector_still_bites() -> None:
    """Les deux versants, sur des sources FABRIQUÉES."""

    def read(src: str) -> bool:
        return reads_public_paths(ast.parse(src))

    def helped(src: str) -> bool:
        return calls_the_helper(ast.parse(src))

    # ── Versant ILLICITE : la garde fautive est vue ───────────────────
    faulty = "PUBLIC = {*app.public_paths}\nif p in PUBLIC: pass"
    assert read(faulty) and not helped(faulty)

    # ── Versant LICITE : la garde réparée passe ───────────────────────
    fixed = (
        "from bretzel.runtime import is_public_asset_path\n"
        "PUBLIC = {*app.public_paths}\n"
        "if p in PUBLIC or is_public_asset_path(p): pass"
    )
    assert read(fixed) and helped(fixed)

    # ── Versant LICITE, celui qui compte : la PROSE n'est pas du code ─
    # Ce fichier-ci parle des deux noms de bout en bout sans monter la
    # moindre garde. Un détecteur textuel le lirait comme un site, et
    # une gate qui rougit sur sa propre documentation finit désactivée.
    prose = '"""Voir app.public_paths et is_public_asset_path."""\nx = 1'
    assert not read(prose) and not helped(prose)
    prose2 = "# app.public_paths sans is_public_asset_path\ny = 2"
    assert not read(prose2) and not helped(prose2)

    # ── Et un autre attribut du même nom de fin ne trompe pas ────────
    assert not read("x = obj.paths\ny = public_paths_count")
