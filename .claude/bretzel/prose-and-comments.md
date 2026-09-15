# Écrire de la prose dans le code

> Comment commenter dans `bretzel/` : quoi écrire, où, et **comment nommer
> le code pour qu'une gate puisse relire ce que tu affirmes**.

`bretzel/` porte **40,8 % de prose** — 17,7 % de commentaires `#` et 23,1 %
de docstrings sur 59 921 lignes (mesuré le 2026-08-16). Ce n'est pas trop
en soi. Le problème est qu'une affirmation fausse y est **indiscernable**
d'une affirmation vraie : l'audit croisé du 2026-08-01 a confronté ~695
affirmations de la doc au code et en a trouvé **214 fausses**, soit une sur
trois dans les zones non gatées.

Ce fichier dit comment écrire pour que ça n'arrive plus, et surtout pour que
la partie mécanisable **soit** mécanisée.

---

## 1. Les trois tiers

Le prédicteur de pourriture n'est ni la longueur ni le sujet : c'est la
**localité**. Une affirmation sur le code sous tes yeux est relue chaque
fois que tu édites ces lignes. Une affirmation sur une autre couche n'est
relue par personne.

| Tier | Quoi | Où | Vérifiable par |
|---|---|---|---|
| **A — contrat** | ce que la fonction garantit, ce que l'appelant doit respecter, ce qu'elle lève | docstring | la signature + le corps, sous les yeux |
| **B — pourquoi local** | pourquoi *cette* ligne est bizarre, quelle alternative a été écartée | `#` juste au-dessus | les ~10 lignes en dessous |
| **C — affirmation non locale** | mécanisme d'une autre couche, compte (« 23 composants… »), historique, mesure | **nulle part tel quel** | rien |

Le tier A est le plus précieux et le plus souvent sacrifié. Exemple réel,
[`registry.py`](../../bretzel/state/registry.py) — `diff_and_notify` :

> « Call end-of-action, BEFORE the refresh drain, so the change reaches the
> current response's re-render. »

Cette phrase ne se dérive de rien. La supprimer coûte plus cher que toute
la pourriture qu'on essaie d'éviter. **Une norme qui la couperait est une
mauvaise norme.**

Le tier C a deux sorties, jamais trois : il **devient une gate**
(`tests/consistency/`), ou il **monte dans ce dossier**. Sinon il est
supprimé. « Je le laisse, ça peut servir » est le mécanisme exact par lequel
on obtient une affirmation fausse sur trois.

---

## 2. La convention de citation : le rôle est un consentement

C'est la règle opératoire du fichier, et elle est **gatée**
(`tests/consistency/test_cited_symbols_resolve.py`).

- **Un symbole Python de ce paquet se cite avec un rôle Sphinx** —
  `` :class:`Component` ``, `` :func:`escape_attr` ``,
  `` :meth:`State.commit` ``, `` :mod:`bretzel.render.pipeline` ``,
  `` :attr:`IS_CONTAINER` ``.
- **Tout le reste garde le double-backtick** — les valeurs (`` ``fixed`` ``,
  `` ``soft`` ``), les identifiants JS du runtime (`` ``_serverSync`` ``),
  les attributs (`` ``bz-show`` ``), les noms de slots, les mots.

Écrire un rôle, c'est **accepter d'être relu**. La gate vérifie que la
cible existe ; si elle n'existe pas, tu es rouge au prochain run.

### Pourquoi pas simplement `` ``X`` `` partout

Parce que c'est mesuré et que ça ne marche pas. Sur les 11 882 citations
`` ``X`` `` du paquet, exiger un symbole Python produirait **1 560 faux
positifs** : 34 % sont des identifiants JS, 34 % sont des *valeurs* et non
des symboles, 17 % des noms de slots ou du DOM. Aucune heuristique ne les
sépare — la distinction est dans l'intention, pas dans la forme.

Et desserrer ne sauve rien : une résolution par sous-chaîne ramène le résidu
à 0,3 % mais ne mord plus que sur 24,5 % des citations. C'est-à-dire une
gate décorative — la pathologie que
`tests/consistency/test_prohibition_gates_declare_a_floor.py` documente
précisément comme celle qu'aucune vérification structurelle n'attrape.

