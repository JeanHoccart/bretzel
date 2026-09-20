"""Probe — la messagerie tient ses deux promesses.

Ce que ça mesure, et pourquoi ``TestClient`` ne le mesure pas
-------------------------------------------------------------
Un GET rendu par ``TestClient`` prouve que Python a sérialisé du HTML. Il
ne dit rien de ce qui fait l'exemple :

- l'adresse est-elle RÉÉCRITE quand on ouvre un message, sans
  rechargement — c'est du ``history.pushState``, donc du navigateur ;
- la flèche retour ramène-t-elle à la vue d'avant ;
- le document est-il vraiment GELÉ (aucune barre au niveau de la page)
  pendant que trois régions défilent chacune de leur côté ;
- un glisser-déposer, qui n'existe qu'en gestes de souris.

Le premier probe porté sur ``bretzel.probe`` (2026-09-11)
---------------------------------------------------------
La moitié de l'ancien fichier n'était pas ce qu'il mesure : lancer
uvicorn sur un port en dur, attendre qu'il réponde, ouvrir Playwright,
définir son propre ``check``, accumuler ses rouges, rendre un code de
sortie. C'était l'état de ``tests/probes/`` — 146 fichiers, 21 898
lignes, 75 qui ouvrent Playwright, 64 qui lancent un serveur, 66 qui
redéfinissent ``check``. Le harnais donne les AXES ; ce fichier ne garde
que le SCÉNARIO.

⚠️ Il ne fait pas moins de lignes pour autant — 545 avant, 549 après.
Le portage ne fait pas maigrir un fichier, il change ce que ses lignes
contiennent. Ce qui a grandi, c'est le nombre de CONSTATS : les deux
versions ont été lancées, 34 avant, 42 après, dont 11 que personne n'a
écrits.

Ce que le portage a rendu en plus, sans une ligne écrite ici : les
erreurs JS, les requêtes en échec et les avertissements de console sont
désormais ASSERTÉS — l'ancien harnais se contentait de les imprimer, et
178 exceptions ont vécu deux jours dans une sortie que personne ne lit ;
la page est mesurée à une SECONDE taille ; les deux thèmes sont
capturés ; et la tabulation est relue à la fin, y compris la règle « pas
dans un overlay fermé » que ce probe même a fait naître le 2026-09-07.

Deux mesures que le harnais rend possibles et que l'ancien ne faisait
pas : le COÛT RÉSEAU d'un geste — la recherche cliente doit coûter zéro
requête, ce que l'ancien ne pouvait qu'inférer du DOM, et un rangement
en coûte exactement une — et la vérification du point d'atterrissage
d'un glisser, que l'ancien portait à la main et que
:meth:`bretzel.probe.Window._assert_landed` rend générale.

Run :  py tests/probes/probe_messagerie.py
       py -m pytest tests/probes/probe_messagerie.py -m probes
"""

from __future__ import annotations

import sys
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeout

from bretzel.probe import Probe, Window, probe

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

APP = "examples.messagerie.main:app"

#: Le corps du formulaire de rédaction — nommé une fois, lu trois.
CORPS = 'textarea[placeholder="Your message…"]'

#: La recherche est un ``ui.filter_each`` client : les lignes restent
#: dans le DOM et se cachent, donc c'est le compte de VISIBLES qui bouge.
VISIBLES = "[data-bz-draggable]:visible"

#: La couleur du TITRE, et surtout pas celle du corps ni de la racine :
#: dans une coque gelée le ``ui.viewport`` ne peint pas et ``<html>`` ne
#: porte aucune couleur (mesuré : ``rgb(0, 0, 0)`` dans les deux thèmes).
#: Le titre, lui, est en ``text-text`` — que les DEUX palettes définissent.
COULEUR_TITRE = "getComputedStyle(document.querySelector('h1')).color"

#: L'ordre des lignes, par clé. Sert deux fois, sur la même liste.
ORDRE_JS = """
Array.from(document.querySelectorAll('[data-bz-draggable]'))
  .map(function (n) { return n.getAttribute('data-bz-key'); })
"""


