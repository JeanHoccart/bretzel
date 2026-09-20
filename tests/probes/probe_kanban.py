"""Playwright probe — le kanban tient sa promesse : le tableau est PARTAGÉ (:8957).

Sert ``examples.kanban.main:app`` sur un port dédié : celle que
l'utilisateur fait tourner sert peut-être un bundle runtime plus ancien,
donc elle ne testerait rien.

Ce que ça mesure, et pourquoi ``TestClient`` ne le mesure pas
-------------------------------------------------------------
Un GET rendu par ``TestClient`` prouve que Python a sérialisé du HTML. Il
ne dit rien de ce qui fait cet exemple :

- **deux fenêtres, une seule vérité** : ce qu'une session glisse doit
  arriver dans l'AUTRE sans qu'elle recharge. C'est du SSE, donc du
  navigateur, et un seul onglet ne prouve rien — il aurait de toute façon
  re-rendu sa propre zone ;
- **le refus d'un dépôt** : la limite d'en-cours ne lève pas et
  n'affiche pas d'erreur serveur ; le navigateur a déjà bougé la carte et
  c'est le morph qui la remet en place ;
- le glisser-déposer lui-même, qui n'existe qu'en gestes de souris ;
- l'ouverture d'un overlay pilotée par le SERVEUR, qui a déjà échoué en
  silence une fois (cf. ``state.Vue``, le champ ``tiroir``).

Les cinq probes minimaux de la discipline #3 sont là aussi : couleurs
distinctes, tailles distinctes, ordre de tabulation, pas de double barre
de défilement, capture.

Run :  py tests/probes/probe_kanban.py
"""

from __future__ import annotations

import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).parent
REPO = HERE.parent.parent
PORT = 8957
BASE = f"http://127.0.0.1:{PORT}"

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{name}: {detail}")


