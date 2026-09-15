"""Une signature DÉJÀ LÀ doit être repeinte, et se comporter comme les traits.

Le bug que cette gate ferme, signalé par l'utilisateur le 2026-08-13 :
``ui.signature_pad(value=doc.signature)`` rendait un cadre **vide**. Le
runtime ne chargeait jamais la data-URL — ``_redraw`` ne connaissait que
``_strokes`` — alors que le SSR avait déjà posé ``data-empty="false"``.
Résultat : un cadre vide, SANS l'invite, sur un composant qui affirmait
porter une signature. Un dossier rouvert perdait la sienne, et la
resoumission l'aurait **effacée**.

**Pourquoi une gate navigateur et pas un test unitaire.** Rien de tout
ça n'existe côté serveur : le HTML était parfaitement correct — la
data-URL était bien dans le porteur, ``data-empty`` bien à ``false``.
C'est le PIXEL qui manquait. Les 12 048 tests du sous-ensemble rapide
étaient verts, et mes quatorze probes navigateur aussi : aucun ne
regardait un pad PRÉ-REMPLI. C'est l'utilisateur qui l'a vu, en dix
secondes, sur une capture d'écran.

Les quatre assertions ne sont pas quatre façons de dire la même chose —
chacune ferme une régression différente :

1. **peinte** : le chargement existe.
2. **survit au redimensionnement** : elle est bien une COUCHE DE FOND
   redessinée, pas un bitmap posé une fois. Un canvas se vide quand on
   le redimensionne ; sans ``_base``, la signature repartirait au
   premier changement de taille (donc à la première rotation de
   téléphone).
3. **signer par-dessus AJOUTE** : le fond n'écrase pas les traits neufs
   et réciproquement — les deux partent ensemble dans le PNG publié.
4. **``.clear()`` emporte les deux** : « effacer » veut dire un cadre
   vide, pas « revenir à la signature d'avant ».

Lourd (uvicorn + Chromium) — à lancer explicitement :
``py -m pytest tests/runtime_js/test_signature_pad_repaints_existing.py -q -m browser``
"""

from __future__ import annotations

import pytest

from tests.audit.harness import audit_server, browser_page

#: Compte les pixels non transparents du canvas. La mesure la plus
#: bête possible, et c'est voulu : elle ne peut pas être satisfaite par
#: un HTML correct, seulement par de l'encre réellement posée.
_SCENARIO = """async () => {
    const tick = (ms) => new Promise(r => setTimeout(r, ms));
    const pads = [...document.querySelectorAll(
        "div[bz-data*='$bz.signaturePad.scope']")];
    const g = pads.find(p => {
        const i = p.querySelector('input[type=hidden]');
        return i && i.getAttribute('value');
    });
    if (!g) return {err: 'aucun pad pré-rempli sur le banc'};
    const c = g.querySelector('canvas');
    const inked = () => {
        const d = c.getContext('2d')
            .getImageData(0, 0, c.width, c.height).data;
        let n = 0;
        for (let i = 3; i < d.length; i += 4) if (d[i] > 0) n++;
        return n;
    };
    const out = {};
    out.painted = inked();

    g.style.width = '55%';
    await tick(150);
    out.afterResize = inked();
    g.style.width = '';
    await tick(150);
    const base = inked();

    const r = c.getBoundingClientRect();
    const o = {bubbles: true, pointerId: 31, pointerType: 'mouse'};
    c.dispatchEvent(new PointerEvent('pointerdown',
        {...o, clientX: r.left + 30, clientY: r.top + 30}));
    for (let i = 1; i <= 8; i++) {
        c.dispatchEvent(new PointerEvent('pointermove',
            {...o, clientX: r.left + 30 + i * 10,
             clientY: r.top + 30 + i * 4}));
    }
    c.dispatchEvent(new PointerEvent('pointerup', {...o}));
    await tick(150);
    out.afterDrawing = inked();
    out.baseBeforeDrawing = base;
    out.publishedLen = g.querySelector('input[type=hidden]').value.length;

    const raw = window.$bz._scopeFor(g);
    (raw.proxy || raw).clear();
    await tick(150);
    out.afterClear = inked();
    out.clearedValue = g.querySelector('input[type=hidden]').value;
    return out;
}"""


@pytest.fixture(scope="module")
def scenario() -> dict:
    with audit_server() as base:
        with browser_page(base, "/signature_pad") as page:
            page.wait_for_timeout(2200)
            return page.evaluate(_SCENARIO)


def test_an_existing_signature_is_painted(scenario: dict) -> None:
    assert "err" not in scenario, scenario.get("err")
    assert scenario["painted"] > 200, (
        f"le canvas d'un pad PRÉ-REMPLI ne porte que "
        f"{scenario['painted']} pixels encrés — la data-URL rendue au "
        f"SSR n'est pas chargée. Le cadre s'affiche vide ET sans invite "
        f"(le serveur a posé data-empty=false), donc le composant "
        f"annonce une signature qu'il ne montre pas."
    )


def test_it_survives_a_resize(scenario: dict) -> None:
    assert scenario["afterResize"] > 200, (
        "la signature chargée disparaît au redimensionnement : elle a "
        "été posée une fois au lieu d'être une COUCHE DE FOND que "
        "``_redraw`` repeint. Un canvas se vide quand on le "
        "redimensionne — donc à la première rotation de téléphone."
    )


def test_drawing_on_top_adds_to_it(scenario: dict) -> None:
    assert scenario["afterDrawing"] > scenario["baseBeforeDrawing"], (
        "signer par-dessus une signature existante n'ajoute pas "
        "d'encre : le fond et les traits s'écrasent au lieu de se "
        "composer."
    )
    assert scenario["publishedLen"] > 500, (
        "le PNG publié est vide alors que le canvas porte de l'encre."
    )


def test_clear_takes_the_base_layer_too(scenario: dict) -> None:
    assert scenario["afterClear"] == 0, (
        f"``.clear()`` laisse {scenario['afterClear']} pixels — la "
        f"couche de fond survit. « Effacer » doit donner un cadre vide, "
        f"pas « revenir à la signature d'avant »."
    )
    assert scenario["clearedValue"] == "", (
        "``.clear()`` laisse une valeur non vide sur le porteur, donc "
        "la soumission renverrait la signature qu'on vient d'effacer."
    )