def params(w: Window) -> dict[str, str]:
    """Les paramètres de l'adresse affichée, à plat."""
    brut = parse_qs(urlparse(w.page.url).query)
    return {cle: valeurs[0] for cle, valeurs in brut.items()}


def bouton(nom: str) -> str:
    """Un bouton par son nom accessible."""
    return f'role=button[name="{nom}"]'


def devient_vrai(w: Window, expr: str, *, timeout: int = 5000) -> bool:
    """L'attente EST la mesure : vrai dès que ``expr`` l'est, faux au bout.

    Un constat qui LIT juste après un geste lit parfois l'état d'avant.
    Mesuré ici sur la bascule de thème : la classe ``dark`` arrive sur
    ``<html>`` avant que le moteur n'ait recalculé la feuille, donc un
    ``getComputedStyle`` dans la foulée rend la couleur précédente —
    2 rouges sur 13 lancements, jamais les mêmes.

    Attendre la CONDITION plutôt que l'événement supprime la course sans
    rien endormir : l'expiration n'est pas avalée, elle devient le rouge.
    """
    try:
        w.page.wait_for_function(expr, timeout=timeout)
    except PlaywrightTimeout:
        return False
    return True


def apparait(w: Window, sel: str, *, timeout: int = 5000) -> bool:
    """Même idée que :func:`devient_vrai`, pour un SÉLECTEUR.

    Un ``wait_for_selector`` nu lève, donc il avorte le scénario : pas de
    ligne rouge, et le balayage de sortie ne tourne jamais. Rendre un
    booléen le range dans un ``p.check``, qui est ce qu'on voulait dire.
    """
    try:
        w.page.wait_for_selector(sel, timeout=timeout)
    except PlaywrightTimeout:
        return False
    return True


def adresse_est_la_vue(p: Probe, a: Window) -> None:
    """① La mécanique de l'exemple : l'adresse dit ce qu'on regarde."""
    print("\n① L'adresse EST la vue")
    a.goto("/")

    p.check(
        "le runtime a fini son boot",
        devient_vrai(a, "document.documentElement.classList.contains('bz-ready')"),
        "`html.bz-ready` n'est jamais arrivé",
    )
    p.check(
        "au départ, aucune conversation dans l'adresse",
        "thread" not in params(a),
        a.page.url,
    )
    p.check("l'état vide est affiché", a.has("text=No conversation open"))

    # L'identifiant n'est PAS écrit en dur : le seed peut être renuméroté
    # (il l'a été, pour que « id croissant » veuille dire « plus récent »)
    # et un probe qui épingle une clé en dur rougirait pour une raison
    # qui n'a rien à voir avec ce qu'il mesure.
    a.click("text=The shed 3 drawings")
    ecrit = devient_vrai(a, "new URL(location.href).searchParams.has('thread')")
    premier = params(a).get("thread", "")
    p.check(
        "ouvrir une conversation écrit sa clé dans l'adresse",
        ecrit and bool(premier) and " " not in premier,
        params(a),
    )
    p.check(
        "le corps du message est affiché",
        a.has("text=Can you confirm the slab"),
    )

    # ⚠️ Le point que seul un navigateur peut mesurer : l'adresse a changé
    # SANS rechargement. Un marqueur posé sur ``window`` avant le clic
    # survit à un pushState et meurt à un rechargement.
    a.page.evaluate("window.__temoin = 42")
    a.click("text=Delivery slot on Tuesday")
    devient_vrai(
        a, f"new URL(location.href).searchParams.get('thread') !== {premier!r}"
    )
    p.check(
        "passer d'un message à l'autre ne recharge pas la page",
        a.page.evaluate("window.__temoin") == 42,
        "le témoin a disparu : il y a eu un rechargement",
    )

    # ⚠️ Attendre le CONTENU, pas l'adresse. Au ``popstate`` le navigateur
    # réécrit l'URL AVANT d'avoir demandé quoi que ce soit au serveur :
    # une sonde qui s'accroche à ``location`` lit donc l'état d'avant la
    # réponse et rend un faux rouge. C'est ce qui est arrivé ici la
    # première fois — l'app était juste, la mesure non.
    a.page.go_back()
    revenu = apparait(a, "text=Can you confirm the slab", timeout=8000)
    p.check(
        "la flèche retour ramène au message précédent",
        revenu and params(a).get("thread") == premier,
        a.page.url,
    )
    p.check(
        "et le contenu suit l'adresse",
        a.has("text=Can you confirm the slab"),
    )

    a.goto("/?folder=archive")
    p.check(
        "une adresse tapée à la main ouvre le bon dossier",
        a.has("text=Planning permission"),
    )


