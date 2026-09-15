"""Gate : tout ``app.<x>`` *utilisé* existe sur ``Bretzel``.

Le défaut qu'elle ferme
-----------------------
Deux commits de V3 ont libéré les décorateurs — ``afa27bc3`` (« page /
layout / error libres + ``app.include()`` ») et ``86efe195``
(« refreshable / subscribe / publish sans ``app`` »). Le déménagement
était volontaire et réussi. Ce qui n'a pas suivi, mesuré le 2026-08-15 :

- **31 des 40 ``tests/probes/bench_*.py`` ne s'importaient plus**, tous
  sur ``AttributeError: 'Bretzel' object has no attribute 'page' /
  'layout' / 'refreshable'``. Neuf seulement étaient vivants. Le harnais
  de vérification visuelle du dépôt était mort aux trois quarts et rien
  ne le disait : ces fichiers ne suivent pas le motif ``test_*.py``, donc
  pytest ne les collecte jamais.
- ~60 docstrings et fragments de doc enseignaient ``@app.page(...)``.
- Le playground **affichait** ``@app.page("/users/{user_id}",
  title="User")`` comme extrait à copier, dans la doc vivante.

Un déménagement d'API ne laisse pas de trace compilable : ``@app.page``
est une syntaxe parfaitement valide qui échoue seulement à l'exécution,
et seulement si quelqu'un exécute.

Deux modes, parce qu'il y a deux natures d'écriture
-----------------------------------------------------
1. **Le code** — balayé à l'AST : un accès d'attribut sur un nom
   littéralement appelé ``app``. Ça ignore chaînes et commentaires par
   construction, donc ``ProvideInfo(..., "app.core.db")`` (un chemin de
   module dans la démo de carte d'app) ne fait pas de bruit. Ça attrape
   la forme appel, ``shell = app.layout(shell)``, que la seule lecture
   des décorateurs raterait.
2. **La prose** — ``@app.<x>`` en **début de ligne** uniquement. Un
   décorateur montré en exemple est toujours en début de ligne ; une
   mention historique (« annonçait ``@app.subscribe`` jusqu'au … ») est
   toujours inline, au milieu d'une phrase. La distinction est mécanique,
   donc la doc garde le droit de nommer ce qui a été supprimé — sans quoi
   cette docstring-ci serait interdite par sa propre gate.

Sa jumelle ``test_probe_benches_still_import`` attrape la même classe par
l'autre bout : elle exécute vraiment les benchs. Les deux servent — celle
-ci nomme le coupable, l'autre attrape ce qu'on n'a pas su nommer.

Ce qu'elle ne peut PAS attraper
--------------------------------
Un ``getattr(app, name)`` dynamique, et une méthode qui existe mais ne
fait plus ce que la phrase autour en dit. Elle vérifie l'existence du
nom, pas la véracité de la prose.
"""

from __future__ import annotations

import ast
import re
from functools import lru_cache
from pathlib import Path

import pytest

from bretzel import Bretzel

_ROOT = Path(__file__).resolve().parents[2]
_SCANNED = ("bretzel", "tests", "examples", ".claude")

#: Un décorateur montré en exemple : ``@app.x`` en tête de ligne (le
#: préfixe absorbe l'indentation d'un bloc de code et les ``>>> `` d'un
#: doctest). Une mention inline reste permise.
_DECORATOR_AT_LINE_START = re.compile(r"^[ \t>]*@app\.([a-z_]+)", re.MULTILINE)

#: Une instance : ``config`` / ``fastapi`` sont posés dans ``__init__``,
#: donc absents de la CLASSE. Tester la classe rendait la gate fausse sur
#: des attributs parfaitement réels.
_APP = Bretzel(secret_key="g" * 32, mode="dev")


#: Les worktrees git que l'outillage ouvre sous ``.claude/worktrees/``.
#:
#: Ce sont des COPIES COMPLÈTES du dépôt, ``archive/V1/`` compris — donc
#: le balayage y retrouvait la V1, que la racine n'a jamais scannée, et
#: la gate rougissait sur ``app.api`` / ``app.engine`` / ``app.router``…
#: Mesuré le 2026-09-05 : 7 rouges, aucun fichier fautif dans le dépôt,
#: la seule cause étant qu'une session parallèle avait ouvert un
#: worktree. Une gate qui rougit parce qu'un collègue travaille à côté
#: est une gate qu'on apprend à ignorer.
_WORKTREES = ".claude/worktrees/"


def _is_in_a_worktree(path: Path) -> bool:
    """Le chemin vit-il dans une copie de travail imbriquée ?"""
    return _WORKTREES in path.as_posix()


@lru_cache(maxsize=1)
def _files() -> tuple[Path, ...]:
    out = []
    for root in _SCANNED:
        for path in (_ROOT / root).rglob("*"):
            if path.suffix not in (".py", ".md"):
                continue
            if "__pycache__" in str(path) or _is_in_a_worktree(path):
                continue
            out.append(path)
    return tuple(out)


