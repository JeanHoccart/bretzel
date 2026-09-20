"""Gate : la population que `bretzel.lint` voit dans `tests/` est FIGÉE.

La jumelle de `test_lint_baseline_on_examples`, sur l'autre corpus — et le
corpus a une nature différente, qui décide de tout ce qui suit.

Pourquoi `tests/` n'est pas `examples/`
----------------------------------------

Dans `examples/`, une faute est une faute. Dans `tests/`, **la faute est
souvent le sujet** : on écrit `ui.pane(wrap=True)` sous
`pytest.raises(TypeError)` pour prouver que la prop est scellée, et
`Button(on_click=lambda: None)` sous `pytest.raises(HandlerError)` pour
prouver que le lambda est refusé. Un linter ne peut pas voir le `raises`
qui entoure l'appel — il voit l'appel.

Exiger zéro serait donc absurde ici. Les 23 entrées ci-dessous ont été
relues **une par une** le 2026-09-10, avec leur contexte, avant d'être
inscrites : chacune est du matériel de test délibéré. Une entrée sans
raison vérifiée serait juste une gate qu'on a fait taire.

Ce qui a été CORRIGÉ plutôt qu'inscrit
---------------------------------------

Deux constats ne sont pas dans la table, et c'est le point de cette gate.
`page-declared-in-a-function` — née le même jour — a trouvé une page
`/` MORTE dans `test_static_dir.py` et dans `test_protocol_compat_gate.py` :
déclarée dans le corps de la fabrique d'app, donc invisible à
`include(__name__)`, qui ne balaie que le premier niveau d'un module.
Vérifié avant/après : `GET /` rendait **404**, il rend **200** depuis
qu'elles sont passées à `app.include(home)`. Elles dormaient depuis le
2026-08-01 parce que ces suites ne visitent jamais cette page.

C'est la règle du fichier jumeau, appliquée : une occurrence NEUVE se
corrige, elle ne s'inscrit pas. Une baseline qui avale les vraies fautes
devient l'allowlist qu'elle imite.

Coût
----

Le balayage lit 745 fichiers en ~21 s (mesuré le 2026-09-10). Il est fait
**une fois**, dans le seul test qui en a besoin — le plancher, lui, ne
lit que la table.
"""

from __future__ import annotations

import collections
import pathlib

from bretzel.lint import run
from bretzel.lint.rules import STATIC

#: Pas de détecteur à rendre aveugle — cf.
#: ``test_a_prohibition_gate_is_mutation_tested``.
MUTATION_NOT_APPLICABLE = (
    "gèle un COUPLE (fichier, règle) → nombre mesuré par `bretzel.lint` "
    "; le détecteur est celui des règles, gardé par "
    "`test_lint_rules_are_not_vacuous`"
)

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TESTS = _ROOT / "tests"

#: ``(chemin, règle) → nombre``, mesuré et RELU le 2026-09-10.
_BASELINE: dict[tuple[str, str], int] = {
    # ── La faute est sous un `pytest.raises` : c'est la preuve du refus ──
    #
    # Le linter voit l'appel, jamais le `raises` qui l'entoure. Retirer
    # ces appels reviendrait à supprimer les tests qui garantissent que
    # le framework refuse ces formes.
    ("tests/unit/components/actions/button/test_button.py", "lambda-handler"): 1,
    ("tests/unit/components/base/test_component.py", "lambda-handler"): 1,
    ("tests/unit/components/layout/test_viewport_pane.py", "unknown-kwarg"): 1,
    # `unknown-kwarg` est la règle dont `test_examples_pass_real_kwargs`
    # exige ZÉRO, au motif qu'un kwarg mort n'a jamais de bonne raison
    # d'exister. C'est vrai d'une app ; ici l'appel est
    # `ui.pane(wrap=True)` sous `raises(TypeError, match="ne se replie
    # pas")`, et il garde le SCELLÉ. La seule occurrence du dépôt.
    #
    # ── Le vocabulaire de thème : deux raisons différentes ──────────────
    #
    # L'une est le test du refus lui-même (`crad` n'existe pas, c'est le
    # sujet). L'autre est un angle mort RÉEL de la règle, qui vaut d'être
    # nommé : `gauge` est un composant TIERS, donc absent du vocabulaire
    # dérivé de `ui.*`. Un thème tiers valide sera toujours signalé —
    # c'est la limite de `theme_vocabulary`, pas une faute du test.
    ("tests/consistency/test_theme_refuses_unknown_keys.py", "unknown-theme-vocabulary"): 2,
    ("tests/integration/test_a_third_party_component_can_be_themed.py", "unknown-theme-vocabulary"): 1,
    # ── L'état construit hors du bon contexte : le sujet des tests d'état ─
    #
    # Ces fichiers montent des registres à la main pour éprouver le cycle
    # (hydratation, diff, commit, types métier). Deux vont plus loin et
    # exercent DÉLIBÉRÉMENT le geste que la règle refuse — le corps
    # `async def` d'`test_an_async_only_backend_still_hydrates` est
    # documenté « le geste qui ne PEUT pas marcher ».
    ("tests/consistency/test_no_state_is_built_through_the_metaclass.py", "state-built-on-the-loop"): 1,
    ("tests/integration/server/test_an_async_only_backend_still_hydrates.py", "state-built-on-the-loop"): 1,
    ("tests/integration/test_an_async_zone_renders_on_both_paths.py", "state-built-on-the-loop"): 1,
    ("tests/unit/state/test_a_business_type_survives_the_store.py", "state-built-on-the-loop"): 1,
    ("tests/unit/state/test_a_commit_writes_in_one_window.py", "state-built-on-the-loop"): 1,
    ("tests/unit/state/test_snapshot_diff.py", "state-built-on-the-loop"): 2,
    # ── Le compteur partagé sans `merge="add"` ──────────────────────────
    #
    # La règle vise l'incrément perdu entre DEUX utilisateurs. Ces
    # quatre-là testent autre chose — l'aller-retour d'action, le
    # regroupement d'une rafale, le rendu d'une zone async — avec une
    # seule session, où le mode d'échec ne peut pas se produire. Le
    # compteur y est le décor le plus court pour observer un re-rendu.
    ("tests/integration/server/test_action_roundtrip.py", "undeclared-shared-counter"): 1,
    ("tests/integration/server/test_an_async_only_backend_still_hydrates.py", "undeclared-shared-counter"): 3,
    ("tests/integration/test_an_async_zone_renders_on_both_paths.py", "undeclared-shared-counter"): 1,
    ("tests/runtime_js/test_a_burst_of_mutations_is_one_refetch.py", "undeclared-shared-counter"): 1,
    # ── Deux crochets de sonde, pas du code d'app ───────────────────────
    #
    # `classes=f"bz-probe-{nom}"` n'est pas une classe Tailwind : c'est un
    # sélecteur que le test cherche ensuite dans le DOM. Rien à styler,
    # donc rien à clôturer en safelist — mais la règle ne peut pas
    # distinguer un préfixe maison d'un utilitaire.
    ("tests/runtime_js/test_a_burst_of_mutations_is_one_refetch.py", "assembled-tailwind-class"): 1,
    # `hx-post` écrit à la main dans un `attrs=` : le test construit
    # exprès le porteur brut pour vérifier qu'un changement relocalisé
    # l'atteint. C'est la famille que
    # `test_raw_htmx_stays_in_the_allowlist` gèle côté framework.
    ("tests/consistency/test_a_relocated_change_reaches_its_carrier.py", "hand-written-transport"): 3,
}