def document_gele(p: Probe, a: Window) -> None:
    """② Le document ne défile pas ; ses trois régions, oui.

    Le balayage du harnais mesure déjà le débordement LATÉRAL et le fait
    qu'aucune région ne finisse sous le bord. Ce qui reste ici est la
    mécanique de l'app : le document est gelé sur les DEUX axes, et il
    délègue le défilement à trois régions.
    """
    print("\n② Le document est gelé, les régions défilent")
    a.goto("/?folder=inbox&thread=the-shed-3-drawings")

    # Le VERTICAL seulement : le balayage asserte déjà l'horizontal, à
    # deux tailles. Le remesurer ici donnerait deux rouges pour une faute.
    trop_haut = a.page.evaluate(
        "document.documentElement.scrollHeight - "
        "document.documentElement.clientHeight"
    )
    p.check(
        "le document ne défile pas verticalement",
        trop_haut <= 1,
        f"{trop_haut} px de trop",
    )

    regions = a.page.evaluate(
        """
        Array.from(document.querySelectorAll('main *')).filter(function (el) {
            const s = getComputedStyle(el);
            return (s.overflowY === 'auto' || s.overflowY === 'scroll')
                   && el.clientHeight > 100;
        }).length
        """
    )
    p.check(
        "trois régions défilent chacune de leur côté",
        regions >= 3,
        f"{regions} région(s) à défilement propre",
    )


def couleurs_et_tailles(p: Probe, a: Window) -> None:
    """③ Ce que le balayage ne peut pas savoir : les formes de CETTE app.

    Le balayage relit la tabulation à la fin, mais il ne connaît ni les
    dossiers ni les lignes de message. Les trois attentes de forme —
    quatre dossiers, deux lignes, rien d'inerte — restent donc ici.
    """
    print("\n③ Couleurs, tailles, tabulation")
    a.goto("/?folder=inbox")

    fond = a.page.evaluate(
        """
        (function () {
            const liens = Array.from(
                document.querySelectorAll('a[href*="folder="]'));
            const actif = liens.find(
                a => a.getAttribute('href').includes('inbox'));
            const autre = liens.find(
                a => a.getAttribute('href').includes('archive'));
            return {actif: getComputedStyle(actif).backgroundColor,
                    autre: getComputedStyle(autre).backgroundColor};
        })()
        """
    )
    p.check(
        "le dossier ouvert ne se peint pas comme les autres",
        fond["actif"] != fond["autre"],
        fond,
    )

    # ⚠️ « plusieurs paliers de taille de texte coexistent » vivait ici et
    # a été retiré le 2026-09-11 : n'importe quelle page avec un titre et
    # du corps le passe. ``_sweep`` refuse le même constat pour la même
    # raison — une ligne verte qui ne mesure rien coûte plus qu'elle ne
    # rapporte. Le fond du dossier actif, au-dessus, est spécifique à
    # CETTE app et reste.

    # L'ordre de tabulation, relevé sur huit pas plutôt que sur un seul :
    # ce qui compte n'est pas qu'UN élément prenne le focus, c'est que les
    # commandes de l'app soient toutes joignables au clavier.
    #
    # La fuite vers un overlay FERMÉ — trouvée ici le 2026-09-07, réparée
    # le 2026-09-10 — n'est plus relue à la main : le balayage du harnais
    # la porte pour toute app, et une gate composant tient les quatre
    # familles d'overlay.
    # ⚠️ Le filtre « hors dialogue » qui vivait ici est parti le
    # 2026-09-11 : cette app ne rend AUCUN ``role=dialog`` — son panneau
    # de rédaction n'est pas un ``ui.dialog`` (``features/inbox.py``) —
    # donc il ne retirait jamais rien. Il aurait en plus absorbé une
    # vraie fuite pendant que le balayage, lui, rougissait.
    arrets = []
    for _ in range(8):
        a.press("Tab")
        arrets.append(a.page.evaluate("document.activeElement.tagName"))
    p.check(
        "les quatre dossiers sont joignables au clavier",
        arrets.count("A") >= 4,
        f"arrêts : {arrets}",
    )
    p.check(
        "les lignes de message aussi",
        arrets.count("BUTTON") >= 2,
        f"arrêts : {arrets}",
    )
    p.check(
        "aucun arrêt sur un élément non interactif",
        all(t in ("A", "BUTTON", "INPUT", "TEXTAREA") for t in arrets),
        f"arrêts : {arrets}",
    )


