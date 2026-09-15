"""``Title`` / ``MetaTag`` / ``Fragment`` test bench.

The three Tier-11 meta primitives have no body footprint :

- ``ui.title`` writes ``ctx.head_title`` (the browser tab + ``<title>``).
- ``ui.meta_tag`` appends an :class:`Element` to ``ctx.head_extras``
  (lands inside ``<head>``, never the body).
- ``ui.fragment`` renders a wrap-less :class:`FragmentNode` (children
  flatten into the parent, no surrounding HTML tag).

The live demo is therefore the **browser tab title** (compare it on
this page vs. the rest of the playground) and the **document head**
(open dev tools → Elements → ``<head>``). The Fragment card stays
in-body because its effect IS the structural side-by-side.
"""

import bretzel
from bretzel import download, refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import (
    ClientExpression,
    ClientState,
    PageState,
    field,
)

from examples.playground.features.inspection import emitted_html_block


PATH = "/meta"


class VerbDemo(ClientState):
    """La valeur que le bouton copie, VIVANTE.

    Elle est en ``ClientState`` et pas en littéral pour montrer le seul
    cas qui compte : ``bretzel.copy`` interpole le CHEMIN du champ, pas
    sa valeur au rendu. Tape dans le champ, copie, colle — c'est ce que
    tu viens de taper qui sort, sans que le serveur l'ait jamais vu.
    """

    secret: str = field(default="sk-live-4f2a91")


# ── Demo state — drives the Server playground card ───────────────────────


class TitlePlayground(PageState):
    """Title playground — one field for the live text.

    Default matches the page-level ``ui.title()`` so a fresh visit
    shows the panel writing the SAME value the page-level call set —
    the override only becomes visible when the user edits.
    """

    text: str = field(default="Meta primitives — Playground")


class MetaTagPlayground(PageState):
    """MetaTag playground — pick the identifier kind + name + content."""

    identifier_kind: str = field(default="name")  # name / property / http_equiv
    identifier:      str = field(default="description")
    content:         str = field(default="Internal tools demo")


def title_changed(state: TitlePlayground) -> None:
    # Typed param: the dispatcher hydrates the changed control into state.
    pass


def meta_tag_changed(state: MetaTagPlayground) -> None:
    # Typed param: the dispatcher hydrates the changed control into state.
    pass


# ── Title panel ──────────────────────────────────────────────────────────


@refreshable(deps=[TitlePlayground])
def title_panel() -> None:
    state = TitlePlayground()
    # ⚠️ Side effect : changing the text below ACTUALLY updates the
    # browser tab title (partial-nav refresh flips the HX-Trigger
    # ``bretzel:title``). Watch the tab while you type.
    ui.title(state.text)

    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
        with ui.vstack(gap="xs"):
            ui.text("text", color="muted", size="xs")
            ui.input(value=state.text, on_change=title_changed,
                     placeholder="Page title")
        with ui.vstack(gap="xs"):
            ui.text("preview (tab title)", color="muted", size="xs")
            ui.text(state.text or "(empty → falls back to decorator)",
                    classes="font-mono")

    ui.divider()

    emitted_html_block(
        "Emitted into <head>",
        f"<title>{state.text}</title>" if state.text else "(no change — decorator wins)",
    )


# ── MetaTag panel ────────────────────────────────────────────────────────


