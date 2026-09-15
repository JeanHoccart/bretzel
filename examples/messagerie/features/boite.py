"""messagerie/boite — les trois panneaux, la barre d'outils, la rédaction.

Trois régions à défilement indépendant, dans un document qui ne défile
pas : les dossiers, la liste du dossier ouvert, le message lu. Chacune
est une zone ``@refreshable`` — ce qu'on regarde change, ou la boîte
change, et seule la région concernée se re-rend.

**Le glisser-déposer va de la liste vers un dossier.** Chaque dossier de
la colonne de gauche est une ``ui.dropzone`` qui déclare
``accepts=["message"]`` ; la liste est la zone source. C'est la zone qui
REÇOIT qui décide — le socle appelle son ``on_move`` — donc chaque
dossier câble le même handler et le ``to_zone`` porte la destination.

``accepts=`` omis ne voudrait PAS dire « n'importe quoi » : une zone qui
ne déclare rien ne reçoit que ses propres items. Recevoir d'ailleurs est
un opt-in, et c'est ce qui empêche la liste d'attraper une carte venue
d'une zone sans rapport.

⚠️ **Aucune commande n'apparaît au survol.** C'est ce que font Gmail et
consorts pour les actions de ligne, et c'est inutilisable ici : le
navigateur de l'auteur rapporte ``hover``, ``any-hover`` et
``pointer:fine`` tous les trois à ``false``. Une commande qu'on ne peut
atteindre qu'en survolant n'existe pas pour lui. Les actions vivent donc
dans la barre d'outils du message ouvert, visibles en permanence.
"""

from __future__ import annotations

from functools import partial

from bretzel import page, refreshable, ui
from examples.messagerie.features.donnees import (
    DOSSIERS,
    Boite,
    apercu,
    date_courte,
    fil_ouvert,
    fils_du_dossier,
    non_lus,
    texte_du_fil,
)
from examples.messagerie.features.logic import (
    ZONE_DOSSIER,
    ZONE_LISTE,
    basculer_lu,
    deplacer,
    envoyer,
    fermer,
    fermer_redaction,
    ouvrir,
    ranger,
    redimensionner,
    rediger,
    repondre,
)
from examples.messagerie.features.shell import shell
from examples.messagerie.features.state import (
    Filtre,
    Panneau,
    Redaction,
    Vue,
)

#: Le groupe de glissement. Un seul dans cette app, mais le nommer est ce
#: qui autorise les dossiers à recevoir : ils déclarent ``accepts=[GROUPE]``.
GROUPE = "message"

#: La bordure qui sépare deux panneaux. Écrite ici plutôt qu'au thème :
#: c'est une décision de mise en page de CETTE app, pas du composant.
SEPARATION = "border-r border-text/10"

#: ⚠️ **``grow=`` sur un ``ui.pane`` dimensionne ses ENFANTS**, pas le
#: panneau : le thème émet ``*:grow *:basis-64``. Et ``flex-none`` est
#: obligatoire — le thème pose ``flex-1``, donc un ``w-56`` seul est
#: écrasé (mesuré : 447 px au lieu de 240).
COLONNE_DOSSIERS = "flex-none w-56 " + SEPARATION
COLONNE_LISTE = "flex-none w-[26rem] " + SEPARATION


@refreshable(deps=[Boite, Vue])
def colonne_dossiers() -> None:
    """Les quatre dossiers. Chacun est aussi une cible de dépôt."""
    vue = Vue()
    with ui.pane(padding="sm", gap="xs", classes=COLONNE_DOSSIERS):
        for cle, libelle, icone in DOSSIERS:
            actif = vue.dossier == cle
            attente = non_lus(cle)
            with ui.dropzone(
                name=f"{ZONE_DOSSIER}{cle}",
                accepts=[GROUPE],
                on_move=deplacer,
                color="primary",
                classes="rounded-full",
            ):
                # Un ``href=``, pas un handler — et c'est la mécanique de
                # cet exemple qui le permet. Le dossier VIT dans l'adresse,
                # donc y aller est une navigation ordinaire : le lien se
                # partage, le clic du milieu ouvre un onglet, et les
                # flèches du navigateur marchent sans qu'on écrive rien.
                #
                # Le retour de bonus : l'absence de ``msg`` dans l'adresse
                # remet ``Vue().ouvert`` à son défaut, donc changer de
                # dossier referme le message tout seul. Pas de handler qui
                # « pense à » remettre l'état à zéro, pas d'oubli possible.
                with ui.card(
                    href=f"/?dossier={cle}",
                    padding="none",
                    classes=(
                        "border-0 shadow-none hover:shadow-none hover:top-0 "
                        "rounded-full px-4 py-2 "
                        + (
                            "bg-primary/15 font-semibold"
                            if actif
                            else "bg-transparent hover:bg-text/5"
                        )
                    ),
                ):
                    with ui.hstack(align="center", gap="sm"):
                        ui.icon(icone, size="sm")
                        ui.text(libelle, size="sm", classes="flex-1")
                        if attente:
                            ui.text(str(attente), size="xs", weight="bold")


