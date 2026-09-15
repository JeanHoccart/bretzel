"""Probe — ``/dnd`` : ce que le geste MONTRE, mesuré pendant le geste.

Ce que ça mesure, et pourquoi aucun test de rendu ne le mesure
--------------------------------------------------------------
Deux choses qui n'existent que **pendant le geste**, pointeur enfoncé :
où l'item atterrit quand on hésite, et ce qu'une zone à UN élément fait
d'un dépôt. Un ``TestClient`` ne voit ni l'un ni l'autre — il lit le
document au repos, et le repos est précisément l'état où tout va bien.

⚠️ **Le défilement fait partie du geste.** Les chaises vivent loin sous
la ligne de flottaison — la page du composant est longue. La première version de ce probe
envoyait le pointeur à ``y = 1257`` dans une fenêtre haute de 1000 : rien
ne se passait, aucune requête ne partait, et le constat accusait la page.
Un geste qu'on joue hors de l'écran ne mesure pas l'écran.

Run :  py tests/probes/probe_dnd.py
       py -m pytest tests/probes/probe_dnd.py -m probes
"""

from __future__ import annotations

import sys

from bretzel.probe import Probe, Window, probe

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

APP = "examples.playground.main:app"

def le_banc_dapercu_est_en_place(p: Probe, a: Window) -> None:
    """① Le banc existe, et il porte ce qu'il annonce."""
    print("\n① Les quatre cartes du banc")
    a.goto("/dnd")
    a.settle(floor=900)
    # Le banc d'aperçu vit dans la carte « Edge cases » de la page du
    # composant, pas sur une page à lui : un banc qui invente sa propre
    # forme se lit comme une exception, et la page de `dropzone` est
    # l'endroit où quelqu'un ira chercher ce que le geste montre.
    p.check("les deux chaises sont là",
            all(a.count(f"[data-bz-dropzone='{z}']") == 1
                for z in ("chaise_g", "chaise_d")),
            [z for z in ("chaise_g", "chaise_d")
             if a.count(f"[data-bz-dropzone='{z}']") != 1])


def une_zone_a_un_element_ecrase(p: Probe, a: Window) -> None:
    """② `holds="one"` : la cible s'annonce écrasable et ne reçoit RIEN.

    ⚠️ **Le défaut avant le 2026-09-13 était d'insérer, toujours.** Le
    runtime glisse le vrai nœud dans la zone survolée — c'est ce qui rend
    l'aperçu gratuit sur une liste. Sur une chaise, ça donnait DEUX
    occupants le temps du survol : la boîte s'ouvrait, le plan se
    décalait, et on ne voyait plus où l'on posait. C'est ce qu'un
    utilisateur a décrit par « l'item prend énormément de place ».

    `holds="one"` ne change pas ce que le dépôt FAIT — c'est le handler
    qui échange, côté serveur, et il l'a toujours fait. Il change ce que
    le geste ANNONCE : la cible ne bouge pas, elle s'éclaire comme
    remplaçable.

    Les deux constats doivent tenir ENSEMBLE. Une cible qui ne reçoit
    rien sans s'annoncer serait un geste muet ; une cible qui s'annonce
    en recevant quand même serait le défaut d'avant, repeint.
    """
    print("\n② Une zone à un élément écrase")
    cible = a.page.locator("[data-bz-dropzone='chaise_d']")
    cible.scroll_into_view_if_needed()
    a.settle(floor=300)
    src = a.page.locator("[data-bz-dropzone='chaise_g'] [data-bz-draggable]")
    b, d = src.first.bounding_box(), cible.first.bounding_box()
    a.page.mouse.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
    a.page.mouse.down()
    for i in range(1, 7):
        a.page.mouse.move(
            b["x"] + b["width"] / 2
            + (d["x"] + d["width"] / 2 - b["x"] - b["width"] / 2) * i / 6,
            b["y"] + b["height"] / 2
            + (d["y"] + d["height"] / 2 - b["y"] - b["height"] / 2) * i / 6,
        )
    a.settle(floor=300)
    pendant = a.page.evaluate(
        """
        (function () {
            const d = document.querySelector(
                "[data-bz-dropzone='chaise_d']");
            return {occupants: d.querySelectorAll(
                        '[data-bz-draggable]').length,
                    marque: d.getAttribute('data-bz-drop-replace')};
        })()
        """
    )
    a.shot("holds-one-survol")
    a.page.mouse.up()
    a.settle(floor=900)

    p.check("la cible n'a jamais porté deux occupants",
            pendant["occupants"] == 1, pendant)
    p.check("et elle s'est annoncée écrasable",
            pendant["marque"] == "true", pendant)
    reste = a.page.evaluate(
        "document.querySelectorAll('[data-bz-drop-replace]').length")
    p.check("la marque ne survit pas au geste", reste == 0, reste)


