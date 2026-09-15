"""Gate G3 — la décision « cette valeur vient-elle du serveur ? » a UN
seul dialecte : ``Component._value_server_backed``.

Le mécanisme est déjà gardé par le comportement
(``test_serversync_gating`` + ``test_server_sync_completeness`` : littéral
→ pas de marker, serveur → marker, binding → pas de marker). Ce qu'aucune
gate ne tenait, c'est **par quel chemin** la décision est prise — et
c'est précisément la cause mécanique des 8 oublis de ``_serverSync`` :
la décision était re-tapée dans 5 dialectes divergents pour 12
call-sites, chacun avec son trou (cf. le docstring de
``_value_server_backed``).

Le helper a été écrit pour clore ça. Sauf que 7 call-sites ne l'ont
jamais adopté (audit 2026-07-18, F17 les 4 overlays / F25
date_range_picker / F49 calendar / F51 date_picker) — ils gardaient le
``getattr(raw, "field_name", None) is not None`` inline. Les gates
comportementales ne les voyaient pas : sur un scalaire, le dialecte
inline et le helper répondent pareil. La divergence est **latente**, et
elle mord dès que la prop tient une liste : ``_value_server_backed``
gère ``[state.debut, state.fin]`` (son branchement « case 3 »), pas
l'inline — ce qui rendait la dérive vivante sur DateRangePicker, dont
la valeur EST une liste de 2 éléments.

D'où une gate de **forme**, pas de comportement : une gate
comportementale ne peut pas distinguer deux dialectes qui coïncident sur
le cas testé. C'est l'exception qui confirme la règle « teste le
symptôme » — ici le symptôme n'apparaît qu'au call-site suivant, celui
que personne n'a encore écrit.

Deux vérifications, complémentaires :

1. **Adoption** — un module qui appelle ``server_sync_marker`` calcule sa
   décision via ``self._value_server_backed`` quelque part. Attrape le
   module qui n'a jamais adopté le helper.
2. **Exclusivité** — plus aucun module de composant hors ``base/`` ne
   teste ``getattr(x, "field_name", …) is not None``, la forme booléenne
   du dialecte. Attrape le module qui appelle le helper d'un côté et
   re-tape l'inline de l'autre. (Lire ``field_name`` pour s'en servir
   comme *nom* reste légitime : ``form_field`` l'utilise pour retrouver
   l'erreur du champ chez son owner — ce n'est pas la même question.)

⚠️ Volontairement PAS de vérification « l'expression ``enabled=`` est
littéralement un appel au helper » : plusieurs composants calculent le
flag dans ``render()`` et le passent en **argument** à un builder
module-level (``tabs``, ``select``, ``slider``, ``pagination``,
``accordion``, ``combobox``), ce qu'aucune analyse AST locale ne peut
suivre. Une gate qui les rougirait serait désactivée dans la semaine.
Les deux règles ci-dessus n'ont aucun faux positif et ferment quand
même la porte : il n'existe plus d'autre chemin pour prendre la
décision.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from tests.consistency._discovery import parsed_sources

_COMPONENTS_DIR = pathlib.Path("bretzel/components").resolve()
_BASE_DIR = _COMPONENTS_DIR / "base"
_HELPER = "_value_server_backed"


#: 262 modules hors ``base/`` le 2026-08-19 ; le plancher laisse de la
#: marge pour une réorganisation sans laisser passer un balayage mort.
_COMPONENTS_FLOOR = 200


def _component_modules() -> list[pathlib.Path]:
    """Tout module composant hors ``base/`` (le socle POSSÈDE le dialecte)."""
    return sorted(
        s.path for s in parsed_sources(_COMPONENTS_DIR, floor=_COMPONENTS_FLOOR)
        if _BASE_DIR not in s.path.parents and s.path.parent != _BASE_DIR
    )


def _mentions_helper(node: ast.AST) -> bool:
    return any(
        isinstance(n, ast.Attribute) and n.attr == _HELPER
        for n in ast.walk(node)
    )


_MODULES = _component_modules()
_IDS = [str(p.relative_to(_COMPONENTS_DIR)) for p in _MODULES]


@pytest.mark.parametrize("path", _MODULES, ids=_IDS)
def test_server_sync_marker_module_adopts_the_helper(path: pathlib.Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))

    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "server_sync_marker"
    ]
    if not calls:
        pytest.skip("module sans server_sync_marker")

    # ``_serverSync`` porte DEUX catégories depuis le 2026-08-03 :
    #
    #   - la clé de VALEUR — conditionnelle, « le serveur en est-il
    #     propriétaire ? », et c'est CETTE décision que le helper unifie ;
    #   - la CONFIG server-owned (``_total``, ``_min``, ``_delay``…) —
    #     inconditionnelle, le client ne l'écrit jamais, donc il n'y a
    #     aucune décision à prendre et aucun helper à appeler.
    #
    # Un module qui ne re-sème QUE de la config (Tooltip et son ``_delay``)
    # n'a donc rien à décider. Exiger le helper de lui reviendrait à exiger
    # un test dont la réponse ne change rien — et pousserait à inventer une
    # fausse notion de « delay server-backed ».
    #
    # Convention vérifiée : aucune ``scope_keys`` déclarée ne commence par
    # ``_``, donc le préfixe partitionne proprement les deux catégories.
    def _only_config(call: ast.Call) -> bool:
        literals = [
            a.value for a in call.args
            if isinstance(a, ast.Constant) and isinstance(a.value, str)
        ]
        # Pas que des littéraux (clé calculée, ``*keys``) → on ne peut pas
        # conclure : on exige le helper, c'est le côté prudent.
        if len(literals) != len(call.args):
            return False
        return bool(literals) and all(k.startswith("_") for k in literals)

    if all(_only_config(c) for c in calls):
        pytest.skip("ne re-sème que de la config server-owned : rien à décider")

    assert _mentions_helper(tree), (
        f"{path.relative_to(_COMPONENTS_DIR)} émet `_serverSync` sans jamais "
        f"appeler `self.{_HELPER}()` — il prend donc la décision "
        f"« serveur ou pas » par un chemin à lui.\n\n"
        f"Le helper est le dialecte unique : il couvre les 3 cas, dont "
        f"`[state.a, state.b]` (une liste dont un ÉLÉMENT porte le stamp), "
        f"qu'une variante inline rate en silence."
    )


@pytest.mark.parametrize("path", _MODULES, ids=_IDS)
def test_no_inline_field_name_boolean_test(path: pathlib.Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        # La forme du dialecte : ``getattr(x, "field_name", …) is not None``
        # (ou ``is None``). Lire ``field_name`` pour s'en servir comme nom
        # n'est pas visé.
        if not isinstance(node, ast.Compare):
            continue
        if not any(isinstance(op, (ast.Is, ast.IsNot)) for op in node.ops):
            continue
        left = node.left
        if not (isinstance(left, ast.Call)
                and isinstance(left.func, ast.Name)
                and left.func.id == "getattr"
                and len(left.args) >= 2
                and isinstance(left.args[1], ast.Constant)
                and left.args[1].value == "field_name"):
            continue
        offenders.append(node.lineno)

    assert not offenders, (
        f"{path.relative_to(_COMPONENTS_DIR)} lignes {offenders} : test "
        f"booléen inline sur `field_name` — c'est le dialecte que "
        f"`Component.{_HELPER}` remplace. Appelle le helper (il couvre en "
        f"plus le cas liste `[state.a, state.b]`)."
    )


def test_the_detector_still_bites() -> None:
    """Mutation : l'appel au helper de dialecte unique est reconnu.

    Le dialecte ``_value_server_backed`` a remplacé cinq orthographes
    concurrentes ; la gate vérifie qui l'adopte. Si le détecteur cessait
    de matcher, elle verrait zéro adoptant et n'aurait plus rien à dire.
    """
    fautif = ast.parse("sync = self._value_server_backed('value')")
    assert _mentions_helper(fautif), "l'appel au helper devrait être vu"

    licite = ast.parse("sync = value_server_backed_lookalike('value')")
    assert not _mentions_helper(licite), "un homonyme nu n'est pas l'appel — faux positif"