Le rôle résout ça en déplaçant la décision vers l'auteur, là où
l'information existe.

---

## 3. Ce que la gate attrape — et ce qu'elle n'attrape pas

**Elle attrape** : le renommage, la suppression, le symbole qui n'a jamais
existé, et le mauvais genre de rôle sur un symbole local (`:class:` posé sur
une méthode).

Sept fautes le jour de sa livraison, dont
`` :func:`_render_with_layouts` `` dans `bretzel/render/pipeline.py` — un
nom qui **n'a jamais existé dans tout l'historique git**, inventé en
écrivant la docstring trois jours plus tôt.

**Elle n'attrape pas :**

1. La **justesse de la phrase**. Un paragraphe de mécanisme devenu faux dont
   tous les symboles vivent encore reste invisible. C'est la limite
   structurelle : seule la classe renommage/suppression est mécanisable.
2. Le **genre** d'un symbole importé ou builtin — on ne le connaît pas sans
   importer, et importer pour vérifier de la prose coûterait plus que ça ne
   rapporte.
3. Le sens inverse : un symbole cité en `` ``X`` `` qui aurait mérité un
   rôle. Par construction (cf. les 1 560 faux positifs). C'est le **ratchet**
   qui porte la migration, pas une interdiction.
4. Les fichiers `.md` de ce dossier — la gate ne balaie que `bretzel/**/*.py`.
   Les chemins qu'ils citent sont gardés séparément par
   `tests/consistency/test_documented_paths_exist.py`.

---

## 4. Le ratchet

766 citations à rôle sur 228 fichiers au 2026-08-16. Le compteur **monte**
au fil des touches : quand tu édites une docstring qui cite un symbole en
`` ``X`` ``, passe-la en rôle. Pas de big-bang, pas de diff de 360 fichiers.

Une **baisse** est possible mais doit être une décision écrite dans le
commit — pas un ajustement silencieux du seuil. Précédent : 767 → 766 le
jour de la livraison, parce qu'une citation désignait un module jamais
écrit et qu'aucun rôle ne pouvait la rendre vraie.

---

## 5. Formes à ne pas écrire

Ces quatre-là sont vraies au moment où tu les tapes et fausses trois mois
plus tard, sans aucun signal :

| Forme | Pourquoi | À la place |
|---|---|---|
| « 23 composants font X » | faux au 24ᵉ | **le marqueur `count:` ci-dessous**, ou rien |
| « 44 % de sa zone » | mesure figée | le commit porte la mesure |
| « avant, ça valait Y » | l'ancêtre s'efface | `git log -S` le retrouve |
| « pas encore livré » | livré un jour, la phrase reste | l'inventaire gaté |

Les deux dernières sont les plus coûteuses parce qu'elles sont les plus
crédibles. Une docstring qui annonce « pas encore livré » ce qui l'est
depuis six mois envoie le lecteur écrire ce qui existe déjà.

**Les nombres appartiennent au message de commit**, qui est daté et
immuable, pas à la prose du code, qui prétend décrire le présent.

### Sauf ceux qu'une gate sait recompter

Livré le 2026-09-04. La première ligne du tableau disait « une gate qui
compte, ou rien » — la gate existe maintenant, et elle change la règle
pour la classe qu'elle couvre :
`tests/consistency/test_declared_counts_are_true.py`.

Écris le nombre, puis **le marqueur** :

```markdown
⚠️ **36 noms de groupes de premier niveau** <!--count:NOM_DU_COMPTEUR-->
```

```python
#: — les chaînes de classes Tailwind des 101 composants — n'y  count:NOM_DU_COMPTEUR
```

Le marqueur nomme un compteur de `COUNTERS`, qui le **calcule** à chaque
run ; le nombre relu est le dernier entier écrit à sa gauche, sur la même
ligne. En markdown c'est un commentaire HTML, donc invisible au rendu.

