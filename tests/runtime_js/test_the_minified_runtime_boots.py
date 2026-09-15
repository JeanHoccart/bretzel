r"""Le bundle que la PROD sert démarre — vérifié en l'exécutant.

Ce que cette gate ferme
-----------------------

``runtime.min.js`` est produit par un scanner maison
(:mod:`bretzel.runtime._minify`) qui retire commentaires et
indentation. Il doit distinguer un ``//`` de commentaire d'un ``//``
dans une chaîne, un gabarit, ou une **expression régulière littérale**
— le bundle en porte 43, dont ``.replace(/\//g, …)``. Une erreur de
scanner ne se voit pas à la relecture : elle produit un fichier qui
*ressemble* à du JS et qui casse au chargement.

Et elle ne casserait **qu'en production** : le mode dev sert l'autre
fichier. Le seul instrument qui peut trancher est donc un navigateur
qui exécute vraiment le bundle réduit, servi par un vrai serveur en
mode prod.

Trois affirmations, dans l'ordre où elles comptent
---------------------------------------------------

1. la prod sert bien le fichier réduit (sinon le reste ne prouve rien) ;
2. le bundle s'analyse et le runtime s'installe — aucune erreur de page ;
3. une directive **évalue** : le runtime n'est pas seulement chargé, il
   marche. C'est ce qu'un simple « ``window.$bz`` existe » raterait,
   parce que le scanner peut très bien n'avoir cassé qu'un littéral
   régulier au fond d'un module.
"""

from __future__ import annotations

import pytest

from bretzel import Bretzel, ui
from bretzel.render import page
from tests.audit.harness import audit_server, browser_page


def _prod_app() -> Bretzel:
    """Une app minimale en mode prod — donc servie par ``runtime.min.js``."""
    app = Bretzel(secret_key="m" * 32, mode="prod")

    @page("/")
    def home() -> None:
        with ui.vstack(id="banc"):
            ui.text("bretzel", id="temoin")
            ui.switch(name="ouvert", id="bascule")

    app.include(home)
    return app


@pytest.fixture(scope="module")
def prod_page():
    with audit_server(_prod_app()) as url:
        with browser_page(url, "/", wait_until="load") as page_obj:
            yield page_obj


def test_prod_serves_the_minified_bundle(prod_page) -> None:
    """Le plancher : sans lui, les deux tests suivants jugeraient le
    bundle LISIBLE et seraient verts pour rien.

    La comparaison porte sur la taille, pas sur l'absence de ``//`` ou
    de ``/*`` : ces deux suites vivent légitimement dans des chaînes du
    bundle réduit (un ``token.endsWith('/*')`` teste un type MIME). Un
    détecteur qui les chercherait rougirait sur du code correct.
    """
    from bretzel.runtime import _build

    body = prod_page.evaluate(
        """async () => (await fetch('/_bretzel/runtime.js')).text()"""
    )
    readable = len(_build.READABLE.read_text(encoding="utf-8"))
    assert len(body) < readable * 0.60, (
        f"bundle servi de {len(body)} caractères pour {readable} au fichier "
        "lisible — la prod ne sert pas la réduction."
    )
    assert len(body) > 50_000, (
        f"bundle servi de {len(body)} caractères — trop court pour être le "
        "runtime complet."
    )


def test_the_minified_bundle_installs_the_runtime(prod_page) -> None:
    """Il s'analyse, et la surface publique est complète."""
    errors: list[str] = []
    prod_page.on("pageerror", lambda err: errors.append(str(err)))
    surface = prod_page.evaluate(
        "() => (window.$bz ? Object.keys(window.$bz).length : 0)"
    )
    assert not errors, f"le bundle réduit a levé au chargement : {errors}"
    assert surface >= 40, (
        f"``window.$bz`` n'expose que {surface} clés — le bundle réduit est "
        "tronqué ou un module a cessé de s'installer."
    )


def test_a_directive_actually_evaluates(prod_page) -> None:
    """Le versant qui MORD : chargé ne veut pas dire vivant.

    ``bz-data`` + ``bz-text`` fait tourner le compilateur d'expressions,
    le graphe de signaux et le balayage — c'est-à-dire les trois modules
    où une regex cassée par le scanner se cacherait.
    """
    rendered = prod_page.evaluate(
        """async () => {
            const host = document.createElement('div');
            host.setAttribute('bz-data', "{ n: 2, mot: 'ok' }");
            const out = document.createElement('span');
            out.setAttribute('bz-text', "mot + (n * 21)");
            host.appendChild(out);
            document.body.appendChild(host);
            window.$bz._scan(host);
            await new Promise(r => requestAnimationFrame(() => r()));
            return out.textContent;
        }"""
    )
    assert rendered == "ok42", (
        f"la directive a rendu {rendered!r} au lieu de 'ok42' — le runtime "
        "réduit est chargé mais n'évalue pas."
    )
