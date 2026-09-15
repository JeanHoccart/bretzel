"""messagerie/logic — les handlers. Ils mutent, l'affichage suit.

Aucun ne touche au DOM et aucun ne renvoie de HTML : ils écrivent dans un
état, et les zones ``@refreshable`` qui en dépendent se re-rendent. Deux
d'entre eux écrivent dans :class:`Vue`, donc **l'adresse change aussi** —
sans qu'une seule ligne ne le demande, parce que ``Vue`` déclare ses
champs adressables.

⚠️ **Une collection se RÉASSIGNE, elle ne se mute pas en place.**
``boite.messages[0]["lu"] = True`` écrit bien la valeur, mais ne change
pas l'identité de la liste : la détection de changement ne voit rien et
la zone ne se re-rend pas (`traps.md` § mutation de collection). D'où le
``remplacer`` ci-dessous, qui rebâtit la liste autour du message modifié.
"""

from __future__ import annotations

import re
from typing import Any

from bretzel.components import Move
from examples.messagerie.features.donnees import (
    CLES,
    Boite,
    fil_de,
    fil_ouvert,
    identifiant_libre,
)
from examples.messagerie.features.state import Panneau, Redaction, Vue

#: Le préfixe du ``name=`` des zones de dépôt de la colonne des dossiers.
#: Le suffixe est la clé du dossier, donc ``to_zone`` suffit à savoir où
#: le message a atterri.
ZONE_DOSSIER = "dossier-"

#: Le ``name=`` de la zone qui porte la liste. Elle est la SOURCE des
#: glissements, jamais leur destination — on ne dépose pas un message sur
#: la liste dont il vient déjà.
ZONE_LISTE = "liste"


def ouvrir(clef: str) -> None:
    """Afficher un FIL, et marquer lus tous ses messages entrants.

    C'est ce que fait un client mail : ouvrir une conversation la lit
    entière. Marquer un seul message laisserait le fil « en partie non
    lu », un état que rien n'affiche et que personne ne sait résoudre.
    """
    vue = Vue()
    if fil_ouvert(vue.dossier, clef) is None:
        return
    vue.ouvert = clef
    boite = Boite()
    boite.messages = [
        {**m, "lu": True} if fil_de(m) == clef and m["entrant"] else m
        for m in boite.messages
    ]


def fermer() -> None:
    """Refermer le fil affiché, sans changer de dossier."""
    Vue().ouvert = ""


#: Ce qui ressemble à une adresse : un arobase, du texte des deux côtés,
#: un point dans le domaine, et aucune espace. VOLONTAIREMENT permissif —
#: la grammaire complète (RFC 5322) accepte des formes que personne
#: n'écrit, et une expression qui prétend l'implémenter rejette surtout
#: des adresses valides. Le vrai contrôle d'une adresse, c'est d'y
#: envoyer un message.
ADRESSE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ── Les actions sur le message affiché ────────────────────────────────
#
# Toutes suivent la même forme : lire le message courant, refuser si
# rien n'est ouvert, muter, et laisser les zones se re-rendre.


def basculer_lu() -> None:
    """Marquer le fil affiché non lu, ou tout relire.

    ⚠️ N'agit que sur les messages ENTRANTS. « Marquer non lu » ce qu'on
    a écrit soi-même n'a pas de sens, et la barre d'outils n'offre le
    bouton que si le fil en contient — ce garde est là pour que la règle
    vive dans le domaine et pas seulement dans le rendu.
    """
    vue = Vue()
    fil = fil_ouvert(vue.dossier, vue.ouvert)
    if fil is None:
        return
    entrants = [m for m in fil["messages"] if m["entrant"]]
    if not entrants:
        return
    cible = fil["non_lus"] == 0  # tout lu → on repasse en non lu
    boite = Boite()
    boite.messages = [
        {**m, "lu": not cible} if fil_de(m) == vue.ouvert and m["entrant"]
        else m
        for m in boite.messages
    ]


def ranger(cible: str) -> None:
    """Déplacer TOUT le fil affiché vers ``cible``, et le refermer.

    Le fil est l'unité : archiver une conversation en laissant deux de
    ses messages dans les reçus la ferait réapparaître à la ligne
    suivante, et personne ne comprendrait pourquoi.
    """
    vue = Vue()
    fil = fil_ouvert(vue.dossier, vue.ouvert)
    if fil is None or cible not in CLES:
        return
    boite = Boite()
    boite.messages = [
        {**m, "dossier": cible} if fil_de(m) == vue.ouvert else m
        for m in boite.messages
    ]
    vue.ouvert = ""


