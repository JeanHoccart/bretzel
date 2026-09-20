"""Probe — ``examples/ecole`` : ce que chaque lot doit tenir à l'écran.

Ce que ça mesure, et pourquoi ``TestClient`` ne le mesure pas
-------------------------------------------------------------
Un GET rendu par ``TestClient`` prouve que Python a sérialisé du HTML.
Les quatre choses que le lot 1 doit tenir n'y sont pas :

- **EF-U2** — changer d'année dans la barre latérale doit changer LES
  DEUX : le sélecteur et le contenu de la page. C'est le silence B2 de
  ``livrer-une-app.md`` — un état mutable lu dans une coque est GELÉ —
  et il ne se voit qu'en cliquant ;
- **RT-1** — l'année en consultation doit le DIRE sur l'écran, et le
  bandeau doit disparaître quand on revient ;
- **EF-U3** — *« rien ne s'affiche sous 19 px »*, dont le plancher
  LITTÉRAL a été retiré le 2026-09-12 (cf. ``examples/ecole/core/
  theme.py``) : la mesure reste, son sujet change. Elle gèle désormais
  les genres de texte que la COQUE peint sous la taille de base, en
  ``getComputedStyle`` sur chaque nœud visible — une taille vient d'une
  feuille compilée, pas d'un attribut Python ;
- **EF-U4** — le bouton de plein écran doit être joignable depuis la
  coque.

Le balayage de ``bretzel.probe`` fait le reste sans qu'on l'écrive :
erreurs JS, requêtes en échec, débordement à deux tailles, ordre de
tabulation, les deux thèmes, les captures.

Run :  py tests/probes/probe_ecole.py
       py -m pytest tests/probes/probe_ecole.py -m probes
"""

from __future__ import annotations

import contextlib
import re
import sys
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeout

from bretzel.probe import Probe, Window, probe

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

APP = "examples.ecole.main:app"

#: L'écart de hauteur ENCORE TOLÉRÉ entre deux contrôles de formulaire.
#:
#: ⚠️ **Ce n'est pas une marge de confort, c'est un défaut gelé.**
#: Mesuré le 2026-09-12 : ``/reglages`` et ``/cahier`` rendent des cadres
#: de champ à 31 ET 33 px, alors que l'app ne pose aucun ``size=`` et que
#: son thème ne retaille aucun contrôle. Deux pixels, sur l'élément
#: BORDÉ des deux côtés — donc pas l'erreur de mesure classique (celle-là
#: est déjà écartée, cf. le sélecteur du constat).
#:
#: **La cause n'est pas établie.** La piste : le framework garde cette
#: parité par ``tests/runtime_js/test_form_controls_share_one_height.py``,
#: qui mesure **avec le thème livré**. Cette app déplace ``--spacing``
#: (0,205 rem), donc ``h-10`` vaut 32,8 px et plus 40 — un palier qui
#: tombe entre deux pixels. Une famille de contrôles qui arrondit d'un
#: côté et l'autre de l'autre rendrait exactement cet écart.
#:
#: Ce que le constat achète en attendant : l'écart ne peut plus
#: GRANDIR. Il valait 8 px le matin même (30, 32, 36 et 38 sur un seul
#: écran), parce que le thème de l'app retaillait onze composants et en
#: oubliait deux — ça, c'est réparé, et gaté côté framework par la règle
#: ``half-overridden-size-step``.
#:
#: **Le nombre ne peut que DESCENDRE.**
RESIDU = 2

#: Le plus petit palier de l'échelle de l'app, en pixels CSS.
#:
#: ⚠️ **Ce chiffre a bougé DEUX fois le 2026-09-12, et les deux fois
#: parce que l'utilisateur a tranché devant l'écran.** 19 px d'abord,
#: par EF-U3 — *« rien ne s'affiche sous 19 px, la tablette est un poste
#: de travail »* — tenu en déplaçant la racine typographique. Puis
#: *« c'est trop gros »* : la semaine sortait de l'écran, l'exigence
#: était tenue à la lettre et son intention ratée. Puis *« kanban est
#: plus compact »*, et l'app a pris l'échelle du kanban — devenue
#: ``bretzel.theme.presets.COMPACT`` le 2026-09-13.
#:
#: Donc 10 px, qui est le plus petit palier que le préréglage laisse
#: atteindre (``badge`` en ``xs``). Ce n'est plus une exigence de
#: lisibilité, c'est un garde-fou : sous ce chiffre, un composant a
#: échappé à l'échelle de l'app, ce qui ne peut pas être voulu.
PLANCHER = 10

#: Combien de GENRES de texte sous le plancher l'app a le droit de
#: rendre. **Zéro**, et c'est tenable depuis qu'elle a une échelle.
#:
#: ⚠️ Ce nombre valait SIX jusqu'à l'échelle, et l'histoire vaut d'être
#: gardée : le plancher était alors à 16 px, six thèmes de composant
#: écrivaient ``text-xs`` ou ``text-sm`` en dur, et geler leur nombre
#: était tout ce qu'on pouvait faire. L'échelle a rendu la question
#: caduque en descendant l'échelle sous eux — ce n'est pas le gel qui a
#: été gagné, c'est le sujet qui a disparu.
#:
#: **Le nombre ne peut que DESCENDRE**, et il est à zéro : il ne peut
#: donc plus que rougir.
GENRES_SOUS_LE_PLANCHER = 0

#: Les genres de texte peints sous :data:`PLANCHER`, page entière, et
#: combien de nœuds de texte le balayage a vus en tout.
#:
#: ⚠️ Le balayage ne séparait plus la coque du contenu depuis le
#: 2026-09-12 : c'est le thème qui décide de la densité PARTOUT, donc
#: les deux régions ont le même propriétaire et les distinguer ne
#: répondrait plus à rien.
#:
#: ⚠️ **``vus`` n'est pas décoratif** : sans lui, un sélecteur cassé rend
#: zéro genre et le constat passe au vert en n'ayant rien regardé. C'est
#: le plancher de non-vacuité de la règle 8.
#:
#: ⚠️ Les nœuds cachés sont écartés : un panneau de ``ui.select`` fermé
#: reste dans le DOM avec toutes ses options, et mesurer leur police
#: répondrait pour quelque chose que personne ne voit. Le filtre est
#: ``offsetParent`` + un texte PROPRE non vide — les nœuds de texte
#: DIRECTS, sinon chaque ancêtre compterait pour ses descendants.
SOUS_LE_PLANCHER = """
(function (plancher) {
    const dedans = {genres: {}, vus: 0};
    document.querySelectorAll('body *').forEach(function (el) {
        if (!el.offsetParent) return;
        const propre = Array.from(el.childNodes)
            .filter(n => n.nodeType === 3)
            .map(n => n.textContent.trim())
            .join('');
        if (!propre) return;
        dedans.vus += 1;
        const taille = parseFloat(getComputedStyle(el).fontSize);
        if (taille >= plancher) return;
        dedans.genres[el.className] = taille + ' px : '
            + propre.slice(0, 20);
    });
    return dedans;
})(""" + str(PLANCHER) + ")"


def devient_vrai(w: Window, expr: str, *, timeout: int = 5000) -> bool:
    """L'attente EST la mesure : vrai dès que ``expr`` l'est, faux au bout.

    Un constat qui LIT juste après un geste lit parfois l'état d'avant.
    Attendre la CONDITION supprime la course sans rien endormir :
    l'expiration n'est pas avalée, elle devient le rouge.
    """
    try:
        w.page.wait_for_function(expr, timeout=timeout)
    except PlaywrightTimeout:
        return False
    return True


def ouvrir_le_pied(w: Window):
    """Ouvre le menu de compte de la barre latérale et le rend.

    ⚠️ Les entrées n'existent **que menu ouvert**. La version d'avant
    lisait des ``[role=option]`` dans le DOM sans rien ouvrir : ça
    marchait parce qu'un ``ui.select`` monte son panneau fermé, et ça a
    rendu une liste vide le jour où le sélecteur est devenu un menu.
    Une lecture qui dépend de la façon dont un composant se monte n'est
    pas une lecture de l'écran.
    """
    ouvert = w.page.locator("[role=menu]:visible")
    if ouvert.count():
        # ⚠️ Déjà ouvert : le menu FLOTTE au-dessus de son déclencheur,
        # donc recliquer dessus part en attente de 30 s. Deux lectures à
        # la suite sont le cas normal — on lit les entrées, puis on en
        # choisit une.
        return ouvert.first
    w.page.locator("aside button").filter(
        has_text="Physique-chimie").first.click()
    menu = w.page.locator("[role=menu]:visible").first
    menu.wait_for(state="visible", timeout=5000)
    return menu


def libelles_annees(w: Window) -> list[str]:
    """Les ANNÉES proposées, menu ouvert — pas les thèmes.

    Le pied porte aussi le choix de thème et le plein écran : lire
    toutes ses entrées ferait passer « Thème clair » pour une année.
    Le filtre est la forme d'un libellé d'année scolaire.
    """
    menu = ouvrir_le_pied(w)
    return [t.strip() for t in menu.get_by_role("menuitem").all_inner_texts()
            if re.match(r"^\d{4}-\d{4}", t.strip())]


