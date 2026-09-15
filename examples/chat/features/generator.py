"""chat/generator — la source de tokens, simulée.

**Aucun appel LLM.** Cet exemple démontre un TRANSPORT, pas une
intégration : brancher un vrai modèle demanderait une clé d'API, ferait
dépendre la démo d'un réseau et d'un budget, et ne changerait pas d'un
octet ce qu'on cherche à montrer — comment un texte qui grandit côté
serveur atteint le navigateur. Le jour où on branche un vrai modèle, seul
:func:`answer_for` change ; tout le reste de l'app est déjà correct.

Débit **par mots** et non par caractères : c'est ce que fait un vrai
tokenizer à la louche, et ça donne des morceaux d'une taille réaliste
(4-6 octets), donc un nombre de ticks réaliste — ce qui compte, puisque
la mesure est le but de cet exemple.
"""

from __future__ import annotations

#: Réponses canned, choisies par un mot-clé du prompt. Un ``dict`` plutôt
#: qu'un ``if`` en cascade : ajouter un cas est une ligne.
_ANSWERS: dict[str, str] = {
    "bretzel": (
        "Bretzel rend le HTML côté serveur et laisse un petit runtime "
        "client appliquer les changements. L'état est typé, réparti en "
        "quatre portées serveur et une portée client. Une mutation "
        "d'état re-rend les sous-arbres qui en dépendent, sans qu'on ait "
        "à le demander. Il n'y a aucune dépendance Node en production : "
        "le CSS est compilé par un binaire, et le runtime est un fichier "
        "JavaScript unique servi tel quel."
    ),
    "stream": (
        "Le texte que tu lis arrive par tranches. À chaque tranche, le "
        "serveur réassigne la valeur complète d'un champ d'état client, "
        "qui redescend dans un patch JSON. Le navigateur écrit alors "
        "directement dans un nœud de texte : pas de HTML analysé, pas de "
        "morphing d'arbre, une seule affectation. C'est pour ça que ça ne "
        "scintille pas."
    ),
}

_DEFAULT = (
    "Je n'ai pas de modèle derrière moi — je suis un générateur simulé, "
    "et c'est volontaire. Cet exemple montre comment un texte produit "
    "progressivement par le serveur atteint ton écran, pas comment on "
    "appelle une API. Essaie les mots « bretzel » ou « stream » pour une "
    "réponse plus longue."
)


def answer_for(prompt: str) -> str:
    """La réponse complète à débiter pour ``prompt``.

    Le SEUL point à remplacer par un vrai appel de modèle.
    """
    lowered = prompt.lower()
    for keyword, answer in _ANSWERS.items():
        if keyword in lowered:
            return answer
    return _DEFAULT


#: Mots publiés par tranche. **Le réglage le plus important de cet
#: exemple**, et c'est un choix d'APPLICATION, pas une limite du framework.
#:
#: Le coût total descendu suit ``n · (k+1) / 2`` — ``n`` la taille finale,
#: ``k`` le nombre de tranches. Modèle vérifié : à ``n=337`` et ``k=57`` il
#: prédit 9 773 octets, la mesure en donne 9 754 (0,2 % d'écart).
#:
#: Donc ``k`` divise le coût ET le nombre de requêtes, **linéairement**.
#: Extrapolé à une réponse de 2 000 tokens (~8 000 octets) :
#:
#: ===============  ==========  ===========
#: mots / tranche     requêtes    descendu
#: ===============  ==========  ===========
#: 1                       400     1 566 Ko
#: 5                        80       316 Ko
#: 20                       20        82 Ko
#: 50                        8        35 Ko
#: ===============  ==========  ===========
#:
#: **3 et non 1**, alors que 1 rend le phénomène plus spectaculaire : un
#: exemple sert de patron autant que de démonstration, et livrer le pire
#: cas par défaut apprendrait le mauvais réflexe. 1 reste à un caractère
#: d'ici pour qui veut voir la courbe s'emballer.
#:
#: ⚠️ Le compromis est RÉEL et il est de goût, pas de technique : des
#: tranches plus grosses arrivent par à-coups visibles là où un mot à la
#: fois donne l'effet « machine à écrire ». Si cet effet compte, la sortie
#: n'est pas de baisser ce nombre — c'est de dissocier la cadence de
#: TRANSPORT de la cadence d'AFFICHAGE : récupérer 20 mots d'un coup et
#: les révéler progressivement côté client. C'est ce que font plusieurs
#: UI de chat réelles, et ça ne demande rien au serveur.
CHUNK_WORDS = 3


def advance(full: str, cursor: int, words: int = CHUNK_WORDS) -> int:
    """Le curseur après ``words`` mot(s) de plus, borné à ``len(full)``.

    Fonction pure : elle ne connaît ni l'état ni la requête, donc elle se
    teste sans monter quoi que ce soit. Le curseur est une position dans
    la chaîne (et non un index de mot) pour que la tranche publiée soit
    un simple ``full[:cursor]``.
    """
    for _ in range(max(1, words)):
        if cursor >= len(full):
            return len(full)
        # Sauter l'espace éventuel, puis le mot, et s'arrêter APRÈS lui :
        # la tranche publiée se termine toujours sur un mot entier.
        nxt = full.find(" ", cursor + 1)
        if nxt == -1:
            return len(full)
        cursor = nxt
    return cursor
