"""messagerie/state — la vue vit dans l'adresse.

C'est LA mécanique que cet exemple met en scène, et elle tient en trois
lignes de déclaration.

Un ``PageState`` vit dans un dictionnaire serveur indexé par un uuid de
rendu, **neuf à chaque navigation**. Sans rien de plus, ouvrir un
message puis appuyer sur la flèche retour n'a aucun effet utile : le
navigateur refait un vrai GET, obtient un uuid neuf, et atterrit sur une
adresse qui ne dit rien de ce qu'on regardait.

``URL = {…}`` déclare les champs dont **l'adresse fait foi**. Le socle
les relit au rendu et réécrit la barre d'adresse à chaque mutation, sans
navigation ni rechargement. À partir de là, trois choses marchent d'un
coup et aucune n'a été codée : le lien se partage, le favori retrouve la
même vue, et les flèches du navigateur font l'aller-retour.

⚠️ **Le nom d'URL est écrit, pas dérivé du nom Python.** ``ouvert``
s'appelle ``msg`` dans l'adresse. Une URL est une API publique : si elle
se dérivait du nom du champ, renommer un attribut casserait les liens
déjà partagés.

⚠️ **Ce qui est déclaré est PUBLIC** — historique du navigateur, journaux
du serveur, en-tête ``Referer`` de la requête suivante. Ici le dossier
ouvert et l'identifiant du message lu ; le brouillon de réponse, lui,
n'est pas de la partie et ne peut pas l'être : il n'a pas de nom d'URL.
"""

from __future__ import annotations

from bretzel.state import ClientState, PageState, field, validator


class Vue(PageState):
    """Ce qu'on regarde : un dossier, et éventuellement un message.

    ``ouvert`` porte la clé d'un FIL, pas d'un message : ce qu'on ouvre
    dans une messagerie est une conversation entière. Vide = rien
    d'ouvert, et le panneau de droite affiche son état vide.

    Une chaîne plutôt qu'un entier, et c'est le regroupement qui le
    décide : un fil n'a pas d'identité propre en base, il se dérive du
    sujet normalisé. L'adresse devient donc lisible —
    ``?fil=les plans du hangar 3`` — ce qui est un effet de bord
    heureux : une URL doit se lire.
    """

    dossier: str = field(default="recus")
    ouvert: str = field(default="")

    URL = {"dossier": "dossier", "ouvert": "fil"}


class Filtre(ClientState):
    """Ce qu'on cherche dans le dossier ouvert.

    ``ClientState`` et non ``PageState``, parce que le filtrage se fait
    **dans le navigateur** : ``ui.filter_each`` prend un
    ``ClientBinding`` et pose un ``bz-show`` par ligne. Taper ne coûte
    donc aucune requête — ni ``on_input``, ni ``debounce``, ni zone à
    re-rendre.

    ⚠️ **Le compromis est dans les deux sens, et il se choisit.** Le
    filtrage client exige que TOUTES les lignes soient dans le DOM : à
    huit messages c'est gratuit, à cinq mille c'est une page qui pèse. Le
    jour où la boîte grossit, la réponse n'est pas de rendre ce champ
    plus malin — c'est de filtrer côté serveur et de paginer, ce que
    ``ui.datatable`` fait déjà (``examples/crm``).

    ⚠️ **Rien ici n'est adressable, et c'est une décision.** Un champ
    déclaré dans ``URL = {…}`` est PUBLIC : historique du navigateur,
    journaux du serveur, en-tête ``Referer`` de la requête suivante. Le
    dossier qu'on regarde ne dit rien de sensible ; ce qu'on cherche dans
    sa boîte mail, si. Le framework tient la même ligne — ``filters``
    n'est adressable dans aucun de ses défauts.
    """

    q: str = field(default="")


class Panneau(PageState):
    """L'état du panneau de rédaction : déployé ? et à quelle taille ?

    Un état SERVEUR et non client, contrairement au brouillon qu'il
    contient. La raison est la taille : passer de « normal » à « plein
    écran » change les classes du conteneur, et une classe ne se lie pas
    côté client comme une valeur. Le panneau est donc une zone
    rafraîchissable, et son contenu textuel — lui — reste dans un
    ``ClientState``, ce qui le fait survivre au re-rendu.
    """

    #: ``normal`` (coin bas-droit) · ``reduit`` (barre de titre seule) ·
    #: ``plein`` (centré, presque tout l'écran).
    taille: str = field(default="normal")
    ouvert: bool = field(default=False)

    #: Ce qui empêche l'envoi, en clair. Vide = rien à signaler.
    erreur: str = field(default="")

    @validator("taille")
    def _taille(cls, value: str) -> str:
        """Une taille hors table retombe sur ``normal``.

        Le validateur COERCE, il ne lève pas : la valeur arrive d'un
        handler de l'app, pas d'une saisie — une faute de frappe ici doit
        rendre un panneau utilisable, pas une page d'erreur.
        """
        return value if value in ("normal", "reduit", "plein") else "normal"


class Redaction(ClientState):
    """Le brouillon du message qu'on écrit.

    ``ClientState`` sans ``send_to_server=False`` : ces valeurs naissent
    dans le navigateur et doivent donc remonter, sinon le handler
    d'envoi ne saurait pas quoi enregistrer. C'est le contre-exemple
    exact de la ``Vue`` au-dessus — celle-ci est écrite par le serveur et
    publiée dans l'adresse, celle-là est écrite par l'humain et ne sort
    jamais de la page tant qu'il n'a pas cliqué.
    """

    a: str = field(default="")
    sujet: str = field(default="")
    corps: str = field(default="")