def choisir_annee(w: Window, actuelle: str, voulue: str) -> None:
    """Piloter le menu du PIED de la barre latérale.

    ⚠️ **C'était un ``ui.select`` jusqu'au 2026-09-12**, posé dans le
    corps de la barre — et replié en rail, il rendait une boîte écrasée
    à la largeur du rail. Le pied, lui, sait se replier : il ne montre
    que l'avatar, et son menu flotte au-dessus de la barre. Les années
    y sont des entrées de menu.

    Le déclencheur est la rangée de compte ; les entrées n'existent
    qu'une fois le menu ouvert, et il faut celle qui est VISIBLE — un
    panneau déjà ouvert une fois reste monté, fermé.
    """
    del actuelle  # le pied s'ouvre par sa rangée de compte, pas par sa valeur
    # ⚠️ **Attendre que la page ait FINI avant d'ouvrir le menu.** Changer
    # d'année redessine une zone qui contient le pied ; ouvrir pendant ce
    # temps donne un menu que le rafraîchissement remplace entre
    # l'ouverture et le clic — Playwright réessaie alors 30 s sur un nœud
    # détaché et rend « element is not visible », ce qui se lit comme un
    # défaut de l'écran. Le grain du redessin a changé le 2026-09-13
    # (``perf(ecole)!: une zone est le grain de ce qu'on redessine``) :
    # ce qui passait par chance ne passe plus.
    w.settle()
    menu = ouvrir_le_pied(w)
    menu.get_by_role("menuitem").filter(has_text=voulue).first.click()


def apparait(w: Window, sel: str, *, timeout: int = 5000) -> bool:
    """Même idée que :func:`devient_vrai`, pour un SÉLECTEUR.

    Un ``wait_for_selector`` nu LÈVE, donc il avorte le scénario : pas de
    ligne rouge, et le balayage de sortie ne tourne jamais. Rendre un
    booléen le range dans un ``p.check``, qui est ce qu'on voulait dire.
    """
    try:
        w.page.wait_for_selector(sel, timeout=timeout)
    except PlaywrightTimeout:
        return False
    return True


def bouton(nom: str) -> str:
    """Un bouton par son nom accessible."""
    return f'role=button[name="{nom}"]'


def params(w: Window) -> dict[str, str]:
    """Les paramètres de l'adresse affichée, à plat."""
    bruts = parse_qs(urlparse(w.page.url).query)
    return {cle: valeurs[0] for cle, valeurs in bruts.items()}


def lundi_courant(w: Window) -> str:
    """Le lundi affiché, lu dans l'ADRESSE — ou celui d'aujourd'hui.

    Le jeu semé est bâti autour de la date du jour (``core/seed.py``),
    donc un lundi écrit en dur rougirait à la prochaine rentrée, pour une
    raison qui n'a rien à voir avec ce qu'on mesure.
    """
    courants = params(w)
    if courants.get("semaine"):
        return courants["semaine"]
    return w.page.evaluate(
        """
        (function () {
            const d = new Date();
            d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
            return d.toISOString().slice(0, 10);
        })()
        """
    )


def avancer_jusqua(w: Window, marqueur: str, bonds: int) -> str:
    """Avance de semaine en semaine jusqu'à voir ``marqueur``.

    Rend le lundi trouvé, ou ``""``. Chercher plutôt qu'épingler une date
    est ce qui rend ces constats reproductibles tous les ans.
    """
    w.goto("/")
    for _ in range(bonds):
        if w.has(marqueur):
            return lundi_courant(w)
        w.click(bouton("Semaine suivante"))
        w.settle(floor=0)
    return ""


def laccueil_montre_les_classes(p: Probe, a: Window) -> None:
    """① Une tuile par classe, l'effectif, le total, la marque « à voir »."""
    print("\n① L'accueil montre les classes (EF-C1)")
    a.goto("/classes")

    p.check(
        "le runtime a fini son boot",
        devient_vrai(a, "document.documentElement.classList"
                        ".contains('bz-ready')"),
        "`html.bz-ready` n'est jamais arrivé",
    )

    # Le seed pose dix classes sur l'année en cours. Le compte est écrit
    # ici plutôt que déduit du DOM : une tuile qui manquerait rendrait
    # une comparaison DOM-contre-DOM verte.
    #
    # ATTENTION : le selecteur vise le LIEN, pas « un div dans la
    # grille ». La premiere version comptait
    # `main [class*=grid] > div` ; au lot 4 la tuile a recu son
    # `href=` et le composant a change de tag, donc le compte est
    # tombe a zero pour une raison qui n'etait pas la faute
    # mesuree. Un selecteur qui decrit ce que la CHOSE EST — un
    # lien vers une classe — survit a la mise en page.
    tuiles = a.count("main a[href^='/classe/']")
    p.check("dix classes affichées", tuiles == 10, f"{tuiles} tuile(s)")

    p.check("une classe de collège est là", a.has("text=6e2"))
    p.check("une classe de lycée aussi", a.has("text=2°GT1"))
    p.check("le total des élèves est affiché",
            a.has("text=élèves en tout"), a.text("h1"))
    p.check("un effectif de classe est affiché", a.has("text=30 élèves"))

    # EF-H4 : la marque « à voir » existe, sinon la fonction est
    # invisible tant qu'on n'ouvre pas chaque fiche.
    a_voir = a.count("text=à voir")
    p.check("au moins une classe porte « à voir »", a_voir >= 1,
            f"{a_voir} marque(s)")


def lannee_change_les_deux(p: Probe, a: Window) -> None:
    """② Le silence B2 : la coque ET la page suivent le sélecteur."""
    print("\n② Changer d'année change la coque ET la page (EF-U2, RT-1)")
    a.goto("/classes")

    en_cours = a.text("h1")
    p.check("au départ, aucun bandeau de consultation",
            not a.has("text=année en consultation"), en_cours)

    # L'année passée est la seule autre entrée du sélecteur ; son libellé
    # n'est pas écrit en dur (il dépend de la date du jour).
    libelles = libelles_annees(a)
    autre = next((t for t in libelles if "en cours" not in t), "")
    p.check("le sélecteur propose une seconde année", bool(autre), libelles)
    if not autre:
        return

    choisir_annee(a, "en cours", autre)
    p.check(
        "le bandeau de consultation apparaît",
        devient_vrai(
            a,
            "!!document.body.innerText.includes('année en consultation')",
        ),
        "RT-1 n'est dit sur aucun écran",
    )
    p.check(
        "et le titre de la page suit l'année choisie",
        devient_vrai(
            a, f"document.querySelector('h1').textContent !== {en_cours!r}"
        ),
        f"le titre est resté « {en_cours} » : la zone est gelée",
    )
    p.check("l'année passée montre ses six classes",
            a.count("main a[href^='/classe/']") == 6,
            a.count("main a[href^='/classe/']"))

    # Le retour compte autant que l'aller : un bandeau qui apparaît et ne
    # part plus est exactement le même défaut, vu de l'autre côté.
    choisir_annee(a, autre, "en cours")
    p.check(
        "revenir à l'année en cours retire le bandeau",
        devient_vrai(
            a,
            "!document.body.innerText.includes('année en consultation')",
        ),
        "le bandeau est resté",
    )


def rien_ne_secrit_trop_petit(p: Probe, a: Window) -> None:
    """③ EF-U3 — la tablette est un poste de travail.

    ⚠️ **Ce constat a changé de sujet le 2026-09-12**, et il vaut de
    dire pourquoi : il exigeait qu'aucun texte ne descende sous 19 px,
    l'app tenait ce plancher en déplaçant sa racine typographique, et
    l'utilisateur l'a retirée — *« c'est trop gros »*. Mesurer un
    plancher que plus personne ne pose reviendrait à juger les valeurs
    par défaut du framework depuis le probe d'une app.

    Ce qui se mesure depuis que l'app a une ÉCHELLE (``base=COMPACT``
    dans ``core/theme.py``) est plus simple et plus fort : **rien n'est
    peint sous son plus petit palier**. Un texte en dessous veut dire
    qu'un composant a échappé à l'échelle, ce qui ne peut pas être une
    intention.

    La moitié STATIQUE du même constat vit dans
    ``tests/consistency/test_ecole_never_sets_a_text_size.py`` : c'est
    elle qui tient *« l'app n'écrit aucune taille »*, et sans elle le
    gel ci-dessous ne dirait plus de qui il parle.
    """
    print(f"\n③ Rien ne s'écrit trop petit (EF-U3, plancher {PLANCHER} px)")
    a.goto("/classes")

    mesure = a.page.evaluate(SOUS_LE_PLANCHER)
    p.check(
        "le balayage des tailles a bien regardé la page",
        mesure["vus"] >= 40,
        f"{mesure['vus']} nœud(s) de texte visibles seulement",
    )
    genres = mesure["genres"]
    p.check(
        f"rien n'échappe à l'échelle de l'app par le bas ({PLANCHER} px)",
        len(genres) <= GENRES_SOUS_LE_PLANCHER,
        list(genres.values()),
    )