def aucun_resultat() -> None:
    """L'état vide de la RECHERCHE — rendu côté client par filter_each."""
    ui.empty_state(
        "Aucun résultat",
        description="Aucun message ne contient ce que tu cherches.",
        icon="search-x",
        size="sm",
    )


@refreshable(deps=[Boite, Vue])
def colonne_liste() -> None:
    """Les FILS du dossier ouvert — la SOURCE des glissements.

    Une messagerie ne liste pas des messages, elle liste des ÉCHANGES :
    dix allers-retours avec la même personne font UNE ligne. Le
    regroupement se fait sur le sujet normalisé (``donnees.fil_de``), et
    c'est le fil entier qu'on ouvre, qu'on range et qu'on glisse.

    ``ui.filter_each`` et non un filtre écrit à la main : le framework
    fournit la primitive, et elle filtre **dans le navigateur**
    (``bz-show`` par ligne, ``ClientBinding`` en entrée). Taper ne coûte
    donc aucune requête, et l'état vide de la recherche est lui aussi
    client.

    ⚠️ **Le compromis se choisit, il ne se subit pas.** Le filtrage
    client exige que toutes les lignes soient dans le DOM. À une
    quarantaine de messages, c'est le bon choix — instantané, zéro
    aller-retour. À cinq mille, ce serait une page qui pèse : la réponse
    est alors de filtrer et paginer au serveur, ce que ``ui.datatable``
    fait déjà.

    ``ui.draggable`` explicite au lieu de ``ui.drag_each`` : les deux
    itérateurs ne se composent pas — chacun veut être la boucle. Le
    composant, lui, s'imbrique dans l'enveloppe que ``filter_each`` pose,
    et le moteur de glissement l'accepte : sa doc dit noir sur blanc
    qu'un item n'est pas forcément enfant direct de sa zone.
    """
    vue = Vue()
    fils = fils_du_dossier(vue.dossier)
    with ui.pane(padding="none", gap="none", classes=COLONNE_LISTE):
        if not fils:
            ui.empty_state(
                "Ce dossier est vide",
                description="Glisse une conversation depuis un autre dossier.",
                icon="inbox",
                size="sm",
            )
            return
        with ui.dropzone(name=ZONE_LISTE, classes="flex flex-col"):
            for fil in ui.filter_each(
                fils,
                query=Filtre().q,
                text=texte_du_fil,
                key=lambda f: f["fil"],
                empty=aucun_resultat,
            ):
                with ui.draggable(key=fil["fil"], group=GROUPE):
                    ligne_fil(fil, ouvert=vue.ouvert == fil["fil"])


def resume_participants(fil: dict) -> str:
    """Qui parle dans ce fil, en une ligne courte.

    Un seul : son nom. Deux : « A, B ». Plus : « A, … B », comme le font
    les clients mail — la liste complète déborderait toujours.
    """
    noms = fil["participants"]
    if len(noms) <= 2:
        return ", ".join(noms)
    return noms[0] + ", … " + noms[-1]


