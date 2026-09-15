"""features/access — logic : qui regarde, et ce qu'il a le droit de voir.

La feature la plus courte du CRM, et celle que toutes les autres lisent.
Elle répond à **une** question — :func:`visible_owner` — et toute la
politique d'accès de l'app tient dans sa réponse :

- un **commercial** est ramené à son propre portefeuille, toujours, sans
  qu'aucun écran ait à le savoir ;
- un **directeur** voit tout (``None``), ou se met à la place de quelqu'un
  en choisissant un portefeuille.

⚠️ **Le filtre est un PARAMÈTRE, pas une variable globale que les repos
iraient lire.** Chaque fonction de lecture prend son ``owner`` et le pose
dans son ``WHERE`` ; l'écran le passe. C'est plus verbeux, et c'est le
point : on peut RELIRE une signature et voir si elle est cadrée. Un repo
qui appellerait ``visible_owner()`` tout seul rendrait le filtrage
invisible au call-site — et un chemin oublié le resterait.

⚠️ ``ViewerPrefs`` est un :class:`~bretzel.state.UserState`, donc il **lève
``AuthRequiredError`` (401) hors d'une session connectée**. C'est la
segmentation d'état que le framework fournit, et la seule chose qu'il
fournit en matière d'utilisateur : ne jamais le toucher depuis une page
publique.
"""

from __future__ import annotations

from bretzel import Feature, redirect
from bretzel.render import current_context
from bretzel.server import auth
from bretzel.state import UserState, field
from examples.crm.core.domain import LOGIN_PATH, OWNERS
from examples.crm.features.auth_data import find_by_id


class ViewerPrefs(UserState):
    """Les préférences attachées au COMPTE, pas à la session.

    Deux navigateurs connectés au même compte voient le même réglage ; deux
    comptes sur le même navigateur n'en partagent aucun. C'est exactement ce
    que ``scope="user"`` veut dire, et c'est la raison d'être de la classe.
    """

    #: Le portefeuille qu'un DIRECTEUR regarde. Vide = tous. Un commercial
    #: ne s'en sert pas : son portefeuille n'est pas un choix.
    portefeuille: str = field(default='')


#: Le nom sous lequel le profil est posé sur ``request.state``. Une
#: constante plutôt qu'un littéral répété : c'est une clé partagée avec
#: le socle, sur un objet qui n'est pas à nous.
_PROFILE_SLOT = "crm_profile"


def current_profile() -> dict | None:
    """Le compte connecté, joint depuis l'identifiant du cookie.

    ``None`` quand personne n'est connecté — ou quand le cookie désigne un
    compte supprimé, ce qui doit se comporter pareil.

    ⚠️ **Mémorisé pour la durée de la REQUÊTE**, sur ``request.state``.
    Sans ce cache, chaque appel rouvrait une connexion SQLite : le choix
    « le cadrage est un paramètre » fait appeler :func:`visible_owner`
    une fois par zone, et l'écran des rapports en comptait **neuf par
    rendu** (sept zones + deux pour la barre latérale), soit neuf
    ouvertures de fichier à 1,6 ms pour répondre « qui regarde ».
    Mesuré : 54,4 ms → 36,6 ms sur ``/rapports`` (−33 %).

    Le cache est **par requête**, pas global (anti-règle 2) : deux
    requêtes ne partagent rien, et une reconnexion en cours de requête
    n'existe pas — la page de connexion ne lit aucun profil.
    """
    try:
        state = current_context().request.state
    except RuntimeError:
        # Hors contexte de rendu (un test qui appelle directement) : pas
        # de requête à quoi accrocher un cache, on lit à chaque fois.
        return read_profile()
    cached = getattr(state, _PROFILE_SLOT, _MISSING)
    if cached is _MISSING:
        cached = read_profile()
        setattr(state, _PROFILE_SLOT, cached)
    return cached


#: Sentinelle : ``None`` est une valeur de cache LÉGITIME (personne n'est
#: connecté), donc elle ne peut pas dire « pas encore lu ».
_MISSING = object()


def read_profile() -> dict | None:
    user_id = auth.user_id()
    return find_by_id(user_id) if user_id else None


def is_director() -> bool:
    profile = current_profile()
    return bool(profile) and profile["role"] == "directeur"


#: Le cadrage d'un ANONYME. Ce n'est pas ``None`` — ``None`` veut dire
#: « tous », et le défaut d'une politique d'accès ne peut pas être « tout ».
#: Aucun propriétaire ne s'appelle ``""``, donc ``WHERE owner = ''`` ne
#: rend rien : c'est un refus qui passe par le même chemin que le reste,
#: sans qu'aucune lecture ait à connaître le cas.
NOBODY = ""


def visible_owner() -> str | None:
    """Le propriétaire dont on a le droit de voir la donnée. ``None`` = tous.

    L'unique porte de la politique d'accès. Trois cas, et l'ordre compte :

    1. **personne n'est connecté** → :data:`NOBODY`, donc rien. La garde
       middleware renvoie déjà sur la connexion ; ce retour est le
       deuxième verrou, pour le jour où une route sortirait de la garde.
       Rendre ``None`` ici serait ouvrir TOUTE la base à l'anonyme — la
       forme d'erreur qu'on ne voit jamais en relisant, parce que la page
       s'affiche parfaitement ;
    2. **commercial** → son propre nom, TOUJOURS. Il n'y a pas de branche
       où il pourrait en obtenir un autre : c'est la propriété qu'on veut
       pouvoir relire d'un coup d'œil ;
    3. **directeur** → ce qu'il a choisi, ou ``None`` s'il n'a rien choisi.
       Un choix qui ne désigne pas un propriétaire connu est ignoré plutôt
       que refusé — un réglage périmé ne doit pas bloquer une page.
    """
    profile = current_profile()
    if profile is None:
        return NOBODY
    if profile["role"] != "directeur":
        return profile["owner"]
    chosen = str(ViewerPrefs().portefeuille)
    return chosen if chosen in OWNERS else None


def sign_out() -> None:
    """Déconnecte et ramène à la page de connexion.

    Ici et non dans ``features/login.py`` : la barre latérale en a
    besoin, et la faire dépendre de la PAGE de connexion faisait
    transitivement importer cette page par tous les écrans. Se
    déconnecter est de la logique d'accès, pas du contenu d'écran.

    ``disconnect`` fait tourner l'identifiant de session en plus
    d'effacer le cookie : tout ce qui était attaché à la session
    précédente — un brouillon d'import, un filtre — repart à zéro, ce
    qui est le comportement attendu quand on quitte un compte sur un
    poste partagé.
    """
    auth.logout()
    redirect(LOGIN_PATH)


def portfolio_options() -> list[tuple[str, str]]:
    """Les choix du sélecteur de la direction. ``""`` = tous."""
    return [("", "Tous les portefeuilles"), *((o, o) for o in OWNERS)]


def set_portfolio(prefs: ViewerPrefs) -> None:
    """Le directeur change de portefeuille ; ``deps=`` re-render les zones.

    ⚠️ Le corps est vide **et c'est le mécanisme** : le socle a déjà
    hydraté ``prefs.portefeuille`` avant d'appeler le handler, et la
    mutation seule déclenche le re-render des zones qui déclarent
    ``deps=[ViewerPrefs]``. Écrire quoi que ce soit ici serait redondant.
    """


feature = Feature(
    name="access",
    kind="logic",
    provides=[ViewerPrefs, current_profile, is_director, visible_owner,
              portfolio_options, set_portfolio, sign_out],
    uses=["auth_data"],
)
