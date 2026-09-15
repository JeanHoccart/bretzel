"""RÉFÉRENCE — L'arbre du framework, construit tout seul.

Cette page n'écrit RIEN. Elle appelle ``describe_package("bretzel")`` et
rend récursivement ce qui revient : 117 dossiers, 303 modules et 608
symboles publics, chacun avec la phrase que son auteur a écrite.

⚠️ **Elle s'arrêtait aux dossiers, et elle paraissait vide** — parce que
73 de leurs 117 docstrings sont des talons générés (« icon_button
component. »). Le contenu était un cran plus bas : 97 % des symboles
publics ont une vraie première ligne. C'est ce cran-là qu'on affiche
depuis le 2026-09-02.

Pourquoi elle existe
---------------------
La question « qu'est-ce que Bretzel sait faire, sans lire tout le
code ? » n'avait pas de réponse d'un seul tenant. Il y en avait trois,
séparées, et il fallait savoir laquelle demander :

======================  =========  ===============================
l'arbre                 117 lignes  ce qui EXISTE
les surfaces classées   258 lignes  à QUOI SERT chaque symbole
le détail ``ui.*``      2 827 lignes  params, slots, events
======================  =========  ===============================

3 202 lignes en tout — illisibles d'un bloc, navigables en arbre. C'est
donc l'arbre qui sert d'ENTRÉE, et le détail vient à la demande.

⚠️ **Elle se construit à chaque rendu, donc elle ne peut pas se
périmer.** Un dossier ajouté demain y apparaît sans que personne ne
touche ce fichier — c'est exactement ce qui manquait aux listes écrites
à la main de ce dépôt, et ce qui a fait supprimer le skill
``bretzel-api`` le 2026-08-01.

Le seul invariant à garder est qu'un dossier ait une docstring, et
``test_every_package_describes_itself`` s'en charge.

⚠️ Ce que la page NE montre pas : d'un symbole, elle donne le nom et la
première ligne, **pas ses paramètres, ses slots ni ses events**. Le
catalogue ``ui.*`` a sa page (``/components``), et ``bretzel describe
<nom>`` rend la fiche complète en ligne de commande. Tout mettre ici
ferait 3 202 lignes que personne ne lirait.
"""

from __future__ import annotations

from bretzel import page, ui
from bretzel.state import ClientState, field
from bretzel.introspect import (
    ModuleInfo,
    PackageNode,
    SymbolLine,
    describe_package,
    module_names,
    package_names,
    walk,
)

from examples.docs.features.shell import shell
from examples.docs.lib.blocks import plain

PATH = "/tree"


class Selection(ClientState):
    """Le paquet sélectionné — CÔTÉ CLIENT, et c'est le point.

    Les 117 panneaux sont rendus d'un coup et `visible=` en masque 116 :
    la sélection est donc INSTANTANÉE — aucun aller-retour, aucune
    latence, aucune zone à rafraîchir. L'alternative (un `@refreshable`
    sur `on_change`) coûterait un POST par clic pour afficher du texte
    que le serveur avait déjà sous la main au premier rendu.

    ⚠️ **Ce que ça coûte, mesuré, et c'est plus que ce qui était écrit
    ici.** La première version de cette docstring disait « 25 Ko de
    texte » — c'est la taille des docstrings, pas celle de la page. La
    page fait **599 Ko** (2026-09-02), parce que le balisage pèse dix
    fois son texte. C'est assumé pour une page de référence qu'on ouvre
    en dev, et ça ne le serait pas dans une app.
    """

    picked: str = field(default="bretzel")

#: Les paquets qui ont EN PLUS un classement par besoin. On les signale
#: dans l'arbre : ce sont les seuls où `describe` rend une surface
#: groupée plutôt qu'un simple rangement.
_CLASSES = frozenset(module_names())


def noeud(n: PackageNode) -> None:
    """Un paquet et sa descendance — RÉCURSIF, comme l'arbre lu.

    ``ui.tree_node`` est un conteneur : un ``with`` de nœuds imbriqués
    en fait une branche. On lui donne donc exactement la forme du
    ``PackageNode``, sans aplatir.
    """
    # Le libellé porte la phrase du dossier — c'est CE qu'on vient lire,
    # et le mettre en infobulle le rendrait invisible au tactile (le
    # survol n'existe pas au doigt).
    with ui.tree_node(value=n.name, label=libelle(n), icon="folder"):
        for enfant in n.children:
            noeud(enfant)


