"""Chaque prop de la famille DnD, exercée sur la VRAIE page ``/dnd``.

``test_dnd_gesture`` prouve le geste sur un DOM fabriqué ; ``test_dnd_end_to_end``
prouve la boucle serveur. Ce fichier-ci répond à une troisième question, et
c'est celle que l'utilisateur a posée : **est-ce que chaque prop fait
vraiment ce qu'il annonce, dans le navigateur ?**

Rien ici n'est déduit du HTML. Un attribut présent ne prouve pas qu'un
comportement existe — ``locked`` et ``disabled`` étaient tous deux
sérialisés correctement pendant qu'on doutait qu'ils marchent. Chaque test
pilote donc une vraie souris et regarde ce qui BOUGE.

Run : ``py -m pytest tests/runtime_js/test_dnd_props.py -q -m browser``
"""

from __future__ import annotations

import json

import pytest

from tests.audit.harness import audit_server, browser_page


@pytest.fixture(scope="module")
def base_url():
    with audit_server() as url:
        yield url


@pytest.fixture(scope="module")
def page(base_url: str):
    with browser_page(base_url, "/dnd", viewport=(1400, 1000)) as p:
        p.wait_for_function("() => window.$bz && window.$bz.dnd", timeout=8000)
        yield p


@pytest.fixture(autouse=True)
def fresh(page):
    """Repartir de l'état initial avant CHAQUE test.

    La page est partagée (fixture de module : un Chromium, pas huit), donc
    un test qui réordonne une zone laisse le suivant avec une disposition
    qu'il n'a pas choisie. ``PageState`` est documenté « reset on a full
    page reload », ce qui fait du rechargement la remise à zéro exacte —
    et ça évite d'inventer un mécanisme de reset dans la page de banc.
    """
    page.reload(wait_until="networkidle")
    page.wait_for_function("() => window.$bz && window.$bz.dnd", timeout=8000)
    yield


# ── Outils ────────────────────────────────────────────────────────────


def keys(page, zone: str) -> list[str]:
    return page.evaluate(
        """(z) => [...document.querySelectorAll(
              `[data-bz-dropzone="${z}"] [data-bz-draggable]`)]
            .map(e => e.getAttribute('data-bz-key'))""",
        zone,
    )


def show(page, *zones: str) -> None:
    """Amener les zones dans le viewport.

    ``page.mouse`` travaille en coordonnées viewport et le runtime teste
    avec ``elementFromPoint``, qui rend ``null`` hors écran : une cible
    sous la ligne de flottaison ne reçoit rien, en silence.
    """
    # ⚠️ ``scrollIntoView`` et PAS ``window.scrollBy`` : le playground
    # défile dans un conteneur interne (le shell), donc scroller la fenêtre
    # ne bouge rien et les zones restent hors écran — où
    # ``elementFromPoint`` rend ``null`` et où le geste meurt en silence.
    # Symptôme : toutes les assertions « ça bouge » échouent et toutes les
    # « ça ne bouge pas » passent, ce qui ressemble à un composant cassé.
    page.evaluate(
        """(zones) => {
            const el = document.querySelector(
                `[data-bz-dropzone="${zones[0]}"]`);
            if (el) el.scrollIntoView({block: 'center'});
        }""",
        list(zones),
    )
    page.wait_for_timeout(200)


def grab_point(page, zone: str, index: int = 0, *, handle: bool | None = None):
    """Où appuyer pour attraper l'item ``index`` de ``zone``.

    ``handle=True`` vise la poignée, ``handle=False`` vise explicitement le
    CORPS de la carte — c'est ce qui permet de prouver qu'une poignée
    rend le reste inerte au lieu de le supposer.
    """
    return page.evaluate(
        """([z, i, mode]) => {
            const items = [...document.querySelectorAll(
                `[data-bz-dropzone="${z}"] [data-bz-draggable]`)];
            const item = items[i];
            if (!item) return null;
            const grip = item.querySelector('[data-bz-drag-handle]');
            let target = item;
            if (mode === true && grip) target = grip;
            if (mode === false && grip) {
                // le corps : à droite de la poignée
                const r = item.getBoundingClientRect();
                const g = grip.getBoundingClientRect();
                return {x: (g.right + r.right) / 2, y: r.top + r.height / 2};
            }
            const r = target.getBoundingClientRect();
            return {x: r.left + r.width / 2, y: r.top + r.height / 2};
        }""",
        [zone, index, handle],
    )


def zone_point(page, zone: str):
    """Le bas de la zone — « déposer à la fin », la cible qui reste valide
    quelle que soit la façon dont la colonne a reflowé."""
    return page.evaluate(
        """(z) => {
            const r = document.querySelector(
                `[data-bz-dropzone="${z}"]`).getBoundingClientRect();
            return {x: r.left + r.width / 2, y: r.bottom - 8};
        }""",
        zone,
    )


def drag(page, start, end, *, steps: int = 10) -> None:
    page.mouse.move(start["x"], start["y"])
    page.mouse.down()
    page.mouse.move(start["x"], start["y"] + 12, steps=3)   # passe le seuil
    page.mouse.move(end["x"], end["y"], steps=steps)
    page.mouse.up()
    page.wait_for_timeout(900)


