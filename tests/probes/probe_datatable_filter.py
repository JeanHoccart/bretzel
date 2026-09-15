"""Probe — le filtre de colonne du datatable, et la barre qui l'héberge.

Chaque mesure porte sur un point que le SSR ne peut PAS décider. Les
assertions SSR vivent à côté, dans
``tests/unit/components/data/test_datatable.py`` — ici on ne met que ce
qui demande un vrai moteur de rendu.

**La barre d'outils** — sa composition, pas ses classes :

- un filtre au repos a une BOÎTE (pas seulement du texte accentué : la
  boîte d'un ``ghost`` n'existe que sous ``hover:``, donc avant le
  survol personne ne voit qu'il y a un contrôle) ;
- l'export est au bout à droite, et pas collé au dernier filtre — à
  gauche on restreint, à droite on sort les données ;
- un filtre ACTIF se distingue de ses voisins par la couleur, pas par la
  boîte : la variante ne bouge pas, donc la barre ne saute pas au
  premier filtre posé ;
- en mode clair, l'export (un ``<a>`` retagué en bouton) reçoit la même
  encre que les ``<button>`` voisins.

**Le panneau** :

- il s'ouvre ancré sous son bouton, dans l'écran, sans défilement
  horizontal, et plus large que le déclencheur (``match_width`` coupé) ;
- la recherche a bien migré du déclencheur vers le panneau (``trigger=``) ;
- cocher / décocher ne déclenche AUCUNE requête, et « Clear » non plus —
  rien ne part tant que le panneau est ouvert ;
- « Clear » ne REFERME pas le panneau qu'il commande ;
- la fermeture applique, une fois, et le compte tombe ;
- **changer de page ne perd pas le filtre** — le bug listé au chantier
  du 2026-08-06, qu'on mesure plutôt que de le supposer caduc.

Plus trois screenshots (barre sombre / barre filtrée / barre claire), un
du panneau ouvert, et un compte des erreurs JS.

Run :  py tests/probes/probe_datatable_filter.py
"""

import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

from tests.probes._serve import free_port

# S'EXÉCUTE au chargement (serveur + Chromium), sans garde ``__main__``
# contrairement aux 48 autres probes. Refuser l'import évite qu'un
# balayage du dépôt démarre un navigateur.
# Cf. ``tests/consistency/test_probes_still_resolve.py``.
if __name__ != "__main__":
    raise RuntimeError(
        "probe_datatable_filter est un script : lance-le "
        "(`py tests/probes/probe_datatable_filter.py`), ne l'importe pas."
    )

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).parent
PORT = free_port()
URL = f"http://127.0.0.1:{PORT}/"
srv = subprocess.Popen(
    [sys.executable, str(HERE / "bench_datatable_filter.py"), str(PORT)],
    cwd=str(HERE.parent.parent),
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)


def wait() -> None:
    for _ in range(60):
        try:
            urllib.request.urlopen(URL, timeout=1)
            return
        except OSError:
            time.sleep(0.3)


FAILURES: list[str] = []


def styles(pg, **selectors) -> dict:
    """``{nom: {color, bg}}`` pour plusieurs sélecteurs, en UNE traversée.

    Trois closures ``getComputedStyle`` identiques vivaient ici ; elles
    mesuraient la même chose et pouvaient donc dériver l'une de l'autre.
    """
    return pg.evaluate(
        """(sels) => Object.fromEntries(Object.entries(sels).map(
            ([k, sel]) => {
                const el = document.querySelector(sel);
                const c = getComputedStyle(el);
                return [k, {color: c.color, bg: c.backgroundColor}];
            }))""",
        selectors,
    )


def painted(bg: str) -> bool:
    """L'élément a-t-il un fond, ou seulement du texte ?"""
    return bg not in ("rgba(0, 0, 0, 0)", "transparent")


