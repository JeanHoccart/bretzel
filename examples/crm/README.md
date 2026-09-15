# `examples/crm/` — l'instrument d'usage réel

**Les quatre tranches sont livrées** : le socle de données, la coque
responsive et les douze écrans (2026-08-19), puis les comptes et
l'authentification (2026-08-20). Le brief, la règle et le journal des
findings vivent dans
[`.claude/work/chantier-crm-2026-08-19.md`](../../.claude/work/chantier-crm-2026-08-19.md).

Ce n'est pas une 18ᵉ démo. Les 17 apps d'`examples/` sont des écrans isolés —
`contacts` (326 lignes), `kanban` (228), `dashboard` (222) sont déjà des
morceaux de CRM, mais aucune n'a de navigation, d'état partagé entre écrans,
ni de sélection.

La règle qui la distingue : **interdiction de se dépanner**. Un `classes=`
posé pour rattraper un composant est une mesure perdue — il se NOTE dans le
journal du chantier, il ne se pose pas. Les quatre tranches en ont produit
**vingt-trois**, pour une seule classe de rattrapage assumée (la hauteur du
`ui.resizable`).

## Lancer

```
py -m examples.crm.main        # port 8016
```

Le premier démarrage sème **262 000 lignes** dans `core/crm.db` (~4 s, 33 Mo,
gitignoré). Les suivants ne resèment pas : le marqueur `SEED_VERSION` de
`core/db.py` décide. Bumpe-le pour reconstruire.

## Se connecter

Tout est fermé sauf `/connexion` : la garde est un **middleware en
défaut-fermé**, pas un `@page(auth=…)` — une page ajoutée demain est
protégée sans que personne y pense.

| login | rôle | ce qu'il voit |
|---|---|---|
| `a.benali`, `m.dubois`, `s.rossi`, `l.martin`, `t.nguyen`, `c.weiss` | commercial | **son seul portefeuille**, sur les douze écrans. Une fiche hors portefeuille rend **404**, pas 403 : dire « interdit » confirmerait qu'elle existe |
| `direction` | direction | tout, ou le portefeuille choisi dans le sélecteur de la barre latérale |

Mot de passe unique : **`bretzel`**. Les hachages sont du PBKDF2-HMAC-SHA256
de la stdlib (240 000 tours) — l'app apporte sa vraie auth, le framework ne
fournit que `bretzel.auth` (quatre fonctions) et la segmentation d'état.

**Le cadrage est un PARAMÈTRE**, pas une variable globale que les repos
iraient lire : chaque fonction de lecture prend son `owner: str | None` et
le pose dans son `WHERE`. C'est plus verbeux, et c'est le point — on peut
RELIRE une signature et voir si elle est cadrée. `features/access.py` est
l'unique porte : `visible_owner()`.

## Les écrans de la tranche 1

