"""Un ``disabled=<ClientBinding>` doit désactiver les contrôles VISIBLES
des deux date pickers — pas décorer un ``<div>``.

Le bug (audit 2026-07-18, F01/F02) : ``disabled`` est déclaré dans
``BINDABLE_PROPS``, donc contractuellement réactif — mais le binding
atterrissait en ``bz-attr:disabled`` sur le ``<div>`` wrapper, où
l'attribut ne fait RIEN. Passer le binding à ``True`` au runtime laissait
le champ éditable, le bouton calendrier cliquable et le ``×`` actif. Seul
le ``<bz-calendar>`` caché dans le popover réagissait.

Pourquoi un test navigateur alors qu'une gate statique existe déjà
(``tests/consistency/test_binding_lands_on_carrier.py``) : la gate prouve
que la directive est posée sur un tag légal. Elle ne prouve pas que le
runtime, en flippant le signal, désactive réellement les éléments. C'est
la moitié que le SSR ne peut pas montrer — et c'est celle que
l'utilisateur voit.

Le probe n'a pas besoin d'une page playground dédiée : il rend les deux
pickers avec un binding côté Python, injecte le HTML dans une page déjà
hydratée, puis lance ``$bz._scan`` — la même passe que le bridge exécute
après un swap.

Lourd (uvicorn + Chromium) — à lancer explicitement ::

    py -m pytest tests/runtime_js/test_date_picker_disabled_binding.py -q -m browser
"""

from __future__ import annotations

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from bretzel.state.scopes.client import ClientBinding
from tests.audit.harness import audit_server, browser_page

_CLASS, _KEY, _FIELD = "probe", "default", "locked"
_PATH = f"{_CLASS}.{_KEY}.{_FIELD}"


def _ssr(component_cls) -> str:
    """Le HTML SSR du picker avec ``disabled`` bindé (valeur initiale False)."""
    binding = ClientBinding(
        class_name=_CLASS, instance_key=_KEY, field_name=_FIELD, value=False,
    )
    with render_isolated():
        return serialize(component_cls(disabled=binding).render())


@pytest.fixture(scope="module")
def base_url():
    with audit_server() as url:
        yield url


@pytest.mark.parametrize(
    "import_path, label",
    [
        ("bretzel.components.inputs.date_picker:DatePicker", "date_picker"),
        ("bretzel.components.inputs.date_range_picker:DateRangePicker",
         "date_range_picker"),
    ],
)
def test_bound_disabled_reaches_the_visible_controls(
    base_url: str, import_path: str, label: str,
) -> None:
    import importlib

    mod_name, cls_name = import_path.split(":")
    html = _ssr(getattr(importlib.import_module(mod_name), cls_name))

    with browser_page(base_url, "/date_picker") as page:
        page.wait_for_function("() => !!window.$bz", timeout=5000)
        result = page.evaluate(
            """([html, path]) => {
                const host = document.createElement('div');
                host.id = 'bz-probe-host';
                host.innerHTML = html;
                document.body.appendChild(host);
                // Seed the bound field to false, then hydrate the subtree
                // exactly like the bridge does after a swap.
                const [cls, key, field] = path.split('.');
                $bz.state[cls][key][field] = false;
                $bz._scan(host);

                // Scope : la BARRE VISIBLE du picker (``bz-ref=bztrigger``,
                // le frame champ + × + trigger). Les ~40 boutons-jours du
                // <bz-calendar> dans le popover relèvent du contrat de
                // Calendar, pas de celui-ci.
                const frame = host.querySelector('[bz-ref=bztrigger]');
                const controls = () => ({
                    fields: [...frame.querySelectorAll('input[type=text]')]
                        .map(el => el.disabled),
                    buttons: [...frame.querySelectorAll('button')]
                        .map(el => el.disabled),
                });
                const before = controls();
                $bz.state[cls][key][field] = true;
                return new Promise(resolve => requestAnimationFrame(() =>
                    requestAnimationFrame(() =>
                        resolve({before, after: controls()}))));
            }""",
            [html, _PATH],
        )

    before, after = result["before"], result["after"]
    assert before["fields"] and before["buttons"], (
        f"{label} : le probe n'a trouvé aucun contrôle visible — "
        f"le HTML injecté n'a pas la forme attendue ({before})"
    )
    assert not any(before["fields"]) and not any(before["buttons"]), (
        f"{label} : les contrôles sont déjà disabled AVANT le flip "
        f"(binding initial False) — {before}"
    )
    assert all(after["fields"]), (
        f"{label} : le champ éditable reste actif après "
        f"`$bz.state.{_PATH} = true` — le binding n'atteint pas le carrier "
        f"(bug F01/F02). fields={after['fields']}"
    )
    assert all(after["buttons"]), (
        f"{label} : le trigger calendrier / le × restent actifs après "
        f"`$bz.state.{_PATH} = true`. buttons={after['buttons']}"
    )
