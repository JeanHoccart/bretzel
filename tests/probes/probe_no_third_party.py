"""Probe — une page Bretzel ne parle à PERSONNE d'autre qu'à son serveur.

Ce qu'il garde
--------------

Une page chargeait quatre choses qui ne viennent pas de nous : htmx,
idiomorph, le composant web iconify, le compilateur Tailwind de dev — et
une cinquième, invisible dans le HTML parce qu'elle part à l'exécution :
les DONNÉES d'icône, que le composant va chercher chez trois hôtes
Iconify.

Pourquoi ça se mesure ICI et pas dans une gate
-----------------------------------------------

Aucune lecture de source ne dit ce qu'un navigateur demande vraiment. Le
composant iconify ne nomme ses hôtes nulle part dans notre code : ils sont
dans SON bundle, et il les interroge quand une icône apparaît. Le seul
instrument qui puisse trancher est une page qui tourne, avec un compteur
de requêtes.

Ce que ça a coûté avant d'être gardé
-------------------------------------

Le compilateur Tailwind venait d'unpkg à chaque page — 276 Ko et deux
allers-retours. Mesuré le 2026-09-13 en le coupant : *aucune* feuille
n'est produite, et l'encre d'un bouton passe de ``oklab(…)`` à
``rgb(0, 0, 0)``. Les 84 probes tournant en dev, la fiabilité de la suite
entière tenait à un site tiers — et sa rouge se déplaçait d'un probe à
l'autre sans jamais parler du code.

Les glyphes, eux, ne déplacent aucune géométrie (une icône absente garde
sa boîte, dimensionnée en ``1em``), donc ils ne fabriquaient pas de
rouges. Ils restaient une dépendance : les trois hôtes coupés rendent
**0 glyphe sur 25**.

Run :  py tests/probes/probe_no_third_party.py
"""

from __future__ import annotations

from bretzel.probe import Probe, Window, probe
from tests.probes._serve import use_local_tailwind

APP = "tests.probes.bench_datatable_filter:app"

#: Ce qu'on lit sur la page : l'encre prouve que le compilateur a
#: COMPILÉ — une page sans feuille rend du noir — et le compte de glyphes
#: que les données d'icône sont arrivées.
LIRE = """() => {
  const ic = [...document.querySelectorAll('iconify-icon')];
  const b = document.querySelector('button');
  return {
    encre: b ? getComputedStyle(b).color : 'aucun bouton',
    glyphes: ic.filter(e => e.shadowRoot
                       && e.shadowRoot.querySelector('svg')).length,
    icones: ic.length,
  };
}"""


def rien_ne_sort_de_la_machine(p: Probe, a: Window) -> None:
    """① Recharger, et compter ce qui part ailleurs que chez nous.

    Le harnais ouvre une fenêtre VIERGE — il ne navigue pas à notre place
    — donc la première peinture est encore devant nous, et c'est elle
    qu'on veut compter : les scripts tiers partent là, pas ailleurs.
    """
    with p.requests() as net:
        a.goto("/")
    a.settle()
    # Les glyphes partent quand l'icône APPARAÎT, pas au chargement.
    p.hold(1.5)

    # ⚠️ ``net.urls`` rend un CHEMIN pour ce qui vient de notre serveur
    # (``/``, ``/_bretzel/…``) et une URL ENTIÈRE pour le reste. Un tiers
    # est donc exactement ce qui porte un schéma sans être la boucle
    # locale — filtrer l'inverse prenait toute la page pour un tiers.
    tiers = [
        u for u in net.urls
        if u.startswith(("http://", "https://"))
        and not u.startswith(("http://127.0.0.1", "http://localhost"))
    ]
    p.check(
        "aucune requête ne sort vers un tiers",
        not tiers,
        f"{tiers} — rapatrie-les (python -m bretzel.render.vendor) ou "
        f"explique pourquoi celui-là doit rester dehors",
    )


def la_page_rend_vraiment(p: Probe, a: Window) -> None:
    """② Le versant LICITE : couper un tiers ne doit pas tout casser.

    Sans lui, un repli qui servirait une page NUE passerait le constat ①
    avec brio — zéro requête sortante, et zéro style. C'est le pire des
    verts : celui qui mesure l'absence.
    """
    m = a.page.evaluate(LIRE)
    p.check(
        "le compilateur a bien compilé",
        m["encre"] not in ("rgb(0, 0, 0)", "aucun bouton"),
        f"encre {m['encre']} — du noir pur veut dire qu'AUCUNE feuille "
        f"n'a été produite",
    )
    p.check(
        "tous les glyphes sont arrivés",
        m["icones"] > 0 and m["glyphes"] == m["icones"],
        f"{m['glyphes']}/{m['icones']}",
    )


def main() -> None:
    use_local_tailwind()
    with probe(APP) as p:
        (a,) = p.windows
        rien_ne_sort_de_la_machine(p, a)
        la_page_rend_vraiment(p, a)


if __name__ == "__main__":
    main()
