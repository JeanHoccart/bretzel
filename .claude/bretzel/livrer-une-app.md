# Livrer une app — la liste de contrôle

**Ce que ce fichier n'est pas.** `creating-a-component.md` § 9 tient déjà
la vérification d'un COMPOSANT : six probes sur un banc, montés seuls.
Celle-ci porte sur une APP assemblée, et ses modes d'échec sont
différents — un composant juste dans un voisinage faux, un handler qui
répond zéro octet, une chaîne de hauteurs coupée trois étages plus haut.

**D'où elle vient.** Elle n'est pas déduite. Chaque ligne a coûté un
aller-retour avec l'utilisateur sur une capture d'écran, et porte la
faute qui la paie. Neuf défauts trouvés en montant `examples/kanban` le
2026-09-09, quatre en montant `examples/messagerie` les jours d'avant.

**Le dénominateur, et c'est lui qui donne la structure du fichier** :
aucun de ces treize défauts n'était visible pour une vérification
automatique lancée ce jour-là, et tous se voyaient à l'écran en dix
secondes. Les probes mesuraient la structure, à une taille de fenêtre,
sur des écrans immobiles. Une liste de contrôle n'est donc pas un
supplément de rigueur : c'est la liste des endroits où le vert ne veut
rien dire.

---

## A. Avant d'écrire — trois refus

**A1. Aucun contrôle fabriqué à la main.** Si ça se clique ou se pose
dans un rang de contrôles, c'est un `ui.*` avec son `size=`. Un `hstack`
avec `px-3 py-1.5 border` ressemble à un bouton et n'en a pas la hauteur.

> *Payé* : la zone « Archiver » du kanban sortait 7 px plus haut que ses
> voisins. `bretzel check` ne pouvait pas le voir — sa règle
> `mixed-sizes` compare les `size=` de la famille `inputs`, et du
> Tailwind brut n'a aucune taille à comparer. **Œil seul, par
> construction.**

**A2. Un composant de RÉGION n'est pas un contrôle.** `ui.dropzone` pose
`min-h-12` pour qu'une colonne vidée reste une cible ; `ui.pane` pose
`flex-1` ; `ui.sidebar` pose `h-screen`. Les mettre dans un rang de
32 px étire le rang entier.

> *Corollaire mesuré* : l'override d'une classe de thème a la MÊME
> spécificité que le thème, donc c'est l'ordre de la feuille qui tranche.
> `min-h-0` nu ne bouge rien, `min-h-0!` oui.

**A3. Nommer la mécanique en une phrase.** Si l'app ne peut pas le faire,
elle n'a pas sa place dans `examples/` — c'est la règle qui a retiré onze
apps le 2026-09-07.

---

## B. Pendant — les six silences

Aucun des six ne lève, ne s'affiche, ni ne se voit en revue de code.
Trois d'entre eux ressemblent trait pour trait au code correct.

**B1. Un handler de valeur sans paramètre typé n'hydrate rien.**

```python
def filtrer() -> None: ...                    # inerte, zéro octet
def filtrer(filtres: Filtres) -> None: ...    # c'est le PARAMÈTRE qui hydrate
```

> *Payé* : les trois filtres du kanban bougeaient à l'écran, le tableau
> ne bougeait pas. **Gatable** — décrit dans `work/todo.md`.

**B2. Un état mutable lu dans une coque est GELÉ.** Un `@layout` est
rendu une fois par chargement. Tout ce qui y lit un état sans être une
zone `@refreshable` ne bougera plus jamais.

> *Payé deux fois.* Dans la messagerie, un bouton gaté sur
> `visible=Filtre().q != ""` n'aurait jamais ni apparu ni disparu. Dans
> le kanban, l'avatar restait sur l'ancienne personne pendant que le
> sélecteur affichait la nouvelle — le contrôle lié se met à jour tout
> seul, donc l'écran montrait la contradiction sans la signaler.
> **Gatable.**

**B3. Une valeur d'état perd sa PROVENANCE dès qu'on la transforme.** Le
socle ne resynchronise un composant que s'il voit que la valeur vient du
serveur. Un cast, une f-string, une arithmétique, un `or`, **une
comparaison** effacent l'estampille.