def _app_is_a_bretzel(tree: ast.Module) -> bool:
    """``app`` désigne-t-il bien une :class:`Bretzel` dans ce module ?

    Sans ce filtre, ``tests/unit/server/middleware/test_csrf.py`` faisait
    rougir la gate sur ``app.add_middleware`` — où ``app`` est une
    ``Starlette`` montée à la main pour tester un middleware isolément.
    Un faux positif de gate coûte la confiance qu'on lui accorde, donc on
    ne devine pas : on exige de VOIR l'affectation ``app = Bretzel(...)``.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(t, ast.Name) and t.id == "app" for t in node.targets
        ):
            continue
        call = node.value
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name):
            return call.func.id == "Bretzel"
        return False
    return False


@lru_cache(maxsize=1)
def _usages() -> dict[str, tuple[str, ...]]:
    """``{attribut: (fichiers, …)}``, les deux modes fusionnés."""
    found: dict[str, set[str]] = {}
    unreadable: list[str] = []

    def note(name: str, path: Path) -> None:
        found.setdefault(name, set()).add(str(path.relative_to(_ROOT)))

    # ⚠️ Ce balayage ne peut PAS passer par ``_discovery.parsed_sources`` :
    # il lit aussi les ``.md`` (la doc enseigne ``@app.page`` autant que le
    # code), et sur QUATRE racines. Il refait donc la lecture — mais avec
    # le même contrat, qui est ce qui compte : ``utf-8-sig``, et un
    # illisible REMONTÉ plutôt que sauté.
    for path in _files():
        try:
            text = path.read_text(encoding="utf-8-sig")
            tree = ast.parse(text) if path.suffix == ".py" else None
        except (UnicodeDecodeError, OSError, SyntaxError) as exc:
            unreadable.append(f"{path.relative_to(_ROOT)} ({type(exc).__name__})")
            continue

        for name in set(_DECORATOR_AT_LINE_START.findall(text)):
            note(name, path)

        if tree is not None:
            if not _app_is_a_bretzel(tree):
                continue
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "app"
                ):
                    note(node.attr, path)

    assert not unreadable, (
        f"Fichiers illisibles ou non-parsables, donc HORS du balayage : "
        f"{unreadable}. Un saut silencieux vaut une gate vacuous."
    )
    return {name: tuple(sorted(paths)) for name, paths in found.items()}


@pytest.mark.parametrize("attr", sorted(_usages()))
def test_used_app_attribute_exists(attr: str) -> None:
    sites = _usages()[attr]
    assert hasattr(_APP, attr), (
        f"``app.{attr}`` est utilisé dans {len(sites)} fichier(s) — "
        f"{sites[:4]}{' …' if len(sites) > 4 else ''} — mais une instance "
        f"de ``Bretzel`` n'a pas cet attribut. Soit c'est une API déménagée "
        f"dont la doc n'a pas suivi (cas de ``page`` / ``layout`` / "
        f"``refreshable``, libérés en afa27bc3 et 86efe195, qui ont laissé "
        f"31 benchs morts pendant des mois), soit c'est du code à corriger. "
        f"Pour une mention HISTORIQUE en doc, écris-la inline dans une "
        f"phrase plutôt qu'en tête de ligne."
    )


def test_sweep_is_not_vacuous() -> None:
    """Plancher : le balayage lit de vrais fichiers et voit les deux modes.

    Ancré sur la DÉCOUVERTE. Si la regex cessait de matcher, ou si le
    filtre AST tombait à côté, la paramétrisation ne produirait aucun cas
    et la gate serait verte sans avoir rien lu — très exactement la panne
    qu'elle est censée détecter, appliquée à elle-même.
    """
    files = _files()
    assert len(files) >= 300, f"Seulement {len(files)} fichiers balayés."

    usages = _usages()
    assert len(usages) >= 5, (
        f"Seulement {len(usages)} attributs ``app.<x>`` distincts trouvés — "
        f"la découverte est probablement cassée."
    )
    # ``include`` est l'idiom central (montage des features) et ``run``
    # le lanceur : les deux se lisent à l'AST dans des dizaines de
    # fichiers. Leur absence signifierait que le mode 1 ne voit rien.
    for expected in ("include", "run"):
        assert expected in usages, (
            f"``app.{expected}`` n'est plus vu — le mode AST est cassé."
        )
    # Et un attribut posé dans ``__init__``, pour verrouiller le fait
    # qu'on teste bien une INSTANCE et pas la classe.
    assert hasattr(_APP, "config") and not hasattr(Bretzel, "config"), (
        "``config`` doit être un attribut d'instance : c'est ce qui rend "
        "obligatoire de tester une instance. Si ça change, relis la gate."
    )


def test_the_detector_still_bites() -> None:
    """Mutation : un décorateur ``@app.x`` est encore reconnu.

    La gate vérifie que l'attribut décoré existe VRAIMENT sur
    ``Bretzel``. Si la regex cessait de matcher, la doc pourrait
    enseigner un décorateur inexistant sans que rien ne rougisse.
    """
    assert _DECORATOR_AT_LINE_START.match("@app.page").group(1) == "page"
    assert _DECORATOR_AT_LINE_START.match("    @app.layout").group(1) == "layout"
    assert not _DECORATOR_AT_LINE_START.match("x = @app.page"), "faux positif"


def test_the_sweep_ignores_nested_worktrees() -> None:
    """L'exclusion ne doit pas disparaître en silence.

    Sans elle, la gate lit une copie complète du dépôt — ``archive/V1``
    compris — et rougit sur du code que personne n'a écrit aujourd'hui.
    Le symptôme est trompeur : il désigne des fichiers réels, avec des
    noms d'attributs réels, et rien n'indique qu'ils vivent dans le
    worktree d'une autre session.
    """
    assert not [p for p in _files() if _is_in_a_worktree(p)], (
        "le balayage descend dans .claude/worktrees/ : la gate va rougir "
        "dès qu'une session parallèle en ouvre un."
    )
    # Le détecteur mord dans les deux sens.
    assert _is_in_a_worktree(_ROOT / ".claude/worktrees/x/archive/V1/a.py")
    assert not _is_in_a_worktree(_ROOT / "bretzel/server/app.py")
