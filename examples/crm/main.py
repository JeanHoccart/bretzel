"""CRM — l'instrument d'usage réel. ``py -m examples.crm.main``.

Ce n'est pas une 18ᵉ démo : c'est l'app dont on se sert pour MESURER le
framework en long et en large. Le brief, la règle « interdiction de se
dépanner » et le journal des findings vivent dans
``.claude/work/chantier-crm-2026-08-19.md``.

``main`` est le seul fichier à connaître l'instance : il ``include`` les
features, sème la base au démarrage, et laisse le contrat se valider.
"""

from pathlib import Path

from bretzel import Bretzel, auth
from bretzel.runtime import is_public_asset_path
from bretzel.server import action_path, redirect_response
from examples.crm.core import db
from examples.crm.core.db import init_db
from examples.crm.core.domain import LOGIN_PATH
from examples.crm.core.texts import FR_TEXTS
from examples.crm.core.theme import THEME
from examples.crm.features import (
    access,
    account_detail,
    accounts,
    accounts_data,
    activities,
    activities_data,
    analyse_nav,
    app_map,
    auth_data,
    contact_detail,
    contacts,
    contacts_data,
    deals_data,
    errors,
    geo,
    import_data,
    import_screen,
    login,
    nightly_hygiene,
    pipeline,
    realtime,
    reports,
    reports_data,
    search,
    search_data,
    settings,
    shell,
)

#: Les assets de l'app, montés sur ``/static`` par ``static_dir=``.
#: Un chemin ABSOLU dérivé de ce fichier : un chemin relatif dépendrait
#: du dossier depuis lequel on lance, et ``Bretzel(static_dir=…)`` LÈVE
#: au démarrage quand il ne pointe pas un dossier existant.
STATIC_DIR = Path(__file__).resolve().parent / "static"

#: L'icône de CETTE app — un entonnoir, pas le nœud de Bretzel.
#:
#: C'est la démonstration de ``favicon=`` : par défaut une app Bretzel
#: porte la marque du framework, et il suffit d'une chaîne pour poser la
#: sienne. Le fichier est servi par ``static_dir``, donc c'est l'app qui
#: en répond — le framework ne fait que l'annoncer dans le ``<head>``.
FAVICON_PATH = "/static/favicon.svg"

app = Bretzel(
    title="Bretzel · CRM",
    secret_key="dev-crm-secret-change-me",
    theme=THEME,
    static_dir=str(STATIC_DIR),
    favicon=FAVICON_PATH,
    # ``prod`` et pas ``dev`` : c'est le seul mode qui montre la vitesse
    # réelle. En dev le CSS est compilé DANS le navigateur par
    # ``@tailwindcss/browser`` et le runtime est servi en version lisible
    # (286 Ko au lieu de 97) — deux choix faits pour la boucle de
    # développement, pas pour l'affichage. En prod : feuille compilée
    # servie en un ``<link>``, ``runtime.min.js``, et les trois scripts
    # tiers rapatriés s'ils sont dans ``.bretzel/vendor/``. Mesuré le
    # 2026-08-27 sur une page minimale, cache froid : DOMContentLoaded à
    # 110 ms contre 644.
    #
    # ⚠️ Deux contreparties, toutes deux réelles : le premier démarrage
    # recompile ``.bretzel/style.css`` (quelques secondes, binaire
    # Tailwind requis dans ``.bretzel/bin/``), et ce cache est PARTAGÉ
    # avec les autres exemples — alterner CRM et playground recompile à
    # chaque fois, parce que leurs thèmes n'ont pas la même empreinte.
    # Repasser à ``mode="dev"`` pour retrouver le rechargement à chaud.
    mode="prod",
    # ── La langue, déclarée UNE fois ──────────────────────────────────
    # Elle pose ``<html lang="fr">`` (un lecteur d'écran y choisit sa
    # voix) et surtout, elle fait nommer les mois et les jours par le
    # navigateur : les quatre composants de date de cet écran rendaient
    # « August / MON TUE WED », et la seule prise était de repasser 19
    # chaînes à CHAQUE montage — trois fois rien que sur l'écran 6.
    lang="fr",
    texts=FR_TEXTS,
)


