"""Probe — l'atelier rend ce qu'il promet, et sa mesure n'est pas creuse.

Ce qu'un ``TestClient`` ne dit pas
----------------------------------
Les quatre pages rendent 200 avec une base vide comme avec 34 000 appels.
Ce qui compte ici n'est pas le code de statut : c'est qu'il y ait des
CHIFFRES à l'écran, que la table trie pour de vrai — donc que sa zone
`@refreshable` soit branchée, ce que le rendu serveur ne montre pas — et
qu'une frise de tâche se lise.

Le deuxième porte un défaut déjà rencontré : une ``ui.datatable`` hors
d'une zone qui surveille son état poste et ne change rien. Le framework
le refuse au montage, mais seul un clic prouve que le câblage tient.

Run :  py tests/probes/probe_atelier.py
"""

from __future__ import annotations

import sys

from bretzel.probe import Probe, Window, probe

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

APP = "examples.atelier.main:app"


def nombres(w: Window, selecteur: str) -> list[str]:
    """Les textes non vides sous un sélecteur — pour prouver le non-creux."""
    return [
        t.strip()
        for t in w.page.locator(selecteur).all_inner_texts()
        if t.strip()
    ]


def le_rythme(p: Probe, a: Window) -> None:
    """① L'écran qui répond à la question posée."""
    print("\n① Le rythme")
    a.goto("/")

    p.check("le titre est rendu", a.has("text=Le rythme"))
    p.check("la règle des cycles est dite", a.has("text=cycles de vérification"))

    # Les quatre compteurs du haut. Une app branchée sur une base vide
    # rendrait la même page avec des zéros : on exige du non-nul.
    #
    # ⚠️ Visé par la CLASSE de taille du nombre et non par un
    # `[data-bz-card]`, qui n'existe pas : `ui.card` rend un `<div>` sans
    # marqueur, et un sélecteur inventé rendrait ce constat rouge pour
    # une raison qui ne concerne pas l'app. Trouvé en le lançant.
    chiffres = nombres(a, ".text-2xl")
    p.check("les compteurs du haut portent des chiffres",
            len(chiffres) >= 4 and any(
                any(c.isdigit() for c in t) for t in chiffres
            ), chiffres[:4])

    lignes = a.count("tbody tr")
    p.check("la table porte des tâches", lignes > 0, lignes)

    # ⚠️ La frise n'est plus UN texte : c'est une lettre par élément,
    # chacune peinte par sa phase. Le constat vise donc la structure — un
    # `text=/[LÉVC] [LÉVC]/` marchait quand les lettres étaient collées
    # dans une chaîne, et il est devenu faux le jour où la couleur est
    # arrivée, sans que l'app ait rien perdu.
    lettres = a.page.evaluate(
        "() => { const c = document.querySelector('tbody tr td:last-child');"
        r" return c ? c.innerText.replace(/\s+/g, '') : ''; }"
    )
    p.check("la frise rend ses lettres",
            bool(lettres) and all(ch in "LÉVC·…" for ch in lettres), lettres)

    couleurs = a.page.evaluate(
        "() => new Set([...document.querySelectorAll("
        "'tbody td:last-child [class*=bz-c-]')]"
        ".map(e => [...e.classList].find(c => c.startsWith('bz-c-')))).size"
    )
    p.check("et elles sont PEINTES par leur phase", couleurs >= 2, couleurs)

    p.check("la légende de la frise est sur CET écran",
            a.has("text=lire et comprendre"))


def la_table_trie(p: Probe, a: Window) -> None:
    """② Le câblage que seul un clic prouve.

    Trier MUTE l'état de la table. Sans zone `@refreshable` qui le
    surveille, le contrôle poste et l'écran ne bouge pas — un défaut
    silencieux, invisible au rendu serveur.
    """
    print("\n② Trier change vraiment la page")
    a.goto("/")
    avant = a.text("tbody tr")

    with p.requests() as net:
        a.click("th:has-text('Appels')")

    apres = a.text("tbody tr")
    p.check("le tri atteint le serveur", net.total >= 1, net.urls)
    p.check("et la première ligne a changé", avant != apres,
            f"{avant[:40]!r} inchangée")
    p.check("l'adresse porte le tri", "tri=" in a.page.url, a.page.url)