*(Le nom est en MAJUSCULES dans ces deux exemples pour une raison qui se
généralise : la gate balaie ce fichier comme les autres, et un marqueur
en minuscules ferait de l'exemple une affirmation — rouge le jour où le
catalogue bouge, pour une phrase qui n'affirmait rien. Un exemple
d'écriture ne doit jamais être une écriture.)*

C'est la même mécanique que le § 2 : **le marqueur est le consentement à
être relu.** Un nombre nu reste interdit — la gate ne le voit pas, et
c'est voulu : les populations FILTRÉES (« 53 composants sur 101 »,
« 8 composants, tous pour `icon` ») ne se recalculent pas, et les
auto-détecter produirait une gate qui rougit pour rien.

**Ce que ça retourne.** Un compte marqué n'est plus la forme la plus
pourrissable de la prose, c'est la plus sûre : il se corrige au lieu de
mentir. Sept des neuf premiers marqués étaient faux le jour de la
livraison — dont « les 13 directives `bz-*` », écrit quatre fois dans le
funnel, alors que `bz-init` en avait fait 14.

**Hors périmètre, et pourquoi** : `.claude/work/` (des rapports datés —
une mesure datée reste vraie, cf. § 6). La surface d'API n'est pas recopiée :
`bretzel describe` la dérive du code à la demande.

Ajouter un compteur : une entrée dans `COUNTERS` qui le calcule depuis le
code. Un compteur que plus aucune prose n'utilise est refusé — une table
de compteurs pourrit comme une allowlist.

---

## 6. La langue : bilingue par strates, et on ne retraduit pas

**Écris en français.** C'est la langue du dépôt depuis juillet 2026, celle
des messages de commit et de tout `.claude/`.

**Ne retraduis pas l'anglais existant.** Décidé le 2026-08-26, après mesure.
Sur les 1 033 docstrings de `bretzel/`, 41 % sont en anglais et 26 % en
français — mais la répartition n'est pas aléatoire, elle est *datée* : elle
suit le mois de création du fichier.

Relevé du 2026-08-26 — c'est une **mesure datée**, pas un compte à tenir à
jour (cf. § 5) : elle restera vraie ce jour-là même quand les chiffres
auront bougé, et c'est la *forme* de la courbe qui porte la décision.

| fichiers nés en | fr | en | part fr |
|---|---|---|---|
| 2026-05 | 84 | 260 | 24 % |
| 2026-06 | 9 | 85 | 10 % |
| 2026-07 | 31 | 21 | 60 % |
| 2026-08 | 113 | 31 | 78 % |

Ce n'est donc pas du désordre, c'est une **couture** — et 42 fichiers la
portent en interne, parce qu'ils ont été édités des deux côtés.

Pourquoi on ne la recoud pas : une retraduction touche des centaines de
docstrings sans changer une ligne de code. Elle produit un diff que
personne ne peut relire, elle détruit le `git blame` de la prose — qui est
ici de la mémoire institutionnelle datée, souvent la source la plus fiable
sur une décision — et elle risque d'introduire exactement ce que ce fichier
existe pour empêcher : une affirmation fausse, indiscernable d'une vraie.
Le bénéfice serait cosmétique ; le coût, une classe entière de dérive.

**Corollaire pour un fichier bilingue** : tu écris en français dans un
fichier majoritairement anglais, et c'est normal. Ne « harmonise » pas la
docstring voisine en passant — c'est une retraduction déguisée, à ceci près
qu'elle arrive non annoncée, dans un commit qui parle d'autre chose.

---

## 7. En pratique, quand tu édites un fichier

1. La docstring dit-elle ce que l'appelant doit **garantir** ? Sinon,
   ajoute-le — c'est le tier A, ce qui manque le plus.
2. Les `#` que tu ajoutes portent-ils sur les lignes juste en dessous ?
   Sinon, ils sont tier C : gate, ou ce dossier, ou rien.
3. Les symboles Python que tu nommes sont-ils en rôle ? Le ratchet compte
   sur toi ; la gate te dira si tu t'es trompé de nom ou de genre.
4. Tu as écrit un nombre ? Vérifie qu'il ne périmera pas seul.

```bash
py -m pytest tests/consistency/test_cited_symbols_resolve.py -q
```