def glisser_vers_un_dossier(p: Probe, a: Window) -> None:
    """④ Le verbe principal d'une messagerie : ranger."""
    print("\n④ Glisser un message vers un dossier")
    a.goto("/?folder=inbox")

    avant = a.count("[data-bz-draggable]")
    # Le point d'atterrissage n'est plus vérifié ici : ``Window.drag``
    # refuse de lâcher ailleurs que dans la cible et lève en nommant la
    # zone réelle. C'est ce qui manquait quand le message finissait dans
    # « Envoyés » pendant que le probe visait « Archives » — le rouge
    # tombait alors sur l'app, deux constats plus bas.
    with p.requests() as net:
        a.drag(
            "text=Highway permit",
            '[data-bz-dropzone="folder-archive"]',
        )

    apres = a.count("[data-bz-draggable]")
    p.check(
        "le message a quitté la liste des reçus",
        apres == avant - 1,
        f"{avant} → {apres}",
    )
    p.check("un rangement coûte UNE écriture", net.total == 1, net.urls)

    a.goto("/?folder=archive")
    p.check(
        "et il est arrivé dans les archives",
        a.has("text=Highway permit"),
    )


def les_trois_defauts_signales(p: Probe, a: Window) -> None:
    """⑤ Les trois défauts que l'utilisateur a vus, en mesures.

    Chacun est parti d'une capture d'écran, pas d'un test. Ils sont ici
    pour ne pas revenir — c'est la règle 8 du charter appliquée à une
    app : un défaut réparé sans mesure redérive.
    """
    print("\n⑤ Les trois défauts signalés")

    # ① « Pourquoi quand je clique sur un mail il apparaît tout en bas ? »
    #    Le tri mettait les non-lus en tête : ouvrir un message le marquait
    #    lu, donc il changeait de groupe et descendait sous le curseur.
    a.goto("/?folder=inbox")

    # ⚠️ Il FAUT un message non lu pour que la mesure morde. Les scénarios
    # précédents ont ouvert la boîte, donc tout y est lu — et un tri fautif
    # « non-lus d'abord » ne déplacerait alors rien du tout. Vérifié par
    # mutation : sans cette remise à non-lu, restaurer le vieux tri
    # laissait la mesure VERTE.
    a.click("text=Minutes of the site meeting")
    a.click(bouton("Mark unread"))
    remis = apparait(a, "[data-bz-draggable] .bg-primary")
    a.click(bouton("Back to the list"))

    avant = a.page.evaluate(ORDRE_JS)
    a.click("text=Minutes of the site meeting")
    ouvert = apparait(a, bouton("Reply"))
    apres = a.page.evaluate(ORDRE_JS)
    p.check(
        "ouvrir un message non lu ne change PAS sa place dans la liste",
        remis and ouvert and apres == avant,
        f"{avant} → {apres}" if remis else "la remise à non lu n'a pas pris",
    )

    # ② « Aucun filtre. » La recherche filtre sur expéditeur, sujet, corps.
    #    Elle est CLIENTE, et c'est le compte de REQUÊTES qui le prouve —
    #    l'ancien probe ne pouvait que l'inférer du nombre de nœuds.
    a.goto("/?folder=inbox")
    dans_le_dom = a.count("[data-bz-draggable]")
    recherche = 'input[placeholder="Search the messages"]'
    with p.requests() as net:
        a.type(recherche, "shed 3")
    restants, encore_la = a.count(VISIBLES), a.count("[data-bz-draggable]")
    p.check(
        "la recherche réduit la liste",
        restants == 1,
        f"{dans_le_dom} → {restants}",
    )
    p.check("sans consulter le serveur : zéro requête", net.total == 0, net.urls)
    p.check(
        "les lignes restent dans le DOM",
        encore_la == dans_le_dom,
        f"{dans_le_dom} → {encore_la}",
    )

    # ⚠️ ``fill`` et pas ``a.type`` : le champ porte déjà « shed 3 », et
    # ``type`` frappe SANS effacer. Le harnais n'a pas de verbe pour vider
    # un champ — le seul trou que ce portage ait rencontré.
    a.page.fill(recherche, "zzzz")
    p.check(
        "et l'état vide de la recherche est client, lui aussi",
        apparait(a, "text=No result"),
        "« Aucun résultat » n'est jamais venu",
    )
    a.page.fill(recherche, "")

    # ③ « Je peux marquer non lu un message ENVOYÉ ??? »
    # ⚠️ Il faut un fil PUREMENT sortant. Depuis que l'unité est la
    # conversation, un fil d'« Envoyés » contient aussi les messages
    # reçus qui l'ont provoqué — et « marquer non lu » y a du sens. Seul
    # un message envoyé resté sans réponse exerce la règle. Le seed en
    # porte un exprès (``relance_sans_reponse``).
    a.goto("/?folder=sent&thread=is-the-concrete-pump-free")
    p.check(
        "une conversation purement sortante n'offre pas « marquer non lu »",
        apparait(a, bouton("Reply")) and a.count(bouton("Mark unread")) == 0,
    )
    a.goto("/?folder=inbox")
    a.click("text=Delivery slot on Tuesday")
    p.check(
        "un message reçu, lui, l'offre",
        apparait(a, bouton("Reply")) and a.count(bouton("Mark unread")) == 1,
    )


