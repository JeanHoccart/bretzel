# auth — four ways in, one identity out

One app, four authentication paths, and **the same `auth.user_id()` at
the end of all four**. This is the split Bretzel holds: the framework
owns the identity and its transport (the signed cookie, the reading
chain); the app owns the proof (the password, the table, the decision to
accept).

The sign-in screen shows the state of all four — no need to re-read the
code to know what is wired.

---

## Everything on, in one command

```powershell
py -m examples.auth.demo
```

It starts the local OIDC provider **and** the app, with the variables
already set: the four ways are live on `http://127.0.0.1:8012`, and
Ctrl+C closes both. This is the way to try it.

The rest of this page takes that command apart — each way on its own,
and what to set to wire it to a real provider.

---

## 1. Password — nothing to configure

```powershell
py -m examples.auth.main
```

`http://127.0.0.1:8012` → `jean@macorp.fr` or `ada@macorp.fr`, password
`demo`.

The app checks, `auth.login(user_id)` transports. That is all the
framework does here.

## 2. A machine token — no browser

No session, no cookie: the bearer IS the proof, re-checked on every
request. `@auth.source` in [`features/access.py`](features/access.py).

```powershell
curl.exe -s -H "Authorization: Bearer demo-token" http://127.0.0.1:8012/me
```

```
user_id      : u-2
address      : ada@macorp.fr
recognised by: machine token (Authorization: Bearer)
```

⚠️ `curl.exe` and not `curl`: under Windows PowerShell, `curl` is an
**alias for `Invoke-WebRequest`**, which understands neither `-s` nor `-H`.

`/me` is **behind the guard**, on purpose: without the header, the same
command returns nothing (302 to `/login`). Seeing those three lines
therefore proves the guard read the token — not that the route would be
open.

## 3. An OAuth / OIDC door — without an account anywhere

A real OIDC provider runs locally ([`local_idp.py`](local_idp.py):
discovery, consent screen, PKCE checked, signed `id_token`). **Two
terminals** — or the single command above, which does exactly that.

```powershell
py -m examples.auth.local_idp
```

It **does not hand control back** — that is normal, it is a server. You
should see:

```
Test OIDC provider — issuer http://localhost:8954
  discovery : http://localhost:8954/.well-known/openid-configuration
  ...
INFO:     Uvicorn running on http://127.0.0.1:8954 (Press CTRL+C to quit)
```

If the port is taken: `$env:BZ_IDP_PORT="8964"` (the issuer follows the
port, and it has to be carried into `BZ_OIDC_ISSUER` below).

```powershell
$env:BZ_OIDC_NAME="testidp"; $env:BZ_OIDC_ISSUER="http://localhost:8954"; $env:BZ_OIDC_CLIENT_ID="bretzel-test-client"; $env:BZ_OIDC_CLIENT_SECRET="bretzel-test-secret"; py -m examples.auth.main
```

On `/login`, a “Continue with testidp” button appears. The provider
offers two accounts:

- **jean@macorp.fr** → accepted, and it lands on `u-1` — the same account
  the password reaches. A door proves an **address**; the app is what
  joins its table;
- **someone@elsewhere.com** → refused and sent back to `/login`, because
  `on_user` returns `None` outside the allowed domain. Without that
  filter, a door is open to anyone holding an account at the provider.

⚠️ The provider is on `localhost` and the app on `127.0.0.1`: two
different **sites** for the browser, so the return trip is cross-site —
which puts the transaction cookie's `SameSite=lax` under real strain. Two
ports of the same host would have proved nothing.

### The real Google / Microsoft / GitHub

Not a line of code to change, only the environment:

| provider | what to set |
|---|---|
| Google | `BZ_OIDC_ISSUER=https://accounts.google.com` |
| Microsoft Entra | `BZ_OIDC_ISSUER=https://login.microsoftonline.com/<tenant>/v2.0` |
| Auth0 | `BZ_OIDC_ISSUER=https://<domain>.eu.auth0.com` |
| Keycloak | `BZ_OIDC_ISSUER=https://<host>/realms/<realm>` |
| GitHub (no OIDC) | the `BZ_OAUTH2_*`, cf. [`core/domain.py`](core/domain.py) |

Plus `BZ_OIDC_CLIENT_ID` / `BZ_OIDC_CLIENT_SECRET`, and **the redirect
URI to declare on their side**:
`http://127.0.0.1:8012/auth/<BZ_OIDC_NAME>/callback`.

## 4. An SSO proxy — the identity arrives in a header

oauth2-proxy, Google IAP, Cloudflare Access: authentication happened
before reaching the app, and the proxy attests it with a header.

```powershell
$env:BZ_TRUST_PROXY_HEADER="1"; py -m examples.auth.main
```

```powershell
curl.exe -s -H "X-Remote-User: jean@macorp.fr" http://127.0.0.1:8012/me
```

```
user_id      : u-1
address      : jean@macorp.fr
recognised by: proxy header (X-Remote-User)
```

⚠️ **Off by default, and that is the point.** A header is declarative:
anyone can send one. It is only worth something behind a proxy that
overwrites it on every request — without that, `curl -H` is a way in.
The switch is explicit so that forgetting it **closes** instead of
opening.

---

## What the app demonstrates, one line per file

| file | what it carries |
|---|---|
| [`features/access.py`](features/access.py) | the two halves: `@auth.source` (who are you) and `@auth.door` (how one gets in) |
| [`features/login.py`](features/login.py) | the public page, and the state of the four ways |
| [`features/home.py`](features/home.py) | a `UserState` — it works identically whichever door was used |
| [`main.py`](main.py) | the middleware guard, and `app.public_paths` which spares it from enumerating the framework |
| [`core/domain.py`](core/domain.py) | the table, the allowed domain, the config read from the environment |

## The automatic check

```powershell
py tests/probes/probe_auth.py
```

```powershell
py tests/probes/probe_oauth_door.py
```

The first drives the password path in Chromium (guard, tab order,
refusal, sign-in, `UserState`, sign-out). The second drives the full OIDC
flow against `local_idp` — it is **the same provider one clicks by
hand**, on purpose: what you measure must be what you try.