def la_frise(p: Probe, a: Window) -> None:
    """③ Le détail d'une tâche : la suite des appels, dans l'ordre."""
    print("\n③ La frise d'une tâche")
    # ⚠️ On CLIQUE la première ligne, on ne fabrique pas ``/tache/1``.
    # Deux raisons, et les deux ont mordu le 2026-09-12 : les écrans ne
    # lisent que les tâches de l'époque (`core/epoque`), donc l'id 1 rend
    # « n'existe pas » ; et un probe qui tape l'adresse n'emprunte pas le
    # chemin de l'utilisateur — c'est ce qui a laissé passer un clic de
    # ligne qui rendait 500, puis une navigation qui repeignait tout.
    a.goto("/")
    # Un témoin que seul un rechargement complet du document efface.
    a.page.evaluate("window.__coque = 1")

    with p.requests() as net:
        a.click("tbody tr:first-child a")
    p.settle()

    p.check("la tâche existe et se rend", not a.has("text=n'existe pas"))
    p.check("le clic a bien ouvert une fiche", "/tache/" in a.page.url,
            a.page.url)
    # ⚠️ LE test de la coque. Sans lui, le défaut est invisible : la
    # bonne page s'affiche, à la bonne adresse — simplement la barre
    # latérale a clignoté et tout l'état client est parti. Aucune autre
    # suite du dépôt ne navigue, donc rien d'autre ne peut le voir.
    p.check("la coque a survécu — pas de rechargement complet",
            a.page.evaluate("window.__coque === 1"))
    p.check("une navigation = une requête", net.total == 1, net.urls)
    p.check("la légende des phases est là", a.has("text=lire et comprendre"))
    appels = a.count("text=/^(lecture|ecriture|verification|livraison|autre)$/")
    p.check("les appels sont listés avec leur phase", appels > 0, appels)

    a.goto("/tache/999999")
    p.check("une tâche absente le DIT au lieu de rendre du vide",
            a.has("text=n'existe pas"))


def les_outils(p: Probe, a: Window) -> None:
    """④ La couche 7 : est-ce qu'elle sert ?"""
    print("\n④ Les outils")
    a.goto("/outils")

    for nom in ("describe", "check", "probe"):
        p.check(f"`{nom}` a sa carte", a.has(f"text={nom}"))
    p.check("le taux d'échec par outil est rendu", a.count("tbody tr") > 0)


def les_phases(p: Probe, a: Window) -> None:
    """⑤ Le profil de travail, et son aveu."""
    print("\n⑤ Les phases")
    a.goto("/phases")

    barres = a.count("[role=progressbar], progress")
    p.check("chaque phase a sa barre", barres >= 4, barres)
    p.check("la part non classée est montrée", a.has("text=autre"))


#: ⚠️ UN probe PAR scénario, et pas une boucle dans un seul.
#:
#: Le balayage gratuit tourne à la sortie du ``with`` et mesure la page où
#: la fenêtre se trouve ALORS. Une boucle interne charge donc cinq pages
#: pour n'en juger qu'une — la dernière. Mesuré : la version d'hier
#: finissait sur `/phases` et rendait 28/28 pendant que `/` portait DEUX
#: barres de défilement imbriquées, que l'utilisateur a vues à l'écran.
#: C'est exactement le piège que le CLI documente dans `_probe`.
SCENARIOS = (le_rythme, la_table_trie, la_frise, les_outils, les_phases)


def main() -> None:
    for scenario in SCENARIOS:
        with probe(APP) as p:
            (a,) = p.windows
            scenario(p, a)


# Pas de fonction ``test_*`` : ``tests/probes/test_probes.py`` lance chaque
# probe en sous-processus et juge son code de sortie. Une seconde porte le
# ferait collecter par le run rapide, qui n'a pas de Chromium à y consacrer.
if __name__ == "__main__":
    main()