def le_plein_ecran_est_joignable(p: Probe, a: Window) -> None:
    """④ EF-U4 — atteignable depuis tous les écrans.

    Il vit dans le pied de la barre latérale, donc derrière un menu : ce
    qu'on mesure est qu'il EXISTE et qu'il s'ouvre, pas qu'il bascule —
    le plein écran d'un Chromium piloté n'est pas une mesure fiable.
    """
    print("\n④ Le bouton de plein écran (EF-U4)")
    a.goto("/classes")

    a.click("text=Physique-chimie")
    p.check(
        "le pied de barre latérale offre le plein écran",
        devient_vrai(
            a, "!!document.body.innerText.includes('Plein écran')"
        ),
        "aucun bouton de plein écran dans la coque",
    )
    a.press("Escape")


def les_reglages_se_lisent(p: Probe, a: Window) -> None:
    """⑤ Lot 2 — l'écran des réglages, et les trois formes d'EF-A11.

    Ce qui ne se mesure qu'ici : la colonne « Cours perdus » doit rendre
    TROIS choses différentes, et deux d'entre elles sont des absences —
    rien du tout pour de vraies vacances, une phrase pour une liste vide.
    Un test de rendu qui compterait des lignes ne distinguerait pas les
    deux.
    """
    print("\n⑤ Les réglages (EF-A1 … EF-A11)")
    a.goto("/reglages")

    p.check(
        "le runtime a fini son boot",
        devient_vrai(a, "document.documentElement.classList"
                        ".contains('bz-ready')"),
        "`html.bz-ready` n'est jamais arrivé",
    )
    p.check("les trois blocs sont là",
            a.has("text=L'année scolaire") and a.has("text=Les trimestres")
            and a.has("text=Les jours sans classe"))

    # EF-A3 : trois numéros × deux cycles = six cases, pas trois.
    cases = a.count("text=Fin du trimestre")
    p.check("six fins de trimestre, trois par cycle", cases == 6, cases)

    # EF-A9 : la ligne qui sépare les périodes de travail. Le jeu semé
    # porte quatre vraies vacances, donc cinq morceaux.
    morceaux = a.count(r"text=/^Période \d+ · \d+ semaines$/")
    p.check("les périodes de travail sont annoncées", morceaux == 5,
            f"{morceaux} ligne(s) de période")

    # EF-A11, les trois réponses. « Armistice » est un férié d'un seul
    # jour posé un mercredi : il tombe DANS une période, donc il a une
    # réponse — et le seed lui donne des cours.
    p.check("un férié dit ce qu'il coûte",
            a.has("text=Armistice"))
    p.check("une liste vide se dit, elle ne se tait pas",
            a.has("text=aucun cours ce jour-là"),
            "aucune ligne ne rend la bonne nouvelle")

    # EF-A8 : un férié montre ses DEUX dates, identiques. Une colonne à
    # moitié vide se lit plus mal que deux colonnes toujours remplies.
    dates_armistice = a.page.evaluate(
        r"""
        (function () {
            const cible = Array.from(document.querySelectorAll('span'))
                .find(s => s.textContent.trim() === 'Armistice');
            if (!cible) return [];
            const ligne = cible.closest('div.grid');
            return Array.from(ligne.querySelectorAll('span'))
                .map(s => s.textContent.trim())
                .filter(t => /^[a-z]{3} \d{2}\/\d{2}$/.test(t));
        })()
        """
    )
    p.check(
        "un férié montre ses deux dates, identiques (EF-A8)",
        len(dates_armistice) == 2
        and dates_armistice[0] == dates_armistice[1],
        dates_armistice,
    )

    # EF-A7 : le jour de la semaine PRÉCÈDE la date.
    p.check(
        "le jour de la semaine précède la date (EF-A7)",
        bool(dates_armistice) and dates_armistice[0][:3] in (
            "lun", "mar", "mer", "jeu", "ven", "sam", "dim"),
        dates_armistice,
    )


def rt1_ferme_les_reglages(p: Probe, a: Window) -> None:
    """⑥ RT-1 vu de l'écran : une année en consultation n'offre rien.

    EF-C10 dit qu'un mouvement ne se PROPOSE que sur l'année en cours —
    « il s'agit de ne pas offrir un bouton qui refusera ». La barrière,
    elle, est testée en Python (``garde_ecriture`` lève) ; ici on mesure
    la politesse par-dessus.
    """
    print("\n⑥ Une année en consultation n'offre aucune écriture (RT-1)")
    a.goto("/reglages")

    libelles = libelles_annees(a)
    autre = next((t for t in libelles if "en cours" not in t), "")
    if not autre:
        p.check("le sélecteur propose une seconde année", False, libelles)
        return

    choisir_annee(a, "en cours", autre)
    p.check(
        "le bandeau de consultation est là",
        devient_vrai(
            a,
            "!!document.body.innerText.includes('année en consultation')",
        ),
    )
    # ⚠️ ``:visible`` de Playwright, et **pas** ``offsetParent``. EF-C10
    # dit « ne pas OFFRIR un bouton qui refusera » : un bouton dans un
    # dialogue FERMÉ n'est offert à personne. Mais un overlay Bretzel se
    # ferme en ``visibility``, pas en ``display`` — son panneau garde
    # donc un ``offsetParent``, et le premier filtre comptait les deux
    # boutons des dialogues comme s'ils étaient à l'écran.
    # ``:visible`` tient compte de la visibilité ET de la boîte.
    actifs = (
        a.page.locator("main button:visible:not([disabled])")
        .filter(has_text="Enregistrer")
        .count()
    )
    p.check(
        "aucun bouton « Enregistrer » visible n'est actif",
        actifs == 0,
        f"{actifs} bouton(s) encore cliquable(s)",
    )
    p.check(
        "et la mise en service est proposée à la place",
        a.has("text=Mettre cette année en service"),
    )
    choisir_annee(a, autre, "en cours")
    a.settle(floor=0)


def la_grille_se_lit(p: Probe, a: Window) -> None:
    """(7) Lot 3 — une semaine se lit (point 1 de la recette, § 11).

    *« La grille montre les bonnes dates, la bonne lettre, les blocs
    réunis, le TP nommé, les vacances vides avec leur nom. »* Quatre de
    ces cinq choses ne se voient qu'à l'écran : une date de colonne est
    calculée, une lettre est déduite, un bloc est une FUSION, et un jour
    vide est une ABSENCE — un test de rendu qui compte des lignes ne
    distingue pas un jour vide d'un jour manquant.
    """
    print("\n(7) Une semaine se lit (EF-B1 ... EF-B13)")
    a.goto("/")
    p.check(
        "le runtime a fini son boot",
        devient_vrai(a, "document.documentElement.classList"
                        ".contains('bz-ready')"),
        "`html.bz-ready` n'est jamais arrive",
    )
    p.check("l'emploi du temps tient la racine (§ 8)",
            a.has("text=Emploi du temps"))

    # EF-B2 : la lettre est DÉDUITE et affichée en tête. Elle ne se
    # choisit pas — il ne doit donc exister aucun contrôle pour elle.
    lettre = a.page.evaluate(
        """
        (function () {
            const el = Array.from(document.querySelectorAll('main span'))
                .find(s => /^Semaine [AB]$/.test(s.textContent.trim()));
            return el ? el.textContent.trim() : '';
        })()
        """
    )
    p.check("la semaine porte sa lettre, deduite (EF-B2)",
            lettre in ("Semaine A", "Semaine B"), lettre or "aucune lettre")

    p.check("les six jours sont la",
            all(a.has("text=" + j) for j in
                ("Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi",
                 "Samedi")))
    bornes = a.count("main button:has-text(':')")
    p.check("les huit bornes horaires sont reglables en premiere colonne",
            bornes >= 8, bornes)

    # ⚠️ **Le constat qui manquait, et il a coûté un aller-retour avec
    # l'utilisateur.** Le balayage du harnais vérifie que la PAGE ne
    # déborde pas latéralement — et il avait raison : la grille défilait
    # dans sa propre région, donc rien ne dépassait du document. Sauf que
    # vendredi et samedi étaient hors champ, sur l'écran dont tout le
    # propos est de se lire d'un coup d'œil. « Ça ne déborde pas » et
    # « ça tient à l'écran » sont deux mesures différentes.
    hors_champ = a.page.evaluate(
        """
        (function () {
            const droite = document.documentElement.clientWidth;
            return Array.from(document.querySelectorAll('main div'))
                .filter(function (el) {
                    const t = (el.firstElementChild || {}).textContent || '';
                    return /^(Lundi|Mardi|Mercredi|Jeudi|Vendredi|Samedi)$/
                        .test(t.trim());
                })
                .map(function (el) {
                    const b = el.getBoundingClientRect();
                    return {jour: el.firstElementChild.textContent.trim(),
                            droite: Math.round(b.right)};
                })
                .filter(j => j.droite > droite);
        })()
        """
    )
    # Le PLANCHER du constat : un selecteur qui ne trouve aucun jour
    # rendrait « rien hors champ » et serait vert en ne mesurant rien.
    # C'est la regle 8 du CLAUDE.md appliquee a un constat de probe.
    vus = a.page.evaluate(
        """
        Array.from(document.querySelectorAll('main div'))
            .filter(function (el) {
                const t = (el.firstElementChild || {}).textContent || '';
                return /^(Lundi|Mardi|Mercredi|Jeudi|Vendredi|Samedi)$/
                    .test(t.trim());
            }).length
        """
    )
    p.check("les six colonnes de jour sont bien mesurees", vus == 6, vus)
    p.check(
        "les SIX jours tiennent a l'ecran, sans defilement lateral",
        vus == 6 and not hors_champ,
        hors_champ,
    )

    avant = a.page.url
    a.click(bouton("Semaine suivante"))
    p.check(
        "la fleche change la semaine ET l'adresse (EF-B1, EF-U1)",
        devient_vrai(a, "new URL(location.href).searchParams.has('semaine')"),
        f"{avant} -> {a.page.url}",
    )

    a.click(bouton("Aujourd'hui"))
    p.check(
        "« Aujourd'hui » ramene a la semaine du jour",
        devient_vrai(
            a, "!new URL(location.href).searchParams.get('semaine')"),
        a.page.url,
    )