```python
ui.stepper(value=int(state.etape))        # ne se resynchronise plus
ui.drawer(open=carte is not None)         # ne s'ouvrira jamais
ui.drawer(open=vue.tiroir)                # un CHAMP booléen déclaré
```

> *Payé* : le tiroir du kanban se re-rendait avec la bonne carte dedans
> et restait fermé. **Le cast est gaté** (`state-lost-by-a-cast`), la
> comparaison ne l'est pas encore — `work/todo.md`.

**B4. Une collection se RÉASSIGNE, elle ne se mute pas en place.**
`state.items[0]["x"] = 1` écrit la valeur et ne change pas l'identité de
la liste : rien ne se re-rend.

**B5. Un champ ÉDITABLE dans une zone diffusée perd ce qu'on tape.** Un
`<input>` rendu par le serveur à l'intérieur d'une zone
`@refreshable(broadcast=[…])` est remplacé chaque fois que n'importe qui
écrit dans l'état diffusé. Le brouillon doit vivre dans un `ClientState`
— sa valeur est dans le magasin du navigateur, le morph la réapplique.
Le serveur peut quand même l'amorcer : écrire un état client depuis un
handler est un chemin normal.

> *Payé* : mesuré à deux sessions sur le kanban. B tape « brouillon en
> cours » dans un commentaire sans l'envoyer, A glisse une carte à
> l'autre bout du tableau, et quatre secondes plus tard le champ de B est
> vide et son titre est revenu à celui du serveur. La garde « ne recharge
> le brouillon que si la carte change » ne protège de rien : elle empêche
> le serveur de RÉÉCRIRE l'état, pas le re-rendu de remplacer les
> ``<input>``.
>
> ⚠️ **Et ça déguise le défaut en probe instable** : la même course a fait
> rougir deux mesures DIFFÉRENTES du même scénario sur deux lancements
> consécutifs. Un probe qui alterne sans que l'app bouge accuse rarement
> le bon coupable.

**B6. Un brouillon édité et une valeur recalée par le serveur ne
partagent pas une classe d'état client.** Écrire UN champ d'un
`ClientState` depuis le serveur renvoie l'objet ENTIER dans le patch :
les champs en cours de frappe sont écrasés par ce que le serveur croyait
savoir.