# ── Les props ─────────────────────────────────────────────────────────


def test_locked_lets_nothing_out_but_still_accepts(page) -> None:
    """``locked=`` ferme UNE porte, pas les deux.

    Les deux moitiés comptent : si rien ne sortait *parce que* rien
    n'entrait, le prop ne prouverait rien. On teste donc le refus ET
    l'acceptation.
    """
    show(page, "kept", "free")
    kept, free = keys(page, "kept"), keys(page, "free")

    drag(page, grab_point(page, "kept"), zone_point(page, "free"))
    assert keys(page, "kept") == kept, "un item est SORTI d'une zone locked"
    assert keys(page, "free") == free

    show(page, "kept", "free")
    drag(page, grab_point(page, "free"), zone_point(page, "kept"))
    assert len(keys(page, "kept")) == len(kept) + 1, (
        "rien n'ENTRE dans la zone locked — alors locked fermerait les deux "
        "portes, et le test ci-dessus ne prouvait rien"
    )


def test_disabled_item_cannot_be_grabbed_but_its_neighbours_can(page) -> None:
    """``disabled=`` est un prédicat PAR ITEM : la carte non saisissable
    ne s'attrape pas, pendant que ses voisines s'attrapent."""
    show(page, "ref_disabled")
    before = keys(page, "ref_disabled")
    locked_index = 1                       # « Pas saisissable », au milieu

    drag(page, grab_point(page, "ref_disabled", locked_index),
         zone_point(page, "ref_disabled"))
    assert keys(page, "ref_disabled") == before, (
        f"l'item disabled a bougé : {before} → {keys(page, 'ref_disabled')}"
    )

    show(page, "ref_disabled")
    drag(page, grab_point(page, "ref_disabled", 0),
         zone_point(page, "ref_disabled"))
    assert keys(page, "ref_disabled") != before, (
        "aucun item de cette zone ne bouge — le test ci-dessus passait "
        "parce que la zone est inerte, pas parce que disabled marche"
    )


def test_a_disabled_item_is_still_displaced_by_its_neighbours(page) -> None:
    """``disabled=`` = « ne s'attrape pas », PAS « ne bouge pas ».

    Signalé par l'utilisateur avec deux captures : la carte non
    saisissable finit ailleurs. Elle n'a pas été *déplacée* — elle a été
    *dépassée*, et dépasser un voisin est la définition de réordonner une
    liste. Même sémantique que Sortable.js (``filter``) et dnd-kit.

    Ce test fige donc le comportement VOULU. Si un jour quelqu'un décide
    qu'un item doit garder sa position, il devra changer cette assertion
    exprès — et se poser la question qui va avec : que veut dire
    « insérer à l'index 1 » quand l'index 1 est épinglé ?
    """
    show(page, "ref_disabled")
    before = page.evaluate(
        """() => [...document.querySelectorAll(
              '[data-bz-dropzone="ref_disabled"] [data-bz-draggable]')]
            .map(e => e.hasAttribute('data-bz-disabled'))"""
    )
    assert before.count(True) == 1 and before.index(True) == 1, (
        f"le banc n'a plus sa carte non-saisissable au milieu : {before}"
    )

    # Tirer la carte du DESSUS en dessous de la non-saisissable.
    drag(page, grab_point(page, "ref_disabled", 0),
         zone_point(page, "ref_disabled"))

    after = page.evaluate(
        """() => [...document.querySelectorAll(
              '[data-bz-dropzone="ref_disabled"] [data-bz-draggable]')]
            .map(e => e.hasAttribute('data-bz-disabled'))"""
    )
    assert after.count(True) == 1, "la carte non-saisissable a disparu"
    assert after.index(True) == 0, (
        f"l'index de la carte non-saisissable n'a PAS bougé ({after}) — "
        f"soit le voisin ne l'a pas dépassée, soit `disabled` épingle "
        f"désormais la position, ce qui serait un autre composant"
    )


def test_handle_makes_the_card_body_inert(page) -> None:
    """``handle=True`` est une RESTRICTION : le corps ne doit plus
    attraper, et la poignée doit toujours attraper."""
    show(page, "ref_handle")
    before = keys(page, "ref_handle")

    body = grab_point(page, "ref_handle", 0, handle=False)
    drag(page, body, zone_point(page, "ref_handle"))
    assert keys(page, "ref_handle") == before, (
        "le CORPS de la carte a attrapé alors que handle=True le rend inerte"
    )

    show(page, "ref_handle")
    grip = grab_point(page, "ref_handle", 0, handle=True)
    drag(page, grip, zone_point(page, "ref_handle"))
    assert keys(page, "ref_handle") != before, (
        "la POIGNÉE n'attrape pas non plus — la carte est simplement morte"
    )