def les_blocs_et_les_tp(p: Probe, a: Window) -> None:
    """(8) EF-B9, EF-B10 — les blocs réunis et le TP nommé.

    Le jeu semé pose exprès deux TP en semaine A — 3e2 le lundi
    (s5-s6-s7) et 2°GT4 le jeudi (s2-s3-s4) — plus un bloc de deux heures
    le lundi matin et une heure à nature le mardi.
    """
    print("\n(8) Les blocs, les TP, les natures")
    lundi = avancer_jusqua(a, "text=/^Semaine A$/", 4)
    if not lundi:
        p.check("une semaine A se trouve dans l'annee", False, "aucune")
        return

    # EF-B10 : la case porte « TP ». Rien n'est stocké — si la marque est
    # là, c'est que la règle a été LUE dans la grille.
    tp = a.count("text=/^TP$/")
    p.check("les TP de la semaine sont nommes (EF-B10)", tp >= 2,
            f"{tp} marque(s) TP")

    # EF-B9 : un bloc de trois heures occupe la hauteur de trois cases.
    # C'est la seule preuve qu'il est RÉUNI plutôt que rendu trois fois.
    hauteurs = a.page.evaluate(
        """
        Array.from(document.querySelectorAll('main [style*="height"]'))
            .map(d => parseFloat(d.style.height))
            .filter(h => h > 0)
        """
    )
    p.check(
        "au moins une case fait la hauteur de trois heures",
        any(h > 13 for h in hauteurs),
        sorted(set(hauteurs))[-4:] if hauteurs else "aucune hauteur calculee",
    )
    p.check("une heure a nature est visible comme telle", a.has("text=HVC"))


def les_jours_sans_classe(p: Probe, a: Window) -> None:
    """(9) EF-B4, EF-B5 — le piège n° 12, vu des deux côtés.

    *« Griser les jours de vacances en laissant lire les classes ne
    suffit pas : on lit quand même cinq cours qu'on ne fera pas. »* Un
    jour sans classe est donc VIDE en lecture — et REMPLI en
    modification, parce que c'est pendant les vacances qu'on reprend la
    grille.
    """
    print("\n(9) Les jours sans classe (EF-B4, EF-B5)")
    lundi = avancer_jusqua(a, "text=Toussaint", 14)
    if not lundi:
        p.check("une semaine de vacances se trouve dans l'annee", False,
                "aucune des quatorze premieres")
        return

    p.check("le nom de la periode est ecrit sous la date (EF-B4)",
            a.has("text=Toussaint"))
    # ⚠️ **La GRILLE, pas tout ``main``.** La page monte aussi les
    # « cadres du jour » (EF-B15) — la dernière séance faite, le travail à
    # vérifier — et ceux-là parlent d'AUJOURD'HUI, pas de la semaine
    # affichée. Ils nomment donc une classe même pendant les vacances,
    # légitimement. Lire tout ``main`` faisait échouer ce constat sur un
    # panneau qui n'est pas son sujet : EF-B4 dit qu'un jour sans classe
    # est vide DANS LA GRILLE.
    #
    # L'ancre est le gabarit de colonnes de la grille, seul de la page.
    classes = a.page.evaluate(
        "(() => {"
        " const g = document.querySelector('main [class*=\"grid-cols-[56px\"]');"
        " return g ? (g.innerText.match(/6e2|5e1|3e5/g) || []).length : -1;"
        "})()"
    )
    p.check("et aucune classe ne se lit ce jour-la", classes == 0,
            f"{classes} classe(s) affichee(s) un jour de vacances")

    a.click(bouton("Modifier la grille"))
    p.check(
        "en modification, TOUT revient (EF-B5)",
        devient_vrai(
            a,
            "!!document.querySelector('main').innerText.match(/6e2|5e1|3e5/)"),
        "la grille type reste cachee pendant les vacances",
    )
    a.click(bouton("Lecture"))
    a.settle(floor=0)


def les_heures_exceptionnelles(p: Probe, a: Window) -> None:
    """(10) EF-B11 — une décision posée sur une VRAIE date.

    Le jeu semé pose les deux formes : une heure EN PLUS sur une case
    libre, et une ANNULATION sur une case occupée. Ce que le probe mesure
    et qu'aucun test Python ne voit, c'est qu'elles se DISTINGUENT à
    l'œil d'un cours ordinaire — le drapeau se perdait dans la fusion des
    blocs, et l'heure exceptionnelle rendait exactement comme un cours.
    """
    print("\n(10) Les heures exceptionnelles (EF-B11)")
    lundi = avancer_jusqua(a, "main .border-l-info", 8)
    if not lundi:
        p.check("une heure exceptionnelle se trouve dans l'annee", False,
                "aucune des huit premieres semaines")
        return
    p.check("une heure en plus se distingue d'un cours ordinaire",
            a.count("main .border-l-info") >= 1)

    # EF-B11 : en mode exceptions, une case OCCUPÉE ne propose qu'une
    # annulation et une case LIBRE qu'un ajout. C'est le libellé du
    # bouton qui le dit, et c'est la seule chose qui les distingue.
    a.click(bouton("Heures exceptionnelles"))
    a.settle(floor=0)
    # ⚠️ Le geste d'une case OCCUPÉE est passé DANS la carte le
    # 2026-09-12, en bouton d'icône : empilé dessous, il sortait de la
    # boîte et recouvrait la case suivante. Son libellé vit donc dans
    # `aria-label` et dans l'infobulle — ce qui distingue les deux cas
    # n'a pas changé, sa forme oui.
    annuler = a.count("main button[aria-label^='Annuler']")
    ajouter = a.count("main button:has-text('Ajouter')")
    p.check("les cases occupees ne proposent qu'une annulation",
            annuler >= 1, annuler)
    p.check("les cases libres ne proposent qu'un ajout", ajouter >= 1,
            ajouter)
    # Une case porte UN geste, jamais les deux : la somme des deux
    # populations doit valoir le nombre de gestes de la grille. Le
    # sélecteur nomme les deux formes — l'icône d'une case occupée,
    # le bouton plein d'une case libre.
    p.check("et les deux libelles ne se melangent pas sur une meme case",
            annuler + ajouter == a.count(
                "main button[aria-label^='Annuler'], "
                "main button:has-text('Ajouter')"),
            f"{annuler} + {ajouter}")
    a.click(bouton("Lecture"))
    a.settle(floor=0)


def une_classe_et_ses_eleves(p: Probe, a: Window) -> None:
    """(11) Lot 4 — la grille de photos, et le chemin qui y mène.

    EF-C2 et EF-C1 se referment l'un sur l'autre : la tuile de l'accueil
    ouvre la classe, la classe montre ses élèves, une vignette ouvre la
    fiche. Ce que le probe mesure ici, c'est la CHAÎNE — un test de rendu
    par page ne dit jamais que les trois se suivent.
    """
    print("\n(11) Une classe, ses eleves, une fiche (EF-C1, EF-C2, EF-C3)")
    a.goto("/classes")
    a.click("text=6e2")
    ouvert = apparait(a, "main h1:has-text('6e2')", timeout=8000)
    p.check("la tuile de l'accueil ouvre la classe (EF-C1)", ouvert,
            a.page.url)
    p.check("l'adresse porte la classe dans le CHEMIN",
            "/classe/" in a.page.url, a.page.url)

    vignettes = a.count("main a[href^='/eleve/']")
    p.check("la classe montre ses eleves en grille (EF-C2)",
            vignettes >= 25, f"{vignettes} vignette(s)")
    p.check("le professeur principal se saisit (EF-C6)",
            a.has("text=Professeur principal"))
    p.check("et son nom ouvre un lien de courrier",
            a.count("a[href^='mailto:']") >= 1)

    a.click("main a[href^='/eleve/']")
    ouverte = apparait(a, "text=Particularités", timeout=8000)
    p.check("une vignette ouvre la fiche de l'eleve (EF-C3)", ouverte,
            a.page.url)
    p.check("la fiche porte ses particularites (EF-C4)",
            a.has("text=Vue fragile") and a.has("text=Gaucher"))
    p.check("et son parcours (EF-C9)", a.has("text=Parcours"))


