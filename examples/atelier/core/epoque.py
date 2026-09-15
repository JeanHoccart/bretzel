"""core/epoque — logic : depuis quand une tâche compte.

Feature ``kind="logic"`` : pas d'état, pas de ressource, une question.

Pourquoi une coupure
---------------------
Décidé par l'utilisateur le 2026-09-12, devant onze tâches d'un
``examples/ecole`` qui n'existe plus : « comme la version aboutie de
describe, check, probe date de pas longtemps, les vieux sujets sont un
peu obsolètes ».

Il a raison, et c'est une question d'honnêteté de la mesure, pas de
ménage. L'atelier juge une tâche sur la RÈGLE DES QUATRE TEMPS — a-t-on
demandé la surface avant d'écrire, fait juger le contrat, vérifié en une
fois. Une tâche de juillet ne pouvait pas faire ces gestes : les
instruments n'existaient pas. La compter, c'est reprocher de ne pas
s'être servi d'un outil qui n'était pas livré.

Le jalon
---------
Le 10 septembre 2026, jour où ``bretzel probe`` a été livré. C'est le
DERNIER des trois instruments : ``describe`` et ``check`` sont du 16
août, donc c'est à cette date seulement que la règle devient jugeable en
entier.

⚠️ Rien n'est supprimé. L'aspiration lit toujours tous les transcripts,
et une suppression de lignes ne tiendrait pas : la prochaine aspiration
les recréerait depuis leur source. C'est la LECTURE qui s'arrête au
jalon, et elle le fait par des vues SQL (``core/db.VUES``) plutôt que par
une clause recopiée dans chaque requête — il y en a vingt-six, donc
vingt-six occasions d'oublier.
"""

from __future__ import annotations

from bretzel import Feature

#: La date à partir de laquelle une tâche est jugeable, en ISO — comparée
#: telle quelle à ``taches.debut``, qui est un horodatage ISO. La
#: comparaison de chaînes suffit et c'est voulu : même format, même ordre.
JALON = "2026-09-10"

#: Le jalon en toutes lettres, pour l'écran. Il DOIT être affiché : une
#: app qui montre 67 tâches sur 1 525 sans dire pourquoi ment par
#: omission.
LIBELLE = "depuis le 10 septembre 2026"

#: Ce que le jalon marque. Sur l'écran aussi — un repère sans sa raison
#: se lit comme un caprice.
POURQUOI = (
    "le jour où `bretzel probe` a été livré, le dernier des trois "
    "instruments que la règle suppose"
)


def est_jugeable(debut: str | None) -> bool:
    """Cette tâche s'est-elle faite avec l'outillage complet ?

    La porte Python de la même règle que les vues SQL. Elle sert au
    test, et à tout appelant qui tient déjà la ligne en main plutôt
    qu'une requête.
    """
    return bool(debut) and str(debut) >= JALON


feature = Feature(
    name="epoque",
    kind="logic",
    provides=[est_jugeable],
)
