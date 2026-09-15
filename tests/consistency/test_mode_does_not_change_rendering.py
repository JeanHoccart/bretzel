"""Gate : le mode ne change pas ce qui est rendu.

Le principe
-----------

Un mode peut changer la vitesse, le bruit, la sécurité et la mise en
cache. **Jamais ce qui est rendu.** C'est la règle qui manquait : le seul
fork sur ``mode`` qui touchait le rendu était le pipeline CSS, et c'est
exactement lui qui a caché une safelist amputée pendant des mois — tout
allait bien en dev *parce que dev rendait par un autre chemin*.

Le pipeline CSS est désormais un réglage nommé (``css=``) que le shell
reçoit tel quel (``browser_css=``), au lieu de le déduire du mode. À
pipeline égal, les deux modes doivent donc produire le même document.

Ce que le test tolère
---------------------

Deux choses varient d'un rendu à l'autre **même à configuration
identique** — l'UUID de page et le contenu de l'enveloppe (jeton CSRF,
horodatage, signatures d'action). Elles sont normalisées, et le test
vérifie d'abord que cette normalisation suffit : si deux rendus de la
MÊME configuration ne deviennent pas identiques, la comparaison
inter-modes ne voudrait rien dire.

Reste légitimement différent : le cache-bust ``?h=`` sur les URLs
d'assets (axe cache, dev uniquement), normalisé lui aussi.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from bretzel import Bretzel, page, ui

#: Preuve de morsure : les deux modes rendus puis compares apres normalisation : le test EST
#: la mutation, il change le mode et exige l'egalite.
MUTATION_PROOF = "test_dev_and_prod_render_the_same_document"

_SECRET = "k" * 32


def _clic() -> None: ...


@page("/p")
def _demo_page() -> None:
    with ui.vstack():
        with ui.tabs(value="a", color="tomato"):
            ui.tab("a", label="A")
            ui.tab("b", label="B")
            with ui.tab_panel(tab="a"):
                ui.text("A")
        ui.button("clic", on_click=_clic)
        ui.input(placeholder="x")
        ui.empty_state("Rien", icon="inbox", color="success")
        with ui.dialog(title="d") as dlg:
            ui.text("x")
        ui.button("Ouvrir", on_click=dlg.open())


_VOLATILE = (
    (re.compile(r"\b[0-9a-f]{32}\b"), "<HEX32>"),      # uuid de page, jetons
    (re.compile(r"\b[0-9a-f]{16,}\b"), "<HEX>"),       # signatures
    # Cache-bust sur les URLs d'assets : présent en dev, absent en prod.
    # C'est l'axe CACHE, légitimement lié au préréglage — on le retire des
    # deux côtés plutôt que de le remplacer, puisque c'est sa présence même
    # qui diffère.
    (re.compile(r"\?h=[0-9a-f]+"), ""),
    (re.compile(r'"ts":\s*"?\d+"?'), '"ts":<TS>'),
    # Horodatage de rendu porté par chaque action signée. Il ne se voyait
    # pas tant que les deux rendus tombaient dans la même seconde — c'est
    # l'étalonnage qui l'a débusqué quand la compilation a écarté les deux
    # appels de trois secondes.
    (re.compile(r'data-bz-ts="\d+"'), 'data-bz-ts="<TS>"'),
)


def _normalise(html: str) -> str:
    for pattern, replacement in _VOLATILE:
        html = pattern.sub(replacement, html)
    return html


def _render(**kwargs: object) -> str:
    app = Bretzel(secret_key=_SECRET, **kwargs)  # type: ignore[arg-type]
    app.include(_demo_page)
    with TestClient(app) as client:
        return client.get("/p").text


@pytest.mark.parametrize("css", ["browser", "build"])
def test_same_config_renders_identically_once_normalised(css: str) -> None:
    # Étalonnage : sans ça, un échec inter-modes pourrait n'être que du
    # bruit par-rendu.
    first = _normalise(_render(mode="dev", css=css, debug=False))
    second = _normalise(_render(mode="dev", css=css, debug=False))
    assert first == second, (
        "Deux rendus de la MÊME configuration diffèrent après "
        "normalisation : il y a une nouvelle source de variation "
        "par-rendu à ajouter à _VOLATILE."
    )


@pytest.mark.parametrize("css", ["browser", "build"])
def test_dev_and_prod_render_the_same_document(css: str) -> None:
    # ``debug=False`` des deux côtés : on isole l'axe testé (les
    # diagnostics changent la lisibilité des IDs, ce qui est leur rôle).
    dev = _normalise(_render(mode="dev", css=css, debug=False))
    prod = _normalise(_render(mode="prod", css=css, debug=False))
    assert dev == prod, (
        f"Le mode change le document rendu (css={css!r}). Un mode peut "
        "changer la vitesse, le bruit, la sécurité, la mise en cache — "
        "jamais le rendu. Un fork de rendu sur le mode est exactement ce "
        "qui a rendu invisible une safelist amputée pendant des mois."
    )