def ligne_fil(fil: dict, *, ouvert: bool) -> None:
    """Une conversation, sur trois étages : qui, quoi, et le dernier mot.

    ⚠️ **Pas la ligne UNIQUE de Gmail**, et c'est une conséquence du
    modèle à trois panneaux. Gmail tient sur une ligne parce qu'il n'a
    PAS de panneau de lecture : sa liste occupe toute la largeur. Ici la
    colonne fait 26 rem, et la même forme rendait « Autorisa… — Vo… » —
    mesuré. Les clients à trois panneaux (Outlook, Apple Mail,
    Thunderbird) empilent tous sur trois étages, pour cette raison.

    ⚠️ ``tag="button"`` : sans lui, ``ui.card(on_click=…)`` rend un
    ``<div hx-post>`` sans ``tabindex`` ni ``role`` — cliquable à la
    souris, **injoignable au clavier**.
    """
    dernier = fil["dernier"]
    non_lu = fil["non_lus"] > 0
    combien = len(fil["messages"])
    with ui.card(
        tag="button",
        on_click=partial(ouvrir, fil["fil"]),
        padding="none",
        classes=(
            "rounded-none border-0 border-b border-text/5 shadow-none "
            "hover:shadow-none hover:top-0 px-3 py-2 cursor-pointer "
            "border-l-2 "
            + (
                "bg-primary/10 border-l-primary"
                if ouvert
                else "bg-transparent border-l-transparent hover:bg-text/5"
            )
        ),
    ):
        with ui.hstack(align="start", gap="sm", classes="w-full text-left"):
            # La gouttière de la pastille est TOUJOURS là, occupée ou non :
            # sans elle, un fil lu et un non lu ne s'alignent pas et l'œil
            # lit un décalage plutôt qu'un état.
            with ui.flex(justify="center", classes="w-2 shrink-0 pt-1.5"):
                if non_lu:
                    # Un rond PLEIN. Les icônes lucide sont tracées au
                    # trait : ``ui.icon("circle")`` rend un anneau, qui se
                    # lit mal à 8 px.
                    ui.flex(classes="w-2 h-2 rounded-full bg-primary")

            # ``min-w-0`` est load-bearing : sans lui, un enfant
            # ``truncate`` refuse de rétrécir sous la largeur de son
            # contenu et déborde la colonne.
            with ui.vstack(gap="none", classes="min-w-0 flex-1"):
                with ui.hstack(justify="between", align="baseline", gap="sm"):
                    with ui.hstack(align="baseline", gap="xs",
                                   classes="min-w-0"):
                        ui.text(
                            resume_participants(fil),
                            size="sm",
                            weight="bold" if non_lu else "normal",
                            truncate=True,
                        )
                        # Le compte ne s'affiche qu'à partir de DEUX : un
                        # « 1 » sur une conversation d'un seul message
                        # serait du bruit sur la majorité des lignes.
                        if combien > 1:
                            ui.text(str(combien), size="xs", color="muted",
                                    classes="shrink-0")
                    ui.text(date_courte(dernier), size="xs", color="muted",
                            classes="shrink-0")
                with ui.hstack(align="center", gap="xs"):
                    ui.text(
                        fil["sujet"],
                        size="sm",
                        weight="semibold" if non_lu else "normal",
                        truncate=True,
                        classes="flex-1 min-w-0",
                    )
                    if any(m["pieces"] for m in fil["messages"]):
                        ui.icon("paperclip", size="xs", color="muted",
                                classes="shrink-0")
                ui.text(apercu(dernier, 110), size="xs", color="muted",
                        truncate=True)


@refreshable(deps=[Boite, Vue])
def panneau_fil() -> None:
    """Le fil ouvert : tous ses messages, du plus RÉCENT au plus ancien.

    ⚠️ L'ordre est l'inverse de celui de la conversation, et c'est
    délibéré : ce qu'on vient de recevoir est ce qu'on veut lire, et
    l'ordre chronologique l'enterre au bas d'un panneau qu'il faut
    dérouler. C'est le choix d'Outlook et d'Apple Mail. Gmail garde
    l'ordre du récit mais REPLIE les anciens — l'autre réponse au même
    problème, qui demande un état de pliage par message.
    """
    vue = Vue()
    fil = fil_ouvert(vue.dossier, vue.ouvert)
    with ui.pane(padding="none", gap="none"):
        if fil is None:
            with ui.flex(justify="center", align="center",
                         classes="h-full p-8"):
                ui.empty_state(
                    "Aucune conversation ouverte",
                    description=(
                        "Choisis une conversation à gauche. Son adresse "
                        "s'écrit dans la barre du navigateur : le lien se "
                        "partage, et la flèche retour ramène ici."
                    ),
                    icon="mail-open",
                )
            return

        barre_outils(fil)

        with ui.vstack(gap="none", classes="px-6 py-5"):
            with ui.hstack(justify="between", align="start", gap="md"):
                with ui.vstack(gap="none", classes="min-w-0 flex-1"):
                    ui.heading(fil["sujet"], level=2, size="lg")
                    if len(fil["messages"]) > 1:
                        ui.text(str(len(fil["messages"])) + " messages",
                                size="xs", color="muted", classes="mt-1")
                # ⚠️ « Répondre » EN HAUT, parce que le fil est affiché
                # du plus récent au plus ancien : le laisser en pied
                # obligeait à dérouler toute la conversation pour
                # répondre au message qu'on vient de lire, en haut.
                # Le bouton suit le message auquel il répond.
                ui.button("Répondre", icon_left="reply", variant="outline",
                          size="sm", on_click=repondre, classes="shrink-0")

            for rang, courant in enumerate(reversed(fil["messages"])):
                if rang:
                    ui.divider(classes="my-4")
                bloc_message(courant)