def la_recherche_garde_les_deux_champs(p: Probe, a: Window) -> None:
    """(12) EF-C7 — nom et prénom restent DISTINCTS.

    *« Un élève qui s'appelle LEA de son nom ne doit pas se confondre
    avec une Léa de prénom. »* Le jeu semé n'a pas d'homonyme fabriqué,
    donc ce qui se mesure ici est la propriété qui le garantit : chercher
    un NOM du jeu ne doit rendre que des lignes dont c'est le nom.
    """
    print("\n(12) La recherche (EF-C7)")
    a.goto("/recherche")
    p.check("l'ecran invite a chercher", a.has("text=Tapez un nom"))

    a.goto("/recherche?q=Courty")
    trouve = apparait(a, "main a[href^='/eleve/']", timeout=8000)
    p.check("une recherche par l'adresse rend des resultats (EF-U1)",
            trouve, a.page.url)

    # ATTENTION : le NOM, pas la premiere ligne de la carte — celle-ci
    # porte les INITIALES de l'avatar. La premiere version lisait
    # « AC » et « BC », et accusait la recherche d'un defaut qui
    # n'existe pas. Le nom est le seul texte de la carte que l'app
    # ecrit en MAJUSCULES.
    noms = a.page.evaluate(
        """
        Array.from(document.querySelectorAll("main a[href^='/eleve/']"))
            .map(function (carte) {
                const lignes = carte.innerText
                    .split(String.fromCharCode(10))
                    .map(t => t.trim()).filter(Boolean);
                return lignes.find(t => t.length > 2
                                        && t === t.toUpperCase()) || '';
            })
        """
    )
    p.check(
        "tous les resultats portent bien ce NOM, pas ce prenom",
        bool(noms) and all(n.upper() == "COURTY" for n in noms),
        noms[:5],
    )

    a.goto("/recherche?q=zzzzzz")
    p.check("une recherche sans resultat le dit",
            apparait(a, "text=Aucun élève", timeout=8000))


def la_saisie_de_masse(p: Probe, a: Window) -> None:
    """(13) Lot 5 — un devoir se saisit de bout en bout (recette, point 2).

    Ce que seul un navigateur peut dire ici : qu'une note trop haute est
    REFUSÉE **et que le refus s'explique** (EF-D5). Un test Python prouve
    que la fonction lève ; il ne dit pas que le professeur comprend
    pourquoi, ni laquelle des trente lignes est en cause.

    Et la saisie de masse elle-même : trente champs, UN envoi. Le compte
    de requêtes le mesure — trente actions séparées rendraient la frappe
    hachée, et c'est le besoin nommé du moment d'usage du soir.
    """
    print("\n(13) La saisie de masse et le refus metier (EF-D4, EF-D5)")
    a.goto("/classes")
    a.click("main a[href^='/classe/']")
    ouvert = apparait(a, "main h1", timeout=8000)
    if not ouvert:
        p.check("une classe s'ouvre", False, a.page.url)
        return

    a.click("text=Évaluations")
    a.settle(floor=0)
    liens = a.count("main a[href^='/evaluation/']")
    p.check("l'onglet Evaluations liste les devoirs (EF-D1)", liens >= 1,
            f"{liens} devoir(s)")
    p.check("chaque ligne dit l'avancement de la saisie",
            a.count("text=/[0-9]+\\/[0-9]+ saisies/") >= 1)

    a.click("main a[href^='/evaluation/']")
    saisie = apparait(a, "text=Saisie des notes", timeout=8000)
    p.check("le devoir s'ouvre sur sa saisie", saisie, a.page.url)
    champs = a.count("main input[name^='note_']")
    p.check("un champ par eleve, tous sur le meme formulaire (EF-D4)",
            champs >= 25, f"{champs} champ(s)")

    # EF-D6 : l'histogramme et la moyenne de la classe.
    p.check("l'histogramme est la (EF-D6)", a.has("text=Répartition"))
    p.check("avec la moyenne de la classe",
            a.has("text=Moyenne de la classe"))

    # EF-D5 : une note au-dessus du bareme est refusee, ET explique.
    premier = "main input[name^='note_']"
    a.page.fill(premier, "999")
    with p.requests() as reseau:
        a.click(bouton("Enregistrer les notes"))
        a.settle()
    p.check(
        "une note au-dessus du bareme est refusee ET expliquee (EF-D5)",
        devient_vrai(
            a, "!!document.body.innerText.match(/refus|dépasse/i)",
            timeout=8000),
        "aucun message de refus a l'ecran",
    )
    p.check(
        "et trente notes partent en UN envoi, pas trente (EF-D4)",
        reseau.total <= 2,
        f"{reseau.total} requete(s) : {reseau.urls[:4]}",
    )


def lappreciation_se_propose_et_se_garde(p: Probe, a: Window) -> None:
    """(14) Lot 6 — le point 3 de la recette, mot pour mot.

    *« Cocher quatre observations, lire le texte proposé, le corriger,
    cocher autre chose, et constater que le texte corrigé N'A PAS
    BOUGÉ. »* C'est EF-E3, et c'est le seul constat de tout ce probe
    qu'aucun test Python ne peut faire à sa place : il faut cocher, puis
    écrire, puis cocher encore, et comparer ce qu'on lit.
    """
    print("\n(14) L'appreciation se propose, puis ne bouge plus (EF-E3)")
    a.goto("/classes")
    a.click("main a[href^='/classe/']")
    if not apparait(a, "main a[href^='/eleve/']", timeout=8000):
        p.check("une classe s'ouvre", False, a.page.url)
        return
    a.click("main a[href^='/eleve/']")
    if not apparait(a, "text=Observations", timeout=8000):
        p.check("la fiche d'un eleve s'ouvre", False, a.page.url)
        return

    p.check("les quatre rangees de tuiles sont la (EF-E1)",
            all(a.has("text=" + c) for c in
                ("Comportement", "Travail", "Participation", "Matériel")))

    # EF-E2 : cocher REPROPOSE un texte. Avant le premier clic il n'y a
    # rien — c'est ce qui rend le constat lisible.
    a.click(bouton("Exemplaire"))
    a.settle()
    propose = a.value("main textarea")
    p.check("cocher une observation propose un texte (EF-E2)",
            bool(propose.strip()), propose[:60] or "(vide)")
    p.check("et le texte tient sous 400 caracteres (EF-E4)",
            len(propose) <= 400, len(propose))

    # EF-E3, premier temps : le professeur ecrit.
    a.page.fill("main textarea", "Texte du professeur, a ne pas toucher.")
    a.click(bouton("Enregistrer mon texte"))
    a.settle()
    p.check(
        "l'ecran DIT que le texte ne sera plus reecrit",
        devient_vrai(
            a, "!!document.body.innerText.includes('ne le réécrira plus')",
            timeout=8000),
        "rien n'explique le changement de comportement",
    )

    # EF-E3, second temps : on coche AUTRE CHOSE, et le texte ne bouge pas.
    a.click(bouton("Régulier"))
    a.settle()
    apres = a.value("main textarea")
    p.check(
        "cocher autre chose ne reecrit PAS le texte du professeur (EF-E3)",
        apres == "Texte du professeur, a ne pas toucher.",
        apres[:80],
    )

    # Et le bouton de retour en arriere existe, lui aussi nomme.
    a.click(bouton("Reproposer"))
    a.settle()
    rendu = a.value("main textarea")
    p.check(
        "« Reproposer » rend la main a l'application",
        rendu != "Texte du professeur, a ne pas toucher." and bool(
            rendu.strip()),
        rendu[:80] or "(vide)",
    )


def le_bilan_se_tait_quand_il_ne_sait_pas(p: Probe, a: Window) -> None:
    """(15) EF-F — le bilan, et ce qu'il refuse de dire."""
    print("\n(15) Le bilan de classe (EF-F1 ... EF-F4)")
    a.goto("/classes")
    a.click("main a[href^='/classe/']")
    if not apparait(a, "text=Bilan", timeout=8000):
        p.check("l'onglet Bilan existe", False, a.page.url)
        return
    a.click("text=Bilan")
    a.settle(floor=0)
    p.check("le bilan du trimestre est redige (EF-F1)",
            a.has("text=Bilan du trimestre"))
    p.check("la repartition des moyennes est montree",
            a.has("text=Répartition des moyennes"))
    p.check("et la relecture de classe est atteignable (EF-E9)",
            a.count("a[href^='/appreciations/']") >= 1)

    a.click("a[href^='/appreciations/']")
    ouvert = apparait(a, "text=/[0-9]+ \\/ 400/", timeout=8000)
    p.check("la relecture montre le compteur de caracteres (EF-E9)",
            ouvert, a.page.url)