| route | écran | ce qu'il met sous contrainte |
|---|---|---|
| `/` | Pipeline | `dropzone` + `drag_each` dans des colonnes qui défilent, drop persisté en SQL avec rang par insertion médiane |
| `/comptes` | Comptes | `ui.datatable` en **mode callable** sur 50 000 lignes — tri, recherche, filtres et export CSV traduits en SQL |
| `/contacts` | Contacts | la **liste sélectionnable** (l'angle mort nommé) et la coque maître-détail, en `ui.resizable` |
| `/contacts/{id}` | Fiche contact | la **première page à paramètre de chemin** des 18 apps : onglets, édition en ligne, `file_upload` en colonne étroite |

## Les écrans de la tranche 2

| route | écran | ce qu'il met sous contrainte |
|---|---|---|
| `/comptes/{id}` | Fiche compte | l'**imbrication** : deux `ui.table` dans deux `ui.card` dans une `ui.grid` |
| `/activites` | Activités | `date_range_picker`, `calendar` et `date_picker` **liés à un état serveur**, dans une barre de filtres et un formulaire — pas montés seuls |
| `/rapports` | Rapports | les **cinq familles de graphiques** sur des `GROUP BY`, pas sur des listes fabriquées |
| `/recherche` | Recherche globale | le cas d'usage qui déciderait `ui.command_palette` — construit sans elle, pour mesurer ce qui manque |

## Les écrans de la tranche 3

| route | écran | ce qu'il met sous contrainte |
|---|---|---|
| `/import` | Import | `ui.stepper` + aperçu en `ui.datatable` **tier liste** — l'autre tier du composant que l'écran 2 monte en callable |
| `/parametres` | Paramètres | `ui.form` en densité : dix champs, validation serveur, `toggle_group` simple et multiple, `switch`, `select` |
| `/temps-reel` | Temps réel | **SSE** : une zone `broadcast=True` qu'un autre onglet fait bouger |
| *(le shell)* | Coque responsive | `Screen().is_mobile` : rail à onze routes ⇆ tab bar à cinq, un seul arbre dans le DOM |

## Les écrans de la tranche 4

| route | écran | ce qu'il met sous contrainte |
|---|---|---|
| `/connexion` | Connexion | `bretzel.auth` — `connect` / `disconnect` et la rotation de session, qu'**aucun des 18 exemples n'exerçait** ; la seule page sans `layout=` |
| *(le shell)* | Identité | `ui.sidebar_footer` + `ui.sidebar_footer_item`, et un `ui.select` **dans une barre latérale repliable** |
| *(le shell)* | Thème | `ColorScheme` en clair / sombre / **système** — un `ClientState` du framework lié à un `ui.toggle_group`, donc le seul réglage de l'app qui bascule sans aller-retour serveur |

## Structure

```
crm/
├── main.py                 Bretzel(...) + app.include(...) + le seed au démarrage
├── core/
│   ├── theme.py            le seul vrai global
│   ├── ui.py               la carte KPI, partagée par quatre écrans
│   ├── domain.py           le vocabulaire métier (étapes, statuts, secteurs…)
│   ├── db.py               infra : connexion, schéma, index, init_db
│   ├── security.py         le hachage PBKDF2 et sa vérification
│   └── seed.py             la fabrique déterministe des 262 000 lignes
└── features/
    ├── shell.py            le rail + l'outlet + l'identité
    ├── access.py           logic — l'UNIQUE porte de la politique d'accès
    ├── auth_data.py        data  — les comptes, et la vérification du mot de passe
    ├── login.py            page  /connexion
    ├── accounts_data.py    data — le repo comptes, dont le `rows=` callable
    ├── contacts_data.py    data — contacts, activités, notes
    ├── deals_data.py       data — le pipeline et le réordonnancement
    ├── pipeline.py         page  /
    ├── accounts.py         page  /comptes
    ├── contacts.py         page  /contacts
    ├── contact_detail.py   page  /contacts/{id}
    ├── account_detail.py   page  /comptes/{id}
    ├── activities_data.py  data — le journal d'activité
    ├── activities.py       page  /activites
    ├── reports_data.py     data — les cinq agrégats des rapports
    ├── reports.py          page  /rapports
    ├── search_data.py      data — la recherche par préfixe, trois tables
    ├── search.py           page  /recherche
    ├── import_data.py      data — lire un CSV, le juger, l'écrire
    ├── import_screen.py    page  /import
    ├── settings.py         page  /parametres
    ├── realtime.py         page  /temps-reel
    ├── app_map.py          page  /_map — la carte des features
    └── errors.py           error — 404 / 403 dans le shell
```

## Vérification

Les douze écrans ont été regardés dans un vrai Chromium avant d'être dits
livrés (discipline #3 du charter). Sur tous : zéro erreur JS, pas de double
ascenseur, pas de débordement horizontal. Et par écran, le geste qui compte —
glisser-déposer à la souris **persisté en SQL**, tri et recherche qui font
bouger le SQL, sélection sans navigation, `file_upload` qui tient dans sa
colonne étroite, sous-tables imbriquées sur un compte réel, clic dans
l'agenda qui referme la fenêtre de dates sur un jour, cinq graphiques rendus
sur des `GROUP BY`, une recherche qui répond à la frappe (une requête
débouncée, pas une par lettre), un CSV collé jugé ligne par ligne avant
écriture, un réglage booléen qui reste à `False` après enregistrement, une
tab bar à 812 px du haut sur un écran de 812 px, et — le seul qui demande
deux onglets — des compteurs qui bougent tout seuls quand l'autre onglet
glisse une carte.

**La tranche 4 a ajouté 54 mesures** : 28 sur les repos (chaque lecture
cadrée rend bien son portefeuille, et la MÊME sans cadrage en rend plus)
et 26 au navigateur — l'anonyme renvoyé sur `/connexion` depuis les douze
écrans **et** depuis `/_bretzel/sse`, `/_bretzel/refetch/…` et
`/_bretzel/datatable.csv` ; un mot de passe faux refusé sans dire laquelle
des deux causes ; aucun autre nom de propriétaire sur aucun des douze
écrans ; un `404` sur une fiche d'un autre et un `200` sur la sienne ; la
déconnexion qui referme ; et le sélecteur de la direction qui recadre les
écrans qu'il touche. Plus **14 mesures sur les écritures** (chacune des
quatre refuse hors portefeuille sans muter la ligne) et **11 sur le
thème** (la classe `.dark`, le fond recalculé, la persistance, le suivi
de l'OS dans les deux sens).

⚠️ **Et ça n'a pas suffi.** Quatre relectures adverses du même diff ont
trouvé un trou de sécurité que les 54 mesures ne pouvaient pas voir — le
cadrage manquait sur les quatre écritures, et `contact_id` arrive du
navigateur. Les deux instruments voient des choses disjointes : la
mesure exerce les chemins que l'interface propose, la relecture regarde
ceux qu'elle ne propose pas. Le journal du chantier détaille les quatre.

L'invariant central est désormais tenu par une **gate** :
`tests/consistency/test_crm_owned_reads_declare_their_scope.py` — elle
lit l'AST des `features/*_data.py` et exige qu'une fonction touchant une
table possédée déclare son cadrage, sauf liste blanche nommée.

⚠️ Un serveur de vérification ad hoc doit éviter les ports **8944–8996** :
trente-quatre d'entre eux appartiennent aux bancs de `tests/probes/`. Un serveur qui traîne sur
l'un d'eux fait rougir un probe pour rien — mesuré une fois, sur
`probe_tipiso`, qui interrogeait le CRM au lieu de son propre banc.

Le script qui a servi à ça était **jetable**, et il l'est resté. Cette app
n'a pas de probe dans `tests/probes/` : elle n'est pas du framework, elle est
l'instrument avec lequel on le mesure. Ce qu'elle produit, ce sont les
findings du chantier — pas une 54ᵉ gate à entretenir.