def panneau(n: PackageNode, selection: Selection) -> None:
    """La fiche d'UN paquet, cachée jusqu'à ce qu'on le choisisse.

    Les 117 sont rendues d'un coup et `visible=` en masque 116. C'est
    ce qui rend la sélection instantanée — cf. `Selection`.
    """
    with ui.vstack(gap="sm", visible=selection.picked == n.name):
        ui.text(n.name, weight="semibold", size="sm", color="primary")
        # Le résumé EST la première ligne de la docstring : l'afficher
        # en plus la répéterait mot pour mot sur les dossiers dont la
        # docstring tient en une ligne — c'est-à-dire la plupart.
        if n.summary and n.summary != n.doc.strip():
            ui.text(plain(n.summary), weight="medium")
        # La docstring ENTIÈRE, débalisée. `ui.text` préserve les sauts
        # de ligne du texte source via `whitespace-pre-line`, sinon les
        # paragraphes d'une docstring se recollent en un seul bloc.
        ui.text(plain(n.doc) or "(ce dossier n'a pas de docstring)",
                size="sm", classes="whitespace-pre-line")
        if n.modules:
            ui.divider()
            publics = sum(len(m.symbols) for m in n.modules)
            ui.text(f"{len(n.modules)} module(s), {publics} symbole(s) public(s)",
                    weight="semibold", size="xs", color="muted")
            for mod in n.modules:
                module(mod)


#: La largeur de la colonne des noms. 22 couvre la grande majorité des
#: symboles ; au-delà, la ligne pousse son résumé d'un cran plutôt que
#: d'être tronquée — un nom coupé serait ingrepable.
_COLONNE = 22

# ⚠️ Un RETRAIT SUSPENDU a été essayé ici (``indent-[-23ch]`` +
# ``ps-[calc(...+23ch)]``) pour que les résumés longs reviennent sous la
# colonne des résumés. **Ça ne marche pas, et c'est structurel** :
# ``text-indent`` s'applique une fois par BLOC, pas par ligne — sous
# ``pre-wrap``, tout le texte est un seul bloc dont seule la première
# ligne est décalée. Le rendu obtenu était pire que le défaut : la
# colonne des noms cessait d'être alignée. Vu sur capture, invisible à
# la lecture du CSS.


def module(mod: ModuleInfo) -> None:
    """Un module, sa phrase, et CE QU'IL EXPOSE.

    ⚠️ C'est ce dernier cran qui porte le contenu réel. Mesuré le
    2026-09-02 : **73 des 117 docstrings de dossier sont des talons**
    (« icon_button component. »), pendant que 592 des 608 symboles
    publics — 97 % — ont une vraie première ligne. Le panneau paraissait
    maigre parce qu'il s'arrêtait un cran trop haut, pas parce que le
    dépôt était mal documenté.

    Pourquoi UN seul nœud de texte pour toute la liste
    --------------------------------------------------
    Parce que le balisage coûte dix fois le texte. Mesuré sur cette page,
    les trois variantes rendues en entier :

    ==========================================  ========
    un ``hstack`` + deux ``text`` par symbole    724 Ko
    un ``text`` par module (celle-ci)            599 Ko
    sans les symboles (l'état d'avant)           497 Ko
    ==========================================  ========

    Les 608 symboles pèsent donc **102 Ko en un nœud par module contre
    227 Ko en trois nœuds par symbole**, pour exactement la même
    information. Ce qu'on perd est la couleur propre au nom ; ce qu'on
    garde à la place est l'alignement en colonne, qui se lit mieux sur
    une liste de 39 lignes (``_wiring``, le record).

    ⚠️ ``whitespace-pre-wrap`` et **pas** ``pre-line`` : le second
    COLLAPSE les suites d'espaces, donc la colonne alignée se refermerait
    en un seul espace. ``pre`` la garderait mais ne renverrait pas à la
    ligne, et un résumé long déborderait du panneau.
    """
    with ui.vstack(gap="none"):
        with ui.hstack(gap="xs", align="baseline", wrap=True):
            ui.text(f"{mod.name}.py", size="xs", weight="medium")
            if mod.summary:
                ui.text(plain(mod.summary), size="xs", color="muted")
        # Le trait vertical rattache les symboles à LEUR module : sans
        # lui, une liste de 39 lignes se lit comme si elle appartenait au
        # dossier plutôt qu'au fichier.
        if mod.symbols:
            ui.text(
                "\n".join(ligne(s) for s in mod.symbols),
                size="xs", color="muted",
                classes="ms-2 ps-2 border-s-(length:--bz-stroke) "
                        "border-text/10 font-mono whitespace-pre-wrap",
            )




def ligne(sym: SymbolLine) -> str:
    """``nom    première ligne`` — ou le genre, faute de docstring.

    Les 16 symboles publics sans docstring (sur 608) affichent leur
    genre : c'est peu, mais une ligne vide ferait croire à un bug de
    lecture plutôt qu'à une docstring manquante.
    """
    resume = plain(sym.summary) or f"({sym.kind})"
    return f"{sym.name.ljust(_COLONNE)} {resume}"