def une_chaise_occupee_echange(p: Probe, a: Window) -> None:
    """③ La zone à UN élément : le dépôt permute, il n'insère pas.

    C'est le cas que l'emplacement mince NE couvre pas, et c'est
    l'argument de la proposition : ouvrir un espace d'insertion sur une
    chaise annoncerait quelque chose qui n'arrivera pas.
    """
    print("\n③ Deux chaises : le dépôt ÉCHANGE")
    cible = a.page.locator("[data-bz-dropzone='chaise_d']")
    cible.scroll_into_view_if_needed()
    a.settle(floor=300)
    avant_g = a.text("[data-bz-dropzone='chaise_g']").strip()
    avant_d = a.text("[data-bz-dropzone='chaise_d']").strip()

    src = a.page.locator("[data-bz-dropzone='chaise_g'] [data-bz-draggable]")
    b, d = src.first.bounding_box(), cible.first.bounding_box()
    a.page.mouse.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
    a.page.mouse.down()
    for i in range(1, 9):
        a.page.mouse.move(
            b["x"] + b["width"] / 2
            + (d["x"] + d["width"] / 2 - b["x"] - b["width"] / 2) * i / 8,
            b["y"] + b["height"] / 2
            + (d["y"] + d["height"] / 2 - b["y"] - b["height"] / 2) * i / 8,
        )
    a.settle(floor=300)
    p.check("la chaise visée s'annonce comme une cible",
            a.count("[data-bz-drop-ok='true']") >= 1,
            a.count("[data-bz-drop-ok='true']"))
    a.shot("chaises-en-vol")
    a.page.mouse.up()
    a.settle(floor=900)

    apres_g = a.text("[data-bz-dropzone='chaise_g']").strip()
    apres_d = a.text("[data-bz-dropzone='chaise_d']").strip()
    p.check("les deux occupants ont permuté",
            apres_g == avant_d and apres_d == avant_g,
            f"{avant_g!r}/{avant_d!r} → {apres_g!r}/{apres_d!r}")
    # Le PLANCHER du constat : deux chaises vides permuteraient aussi, et
    # l'égalité ci-dessus serait vraie sans que rien ne bouge.
    p.check("et les deux chaises portaient bien quelqu'un",
            bool(avant_g) and bool(avant_d), f"{avant_g!r}/{avant_d!r}")


def le_defaut_garde_la_carte_et_publie_son_axe(p: Probe, a: Window) -> None:
    """③ Le DÉFAUT : la carte garde sa taille, et l'axe reste offert.

    Deux moitiés, et la seconde est celle qui coûte.

    **Le défaut** : une carte en vol garde sa boîte. La zone d'arrivée
    s'ouvre de la hauteur d'une carte, et ce qu'on voit est ce qu'on va
    obtenir, à l'échelle où on l'obtiendra. L'autre convention — un
    emplacement fin — a été essayée, mesurée et retirée du défaut le
    2026-09-13.

    **Le hook** : le runtime publie quand même ``data-bz-drag-axis`` sur
    l'élément en vol, pour une zone qui INSÈRE. C'est ce qui permet à une
    app de choisir l'emplacement en surchargeant le slot ``dragging``,
    sans prop. Un hook que personne ne mesure finit par disparaître à la
    première refonte, et l'échappatoire documentée devient un mensonge.

    Une zone ``holds="one"``, elle, n'en reçoit pas : elle n'insère rien.
    """
    print("\n③ Le défaut garde la carte, et publie son axe")

    def en_vol(zone: str, dy: int) -> tuple[float, float, str | None]:
        items = a.page.locator(
            f"[data-bz-dropzone='{zone}'] [data-bz-draggable]")
        items.first.scroll_into_view_if_needed()
        a.settle(floor=200)
        repos = items.first.bounding_box()
        a.page.mouse.move(repos["x"] + repos["width"] / 2,
                          repos["y"] + repos["height"] / 2)
        a.page.mouse.down()
        for i in range(1, 6):
            a.page.mouse.move(repos["x"] + repos["width"] / 2,
                              repos["y"] + repos["height"] / 2 + dy * i / 5)
        a.settle(floor=300)
        vole = a.page.locator("[data-bz-dragging='true']").first
        boite = vole.bounding_box()
        axe = vole.get_attribute("data-bz-drag-axis")
        a.page.mouse.up()
        a.settle(floor=700)
        return repos["height"], boite["height"], axe

    liste_repos, liste_vol, liste_axe = en_vol("ref_basic", 90)
    p.check("la carte en vol garde sa taille",
            abs(liste_vol - liste_repos) < 3,
            f"{liste_vol:.0f} px pour {liste_repos:.0f} au repos")
    p.check("et la liste publie son axe — l'échappatoire du thème",
            liste_axe in ("x", "y"), liste_axe)

    chaise_repos, chaise_vol, chaise_axe = en_vol("chaise_g", 40)
    p.check("une zone holds=one ne publie aucun axe",
            chaise_axe is None, chaise_axe)
    p.check("et son occupant garde sa taille lui aussi",
            abs(chaise_vol - chaise_repos) < 3,
            f"{chaise_vol:.0f} px pour {chaise_repos:.0f} au repos")


