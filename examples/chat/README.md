# Chat — le streaming serveur → navigateur, et ce qu'il coûte

```bash
py -m examples.chat.main
```

Un texte qui se remplit progressivement est le cas qui **oblige à choisir**
entre les deux façons qu'a Bretzel de changer le DOM. Cet exemple les met
côte à côte sur une seule page.

## Les deux moitiés, et pourquoi elles ne se recouvrent pas

| ce qui change | mécanisme | dans cet exemple |
|---|---|---|
| **Structure** — un nœud apparaît | `@refreshable` → re-rendu + morph | le journal des messages (`message_log`) |
| **Valeur** — un nœud déjà lié change | `ClientState` → patch → signal | la bulle en cours (`streaming_bubble`) |

Ce ne sont pas deux solutions au même problème. Un message **de plus** est
une structure : seul un re-rendu serveur peut le faire apparaître. Le
**texte** de ce message qui grandit est une valeur : le serveur réassigne
un champ, il redescend dans un patch JSON, et le navigateur écrit dans un
nœud de texte — aucun HTML analysé, aucun morphing.

## Deux états, deux directions

C'est le découpage qui porte tout le reste :

```python
class Draft(ClientState, send_to_server=False):   # serveur → client
    answer: str = ""          # le texte affiché pendant la génération
    streaming: bool = False   # le gate du ui.interval

class Prompt(ClientState):                        # client → serveur
    text: str = ""            # ce que l'utilisateur tape
```

`Draft` ne remonte **jamais** : sans ce réglage, le texte en cours
d'écriture repartirait vers le serveur à chaque tick, pour des données que
le client vient de recevoir. Le corollaire surprend et se lit dans
`logic.py` : `Draft().answer` vaut `""` dans un handler, donc on
**réassigne** `full[:cursor]` au lieu d'accumuler avec `+=`.

`Prompt` remonte, parce que sa valeur naît dans le navigateur. Le socle
refuse d'ailleurs de lier une prop two-way (`ui.input(value=…)`) à un état
descendant-seul — la faute est attrapée à la construction, pas découverte
en production.

## La cadence est tirée par le client, et c'est le point

```python
ui.interval(on_tick=pull_chunk, seconds=0.12, active=Draft().streaming)
```

`active=` est un `ClientBinding` : le serveur le bascule à `False` et le
timer s'arrête **au même instant**. C'est ce qui rend le bouton *Stop*
honnête.

Une boucle serveur (`@app.background`) ne saurait pas faire : elle est
sans contexte de requête, donc incapable de relire l'état qui lui dirait
de s'arrêter. Elle continuerait à produire des requêtes après le clic.
C'est écrit dans `.claude/bretzel/handlers.md` § *background*, et le
stepper du playground a fait ce chemin en sens inverse pour la même
raison.

## Ce que ça coûte — mesuré, puis modélisé

Chaque tick renvoie la tranche **entière**, pas le delta. Le total
descendu suit donc :

```
total = n · (k + 1) / 2        n = taille finale, k = nombre de tranches
```

Modèle **validé contre le navigateur** : à `n = 337` et `k = 57`, il
prédit 9 773 octets et `tests/runtime_js/test_chat_example_streams.py` en
mesure 9 754 — 0,2 % d'écart. Une simulation hors navigateur de la même
boucle retombe sur le chiffre exact.

Ce qui compte, c'est que **`k` est un choix d'application**, pas une
limite du framework. Il divise le coût ET le nombre de requêtes,
linéairement. Extrapolé à une réponse de 2 000 tokens (~8 Ko) :

| mots / tranche | requêtes | descendu |
|---:|---:|---:|
| 1 | 400 | 1 566 Ko |
| 3 *(défaut ici)* | 133 | 525 Ko |
| 5 | 80 | 316 Ko |
| 20 | 20 | **82 Ko** |
| 50 | 8 | 35 Ko |

**Conclusion, et elle est négative** : à une taille de tranche
raisonnable, le transport actuel suffit. 20 requêtes et 82 Ko pour une
réponse complète ne justifient pas de faire porter au canal SSE un patch
d'ajout, ni d'inventer un mécanisme de plus. Le coût spectaculaire du
premier relevé venait d'un réglage de l'exemple, pas du framework.

Le chantier redeviendrait justifié à **une condition précise** : vouloir
l'effet « machine à écrire » mot à mot ET une réponse longue — c'est-à-dire
`k` grand par exigence de UX. Mais même là, la bonne réponse est
probablement de dissocier la cadence de transport de la cadence
d'affichage (récupérer par blocs, révéler progressivement côté client)
plutôt que d'ajouter un canal.

Le panneau de mesure de la page affiche tout ça en direct, sans le
maquiller : un exemple qui cache le coût de ce qu'il démontre n'apprend
rien.

## Le générateur est simulé

Aucun appel LLM, aucune clé d'API. Le sujet est le **transport** ; brancher
un vrai modèle ne changerait que `features/generator.py` § `answer_for`, et
ne dirait rien de plus sur ce que cet exemple démontre.

## Détail qui n'en est pas un

Pendant la génération, la bulle affiche du **texte brut** ; à la
validation, le message passe par `ui.markdown`. `ui.markdown` refuse un
`ClientBinding` au constructeur — un chemin de binding réduirait toute la
structure (titres, listes, code) à du texte plat et mentirait en silence.
La plupart des UI de chat font pareil, pour une raison voisine : un
markdown à moitié écrit n'est pas du markdown valide.
