"""Le magasin client part en JSON — vérifié dans un vrai navigateur.

``tests/consistency/test_client_store_travels_as_json.py`` garde la FORME
de l'encodage (la valeur passe par ``wireValue``) en trois secondes. Ce
test-ci ferme la boucle : il regarde ce que htmx met réellement dans le
corps de la requête, parce que c'est htmx — pas nous — qui décidait de
défaire un tableau.

Ce qu'il empêche de revenir, mesuré le 2026-08-19
--------------------------------------------------
``formDataFromObject`` fait ``obj[key].forEach(v => append(key, v))`` :

- ``["a","b"]`` partait en DEUX champs de même nom, et le serveur gardait
  le dernier — la liste arrivait comme ``"b"`` ;
- ``[]`` n'ajoutait **rien**, donc la clé était absente, et l'hydratation
  n'écrivant que les champs présents, **une liste client vidée ne pouvait
  plus jamais vider son champ serveur**.

La forme seule ne suffirait pas à le garder : le jour où htmx change sa
sérialisation, c'est ici que ça se verra, pas dans la regex.

Lourd (uvicorn + Chromium) — à lancer explicitement ::

    py -m pytest tests/runtime_js/test_client_store_travels_as_json.py -q -m browser
"""

from __future__ import annotations

import pytest

from tests.audit.harness import audit_server, browser_page

#: Un chemin de magasin fabriqué : la gate n'a pas besoin qu'une page
#: précise porte un état à liste, et ne devient donc pas fausse le jour où
#: cette page-là change.
_PATH = "_SondeMagasin.default"


@pytest.fixture(scope="module")
def base_url():
    with audit_server() as url:
        yield url


def test_composites_ship_as_json_and_scalars_ship_raw(base_url: str) -> None:
    with browser_page(base_url, "/button") as page:
        page.wait_for_function("() => !!window.$bz", timeout=5000)
        captured = page.evaluate(
            """(path) => {
                // Trois valeurs qui couvrent les trois cas : la liste
                // pleine que htmx éclatait, la liste VIDE qu'il faisait
                // disparaître, et un scalaire qui ne doit PAS être encodé.
                $bz._store.set(path + '.pleine', ['a', 'b']);
                $bz._store.set(path + '.vide', []);
                $bz._store.set(path + '.mot', 'texte');

                // On lit ce que le pont pose dans le corps, sans laisser
                // partir la requête : `preventDefault` sur configRequest
                // annule l'envoi (htmx 2.0.4, mesuré).
                let seen = null;
                const grab = (e) => {
                    seen = {};
                    for (const [k, v] of Object.entries(e.detail.parameters))
                        seen[k] = [typeof v, String(v)];
                    e.preventDefault();
                };
                document.body.addEventListener('htmx:configRequest', grab);
                const trigger = document.querySelector('[hx-post]');
                if (trigger) trigger.click();
                document.body.removeEventListener('htmx:configRequest', grab);
                return seen;
            }""",
            _PATH,
        )

    assert captured, (
        "aucun `htmx:configRequest` capturé — la page ne porte plus de "
        "déclencheur `hx-post`, donc ce test ne mesure rien."
    )
    pleine = captured.get(f"{_PATH}.pleine")
    vide = captured.get(f"{_PATH}.vide")
    mot = captured.get(f"{_PATH}.mot")

    assert pleine and pleine[0] == "string" and pleine[1] == '["a","b"]', (
        f"une liste pleine part en {pleine!r} au lieu d'une chaîne JSON : "
        f"htmx va l'éclater en deux champs de même nom, et le serveur ne "
        f"gardera que le dernier élément."
    )
    assert vide is not None, (
        "une liste VIDE a disparu du corps de la requête — c'est le bug : "
        "la clé absente ne peut pas vider le champ serveur, parce que "
        "l'hydratation n'écrit que ce qui est présent."
    )
    assert vide[1] == "[]", f"la liste vide part en {vide!r} au lieu de `[]`"
    assert mot and mot[1] == "texte", (
        f"un scalaire part en {mot!r} : l'encodage ne doit PAS le toucher, "
        f"sinon chaque champ texte gagne une paire de guillemets par "
        f"aller-retour."
    )