@refreshable(deps=[MetaTagPlayground])
def meta_tag_panel() -> None:
    state = MetaTagPlayground()
    # Side effect : actually appends a <meta> to this page's head.
    # Open dev tools to see it.
    kind = state.identifier_kind
    if state.identifier and state.content:
        if kind == "name":
            ui.meta_tag(name=state.identifier, content=state.content)
        elif kind == "property":
            ui.meta_tag(property=state.identifier, content=state.content)
        else:
            ui.meta_tag(http_equiv=state.identifier, content=state.content)

    with ui.grid(cols={"base": 1, "sm": 3}, gap="md"):
        with ui.vstack(gap="xs"):
            ui.text("identifier kind", color="muted", size="xs")
            ui.select(
                value=state.identifier_kind,
                options=[
                    ("name",       "name= (description / robots / twitter:*)"),
                    ("property",   "property= (og:*)"),
                    ("http_equiv", "http_equiv= (refresh / X-UA-Compatible)"),
                ],
                on_change=meta_tag_changed,
            )
        with ui.vstack(gap="xs"):
            ui.text("identifier value", color="muted", size="xs")
            ui.input(value=state.identifier, on_change=meta_tag_changed,
                     placeholder="description")
        with ui.vstack(gap="xs"):
            ui.text("content", color="muted", size="xs")
            ui.input(value=state.content, on_change=meta_tag_changed,
                     placeholder="Internal tools demo")

    ui.divider()

    # Mirror what landed in <head> as a hand-formatted string. We
    # don't go through ``serialize_html`` because the actual MetaTag
    # render writes to ``ctx.head_extras`` (no visible body footprint)
    # — the EMITTED HTML for this preview is straightforward to spell
    # out directly from the live state.
    if state.identifier and state.content:
        attr_name = kind.replace("_", "-")
        emitted = (
            f'<meta {attr_name}="{state.identifier}" '
            f'content="{state.content}"/>'
        )
    else:
        emitted = "(missing identifier or content — nothing emitted)"

    emitted_html_block("Emitted into <head>", emitted)



class IntervalDemo(ClientState, persist="memory"):
    """La porte du minuteur et son compteur.

    ``ClientState`` et pas ``PageState`` : tout le point de
    ``ui.interval`` est que la cadence s'arrête sans que le
    serveur ait une tâche à gérer. Un état serveur ramènerait
    exactement le cycle de vie qu'on évite.
    """

    running: bool = field(default=False)
    ticks:   int  = field(default=0)


class FilterDemo(ClientState, persist="memory"):
    """La saisie qui filtre. ``ClientState`` pour la même raison que
    ci-dessus : tout l'intérêt de ``filter_each`` est de filtrer SANS
    aller-retour, donc son état ne peut pas vivre au serveur."""

    query: str = field(default="")


#: Le jeu filtré. Court exprès — on démontre le mécanisme, pas la
#: pagination.
FRUITS: list[str] = [
    "abricot", "banane", "cerise", "citron", "figue", "fraise",
    "framboise", "grenade", "kiwi", "mangue", "myrtille", "pêche",
]


@download("/meta-demo.csv", filename="fruits.csv")
def fruits_csv() -> list[dict]:
    """La démo de ``@download`` — un vrai fichier, une vraie route.

    Au niveau MODULE et pas dans le corps de la page : ``@download``
    MARQUE une fonction, et l'app ramasse la marque à ``include()``.
    Déclarée dans un rendu, elle serait re-marquée à chaque requête et
    ne serait jamais montée.
    """
    return [{"fruit": f, "lettres": len(f)} for f in FRUITS]

# ── Page ─────────────────────────────────────────────────────────────────


