# En-têtes de sécurité & CSP

> Ce que Bretzel envoie sur chaque réponse, ce qu'il laisse à l'app, et
> pourquoi la ligne passe exactement là.

## En une ligne

```python
Bretzel(csp="report-only")     # observation : le navigateur signale, ne bloque rien
Bretzel(csp=True)              # blocage
Bretzel(csp=True, csp_sources={"font-src": ["https://fonts.gstatic.com"]})
Bretzel(security_headers=False)   # retirer les trois en-têtes ennuyeux
```

## Deux étages, et la ligne entre eux

**Les en-têtes ennuyeux sont un défaut.** `X-Content-Type-Options:
nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`,
`X-Frame-Options: SAMEORIGIN`. Aucun ne dépend de ce que l'app charge,
donc aucun ne peut la casser — il n'y a pas de décision à prendre, et
c'est pour ça qu'ils sont posés sans rien demander.

**La CSP n'en est pas un.** Elle dépend des polices, CDN, iframes et
`ui.video` distants de l'app, que le framework ne peut pas deviner.
L'activer d'office casserait une app sur deux au premier déploiement, en
silence : une ressource refusée ne produit qu'une ligne dans la console
du navigateur.

Mais **le dev ne rédige pas la politique**. Bretzel calcule ce qu'il se
doit à lui-même ; `csp_sources=` ne sert qu'à déclarer ce que l'app
ajoute. C'est le même partage que l'auth — le framework possède son
transport, l'app possède ce qu'elle seule sait.

## Commencer par `report-only`

C'est le premier barreau, et il existe exactement pour ne pas découvrir
en production qu'il manquait une origine : le navigateur **évalue** la
politique et signale ce qui aurait sauté, sans rien bloquer. On regarde
ce qui remonte dans la console, on complète `csp_sources`, puis on passe
à `csp=True`.

Mesuré le 2026-09-05 sur les 77 pages du playground en blocage : **zéro
violation venue du framework**. Les deux seules pages rouges chargeaient
des avatars `i.pravatar.cc` et une iframe — du contenu d'app, donc
exactement ce que `csp_sources` déclare.

## Étendre : `csp_sources`

```python
Bretzel(csp=True, csp_sources={
    "font-src": ["https://fonts.gstatic.com"],
    "frame-src": ["https://www.youtube.com"],
})
```

On élargit, jamais on ne rétrécit — et c'est vrai **y compris pour une
directive que le socle ne porte pas**. Dans une CSP brute, une directive
absente n'est pas permissive : elle retombe sur `default-src`, donc
l'écrire la sort de ce repli et lui fait perdre ce dont elle héritait.
`build_policy` amorce toute directive neuve avec les valeurs de
`default-src` pour que le piège n'existe pas ici. Il a mordu pour de
vrai le 2026-09-05 (`frame-src: ["data:"]` a bloqué une iframe
même-origine du playground) ; cf. `traps.md` § Sécurité.

Une clé mal orthographiée est refusée **au démarrage**, pas ignorée :
`img_src` ou `image-src` ne fait rien du tout dans un navigateur, la
ressource est simplement bloquée sans message.

Le playground est le banc d'essai, en blocage : cf.
`examples/playground/main.py`. Mesuré le 2026-09-05, **77 pages, zéro
violation**.

## Ce que Bretzel calcule tout seul

| Quoi | Pourquoi |
|---|---|
| `'unsafe-eval'` | Le moteur de directives compile chaque `bz-*` en fonction (`new Function`). Irréductible : cf. plus bas. |
| Trois `'sha256-…'` | Les corps inline de la coque, qui sont déterministes. |
| `https://api.iconify.design` + deux replis dans `connect-src` | Compatibilité conservée dans la CSP. La coque actuelle dirige les glyphes vers `/_bretzel/icons` ; le serveur relaie un manque puis le met en cache. |
| Les origines des assets telles qu'elles sont | Le repli CDN est la règle tant que `python -m bretzel.render.vendor` n'a pas tourné : la politique lit les URL que la coque va **réellement** émettre. |

## Pourquoi des empreintes et pas un `nonce`

Un `nonce` est la réponse standard, et c'est **la mauvaise ici**. Il
faudrait une valeur par réponse — donc une page non cachable — et un
paramètre de plus dans la signature de toute coque personnalisée
(`meta.shell` est remplaçable par l'app).

Or les trois corps inline ne dépendent que du thème et de
`mobile_breakpoint`, jamais de la requête. Mesuré : **3 empreintes
distinctes sur 77 pages × 2 requêtes**. Les hashes ne coûtent donc rien
et ne touchent aucune signature.

⚠️ **Un script inline se déclare dans
`bretzel.render.shell.inline_scripts`, jamais directement dans
`_build_head`.** Un quatrième script posé ailleurs ne casse rien tant que
la CSP est désactivée — c'est le défaut — puis rend la page morte le jour
où une app l'active. Gaté par
`tests/consistency/test_every_inline_script_is_in_the_policy.py`.

## `'unsafe-eval'` : pourquoi il reste, et pourquoi ça va

Le moteur de directives compile les attributs `bz-*` en fonctions
(`02_directives.js` et `03_scope.js`). S'en passer voudrait dire
interpréter ces expressions — et mesuré le 2026-09-05 sur les 134 057
expressions que le playground émet, **29 % sortent d'un sous-ensemble
interprétable** : fonctions fléchées à corps d'instructions (17 %),
`if`/`return` (9,5 %), indexation calculée (9 %), `new X()` (2,3 %). Ce
ne sont pas les apps qui les écrivent, ce sont les composants du
framework — `bz-init` 97 % dures, `bz-on:focus` 97 %, `bz-class` 92 %,
`bz-effect` 87 %. La restriction façon Alpine-CSP demanderait de
réécrire leur comportement client.

**Ça n'annule pas la protection.** `script-src` ne porte pas
`'unsafe-inline'` : une balise `<script>` injectée ne s'exécute pas, et
c'est la classe XSS dominante. `'unsafe-eval'` ne sert un attaquant
qu'une fois qu'il peut déjà faire entrer une chaîne dans une expression
`bz-*` — ce que `bretzel.core.escape.escape_js` ferme (antislash
d'abord, puis les quotes, puis `</` neutralisé).

Vérifié dans un navigateur, pas sur le papier :
`tests/runtime_js/test_a_page_runs_under_its_own_policy.py` injecte un
`<script>` et exige qu'il soit refusé — avec le contrôle qui montre que
la même injection PASSE sans la politique.

## `'unsafe-inline'` sur `style-src` : irréductible

La page porte des attributs `style=`, et **ni un hash ni un nonce ne
couvre un attribut**. Pire : en présence de l'un d'eux, le navigateur
IGNORE `'unsafe-inline'`, donc l'attribut saute quand même. Le
compilateur Tailwind navigateur (mode dev) injecte en plus sa feuille au
runtime.

## Où c'est écrit

| Quoi | Où |
|---|---|
| La politique et ses constantes | `bretzel/server/security.py` |
| La pose sur la réponse | `bretzel/server/middleware/security.py` |
| Les réglages + leur validation au démarrage | `bretzel/server/config.py` |
| La source unique des scripts inline | `bretzel.render.shell.inline_scripts` |

Le middleware est **le plus externe** de la pile framework (juste sous la
compression) : ses en-têtes couvrent aussi les réponses que les couches
du dessous produisent seules — un 403 CSRF, un 401 auth, un 404. Posé
plus bas, il ne verrait que les pages.