def le_plan_se_fait_et_se_fige(p: Probe, a: Window) -> None:
    """(16) Lot 7 — le point 4 de la recette, mot pour mot.

    *« Tracer la salle, ouvrir deux allées, poser deux contraintes,
    répartir automatiquement, déplacer un élève, figer, et CONSTATER QUE
    LE GLISSER NE FAIT PLUS RIEN. »*

    Le dernier constat est le seul de tout ce probe qui mesure une
    ABSENCE d'effet, et c'est le piège n° 11 : *« sur tablette, la main
    qui tient l'appareil effleure l'écran et déplace un élève sans que
    rien ne le signale — on s'en aperçoit au cours suivant, devant un
    plan faux »*. Un test Python peut vérifier que le handler refuse ; il
    ne peut pas vérifier que le GESTE ne passe plus.
    """
    print("\n(16) Le plan de classe (EF-G1 ... EF-G14)")
    # ⚠️ L'identifiant se lit dans le HREF de la tuile, **avant** de
    # cliquer. La première version le lisait dans l'adresse APRÈS le
    # clic, et l'adresse n'avait pas encore changé : le probe demandait
    # `/plan/classes`, recevait une 500, et accusait le plan d'un défaut
    # qui était le sien.
    a.goto("/classes")
    if not apparait(a, "main a[href^='/classe/']", timeout=8000):
        p.check("l'accueil liste des classes", False, a.page.url)
        return
    lien = a.page.get_attribute("main a[href^='/classe/']", "href") or ""
    classe_id = lien.rstrip("/").rsplit("/", 1)[-1]
    a.goto(f"/plan/{classe_id}")
    if not apparait(a, "text=Tableau", timeout=8000):
        p.check("le plan s'ouvre", False, a.page.url)
        return

    places = a.count("[data-bz-dropzone^='place_']")
    p.check("la salle est une grille de places (EF-G1)", places >= 20,
            f"{places} place(s)")
    # EF-G2 : *« la salle se trace d'un seul geste »*. On la trace plus
    # GRANDE que la classe — trente places pour trente élèves ne laissent
    # aucune marge, donc aucun glisser possible, et ce n'est pas ce que
    # la recette demande de mesurer.
    a.click(bouton("Tracer la salle"))
    if not apparait(a, "text=Places par rangée", timeout=8000):
        p.check("le trace de salle s'ouvre (EF-G2)", False, a.page.url)
        return
    a.page.fill("input[name$='rangees']", "6")
    a.page.fill("input[name$='par_rangee']", "6")
    a.click(bouton("Tracer"))
    a.settle()
    p.check(
        "la salle se trace d'un seul geste (EF-G2)",
        devient_vrai(
            a,
            "document.querySelectorAll("
            "\"[data-bz-dropzone^='place_']\").length === 36",
            timeout=8000),
        a.count("[data-bz-dropzone^='place_']"),
    )

    # EF-G4 : un bouton d'allee par COLONNE, et JAMAIS pour la premiere
    # (EF-G5) — un bouton qui ne peut que refuser n'a rien a faire la.
    allees = a.page.evaluate(
        """
        Array.from(document.querySelectorAll('main button'))
            .map(b => b.textContent.trim())
            .filter(t => t.startsWith('avant '))
        """
    )
    p.check("un bouton d'allee par colonne, sauf la premiere (EF-G4, EF-G5)",
            bool(allees) and "avant 1" not in allees, allees)

    # EF-G9 : repartir. Jamais d'echec bloquant.
    debout_avant = a.count("[data-bz-dropzone='attente'] [data-bz-draggable]")
    a.click("main button:has-text('Répartir')")
    a.settle()
    debout_apres = a.count("[data-bz-dropzone='attente'] [data-bz-draggable]")
    p.check(
        "la repartition assied la classe (EF-G9)",
        debout_apres < debout_avant,
        f"{debout_avant} debout avant, {debout_apres} apres",
    )

    # EF-G8 : deplacer un eleve d'une place a une autre. C'est le GESTE,
    # et le serveur arbitre au lacher.
    occupees = a.page.evaluate(
        """
        Array.from(document.querySelectorAll("[data-bz-dropzone^='place_']"))
            .filter(z => z.querySelector('[data-bz-draggable]'))
            .map(z => z.getAttribute('data-bz-dropzone'))
        """
    )
    libres = a.page.evaluate(
        """
        Array.from(document.querySelectorAll("[data-bz-dropzone^='place_']"))
            .filter(z => !z.querySelector('[data-bz-draggable]'))
            .map(z => z.getAttribute('data-bz-dropzone'))
        """
    )
    if occupees and libres:
        source = f"[data-bz-dropzone='{occupees[0]}'] [data-bz-draggable]"
        cible = f"[data-bz-dropzone='{libres[0]}']"
        qui = a.page.get_attribute(source, "data-bz-key")
        a.drag(source, cible)
        a.settle()
        arrive = a.page.evaluate(
            "!!document.querySelector(\"[data-bz-dropzone='"
            + libres[0] + "'] [data-bz-draggable]\")"
        )
        p.check("un eleve se deplace par glisser (EF-G8)", arrive,
                f"{qui} n'est pas arrive en {libres[0]}")
    else:
        p.check("il y a des places occupees ET libres pour glisser", False,
                f"{len(occupees)} occupees, {len(libres)} libres")
        return

    # EF-G14 : figer. Le libelle dit ce qu'on va POUVOIR FAIRE.
    p.check("le bouton dit « Figer », pas « Defiger »",
            a.has("main button:has-text('Figer')"))
    a.click(bouton("Figer"))
    a.settle()
    p.check(
        "figé, le bouton propose « Modifier »",
        devient_vrai(
            a,
            "!!Array.from(document.querySelectorAll('main button'))"
            ".find(b => b.textContent.trim() === 'Modifier')",
            timeout=8000),
        "le libelle n'a pas change",
    )

    # *« Figé, le glisser est COUPÉ ET les boutons qui déplacent sont
    # grisés, répartition automatique comprise. »*
    grises = a.page.evaluate(
        """
        Array.from(document.querySelectorAll('main button'))
            .filter(b => /Répartir|Tout vider|Tracer la salle/
                            .test(b.textContent))
            .every(b => b.disabled)
        """
    )
    p.check("et les boutons qui deplacent sont grises (EF-G14)", grises)

    # Le constat qui compte : le GESTE ne fait plus rien.
    occupees2 = a.page.evaluate(
        """
        Array.from(document.querySelectorAll("[data-bz-dropzone^='place_']"))
            .filter(z => z.querySelector('[data-bz-draggable]'))
            .map(z => z.getAttribute('data-bz-dropzone'))
        """
    )
    libres2 = a.page.evaluate(
        """
        Array.from(document.querySelectorAll("[data-bz-dropzone^='place_']"))
            .filter(z => !z.querySelector('[data-bz-draggable]'))
            .map(z => z.getAttribute('data-bz-dropzone'))
        """
    )
    if occupees2 and libres2:
        # ⚠️ Le glisser LÈVE quand rien n'atterrit — c'est
        # ``DropMissedError``, et c'est exactement ce qu'on attend ici :
        # la zone est verrouillée. On l'étouffe pour que le CONSTAT qui
        # suit devienne la mesure, plutôt qu'une trace qui avorte le
        # scénario avant le balayage.
        with contextlib.suppress(Exception):
            a.drag(f"[data-bz-dropzone='{occupees2[0]}'] [data-bz-draggable]",
                   f"[data-bz-dropzone='{libres2[0]}']")
        a.settle()
        reste_vide = a.page.evaluate(
            "!document.querySelector(\"[data-bz-dropzone='"
            + libres2[0] + "'] [data-bz-draggable]\")"
        )
        p.check(
            "FIGÉ, le glisser ne fait plus rien (EF-G14, piege n° 11)",
            reste_vide,
            f"un eleve est quand meme arrive en {libres2[0]}",
        )

    a.click(bouton("Modifier"))
    a.settle(floor=0)


def le_travail_a_verifier(p: Probe, a: Window) -> None:
    """(17) Lot 8 — EF-H, et la règle qui dit que rien ne s'efface.

    *« Trois cahiers incomplets dans le trimestre disent quelque chose
    que trois lignes effacées ne diraient plus. »* Le constat qui compte
    ici mesure donc une PERSISTANCE : on pose, on coche « fait », et la
    ligne doit être encore là — déplacée, pas disparue.
    """
    print("\n(17) Le travail a verifier (EF-H1 ... EF-H4)")
    a.goto("/classes")
    if not apparait(a, "main a[href^='/classe/']", timeout=8000):
        p.check("l'accueil liste des classes", False, a.page.url)
        return
    a.click("main a[href^='/classe/']")
    if not apparait(a, "main a[href^='/eleve/']", timeout=8000):
        p.check("une classe s'ouvre", False, a.page.url)
        return
    a.click("main a[href^='/eleve/']")
    if not apparait(a, "text=Travail à vérifier", timeout=8000):
        p.check("la fiche porte le travail a verifier (EF-C3)", False,
                a.page.url)
        return

    # EF-H2 : *« se coche d'un doigt »* — un bouton par motif courant,
    # aucun dialogue. Une note qui demande dix secondes de plus est une
    # note qu'on ne prend pas.
    p.check("les motifs courants se posent d'un seul geste (EF-H2)",
            a.has("main button:has-text('cahier incomplet')"))

    avant = a.count("text=/posé le/")
    a.click("main button:has-text('cahier incomplet')")
    a.settle()
    p.check(
        "poser un rappel l'affiche aussitot",
        devient_vrai(
            a,
            "document.querySelectorAll('main').length && "
            "(document.querySelector('main').innerText.match(/posé le/g)"
            " || []).length > " + str(avant),
            timeout=8000),
        f"{avant} avant",
    )

    # EF-H3 : la date est POSÉE, la ligne reste.
    a.click("main button:has-text(\"C'est fait\")")
    a.settle()
    p.check(
        "coche « fait », la ligne RESTE (EF-H3)",
        devient_vrai(
            a,
            "!!document.querySelector('main').innerText.match(/fait le/)",
            timeout=8000),
        "la ligne a disparu au lieu d'etre datee",
    )
    p.check("et elle est rangee dans les deja verifies",
            a.has("text=/déjà vérifié/"))


