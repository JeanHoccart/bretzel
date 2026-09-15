# Jeux d'essai pour l'écran « Importer »

Deux fichiers, vérifiés contre le vrai analyseur (`parse_csv`) et le vrai
juge (`judge`) du CRM, **connecté en commercial** — le cas par défaut.

⚠️ Les deux sont écrits pour **Aïcha Benali** (`a.benali`). Si tu te
connectes avec un autre commercial, remplace la colonne `owner` par ton
nom : le cadrage **refuse** une ligne qui n'est pas à toi au lieu de
réécrire son propriétaire, et l'import est tout-ou-rien — donc une seule
ligne au mauvais nom bloque le fichier entier. Un directeur qui n'a
choisi aucun portefeuille, lui, voit tout passer.

## `comptes-valides.csv` — 10 lignes, 0 refus

S'importe en entier.

## `comptes-a-corriger.csv` — 9 lignes, 8 refus

Un refus par cause, pour voir l'écran de vérification faire son travail :

| ligne | ce qu'elle teste |
|---|---|
| Maison Kieffer | (bonne — le témoin) |
| *(nom vide)* | nom manquant |
| Transports Weber | secteur inconnu (« Transport » n'est pas « Logistique ») |
| Atlas Marine | pays hors des quatre acceptés |
| Studio Mirabel | taille inconnue (« Startup ») |
| Groupe Sanchez | propriétaire inconnu |
| Ateliers Lorrains | ARR avec des espaces — `1 250 000` |
| Ferme du Ried | ARR vide |
| Cabinet Aubert | propriétaire connu mais **hors portefeuille** |

Le témoin est là pour qu'on voie que le refus est ciblé et pas global.

## Le vocabulaire accepté

De `examples/crm/core/domain.py` et `import_data.py` :

- **secteur** : Industrie, Santé, Finance, Logistique, Distribution,
  Énergie, Éducation, Bâtiment, Média, Agroalimentaire
- **pays** : France, Belgique, Suisse, Canada
- **taille** : TPE, PME, ETI, Grand compte
- **propriétaire** : Aïcha Benali, Marc Dubois, Sofia Rossi, Léa Martin,
  Tom Nguyen, Clara Weiss
- **arr** : des chiffres, rien d'autre — pas de séparateur, pas de devise