> *Payé* : le tiroir du kanban réconciliait un compteur optimiste (la
> barre d'avancement) au rendu. Le commentaire vivait dans la même
> classe. On tape, et 1,2 s plus tard le champ est vide — le coupable
> étant une affectation d'entier dix lignes plus haut, sur un champ sans
> rapport. Séparer coûte une classe de cinq lignes.

> ⚠️ **Et un probe qui clique trop vite ne le voit pas.** Celui du kanban
> envoyait le commentaire dans la foulée de la frappe : il ne laissait à
> personne le temps de l'effacer. La mesure qui mord ATTEND, puis vérifie
> que le champ tient encore.

---

## C. Avant de montrer — ce qu'on mesure, et où

**C1. La plus PETITE fenêtre plausible, jamais la plus grande.** Mesurer
à 1500×940 valide la taille où tout tient. Prendre 1280×700 et 1366×640.

> *Payé* : le kanban ne défilait pas. La zone faisait 878 px dans un
> cadre de 591, débordait par le bas, et le document est gelé donc rien
> ne pouvait rattraper. Le probe affirmait « toutes les colonnes tiennent
> dans l'écran » — et il avait raison, à sa taille à lui.

Ce qui se mesure, dans un document gelé : la page ne déborde pas (`0`),
chaque région défilante finit **au-dessus** du bord, et une région qui
déborde rend un `scrollTop` non nul à la molette.

**C2. Un contrôle contre CHAQUE bord.** Les panneaux ancrés sont recadrés
par le bord de l'écran, et c'est là que le placement se sépare de ce qui
le désigne.

> *Payé* : la flèche d'un `ui.tooltip` pointait 25 px à côté de son
> bouton dès qu'on approchait du bord droit. Aucun banc du dépôt ne pose
> un contrôle contre un bord. **Gaté depuis** —
> `test_a_tooltip_arrow_points_at_its_trigger.py`.

**C3. Les gestes, pas seulement les écrans.** Un glisser, un refus, une
annulation. Un écran immobile ne dit rien d'un geste optimiste.

> *Payé* : un dépôt refusé côté serveur laissait la carte dans la colonne
> qui l'avait refusée. La gate qui prétendait couvrir ça était vacante —
> son banc incrémentait un compteur, donc le snap-back venait du
> compteur. **Gaté depuis, dans les deux sens.**

**C4. Les deux thèmes, et l'ordre des priorités.** Le clair d'abord si
l'auteur code en sombre : c'est celui qu'il ne regarde jamais.

**C5. Où atterrit la tabulation — et où elle n'a rien à faire.** Un
contrôle joignable au clavier dans un panneau FERMÉ n'est pas hors
écran : un dialogue est centré, ses champs sont pile au milieu du
viewport. Le contrôle « ça ne sort pas de l'écran » le laissait passer.

> *Payé* : sur la messagerie, la 2ᵉ tabulation de la page atterrissait
> dans le `ui.file_upload` d'un dialogue de rédaction fermé — invisible,
> et pourtant focusable. La cause était dans le framework : la règle
> anti-flash du shell re-déclarait `visibility:visible` sur tout porteur
> de `bz-data`, ce qui l'affranchissait du masquage de l'overlay.
> **Gaté depuis** — `test_a_closed_overlay_is_out_of_the_tab_order.py`
> pour les composants, et le balayage de `bretzel.probe` pour les apps.

---

## D. Avant de dire « c'est livré »

**D1. Le trajet d'ÉCRITURE en entier, pas seulement la lecture.** Créer,
puis rouvrir ce qu'on vient de créer.

> *Payé* : un `KeyError` livré à l'utilisateur dans la messagerie. Le
> handler d'envoi ne posait pas un champ que la graine avait ; le probe
> lisait la boîte, il n'y écrivait jamais.

**D2. Compter les requêtes d'un geste.** Le réseau ne se voit ni dans le
DOM ni dans les pixels.

> *Payé deux fois* : `ui.image` avec `src=""` retéléchargeait la page
> entière (2026-08-14, trouvé par l'utilisateur dans les logs) ; et une
> écriture d'`AppState` sur le kanban coûte cinq requêtes au lieu d'une,
> l'onglet qui agit recevant sa propre diffusion.

**D3. `bretzel check <app>` sans constat**, et `check --deep
<module:attr>` si l'app déclare des `Feature`.

**D4. Dire ce qui n'a PAS été vérifié.** Un « livré » implicite sur une
interaction non mesurée est le mode d'échec que la discipline #3 nomme.

---

## E. Ce qui doit devenir une gate

Une ligne de cette liste qui reste une ligne redérive. L'état au
2026-09-09 :

| Vérification | Statut |
|---|---|
| Flèche d'un panneau ancré au bord | **gatée** |
| Refus de dépôt sans mutation | **gatée** |
| Cast autour d'une valeur d'état | **gatée** (lint) |
| Champs frères à des tailles différentes | **gatée** (lint) |
| Handler de valeur sans paramètre typé | *gatable*, décrite dans `work/todo.md` |
| Comparaison qui efface la provenance | *gatable*, décrite dans `work/todo.md` |
| État mutable lu dans une coque | *gatable*, à décrire |
| Brouillon et valeur recalée dans la même classe | *gatable*, à décrire |
| Champ éditable dans une zone diffusée | *gatable*, à décrire — la population est nommable : un composant à saisie rendu sous une zone `broadcast=` dont la valeur vient d'un état SERVEUR |
| Contrôle fabriqué à la main | **œil seul** — rien à quoi s'accrocher |
| Chaîne de hauteurs d'un document gelé | **œil seul** — dépend de la taille de fenêtre |

Les deux dernières lignes sont la raison d'être de ce fichier : elles ne
seront jamais automatiques, donc elles doivent être *écrites*.
