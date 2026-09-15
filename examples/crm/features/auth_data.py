"""features/auth_data — data : la table des comptes utilisateurs.

Le framework ne modélise pas d'utilisateur au-delà de son identifiant :
``bretzel.auth`` retient « telle requête appartient à X » dans un cookie
signé, et expose quatre fonctions pour l'écrire et le relire. **Le profil,
le rôle et le mot de passe sont à l'app** — c'est écrit dans le module.

Cette feature est donc la moitié que le CRM apporte, côté données. Le
hachage vit dans ``core/security.py`` (bibliothèque standard, PBKDF2), et
la décision « qui voit quoi » vit dans ``access.py`` — trois choses
distinctes, trois endroits.
"""

from __future__ import annotations

from bretzel import Feature

from examples.crm.core.db import query
from examples.crm.core.security import verify_password


def find_by_login(login: str) -> dict | None:
    """Un compte par son login, ou ``None``.

    ``COLLATE NOCASE`` : un login se tape, et refuser « A.Benali » parce
    qu'on a saisi une majuscule est une frustration sans contrepartie —
    l'unicité est déjà garantie par la contrainte de colonne.
    """
    rows = query(
        "SELECT * FROM users WHERE login = ? COLLATE NOCASE", (login.strip(),)
    )
    return rows[0] if rows else None


def all_users() -> list[dict]:
    """Les comptes, pour la liste de démonstration de la connexion.

    Lue en BASE plutôt que refabriquée depuis ``OWNERS`` : la page de
    connexion la reconstruisait à la main, donc ajouter un compte au semis
    la faisait mentir en silence. ``role`` d'abord : « commercial » trie
    avant « directeur ».
    """
    return query(
        "SELECT login, display_name, role FROM users ORDER BY role, login"
    )


def find_by_id(user_id: str) -> dict | None:
    """Un compte par l'identifiant que porte le cookie d'authentification.

    ``bretzel.auth`` ne transporte qu'une **chaîne** — c'est ce que dit sa
    docstring, et c'est pour ça qu'on la reconvertit ici plutôt que de
    supposer un entier ailleurs. Un cookie signé mais dont l'utilisateur a
    été supprimé rend ``None``, et l'appelant traite ça comme anonyme.
    """
    if not user_id.isdigit():
        return None
    rows = query("SELECT * FROM users WHERE id = ?", (int(user_id),))
    return rows[0] if rows else None


def authenticate(login: str, password: str) -> dict | None:
    """Le compte si les identifiants sont bons, ``None`` sinon.

    ⚠️ **Un seul message d'échec pour les deux causes**, et c'est
    volontaire : distinguer « login inconnu » de « mot de passe faux »
    donne à qui essaie la liste des comptes qui existent. L'appelant ne
    reçoit donc qu'un ``None``, et n'a pas de quoi être plus bavard.

    ⚠️ On vérifie le mot de passe **même quand le login n'existe pas** —
    contre une empreinte factice. Sinon le temps de réponse trahit
    l'existence du compte : quelques millisecondes pour un login inconnu,
    240 000 itérations de PBKDF2 pour un login connu.
    """
    user = find_by_login(login)
    stored = user["password_hash"] if user else _DUMMY_HASH
    ok = verify_password(password, stored)
    return user if ok else None


#: Une empreinte valide d'un mot de passe que personne n'a. Elle n'existe
#: que pour donner à :func:`authenticate` quelque chose à vérifier quand le
#: login est inconnu — cf. sa docstring.
_DUMMY_HASH = (
    "pbkdf2_sha256$240000$"
    "00000000000000000000000000000000$"
    "0000000000000000000000000000000000000000000000000000000000000000"
)


feature = Feature(
    name="auth_data",
    kind="data",
    provides=[find_by_login, find_by_id, all_users, authenticate],
    uses=["db"],
)