def _measured() -> dict[tuple[str, str], int]:
    report = run([_TESTS])
    assert report.files_scanned > 0, f"aucun fichier balayé sous {_TESTS}"
    return dict(
        collections.Counter(
            (f.path.resolve().relative_to(_ROOT).as_posix(), f.rule)
            for f in report.findings
        )
    )


def test_the_baseline_cites_only_known_rules() -> None:
    """Plancher : une entrée morte autorise ce qu'on ne mesure plus.

    Une règle renommée ou supprimée laisserait ici un couple qui ne
    correspond à rien — et la table continuerait de « couvrir » une
    population que personne ne compte.
    """
    known = set(STATIC)
    baselined = {rule for _, rule in _BASELINE}
    assert baselined <= known, (
        f"la baseline cite des règles inconnues : {sorted(baselined - known)}."
    )


def test_the_two_404_rules_stay_at_zero() -> None:
    """Les deux règles du 404 trompeur n'ont AUCUNE entrée, et c'est voulu.

    Une `@page` morte ou un `TestClient` hors lifespan ne peut pas être du
    matériel de test délibéré : contrairement à un `raises`, il n'y a rien
    à démontrer avec une page que personne ne récolte. Ce test est ce qui
    empêche d'inscrire dans la table, un jour de fatigue, les deux fautes
    que cette gate vient de faire corriger.
    """
    interdites = {"page-declared-in-a-function", "test-client-without-lifespan"}
    assert interdites <= set(STATIC), (
        f"règle(s) disparue(s) : {sorted(interdites - set(STATIC))} — ce test "
        f"serait vert sans rien garder."
    )
    inscrites = {rule for _, rule in _BASELINE} & interdites
    assert not inscrites, (
        f"{sorted(inscrites)} figure(nt) dans la baseline. Ces deux fautes se "
        f"CORRIGENT : passe la page à `app.include(<nom>)`, ou ouvre le client "
        f"en `with TestClient(app) as client:`. Les inscrire rendrait la gate "
        f"muette sur le mode d'échec pour lequel elle a été écrite."
    )


def test_the_population_has_not_moved() -> None:
    measured = _measured()
    added = {k: n for k, n in measured.items() if _BASELINE.get(k, 0) != n}
    removed = {k: n for k, n in _BASELINE.items() if measured.get(k, 0) != n}
    if not added and not removed:
        return

    def _fmt(entries: dict[tuple[str, str], int]) -> str:
        return "\n".join(
            f"      {path}  [{rule}] ×{n}"
            for (path, rule), n in sorted(entries.items())
        )

    raise AssertionError(
        "la population vue par `bretzel.lint` sous `tests/` a bougé.\n"
        f"  mesuré, absent ou différent de la baseline :\n{_fmt(added)}\n"
        f"  attendu par la baseline, plus mesuré ainsi :\n{_fmt(removed)}\n\n"
        "  Si c'est une occurrence NEUVE : lis le constat. Dans `tests/` la "
        "faute est souvent le SUJET (un `pytest.raises` autour de l'appel) — "
        "inscris-la alors ici AVEC sa raison, relue. Si c'en est une vraie, "
        "corrige-la.\n"
        "  Si tu en as retiré une : retire aussi son entrée, sinon la "
        "baseline autorise plus que la réalité."
    )
