"""features/search_data — data : la recherche globale, trois tables en une.

Sert l'écran 8. Chaque table est interrogée séparément puis plafonnée : un
``UNION`` sur trois schémas différents demanderait de les aplatir en colonnes
communes, et le résultat ne saurait plus dire ce qu'il montre.

**Le préfixe, pas la sous-chaîne.** Une recherche globale se tape lettre par
lettre : ``LIKE '%mot%'`` interdit tout index et scanne 170 000 lignes à
chaque frappe. ``LIKE 'mot%'`` peut être une plage d'index. Ce que ça coûte
est réel et assumé : « genève » ne trouve plus « Bordeaux-Genève ». Une
recherche par sous-chaîne à ces volumes demande un index FTS, pas un
``LIKE``.

⚠️ **« Peut être », pas « est »** — et la nuance vaut un facteur 20. SQLite
n'applique l'optimisation que si l'index a la MÊME collation que ``LIKE``,
qui est insensible à la casse par défaut. Avec les seuls index binaires, les
trois requêtes ci-dessous planifiaient un ``SCAN`` : 898 ms par frappe sur
les contacts. Les index ``COLLATE NOCASE`` de ``core/db.py`` sont ce qui
rend la phrase vraie — 43,7 ms. Écrire « c'est une plage d'index » sans
regarder ``EXPLAIN QUERY PLAN`` était une croyance, pas une mesure.
"""

from __future__ import annotations

from bretzel import Feature
from examples.crm.core.db import owner_scope, query

#: Un plafond par famille. Une recherche globale montre les meilleurs, pas
#: tous — et trois listes de dix tiennent dans un écran, trois listes de cent
#: sont une pagination déguisée.
PER_KIND = 8


def search_accounts(needle: str, owner: str | None,
                    limit: int = PER_KIND) -> list[dict]:
    scope, scope_params = owner_scope(owner, " AND owner = ?")
    return query(
        "SELECT id, name, city, industry, arr FROM accounts "
        f"WHERE name LIKE ?{scope} ORDER BY name LIMIT ?",
        (f"{needle}%", *scope_params, limit),
    )


#: Une lecture de contact, sans son ``WHERE``. Les deux branches de
#: :func:`search_contacts_by_name` doivent projeter EXACTEMENT les mêmes
#: colonnes — un ``UNION`` qui diverge d'une colonne lève à l'exécution,
#: et seulement quand quelqu'un cherche.
_CONTACT_SELECT = (
    "SELECT c.id, c.first_name, c.last_name, c.email, c.status, "
    "a.name AS account_name FROM contacts c "
    "JOIN accounts a ON a.id = c.account_id "
)


def search_contacts_by_name(needle: str, owner: str | None,
                            limit: int = PER_KIND) -> list[dict]:
    """Nom de famille OU email — les deux clés par lesquelles on cherche
    quelqu'un, et les deux qui ont un index utilisable en préfixe.

    ⚠️ **Un ``UNION`` de deux lectures, pas un ``OR``.** SQLite sait
    servir ``last_name LIKE 'x%' OR email LIKE 'x%'`` par un
    ``MULTI-INDEX OR`` — mais il ne sait PAS combiner ce plan avec un
    prédicat d'égalité sur ``owner``. Cadré, le ``OR`` retombait en scan :
    **93,7 ms**. Deux lectures cadrées réunies, chacune sur son index
    ``(owner, colonne COLLATE NOCASE)`` : **6,1 ms**.

    ⚠️ Le ``LIMIT`` est posé DEUX fois par branche et une fois sur
    l'union : sans les internes, chaque branche rendrait tout avant qu'on
    en jette ; sans l'externe, l'union en rendrait deux fois trop.
    """
    scope, scope_params = owner_scope(owner, " AND c.owner = ?")
    pattern = f"{needle}%"
    return query(
        f"SELECT * FROM ({_CONTACT_SELECT}"
        f"  WHERE c.last_name LIKE ?{scope}"
        f"  ORDER BY c.last_name, c.first_name LIMIT ?) "
        f"UNION "
        f"SELECT * FROM ({_CONTACT_SELECT}"
        f"  WHERE c.email LIKE ?{scope}"
        f"  ORDER BY c.email LIMIT ?) "
        f"ORDER BY last_name, first_name LIMIT ?",
        (pattern, *scope_params, limit,
         pattern, *scope_params, limit, limit),
    )


def search_deals(needle: str, owner: str | None,
                 limit: int = PER_KIND) -> list[dict]:
    """Les affaires, par le nom de LEUR COMPTE.

    Une affaire s'appelle « Renouvellement annuel » chez tout le monde : la
    chercher par son propre nom rendrait douze lignes indiscernables.
    """
    scope, scope_params = owner_scope(owner, " AND a.owner = ?")
    return query(
        "SELECT d.id, d.name, d.stage, d.amount, d.close_date, "
        "a.name AS account_name, a.id AS account_id FROM deals d "
        "JOIN accounts a ON a.id = d.account_id "
        f"WHERE a.name LIKE ?{scope} ORDER BY d.close_date DESC LIMIT ?",
        (f"{needle}%", *scope_params, limit),
    )


def search_everywhere(needle: str,
                      owner: str | None) -> dict[str, list[dict]]:
    """Les trois familles d'un coup. Vide en dessous de deux caractères.

    Le plancher n'est pas cosmétique : à une lettre, chaque famille rend son
    plafond et le classement ne veut rien dire.
    """
    needle = needle.strip()
    if len(needle) < 2:
        return {"comptes": [], "contacts": [], "affaires": []}
    return {
        "comptes": search_accounts(needle, owner),
        "contacts": search_contacts_by_name(needle, owner),
        "affaires": search_deals(needle, owner),
    }


feature = Feature(
    name="search_data",
    kind="data",
    # ``PER_KIND`` n'est PAS déclaré : un ``provides`` classe ses entrées
    # par ``__name__``, qu'un ``int`` n'a pas — la carte de l'app affichait
    # un nœud nommé « int », et la garde d'import se réduisait à l'identité
    # du petit entier interné par CPython.
    provides=[search_everywhere],
    uses=["db"],
)