def bloc_message(courant: dict) -> None:
    """Un message DANS un fil : en-tête compact, puis le corps."""
    with ui.vstack(gap="sm", classes="pt-4"):
        with ui.hstack(align="center", gap="md", classes="min-w-0"):
            ui.avatar(name=courant["de"], size="sm", classes="shrink-0")
            with ui.vstack(gap="none", classes="min-w-0 flex-1"):
                ui.text(courant["de"], size="sm", weight="semibold",
                        truncate=True)
                ui.text(courant["adresse"], size="xs", color="muted",
                        truncate=True)
            ui.text(courant["date"], size="xs", color="muted",
                    classes="shrink-0")

        ui.markdown(courant["corps"])

        if courant["pieces"]:
            with ui.hstack(gap="sm", wrap=True, classes="pt-1"):
                for nom in courant["pieces"]:
                    with ui.card(padding="sm", color="surface"):
                        with ui.hstack(align="center", gap="sm"):
                            ui.icon("file-text", size="sm", color="muted")
                            ui.text(nom, size="sm")


def barre_outils(fil: dict) -> None:
    """Les actions du FIL affiché. Toujours visibles, jamais au survol."""
    dossier = Vue().dossier
    a_des_entrants = any(m["entrant"] for m in fil["messages"])
    with ui.hstack(
        justify="between", align="center", gap="sm",
        classes="px-4 py-2 border-b border-text/10 shrink-0",
    ):
        with ui.hstack(align="center", gap="xs"):
            ui.icon_button("arrow-left", variant="ghost", size="sm",
                           on_click=fermer, tooltip="Retour à la liste")
            ui.icon_button(
                "archive", variant="ghost", size="sm",
                on_click=partial(ranger, "archives"),
                disabled=dossier == "archives",
                tooltip="Archiver la conversation",
            )
            ui.icon_button(
                "trash-2", variant="ghost", size="sm",
                on_click=partial(ranger, "corbeille"),
                disabled=dossier == "corbeille",
                tooltip="Mettre la conversation à la corbeille",
            )
            ui.icon_button(
                "inbox", variant="ghost", size="sm",
                on_click=partial(ranger, "recus"),
                disabled=dossier == "recus",
                tooltip="Remettre dans les reçus",
            )
            # ⚠️ Le bouton n'existe QUE si le fil contient du courrier
            # reçu. « Marquer non lu » ce qu'on a écrit soi-même n'a pas
            # de sens — et le handler le refuse aussi, pour que la règle
            # ne vive pas seulement dans le rendu.
            if a_des_entrants:
                ui.icon_button(
                    "mail" if fil["non_lus"] == 0 else "mail-open",
                    variant="ghost", size="sm", on_click=basculer_lu,
                    tooltip="Marquer non lu" if fil["non_lus"] == 0
                    else "Marquer comme lu",
                )
        ui.icon_button("x", variant="ghost", size="sm", on_click=fermer,
                       tooltip="Fermer")


#: Les trois tailles du panneau de rédaction, et les classes de chacune.
#: Une table fermée plutôt que des classes assemblées : une classe
#: Tailwind construite par f-string n'existe qu'en dev (le compilateur de
#: prod ne la voit pas dans la source).
TAILLES_PANNEAU: dict[str, str] = {
    "normal": "bottom-0 right-6 w-[30rem] max-w-[calc(100vw-3rem)]",
    "reduit": "bottom-0 right-6 w-80",
    "plein": "bottom-0 right-0 left-0 mx-auto w-[min(64rem,calc(100vw-3rem))] "
             "top-16",
}