def rgb(value: str) -> list[int]:
    """``rgb(15, 23, 42)`` OU ``rgb(15 23 42)`` -> ``[15, 23, 42]``.

    Tailwind v4 émet la forme SANS virgules, et un
    ``.strip("rgb()").split(",")`` y rend un seul jeton — la comparaison
    passait alors par accident. Même orthographe que
    ``probe_inputs.py``.
    """
    return [int(n) for n in re.findall(r"\d+", value)[:3]]


def check(label: str, ok: bool, detail: str = "") -> None:
    """L'idiome maison des probes (cf. ``probe_combobox.py``) : le
    ``check`` accumule lui-même. Le libellé humain EST l'identifiant du
    échec — pas besoin d'un second jeu de tags."""
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}"
          + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(f"{label}: {detail}")


try:
    wait()
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900},
                                color_scheme="dark")
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(URL)
        page.wait_for_selector("html.bz-ready")

        box = "#bzf_Issues_status"
        results = "text=/\\d+ results/"

        before = page.text_content(results).strip()
        print(f"footer at rest : {before!r}")

        # ── 0a. la zone est TRANSPARENTE a la disposition ────────────
        # Un `@refreshable` est une frontiere de transport : HTMX vise
        # son id, idiomorph la retrouve. Rien la-dedans ne demande une
        # boite — et tant qu'elle en avait une, ses N enfants comptaient
        # pour UN dans le stack parent, donc le `gap` s'arretait a elle.
        # 100 des 201 zones du playground le subissaient.
        zone = page.evaluate(
            """() => {
                const z = document.querySelector('[bz-id^="refresh_"]');
                const p = z.parentElement;
                const gap = parseFloat(getComputedStyle(p).rowGap) || 0;
                const cap = document.getElementById('caption');
                const dt = document.getElementById('dt');
                return {
                    display: getComputedStyle(z).display,
                    parentGap: gap,
                    // L'ecart REEL entre la legende et le tableau : ils
                    // sont freres DANS la zone, donc il ne vaut le gap du
                    // parent que si la zone ne fait pas boite.
                    inner: dt.getBoundingClientRect().top
                         - cap.getBoundingClientRect().bottom,
                };
            }""")
        print(f"zone display={zone['display']} | gap parent="
              f"{zone['parentGap']}px | ecart interne={zone['inner']:.0f}px")
        check(
            "la zone n'a pas de boite (display:contents)",
            zone["display"] == "contents", zone["display"],
        )
        # `parentGap > 0` n'est pas decoratif : sans lui, un parent SANS
        # gap rendrait `abs(0 - 0) < 2` vrai avec la boite encore la —
        # l'assertion passerait en prouvant l'inverse de ce qu'elle dit.
        check(
            "le gutter du parent traverse la zone",
            zone["parentGap"] > 0
            and abs(zone["inner"] - zone["parentGap"]) < 2,
            f"{zone['inner']:.0f}px vs gap parent {zone['parentGap']}px",
        )

        # ── 0. la barre d'outils : deux moitiés, et des boîtes ───────
        bar = page.evaluate(
            """() => {
                const box = (el) => el.getBoundingClientRect();
                const tb = document.querySelector('.bz-datatable > div');
                // Le DERNIER filtre, pas le premier : c'est l'ecart a
                // CELUI-LA qui dit si l'export est colle au groupe. La
                // premiere version mesurait depuis `status` en l'appelant
                // « dernier filtre », donc son seuil enjambait les deux
                // autres filtres et ne voulait plus rien dire.
                const trigs = [...document.querySelectorAll(
                    '[bz-ref=bztrigger] button')];
                const last = trigs[trigs.length - 1];
                const exp = document.querySelector('a[download]');
                return {
                    barRight: box(tb).right,
                    lastRight: box(last).right,
                    expLeft: box(exp).left,
                    expRight: box(exp).right,
                    nFilters: trigs.length,
                };
            }""")
        tone = styles(page, filtre=f"{box} [bz-ref=bztrigger] button")["filtre"]
        print(f"filtre bg={tone['bg']} color={tone['color']}")
        print(f"barre droite={bar['barRight']:.0f} | export "
              f"{bar['expLeft']:.0f}..{bar['expRight']:.0f} | dernier des "
              f"{bar['nFilters']} filtres finit a {bar['lastRight']:.0f}")
        # `soft` doit PEINDRE au repos. La boite d'un `ghost` n'existe que
        # sous `hover:` — donc avant le survol, souris ou pas, personne ne
        # voit qu'il y a un controle. Un fond transparent ici = la
        # regression vers une barre qui se lit comme une rangee de liens.
        check(
            "un filtre au repos a une boite (pas seulement du texte)",
            painted(tone["bg"]), f"background-color={tone['bg']}",
        )
        # L'export est A L'AUTRE BOUT : a gauche on restreint, a droite on
        # sort les donnees. Colle aux filtres, il se lisait comme l'un
        # d'eux.
        check(
            "l'export est au bout a droite de la barre",
            abs(bar["expRight"] - bar["barRight"]) < 2
            and bar["expLeft"] - bar["lastRight"] > 80,
            f"fin export={bar['expRight']:.0f} fin barre="
            f"{bar['barRight']:.0f} ; ecart au dernier filtre="
            f"{bar['expLeft'] - bar['lastRight']:.0f}px",
        )
        page.screenshot(path=str(HERE / "datatable_toolbar_dark.png"),
                        clip={"x": 0, "y": 0, "width": 1280, "height": 220})

        # ── 0a-bis. la barre se lit comme UNE famille ────────────────
        # La recherche est une surface bordee (`bg-interface` +
        # `border-text/10`) ; les chips l'etaient pas — un lavis d'encre
        # sans bordure. Deux recettes cote a cote dans la meme barre.
        # Elles partagent desormais la variante `surface`.
        #
        # Et le hover de l'export : un `Button(tag="a")` perdait TOUTES
        # ses regles `enabled:`, parce que `:enabled` ne matche que les
        # elements de formulaire — jamais une ancre. Mesure avant le
        # fix : fond identique au repos et au survol.
        fam = {}
        for name, sel in (("recherche", ".bz-datatable input[type=text]"),
                          ("filtre", f"{box} [bz-ref=bztrigger] button"),
                          ("export", "a[download]")):
            rest = styles(page, e=sel)["e"]
            page.hover(sel)
            page.wait_for_timeout(350)
            hov = styles(page, e=sel)["e"]
            page.mouse.move(5, 5)
            page.wait_for_timeout(150)
            border = page.evaluate(
                """(s) => { const c = getComputedStyle(
                     document.querySelector(s));
                   return c.borderTopWidth + ' ' + c.borderTopColor; }""", sel)
            fam[name] = {"bg": rest["bg"], "border": border,
                         "hovers": rest["bg"] != hov["bg"]}
        print("famille :", {k: v["bg"] for k, v in fam.items()})
        check(
            "recherche, filtre et export partagent la meme surface",
            len({v["bg"] for v in fam.values()}) == 1
            and len({v["border"] for v in fam.values()}) == 1,
            f"fonds={[v['bg'] for v in fam.values()]} "
            f"bordures={[v['border'] for v in fam.values()]}",
        )
        # L'export DOIT survoler : c'est un `<a>`, et c'est la ou
        # `enabled:` echouait en silence.
        check(
            "l'export a un hover malgre son tag <a>",
            fam["export"]["hovers"],
        )
        check(
            "le filtre a un hover",
            fam["filtre"]["hovers"],
        )

        # ── 0b. la barre encaisse l'etroitesse en compressant, pas en
        #        passant a la ligne ────────────────────────────────────
        # Sous `flex-wrap`, un debordement RETOURNE A LA LIGNE — il ne
        # compresse pas. Avec `w-full` la recherche restait donc a 320 px
        # de 1400 a 700 px (mesure : pas un pixel cede) et l'export se
        # payait une rangee entiere des ~1000 px. `flex-1` + `min-w-48`
        # en fait l'amortisseur de la barre : elle est le seul controle
        # dont la largeur ne soit pas dictee par son texte.
        #
        # On mesure a 800 px, DANS l'etat charge (un filtre pose, donc le
        # bouton de remise a zero present) : c'est la configuration de la
        # capture qui a lance ce travail. 800 et pas 900 parce qu'a 900 la
        # barre tient SANS que la recherche ait a ceder — l'icone de
        # remise a zero a rendu ~78 px — et on veut mesurer l'amortisseur
        # en train d'amortir, pas au repos. Seuil mesure : la compression
        # demarre vers 850 px, le debordement vers 760.
        page.click(f"{box} [bz-ref=bztrigger] button")
        page.wait_for_timeout(200)
        page.click(f"{box} [role=listbox] [role=option][data-value=closed]")
        page.mouse.click(20, 20)
        page.wait_for_timeout(700)
        page.set_viewport_size({"width": 800, "height": 900})
        page.wait_for_timeout(250)
        narrow = page.evaluate(
            """() => {
                const tb = document.querySelector('.bz-datatable > div');
                // Le CENTRE, pas le haut. La barre est en `items-center`,
                // donc deux enfants de hauteurs differentes sur la MEME
                // ligne n'ont pas le meme `top` — le compteur voyait alors
                // deux rangees la ou il n'y en a qu'une. Mesure du
                // 2026-09-13 : barre de 852 px pour 764 px de contenu,
                // donc une seule ligne, et le probe annoncait deux.
                // Un enfant de 24 px a cote d'un champ de 30 suffisait.
                const tops = new Set([...tb.children].map((k) => {
                    const r = k.getBoundingClientRect();
                    return Math.round(r.top + r.height / 2);
                }));
                const field = document.querySelector(
                    '.bz-datatable input[type=text]');
                const reset = document.querySelector(
                    '.bz-datatable button[aria-label="Clear filters"]');
                return {
                    rows: tops.size,
                    search: field.closest('div[class*="min-w"]')
                                 .getBoundingClientRect().width,
                    resetText: reset ? reset.textContent.trim() : null,
                    resetColor: reset ? getComputedStyle(reset).color : null,
                };
            }""")
        print(f"a 800px : {narrow['rows']} rangee(s), recherche "
              f"{narrow['search']:.0f}px, reset={narrow['resetText']!r}")
        check(
            "a 800px la barre tient encore sur UNE rangee",
            narrow["rows"] == 1, f"{narrow['rows']} rangees",
        )
        check(
            "la recherche a cede du terrain sans passer sous son plancher",
            192 <= narrow["search"] < 320, f"{narrow['search']:.0f}px",
        )
        # La remise a zero est une ICONE : elle n'apparait QUE lorsque
        # quelque chose filtre, donc elle chargeait la barre pile au
        # moment ou elle etait deja pleine.
        check(
            "la remise a zero est une icone, pas un libelle",
            narrow["resetText"] == "", repr(narrow["resetText"]),
        )
        page.set_viewport_size({"width": 1280, "height": 900})
        page.wait_for_timeout(200)
        page.reload()
        page.wait_for_selector("html.bz-ready")
        page.wait_for_timeout(200)

        # ── 0c. la croix de la recherche ─────────────────────────────
        # Elle doit faire DEUX choses, et la seconde est celle qu'un test
        # SSR ne peut pas voir : vider le champ, et relancer la requete.
        # Ecrire `.value = ''` ne suffit pas — ni `bz-model` ni le
        # `hx-trigger="change"` du handler ne verraient rien.
        field = ".bz-datatable input[type=text]"
        cross = '.bz-datatable button[aria-label="Clear"]'
        shown = page.evaluate(
            f"""() => getComputedStyle(
                 document.querySelector('{cross}')).display""")
        check(
            "la croix est absente quand le champ est vide",
            shown == "none", f"display={shown}",
        )
        page.fill(field, "issue 1")
        page.wait_for_timeout(150)
        shown = page.evaluate(
            f"""() => getComputedStyle(
                 document.querySelector('{cross}')).display""")
        check(
            "la croix parait des qu'il y a quelque chose a effacer",
            shown != "none", f"display={shown}",
        )
        page.dispatch_event(field, "change")
        page.wait_for_timeout(700)
        searched = page.text_content(results).strip()
        page.click(cross)
        page.wait_for_timeout(700)
        cleared = page.text_content(results).strip()
        value_after = page.input_value(field)
        print(f"recherche : {before!r} -> {searched!r} -> croix -> "
              f"{cleared!r} (champ={value_after!r})")
        check(
            "la croix vide le champ", value_after == "", repr(value_after),
        )
        check(
            "la croix relance la requete serveur",
            searched != before and cleared == before,
            f"{before!r} -> {searched!r} -> {cleared!r}",
        )

        # ── 1-2. open, anchored, wider than the trigger ──────────────
        page.click(f"{box} [bz-ref=bztrigger] button")
        page.wait_for_timeout(250)
        geom = page.evaluate(
            """(sel) => {
                const root = document.querySelector(sel);
                const trig = root.querySelector('[bz-ref=bztrigger]')
                                 .firstElementChild;
                const panel = root.querySelector('[role=listbox]');
                const t = trig.getBoundingClientRect();
                const p = panel.getBoundingClientRect();
                return {tw: t.width, tb: t.bottom, tl: t.left,
                        pw: p.width, pt: p.top, pl: p.left,
                        ph: p.height,
                        sw: panel.scrollWidth, cw: panel.clientWidth,
                        vw: innerWidth, vh: innerHeight,
                        display: getComputedStyle(panel).display};
            }""", box)
        print(f"trigger {geom['tw']:.0f}px @({geom['tl']:.0f},{geom['tb']:.0f}) "
              f"| panel {geom['pw']:.0f}x{geom['ph']:.0f} @({geom['pl']:.0f},"
              f"{geom['pt']:.0f})")
        check(
            "le panneau est visible et dans l'écran",
            geom["display"] != "none"
            and 0 <= geom["pl"] and geom["pl"] + geom["pw"] <= geom["vw"]
            and 0 <= geom["pt"] < geom["vh"],
        )
        check(
            "le panneau est ancré sous son déclencheur",
            abs(geom["pt"] - geom["tb"]) < 24
            and abs(geom["pl"] - geom["tl"]) < 24,
        )
        check(
            "le panneau est plus large que le bouton (match_width coupé)",
            geom["pw"] > geom["tw"] + 20,
            f"{geom['pw']:.0f} > {geom['tw']:.0f}",
        )
        check(
            "pas de défilement horizontal dans le panneau",
            geom["sw"] <= geom["cw"] + 1,
            f"scrollWidth={geom['sw']} clientWidth={geom['cw']}",
        )

        # The relocated search field lives INSIDE the panel.
        in_panel = page.evaluate(
            """(sel) => {
                const root = document.querySelector(sel);
                const panel = root.querySelector('[role=listbox]');
                const trig = root.querySelector('[bz-ref=bztrigger]');
                return {
                    panel: !!panel.querySelector('input[type=text]'),
                    trigger: !!trig.querySelector('input[type=text]'),
                };
            }""", box)
        check(
            "la recherche a migré dans le panneau",
            in_panel["panel"] and not in_panel["trigger"],
        )

        page.screenshot(path=str(HERE / "datatable_filter_open.png"))

        # ── 3. ticking posts nothing ─────────────────────────────────
        page.click(f"{box} [role=listbox] [role=option][data-value=closed]")
        page.click(f"{box} [role=listbox] [role=option][data-value=draft]")
        page.wait_for_timeout(400)
        during = page.text_content(results).strip()
        check(
            "cocher ne poste rien",
            during == before, f"{before!r} -> {during!r}",
        )

        # ── 4. Clear does not dismiss the panel ──────────────────────
        page.click(f"{box} [role=listbox] button:has-text('Clear')")
        page.wait_for_timeout(300)
        still_open = page.evaluate(
            """(sel) => getComputedStyle(document.querySelector(sel)
                 .querySelector('[role=listbox]')).display !== 'none'""", box)
        after_clear = page.text_content(results).strip()
        check(
            "« Clear » ne referme pas le panneau qu'il commande",
            still_open,
        )
        check(
            "« Clear » ne poste rien non plus",
            after_clear == before, f"{before!r} -> {after_clear!r}",
        )

        # ── 5. closing applies, once ─────────────────────────────────
        # Two statuses kept → 14 of 34 rows, so the table still pages :
        # that is what the pagination check below needs.
        for value in ("open", "merged"):
            page.click(f"{box} [role=listbox] [role=option]"
                       f"[data-value={value}]")
            page.wait_for_timeout(120)
        page.mouse.click(20, 20)                     # click outside → close
        page.wait_for_timeout(700)
        after = page.text_content(results).strip()
        # « 14 results », PAS « 14 results of 34 » : le bench est en tier
        # callable, ou le composant ne detient aucune ligne et ne peut
        # donc pas connaitre le total non filtre. `_result_label` refuse
        # de l'inventer — « 34 results of 0 » est pire que « 34 results ».
        check(
            "la fermeture applique le filtre",
            after == "14 results", f"{before!r} -> {after!r}",
        )
        check(
            "le déclencheur porte le compte de la sélection",
            "2/5" in (page.text_content(f"{box} [bz-ref=bztrigger]") or ""),
            repr(page.text_content(f"{box} [bz-ref=bztrigger]")),
        )

        # ── 6. the filter survives a page change ─────────────────────
        # Bug listé au chantier : « filtre actif → 22 results, clic page 2
        # → 34 results ». Le passage des coches en scope client devrait
        # l'avoir rendu caduc ; on le MESURE plutôt que de le supposer.
        page.click("nav[role=navigation] button:has-text('2'), "
                   "[aria-label='Page 2']")
        page.wait_for_timeout(700)
        paged = page.text_content(results).strip()
        check(
            "changer de page ne perd pas le filtre",
            paged == after, f"{after!r} -> {paged!r}",
        )

        # ── 6b. la zone a survecu aux swaps ──────────────────────────
        # ICI et pas au repos : a ce point la zone a ete swappee en OOB
        # plusieurs fois (le filtre, puis la pagination). C'est ce qui
        # rend l'assertion non triviale — un `display:contents` n'a pas
        # de boite, et la question etait justement de savoir si HTMX et
        # idiomorph savent encore viser un element qui n'en a pas.
        survived = page.evaluate(
            """() => {
                const z = document.querySelector('[bz-id^="refresh_"]');
                if (!z) return null;
                return {display: getComputedStyle(z).display,
                        targetable: document.getElementById(z.id) === z,
                        hasRows: !!z.querySelector('tbody tr')};
            }""")
        check(
            "apres plusieurs swaps, la zone est toujours une cible sans boite",
            survived is not None and survived["display"] == "contents"
            and survived["targetable"] and survived["hasRows"],
            repr(survived),
        )

        # ── 7. l'accent est le SEUL signal d'un filtre actif ─────────
        # Un filtre au repos et un filtre qui filtre partagent la meme
        # variante `soft` et donc la meme boite : la barre ne bouge pas
        # au premier filtre pose. Ce qui change est le TON — et c'est la
        # regle que les en-tetes de tri appliquent deja (l'accent se
        # depense sur ce qui est ACTIF). On le mesure : la couleur d'un
        # filtre actif doit differer de celle de ses voisins au repos.
        tones = styles(
            page,
            active="#bzf_Issues_status [bz-ref=bztrigger] button",
            idle="#bzf_Issues_priority [bz-ref=bztrigger] button",
        )
        print(f"actif={tones['active']['color']} | repos={tones['idle']['color']}")
        check(
            "un filtre actif se distingue de ses voisins par la couleur",
            tones["active"]["color"] != tones["idle"]["color"],
            f"{tones['active']['color']} vs {tones['idle']['color']}",
        )
        page.screenshot(path=str(HERE / "datatable_toolbar_filtered.png"),
                        clip={"x": 0, "y": 80, "width": 1280, "height": 70})

        # Le meme systeme doit tenir dans les deux themes : `bg-current/10`
        # suit la couleur de texte HERITEE, qui s'inverse d'un mode a
        # l'autre.
        #
        # PAGE NEUVE, pas `emulate_media` sur celle-ci : basculer le
        # schema sur une page deja peinte laisse un etat intermediaire —
        # l'export y sortait delave alors qu'un chargement propre lui
        # donne exactement l'encre des filtres. Un screenshot de cet
        # artefact, garde dans le depot, se relit plus tard comme un bug.
        light = browser.new_page(viewport={"width": 1280, "height": 700},
                                 color_scheme="light")
        light.goto(URL)
        light.wait_for_selector("html.bz-ready")
        # `bz-ready` dit que le runtime a demarre, PAS que la peinture a
        # fini. On ATTEND LA STABILITE plutot qu'une constante : la
        # premiere version dormait 400 ms « pour couvrir la transition de
        # 200 ms », et c'etait calibre sur la mauvaise variable — ce qui
        # bouge ici est le JIT Tailwind du mode dev, qui regenere sa
        # feuille en un temps proportionnel a la charge machine (mesure :
        # 13 ms a chaud, 283 et 309 ms a froid). 400 ms valait donc 30x
        # trop en tiede et 1,3x le pire cas mesure — une marge trop mince
        # pour l'assertion a +/-4 qu'elle alimente. Deux lectures
        # identiques d'affilee, et on sait qu'on lit l'etat stable.
        light.wait_for_function(
            """() => {
                const g = (s) => getComputedStyle(
                    document.querySelector(s)).color;
                const now = g('#bzf_Issues_priority [bz-ref=bztrigger] button')
                          + '|' + g('a[download]');
                const stable = window.__bzPrev === now;
                window.__bzPrev = now;
                return stable;
            }""",
            polling=100, timeout=5000,
        )
        light_tones = styles(
            light,
            filtre="#bzf_Issues_priority [bz-ref=bztrigger] button",
            export="a[download]",
        )
        print(f"clair : filtre {light_tones['filtre']} | export "
              f"{light_tones['export']}")
        # PAS de second « a une boite au repos » ici : `soft` est
        # `bg-{color}/10`, donc non transparent PAR CONSTRUCTION dans les
        # deux themes — le seul moyen de le faire echouer serait un
        # retour a `ghost`, que la mesure en sombre attrape deja. Ce que
        # le mode clair peut dire et l'autre non, c'est la PARITE : un
        # `<a>` retague en bouton doit recevoir la meme encre que les
        # `<button>` voisins, ou le seul controle qui SORT les donnees
        # serait le moins lisible de la barre.
        check(
            "l'export a la meme encre que les filtres (c'est un <a>)",
            max(abs(a - b) for a, b in zip(rgb(light_tones["export"]["color"]),
                                           rgb(light_tones["filtre"]["color"])))
            <= 4,
            f"{light_tones['export']['color']} vs "
            f"{light_tones['filtre']['color']}",
        )
        light.screenshot(path=str(HERE / "datatable_toolbar_light.png"),
                         clip={"x": 0, "y": 80, "width": 1280, "height": 70})
        light.close()

        check(
            "aucune erreur JS", not errors, "; ".join(errors[:3]),
        )

        browser.close()
finally:
    srv.terminate()
    srv.wait(timeout=10)

print("PROBE", "FAILED" if FAILURES else "PASSED")
for line in FAILURES:
    print("  -", line)
sys.exit(1 if FAILURES else 0)