def la_redaction(p: Probe, a: Window) -> None:
    """⑥ Écrire : l'envoi, la validation d'adresse, les trois tailles."""
    print("\n⑥ La rédaction")
    a.goto("/?folder=inbox")

    # ① Une adresse invalide ne part pas — et le DIT.
    a.click(bouton("New message"))
    a.type('input[placeholder="To"]', "pas-une-adresse")
    a.type('input[placeholder="Subject"]', "Refusé")
    a.click(bouton("Send"))
    p.check(
        "une adresse invalide est refusée, avec le motif",
        apparait(a, "text=valid address"),
        "aucun motif affiché",
    )

    # ② Les trois tailles changent VRAIMENT la boîte du panneau.
    panneau = "[data-bz-zone]:has(input[type=email])"
    normal = a.box(panneau)
    a.click(bouton("Full screen"))
    p.check(
        "« plein écran » agrandit le panneau",
        devient_vrai(
            a,
            "document.querySelector('[data-bz-zone] input[type=email]')"
            ".closest('[data-bz-zone]').getBoundingClientRect().width > "
            f"{normal.width}",
        ),
        f"le panneau est resté à {int(normal.width)} px",
    )

    a.click(bouton("Leave full screen"))
    a.click(bouton("Shrink"))
    p.check(
        "« réduire » retire le corps du formulaire",
        devient_vrai(a, f"!document.querySelector({CORPS!r})"),
        "le corps est encore rendu",
    )
    a.click(bouton("Enlarge"))

    # ③ Un envoi valide arrive dans « Envoyés » — et s'y AFFICHE.
    #    ⚠️ Ce trajet manquait, et c'est là qu'un `KeyError: 'court'` est
    #    passé en production : le message créé par le handler ne portait
    #    pas un champ que le seed avait, et la liste d'« Envoyés » levait.
    a.page.fill('input[placeholder="To"]', "me@northgate-works.com")
    a.page.fill('input[placeholder="Subject"]', "Control message")
    a.type(CORPS, "Corps du message.")
    a.click(bouton("Send"))
    p.check(
        "un envoi valide referme le panneau",
        devient_vrai(
            a, "!document.querySelector('[data-bz-zone] input[type=email]')"
        ),
        "le panneau est resté ouvert",
    )

    # ⚠️ Le constat « sans lever » vivait ici, et il est parti le
    # 2026-09-11 : un rendu qui lève est un 5xx, et le balayage asserte
    # « aucune requête en échec » pour toute la fenêtre. Le TRAJET, lui,
    # reste — c'est lui qui manquait le jour du `KeyError`.
    a.goto("/?folder=sent")
    p.check(
        "et le message s'affiche dans « Envoyés »",
        a.count("text=Control message") >= 1,
    )


