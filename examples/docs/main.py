"""Doc vivante Bretzel — ``py -m examples.docs.main`` (port 8006).

Structure plate : pas de dossier ``app/``. Chaque feature se décore
elle-même (``@page`` / ``@error``) et référence le shell par import
direct ; ``main`` include les modules features. Le ``shell`` (``@layout``)
n'est pas inclus — il se résout par référence (``layout=shell``).

LA RÈGLE : un index LISTE, un chapitre ENSEIGNE
===============================================
Posée le 2026-09-03, parce que quatre pages répondaient à « qu'est-ce
que Bretzel sait faire » sans qu'aucune fasse autorité, et que rien ne
disait **où écrire** en ajoutant un sujet.

Deux natures de page, et on choisit avant d'écrire une ligne :

**Un INDEX** est GÉNÉRÉ d'une source unique, ne porte aucune prose de
son cru, et RENVOIE. Il y en a quatre, chacun sur sa source :

===================  =====================================  ==============
``/capabilities``    ``introspect.CAPABILITIES``            ce que ça PERMET
``/tree``            ``introspect.describe_package``        où c'est RANGÉ
``/components``      ``introspect.describe_components``     la SIGNATURE exacte
``/cheatsheet``      la surface du paquet                   tout, Ctrl-F
===================  =====================================  ==============

**Un CHAPITRE** est écrit à la main, enseigne UN mécanisme, et c'est le
seul endroit où l'on explique. Un mécanisme a un chapitre et un seul.

Ce qui rend la règle applicable plutôt que pieuse
--------------------------------------------------
Chaque entrée de :data:`~bretzel.introspect.CAPABILITIES` déclare son
chapitre (``chapter="/browser"``), et
``test_a_capability_is_anchored`` vérifie que la route existe pour de
vrai. Une capacité sans chapitre s'affiche « pas encore de chapitre »
sur la page — dette visible — et un cliquet interdit d'en ajouter une
neuvième. Mesuré à la pose : 8 sur 19.

⚠️ **Ce que la mesure a dit, et qui n'était pas ce qu'on croyait.** On
soupçonnait des doublons entre chapitres. Il n'y en a pas : en ne
regardant que ce dont ils PARLENT — les chaînes de ``ui.code`` et de
``ui.text``, pas les composants qu'ils emploient pour se rendre — trois
paires seulement partagent quatre symboles, et ce sont ``Bretzel``,
``page`` et ``ui.button``, dont tout extrait a besoin. Le désordre
n'était pas de la redite, c'était l'absence de règle.
"""

import os

from bretzel import Bretzel

mode = os.environ.get("BRETZEL_DOCS_MODE", "dev")
secret_key = os.environ.get("BRETZEL_DOCS_SECRET_KEY")
if secret_key is None:
    if mode == "prod":
        raise RuntimeError(
            "BRETZEL_DOCS_SECRET_KEY is required when BRETZEL_DOCS_MODE=prod"
        )
    secret_key = "dev-docs-secret-change-me"

app = Bretzel(
    title="Bretzel · Docs",
    secret_key=secret_key,
    mode=mode,
)

from examples.docs.features import (      # noqa: E402 — marks ramassées par include
    actions_client,
    actions_server,
    app_map,
    auth,
    cadence,
    capabilities,
    check,
    charts,
    cheatsheet,
    components,
    config,
    describe,
    drag,
    errors,
    forms,
    home,
    how,
    languages,
    lists,
    quickstart,
    reactivity_client,
    reactivity_server,
    browser,
    tree,
    runtime,
    state_client,
    state_server,
    scrolling,
    structure,
    theme,
    traps,
    stubs,
)

# L'ordre de la barre de gauche : DÉMARRER, LE CYCLE, CONSTRUIRE,
# LES SUJETS, CHERCHER — puis les stubs et les erreurs.
# ⚠️ `stubs` DOIT rester après les vrais chapitres : il lit leurs
# marques `@page` pour savoir lesquels sont livrés.
app.include(
    home, quickstart, how, describe, check,
    state_server, state_client,
    actions_server, actions_client,
    reactivity_server, reactivity_client,
    config, components, runtime, capabilities, tree,
    lists, forms, drag, charts, cadence, scrolling, languages, auth, browser,
    theme, structure, traps, cheatsheet, app_map,
    stubs, errors,
)


if __name__ == "__main__":
    app.run(port=8006, reload=True)