def deplacer(mouvement: Move) -> None:
    """Ranger un message dans le dossier où on vient de le lâcher.

    C'est la zone qui REÇOIT qui décide : le socle appelle le ``on_move``
    de la zone d'arrivée, donc ``to_zone`` porte déjà la destination et
    ce handler n'a rien à deviner.

    Refuser, c'est ne rien faire. Le navigateur a déjà bougé la carte de
    façon optimiste ; un handler qui ne mute pas laisse le re-rendu
    serveur en désaccord avec le DOM, et le morph la remet en place. Il
    n'y a donc pas de ``reject()`` à appeler.
    """
    if not mouvement.to_zone.startswith(ZONE_DOSSIER):
        return
    cible = mouvement.to_zone[len(ZONE_DOSSIER) :]
    if cible not in CLES:
        return
    # ``item_key`` est la clé du FIL : c'est un fil qu'on glisse, donc
    # c'est un fil entier qui change de dossier.
    clef = mouvement.item_key
    boite = Boite()
    concernes = [m for m in boite.messages if fil_de(m) == clef]
    if not concernes:
        return
    boite.messages = [
        {**m, "dossier": cible} if fil_de(m) == clef else m
        for m in boite.messages
    ]
    # Le fil quitte le dossier affiché : le panneau de droite ne peut
    # plus le montrer. Le refermer ICI plutôt que de laisser la vue
    # pointer un fil absent — et l'adresse suit.
    if Vue().ouvert == clef:
        Vue().ouvert = ""


# ── La rédaction ──────────────────────────────────────────────────────


def rediger() -> None:
    """Déployer le panneau de rédaction, vide."""
    brouillon = Redaction()
    brouillon.a = ""
    brouillon.sujet = ""
    brouillon.corps = ""
    deployer()


def citer(messages: list[dict[str, Any]]) -> str:
    """TOUT le fil en citation, du plus récent au plus ancien.

    ⚠️ Pas seulement le dernier message. Une réponse par courrier
    emporte l'historique — c'est ce qui permet au destinataire de relire
    l'échange sans ouvrir sa propre boîte, et c'est ce que fait Outlook
    en réabattant le fil sous la réponse. La première version ne citait
    que le message auquel on répondait : sur une conversation de six
    allers-retours, la réponse arrivait sans son contexte.

    Le corps est rendu en markdown à l'affichage, donc le préfixe ``>``
    n'est pas décoratif : il produit un vrai bloc de citation. Deux
    lignes vides devant, pour que le curseur arrive AU-DESSUS de la
    citation — c'est la convention de tous les clients mail, et l'inverse
    (écrire sous la citation) est ce qu'on reproche au courrier
    d'entreprise depuis vingt ans.
    """
    blocs = []
    for courant in reversed(messages):
        lignes = courant["corps"].splitlines()
        citation = "\n".join(f"> {l}" if l else ">" for l in lignes)
        # « X a écrit (date) » et non « Le {date}, X a écrit » : les dates
        # de cette boîte prennent trois formes (« aujourd'hui, 09:14 »,
        # « hier, 18:37 », « 12 août »), et la seconde tournure rend
        # « Le hier, 18:37, X a écrit ». La parenthèse marche avec les
        # trois.
        blocs.append(
            f"{courant['de']} a écrit ({courant['date']}) :\n{citation}"
        )
    return "\n\n" + "\n\n".join(blocs)


def repondre() -> None:
    """Déployer le panneau, en réponse au DERNIER message du fil."""
    vue = Vue()
    fil = fil_ouvert(vue.dossier, vue.ouvert)
    if fil is None:
        return
    courant = fil["dernier"]
    sujet = courant["sujet"]
    brouillon = Redaction()
    brouillon.a = courant["adresse"]
    brouillon.sujet = sujet if sujet.startswith("Re: ") else f"Re: {sujet}"
    brouillon.corps = citer(fil["messages"])
    deployer()


def deployer() -> None:
    """Ouvrir le panneau à sa taille normale, sans erreur affichée."""
    panneau = Panneau()
    panneau.ouvert = True
    panneau.taille = "normal"
    panneau.erreur = ""


def redimensionner(taille: str) -> None:
    """Passer le panneau en ``normal``, ``reduit`` ou ``plein``."""
    Panneau().taille = taille


def fermer_redaction() -> None:
    """Replier le panneau sans rien enregistrer."""
    panneau = Panneau()
    panneau.ouvert = False
    panneau.erreur = ""


def envoyer() -> None:
    """Déposer le brouillon dans « Envoyés », puis replier le panneau.

    La validation est ici, au SERVEUR, et pas seulement dans le
    ``type="email"`` de l'input. Le contrôle natif du navigateur est un
    confort — il signale la faute pendant la frappe — mais il se
    contourne : rien n'empêche de poster l'action sans passer par le
    formulaire. Un handler qui fait foi ne peut pas se contenter de ce
    que le client lui promet.
    """
    brouillon = Redaction()
    panneau = Panneau()
    sujet = (brouillon.sujet or "").strip()
    corps = (brouillon.corps or "").strip()
    destinataire = (brouillon.a or "").strip()

    if not destinataire:
        panneau.erreur = "Il manque le destinataire."
        return
    if not ADRESSE.match(destinataire):
        panneau.erreur = f"« {destinataire} » n'est pas une adresse valide."
        return
    if not sujet and not corps:
        panneau.erreur = "Un message vide et sans objet ne part pas."
        return
    panneau.erreur = ""

    boite = Boite()
    boite.messages = [
        *boite.messages,
        {
            "id": identifiant_libre(),
            "dossier": "envoyes",
            "entrant": False,
            "de": "moi",
            "adresse": destinataire,
            "sujet": sujet or "(sans objet)",
            "date": "à l'instant",
            "lu": True,
            "corps": corps,
            "pieces": [],
        },
    ]

    brouillon.a = ""
    brouillon.sujet = ""
    brouillon.corps = ""
    panneau.ouvert = False
