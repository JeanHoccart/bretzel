# auth — les quatre façons d'entrer, une seule identité en sortie

Une app, quatre chemins d'authentification, et **le même `auth.user_id()`
au bout des quatre**. C'est le partage que Bretzel tient : le framework
possède l'identité et son transport (le cookie signé, la chaîne de
lecture) ; l'app possède la preuve (le mot de passe, la table, la
décision d'accepter).

L'écran de connexion affiche l'état des quatre — inutile de relire le
code pour savoir ce qui est branché.

---

## Tout allumé, en une commande

```powershell
py -m examples.auth.demo
```

Elle démarre le fournisseur OIDC local **et** l'app, avec les variables
déjà posées : les quatre façons sont actives, `http://127.0.0.1:8012`,
et Ctrl+C ferme les deux. C'est la voie à prendre pour essayer.

Le reste de cette page démonte cette commande — chaque façon séparément,
et ce qu'il faut poser pour la brancher sur un vrai fournisseur.

---

## 1. Mot de passe — rien à configurer

```powershell
py -m examples.auth.main
```

`http://127.0.0.1:8012` → `jean@macorp.fr` ou `ada@macorp.fr`, mot de
passe `demo`.

L'app vérifie, `auth.login(user_id)` transporte. C'est tout ce que le
framework fait ici.

## 2. Un jeton de machine — sans navigateur

Aucune session, aucun cookie : le porteur EST la preuve, revérifié à
chaque requête. `@auth.source` dans [`features/access.py`](features/access.py).

```powershell
curl.exe -s -H "Authorization: Bearer jeton-demo" http://127.0.0.1:8012/moi
```

```
user_id     : u-2
adresse     : ada@macorp.fr
reconnu par : jeton de machine (Authorization: Bearer)
```

⚠️ `curl.exe` et pas `curl` : sous Windows PowerShell, `curl` est un
**alias d'`Invoke-WebRequest`**, qui ne comprend ni `-s` ni `-H`.

`/moi` est **derrière la garde**, exprès : sans l'en-tête, la même
commande ne rend rien (302 vers `/login`). Voir ces trois lignes prouve
donc que la garde a lu le jeton — pas que la route serait ouverte.

## 3. Une porte OAuth / OIDC — sans compte chez personne

Un vrai fournisseur OIDC tourne en local
([`local_idp.py`](local_idp.py) : découverte, écran de consentement,
PKCE vérifié, `id_token` signé). **Deux terminaux** — ou la commande
unique ci-dessus, qui fait exactement ça.

```powershell
py -m examples.auth.local_idp
```

Il **ne rend pas la main** — c'est normal, c'est un serveur. Tu dois voir :

```
Fournisseur OIDC de test — issuer http://localhost:8954
  découverte : http://localhost:8954/.well-known/openid-configuration
  ...
INFO:     Uvicorn running on http://127.0.0.1:8954 (Press CTRL+C to quit)
```

Si le port est pris : `$env:BZ_IDP_PORT="8964"` (l'issuer suit le port,
et il faudra le reporter dans `BZ_OIDC_ISSUER` ci-dessous).

```powershell
$env:BZ_OIDC_NAME="testidp"; $env:BZ_OIDC_ISSUER="http://localhost:8954"; $env:BZ_OIDC_CLIENT_ID="bretzel-test-client"; $env:BZ_OIDC_CLIENT_SECRET="bretzel-test-secret"; py -m examples.auth.main
```

Sur `/login`, un bouton « Continuer avec testidp » apparaît. Le
fournisseur propose deux comptes :

- **jean@macorp.fr** → accepté, et il retombe sur `u-1` — le même compte
  que le mot de passe atteint. Une porte prouve une **adresse** ; c'est
  l'app qui joint sa table ;
- **someone@ailleurs.com** → refusé et renvoyé sur `/login`, parce que
  `on_user` rend `None` hors du domaine autorisé. Sans ce filtre, une
  porte est ouverte à toute personne ayant un compte chez le fournisseur.

⚠️ Le fournisseur est sur `localhost` et l'app sur `127.0.0.1` : deux
**sites** différents pour le navigateur, donc le retour est inter-site —
ce qui met le `SameSite=lax` du cookie de transaction sous contrainte
réelle. Deux ports du même hôte n'auraient rien prouvé.

### Le vrai Google / Microsoft / GitHub

Aucune ligne de code à changer, seulement l'environnement :

| fournisseur | ce qu'on pose |
|---|---|
| Google | `BZ_OIDC_ISSUER=https://accounts.google.com` |
| Microsoft Entra | `BZ_OIDC_ISSUER=https://login.microsoftonline.com/<tenant>/v2.0` |
| Auth0 | `BZ_OIDC_ISSUER=https://<domaine>.eu.auth0.com` |
| Keycloak | `BZ_OIDC_ISSUER=https://<hôte>/realms/<realm>` |
| GitHub (pas d'OIDC) | les `BZ_OAUTH2_*`, cf. [`core/domain.py`](core/domain.py) |

Plus `BZ_OIDC_CLIENT_ID` / `BZ_OIDC_CLIENT_SECRET`, et **l'URI de
redirection à déclarer chez eux** :
`http://127.0.0.1:8012/auth/<BZ_OIDC_NAME>/callback`.

## 4. Un proxy SSO — l'identité arrive par en-tête

oauth2-proxy, Google IAP, Cloudflare Access : l'authentification a eu
lieu avant d'atteindre l'app, le proxy l'atteste par un en-tête.

```powershell
$env:BZ_TRUST_PROXY_HEADER="1"; py -m examples.auth.main
```

```powershell
curl.exe -s -H "X-Remote-User: jean@macorp.fr" http://127.0.0.1:8012/moi
```

```
user_id     : u-1
adresse     : jean@macorp.fr
reconnu par : en-tête de proxy (X-Remote-User)
```

⚠️ **Éteinte par défaut, et c'est le sujet.** Un en-tête est déclaratif :
n'importe qui peut l'envoyer. Elle ne vaut que derrière un proxy qui
l'écrase à chaque requête — sans ça, `curl -H` est une porte d'entrée.
L'interrupteur est explicite pour que l'oubli **ferme** au lieu d'ouvrir.

---

## Ce que l'app démontre, en une ligne par fichier

| fichier | ce qu'il porte |
|---|---|
| [`features/access.py`](features/access.py) | les deux moitiés : `@auth.source` (qui es-tu) et `@auth.door` (comment on entre) |
| [`features/login.py`](features/login.py) | la page publique, et l'état des quatre façons |
| [`features/home.py`](features/home.py) | un `UserState` — il marche à l'identique quelle que soit la porte |
| [`main.py`](main.py) | la garde middleware, et `app.public_paths` qui lui évite d'énumérer le framework |
| [`core/domain.py`](core/domain.py) | la table, le domaine autorisé, la config lue dans l'environnement |

## La vérification automatique

```powershell
py tests/probes/probe_auth.py
```

```powershell
py tests/probes/probe_oauth_door.py
```

Le premier conduit le mot de passe dans Chromium (garde, tab order, refus,
connexion, `UserState`, déconnexion). Le second conduit le flux OIDC
complet contre `local_idp` — c'est **le même fournisseur que celui qu'on
clique à la main**, exprès : celui qu'on mesure doit être celui qu'on
essaie.