def wait_server(timeout: float = 25.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(BASE + "/", timeout=1):
                return
        except OSError:
            time.sleep(0.3)
    raise RuntimeError(f"le kanban n'est jamais monté sur :{PORT}")


def pret(page) -> None:
    """Attend le drapeau de fin de boot du runtime.

    ``wait_for_selector("html.bz-ready")`` ne marche pas ici : l'app pose
    un cadre gelé (``ui.viewport``), donc ``<html>`` n'a pas de boîte et
    Playwright le juge « hidden ». On teste la CLASSE, pas la visibilité.
    """
    page.wait_for_function(
        "() => document.documentElement.classList.contains('bz-ready')",
        timeout=15000,
    )
    page.wait_for_timeout(400)


#: Les libellés d'étiquette, tels qu'une carte les rend.
#:
#: ⚠️ Ils sont ici pour être ÉCARTÉS. La première version de :func:`titres`
#: prenait la première ligne non vide d'une carte — c'est-à-dire son
#: premier badge d'étiquette dès qu'elle en portait un. Les mesures
#: d'ordre de ce fichier comparaient donc des suites de « Bug / UX /
#: Infra » en croyant comparer des titres. Elles passaient tant que ces
#: suites suffisaient à distinguer deux ordres, et ont rougi le jour où
#: deux cartes ont partagé leur première étiquette : des tests VERTS PAR
#: ACCIDENT, devenus rouges sans que l'app ait bougé d'une ligne.
LIBELLES_ETIQUETTE = {"Bug", "UX", "Perf", "Doc", "Infra"}


def titres(page, zone: str) -> list[str]:
    """Les titres des cartes d'une colonne, dans l'ordre affiché.

    Le titre est la première ligne qui n'est ni une étiquette ni une
    ligne de méta — donc la seule à contenir une espace.
    """
    cartes = page.evaluate(
        """(nom) => Array.from(document.querySelectorAll(
             '[data-bz-dropzone="' + nom + '"] [data-bz-draggable]'
           )).map(n => (n.innerText || '').split('\\n')
                        .map(l => l.trim()).filter(Boolean))""",
        zone,
    )
    return [
        next((ligne for ligne in carte
              if ligne not in LIBELLES_ETIQUETTE and " " in ligne), "")
        for carte in cartes
    ]


def attendre_texte(page, texte: str, delai: int = 8000) -> bool:
    """Attendre que ``texte`` apparaisse. Rend le verdict, ne lève pas.

    ⚠️ **Attendre l'ÉTAT, jamais une durée.** Les zones de cette app
    répondent en 40 à 270 ms selon ce que le serveur re-rend, et une
    écriture d'``AppState`` en re-rend quatre. Un ``wait_for_timeout(900)``
    passait la plupart du temps — et ce « la plupart du temps » est
    exactement ce qui rend un probe non concluant : deux lancements
    consécutifs ont rougi sur deux mesures DIFFÉRENTES du même scénario,
    sans que l'app ait bougé d'une ligne.
    """
    try:
        page.wait_for_function(
            r"(t) => document.body.innerText"
            r".replace(/\s+/g, ' ').includes(t)",
            arg=texte, timeout=delai)
        return True
    except Exception:
        return False


def cartes_de(page, zone: str) -> int:
    return page.locator(
        f'[data-bz-dropzone="{zone}"] [data-bz-draggable]').count()


def choisir(page, actuelle: str, option: str) -> None:
    """Piloter un ``ui.select``.

    ⚠️ Ce n'est PAS un ``<select>`` natif, donc ``select_option`` reste en
    attente jusqu'au bout du délai. Le déclencheur porte ``role=combobox``
    et affiche la valeur courante ; les options n'apparaissent qu'une fois
    la liste ouverte.
    """
    page.get_by_role("combobox").filter(has_text=actuelle).first.click()
    # ⚠️ ``[role=listbox]`` tout court résout QUATRE éléments dès que le
    # tiroir a été ouvert une fois : les listes des overlays restent
    # montées, fermées. Il faut celle qui est VISIBLE.
    liste = page.locator("[role=listbox]:visible").first
    liste.wait_for(state="visible", timeout=5000)
    liste.get_by_role("option").filter(has_text=option).first.click()
    page.wait_for_timeout(900)


def glisser(page, source, zone: str) -> str | None:
    """Faire le geste, et rendre la zone qui CONTIENT la carte au lâcher.

    ⚠️ **Re-viser avant de lâcher.** Le moteur reparente l'élément dans la
    zone survolée pendant le geste, donc les boîtes bougent sous le
    curseur : la coordonnée calculée AVANT le glissement ne désigne plus
    la même zone à l'arrivée.
    """
    cible = page.locator(f'[data-bz-dropzone="{zone}"]')
    depart = source.bounding_box()
    arrivee = cible.bounding_box()
    if not (depart and arrivee):
        return None

    page.mouse.move(depart["x"] + depart["width"] / 2,
                    depart["y"] + depart["height"] / 2)
    page.mouse.down()
    for fraction in (0.3, 0.7, 1.0):
        page.mouse.move(
            depart["x"] + (arrivee["x"] + arrivee["width"] / 2
                           - depart["x"]) * fraction,
            depart["y"] + (arrivee["y"] + 60 - depart["y"]) * fraction,
            steps=8,
        )
    corrigee = cible.bounding_box()
    if corrigee:
        page.mouse.move(corrigee["x"] + corrigee["width"] / 2,
                        corrigee["y"] + 60, steps=8)
    atterrissage = page.evaluate(
        """(function () {
             const item = document.querySelector('[data-bz-dragging]');
             const zone = item && item.closest('[data-bz-dropzone]');
             return zone ? zone.getAttribute('data-bz-dropzone') : null;
           })()"""
    )
    page.mouse.up()
    page.wait_for_timeout(700)
    return atterrissage


# ── ① La mécanique : deux fenêtres, une seule vérité ──────────────────


def le_tableau_est_partage(page_a, page_b) -> None:
    print("\n① Deux fenêtres, une seule vérité")
    for p in (page_a, page_b):
        p.goto(BASE + "/")
        pret(p)

    # La seconde session prend une autre identité : le journal doit dire
    # QUI a fait le geste, pas « quelqu'un ».
    choisir(page_b, "Camille Roux", "Samuel Diallo")

    # Le témoin : s'il survit, la page n'a pas rechargé.
    page_b.evaluate("window.__temoin = 'vivant'")

    avant_b = cartes_de(page_b, "fini")
    source = page_a.get_by_text("Refonte de la page de tarifs").first
    zone = glisser(page_a, source, "fini")
    check("A : la carte est bien lâchée dans « Terminé »", zone == "fini",
          f"lâchée dans {zone!r}")

    try:
        page_b.wait_for_function(
            "(n) => document.querySelectorAll("
            "'[data-bz-dropzone=\"fini\"] [data-bz-draggable]').length === n",
            arg=avant_b + 1, timeout=12000)
        arrivee = True
    except Exception:
        arrivee = False

    check("B voit la carte arriver sans avoir rien fait", arrivee,
          f"{avant_b} → {cartes_de(page_b, 'fini')}")
    check("et B n'a pas rechargé",
          page_b.evaluate("window.__temoin") == "vivant")
    check("le fil d'activité de B dit qui l'a fait",
          page_b.get_by_text("Camille Roux a déplacé").count() >= 1,
          page_b.locator("text=Activité").count() and "aucune ligne")


# ── ② Le serveur arbitre : la limite d'en-cours refuse ────────────────


def la_limite_refuse(page) -> None:
    print("\n② « En cours » est à 3/3 : le dépôt est refusé")
    page.goto(BASE + "/")
    pret(page)

    check("la colonne est bien saturée au départ",
          cartes_de(page, "en_cours") == 3,
          f"{cartes_de(page, 'en_cours')} cartes")

    avant_source = cartes_de(page, "a_faire")
    source = page.get_by_text("Journal d'audit exportable en CSV").first
    glisser(page, source, "en_cours")
    page.wait_for_timeout(900)

    check("« En cours » n'a pas gagné de carte",
          cartes_de(page, "en_cours") == 3,
          f"{cartes_de(page, 'en_cours')} cartes")
    check("et la carte est revenue dans « À faire »",
          cartes_de(page, "a_faire") == avant_source,
          f"{avant_source} → {cartes_de(page, 'a_faire')}")
    check("le refus est DIT, pas silencieux",
          page.get_by_text("Dépôt refusé").count() >= 1)


# ── ③ Réordonner DANS une colonne ─────────────────────────────────────


def reordonner(page) -> None:
    print("\n③ Réordonner dans une colonne")
    page.goto(BASE + "/")
    pret(page)

    avant = titres(page, "a_faire")
    check("la colonne a de quoi réordonner", len(avant) >= 3,
          f"{len(avant)} cartes")
    # Plancher du LECTEUR, pas de l'app. Si ``titres`` rendait autre chose
    # que des titres — ses étiquettes, par exemple — toutes les mesures
    # d'ordre de ce fichier compareraient des suites sans rapport, en
    # restant vertes par accident.
    check("et ce sont bien des titres qu'on lit",
          all(t and t not in LIBELLES_ETIQUETTE for t in avant),
          f"lu : {avant}")
    if len(avant) < 3:
        return

    dernier = page.locator(
        '[data-bz-dropzone="a_faire"] [data-bz-draggable]').last
    boite = page.locator('[data-bz-dropzone="a_faire"]').bounding_box()
    depart = dernier.bounding_box()
    page.mouse.move(depart["x"] + depart["width"] / 2,
                    depart["y"] + depart["height"] / 2)
    page.mouse.down()
    for fraction in (0.3, 0.7, 1.0):
        page.mouse.move(depart["x"] + depart["width"] / 2,
                        depart["y"] + (boite["y"] + 20 - depart["y"])
                        * fraction, steps=8)
    page.mouse.up()
    page.wait_for_timeout(900)

    apres = titres(page, "a_faire")
    check("l'ordre a changé", apres != avant, f"{avant} → {apres}")
    check("aucune carte n'a été perdue en route", len(apres) == len(avant),
          f"{len(avant)} → {len(apres)}")
    check("la carte déplacée est en tête", apres[0] == avant[-1],
          f"tête = {apres[0]!r}, attendu {avant[-1]!r}")

    page.reload()
    pret(page)
    check("et l'ordre survit à un rechargement",
          titres(page, "a_faire") == apres)


# ── ④ Annuler / rétablir ──────────────────────────────────────────────


def annuler_et_refaire(page) -> None:
    print("\n④ Annuler, puis rétablir")
    page.goto(BASE + "/")
    pret(page)

    avant = titres(page, "a_faire")
    page.get_by_role("button", name="Annuler").first.click()
    page.wait_for_timeout(900)
    milieu = titres(page, "a_faire")
    check("annuler défait le dernier geste", milieu != avant,
          f"{avant} → {milieu}")

    page.get_by_role("button", name="Rétablir").first.click()
    page.wait_for_timeout(900)
    check("rétablir le refait à l'identique", titres(page, "a_faire") == avant,
          f"{avant} → {titres(page, 'a_faire')}")


# ── ⑤ Le tiroir de détail ─────────────────────────────────────────────


def ouvert(page) -> bool:
    """Le tiroir est-il déployé ? L'attribut, pas la présence du HTML.

    ⚠️ C'est LA mesure qui manquait : le panneau était bien rendu avec la
    bonne carte dedans, et restait fermé — ``open=`` recevait une
    expression Python, donc le socle ne pouvait plus dire d'où venait la
    valeur et n'émettait pas le marqueur de resynchronisation.
    """
    return page.evaluate(
        """(function () {
             const p = Array.from(document.querySelectorAll(
               '[data-bz-overlay]')).filter(
                 n => n.getBoundingClientRect().width < window.innerWidth);
             return p.some(n => n.getAttribute('data-open') === 'true');
           })()"""
    )


def le_tiroir(page) -> None:
    print("\n⑤ Le tiroir de détail")
    page.goto(BASE + "/")
    pret(page)

    check("au départ, rien n'est déployé", not ouvert(page))
    page.get_by_text("Fusion des comptes en double").first.click()
    attendre_texte(page, "Carte c07")
    page.wait_for_timeout(300)
    check("cliquer une carte DÉPLOIE le tiroir", ouvert(page))
    check("et il porte la bonne carte",
          page.get_by_text("Carte c07").count() >= 1)

    # Cocher une sous-tâche : écriture immédiate, sans « Enregistrer ».
    # ⚠️ Le texte est composé de DEUX éléments — le compteur suit un
    # état client, la constante non — donc ``innerText`` peut glisser un
    # blanc entre eux. Une assertion littérale sur un texte rendu se lit
    # sur la version NORMALISÉE, sinon elle mesure la mise en page.
    check("l'avancement est affiché", attendre_texte(page, "2 sur 3"))
    page.get_by_text("Rejeu de l'historique").click()
    check("cocher une sous-tâche écrit tout de suite",
          attendre_texte(page, "3 sur 3"))

    # Un commentaire.
    page.get_by_placeholder("Écrire un commentaire").fill("Vu, je relis.")
    # ⚠️ Une PAUSE avant d'envoyer, à dessein. Elle mesure que le
    # brouillon SURVIT — un re-rendu venu d'un geste voisin ne doit pas
    # le vider. Sans elle, le probe cliquait si vite qu'il ne laissait à
    # personne le temps de l'effacer, et il est resté vert pendant que le
    # défaut existait.
    page.wait_for_timeout(1500)
    check("le brouillon survit à l'attente",
          page.get_by_placeholder("Écrire un commentaire").input_value()
          == "Vu, je relis.",
          "le champ s'est vidé tout seul")
    page.get_by_role("button", name="Commenter").click()
    check("le commentaire est publié",
          attendre_texte(page, "Vu, je relis."))

    # Le titre attend « Enregistrer », lui.
    # ⚠️ Surtout pas ``get_by_role("textbox").first`` : le premier champ
    # de la page est la RECHERCHE du bandeau, et le probe filtrait donc le
    # tableau avec le titre qu'il croyait enregistrer.
    page.get_by_placeholder("Titre de la carte").fill(
        "Fusion des comptes doublons")
    page.get_by_role("button", name="Enregistrer").click()
    check("le titre enregistré est repris dans le tiroir",
          attendre_texte(page, "Fusion des comptes doublons"))

    page.keyboard.press("Escape")
    page.wait_for_timeout(700)
    check("échapper referme le tiroir", not ouvert(page))
    check("et le tableau porte le nouveau titre",
          page.locator('[data-bz-dropzone="en_cours"]').inner_text().find(
              "Fusion des comptes doublons") >= 0,
          page.locator('[data-bz-dropzone="en_cours"]').inner_text()[:80])
    page.reload()
    pret(page)
    check("et la fermeture est connue du serveur", not ouvert(page))


# ── ⑥ Les filtres ─────────────────────────────────────────────────────


def les_filtres(page) -> None:
    print("\n⑥ Filtrer sans perdre le tableau")
    page.goto(BASE + "/")
    pret(page)
    total = sum(cartes_de(page, z)
                for z in ("a_faire", "en_cours", "en_revue", "fini"))

    choisir(page, "Toute l'équipe", "Noa Berger")
    restant = sum(cartes_de(page, z)
                  for z in ("a_faire", "en_cours", "en_revue", "fini"))
    check("filtrer par personne réduit l'affichage", 0 < restant < total,
          f"{total} → {restant}")

    check("les colonnes disent encore leur occupation RÉELLE",
          page.get_by_text("3 / 3").count() >= 1,
          "la limite compte le travail, pas ce que le filtre laisse voir")

    choisir(page, "Noa Berger", "Toute l'équipe")
    check("et retirer le filtre rend tout",
          sum(cartes_de(page, z)
              for z in ("a_faire", "en_cours", "en_revue", "fini")) == total)


# ── La bande d'archivage : elle reçoit, et elle ne BOUGE pas ─────────


def la_bande_darchive(page) -> None:
    print("\n⑦ Archiver en lâchant sur la bande")
    page.goto(BASE + "/")
    pret(page)

    def boite_bande():
        return page.evaluate(
            """() => {
                 const z = document.querySelector(
                   '[data-bz-dropzone=\"archive\"]');
                 const r = z.getBoundingClientRect();
                 return [Math.round(r.width), Math.round(r.height)];
               }""")

    avant_taille = boite_bande()
    avant = cartes_de(page, "a_faire")
    source = page.get_by_text("Guide de démarrage en dix minutes").first
    cible = page.locator('[data-bz-dropzone="archive"]')
    depart, arrivee = source.bounding_box(), cible.bounding_box()
    check("la bande existe et la carte aussi", bool(depart and arrivee),
          f"{depart} / {arrivee}")
    if not (depart and arrivee):
        return

    page.mouse.move(depart["x"] + depart["width"] / 2,
                    depart["y"] + depart["height"] / 2)
    page.mouse.down()
    for fraction in (0.3, 0.7, 1.0):
        page.mouse.move(
            depart["x"] + (arrivee["x"] + arrivee["width"] / 2
                           - depart["x"]) * fraction,
            depart["y"] + (arrivee["y"] + arrivee["height"] / 2
                           - depart["y"]) * fraction,
            steps=8)
    page.wait_for_timeout(400)

    # ⚠️ LA mesure de ce scénario. Le moteur reparente le nœud déplacé
    # dans la zone survolée : une zone qui se laisse dimensionner par ce
    # qu'elle héberge grandit de la taille d'une carte AU MOMENT où on
    # vise. Mesuré sur la version d'avant, posée dans le bandeau : 104×32
    # → 362×105, et toute la barre poussée de 73 px.
    pendant = boite_bande()
    check("la bande ne grandit pas quand elle accueille la carte",
          pendant == avant_taille, f"{avant_taille} → {pendant}")

    page.mouse.up()
    page.wait_for_timeout(1000)
    check("la carte a quitté le tableau", cartes_de(page, "a_faire") == avant - 1,
          f"{avant} → {cartes_de(page, 'a_faire')}")
    check("et le journal le dit",
          page.get_by_text("a archivé").count() >= 1)


# ── ⑧ Les cinq mesures minimales de la discipline #3 ──────────────────


def le_socle_visuel(page) -> None:
    print("\n⑧ Document gelé, couleurs, tailles, tabulation, capture")
    page.goto(BASE + "/")
    pret(page)

    mesures = page.evaluate(
        """(function () {
             const doc = document.documentElement;
             const zones = Array.from(document.querySelectorAll(
               '[data-bz-dropzone]')).filter(z => z.id !== 'archive');
             const badges = Array.from(document.querySelectorAll(
               '[data-bz-dropzone] span')).slice(0, 40);
             return {
               page_defile: doc.scrollHeight > doc.clientHeight,
               corps_defile: document.body.scrollHeight >
                             document.body.clientHeight,
               zones_dans_lecran: zones.every(z => {
                 const r = z.getBoundingClientRect();
                 return r.bottom <= window.innerHeight + 2;
               }),
               couleurs: Array.from(new Set(badges.map(
                 b => getComputedStyle(b).color))).length,
               tailles: Array.from(new Set(badges.map(
                 b => getComputedStyle(b).fontSize))).length,
             };
           })()"""
    )
    check("le document ne défile pas", not mesures["page_defile"])
    check("pas de seconde barre sur le corps", not mesures["corps_defile"])
    check("toutes les colonnes tiennent dans l'écran",
          mesures["zones_dans_lecran"])
    check("les étiquettes ont des couleurs distinctes",
          mesures["couleurs"] >= 3, f"{mesures['couleurs']} couleurs")
    check("et des tailles distinctes de leur voisinage",
          mesures["tailles"] >= 2, f"{mesures['tailles']} tailles")

    # Ordre de tabulation : la recherche vient avant les filtres.
    page.keyboard.press("Tab")
    ordre = []
    for _ in range(4):
        ordre.append(page.evaluate(
            "document.activeElement.getAttribute('placeholder') "
            "|| document.activeElement.tagName"))
        page.keyboard.press("Tab")
    check("le clavier atteint la recherche dans les quatre premiers arrêts",
          "Rechercher une carte" in ordre, f"ordre = {ordre}")

    page.screenshot(path=str(HERE / "_shots" / "kanban.png"))
    check("capture écrite", (HERE / "_shots" / "kanban.png").exists())


def les_deux_themes(page) -> None:
    print("\n⑨ Les deux thèmes")
    page.goto(BASE + "/")
    pret(page)
    clair = page.evaluate(
        "getComputedStyle(document.body).backgroundColor")
    page.get_by_role("button", name="Passer en sombre").first.click()
    page.wait_for_timeout(800)
    sombre = page.evaluate(
        "getComputedStyle(document.body).backgroundColor")
    check("le fond change vraiment de thème", clair != sombre,
          f"{clair} == {sombre}")
    check("et la classe est posée",
          page.evaluate(
              "document.documentElement.classList.contains('dark')"))


def l_anglais_est_le_defaut(browser, taille) -> None:
    """Un visiteur sans cookie reçoit l'ANGLAIS — chrome ET cartes.

    Un contexte NEUF, donc une session neuve : c'est la seule façon de
    voir la graine dans l'autre langue, puisqu'elle est tirée une fois
    par session (``donnees.graine``).
    """
    print("\n⓪ L'anglais est le défaut, cartes comprises")
    ctx = browser.new_context(viewport=taille)
    page = ctx.new_page()
    page.goto(BASE + "/")
    pret(page)
    check("le bandeau est en anglais",
          page.get_by_text("Client portal rework").count() >= 1)
    check("les colonnes aussi",
          page.get_by_text("To do", exact=True).count() >= 1)
    check("et les cartes semées — c'est ce qu'un dict de traduction "
          "posé trop tard raterait",
          page.get_by_text("Sign-in screen: forgotten password").count() >= 1)
    check("le sélecteur de langue est là",
          page.get_by_role("button", name="Language").count() >= 1)
    ctx.close()


def main() -> int:
    (HERE / "_shots").mkdir(exist_ok=True)
    server = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "examples.kanban.main:app",
            "--host", "127.0.0.1", "--port", str(PORT),
        ],
        cwd=REPO,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            taille = {"width": 1500, "height": 940}
            # DEUX contextes : deux jarres de cookies, donc deux sessions,
            # donc deux personnes. Deux onglets d'un même contexte
            # partageraient l'identité et ne prouveraient pas grand-chose.
            ctx_a = browser.new_context(viewport=taille)
            ctx_b = browser.new_context(viewport=taille)
            # ⚠️ Les deux contextes sont mis en FRANÇAIS avant le
            # premier rendu. L'app est bilingue depuis le 2026-09-20 et
            # sert l'ANGLAIS par défaut ; ce probe, lui, est écrit en
            # français — ses six cents lignes de sélecteurs citent les
            # libellés et les titres de cartes. Le cookie est posé avant
            # le premier ``goto`` parce que la graine du tableau est
            # tirée au PREMIER rendu de la session : arrivée trop tard,
            # elle traduirait le chrome et laisserait les cartes en
            # anglais. La langue par défaut a sa propre vérification,
            # ``l_anglais_est_le_defaut``.
            for ctx in (ctx_a, ctx_b):
                ctx.add_cookies([{
                    "name": "bz_lang", "value": "fr",
                    "url": BASE,
                }])
            page_a, page_b = ctx_a.new_page(), ctx_b.new_page()

            l_anglais_est_le_defaut(browser, taille)

            le_tableau_est_partage(page_a, page_b)
            ctx_b.close()

            la_limite_refuse(page_a)
            reordonner(page_a)
            annuler_et_refaire(page_a)
            le_tiroir(page_a)
            les_filtres(page_a)
            la_bande_darchive(page_a)
            le_socle_visuel(page_a)
            les_deux_themes(page_a)

            ctx_a.close()
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAIL")
        for line in FAILURES:
            print("  -", line)
        return 1
    print("Tout vert.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