def les_deux_themes(p: Probe, a: Window) -> None:
    """⑦ Le bascule clair/sombre.

    Les deux visions doivent se valider sans bricoler : un exemple qui
    n'offre pas de bascule oblige à changer la préférence de l'OS pour
    voir sa moitié sombre — ce qui n'arrive jamais, donc la moitié
    sombre n'est jamais regardée.

    Les CAPTURES des deux thèmes, elles, ne sont plus prises ici : le
    balayage du harnais les prend pour toute app, à la sortie du ``with``.
    """
    print("\n⑦ Les deux thèmes")
    a.goto("/?thread=the-shed-3-drawings")

    sombre = "document.documentElement.classList.contains('dark')"
    depart = a.page.evaluate(sombre)
    teinte_depart = a.css("h1", "color")

    a.click(bouton("Switch to light" if depart else "Switch to dark"))
    p.check(
        "le bascule change bien de thème",
        devient_vrai(a, f"{sombre} === {str(not depart).lower()}"),
        f"la classe `dark` est restée à {depart}",
    )
    p.check(
        "et la palette suit",
        devient_vrai(a, f"{COULEUR_TITRE} !== {teinte_depart!r}"),
        f"couleur inchangée : {teinte_depart}",
    )

    # Remettre la préférence à « celle du système » AVANT de rendre la
    # main. Le balayage capture les deux thèmes en ÉMULANT la préférence
    # de l'OS, et le choix rangé dans ``localStorage`` par la bascule la
    # supplanterait : la capture « clair » rendrait l'app en sombre.
    a.page.evaluate("localStorage.removeItem('$bz:ColorScheme.default')")
    a.page.reload()
    a.settle(floor=0)


def main() -> None:
    with probe(APP) as p:
        (a,) = p.windows
        adresse_est_la_vue(p, a)
        document_gele(p, a)
        couleurs_et_tailles(p, a)
        glisser_vers_un_dossier(p, a)
        les_trois_defauts_signales(p, a)
        la_redaction(p, a)
        les_deux_themes(p, a)


# Pas de fonction ``test_*`` ici, et c'est voulu : ``tests/probes/
# test_probes.py`` lance CHAQUE probe en sous-processus et juge son code
# de sortie. Une seconde porte d'entrée le ferait collecter aussi par le
# run rapide — qui n'a ni marqueur ``probes`` ni Chromium à y consacrer.
if __name__ == "__main__":
    main()
