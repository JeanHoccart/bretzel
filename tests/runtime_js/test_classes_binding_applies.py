"""Un ``classes=<ClientBinding>`` ajoute/retire vraiment les classes au
runtime — et laisse le thème intact.

La gate ``tests/consistency/test_reactive_classes_universal.py`` prouve
que la directive est émise sur les 55 composants. Elle ne prouve pas que
le runtime l'honore : c'est précisément l'erreur du mécanisme précédent
(``:class="…"``, syntaxe Alpine émise pendant des mois sans qu'aucun
runtime V3 ne la lise). Ce probe ferme la boucle côté navigateur.

Lourd (uvicorn + Chromium) — à lancer explicitement ::

    py -m pytest tests/runtime_js/test_classes_binding_applies.py -q -m browser
"""

from __future__ import annotations

import pytest

from bretzel.components.actions.button import Button
from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from bretzel.state.scopes.client import ClientBinding
from tests.audit.harness import audit_server, browser_page

_CLASS, _KEY, _FIELD = "probe", "default", "extra"


@pytest.fixture(scope="module")
def base_url():
    with audit_server() as url:
        yield url


def test_classes_binding_adds_and_removes_without_touching_the_theme(
    base_url: str,
) -> None:
    binding = ClientBinding(
        class_name=_CLASS, instance_key=_KEY, field_name=_FIELD, value="",
    )
    with render_isolated():
        html = serialize(Button("Save", classes=binding).render())

    with browser_page(base_url, "/button") as page:
        page.wait_for_function("() => !!window.$bz", timeout=5000)
        result = page.evaluate(
            """([html, cls, key, field]) => {
                const host = document.createElement('div');
                host.innerHTML = html;
                document.body.appendChild(host);
                $bz.state[cls][key][field] = '';
                $bz._scan(host);
                const btn = host.querySelector('button');
                const snap = () => [...btn.classList];
                const tick = () => new Promise(r =>
                    requestAnimationFrame(() => requestAnimationFrame(r)));
                return (async () => {
                    const before = snap();
                    $bz.state[cls][key][field] = 'ring-2 ring-offset-1';
                    await tick();
                    const added = snap();
                    $bz.state[cls][key][field] = '';
                    await tick();
                    return {before, added, removed: snap()};
                })();
            }""",
            [html, _CLASS, _KEY, _FIELD],
        )

    before, added, removed = (
        result["before"], result["added"], result["removed"],
    )
    # Le thème est là dès le départ et ne bouge jamais : c'est ce que
    # l'ancien ``:class`` détruisait (bouton rendu sans aucune classe).
    assert "rounded-field" in before, (
        f"la composition du thème manque avant même le flip : {before}"
    )
    assert "ring-2" not in before, f"classe du binding déjà là : {before}"
    assert "ring-2" in added and "ring-offset-1" in added, (
        f"le binding n'a pas ajouté ses classes au runtime : {added}"
    )
    assert "rounded-field" in added, (
        f"le binding a effacé la composition du thème : {added}"
    )
    assert "ring-2" not in removed and "rounded-field" in removed, (
        f"repasser le binding à vide doit retirer SES classes seulement : "
        f"{removed}"
    )
