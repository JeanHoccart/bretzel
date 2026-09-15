"""RÉFÉRENCE — Ce que Bretzel sait FAIRE.

La seule page qui réponde à « qu'est-ce que ce framework sait faire »
sans qu'on lise le code, et la seule dont la source soit écrite à la
main. Ce n'est pas un oubli : **une capacité ne tient pas dans un
dossier**, donc aucun lecteur d'arbre ne peut la déduire.

Servir un fichier, par exemple, c'est ``render/decorators/download.py``
+ ``server/routing/downloads.py`` + ``server/routing/_csv.py`` + le
``download=`` de ``components/actions/link`` + l'export de
``components/data/datatable``. Cinq dossiers, cinq docstrings, aucune
qui dise « Bretzel sait servir un fichier ».

Comment elle ne peut pas mentir malgré ça
------------------------------------------
La page ne fait que rendre :data:`~bretzel.introspect.CAPABILITIES`, et
``test_a_capability_is_anchored`` tient la source : chaque symbole
d'entrée est RÉSOLU, chaque extrait doit parser ET employer les symboles
qu'il annonce, et aucun symbole ne peut être revendiqué par deux
capacités — c'est le détecteur de doublon.

⚠️ Ce qu'aucune gate ne garde : que la phrase soit VRAIE. Un ``does:``
qui promet plus que le code fait passerait au vert. C'est pourquoi
chaque capacité porte un ``caveat:`` — la limite est souvent
l'information la plus chère, et c'est elle qui dit que la PWA n'a pas
encore de service worker.
"""

from __future__ import annotations

from bretzel import page, ui
from bretzel.introspect import CAPABILITIES, Capability
from bretzel.state import ClientState, field

from examples.docs.features.shell import shell

PATH = "/capabilities"


class Filtre(ClientState):
    """Le texte cherché — CÔTÉ CLIENT, et c'est le point.

    Les 19 capacités tiennent en quelques dizaines de kilo-octets. Les
    rendre toutes et n'en masquer que certaines coûte donc moins qu'un
    aller-retour, et le filtre répond à la frappe sans latence.

    La comparaison est faite par `ui.filter_each`, qui pose un `bz-show`
    sur chaque carte — on écrit du Python, il n'y a pas une ligne de
    JavaScript ici, et les cartes sont CACHÉES, pas retirées.
    """

    cherche: str = field(default="")


def matiere(cap: Capability) -> str:
    """Le texte sur lequel le filtre cherche.

    Le titre ET la phrase ET les symboles d'entrée : quelqu'un qui tape
    « csv » ne connaît pas forcément le mot ``download``, et c'est
    précisément la personne à qui cette page sert.
    """
    return f"{cap.name} {cap.does} {' '.join(cap.entry)} {cap.chapter}"


def carte(cap: Capability) -> None:
    """Une capacité : ce qu'elle permet, par où on entre, et sa limite.

    L'ordre compte et il est délibéré. Le titre dit l'ACTION à
    l'infinitif — « Servir un fichier », pas « Le décorateur
    download » — parce que c'est sous cette forme qu'on cherche quand on
    ne connaît pas encore le nom du symbole.
    """
    with ui.card():
        with ui.vstack(gap="sm"):
            ui.heading(cap.name, level=2, size="lg")
            ui.text(cap.does, color="muted", size="sm")

            with ui.hstack(gap="xs", wrap=True, align="center"):
                ui.text("On entre par", size="xs", color="muted")
                for chemin in cap.entry:
                    ui.badge(chemin, color="primary", variant="soft",
                             size="sm")

            # Le renvoi vers le chapitre — c'est LA règle rendue
            # visible : cette page liste, le chapitre enseigne. Une
            # capacité sans chapitre le dit en clair plutôt que de
            # laisser croire qu'il n'y a rien de plus à savoir.
            with ui.hstack(gap="xs", wrap=True, align="baseline"):
                if cap.chapter:
                    ui.text("Le chapitre qui l'enseigne :", size="xs",
                            color="muted")
                    ui.link(cap.chapter, href=cap.chapter)
                else:
                    ui.badge("pas encore de chapitre", color="warning",
                             variant="soft", size="sm")

            ui.code(cap.snippet, lang="python")

            if cap.caveat:
                ui.alert(cap.caveat, color="warning",
                         title="Ce qu'il faut savoir avant")


@page(PATH, layout=shell, title="Ce que Bretzel sait faire")
def capabilities_page() -> None:
    filtre = Filtre()

    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("Ce que Bretzel sait faire", level=1, size="3xl")
            ui.text(
                f"{len(CAPABILITIES)} capacités, chacune avec le symbole "
                "par lequel on y entre et le plus petit code qui la met "
                "en œuvre. C'est la réponse à « de quoi ce framework est "
                "capable » — celle que ni l'arbre des dossiers, ni le "
                "catalogue des composants ne peuvent donner.",
                color="muted", size="lg",
            )

            ui.alert(
                "Cette page donne une vue d’ensemble. Chaque capacité "
                "renvoie vers le chapitre qui l’explique, avec son point "
                "d’entrée dans l’API et ses limites actuelles.",
                color="success", title="Un index liste, un chapitre enseigne",
            )

            ui.alert(
                "Utilisez le filtre pour chercher un besoin (« csv », "
                "« temps réel », « thème ») même si vous ne connaissez pas "
                "encore le nom du composant correspondant.",
                color="info", title="Cherchez par besoin",
            )

            ui.input(
                value=filtre.cherche,
                placeholder="Filtrer — « csv », « sombre », « temps réel »…",
                clearable=True,
            )

            # `filter_each` fait le travail ENTIÈREMENT côté client : il
            # pose un `bz-show` sur chaque carte, comparé à ce qu'on
            # tape. Aucun aller-retour, aucun JS écrit à la main — et
            # surtout, aucun helper à inventer : la primitive existait,
            # il fallait la chercher avant d'écrire la comparaison à la
            # main (ce que j'avais commencé à faire, avec un
            # `.contains()` qui compare dans le mauvais sens).
            with ui.vstack(gap="md"):
                for cap in ui.filter_each(
                    CAPABILITIES,
                    query=filtre.cherche,
                    text=matiere,
                    key=lambda c: c.name,
                    empty=lambda: ui.text(
                        "Aucune capacité ne correspond à cette recherche.",
                        color="muted", size="sm",
                    ),
                ):
                    carte(cap)

            with ui.card(color="surface"):
                with ui.vstack(gap="sm"):
                    ui.heading("La même chose en ligne de commande",
                               level=2, size="lg")
                    ui.code(
                        "py -m bretzel.cli.main describe capabilities\n",
                        lang="bash",
                    )
                    with ui.hstack(gap="sm", wrap=True, align="baseline"):
                        ui.text("Pour le détail d'un symbole nommé "
                                "ci-dessus :", color="muted", size="sm")
                        ui.link("Catalogue ui.* →", href="/components")
                        ui.link("L'arbre du framework →", href="/tree")
