"""Gate : un composant ne lit JAMAIS un thème sans le résoudre.

``cls.THEME`` et les constantes ``<X>_THEME`` des modules sont les dicts
**livrés**. Les lire directement au render contourne
``Theme(components={…})`` : l'override de l'app est ignoré, en silence.
La seule lecture correcte est ``self._resolved_theme()`` — ou
``self._resolved_theme("<autre>", OTHER_THEME)`` pour le thème d'un
autre composant.

Pourquoi cette gate (audit 2026-07-15). Le fix du merge (``a948a2a`` —
avant lui un override faisait passer un Button de 25 classes à 1) était
**incomplet** : trois sites contournaient encore le résolveur, et aucun
test ne le voyait.

- ``badge.py`` lisait ``self.THEME["sizes"]`` pour la taille d'icône →
  un override de la table ``sizes`` du badge n'atteignait pas l'icône.
- ``combobox.py`` / ``select.py`` composent leurs pills depuis
  ``BADGE_THEME`` (ils rendent les pills dans un template ``bz-for``
  client, ils ne peuvent donc pas instancier de vrais ``ui.badge``). Le
  docstring du helper promettait « a Badge theme tweak propagates
  everywhere automatically » — c'était faux pour un tweak **utilisateur**.
- ``markdown.py`` lisait ``CODE_THEME`` pour ses blocs fencés → un
  override de ``code`` atteignait ``ui.code`` mais pas le markdown.

Aucun n'était détectable autrement : le rendu est correct, seul
l'override est muet.

Exemption unique et nominative : ``_resolved_theme`` lui-même, qui EST
le résolveur. ``theme.py`` (les fichiers de définition) est hors scope —
y déclarer sa propre constante est le but.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from tests.consistency._discovery import parsed_sources

_COMPONENTS = pathlib.Path(__file__).resolve().parents[2] / "bretzel" / "components"

#: 272 fichiers sous bretzel/components le 2026-08-19.
_COMPONENTS_FLOOR = 200

# (fichier, fonction) autorisés à lire un thème brut.
_ALLOWED: frozenset[tuple[str, str]] = frozenset({
    ("component.py", "_resolved_theme"),
})


def _py_files() -> list[pathlib.Path]:
    return [
        s.path
        for s in parsed_sources(_COMPONENTS, floor=_COMPONENTS_FLOOR)
        if s.path.name != "theme.py"
    ]


def _enclosing(tree: ast.AST, target: ast.AST) -> str:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                if child is target:
                    return node.name
    return ""


def _offenders(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: list[str] = []

    # 1. ``self.THEME`` / ``type(self).THEME`` lu dans un corps de méthode.
    #    (La déclaration ``THEME: ClassVar = X_THEME`` au niveau classe
    #    n'est pas dans une FunctionDef → jamais flaggée.)
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if (path.name, fn.name) in _ALLOWED:
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.Attribute) and node.attr == "THEME":
                out.append(f"{path.name}:{node.lineno} — .THEME dans {fn.name}()")

    # 2. Lecture d'une constante ``<X>_THEME`` de module par subscript
    #    ou ``.get`` — c'est le thème d'un AUTRE composant, non résolu.
    for node in ast.walk(tree):
        target = None
        if isinstance(node, ast.Subscript) or (isinstance(node, ast.Attribute) and node.attr == "get"):
            target = node.value
        if isinstance(target, ast.Name) and target.id.endswith("_THEME"):
            fn_name = _enclosing(tree, node)
            if (path.name, fn_name) in _ALLOWED:
                continue
            out.append(f"{path.name}:{node.lineno} — {target.id} lu en direct")
    return out


@pytest.mark.parametrize("path", _py_files(), ids=lambda p: p.name)
def test_theme_is_never_read_unresolved(path: pathlib.Path) -> None:
    offenders = _offenders(path)
    assert not offenders, (
        f"Thème lu sans résolution : {offenders}. Utilise "
        f"`self._resolved_theme()` (ou `self._resolved_theme(\"<clé>\", "
        f"OTHER_THEME)` pour le thème d'un autre composant) — sinon un "
        f"`Theme(components={{…}})` de l'app est ignoré EN SILENCE : le "
        f"rendu reste correct, seul l'override est muet."
    )


def test_detector_catches_the_pattern() -> None:
    """Auto-test : le détecteur voit-il vraiment ce qu'il prétend ?"""
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        probe = pathlib.Path(d) / "probe.py"
        probe.write_text(
            "class C:\n"
            "    THEME = SOME_THEME            # déclaration : OK\n"
            "    def render(self):\n"
            "        a = self.THEME['sizes']   # ← doit être flaggé\n"
            "        b = BADGE_THEME['slots']  # ← doit être flaggé\n"
            "        c = self._resolved_theme()  # OK\n",
            encoding="utf-8",
        )
        found = _offenders(probe)
    assert len(found) == 2, (
        f"le détecteur doit flagger `self.THEME[...]` ET `BADGE_THEME[...]`, "
        f"et laisser passer la déclaration de classe — trouvé : {found}"
    )


def test_gate_is_not_vacuous() -> None:
    assert len(_py_files()) >= 50
