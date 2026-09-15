"""Le surlignage actif d'une Navbar suit l'URL, y compris quand la nav
ne vient pas d'elle.

``current_path`` est un signal de scope que la Navbar possède ; le clic
sur un item le bascule de façon optimiste. Tout ce qui navigue AUTREMENT
— le back/forward du navigateur, une nav partielle déclenchée par une
sidebar montée à côté — laisserait le surlignage sur l'ancienne entrée.
La Sidebar câblait les deux écoutes ``popstate`` / ``htmx:after-request``
depuis toujours ; la Navbar portait un TODO à la place, alors que son
docstring promettait la parité (audit F26).

Pourquoi un test navigateur : c'est un comportement d'**historique**. Le
SSR montre au mieux qu'un ``bz-init`` est émis — pas que ``popstate``
fait bouger le `data-active`. Le probe pousse une entrée d'historique,
revient en arrière, et lit l'attribut.

Lourd (uvicorn + Chromium) — à lancer explicitement ::

    py -m pytest tests/runtime_js/test_navbar_path_resync.py -q -m browser
"""

from __future__ import annotations

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.navigation.navbar.navbar import (
    Navbar,
    NavbarItem,
    NavbarSection,
)
from bretzel.core.serialize import serialize
from tests.audit.harness import audit_server, browser_page


@pytest.fixture(scope="module")
def base_url():
    with audit_server() as url:
        yield url


def _ssr() -> str:
    with render_isolated():
        with Navbar() as nav:
            with NavbarSection(side="center"):
                NavbarItem("Docs", href="/docs")
                NavbarItem("Blog", href="/blog")
        return serialize(nav.render())


def test_active_highlight_follows_browser_back(base_url: str) -> None:
    html = _ssr()
    with browser_page(base_url, "/navbar") as page:
        page.wait_for_function("() => !!window.$bz", timeout=5000)
        result = page.evaluate(
            """(html) => {
                const host = document.createElement('div');
                host.innerHTML = html;
                document.body.appendChild(host);
                $bz._scan(host);
                const link = (href) =>
                    host.querySelector(`a[href="${href}"]`);
                const state = () => ({
                    docs: link('/docs').getAttribute('data-active'),
                    blog: link('/blog').getAttribute('data-active'),
                });
                const tick = () => new Promise(r =>
                    requestAnimationFrame(() => requestAnimationFrame(r)));
                return (async () => {
                    const out = {};
                    // Le scope seed sur window.location.pathname : on part
                    // d'une URL neutre, donc rien d'actif.
                    out.initial = state();

                    history.pushState({}, '', '/docs');
                    window.dispatchEvent(new PopStateEvent('popstate'));
                    await tick();
                    out.on_docs = state();

                    history.pushState({}, '', '/blog');
                    window.dispatchEvent(new PopStateEvent('popstate'));
                    await tick();
                    out.on_blog = state();

                    // Le vrai back : l'historique revient à /docs et
                    // ``popstate`` part tout seul.
                    history.back();
                    await new Promise(r => setTimeout(r, 120));
                    await tick();
                    out.after_back = state();
                    out.url_after_back = window.location.pathname;
                    return out;
                })();
            }""",
            html,
        )

    assert result["on_docs"]["docs"] == "true", (
        f"une nav vers /docs doit allumer l'item Docs — {result['on_docs']}"
    )
    assert result["on_blog"] == {"docs": "false", "blog": "true"}, (
        f"le surlignage doit SUIVRE, pas s'accumuler — {result['on_blog']}"
    )
    assert result["url_after_back"] == "/docs", (
        f"le back n'a pas ramené l'URL à /docs ({result['url_after_back']}) "
        f"— le probe ne teste alors plus ce qu'il croit"
    )
    assert result["after_back"] == {"docs": "true", "blog": "false"}, (
        f"APRÈS UN BACK NAVIGATEUR le surlignage est resté sur l'ancienne "
        f"entrée — c'est exactement F26 : sans l'écoute ``popstate``, "
        f"``current_path`` ne bouge que sur un clic parti de la navbar. "
        f"got {result['after_back']}"
    )