def un_glisser_qui_hesite_ne_perd_pas_sa_boite(p: Probe, a: Window) -> None:
    """④ Sortir d'une zone, changer d'avis, revenir.

    ⚠️ **Le geste ordinaire, et il était cassé jusqu'au 2026-09-13.**
    Quand on ramène un item dans sa zone d'origine, celle-ci est VIDE —
    l'item en est sorti une seconde plus tôt. Le runtime n'avait alors
    « plus rien à quoi se raccrocher » et le ré-attachait à la ZONE,
    c'est-à-dire hors du conteneur que l'app a rendu (un `vstack`, une
    grille). L'item s'affichait À CÔTÉ de sa boîte.

    Le commentaire du runtime disait que le prochain rendu serveur
    remettrait la carte dans la pile. Il ne la remet pas : le nœud garde
    son `bz-id`, qui encode son chemin dans l'arbre, ce chemin a changé,
    donc idiomorph ne le ré-apparie pas et la carte reste où elle est.

    Rien ne le signalait — ni erreur, ni requête en échec, ni rognage :
    l'item est parfaitement visible, simplement au mauvais endroit. Il a
    fallu qu'un utilisateur envoie une capture.
    """
    print("\n④ Un glisser qui hésite")
    cible = a.page.locator("[data-bz-dropzone='chaise_d']")
    cible.scroll_into_view_if_needed()
    a.settle(floor=300)
    source = a.page.locator("[data-bz-dropzone='chaise_g']")
    item = a.page.locator("[data-bz-dropzone='chaise_g'] [data-bz-draggable]")
    p.check("il y a bien quelqu'un à déplacer", item.count() == 1,
            item.count())

    b = item.first.bounding_box()
    g, d = source.first.bounding_box(), cible.first.bounding_box()
    cg = (g["x"] + g["width"] / 2, g["y"] + g["height"] / 2)
    cd = (d["x"] + d["width"] / 2, d["y"] + d["height"] / 2)
    a.page.mouse.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
    a.page.mouse.down()
    for i in range(1, 7):                       # on part
        a.page.mouse.move(cg[0] + (cd[0] - cg[0]) * i / 6, cd[1])
    a.settle(floor=200)
    for i in range(1, 7):                       # on revient
        a.page.mouse.move(cd[0] + (cg[0] - cd[0]) * i / 6, cg[1])
    a.settle(floor=200)
    a.page.mouse.up()
    a.settle(floor=900)

    dehors = a.page.evaluate(
        """
        ['chaise_g', 'chaise_d'].filter(function (n) {
            const z = document.querySelector(
                "[data-bz-dropzone='" + n + "']");
            const it = z && z.querySelector('[data-bz-draggable]');
            return it && it.parentElement === z;
        })
        """
    )
    p.check("aucun occupant n'est enfant DIRECT de sa zone", not dehors,
            dehors)


def main() -> None:
    with probe(APP, size=(1440, 1000)) as p:
        (a,) = p.windows
        le_banc_dapercu_est_en_place(p, a)
        une_zone_a_un_element_ecrase(p, a)
        une_chaise_occupee_echange(p, a)
        le_defaut_garde_la_carte_et_publie_son_axe(p, a)
        un_glisser_qui_hesite_ne_perd_pas_sa_boite(p, a)


if __name__ == "__main__":
    main()
