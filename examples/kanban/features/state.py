"""kanban/state — ce que chacun regarde, par-dessus le tableau commun.

Le tableau lui-même vit dans ``donnees.Tableau`` (``AppState``) : il est
le même pour tout le monde. Tout ce qui est ici est PERSONNEL, et la
portée le dit sans qu'un commentaire ait à le rappeler.

- :class:`Moi` est un ``SessionState`` : qui je suis tient au cookie,
  donc deux fenêtres du même navigateur sont la même personne et une
  fenêtre privée en est une autre. C'est ce qui rend l'essai à deux
  écrans lisible.
- :class:`Vue` et :class:`Filtres` sont des ``PageState`` : ce que je
  regarde ne regarde que moi. Filtrer sur mes cartes ne doit rien changer
  chez les autres — et c'est précisément pour ça que ces états ne sont
  **pas** diffusés (cf. ``broadcast=`` dans ``tableau.py``).

**Rien n'est adressable ici, et c'est une décision.** ``URL = {…}`` est
la mécanique que met en scène ``examples/messagerie`` ; la reprendre
donnerait deux sujets à une app qui en démontre un. Le lien vers une
carte est donc le premier manque assumé de cet exemple.
"""

from __future__ import annotations

from bretzel import Feature
from bretzel.state import (
    ClientState,
    PageState,
    SessionState,
    field,
    validator,
)
from examples.kanban.features.donnees import CLES, LIB_ETIQUETTE, NOMS


class Moi(SessionState):
    """Qui je suis sur ce tableau.

    Il n'y a pas d'authentification : cet exemple met en scène l'état
    partagé, et une page de connexion est le sujet d'``auth``. Le
    sélecteur du bandeau permet donc de changer d'identité en un clic,
    ce qui suffit à voir un journal signé de plusieurs mains.

    ``SessionState`` et non ``PageState`` : changer d'identité dans un
    onglet doit valoir pour tous les onglets de la même personne.
    """

    membre: str = field(default="cam")

    @validator("membre")
    def _membre(cls, value: str) -> str:
        return value if value in NOMS else "cam"


class Vue(PageState):
    """Ce que cette page affiche en plus du tableau.

    ``ouverte`` porte l'identifiant de la carte montrée dans le tiroir,
    ``tiroir`` dit s'il est déployé. Deux champs pour une idée, et c'est
    le socle qui l'impose :

    ⚠️ ``open=`` d'un overlay ne se resynchronise depuis le serveur que
    si la valeur passée porte encore sa PROVENANCE — un champ d'état, pas
    une expression. ``open=vue.ouverte != ""`` rend un ``bool`` Python
    ordinaire : le socle ne peut plus dire d'où il vient, n'émet pas le
    marqueur de resynchronisation, et le tiroir garde son état client à
    travers le morph. Mesuré : la carte s'affichait bien dans le panneau,
    et le panneau restait fermé. C'est la même famille que la règle
    ``etat-perdu-par-un-cast`` de ``bretzel check``.
    """

    ouverte: str = field(default="")
    tiroir: bool = field(default=False)


class Affichage(ClientState):
    """Ce qui est déployé à l'écran, et rien d'autre.

    ``ClientState`` parce que montrer ou cacher une colonne ne regarde
    personne d'autre et ne change aucune donnée : le faire voyager
    jusqu'au serveur coûtait un aller-retour et un re-rendu de zone pour
    basculer une classe. Les deux versions — le panneau et son rail — sont
    rendues, et ``visible=`` en cache une. Zéro requête.

    C'est le pendant exact du choix inverse pris pour :class:`Filtres`
    juste dessous : là-bas le serveur DOIT savoir, ici non.
    """

    activite: bool = field(default=True)


class Filtres(PageState):
    """Les trois filtres du bandeau. Serveur, pas client — et pourquoi.

    ``examples/messagerie`` filtre dans le navigateur avec
    ``ui.filter_each`` : zéro requête par frappe. Ici ce serait un bug.
    Un filtre client laisse les cartes masquées DANS le DOM ; le socle
    lit l'index d'un dépôt parmi les éléments glissables réellement
    présents, donc déposer « en deuxième position » d'une colonne
    filtrée viserait des voisins invisibles, et la carte atterrirait
    ailleurs que là où le doigt l'a lâchée.

    Le serveur, lui, filtre et calcule les voisins avec la MÊME fonction
    (``donnees.colonne_de``), donc les deux ne peuvent pas diverger.
    """

    qui: str = field(default="tous")
    etiquette: str = field(default="toutes")
    q: str = field(default="")

    @validator("qui")
    def _qui(cls, value: str) -> str:
        return value if value in NOMS else "tous"

    @validator("etiquette")
    def _etiquette(cls, value: str) -> str:
        return value if value in LIB_ETIQUETTE else "toutes"