def test_two_undeclared_zones_do_not_exchange_items(page) -> None:
    """Sans ``accepts=``, une zone ne reçoit que ses PROPRES items."""
    show(page, "iso_a", "iso_b")
    a, b = keys(page, "iso_a"), keys(page, "iso_b")
    drag(page, grab_point(page, "iso_a"), zone_point(page, "iso_b"))
    assert keys(page, "iso_a") == a and keys(page, "iso_b") == b, (
        "deux listes indépendantes se sont échangé une carte sans que "
        "personne ait déclaré accepts="
    )


def test_accepts_and_group_let_declared_zones_exchange(page) -> None:
    """L'autre moitié : deux zones qui déclarent le MÊME groupe échangent.

    Sans ce test, celui du dessus serait vrai pour une mauvaise raison
    (le cross-zone cassé partout).
    """
    show(page, "todo", "done")
    todo, done = keys(page, "todo"), keys(page, "done")
    assert todo, "la colonne « À faire » est vide, le test ne prouverait rien"

    drag(page, grab_point(page, "todo", 0, handle=True),
         zone_point(page, "done"))
    assert len(keys(page, "done")) == len(done) + 1, (
        f"accepts=['card'] + group='card' n'échangent pas : "
        f"todo {todo}→{keys(page, 'todo')}, done {done}→{keys(page, 'done')}"
    )


def test_accepts_does_not_freeze_a_zones_own_reordering(page) -> None:
    """``accepts=`` gouverne l'ENTRÉE depuis ailleurs, pas le tri interne.

    Le kanban déclare ``accepts=['card']`` : ses colonnes doivent pouvoir
    se réordonner elles-mêmes. La règle consultait ``accepts`` aussi pour
    le cas interne, donc une zone dont le ``group=`` des items ne
    répondait pas à son ``accepts=`` devenait totalement inerte — en
    silence, et sans qu'aucun attribut n'ait l'air faux.
    """
    show(page, "todo")
    before = keys(page, "todo")
    assert len(before) >= 2, "il faut deux cartes pour prouver un tri interne"

    drag(page, grab_point(page, "todo", 0, handle=True),
         zone_point(page, "todo"))
    assert keys(page, "todo") != before, (
        f"une zone à accepts= ne peut plus se réordonner elle-même "
        f"({before}) — accepts gouverne l'entrée, pas le tri"
    )


def test_key_is_what_the_payload_reports(page) -> None:
    """``key=`` (ou la clé d'itération) est ce que le handler reçoit dans
    ``Move.item_key`` — pas un index, pas un id de DOM."""
    posts: list[str] = []
    page.on(
        "request",
        lambda r: posts.append(r.post_data or "") if "/action/" in r.url else None,
    )
    show(page, "events")
    before = keys(page, "events")
    drag(page, grab_point(page, "events", 0), zone_point(page, "events"))

    import urllib.parse

    blobs = [urllib.parse.parse_qs(p).get("bz_move", [""])[0] for p in posts]
    blobs = [b for b in blobs if b]
    assert blobs, "aucun Move n'a été posté"
    move = json.loads(blobs[-1])
    assert move["item_key"] == before[0], (
        f"item_key={move['item_key']!r} ne correspond pas à la clé rendue "
        f"{before[0]!r}"
    )
    assert move["from_zone"] == move["to_zone"] == "events"


def test_color_tints_the_highlight_of_that_zone_only(page) -> None:
    """``color=`` ne se voit que PENDANT un geste, sur ``data-bz-drop-ok``.

    Mesuré sur la couleur calculée, pas sur la classe : une classe
    présente ne prouve pas qu'une règle CSS existe.
    """
    show(page, "ref_primary", "ref_secondary")
    start = grab_point(page, "ref_primary")
    page.mouse.move(start["x"], start["y"])
    page.mouse.down()
    page.mouse.move(start["x"], start["y"] + 20, steps=4)

    tint = page.evaluate(
        """() => {
            const z = document.querySelector('[data-bz-dropzone="ref_primary"]');
            return {marked: z.hasAttribute('data-bz-drop-ok'),
                    border: getComputedStyle(z).borderTopColor};
        }"""
    )
    page.mouse.up()
    page.wait_for_timeout(300)
    at_rest = page.evaluate(
        """() => getComputedStyle(document.querySelector(
              '[data-bz-dropzone="ref_primary"]')).borderTopColor"""
    )

    assert tint["marked"], "la zone d'origine n'est pas marquée pendant le geste"
    assert tint["border"] != at_rest, (
        f"la bordure ne change pas pendant le geste ({tint['border']}) — "
        f"color= ne peint rien"
    )


def test_a_client_only_handler_fires_without_any_server_call(page) -> None:
    """``on_move="<expr>"`` : le geste doit déclencher l'expression client
    et n'émettre AUCUN POST."""
    posts: list[str] = []
    page.on(
        "request",
        lambda r: posts.append(r.url) if "/action/" in r.url else None,
    )
    show(page, "client")
    before = keys(page, "client")
    drag(page, grab_point(page, "client"), zone_point(page, "client"))

    assert keys(page, "client") != before, "le réordonnancement client n'a pas eu lieu"
    assert not posts, (
        f"un handler CLIENT a quand même posté au serveur : {posts}"
    )