@refreshable(deps=[Panneau])
def panneau_redaction() -> None:
    """Le panneau de rédaction, ancré en bas à droite, en trois tailles.

    **Pas un ``ui.dialog``.** Une modale prend tout l'écran et interdit de
    relire la boîte pendant qu'on écrit — c'est justement ce qu'on veut
    faire en répondant. Tous les clients mail ancrent la rédaction dans
    un coin, sans bloquer le reste.

    **Une zone rafraîchissable, et pas un ``visible=`` client.** La
    taille change les CLASSES du conteneur, et une classe ne se lie pas
    côté client comme une valeur se lie. Le texte du brouillon, lui,
    reste dans un ``ClientState`` : il survit donc au re-rendu, ce qui
    est exactement ce qu'on veut d'un brouillon.
    """
    panneau = Panneau()
    if not panneau.ouvert:
        return

    brouillon = Redaction()
    reduit = panneau.taille == "reduit"
    plein = panneau.taille == "plein"

    with ui.vstack(
        gap="none",
        classes=(
            "fixed z-40 rounded-t-xl border border-text/10 bg-interface "
            "shadow-2xl " + TAILLES_PANNEAU[panneau.taille]
        ),
    ):
        with ui.hstack(
            justify="between", align="center",
            classes=(
                "px-4 py-2.5 rounded-t-xl bg-text/5 border-b border-text/10"
            ),
        ):
            # Le titre suit le sujet pendant la frappe, sans aller-retour :
            # ``brouillon.sujet`` est un ``ClientState``, donc la
            # comparaison produit une expression JS et non un booléen
            # Python. Deux textes gatés l'un par l'inverse de l'autre —
            # le même idiome que les bulles de ``examples/chat``.
            ui.text("Nouveau message", size="sm", weight="semibold",
                    visible=brouillon.sujet == "")
            ui.text(brouillon.sujet, size="sm", weight="semibold",
                    truncate=True, classes="min-w-0",
                    visible=brouillon.sujet != "")
            with ui.hstack(align="center", gap="none", classes="shrink-0"):
                ui.icon_button(
                    "chevron-up" if reduit else "minus",
                    variant="ghost", size="sm",
                    on_click=partial(redimensionner,
                                     "normal" if reduit else "reduit"),
                    tooltip="Agrandir" if reduit else "Réduire",
                )
                ui.icon_button(
                    "minimize-2" if plein else "maximize-2",
                    variant="ghost", size="sm",
                    on_click=partial(redimensionner,
                                     "normal" if plein else "plein"),
                    tooltip="Quitter le plein écran" if plein
                    else "Plein écran",
                )
                ui.icon_button("x", variant="ghost", size="sm",
                               on_click=fermer_redaction, tooltip="Fermer")

        # Réduit : la barre de titre SEULE. Le corps n'est pas caché, il
        # n'est pas rendu — un champ masqué resterait dans l'ordre de
        # tabulation, et c'est le défaut d'accessibilité que cette app a
        # déjà rencontré avec le dialogue fermé.
        if reduit:
            return

        with ui.vstack(gap="sm", classes="px-4 py-3 flex-1 min-h-0"):
            if panneau.erreur:
                ui.alert(panneau.erreur, color="error")
            # ``type="email"`` donne le contrôle NATIF du navigateur —
            # un confort pendant la frappe. Il ne remplace pas la
            # validation du handler : une action peut arriver sans passer
            # par le formulaire.
            ui.input(value=brouillon.a, placeholder="À",
                     type="email", icon_left="user", size="sm")
            ui.input(value=brouillon.sujet, placeholder="Objet", size="sm")
            ui.textarea(value=brouillon.corps, placeholder="Ton message…",
                        rows=18 if plein else 7, size="sm",
                        classes="flex-1 min-h-0" if plein else "")
            ui.file_upload(label="Pièces jointes", multiple=True,
                           max_files=3, size="sm")
            with ui.hstack(justify="between", align="center", gap="sm"):
                ui.button("Envoyer", color="primary", size="sm",
                          icon_left="send", on_click=envoyer)
                ui.icon_button("trash-2", variant="ghost", size="sm",
                               on_click=fermer_redaction,
                               tooltip="Abandonner le brouillon")


@page("/", layout=shell, title="Messagerie")
def boite_page() -> None:
    colonne_dossiers()
    colonne_liste()
    panneau_fil()
    panneau_redaction()

    ui.button(
        "Nouveau message",
        color="primary",
        icon_left="pen-line",
        on_click=rediger,
        classes="fixed bottom-6 left-6 z-30 shadow-lg rounded-full",
    )
