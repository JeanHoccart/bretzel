"""``examples/chat`` streame-t-il vraiment, et le Stop arrête-t-il vraiment ?

Un `TestClient` prouve que la page contient les bons attributs. Il ne
prouve aucune des trois choses qui font l'exemple :

1. le texte **grandit** par tranches (donc le patch descend et le
   ``bz-text`` s'applique, sans re-rendu de zone) ;
2. *Stop* **arrête** — c'est la propriété qui a fait choisir ``ui.interval``
   plutôt qu'une boucle ``@app.background``, et elle est invérifiable
   autrement qu'en la mesurant : une boucle serveur non annulable
   continuerait à produire des requêtes après le clic ;
3. le message interrompu **atterrit** dans le journal, qui est l'autre
   moitié du mécanisme (la structure, via ``@refreshable``).

Ce fichier sert aussi de mesure : il imprime le coût réel du transport,
le chiffre qui décidera un jour si le canal SSE doit porter un patch
d'ajout. Une estimation de tête ne vaut rien pour cet arbitrage.

Run : ``py -m pytest tests/runtime_js/test_chat_example_streams.py -q -m browser -s``
"""

from __future__ import annotations

import pytest

from tests.audit.harness import audit_server, browser_page

pytestmark = pytest.mark.browser


def _answer(browser) -> str:  # type: ignore[no-untyped-def]
    """Le texte de la bulle en cours — vide si elle est masquée."""
    return browser.evaluate(
        """() => {
            const el = document.querySelector('#bz-stream-answer');
            return el ? el.textContent : '';
        }"""
    )


def _start(browser, prompt: str) -> None:  # type: ignore[no-untyped-def]
    browser.fill("input[type='text']", prompt)
    browser.click("button:has-text('Envoyer')")


def test_the_answer_grows_and_stop_actually_stops() -> None:
    from examples.chat.features.generator import answer_for
    from examples.chat.main import app

    with audit_server(app) as base_url:
        with browser_page(base_url, "/", wait_until="load") as browser:
            assert _answer(browser) == "", "rien ne devrait streamer au repos"

            _start(browser, "raconte-moi bretzel")

            # ── 1. Le texte grandit ────────────────────────────────────
            browser.wait_for_function(
                "() => (document.querySelector('#bz-stream-answer')?.textContent"
                " || '').length > 20",
                timeout=5000,
            )
            grown = _answer(browser)
            assert len(grown) > 20, f"la bulle ne se remplit pas : {grown!r}"

            # ── 2. Stop arrête VRAIMENT ────────────────────────────────
            browser.click("button:has-text('Stop')")
            # Le gate est un ClientBinding : le timer doit être coupé à
            # l'application du patch, pas au tick suivant. On laisse une
            # marge généreuse et on compare DEUX relevés espacés — si une
            # boucle serveur continuait, le compteur bougerait encore.
            browser.wait_for_timeout(300)
            ticks_a = browser.evaluate('() => $bz._store.peek("Draft.default.ticks")')
            browser.wait_for_timeout(900)
            ticks_b = browser.evaluate('() => $bz._store.peek("Draft.default.ticks")')

            assert ticks_a == ticks_b, (
                f"Le compteur bouge encore après Stop ({ticks_a} → {ticks_b}) : "
                "la cadence n'est pas réellement gatée. C'est exactement le "
                "défaut d'une boucle @app.background — sans contexte, elle ne "
                "peut pas relire l'état qui l'arrête."
            )
            assert (
                browser.evaluate('() => $bz._store.peek("Draft.default.streaming")')
                is False
            ), "le gate ClientState devrait être retombé à False"

            # ── 3. Le texte produit atterrit dans le journal ───────────
            log = browser.evaluate(
                "() => document.body.innerText"
            )
            head = grown[:20]
            assert head in log, (
                "Le message interrompu n'est pas dans le journal. Une réponse "
                "coupée reste une réponse — la jeter punirait l'utilisateur "
                "d'avoir cliqué sur Stop."
            )

            print(
                f"\n[mesure] après {ticks_b} tick(s) : "
                f"{browser.evaluate('() => $bz._store.peek(\"Draft.default.bytes_down\")')}"
                f" octets descendus pour {len(grown)} caracteres affiches."
            )


def test_a_full_generation_costs_quadratic_bytes() -> None:
    """La mesure qui motive (ou non) le patch d'ajout sur SSE.

    On laisse une réponse aller à son terme et on compare les octets
    réellement descendus au texte utile. Le rapport est le chiffre à citer
    dans la décision — pas une estimation.
    """
    from examples.chat.features.generator import answer_for
    from examples.chat.main import app

    with audit_server(app) as base_url:
        with browser_page(base_url, "/", wait_until="load") as browser:
            _start(browser, "explique le stream")

            browser.wait_for_function(
                '() => $bz._store.peek("Draft.default.streaming") === false',
                timeout=15000,
            )

            ticks = browser.evaluate('() => $bz._store.peek("Draft.default.ticks")')
            down = browser.evaluate('() => $bz._store.peek("Draft.default.bytes_down")')

            assert ticks > 5, f"generation trop courte pour mesurer ({ticks} ticks)"
            assert down > 0

            # Le texte utile : ce que l'utilisateur a fini par lire. On le
            # calcule depuis la source plutot que depuis le DOM — le DOM
            # est deja passe par le markdown, donc ses octets ne sont plus
            # ceux du transport.
            useful = len(answer_for("explique le stream").encode("utf-8"))
            print(
                f"\n[mesure] {ticks} requetes | {down} octets descendus | "
                f"{useful} octets utiles | amplification x{down / useful:.1f}"
            )

            # La propriete, pas le chiffre : renvoyer la tranche entiere a
            # chaque tick coute STRICTEMENT plus que le texte final. Le
            # rapport exact depend de la longueur, donc l'assertion porte
            # sur le fait, et le chiffre est imprime pour la decision.
            assert down > useful, (
                "Le total descendu ne depasse pas le texte utile : soit la "
                "mesure est debranchee, soit le transport a change de nature "
                "(un patch d'ajout, par exemple) — auquel cas c'est ce test "
                "qu'il faut reecrire, pas le compteur."
            )