class Fiche(PageState):
    """QUELLE carte le brouillon du tiroir appartient à.

    Un seul champ, écrit par le serveur à l'ouverture. C'est lui qui
    empêche d'enregistrer le brouillon d'une carte sur une autre quand
    l'enregistrement part pendant qu'on en ouvrait une autre.
    """

    carte_id: str = field(default="")


class Brouillon(ClientState):
    """Ce qu'on est en train d'écrire dans le tiroir.

    ⚠️ **``ClientState``, et il a fallu une mesure pour l'écrire.** Ces
    champs vivaient dans le ``PageState`` ci-dessus, donc ils étaient
    rendus par le serveur — à l'intérieur d'une zone qui déclare
    ``broadcast=[Tableau]``. Conséquence : **n'importe qui déplaçait une
    carte, et ce que tu tapais disparaissait.** Mesuré à deux sessions le
    2026-09-09 — B écrit « brouillon en cours » sans envoyer, A glisse une
    carte à l'autre bout du tableau, et quatre secondes plus tard le champ
    de B est vide et son titre est revenu à celui du serveur.

    Une valeur de ``ClientState`` vit dans le magasin du navigateur : le
    morph la réapplique, donc elle survit à un re-rendu venu d'ailleurs.
    C'est la même décision que la rédaction d'``examples/messagerie``, et
    pour la même raison.

    Le serveur peut quand même l'AMORCER — ``logic.charger`` recopie la
    carte ouverte dedans, et la valeur redescend dans le patch. Écrire un
    état client depuis un handler est un chemin normal du socle, pas un
    détour.

    Deux régimes se lisent encore à l'écran : le titre, la description,
    l'assigné, l'échéance et les points attendent « Enregistrer » — les
    écrire à chaque frappe ferait une écriture partagée par caractère.
    Les étiquettes, les sous-tâches et les commentaires partent au clic,
    parce qu'un clic EST déjà la décision.
    """

    titre: str = field(default="")
    description: str = field(default="")
    qui: str = field(default="cam")
    echeance: str = field(default="")
    points: int = field(default=0)

    #: Les deux champs d'ajout du tiroir. Ils se vident après usage, donc
    #: ils ne font pas partie du brouillon qu'on enregistre.
    sous_tache: str = field(default="")
    commentaire: str = field(default="")




class Avancement(ClientState):
    """Combien de sous-tâches sont cochées, tenu DANS le navigateur.

    La vérité reste le tableau : c'est lui que le serveur écrit, et c'est
    de lui que ce compteur est réamorcé à chaque rendu du tiroir. Mais
    cocher une case déplace la barre **avant** que la requête parte, au
    lieu d'attendre les 180 Ko de la réponse. C'est de l'optimiste au sens
    strict — le client avance, le serveur arbitre, le rendu suivant
    recale. Sans lui la barre était juste et EN RETARD, ce qui est le pire
    des deux : le geste a l'air de n'avoir rien fait.

    ⚠️ **Une classe à part, et c'est la mesure qui l'impose.** Ce champ a
    d'abord vécu dans :class:`Brouillon`. Écrire UNE valeur d'un état
    client depuis le serveur renvoie l'objet ENTIER dans le patch : la
    réconciliation de ce compteur remettait donc aussi ``commentaire`` à
    la valeur que le serveur croyait, c'est-à-dire vide. Mesuré — on
    tape, la réponse d'un geste voisin arrive 1,2 s plus tard, et le
    champ se vide tout seul.

    La règle qui en sort : **un brouillon que l'humain édite et une
    valeur que le serveur recale ne partagent pas une classe.**
    """

    faites: int = field(default=0)


class Nouvelle(PageState):
    """La carte qu'on est en train de créer, dans le dialogue."""

    titre: str = field(default="")
    colonne: str = field(default="a_faire")

    @validator("colonne")
    def _colonne(cls, value: str) -> str:
        return value if value in CLES else "a_faire"


feature = Feature(
    name="state", kind="state",
    provides=[Moi, Vue, Affichage, Filtres, Fiche, Brouillon,
              Avancement, Nouvelle],
    uses=["donnees"],
)
