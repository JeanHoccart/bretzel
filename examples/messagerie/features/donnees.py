"""messagerie/donnees — la boîte, en mémoire, partagée par tout le monde.

``AppState`` et pas ``SessionState`` : une messagerie est un objet unique
dont tous les onglets parlent. Déplacer un message dans un onglet doit se
voir dans l'autre — c'est la portée qui le dit, pas un mécanisme de
synchronisation écrit à la main.

Aucune base de données, et c'est le choix de cet exemple : trois autres
démos (`crm`, `mad`) montrent SQLite, aucune ne montrait un état
partagé en mémoire comme source de vérité d'une app entière. Le prix est
écrit : redémarrer le serveur remet la boîte à son état de départ.

Un message est un ``dict`` et pas une dataclass, pour la même raison que
``examples/chat`` : ce qui est démontré ici est le transport de la vue,
pas la modélisation du domaine. Un `dict` se lit sans ouvrir un second
fichier.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from bretzel.state import AppState, field

#: Les quatre dossiers, dans l'ordre où la colonne les affiche. La clé
#: voyage dans l'URL (`?dossier=archives`), donc elle est une API
#: publique : la renommer casserait les liens partagés.
DOSSIERS: tuple[tuple[str, str, str], ...] = (
    ("recus", "Reçus", "inbox"),
    ("envoyes", "Envoyés", "send"),
    ("archives", "Archives", "archive"),
    ("corbeille", "Corbeille", "trash-2"),
)

#: Les clés seules, pour valider un paramètre d'URL saisi à la main.
CLES = tuple(cle for cle, _, _ in DOSSIERS)


#: L'arrière-plan de la boîte : du courrier plus ancien, écrit en table
#: parce qu'il ne sert qu'à donner du VOLUME. Les huit messages détaillés
#: de ``courrier_recent`` portent la démonstration ; ceux-ci portent la
#: densité — sans eux, la liste tient sur un demi-écran et on ne voit ni
#: le défilement, ni ce que la recherche fait vraiment.
#:
#: Ordre : du plus ANCIEN au plus récent. Les identifiants sont attribués
#: par position dans :func:`semer`, pas écrits ici.
ARRIERE_PLAN: tuple[tuple[str, str, str, str, str, bool], ...] = (
    # (expéditeur, adresse, sujet, date, dossier, lu)
    ("Groupama Pro", "contrats@groupama-pro.fr",
     "Échéance de votre contrat décennale", "2 juin", "archives", True),
    ("Kiloutou", "agence-lille@kiloutou.fr",
     "Devis location nacelle 12 m", "5 juin", "archives", True),
    ("Sofia Bendjelloul", "s.bendjelloul@beton-flandres.fr",
     "Planning de coulage — semaine 24", "11 juin", "archives", True),
    ("URSSAF", "no-reply@urssaf.fr",
     "Votre attestation de vigilance est disponible", "14 juin", "archives",
     True),
    ("Thomas Lecomte", "t.lecomte@charpentes-lecomte.fr",
     "Relance : métré de la charpente", "18 juin", "corbeille", True),
    ("Point P", "commandes@pointp.fr",
     "Confirmation de commande CP-88214", "21 juin", "archives", True),
    ("Élodie Vasseur", "e.vasseur@cabinet-vasseur.fr",
     "Compte rendu de visite — lot 3", "25 juin", "archives", True),
    ("Newsletter Batiactu", "info@batiactu.com",
     "RE 2020 : ce qui change au 1er juillet", "28 juin", "corbeille", True),
    ("Karim Ferhati", "k.ferhati@electricite-ferhati.fr",
     "Disponibilité pour le tableau divisionnaire", "1 juillet", "archives",
     True),
    ("Mairie de Kerlouan", "urbanisme@mairie-kerlouan.fr",
     "Demande de pièce complémentaire — PC 2026-0042", "3 juillet",
     "archives", True),
    ("Sofia Bendjelloul", "s.bendjelloul@beton-flandres.fr",
     "Report du coulage : météo", "8 juillet", "archives", True),
    ("Loxam", "devis@loxam.fr",
     "Votre devis n° D-77120", "12 juillet", "corbeille", True),
    ("Thomas Lecomte", "t.lecomte@charpentes-lecomte.fr",
     "Métré charpente — version corrigée", "15 juillet", "archives", True),
    ("Assurance MAAF", "sinistres@maaf.fr",
     "Déclaration de sinistre : accusé de réception", "19 juillet",
     "archives", True),
    ("Élodie Vasseur", "e.vasseur@cabinet-vasseur.fr",
     "Plans d'exécution — indice C", "23 juillet", "archives", True),
    ("Karim Ferhati", "k.ferhati@electricite-ferhati.fr",
     "Facture FE-2026-118", "27 juillet", "archives", True),
    ("Sofia Bendjelloul", "s.bendjelloul@beton-flandres.fr",
     "Bon de livraison — 14 m³", "30 juillet", "archives", True),
    ("Point P", "commandes@pointp.fr",
     "Rupture temporaire sur le parpaing 20", "4 août", "recus", True),
    ("Nolwenn Le Guen", "n.leguen@mairie-kerlouan.fr",
     "Réunion publique du 20 août", "6 août", "recus", True),
    ("Thomas Lecomte", "t.lecomte@charpentes-lecomte.fr",
     "Intervention décalée au 18", "9 août", "recus", True),
    ("Élodie Vasseur", "e.vasseur@cabinet-vasseur.fr",
     "Validation du bardage : teinte retenue", "13 août", "recus", True),
    ("Karim Ferhati", "k.ferhati@electricite-ferhati.fr",
     "Relance facture FE-2026-118", "17 août", "recus", True),
    ("Sofia Bendjelloul", "s.bendjelloul@beton-flandres.fr",
     "Planning de coulage — semaine 35", "20 août", "recus", True),
    ("Groupama Pro", "contrats@groupama-pro.fr",
     "Renouvellement : votre échéancier 2027", "24 août", "recus", True),
    ("Mairie de Kerlouan", "urbanisme@mairie-kerlouan.fr",
     "Arrêté de circulation — rue du Moulin", "27 août", "recus", True),
    ("Point P", "commandes@pointp.fr",
     "Votre commande CP-90331 est prête", "30 août", "recus", True),
    ("Élodie Vasseur", "e.vasseur@cabinet-vasseur.fr",
     "Réserves levées sur le lot 3", "2 septembre", "recus", True),
    ("Thomas Lecomte", "t.lecomte@charpentes-lecomte.fr",
     "Devis complémentaire : renfort de panne", "4 septembre", "recus", False),
)

#: Le corps des messages d'arrière-plan. Deux phrases, dérivées du sujet :
#: ils doivent se LIRE dans l'aperçu sans que personne les ait écrits un
#: par un.
def corps_generique(sujet: str, de: str) -> str:
    return (
        f"Bonjour,\n\n"
        f"Pour faire suite à nos échanges au sujet de « {sujet.lower()} », "
        f"je reviens vers vous avec les éléments demandés.\n\n"
        f"N'hésitez pas si un point mérite d'être repris.\n\n"
        f"{de}"
    )


def arriere_plan() -> list[dict[str, Any]]:
    """Le courrier ancien, matérialisé depuis :data:`ARRIERE_PLAN`."""
    return [
        {
            "id": 0,  # attribué par position dans ``semer``
            "dossier": dossier,
            "entrant": True,
            "de": de,
            "adresse": adresse,
            "sujet": sujet,
            "date": date,
            "lu": lu,
            "corps": corps_generique(sujet, de),
            "pieces": ["piece-jointe.pdf"] if "acture" in sujet else [],
        }
        for de, adresse, sujet, date, dossier, lu in ARRIERE_PLAN
    ]


def semer() -> list[dict[str, Any]]:
    """La boîte au démarrage. Rejouée à chaque lancement du serveur.

    Les identifiants sont attribués PAR POSITION, du plus ancien au plus
    récent : c'est ce qui fait que « id croissant » veut dire « plus
    récent », et donc que ``identifiant_libre()`` place un message neuf en
    tête de liste sans rien avoir à trier.
    """
    # ``courrier_recent`` s'écrit dans l'ordre où on l'a rédigé, pas dans
    # l'ordre du temps ; ses ``id`` littéraux, eux, sont chronologiques.
    # On s'en sert pour le remettre en ordre, puis TOUS les identifiants
    # sont réattribués par position.
    ordonnes = [
        *arriere_plan(),
        *sorted(courrier_recent(), key=lambda m: m["id"]),
        *echange_hangar(),
        *relance_sans_reponse(),
    ]
    for rang, message_ in enumerate(ordonnes, start=1):
        message_["id"] = rang
    return ordonnes


def echange_hangar() -> list[dict[str, Any]]:
    """Cinq allers-retours avec la même personne, dans le MÊME fil.

    C'est ce qui rend le regroupement visible : sans un vrai échange, un
    fil et un message se ressemblent, et la liste ne prouve rien. Le
    sujet reste « Re: Les plans du hangar 3 », donc ces messages tombent
    dans le fil ouvert par Camille ce matin.
    """
    echange = (
        ("moi", "moi@atelier-nord.fr", "envoyes", "aujourd'hui, 09:41", True,
         "La dalle est coulée depuis vendredi, on est dans les temps.\n\n"
         "En revanche la section de charpente change tout pour l'appui : "
         "il faut que je repasse voir le bureau d'études avant de "
         "commander l'acier."),
        ("Camille Roussel", "camille.roussel@atelier-nord.fr", "recus",
         "aujourd'hui, 10:02", True,
         "Parfait pour la dalle.\n\nPour l'acier, attends leur retour de "
         "lundi — ils parlaient de reprendre la descente de charge, ça "
         "peut encore bouger d'une section."),
        ("moi", "moi@atelier-nord.fr", "envoyes", "aujourd'hui, 10:20", True,
         "Entendu, je bloque la commande jusqu'à lundi soir."),
        ("Camille Roussel", "camille.roussel@atelier-nord.fr", "recus",
         "aujourd'hui, 10:47", True,
         "Autre chose : le maître d'ouvrage demande si on peut avancer la "
         "pose du bardage d'une semaine. Tu as la main sur le planning ?"),
        ("Camille Roussel", "camille.roussel@atelier-nord.fr", "recus",
         "aujourd'hui, 11:26", False,
         "Je relance — il lui faut une réponse avant sa réunion de "
         "demain matin."),
    )
    return [
        {
            "id": 0,  # attribué par position dans ``semer``
            "dossier": dossier,
            "entrant": de != "moi",
            "de": de,
            "adresse": adresse,
            "sujet": "Re: Les plans du hangar 3",
            "date": date,
            "lu": lu,
            "corps": corps,
            "pieces": [],
        }
        for de, adresse, dossier, date, lu, corps in echange
    ]


def relance_sans_reponse() -> list[dict[str, Any]]:
    """Un message envoyé qui n'a jamais reçu de réponse.

    Il existe pour une raison précise : c'est le SEUL fil purement
    sortant de la boîte, donc le seul qui exerce la règle « on ne marque
    pas non lu ce qu'on a écrit soi-même ». Sans lui, tous les fils
    d'« Envoyés » contiennent aussi du courrier reçu — le fil est
    l'unité, et il s'affiche entier — et la règle n'aurait plus de cas
    pour la vérifier.
    """
    return [
        {
            "id": 0,  # attribué par position dans ``semer``
            "dossier": "envoyes",
            "entrant": False,
            "de": "moi",
            "adresse": "s.bendjelloul@beton-flandres.fr",
            "sujet": "Disponibilité de la pompe à béton",
            "date": "aujourd'hui, 11:40",
            "lu": True,
            "corps": (
                "Bonjour Sofia,\n\n"
                "Auriez-vous une pompe disponible le 22 au matin ? Le "
                "volume est de 18 m³ environ.\n\n"
                "Merci d'avance."
            ),
            "pieces": [],
        },
    ]


def courrier_recent() -> list[dict[str, Any]]:
    """Les huit messages détaillés — ceux qui portent la démonstration."""
    return [
        {
            "id": 8,
            "dossier": "recus",
            "entrant": True,
            "de": "Camille Roussel",
            "adresse": "camille.roussel@atelier-nord.fr",
            "sujet": "Les plans du hangar 3",
            "date": "aujourd'hui, 09:14",
            "lu": False,
            "corps": (
                "Bonjour,\n\n"
                "Je t'envoie les plans revus du hangar 3. La travée est "
                "passée de 12 à 14 mètres, donc la charpente change de "
                "section — le bureau d'études repasse dessus lundi.\n\n"
                "Peux-tu me confirmer que la dalle est coulée avant le 20 ?"
            ),
            "pieces": ["hangar-3-plans-v4.pdf", "note-bureau-etudes.pdf"],
        },
        {
            "id": 6,
            "dossier": "recus",
            "entrant": True,
            "de": "Farid Benali",
            "adresse": "f.benali@transports-benali.com",
            "sujet": "Créneau de livraison mardi",
            "date": "aujourd'hui, 08:02",
            "lu": False,
            "corps": (
                "Le camion peut passer mardi entre 7 h et 9 h, ou en fin "
                "de journée après 17 h.\n\n"
                "Dis-moi ce qui vous arrange, je bloque le créneau."
            ),
            "pieces": [],
        },
        {
            "id": 5,
            "dossier": "recus",
            "entrant": True,
            "de": "Inès Marchand",
            "adresse": "ines@marchand-archi.fr",
            "sujet": "Compte rendu de la réunion de chantier",
            "date": "hier, 18:37",
            "lu": True,
            "corps": (
                "Compte rendu de la réunion du 4 :\n\n"
                "- le raccordement électrique est décalé d'une semaine ;\n"
                "- l'étanchéité de la toiture est réceptionnée ;\n"
                "- reste à trancher la couleur des menuiseries.\n\n"
                "Prochaine réunion le 18, même heure."
            ),
            "pieces": ["cr-reunion-04.pdf"],
        },
        {
            "id": 4,
            "dossier": "recus",
            "entrant": True,
            "de": "Service comptabilité",
            "adresse": "compta@atelier-nord.fr",
            "sujet": "Facture 2026-0871 — échéance dépassée",
            "date": "hier, 11:20",
            "lu": True,
            "corps": (
                "La facture 2026-0871 est échue depuis le 31 août.\n\n"
                "Merci de nous dire si le règlement est parti, faute de "
                "quoi nous relancerons le client directement."
            ),
            "pieces": ["facture-2026-0871.pdf"],
        },
        {
            "id": 3,
            "dossier": "recus",
            "entrant": True,
            "de": "Nolwenn Le Guen",
            "adresse": "n.leguen@mairie-kerlouan.fr",
            "sujet": "Autorisation de voirie — accusé de réception",
            "date": "lundi, 15:05",
            "lu": True,
            "corps": (
                "Votre demande d'occupation temporaire du domaine public "
                "a bien été enregistrée sous le numéro OTDP-2026-114.\n\n"
                "Le service instructeur revient vers vous sous 15 jours."
            ),
            "pieces": [],
        },
        {
            "id": 7,
            "dossier": "envoyes",
            "entrant": False,
            "de": "moi",
            "adresse": "moi@atelier-nord.fr",
            "sujet": "Re: Créneau de livraison mardi",
            "date": "aujourd'hui, 08:41",
            "lu": True,
            "corps": "Le matin nous arrange, 7 h 30 si c'est possible.",
            "pieces": [],
        },
        {
            "id": 2,
            "dossier": "archives",
            "entrant": True,
            "de": "Inès Marchand",
            "adresse": "ines@marchand-archi.fr",
            "sujet": "Permis de construire — accord",
            "date": "12 août",
            "lu": True,
            "corps": (
                "L'accord est arrivé ce matin, sans réserve.\n\n"
                "On peut lancer le terrassement dès que tu veux."
            ),
            "pieces": ["pc-accord.pdf"],
        },
        {
            "id": 1,
            "dossier": "corbeille",
            "entrant": True,
            "de": "Newsletter BTP Hebdo",
            "adresse": "no-reply@btp-hebdo.fr",
            "sujet": "Les 10 tendances du gros œuvre en 2026",
            "date": "3 août",
            "lu": True,
            "corps": "Vous recevez ce message car vous êtes inscrit.",
            "pieces": [],
        },
    ]


class Boite(AppState):
    """Tous les messages, tous dossiers confondus.

    Un seul champ : le dossier d'un message est une propriété DU message,
    pas une liste par dossier. C'est ce qui fait qu'un déplacement est une
    écriture d'un caractère et non un retrait suivi d'un ajout — donc
    qu'il ne peut pas laisser le message dans deux dossiers à la fois.
    """

    messages: list[dict[str, Any]] = field(default_factory=semer)


def messages_du_dossier(cle: str) -> list[dict[str, Any]]:
    """Les messages d'un dossier, du plus récent au plus ancien.

    ⚠️ **Le tri ne regarde PAS ``lu``.** La première version mettait les
    non-lus en tête : ouvrir un message le marquait lu, donc il changeait
    de groupe et **descendait au bas de la pile sous le curseur**. Aucun
    client mail ne fait ça, et pour une bonne raison — l'ordre d'une
    liste doit être stable sous l'action de la lire. Le non-lu se signale
    par l'apparence, jamais par la position.
    """
    dedans = [m for m in Boite().messages if m["dossier"] == cle]
    return sorted(dedans, key=lambda m: -m["id"])


# ── Les fils de conversation ──────────────────────────────────────────
#
# Une messagerie ne montre pas des messages, elle montre des ÉCHANGES :
# dix allers-retours avec la même personne font UNE ligne, pas dix. Le
# regroupement se fait sur le sujet NORMALISÉ — c'est ce que font les
# clients mail qui n'ont pas d'en-tête ``References`` à se mettre sous la
# dent, et un exemple n'a pas de vraies en-têtes.


def sujet_normalise(sujet: str) -> str:
    """« Re: Re: Les plans » et « Les plans » sont le MÊME fil."""
    nu = sujet.strip()
    bas = nu.lower()
    while bas.startswith(("re:", "re :", "tr:", "fwd:")):
        nu = nu.split(":", 1)[1].strip()
        bas = nu.lower()
    return nu.lower()


def fil_de(message: dict[str, Any]) -> str:
    """La clé de fil d'un message — un SLUG, parce qu'elle voyage en URL.

    ``?fil=les-plans-du-hangar-3`` et non ``?fil=les+plans+du+hangar+3``.
    Une clé qui part dans l'adresse est une API publique : elle doit se
    lire, se recopier au téléphone et survivre à un copier-coller. Les
    espaces n'y ont pas leur place.
    """
    nu = unicodedata.normalize("NFKD", sujet_normalise(message["sujet"]))
    sans_accent = "".join(c for c in nu if not unicodedata.combining(c))
    garde = [c if c.isalnum() else "-" for c in sans_accent]
    return re.sub(r"-{2,}", "-", "".join(garde)).strip("-")


def fils_du_dossier(cle: str) -> list[dict[str, Any]]:
    """Les fils visibles dans un dossier, du plus récent au plus ancien.

    Un fil apparaît dans un dossier dès qu'UN de ses messages y est, et
    il s'y montre ENTIER — mes réponses comprises, même si elles vivent
    dans « Envoyés ». C'est ce que fait Gmail, et c'est ce qui rend un
    échange lisible : la première version ne gardait que les messages du
    dossier courant, donc on lisait quatre messages de la même personne
    sans les réponses qui les séparaient.

    ⚠️ Simplification assumée : un message mis à la corbeille emmène donc
    son fil dans la corbeille aussi. Un vrai client sépare les deux ;
    l'exemple ne le fait pas, parce que ça demanderait un état par
    (fil, dossier) qui n'apprend rien de plus sur Bretzel.

    Chaque fil rend un dictionnaire prêt à afficher : ses messages du
    plus ancien au plus récent, le dernier, le compte de non-lus, et la
    liste des participants dans l'ordre où ils ont parlé.
    """
    ici = {fil_de(m) for m in Boite().messages if m["dossier"] == cle}
    par_fil: dict[str, list[dict[str, Any]]] = {}
    for m in Boite().messages:
        clef = fil_de(m)
        if clef in ici:
            par_fil.setdefault(clef, []).append(m)

    fils = []
    for clef, membres in par_fil.items():
        membres = sorted(membres, key=lambda m: m["id"])
        dernier = membres[-1]
        participants: list[str] = []
        for m in membres:
            if m["de"] not in participants:
                participants.append(m["de"])
        fils.append({
            "fil": clef,
            "messages": membres,
            "dernier": dernier,
            "sujet": sujet_court(membres[0]["sujet"]),
            "non_lus": sum(1 for m in membres if m["entrant"] and not m["lu"]),
            "participants": participants,
        })
    return sorted(fils, key=lambda f: -f["dernier"]["id"])


def sujet_court(sujet: str) -> str:
    """Le sujet du fil : celui du premier message, sans son « Re: »."""
    nu = sujet.strip()
    while nu.lower().startswith(("re:", "re :", "tr:", "fwd:")):
        nu = nu.split(":", 1)[1].strip()
    return nu


def fil_ouvert(cle: str, clef: str) -> dict[str, Any] | None:
    """Le fil ``clef`` dans le dossier ``cle``, ou ``None``."""
    for fil in fils_du_dossier(cle):
        if fil["fil"] == clef:
            return fil
    return None


def texte_du_fil(fil: dict[str, Any]) -> str:
    """Tout ce sur quoi la recherche mord dans un fil."""
    morceaux = []
    for m in fil["messages"]:
        morceaux += [m["de"], m["adresse"], m["sujet"], m["corps"]]
    return " ".join(morceaux)


def message(identifiant: int) -> dict[str, Any] | None:
    """Un message par son identifiant, ou ``None`` s'il n'existe plus."""
    for candidat in Boite().messages:
        if candidat["id"] == identifiant:
            return candidat
    return None


def non_lus(cle: str) -> int:
    """Combien de messages ENTRANTS non lus dans ce dossier.

    Les messages qu'on a écrits ne comptent pas : « Envoyés » affichait
    une pastille de non-lus, ce qui n'a aucun sens — on a lu ce qu'on
    vient d'écrire.
    """
    return sum(
        1 for m in Boite().messages
        if m["dossier"] == cle and m["entrant"] and not m["lu"]
    )


def date_courte(message: dict[str, Any]) -> str:
    """La date de la liste, DÉRIVÉE de la date longue.

    ⚠️ Elle était un champ recopié dans chaque message, et le message
    créé par « Envoyer » ne le portait pas : afficher « Envoyés » levait
    un ``KeyError: 'court'``. Une valeur dérivable ne se stocke pas — la
    dériver rend le cas impossible plutôt que rare.
    """
    longue = message["date"]
    if longue.startswith("aujourd'hui, "):
        return longue.removeprefix("aujourd'hui, ")
    if longue.startswith("hier"):
        return "hier"
    if "," in longue:
        return longue.split(",")[0]
    return longue


def apercu(message: dict[str, Any], taille: int = 90) -> str:
    """La première ligne du corps, pour la liste.

    Une messagerie sans aperçu ne se lit pas : le sujet seul oblige à
    ouvrir pour savoir de quoi il s'agit. C'est ce que fait tout client
    mail, et c'est ce qui distingue une liste d'une table.
    """
    plat = " ".join(message["corps"].split())
    return plat if len(plat) <= taille else plat[: taille - 1].rstrip() + "…"


def identifiant_libre() -> int:
    """Le prochain identifiant, dérivé de la boîte plutôt que compté.

    Un compteur sur un ``AppState`` est un compteur PARTAGÉ : deux envois
    simultanés le liraient à la même valeur et le second écraserait le
    premier. Le dériver du maximum le rend idempotent, et supprime le
    besoin d'un ``merge="add"`` que rien d'autre ici ne justifierait.
    """
    return max((m["id"] for m in Boite().messages), default=0) + 1