def les_rappels_et_les_cadres(p: Probe, a: Window) -> None:
    """(18) EF-I et EF-B15 — ce que l'application voit venir.

    Les deux rappels sont **calculés à la demande** : rien ne les stocke,
    donc rien ne peut diverger. Ce que le probe mesure, c'est qu'ils
    apparaissent quand ils doivent, et qu'ils se TAISENT sinon — une
    bannière permanente serait du bruit, et le cahier est explicite là-
    dessus (EF-I3 : *« mieux vaut se taire que signaler à tort »*).
    """
    print("\n(18) Les rappels et les cadres d'entree en cours")
    a.goto("/classes")
    a.settle(floor=0)
    rappels = a.page.evaluate(
        """
        (document.querySelector('main').innerText
            .match(/pas encore marquées reportées|aucune observation|"""
        """corrigée\\(s\\) après coup/g) || []).length
        """
    )
    p.check(
        "l'accueil porte les rappels calcules (EF-I1, EF-I2)",
        rappels >= 1,
        f"{rappels} rappel(s) — le jeu seme en produit au moins un",
    )

    # EF-B15 : les cadres d'entrée en cours vivent en TÊTE de la grille.
    # Ils peuvent être absents — c'est légitime un jour sans cours — donc
    # le constat porte sur l'absence d'erreur, pas sur leur présence.
    a.goto("/")
    a.settle(floor=0)
    p.check("l'emploi du temps s'ouvre toujours", a.has("text=Emploi du temps"))
    p.check(
        "et pas de bandeau « Maintenant » (EF-B16)",
        not a.has("text=/^Maintenant/"),
        "le bandeau retire deux fois est revenu",
    )


def le_soir_se_remplit(p: Probe, a: Window) -> None:
    """(19) Lot 9 — le point 5 de la recette, mot pour mot.

    *« Ouvrir le cahier, trouver la classe et la séance DÉJÀ PROPOSÉES,
    écrire, copier les deux champs, et voir la pastille apparaître sur la
    case de la grille. »*

    Le dernier constat traverse deux écrans : ce qui est consigné dans le
    cahier doit se voir dans l'emploi du temps (EF-B13). Aucun test de
    rendu par page ne peut le dire.
    """
    print("\n(19) Le soir se remplit (EF-K1 ... EF-K12)")
    a.goto("/cahier")
    if not apparait(a, "text=Ce qu'on a fait", timeout=8000):
        p.check("le cahier de texte s'ouvre", False, a.page.url)
        return

    # EF-K2 : la classe, le chapitre et la séance sont DÉJÀ choisis.
    titre = a.value("main input[name$='titre']")
    contenu = a.value("main textarea")
    p.check("la seance suivante est deja proposee (EF-K2)", bool(titre),
            titre or "(vide)")
    p.check("et le texte est deja ecrit", bool(contenu.strip()),
            contenu[:60] or "(vide)")

    # EF-K3 : DEUX boutons de copie, un par champ d'École Directe.
    copies = a.page.evaluate(
        """
        Array.from(document.querySelectorAll('main button'))
            .filter(b => b.textContent.trim().startsWith('Copier'))
            .length
        """
    )
    p.check("deux boutons de copie, un par champ (EF-K3)", copies == 2,
            f"{copies} bouton(s)")

    # On consigne, et on relit la classe et la date dans l'adresse.
    classe_visee = a.page.evaluate(
        "new URL(location.href).searchParams.get('classe')")
    a.click(bouton("Consigner"))
    a.settle()
    p.check(
        "la seance est consignee et la liste la montre",
        devient_vrai(
            a,
            "!!document.querySelector('main').innerText"
            ".includes(" + repr(titre) + ")",
            timeout=8000),
        "la seance consignee n'apparait pas dans la liste",
    )
    del classe_visee

    # EF-L1 : le tableau de progression, une ligne par classe, une
    # colonne par chapitre. C'est ce qui rend le décalage lisible d'un
    # coup d'œil plutôt qu'en lisant cinq cahiers.
    p.check("le tableau de progression est la (EF-L1)",
            a.has("text=Progression par niveau"))


def la_pastille_traverse_deux_ecrans(p: Probe, a: Window) -> None:
    """(20) EF-B13 — ce que le cahier écrit, la grille le montre.

    *« Une pastille sur la case dit que cette heure est déjà consignée au
    cahier de texte. D'un coup d'œil sur la semaine on voit ce qui reste
    à écrire. »* Le seul constat de ce probe qui relie deux écrans par
    une DONNÉE plutôt que par un lien.
    """
    print("\n(20) La pastille du cahier sur la grille (EF-B13)")
    a.goto("/")
    a.settle(floor=0)
    pastilles = a.count("main [data-icon='book-check'], "
                        "main iconify-icon[icon*='book-check']")
    p.check(
        "des heures deja consignees portent leur pastille (EF-B13)",
        pastilles >= 1,
        f"{pastilles} pastille(s) — le jeu seme consigne ~150 seances",
    )

    # EF-B14 : la case mène à DEUX endroits, et le second existe enfin.
    p.check(
        "une case mene aussi au cahier de texte, avec sa date (EF-B14)",
        a.count("main a[href^='/cahier?classe=']") >= 1,
        a.count("main a[href^='/cahier?classe=']"),
    )


def limport_se_fait_en_deux_temps(p: Probe, a: Window) -> None:
    """(21) Lot 10 — EF-J1, rendu STRUCTUREL.

    *« Rien n'entre en base avant que le professeur ait vu la liste — un
    import est la seule opération qui crée trois cents élèves d'un
    coup. »* Le constat qui compte mesure donc une ABSENCE : avant
    l'analyse, les deux boutons d'écriture n'existent pas dans le DOM.
    Un écran qui les grise les laisserait atteignables au clavier.
    """
    print("\n(21) L'import en deux temps (EF-J1 ... EF-J7)")
    a.goto("/import")
    if not apparait(a, "text=1 · On analyse", timeout=8000):
        p.check("l'ecran d'import s'ouvre", False, a.page.url)
        return

    ecriture = a.count("main button:has-text('Ajouter les élèves'), "
                       "main button:has-text('Remplacer les photos')")
    p.check(
        "avant l'analyse, aucun bouton n'ecrit (EF-J1)",
        ecriture == 0,
        f"{ecriture} bouton(s) d'ecriture deja la",
    )

    a.page.fill("main input[name$='code']", "3eTEST")
    a.page.fill("main textarea",
                "COURTY;Léane" + chr(10) + "VALLOIS;Malo" + chr(10) + "MALO")
    a.click(bouton("Analyser"))
    a.settle()
    p.check(
        "l'analyse ouvre le second temps",
        devient_vrai(
            a,
            "!!document.querySelector('main').innerText"
            ".includes('2 · On valide')",
            timeout=8000),
        "le second temps ne s'ouvre pas",
    )

    # EF-J4 : DEUX boutons, et ils ne font pas la meme chose.
    p.check("deux boutons separes, pas un (EF-J4)",
            a.has("main button:has-text('Ajouter les élèves')")
            and a.has("main button:has-text('Remplacer les photos')"))

    # EF-J7 : ce qu'on ne reconnait pas est DIT, pas devine.
    p.check("la ligne illisible est signalee (EF-J7)",
            a.has("text=nom et prénom attendus"))


def limport_refuse_une_classe_pleine(p: Probe, a: Window) -> None:
    """(22) EF-J3 — *« un second passage y dupliquerait la liste »*."""
    print("\n(22) Une classe deja pleine refuse l'import (EF-J3)")
    a.goto("/import")
    if not apparait(a, "text=1 · On analyse", timeout=8000):
        p.check("l'ecran d'import s'ouvre", False, a.page.url)
        return
    a.page.fill("main input[name$='code']", "6e2")
    a.page.fill("main textarea", "COURTY;Léane")
    a.click(bouton("Analyser"))
    a.settle()
    p.check(
        "le refus est dit, avec son chiffre",
        devient_vrai(
            a,
            "!!document.querySelector('main').innerText"
            ".match(/a déjà \\d+ élèves/)",
            timeout=8000),
        "aucun refus a l'ecran",
    )
    grises = a.page.evaluate(
        """
        Array.from(document.querySelectorAll('main button'))
            .filter(b => /Ajouter les élèves|Remplacer les photos/
                            .test(b.textContent))
            .every(b => b.disabled)
        """
    )
    p.check("et les deux boutons d'ecriture sont grises", grises)


def larchive_se_relit(p: Probe, a: Window) -> None:
    """(23) EF-N — *« une archive, pas un bulletin »*.

    *« Elle doit se relire dans dix ans sans le programme qui l'a
    produite. Imprimable et complète. »* Tout sur une page : trois
    onglets seraient plus propres à l'écran et perdraient à l'impression.
    """
    print("\n(23) L'archive d'une classe (EF-N1, EF-N2)")
    a.goto("/import?vue=archives")
    if not apparait(a, "text=Trombinoscope", timeout=8000):
        p.check("l'archive s'ouvre", False, a.page.url)
        return
    p.check("l'archive porte sa date de fabrication (EF-N2)",
            a.has("text=archive fabriquée le"))
    p.check("et le trombinoscope de la classe (EF-N1)",
            a.count("main img, main span[class*=rounded-full]") >= 10)
    p.check("avec les moyennes generales",
            a.has("text=/Moyenne générale/"))
    p.check("et un bouton d'impression",
            a.has("main button:has-text('Imprimer')"))