def libelle(n: PackageNode) -> ui.Fragment:
    """Le nom, et rien d'autre — le panneau de droite raconte.

    ⚠️ La première version mettait le résumé ICI, à côté du nom. Dans
    une colonne au tiers de la page, il se faisait COUPER en plein mot
    (« Layer 5 — the user-facing ui namespa… ») — vu sur capture, pas
    dans le code, où la ligne paraissait très bien.

    Le résumé n'est pas perdu : il est en tête du panneau, avec la
    docstring entière. Un arbre sert à repérer, pas à lire.
    """
    with ui.fragment() as frag:
        with ui.hstack(gap="xs", align="center"):
            ui.text(n.name.split(".")[-1], weight="semibold", size="sm")
            if n.name in _CLASSES:
                ui.badge("classé", color="primary", size="xs")
    return frag


@page(PATH, layout=shell, title="L'arbre du framework")
def tree_page() -> None:
    racine = describe_package("bretzel")
    total = len(package_names())

    # ⚠️ ``2xl`` et non le ``lg`` des 18 autres chapitres, et c'est
    # DÉLIBÉRÉ : ``lg`` (``max-w-5xl``, 64 rem) est la mesure de lecture
    # de la maison, faite pour de la prose. Cette page n'est pas de la
    # prose, c'est un explorateur à deux volets — et mesuré sur une
    # fenêtre de 1 909 px, le clamp ``lg`` laissait **626 px inutilisés,
    # soit 38 % de la largeur disponible** : l'arbre était comprimé et
    # les résumés se repliaient sans raison.
    #
    # ``2xl`` (96 rem) remplit un écran de bureau sans lâcher la bride :
    # sur un ultra-large, un panneau de texte de 3 000 px serait
    # illisible. Vérifié compilé en PROD, pas seulement en dev :
    # ``.max-w-screen-2xl{max-width:var(--breakpoint-2xl)}`` avec
    # ``--breakpoint-2xl:96rem`` — la variable est bien définie.
    with ui.container(width="2xl"):
        with ui.vstack(gap="lg"):
            ui.heading("L'arbre du framework", level=1, size="3xl")
            ui.text(
                f"{total} paquets, lus en direct. Cette page n'écrit "
                f"aucun nom et aucune description : elle appelle "
                f"`describe_package('bretzel')` et rend ce qui revient. "
                f"Un dossier ajouté demain apparaît ici sans que personne "
                f"ne touche à ce fichier.",
                color="muted",
            )

            ui.alert(
                "Les dossiers marqués « classé » ont EN PLUS une table "
                "qui groupe leurs symboles par besoin — c'est ce que rend "
                "`bretzel describe bretzel.state`. Les autres n'ont que "
                "leur rangement, ce qui est déjà la réponse à « qu'est-ce "
                "qu'il y a là-dedans ».",
                color="info", title="Deux niveaux, et ils se complètent",
            )

            selection = Selection()
            # Deux colonnes : l'arbre navigue, le panneau raconte. Sous
            # `md` elles s'empilent — un arbre à 117 entrées et un
            # panneau de texte côte à côte sur un téléphone ne donnerait
            # ni l'un ni l'autre.
            # `cols` prend un DICT responsive — c'est la forme du
            # framework, pas un `md_cols=` inventé (que le socle
            # refuse, et il a raison : un kwarg mort ne lève pas,
            # ne s'affiche pas, et ne se voit pas en revue).
            with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                with ui.card():
                    with ui.vstack(gap="sm"):
                        ui.heading("Le rangement", level=2, size="lg")
                        with ui.tree(value=selection.picked,
                                     expanded=[racine.name], size="sm"):
                            noeud(racine)

                # ⚠️ La carte porte elle-même `md:col-span-2`. Elle était
                # enveloppée dans un `ui.container`, qui est un gabarit de
                # PAGE (`mx-auto max-w-5xl px-6 py-8`) et pas une cellule
                # de grille : son `py-8` décalait la carte de droite de
                # 32 px vers le bas, et son `px-6` la rétrécissait de 48.
                # Les deux cartes ne s'alignaient donc pas — visible à
                # l'œil, invisible à la lecture du code.
                with ui.card(classes="md:col-span-2"):
                    with ui.vstack(gap="sm"):
                        ui.heading("Ce que le dossier dit de lui-même",
                                   level=2, size="lg")
                        for n in walk(racine):
                            panneau(n, selection)

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Ce que cette page ne montre pas", level=2)
                    ui.text(
                        "D'un symbole, l'arbre donne le nom et la "
                        "première ligne. Pas ses paramètres, pas ses "
                        "slots, pas ses events : il y en a 2 827 lignes pour "
                        "les 111 composants seuls, et les afficher ici "
                        "ferait une page que personne ne lirait. Le "
                        "catalogue a sa propre page, et "
                        "`bretzel describe <nom>` rend la fiche "
                        "complète en ligne de commande.",
                        color="muted", size="sm",
                    )
                    with ui.hstack(gap="sm", wrap=True):
                        ui.link("Catalogue ui.*", href="/components")
                        ui.link("Cheat-sheet", href="/cheatsheet")
                        ui.link("Capacités navigateur", href="/browser")