#: Les chemins joignables SANS être connecté. Tout le reste est fermé —
#: c'est le sens d'une garde par middleware, et la raison pour laquelle
#: ce n'est pas un ``@page(auth=…)`` : une page ajoutée demain est
#: protégée sans que personne y pense.
#: ⚠️ ``PUBLIC_ASSET_ROUTES`` vient du FRAMEWORK, et c'est le point.
#: Ces trois chemins étaient énumérés ici à la main — plus un quatrième
#: (``theme.js``) qui n'était monté par personne, et qui a été retiré du
#: framework en conséquence. Surtout, il fallait
#: SAVOIR que ``/_bretzel/refetch`` et ``/_bretzel/sse`` rendent du HTML
#: de page et doivent rester fermés. C'est de la connaissance du socle
#: dans du code d'app : une route interne ajoutée demain cassait cette
#: garde, ou l'ouvrait, sans que rien ne le dise. Le classement
#: appartient à celui qui monte les routes, et il est gaté
#: (``test_framework_routes_are_classified``).
#: ⚠️ Et c'est ``is_public_asset_path`` qui tranche, PAS une égalité sur
#: ``PUBLIC_ASSET_ROUTES`` : cet ensemble contient des MOTIFS de route.
#: ``/_bretzel/vendor/{filename}`` n'est égal à aucun chemin réel, donc
#: l'égalité refusait les trois scripts tiers — et le navigateur recevait
#: cette page de connexion à la place d'un ``<script>``. Symptôme exact,
#: mesuré le 2026-08-27 : trois ``Unexpected token '<'`` en console, la
#: page rendue à 100 nœuds au lieu de 1 700, aucune erreur serveur.
#: ⚠️ **L'icône de l'app en fait partie, et ce n'est pas intuitif.**
#: ``is_public_asset_path`` ne connaît que les assets du FRAMEWORK —
#: c'est sa définition. Une icône posée par ``favicon=`` vit chez l'app,
#: sur ``/static``, donc la garde la refuse comme n'importe quelle page :
#: la connexion demande son icône avant que quiconque soit connecté, et
#: reçoit une 302 vers elle-même. Symptôme : aucune icône sur l'écran de
#: connexion, une seule, et rien dans les logs. C'est le prix de poser sa
#: propre marque, et il se paie ici, sur une ligne.
PUBLIC_PATHS: frozenset[str] = frozenset({LOGIN_PATH, FAVICON_PATH})

#: L'action de connexion, et elle seule — nommée par la FONCTION.
#:
#: ⚠️ C'était un préfixe de module (``…/examples.crm.features.login::``).
#: Le résolveur du socle marche en ``getattr`` sur le module, donc ce
#: préfixe ouvrait nominalement tout ce que ``login.py`` importe —
#: ``auth.login``, ``redirect``, la fabrique de composants. La
#: signature HMAC restait la vraie barrière, mais le périmètre de la
#: garde grandissait avec la liste d'imports d'un fichier, en silence.
#:
#: ⚠️ Ouvrir ``/_bretzel/action/`` en entier serait plus court et FAUX :
#: les zones ``@refreshable`` se re-rendent par ``/_bretzel/refetch/…`` et
#: le temps réel par ``/_bretzel/sse`` — deux routes qui rendent du HTML
#: de page. Les laisser dehors, c'est laisser douze écrans se rendre pour
#: un anonyme.
#:
#: ``sign_out`` n'y est PAS : on ne se déconnecte que connecté.
#: ⚠️ Le chemin se DEMANDAIT au framework depuis le 2026-08-24
#: (``action_path``) : il était recomposé ici à la main, avec le
#: séparateur de wire-id, et ``examples/auth`` allait le recopier.
PUBLIC_ACTIONS: frozenset[str] = frozenset(
    action_path(fn) for fn in (login.sign_in,)
)


@app.middleware
async def require_login(request, call_next):
    """La garde. Écrite en PREMIER, donc la plus externe.

    ``auth.user_id`` et non ``auth.is_authenticated`` : à ce
    niveau ni le contexte de rendu ni ``request.state.user`` n'existent
    encore. Jusqu'au 2026-08-23 cet exemple lisait le cookie lui-même et
    devait recevoir ``app.config._auth_key`` — l'attribut privé — depuis
    ici.

    ``redirect_response`` et non ``redirect`` : le premier tranche entre
    une vraie 302 (navigation) et un ``HX-Redirect`` (action du bridge),
    le second lève hors d'un contexte de rendu.
    """
    path = request.url.path
    if (path in PUBLIC_PATHS
            or is_public_asset_path(path)
            or path in PUBLIC_ACTIONS
            or auth.user_id(request)):
        return await call_next(request)
    return redirect_response(request, LOGIN_PATH)


@app.startup
async def seed_db() -> None:
    # Idempotent : ne resème que si ``SEED_VERSION`` a bougé. ~4 s la
    # première fois pour 262 000 lignes, zéro les suivantes.
    init_db()


app.include(
    db,                          # infra
    shell,                       # shell
    analyse_nav,                 # layout (shell ▸ analyse_nav ▸ pages)
    access,                      # logic (la politique d'accès)
    geo,                         # facade (le géocodeur, service externe)
    nightly_hygiene,             # job (aucune route, aucun rendu)
    auth_data,                                  # data
    accounts_data, contacts_data, deals_data,
    activities_data, reports_data, search_data, import_data,
    login,                                      # pages
    pipeline, accounts, account_detail,
    contacts, contact_detail, activities, reports, search,
    import_screen, settings, realtime,
    errors,                                     # error
    app_map,                                    # meta (carte)
)


if __name__ == "__main__":
    app.run(port=8016, reload=True)
