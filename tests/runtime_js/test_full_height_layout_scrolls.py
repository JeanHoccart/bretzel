"""La recette « layout pleine hauteur » tient-elle encore ?

Un layout d'app — chat, boîte mail, tableau de bord — veut occuper l'écran
et faire défiler une zone INTERNE, pas le document. Bretzel le permet, mais
la chaîne de hauteurs doit être continue jusqu'à la page, et deux maillons
sont à câbler à la main : ``ui.container`` est un ``block`` (son enfant ne
peut pas prendre ``flex-1``), et ``ui.outlet`` rend un ``<main>`` sans
hauteur ni ``flex``.

**Aucune suite ne le vérifiait**, et le mode d'échec est silencieux : sans
ces classes la zone grandit avec son contenu, ``overflow-y-auto`` n'a rien
à faire, et le trop-plein est clippé par un ancêtre. Pas d'erreur, pas de
barre — juste des messages qui disparaissent. Mesuré le 2026-08-15 en
montant ``examples/chat`` : ``<main>`` à 1 888 px dans un parent de 855 px.

Ce que la gate protège n'est PAS l'exemple, c'est la recette : elle rougit
si ``ui.outlet``, ``ui.container`` ou le shell cessent de laisser passer la
contrainte — ce qui est précisément le risque d'une refonte du shell.

Elle est aussi un garde-fou de mesure : elle exige que la zone contienne
plus de contenu qu'elle n'a de hauteur, sinon « ça ne défile pas » serait
la bonne réponse et le test passerait pour une raison fausse.

Run : ``py -m pytest tests/runtime_js/test_full_height_layout_scrolls.py -q -m browser``
"""

from __future__ import annotations

import pytest

from tests.audit.harness import audit_server, browser_page

pytestmark = pytest.mark.browser

#: La zone qui doit défiler = l'ancêtre ``overflow-y-auto`` du repère.
_MEASURE = """() => {
    const anchor = document.querySelector('#bz-stream-answer');
    if (!anchor) return {ok: false, why: 'repere #bz-stream-answer absent'};
    let el = anchor.parentElement;
    while (el && !String(el.className).includes('overflow-y-auto')) {
        el = el.parentElement;
    }
    if (!el) return {ok: false, why: 'aucun ancetre overflow-y-auto'};
    return {
        ok: true,
        scrollH: el.scrollHeight,
        clientH: el.clientHeight,
        docOverflows: document.documentElement.scrollHeight > window.innerHeight + 2,
    };
}"""


def test_an_inner_zone_scrolls_instead_of_the_document() -> None:
    from examples.chat.main import app

    with audit_server(app) as base_url:
        with browser_page(base_url, "/", wait_until="load") as browser:
            # Assez de contenu pour dépasser l'écran — sinon « ne défile
            # pas » serait correct et la gate passerait à tort.
            for _ in range(6):
                browser.fill("input[type='text']", "explique le stream")
                browser.click("#bz-send")
                browser.wait_for_function(
                    '() => $bz._store.peek("Draft.default.streaming") === false',
                    timeout=15000,
                )
            browser.wait_for_timeout(300)

            m = browser.evaluate(_MEASURE)
            assert m["ok"], m.get("why")

            # ⚠️ L'ORDRE de ces deux assertions compte, et il a été corrigé
            # après mutation-test. Quand la chaîne casse, la zone grandit
            # avec son contenu, donc ``scrollH == clientH`` — et un plancher
            # placé en premier accusait « pas assez de contenu », envoyant
            # le lecteur ajouter des tours pour un problème de layout. La
            # cause d'abord, le plancher ensuite.
            assert m["clientH"] < 900, (
                f"La zone fait {m['clientH']} px : elle a grandi avec son "
                "contenu au lieu d'être bornée par la hauteur de l'écran. La "
                "chaîne de hauteurs est rompue — vérifier le `flex flex-col` "
                "du container et le `flex-1 min-h-0 flex flex-col` de "
                "l'outlet (cf. le docstring de components/meta/outlet)."
            )
            assert m["scrollH"] > m["clientH"] + 200, (
                "Le contenu ne dépasse pas la zone : la gate ne mesure rien. "
                f"scrollHeight={m['scrollH']} clientHeight={m['clientH']}. "
                "Générer plus de tours avant de conclure que le défilement "
                "fonctionne."
            )
            assert not m["docOverflows"], (
                "Le DOCUMENT déborde : c'est la page entière qui défile, pas "
                "la zone interne. Un shell pleine hauteur doit sortir du flux "
                "(`fixed inset-0`, cf. traps.md § Shell layout h-screen)."
            )