def rien_ne_se_perd_dans_la_grille(p: Probe, a: Window) -> None:
    """(24) Trois défauts qui rendaient tous un HTML JUSTE (F8, F9, F10).

    C'est ce qu'ils ont en commun, et c'est pour ça qu'ils sont ici
    plutôt que dans un test : ``TestClient`` était vert sur les trois.
    Ce qui trahissait était ailleurs — le parseur du navigateur, le
    thème d'un composant, l'arithmétique de l'app.

    **Ce qui est coupé (F9).** Les cases portent une hauteur calculée —
    c'est ce qui tient les six colonnes alignées sur leurs heures — et
    ``ui.card`` pose ``overflow:hidden``. Une carte trop courte perd son
    contenu **en silence** : mesurée à 52 px, une heure simple affichait
    sa classe et rien d'autre. Reprise à 64, il en fallait 80 : le
    rembourrage du thème mangeait la moitié de la case.

    **Ce qui sort de la carte (F8).** Un ``ui.link`` DANS une carte
    cliquable. HTML interdit le lien gigogne, donc le parseur ferme le
    premier ``<a>`` en rencontrant le second et tout ce qui suit
    atterrit DEHORS — 130 px de vide, et le nom de la salle affiché
    dans la case de l'heure d'après.

    **Ce qui glisse (F10).** La hauteur d'un bloc de N heures vaut
    ``N × case + (N-1) × espace``, et cet espace doit être exactement le
    ``gap`` de la colonne. Il valait 6 px pour un ``gap-1`` de 4 :
    chaque bloc de deux heures descendait SA colonne de 2 px, donc un
    jour cessait d'être en face de son horaire, et l'écart grandit avec
    le nombre de blocs.
    """
    print("\n(24) Rien ne se perd dans la grille (F8, F9, F10)")
    a.goto("/")
    a.settle(floor=300)

    cases = a.count("main [style*='height']")
    p.check("des cases à hauteur imposée sont bien là", cases >= 10, cases)

    rognees = a.page.evaluate(
        """
        Array.from(document.querySelectorAll('main [style*="height"]'))
            .filter(function (el) {
                // Un conteneur qui DEFILE a le droit de deborder : son
                // contenu reste atteignable. Ce qu'on cherche, c'est ce
                // qui est coupe pour de bon.
                const coupe = getComputedStyle(el).overflowY;
                return (coupe === 'hidden' || coupe === 'clip')
                    && el.clientHeight > 0
                    && el.scrollHeight > el.clientHeight + 2;
            })
            .map(el => el.innerText.replace(/\\s+/g, ' ').slice(0, 24)
                       + ' (' + el.clientHeight + ' pour '
                       + el.scrollHeight + ')')
        """
    )
    p.check("aucune case ne coupe ce qu'elle porte", not rognees, rognees)

    gigognes = a.page.evaluate("document.querySelectorAll('a a').length")
    p.check("aucun lien n'est imbriqué dans un autre", gigognes == 0,
            gigognes)

    # ⚠️ On lit la DERNIÈRE CASE de chaque colonne, pas la colonne :
    # les enfants d'une grille s'étirent (``align-items: stretch``), donc
    # leurs boîtes finissent toutes au même pixel quoi qu'elles portent.
    # Un constat écrit sur les colonnes serait vert par construction.
    colonnes = a.page.evaluate(
        """
        Array.from(document.querySelectorAll('main [class*="grid-cols-"]'))
            .filter(g => g.children.length === 7)
            .slice(0, 1)
            .flatMap(g => Array.from(g.children))
            .map(function (c) {
                const dernier = c.lastElementChild;
                return dernier
                    ? Math.round(dernier.getBoundingClientRect().bottom)
                    : null;
            })
        """
    )
    p.check("les sept colonnes de la grille sont bien mesurées",
            len(colonnes) == 7 and all(c is not None for c in colonnes),
            colonnes)
    ecart = max(colonnes) - min(colonnes) if colonnes else -1
    p.check("les sept colonnes finissent au même pixel", 0 <= ecart <= 1,
            f"{ecart} px d'écart : {colonnes}")


def les_champs_ont_tous_la_meme_hauteur(p: Probe, a: Window) -> None:
    """(25) Une table de tailles écrite à la main est TOUJOURS partielle.

    ⚠️ **Le défaut que ce constat garde a été vu par l'utilisateur sur
    une capture, pas par une vérification.** Trois contrôles côte à côte
    — une date, un choix, un nombre — à trois hauteurs différentes.

    La cause était un thème d'app qui écrivait ses tailles composant par
    composant : onze noms cités, et ``ui.date_picker`` comme
    ``ui.number_input`` n'en faisaient pas partie, donc ils gardaient la
    hauteur par défaut pendant que leurs voisins descendaient. Mesuré
    sur ``/reglages`` : **quatre hauteurs de champ texte sur un écran —
    30, 32, 36 et 38 px**.

    Rien ne pouvait le dire. ``bretzel check`` a bien une règle pour les
    champs FRÈRES à des tailles différentes, mais elle compare les
    ``size=`` DÉCLARÉS : ici ils étaient tous au défaut, et c'est le
    thème qui les séparait. La suite était verte, le HTML juste, et le
    seul symptôme était visuel.

    Ce qui le garde maintenant, c'est la mesure : sur chaque écran, les
    champs texte visibles doivent rendre **une seule** hauteur. Le vrai
    correctif, lui, est ailleurs — la densité se règle par ``--spacing``,
    un jeton dont TOUTE l'échelle Tailwind dérive, donc sans liste à
    tenir à jour (cf. ``Theme(spacing=…)`` et le préréglage
    ``bretzel.theme.presets.COMPACT``).
    """
    print("\n(25) Les champs ont tous la meme hauteur")
    # ⚠️ On mesure le CADRE, pas l'``<input>``. Un ``ui.input`` porte sa
    # bordure et sa hauteur sur le même élément ; un ``ui.date_picker``
    # met la bordure sur un cadre et l'entrée DEDANS. Mesurer les
    # ``<input>`` compare donc deux étages différents et rend 31 contre
    # 33 sur des contrôles parfaitement alignés à l'écran — le piège
    # « la hauteur d'un palier vit sur l'élément BORDÉ ».
    hauteurs_js = """
        Array.from(document.querySelectorAll('main [class*="rounded-field"]'))
            .filter(function (el) {
                if (!el.offsetParent) return false;
                if (el.tagName === 'BUTTON' || el.tagName === 'TEXTAREA') {
                    return false;
                }
                const s = getComputedStyle(el);
                if (parseFloat(s.borderTopWidth) < 0.5) return false;
                const h = el.getBoundingClientRect().height;
                return h > 4 && h < 60;
            })
            .map(el => Math.round(el.getBoundingClientRect().height))
    """
    for route, mini in (("/reglages", 6), ("/cahier", 3)):
        a.goto(route)
        a.settle(floor=400)
        hauteurs = a.page.evaluate(hauteurs_js)
        # Le plancher : sans champ mesuré, « une seule hauteur » est vrai
        # de l'ensemble vide, et le constat passerait en ne regardant rien.
        p.check(f"{route} montre bien ses champs",
                len(hauteurs) >= mini, f"{len(hauteurs)} champ(s)")
        distinctes = sorted(set(hauteurs))
        ecart = distinctes[-1] - distinctes[0] if distinctes else 0
        p.check(
            f"{route} : les champs tiennent dans {RESIDU} px d'écart",
            ecart <= RESIDU,
            f"{distinctes} px",
        )


def main() -> None:
    with probe(APP) as p:
        (a,) = p.windows
        laccueil_montre_les_classes(p, a)
        lannee_change_les_deux(p, a)
        rien_ne_secrit_trop_petit(p, a)
        le_plein_ecran_est_joignable(p, a)
        les_reglages_se_lisent(p, a)
        rt1_ferme_les_reglages(p, a)
        la_grille_se_lit(p, a)
        les_blocs_et_les_tp(p, a)
        les_jours_sans_classe(p, a)
        les_heures_exceptionnelles(p, a)
        une_classe_et_ses_eleves(p, a)
        la_recherche_garde_les_deux_champs(p, a)
        la_saisie_de_masse(p, a)
        lappreciation_se_propose_et_se_garde(p, a)
        le_bilan_se_tait_quand_il_ne_sait_pas(p, a)
        le_plan_se_fait_et_se_fige(p, a)
        le_travail_a_verifier(p, a)
        les_rappels_et_les_cadres(p, a)
        le_soir_se_remplit(p, a)
        la_pastille_traverse_deux_ecrans(p, a)
        limport_se_fait_en_deux_temps(p, a)
        limport_refuse_une_classe_pleine(p, a)
        larchive_se_relit(p, a)
        rien_ne_se_perd_dans_la_grille(p, a)
        les_champs_ont_tous_la_meme_hauteur(p, a)


# Pas de fonction ``test_*`` ici, et c'est voulu : ``tests/probes/
# test_probes.py`` lance CHAQUE probe en sous-processus et juge son code
# de sortie. Une seconde porte d'entrée le ferait collecter aussi par le
# run rapide — qui n'a ni marqueur ``probes`` ni Chromium à y consacrer.
if __name__ == "__main__":
    main()
