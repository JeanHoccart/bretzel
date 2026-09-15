"""Gate : personne ne reconstruit un chemin client à la main.

``Component.path_of(binding)`` est LA façon d'obtenir le chemin client
d'un binding. Elle est polymorphe :

- ``ClientBinding`` → ``$bz.state.<Class>.<key>.<field>`` (préfixe ajouté) ;
- ``ClientExpression`` → l'expression verbatim, qui porte **déjà** son
  préfixe (``$bz.state.S.k.a || $bz.state.S.k.b``).

Écrire ``f"$bz.state.{b.serialize_path()}"`` à la main marche pour le
premier sous-type et **corrompt** le second : ``$bz.state.($bz.state.…``.
Le JS reste syntaxiquement valide → aucune erreur, juste un binding mort.

Audit 2026-07-15 : **30 f-strings** de cette forme vivaient dans
``components/``, dont ``forward_binding`` et ``_apply_bindable_carriers``
— les deux primitives que ``components.md`` vend comme LA solution
carrier. 29 étaient masquées par un crash amont ; **``tooltip.py`` ne
l'était pas** et émettait un chemin corrompu en production, pour
``ui.tooltip(text=expr)`` comme pour le kwarg universel ``tooltip=expr``
(donc sur n'importe quel composant).

⚠️ **Gate AST, pas regex.** Une regex flagge la docstring de ``path_of``
(qui montre le motif comme contre-exemple) ; l'AST ne voit qu'un
``ast.Constant``, jamais un ``ast.JoinedStr`` — le faux positif disparaît
sans exemption.

Cf. traps.md § « path_of — chemin client à source unique » et
[[project_consistency_gates]] (la classe de gate qui manquait :
« la primitive livrée est-elle adoptée à tous ses call-sites ? »).
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from tests.consistency._discovery import parsed_sources, source_of

_COMPONENTS = pathlib.Path(__file__).resolve().parents[2] / "bretzel" / "components"

#: 272 fichiers sous ``bretzel/components`` le 2026-08-19 ; le plancher
#: laisse de la marge pour une réorganisation sans laisser passer un
#: balayage mort.
_COMPONENTS_FLOOR = 200

# ``_bind_x_model`` construit la cible d'un ``bz-model`` — un chemin
# ASSIGNABLE (le runtime compile ``<expr> = $value``). Il ne peut pas
# passer par ``path_of`` : une expression n'est pas assignable, et le
# refus vit dans ``TWO_WAY_PROPS`` (rejet à la construction). Exemption
# nominative, pas un fichier entier.
_ALLOWED: frozenset[tuple[str, str]] = frozenset({
    ("component.py", "_bind_x_model"),
})


def _py_files() -> list[pathlib.Path]:
    return [s.path for s in parsed_sources(_COMPONENTS, floor=_COMPONENTS_FLOOR)]


def _enclosing_func(tree: ast.AST, target: ast.AST) -> str:
    """Nom de la fonction contenant ``target`` ('' si top-level)."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                if child is target:
                    return node.name
    return ""


def _offenders(tree: ast.AST, name: str = "") -> list[str]:
    """Le détecteur, sur un ARBRE — pas sur un chemin.

    Il prend l'arbre plutôt que le fichier pour que le test de mutation
    puisse lui donner une sonde fabriquée : le lecteur partagé
    (``source_of``) ne connaît que les fichiers du dépôt, et c'est très
    bien — mais un détecteur qui ne s'exerce que sur du réel ne se
    vérifie pas.
    """
    out: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.JoinedStr):
            continue
        if not any(
            isinstance(p, ast.Constant) and "$bz.state." in str(p.value)
            for p in node.values
        ):
            continue
        if (name, _enclosing_func(tree, node)) in _ALLOWED:
            continue
        out.append(f"{name}:{node.lineno}")
    return out


@pytest.mark.parametrize("path", _py_files(), ids=lambda p: p.name)
def test_no_handbuilt_client_path(path: pathlib.Path) -> None:
    offenders = _offenders(source_of(path).tree, path.name)
    assert not offenders, (
        f"Chemin client construit à la main dans {offenders} — utilise "
        f"`self.path_of(binding)` (ou `binding.binding_path()` dans une "
        f"fonction module-level). La forme f\"$bz.state.{{…}}\" corrompt "
        f"une ClientExpression en `$bz.state.($bz.state.…`, silencieusement."
    )


def test_gate_is_not_vacuous() -> None:
    # Un refactor qui déplacerait les composants ferait passer la gate à vide.
    files = _py_files()
    assert len(files) >= 50
    # Et le motif DOIT être détecté quand il existe : auto-test du détecteur.
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        probe = pathlib.Path(d) / "probe.py"
        probe.write_text(
            'x = f"$bz.state.{b.serialize_path()}"\n'
            'doc = "$bz.state.Class.key.field"  # Constant, pas JoinedStr\n',
            encoding="utf-8",
        )
        found = _offenders(ast.parse(probe.read_text(encoding='utf-8')))
    assert len(found) == 1, (
        f"le détecteur doit flagger le f-string ET ignorer la string "
        f"littérale (docstring / exemple) — trouvé : {found}"
    )
