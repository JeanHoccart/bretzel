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
from html import escape

from bretzel import Bretzel
from starlette.responses import Response

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
    description="Bretzel documentation: the Python web framework where the mockup is the app — built with an AI agent, every file checked.",
    secret_key=secret_key,
    mode=mode,
    lang="en",
)


@app.fastapi.get("/robots.txt", include_in_schema=False)
async def robots_txt() -> Response:
    """Expose crawler policy at the documentation host root."""
    return Response(
        "User-agent: *\nAllow: /\n\nSitemap: https://docs.bretzel-py.dev/sitemap.xml\n",
        media_type="text/plain",
    )


@app.fastapi.get("/sitemap.xml", include_in_schema=False)
async def sitemap_xml() -> Response:
    """List every public documentation route for search-engine discovery.

    Read from ``app.fastapi.routes`` — the routes as they are MOUNTED,
    at request time. The first version walked ``app._pages`` and each
    page's ``._bz_page``, two private attributes; the gate
    ``test_no_example_reads_a_private_attribute`` says why, and it is
    the shape ``app.config._auth_key`` had before ``auth.user_id``
    existed. Nothing private is needed here: a page that is mounted has
    a route, and a route is public.

    The three filters are the definition of "public documentation
    route": the framework's own endpoints (``/_bretzel/…``), the
    parameterised ones (no single URL to publish), and this file's
    non-HTML routes.
    """
    hidden = {"/sitemap.xml", "/robots.txt", "/llms.txt", "/llms-full.txt"}
    paths = sorted({
        route.path
        for route in app.fastapi.routes
        if getattr(route, "path", "").startswith("/")
        and not route.path.startswith("/_")
        and "{" not in route.path
        and route.path not in hidden
    })
    entries = "".join(
        f"  <url><loc>https://docs.bretzel-py.dev{escape(path)}</loc></url>\n"
        for path in paths
    )
    return Response(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{entries}</urlset>\n",
        media_type="application/xml",
    )


@app.fastapi.get("/llms.txt", include_in_schema=False)
async def llms_txt() -> Response:
    """The documentation map for language models (llmstxt.org).

    An assistant asked about Bretzel reads this file before the pages.
    The recipes come first, each with the address of its raw Markdown
    and the need it answers: one complete app per common request is what
    an agent should read before writing. Then one line per chapter, in
    the order of the sidebar. Both are read from their own source — the
    recipe files and ``NAV`` — so an addition there is listed here with
    no second edit.
    """
    from examples.docs.features.shell import NAV, RECIPES_SECTION
    from examples.docs.recipes import RECIPES

    lines = [
        "# Bretzel documentation",
        "",
        "> Bretzel is a Python web framework for building apps with an AI "
        "agent: ask for a screen, approve a real mockup made of the components "
        "the app will ship, and the same file becomes the working screen. "
        "`bretzel describe` gives the exact API of the installed version, "
        "`bretzel check` judges every file written. Typed state, targeted "
        "server rendering, 100+ components, realtime over SSE, no npm "
        "toolchain. Alpha: APIs may change.",
        "",
        "Install with `pip install bretzel` (Python 3.12, 3.13 or 3.14). "
        "Source: https://github.com/JeanHoccart/bretzel — "
        "component gallery: https://ui.bretzel-py.dev",
        "",
        "The whole API of the version this site runs, in one file generated "
        "from the code: https://docs.bretzel-py.dev/llms-full.txt",
        "",
        "## Recipes — read these first: one complete app per common request",
        "",
    ]
    lines += [
        f"- [{recipe.title}](https://docs.bretzel-py.dev/recipes/{recipe.slug}.md): {recipe.need}"
        for recipe in RECIPES
    ]
    for section, items in NAV:
        if section == RECIPES_SECTION:
            continue  # listed first, above, as raw Markdown
        lines += ["", f"## {section.capitalize()}", ""]
        for label, href, _icon, _blurb in items:
            url = href if href.startswith("http") else f"https://docs.bretzel-py.dev{href}"
            lines.append(f"- [{label}]({url})")
    return Response("\n".join(lines) + "\n", media_type="text/plain; charset=utf-8")


@app.fastapi.get("/llms-full.txt", include_in_schema=False)
async def llms_full_txt() -> Response:
    """The map of ``/llms.txt``, then every card ``bretzel describe`` prints
    for the version this site runs: the ``ui.*`` index, each component and
    helper, each public module. Generated, so it cannot drift from the code:
    what an assistant reads here is what it will import."""
    from bretzel.introspect import describe, index, module_names, ui_symbol_names

    cards = [describe(name) for name in (*sorted(ui_symbol_names()), *module_names())]
    text = "\n\n".join([bytes((await llms_txt()).body).decode(), index(), *cards])
    return Response(text + "\n", media_type="text/plain; charset=utf-8")

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
    compare,
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
    mockup,
    quickstart,
    reactivity_client,
    reactivity_server,
    recipes,
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

# L'ordre de la barre de gauche : DÉMARRER, RECETTES, LE CYCLE,
# CONSTRUIRE, LES SUJETS, CHERCHER — puis les stubs et les erreurs.
# ⚠️ `stubs` DOIT rester après les vrais chapitres : il lit leurs
# marques `@page` pour savoir lesquels sont livrés.
app.include(
    home, mockup, quickstart, how, compare, describe, check,
    recipes,
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