def page() -> None:
    # Page-level title : overrides @page(title=...) when present
    # (the playground routes don't pass title= today, so this is the
    # final value).
    ui.title("Meta primitives — Playground")
    # A few static meta_tags so the head of THIS page actually carries
    # the social-card setup any production page would ship.
    ui.meta_tag(name="description",
                content="Bretzel meta primitives — Title / MetaTag / Fragment.")
    ui.meta_tag(property="og:title", content="Bretzel — Meta primitives")
    ui.meta_tag(property="og:type",  content="website")
    ui.meta_tag(name="twitter:card", content="summary")

    with ui.container():
        with ui.vstack():
            ui.heading("Meta primitives", level=1)
            ui.text(
                "Three Tier-11 primitives that don't render into the "
                "page body : ``ui.title`` rewrites the browser tab + "
                "the ``<title>`` element, ``ui.meta_tag`` injects "
                "``<meta>`` into ``<head>``, and ``ui.fragment`` "
                "groups children without a wrapping HTML tag. The live "
                "demo is the **browser tab title** + the document "
                "**``<head>``** (open dev tools to inspect).",
                color="muted",
            )

            # ── Card 1 — Title ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Title", level=2)
                    ui.text(
                        "``ui.title(\"…\")`` overrides the "
                        "``@page(title=…)`` decorator value at "
                        "render time. Useful when the title depends on "
                        "data the decorator couldn't know (current "
                        "user, loaded record, etc.). Last call wins ; "
                        "empty string falls through to the decorator.",
                        color="muted", size="sm",
                    )

                    ui.heading("Live playground", level=3)
                    ui.text(
                        "Type below — the browser tab updates "
                        "(partial-nav refresh flips ``bretzel:title``).",
                        color="muted", size="xs",
                    )
                    title_panel()

                    ui.divider()

                    ui.heading("Usage", level=3)
                    ui.code(
                        "@page(\"/users/{user_id}\", title=\"User\")\n"
                        "def user_detail(user_id: int) -> None:\n"
                        "    user = load_user(user_id)\n"
                        "    ui.title(f\"{user.name} — Users\")"
                        "  # overrides decorator\n"
                        "    with ui.container():\n"
                        "        ui.heading(user.name)",
                        lang="python",
                    )

            # ── Card 2 — MetaTag ────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("MetaTag", level=2)
                    ui.text(
                        "``ui.meta_tag(name=/property=/http_equiv=, "
                        "content=)`` appends a ``<meta>`` element to "
                        "the document head. Exactly ONE identifier "
                        "kwarg ; ``content=`` always required. "
                        "``charset`` and ``viewport`` are framework-"
                        "owned (cf. ``render/shell.py``) and "
                        "deliberately NOT exposed — overriding them "
                        "would only invite drift.",
                        color="muted", size="sm",
                    )

                    ui.heading("Live playground", level=3)
                    ui.text(
                        "Tweak below — the rendered ``<meta>`` lands "
                        "in this page's head (open dev tools to see "
                        "it). The emitted HTML preview below mirrors "
                        "what's injected.",
                        color="muted", size="xs",
                    )
                    meta_tag_panel()

                    ui.divider()

                    ui.heading("Common shapes", level=3)
                    ui.code(
                        "ui.meta_tag(name=\"description\",      "
                        "content=\"Internal tool for Acme\")\n"
                        "ui.meta_tag(name=\"twitter:card\",     "
                        "content=\"summary_large_image\")\n"
                        "ui.meta_tag(property=\"og:title\",     "
                        "content=\"Dashboard — Acme\")\n"
                        "ui.meta_tag(property=\"og:image\",     "
                        "content=\"https://acme.com/og.png\")\n"
                        "ui.meta_tag(http_equiv=\"refresh\",    "
                        "content=\"30; url=/logout\")",
                        lang="python",
                    )

            # ── Card 3 — Fragment ───────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Fragment", level=2)
                    ui.text(
                        "``with ui.fragment(): …`` groups children with "
                        "**no surrounding tag**. Use it inside helpers "
                        "that need to emit multiple children without "
                        "imposing a layout wrapper on every caller "
                        "(``ui.flex()`` / ``ui.hstack()`` would change "
                        "the layout context).",
                        color="muted", size="sm",
                    )

                    ui.heading("Side-by-side comparison", level=3)
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        with ui.vstack(gap="xs"):
                            ui.text("Without Fragment — wrapper visible",
                                    color="muted", size="xs")
                            with ui.card(padding="sm",
                                         classes="bg-muted/5"):
                                with ui.vstack(gap="sm"):
                                    ui.text("Header")
                                    with ui.hstack(gap="xs"):  # ← wrapper
                                        ui.button("A", size="sm")
                                        ui.button("B", size="sm")
                                    ui.text("Footer")
                            ui.text("→ buttons are nested inside a flex "
                                    "row ; the outer vstack sees 3 "
                                    "children.",
                                    color="muted", size="xs")
                        with ui.vstack(gap="xs"):
                            ui.text("With Fragment — flat children",
                                    color="muted", size="xs")
                            with ui.card(padding="sm",
                                         classes="bg-muted/5"):
                                with ui.vstack(gap="sm"):
                                    ui.text("Header")
                                    with ui.fragment():
                                        ui.button("A", size="sm")
                                        ui.button("B", size="sm")
                                    ui.text("Footer")
                            ui.text("→ buttons are direct children of "
                                    "the outer vstack (4 siblings) ; "
                                    "no wrapper element.",
                                    color="muted", size="xs")

                    ui.divider()

                    ui.heading("Helper composition", level=3)
                    ui.text(
                        "The classic use case : a helper that adds "
                        "buttons to whatever layout the caller uses, "
                        "without locking them into a flex row.",
                        color="muted", size="xs",
                    )
                    ui.code(
                        "def user_actions(user):\n"
                        "    with ui.fragment():\n"
                        "        ui.button(\"Edit\",   "
                        "on_click=...)\n"
                        "        ui.button(\"Delete\", "
                        "on_click=...)\n\n"
                        "with ui.hstack(gap=\"lg\"):\n"
                        "    user_actions(user)"
                        "  # buttons land flat in the hstack\n"
                        "    ui.button(\"Save\")"
                        "  # arrives as a 3rd sibling",
                        lang="python",
                    )

                    ui.divider()

                    ui.heading("Emitted HTML", level=3)
                    ui.text(
                        "The Fragment leaves no marker in the output — "
                        "its children appear in the parent's HTML as "
                        "if they had been written there directly.",
                        color="muted", size="xs",
                    )
                    demo = ui.hstack()
                    with demo:
                        with ui.fragment():
                            ui.button("Edit", size="sm")
                            ui.button("Delete", size="sm")
                        ui.button("Save", size="sm")
                    emitted_html_block("Emitted HTML", serialize_html(demo))

            # ── Card 4 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text(
                        "Inputs that surface user errors instead of "
                        "silently swallowing them.",
                        color="muted", size="sm",
                    )

                    ui.heading("Title", level=3)
                    with ui.vstack(gap="xs"):
                        ui.text(
                            "• Multiple ``ui.title()`` calls in the "
                            "same render scope → **last call wins**. "
                            "Layouts can set a fallback ; pages "
                            "override.",
                            color="muted", size="sm",
                        )
                        ui.text(
                            "• Empty string → **skipped** (better to "
                            "fall through to the decorator default "
                            "than ship ``<title></title>``).",
                            color="muted", size="sm",
                        )
                        ui.text(
                            "• Called outside a render scope → "
                            "**RuntimeError** (no silent loss).",
                            color="muted", size="sm",
                        )

                    ui.heading("MetaTag", level=3)
                    with ui.vstack(gap="xs"):
                        ui.text(
                            "• No identifier kwarg → **TypeError** "
                            "(``<meta content=…>`` alone is invalid "
                            "HTML).",
                            color="muted", size="sm",
                        )
                        ui.text(
                            "• Multiple identifier kwargs in one "
                            "call → **TypeError** (pick the one that "
                            "matches the semantics).",
                            color="muted", size="sm",
                        )
                        ui.text(
                            "• No auto-dedup — emit "
                            "``<meta name=\"description\">`` once. "
                            "The pipeline appends every call.",
                            color="muted", size="sm",
                        )

                    ui.heading("Fragment", level=3)
                    with ui.vstack(gap="xs"):
                        ui.text(
                            "• Any kwarg (``classes=`` / ``id=`` / "
                            "``style=``) → **TypeError** (no DOM "
                            "element to attach attrs to).",
                            color="muted", size="sm",
                        )
                        ui.text(
                            "• Empty Fragment → serializes to ``\"\"`` "
                            "(safe for ``if cond:`` blocks).",
                            color="muted", size="sm",
                        )
                        ui.text(
                            "• Fragments inside Fragments → fully "
                            "flatten (no \"fragment of fragments\" "
                            "intermediate).",
                            color="muted", size="sm",
                        )

            # ── Card 5 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text(
                        "Patterns the meta primitives unlock together.",
                        color="muted", size="sm",
                    )

                    ui.heading("Nested fragments flatten all the way",
                               level=3)
                    nested = ui.hstack()
                    with nested:
                        with ui.fragment():
                            ui.badge("A", color="primary")
                            with ui.fragment():
                                ui.badge("B", color="success")
                                ui.badge("C", color="warning")
                            ui.badge("D", color="error")
                    ui.text("→ 4 badges, all direct siblings of the "
                            "outer hstack. No nesting in the HTML.",
                            color="muted", size="xs")
                    emitted_html_block("Emitted HTML",
                                       serialize_html(nested))

                    ui.divider()

                    ui.heading("Fragment + conditional emit", level=3)
                    ui.text(
                        "An empty Fragment serializes to the empty "
                        "string — useful when the children are "
                        "conditional and you don't want a leftover "
                        "wrapper when the condition is false.",
                        color="muted", size="xs",
                    )
                    cond = ui.hstack()
                    with cond:
                        ui.text("Always here.")
                        with ui.fragment():
                            # Empty body — common when wrapped in `if`.
                            pass
                        ui.text("Also always here.")
                    emitted_html_block("Emitted HTML (empty fragment)",
                                       serialize_html(cond))

            # ── Card 6 — Interval ────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Interval", level=2)
                    ui.text(
                        "La quatrième primitive du groupe, et la seule "
                        "qui BOUGE : un minuteur caché. Elle est arrivée "
                        "ici le 2026-08-30, en supprimant ``/matrix`` — "
                        "qui était le seul endroit du playground où elle "
                        "était construite.",
                        color="muted", size="sm",
                    )
                    ui.text(
                        "``seconds=`` fixe la cadence, ``on_tick=`` ce "
                        "qui part à chaque battement, et ``active=`` la "
                        "porte. C'est ``active`` qui compte : lié à un "
                        "``ClientBinding``, il rend la cadence "
                        "arrêtable SANS cycle de vie côté serveur — "
                        "personne n'a de tâche à démarrer ni à tuer, un "
                        "interrupteur du navigateur suffit.",
                        color="muted", size="sm",
                    )

                    ui.heading("Live — un compteur qu'on coupe", level=3)
                    ticker = IntervalDemo()
                    with ui.hstack(gap="sm", align="center"):
                        ui.switch(checked=ticker.running,
                                  label="cadence active")
                        ui.text(
                            ClientExpression(
                                "'battements : ' + "
                                "($bz.state.IntervalDemo.default.ticks"
                                " || 0)"
                            ),
                            color="muted", size="sm",
                            classes="font-mono",
                        )
                    ui.interval(
                        seconds=1.0,
                        active=ticker.running,
                        on_tick=ticker.ticks.increment(),
                    )

                    ui.heading("Le HTML émis", level=3)
                    ui.text(
                        "Aucune surface visible : un nœud caché qui "
                        "porte sa cadence et sa porte. C'est pourquoi "
                        "il vit dans le groupe meta et non dans les "
                        "composants d'affichage.",
                        color="muted", size="xs",
                    )
                    emitted_html_block(
                        "Emitted HTML (Interval)",
                        serialize_html(
                            ui.interval(seconds=1.0,
                                        active=ticker.running,
                                        on_tick=ticker.ticks.increment())
                        ),
                    )

            with ui.card():
                with ui.vstack():
                    ui.heading("filter_each", level=2)
                    ui.text(
                        "La cinquième primitive du groupe, et elle "
                        "arrive ici le 2026-08-31 pour une raison qu'il "
                        "faut dire : ``ui.filter_each`` est PUBLIC et "
                        "n'était démontré NULLE PART. Sa seule page — "
                        "le hub filtrable — est partie avec ``/matrix`` "
                        "le 2026-08-30, et il ne restait qu'un probe "
                        "navigateur qui lançait un banc supprimé, donc "
                        "mort en silence.",
                        color="muted", size="sm",
                    )
                    ui.text(
                        "Ce qu'elle fait : elle enveloppe chaque ligne "
                        "d'un ``bz-show`` dérivé du framework, qui "
                        "compare ``text(item)`` à ``query``. Le filtre "
                        "est donc ENTIÈREMENT côté client — aucun "
                        "aller-retour, aucun JS écrit à la main — et "
                        "les lignes sont cachées, pas retirées.",
                        color="muted", size="sm",
                    )

                    ui.heading("Live — la liste se resserre à la frappe",
                               level=3)
                    filtre = FilterDemo()
                    ui.input(value=filtre.query, placeholder="Filtrer…",
                             size="sm", id="meta-filter-input")
                    with ui.vstack(gap="xs", id="meta-filter-rows"):
                        for fruit in ui.filter_each(
                            FRUITS,
                            query=filtre.query,
                            text=lambda f: f,
                            key=lambda f: f,
                            empty=lambda: ui.text(
                                "Aucun fruit ne correspond.",
                                color="muted", size="sm",
                            ),
                        ):
                            ui.text(fruit, size="sm")

                    ui.heading("Le HTML émis", level=3)
                    ui.text(
                        "Chaque ligne porte son ``bz-show`` : c'est ce "
                        "qui rend le filtre instantané, et ce qui "
                        "explique que le compte du DOM ne bouge pas "
                        "quand on tape.",
                        color="muted", size="xs",
                    )
                    emitted_html_block(
                        "Emitted HTML (filter_each)",
                        serialize_html(
                            ui.text("abricot", size="sm")
                        ),
                    )

            # ── Card 7 — A11y ────────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Verbes clients", level=2)
                    ui.text(
                        "``bretzel.copy`` / ``print_page`` / "
                        "``fullscreen`` — livrés le 2026-09-01. Ce ne "
                        "sont pas des composants, d'où leur place ici : "
                        "ils n'émettent aucun balisage, ils déclenchent "
                        "une action du NAVIGATEUR.",
                        color="muted", size="sm",
                    )
                    ui.text(
                        "Ils ne coûtent presque rien parce que le slot "
                        "existait déjà : ``on_<event>=`` est polymorphe "
                        "— un callable part en POST signé, une CHAÎNE "
                        "est de la source client évaluée sur place. "
                        "C'est le contrat de ``dialog.open()``, les "
                        "verbes s'y branchent sans plomberie neuve.",
                        color="muted", size="sm",
                    )

                    ui.heading("Live — copie ce que tu tapes", level=3)
                    ui.text(
                        "La valeur vit dans un ``ClientState``. Le verbe "
                        "interpole son CHEMIN, pas sa valeur au rendu : "
                        "modifie le champ, copie, colle — c'est ta "
                        "saisie qui sort, et le serveur ne l'a jamais "
                        "vue passer.",
                        color="muted", size="sm",
                    )
                    verbes = VerbDemo()
                    with ui.hstack(gap="sm", align="center"):
                        ui.input(value=verbes.secret, size="sm",
                                 id="meta-verb-input")
                        ui.button("Copier", size="sm",
                                  id="meta-verb-copy",
                                  on_click=bretzel.copy(verbes.secret))
                        ui.button("Imprimer", size="sm", variant="outline",
                                  id="meta-verb-print",
                                  on_click=bretzel.print_page())
                    ui.text(
                        "⚠️ Aucun retour visuel, et c'est le contrat : "
                        "le verbe copie, l'app câble le retour qu'elle "
                        "veut. Un ``ui.copy_button`` qui bascule deux "
                        "secondes reste la forme évidente le jour où le "
                        "besoin remonte.",
                        color="muted", size="sm",
                    )

                    ui.heading("Plein écran", level=3)
                    ui.text(
                        "``fullscreen()`` vise la page ; "
                        "``fullscreen(un_composant)`` vise un élément par "
                        "son ``id`` — même convention que l'API "
                        "impérative. Le navigateur EXIGE un geste de "
                        "l'utilisateur, ce qui est tenu par "
                        "construction : un verbe vit toujours dans un "
                        "``on_*=``.",
                        color="muted", size="sm",
                    )
                    # On garde la RÉFÉRENCE de la carte, exactement comme
                    # l'API impérative (``confirm = ui.dialog()`` puis
                    # ``confirm.open()``). Construire un second composant
                    # juste pour porter le même ``id`` marcherait à
                    # l'écran et émettrait un élément vide de plus — la
                    # première version de cette carte le faisait.
                    zone = ui.card(padding="sm", id="meta-verb-zone")
                    with zone:
                        ui.text("Cette carte peut passer en plein écran.",
                                size="sm")
                        ui.button("Plein écran", size="sm",
                                  variant="outline",
                                  id="meta-verb-fullscreen",
                                  on_click=bretzel.fullscreen(zone))

                    ui.heading("Partager et vibrer", level=3)
                    ui.text(
                        "``share()`` ouvre la feuille native — et quand "
                        "elle manque, ce qui est le cas NORMAL sur un "
                        "navigateur de bureau, elle COPIE l'URL. Sans "
                        "argument, c'est la page courante qui part : "
                        "depuis que l'état s'écrit dans l'adresse, l'URL "
                        "porte la vue, donc partager la page c'est "
                        "partager ce qu'on regarde.",
                        color="muted", size="sm",
                    )
                    with ui.hstack(gap="sm", align="center"):
                        ui.button("Partager cette vue", size="sm",
                                  variant="outline", id="meta-verb-share",
                                  on_click=bretzel.share(title="Bretzel · meta"))
                        ui.button("Vibrer", size="sm", variant="outline",
                                  id="meta-verb-vibrate",
                                  on_click=bretzel.vibrate([50, 30, 50]))
                    ui.text(
                        "``vibrate`` ne fait rien sur un ordinateur, et "
                        "c'est normal : la fonction existe partout, elle "
                        "n'a simplement aucun matériel à piloter. C'est "
                        "ce qui la rend gratuite — il n'y a aucune "
                        "absence à gérer, contrairement à ``share``.",
                        color="muted", size="sm",
                    )

                    ui.heading("@download — un vrai fichier", level=3)
                    ui.text(
                        "Ce n'est PAS un verbe : la réponse d'une action "
                        "est avalée par le bridge et appliquée en "
                        "``<bz-patch>``, alors qu'un téléchargement doit "
                        "ÊTRE le fichier. C'est donc un lien ORDINAIRE, "
                        "pas un ``on_click=`` — et il ne se fait pas "
                        "avaler par le ``hx-boost`` de la coque, ce que "
                        "seul un navigateur peut vérifier "
                        "(``tests/probes/probe_download.py``).",
                        color="muted", size="sm",
                    )
                    # ``download=True`` est OBLIGATOIRE ici, et ce n'est
                    # pas de la décoration : sans lui la coque avale le
                    # lien en ``hx-boost`` et injecte le CSV dans la
                    # page au lieu de le télécharger. Mesuré.
                    ui.link("Télécharger les fruits (CSV)",
                            href="/meta-demo.csv", download=True,
                            id="meta-download-link")
                    ui.text(
                        "La fonction rend une ``list[dict]`` et le "
                        "framework en fait un CSV : en-têtes déduits des "
                        "clés, BOM UTF-8 pour qu'Excel ne mange pas les "
                        "accents, citation RFC 4180. Elle peut aussi "
                        "rendre une ``str``, des ``bytes``, ou une "
                        "``Response`` construite à la main.",
                        color="muted", size="sm",
                    )

                    ui.heading("Le presse-papiers a une condition", level=3)
                    ui.text(
                        "``navigator.clipboard`` exige un contexte "
                        "SÉCURISÉ. ``https://`` et ``http://localhost`` "
                        "en sont ; ``http://192.168.1.20:8000`` n'en est "
                        "PAS — et c'est très exactement la façon dont un "
                        "outil interne se sert. Là-bas l'API vaut "
                        "``undefined``, et un appel nu ne ferait rien, "
                        "sans un mot. D'où le repli sur "
                        "``document.execCommand`` dans "
                        "``22_verbs.js`` : déprécié, et le seul chemin "
                        "qui existe là-bas.",
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "No keyboard-test control here — none of "
                        "these three primitives render a DOM node, "
                        "so there is nothing to Tab onto. What "
                        "actually matters for accessibility :",
                        color="muted", size="sm",
                    )
                    with ui.vstack(gap="xs"):
                        ui.text(
                            "• ``ui.title()`` — most screen readers "
                            "announce a changed ``<title>`` on "
                            "partial-nav (SPA-style) updates, same "
                            "as a full page load. Keep it accurate "
                            "and unique per page ; don't leave it "
                            "on a stale value after navigating.",
                            color="muted", size="sm",
                        )
                        ui.text(
                            "• ``ui.meta_tag()`` — ``name=\"description\"`` "
                            "and the ``og:*`` family are read by "
                            "search engines and social-share "
                            "unfurlers, not assistive tech directly "
                            "— but an accurate description IS part "
                            "of a page's overall accessibility (it's "
                            "often the first thing a screen-reader "
                            "user hears about a link before opening "
                            "it).",
                            color="muted", size="sm",
                        )
                        ui.text(
                            "• ``ui.fragment()`` — zero accessibility "
                            "surface : it emits no element and no "
                            "attribute, purely a Python-side grouping "
                            "construct.",
                            color="muted", size="sm",
                        )
