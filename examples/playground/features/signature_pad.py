"""``SignaturePad`` test bench.

Dix cards. ``SignaturePad.BINDABLE_PROPS = ("value",)`` — la data-URL du
tracé est bindable (le client l'écrit en dessinant) ; placeholder /
clear_label / disabled / size / color restent du design-time. Event :
``change``. Impératif : ``.clear()``.
"""

from urllib.parse import quote

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field
from examples.playground.features.inspection import emitted_html_block

PATH = "/signature_pad"


#: Une signature « déjà là » pour la démo du dossier rouvert.
#:
#: Une data-URI SVG plutôt qu'un PNG en base64, pour deux raisons : elle
#: reste LISIBLE dans la source (un blob base64 ne dit rien de ce qu'il
#: dessine), et elle exerce l'autre branche de data-URI — celle qui est
#: percent-encodée, sans padding ``=``. Le canvas charge les deux
#: pareil.
#:
#: ⚠️ La première version de cette carte utilisait un PNG 1×1
#: TRANSPARENT : même une fois le chargement corrigé, elle n'aurait rien
#: montré. Une démo qui ne peut pas échouer visiblement ne démontre rien.
#: ⚠️ La couleur s'écrit ``#334155`` en CLAIR : c'est ``quote`` qui
#: l'encode en ``%23``. L'écrire déjà encodée la fait doubler
#: (``%2523``), le SVG lit alors une couleur invalide, et le tracé ne
#: rend RIEN — mesuré, et invisible autrement qu'en comptant les pixels.
EXISTING_SIGNATURE = "data:image/svg+xml," + quote(
    "<svg xmlns='http://www.w3.org/2000/svg' width='320' height='110'>"
    "<path d='M20 78 C 55 18, 78 96, 108 52 S 156 12, 186 66 "
    "S 236 88, 262 34' fill='none' stroke='#334155' stroke-width='4' "
    "stroke-linecap='round' stroke-linejoin='round'/>"
    "</svg>"
)

SIZES = ["xs", "sm", "md", "lg", "xl"]
COLORS = ["primary", "secondary", "success", "warning",
          "error", "info", "muted"]


class SignaturePadPlayground(PageState):
    value: str = field(default="")
    placeholder: str = field(default="Sign here")
    clear_label: str = field(default="Clear")
    disabled: bool = field(default=False)
    size: str = field(default="md")
    color: str = field(default="primary")
    name: str = field(default="")
    # Escape hatches.
    classes: str = field(default="")
    custom_id: str = field(default="")
    aria_label: str = field(default="")
    style: str = field(default="")
    extra_attrs: str = field(default="")
    # Universal modifiers.
    visible: str = field(default="on")
    tooltip: str = field(default="")
    # Event-handler shape.
    on_change_mode: str = field(default="none")


class SignaturePadEvents(PageState):
    log: list = field(default_factory=list)


# Le cas CANONIQUE du composant : la signature vit dans un état SERVEUR,
# et l'autoname dérive le ``name`` de l'input caché depuis le champ. Rien
# à câbler — ``_hydrate_state`` la réécrit à la soumission.
class Contract(PageState):
    signature: str = field(default="")
    signed_by: str = field(default="")


class SignaturePadClient(ClientState, persist="memory"):
    sig: str = field(default="")


class SignaturePadClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


# ⚠️ Le state qui rend le ``change`` du banc LISIBLE. Sans binding ni
# ``name=``, le composant ne pose AUCUN ``name`` sur son input caché
# (choix délibéré du socle : un name par défaut injecterait un champ
# parasite dans chaque formulaire englobant), donc le handler part avec
# une FormData vide. Leçon payée sur le banc /resizable le même jour.
class SignaturePadServerEvents(ClientState, persist="memory"):
    value: str = field(default="")


def log(name: str) -> None:
    state = SignaturePadEvents()
    state.log = [*state.log, name]


def log_change(value: str = "") -> None:
    # On journalise la TAILLE et le préfixe, pas la data-URL : trente
    # kilo-octets de base64 dans un log rendraient la page illisible.
    head = value[:30] + "…" if len(value) > 30 else value
    log(f"change(len={len(value)}, head={head!r})")


def clear_log() -> None:
    state = SignaturePadEvents()
    state.log = []


def server_changed(state: SignaturePadPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed control's value
    # into ``state`` (coerced + persisted).
    pass


def playground_change_handler(value: str = "") -> None:
    log(f"playground-server-change(len={len(value)})")


def sign_contract(doc: Contract) -> None:
    """Le handler de la démo formulaire — hydraté depuis la soumission.

    C'est LE point du composant : ``doc.signature`` porte la data-URL
    sans qu'aucun endpoint ni encodage n'ait été écrit.
    """
    log(
        f"submit(signed_by={doc.signed_by!r}, "
        f"signature_len={len(doc.signature)})"
    )


_CLIENT_CHANGE_EXPR = "$el.classList.toggle('ring-4')"


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def build_preview(state: SignaturePadPlayground) -> dict:
    kwargs: dict = {
        "disabled": state.disabled,
        "size": state.size,
        "color": state.color,
    }
    # Chaîne vide = ne pas passer le kwarg.
    if state.placeholder:
        kwargs["placeholder"] = state.placeholder
    if state.clear_label:
        kwargs["clear_label"] = state.clear_label
    if state.value:
        kwargs["value"] = state.value
    if state.name:
        kwargs["name"] = state.name
    if state.classes:
        kwargs["classes"] = state.classes
    if state.custom_id:
        kwargs["id"] = state.custom_id
    if state.style:
        kwargs["style"] = state.style
    attrs: dict = {}
    if state.aria_label:
        attrs["aria-label"] = state.aria_label
    attrs.update(parse_extra_attrs(state.extra_attrs))
    if attrs:
        kwargs["attrs"] = attrs
    if state.tooltip:
        kwargs["tooltip"] = state.tooltip
    if state.visible == "off":
        kwargs["visible"] = False
    if state.on_change_mode == "server":
        kwargs["on_change"] = playground_change_handler
    elif state.on_change_mode == "client":
        kwargs["on_change"] = _CLIENT_CHANGE_EXPR
    elif state.on_change_mode == "both":
        kwargs["on_change"] = [playground_change_handler,
                               _CLIENT_CHANGE_EXPR]
    return kwargs


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[SignaturePadPlayground])
def server_panel() -> None:
    state = SignaturePadPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("placeholder (vide = pas d'invite)"):
            ui.input(value=state.placeholder, placeholder="Sign here",
                     on_change=server_changed)
        with control("clear_label (vide = pas de bouton)"):
            ui.input(value=state.clear_label, placeholder="Clear",
                     on_change=server_changed)
        with control("disabled"):
            ui.switch(checked=state.disabled, on_change=server_changed)
        with control("size (hauteur du cadre)"):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("name (overrides autoname)"):
            ui.input(value=state.name, placeholder="signature",
                     on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="!h-64",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-pad",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label, placeholder="Signature",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="max-width: 420px",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=pad",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, placeholder="Signez ici",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)
        with control("on_change mode"):
            ui.select(value=state.on_change_mode,
                      options=[("none", "None (no handler)"),
                               ("server", "Server callable"),
                               ("client", "Client string"),
                               ("both", "Both (list)")],
                      on_change=server_changed)

    ui.divider()

    kwargs = build_preview(state)
    ui.signature_pad(**kwargs)

    ui.divider()

    emitted_html_block(
        "Emitted HTML (SignaturePad + son canvas + le porteur caché)",
        serialize_html(ui.signature_pad(**kwargs)),
    )


@refreshable(deps=[SignaturePadEvents])
def events_panel() -> None:
    state = SignaturePadEvents()

    ui.text(
        "Le pad émet UN ``change`` au LEVER du stylo, jamais pendant le "
        "tracé — un PNG pèse des dizaines de kilo-octets, et l'émettre "
        "par frame ferait partir autant de POST. Signez ci-dessous et "
        "levez le doigt : une seule ligne apparaît.",
        color="muted", size="sm",
    )

    sig_state = SignaturePadServerEvents()
    with ui.vstack():
        ui.signature_pad(value=sig_state.value, on_change=log_change)

    ui.divider()

    ui.heading("Le cas canonique — un formulaire", level=3)
    ui.text(
        "La signature vit dans un ServerState. L'autoname dérive "
        "``name=\"signature\"`` du champ, et le handler la reçoit "
        "hydratée : ni endpoint, ni encodage à écrire.",
        color="muted", size="sm",
    )
    doc = Contract()
    with ui.form(on_submit=sign_contract), ui.vstack(gap="sm"):
        ui.input(value=doc.signed_by, placeholder="Votre nom")
        ui.signature_pad(value=doc.signature)
        with ui.hstack():
            ui.button("Signer", type="submit")

    ui.divider()

    with ui.hstack(justify="between", align="center"):
        ui.text("Live log (newest first, last 10)", color="muted", size="sm")
        ui.button("Clear", variant="ghost", size="xs",
                  on_click=clear_log, disabled=not state.log)

    if state.log:
        with ui.vstack(gap="xs"):
            for i, evt in enumerate(reversed(state.log[-10:]), 1):
                ui.text(f"{i}. {evt}",
                        color="muted", size="sm", classes="font-mono")
    else:
        ui.text("(no events yet — signez le pad ci-dessus)",
                color="muted", size="sm")

    ui.divider()

    emitted_html_block(
        "Emitted HTML (SignaturePad with on_change handler)",
        serialize_html(
            ui.signature_pad(value=sig_state.value, on_change=log_change)
        ),
    )


def page() -> None:
    with ui.container(), ui.vstack():
        ui.heading("Signature pad", level=1)
        ui.text(
            "Signer au doigt ou à la souris, dans un formulaire. La "
            "valeur est un PNG en data-URL, portée par un input caché "
            "nommé — donc elle part avec le formulaire comme un champ "
            "ordinaire, et ton ServerState la reçoit hydratée. Le "
            "premier et le seul <canvas> du dépôt.",
            color="muted",
        )

        # ── Card 1 — Reference ──────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Reference", level=2)
            ui.text("Visual scan of every prop.",
                    color="muted", size="sm")

            ui.heading("Basic", level=3)
            ui.signature_pad()

            ui.heading("Sizes (hauteur du cadre)", level=3)
            ui.text(
                "Le seul axe de taille qu'un pad ait : un <canvas> n'a "
                "AUCUNE dimension intrinsèque, donc sans hauteur "
                "déclarée il fait zéro pixel.",
                color="muted", size="xs",
            )
            for s in SIZES:
                ui.text(f"size={s}", color="muted", size="xs")
                ui.signature_pad(size=s)

            ui.heading("Colors (cadre focalisé + bouton)", level=3)
            ui.text(
                "La couleur ne teinte PAS l'encre : le trait prend la "
                "couleur de texte, pour rester lisible dans les deux "
                "thèmes. Un pen_color= aurait figé une encre invisible "
                "sur l'autre fond.",
                color="muted", size="xs",
            )
            for c in COLORS:
                ui.signature_pad(color=c, size="sm", placeholder=c)

            ui.heading("disabled", level=3)
            ui.text(
                "Le cadre passe en trait plein et se grise : un pad "
                "signé ne doit plus INVITER à signer.",
                color="muted", size="xs",
            )
            ui.signature_pad(disabled=True)

        # ── Card 2 — Slots ──────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Slots", level=2)
            ui.text(
                "Deux textes, et pas de sous-composant : l'invite et le "
                "libellé du bouton. Vider l'un le fait DISPARAÎTRE — "
                "c'est l'échappatoire pour un pad sans invite, ou sans "
                "bouton parce que la page en a déjà un ailleurs.",
                color="muted", size="sm",
            )

            ui.heading("placeholder personnalisé", level=3)
            ui.signature_pad(placeholder="Signez dans le cadre")

            ui.heading("Sans invite", level=3)
            ui.signature_pad(placeholder="")

            ui.heading("Sans bouton Effacer", level=3)
            ui.signature_pad(clear_label="")

            ui.heading("Libellé du bouton traduit", level=3)
            ui.signature_pad(clear_label="Effacer",
                             placeholder="Signez ici")

        # ── Card 3 — Edge cases ─────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Edge cases", level=2)
            ui.text("Edge inputs and exotic combinations.",
                    color="muted", size="sm")

            ui.heading("Ni invite ni bouton", level=3)
            ui.text("Un cadre nu — pas une erreur.",
                    color="muted", size="xs")
            ui.signature_pad(placeholder="", clear_label="")

            ui.heading("Invite très longue", level=3)
            ui.signature_pad(
                placeholder="Signez ici en utilisant votre doigt, votre "
                            "stylet ou votre souris, puis validez"
            )

            ui.heading("Une signature déjà là", level=3)
            ui.text(
                "Un dossier rouvert : la data-URL est rendue au SSR, "
                "chargée à l'hydratation et peinte SOUS les traits "
                "neufs. Signez par-dessus : les deux partent ensemble. "
                "Effacer emporte les deux aussi — « effacer » veut dire "
                "un cadre vide, pas « revenir à la signature d'avant ».",
                color="muted", size="xs",
            )
            ui.signature_pad(value=EXISTING_SIGNATURE)

            ui.heading("Dans un cadre étroit", level=3)
            ui.text(
                "Le pad remplit la place qu'on lui donne — il n'a "
                "aucune largeur intrinsèque à laquelle se réduire.",
                color="muted", size="xs",
            )
            with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                ui.signature_pad(size="sm")
                ui.text("Cellule voisine.", color="muted")
                ui.text("Autre voisine.", color="muted")

        # ── Card 4 — Composability ──────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Composability", level=2)
            ui.text("SignaturePad dans ses contextes habituels.",
                    color="muted", size="sm")

            ui.heading("Dans un ui.form_field", level=3)
            with ui.form_field(label="Signature",
                               hint="Signez dans le cadre ci-dessus"):
                ui.signature_pad(size="sm")

            ui.heading("Dans un ui.dialog", level=3)
            with ui.dialog(title="Signer le contrat", width="lg") as dlg, \
                    ui.vstack():
                ui.signature_pad()
            ui.button("Ouvrir le dialogue", on_click=dlg.open())

            ui.heading("Dans un panneau redimensionnable", level=3)
            ui.text(
                "Le test qui compte, et le seul qu'un screenshot ne "
                "montre pas : redimensionner un <canvas> l'EFFACE. "
                "Signez, tirez la poignée — la signature doit survivre.",
                color="muted", size="xs",
            )
            ui.text(
                "⚠️ Noter la composition : un panneau est un EMPLACEMENT, "
                "il ne rembourre pas. C'est le vstack qu'on met dedans "
                "qui pose le p-4 — sinon le pad colle au bord et au "
                "séparateur. Les surfaces rembourrent (card, dialog), "
                "les emplacements non (panneau, slide, tab panel).",
                color="muted", size="xs",
            )
            with ui.resizable(sizes=[60, 40], style="height: 260px"):
                with ui.resizable_panel(min_size=30):
                    with ui.vstack(gap="sm", classes="p-4 h-full"):
                        ui.text("Signez, puis tirez la poignée.",
                                color="muted", size="xs")
                        ui.signature_pad(size="sm")
                with ui.resizable_panel():
                    with ui.vstack(classes="p-4"):
                        ui.text("Le panneau voisin.", color="muted")

        # ── Card 5 — A11y ───────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("A11y", level=2)
            ui.text(
                "Le <canvas> est aria-hidden À DESSEIN : ce qui est "
                "annoncé et atteignable au clavier, c'est l'input caché "
                "(un vrai contrôle de formulaire, avec son name) et le "
                "bouton Effacer. Poser un rôle sur une surface de "
                "dessin annoncerait un contrôle qu'aucune touche ne "
                "pilote — la moitié d'un motif ARIA vaut moins que pas "
                "de motif du tout.",
                color="muted", size="sm",
            )
            ui.signature_pad(aria_label="Demo signature")

        # ── Card 6 — Server playground ──────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Server playground", level=2)
            ui.text(
                "Every SignaturePad prop AND every escape hatch is "
                "wired to a control ; the preview AND the emitted HTML "
                "both refresh on every change.",
                color="muted", size="sm",
            )
            server_panel()

        # ── Card 7 — Server events ──────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Server events", level=2)
            events_panel()

        # ── Card 8 — Client playground ──────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Client playground", level=2)
            ui.text(
                "Mirror of SignaturePad's BINDABLE_PROPS = ('value',). "
                "⚠️ À n'utiliser que si un AUTRE composant doit lire la "
                "signature côté client : le snapshot ClientState part "
                "ENTIER à chaque POST d'action, donc un pad lié renvoie "
                "ses dizaines de kilo-octets à chaque clic de la page. "
                "Le cas normal, c'est un ServerState (carte « Server "
                "events »).",
                color="muted", size="sm",
            )
            client = SignaturePadClient()
            ui.signature_pad(value=client.sig)

            ui.text(
                ClientExpression(
                    "'octets dans le store : ' + "
                    "(($bz.state.SignaturePadClient.default.sig || '')"
                    ".length)"
                ),
                color="muted", size="sm", classes="font-mono",
            )

            ui.divider()

            emitted_html_block(
                "Emitted HTML — le porteur lit la cellule du store "
                "directement ; le runtime y écrit au lever du stylo.",
                serialize_html(ui.signature_pad(value=client.sig)),
            )

        # ── Card 9 — External controls — the 3 modes ────────────
        with ui.card(), ui.vstack():
            ui.heading("External controls — the 3 modes", level=2)
            ui.text(
                ".clear() dispatche TOUJOURS un event DOM, binding ou "
                "pas : vider n'est pas « écrire la chaîne vide », il "
                "faut aussi jeter les points gardés en mémoire et "
                "repeindre — et seul le runtime sait le faire.",
                color="muted", size="sm",
            )

            ui.heading("Mode 1 — Imperative only (default)", level=3)
            m1 = ui.signature_pad()
            with ui.hstack(gap="sm"):
                ui.button("Effacer", variant="outline",
                          on_click=m1.clear())

            ui.divider()

            ui.heading("Mode 2 — ClientBinding only", level=3)
            bound = SignaturePadClient(key="binding_only")
            ui.signature_pad(value=bound.sig)
            ui.text(
                ClientExpression(
                    "(($bz.state.SignaturePadClient.binding_only.sig "
                    "|| '').length ? 'signé' : 'vide')"
                ),
                color="muted", size="sm",
            )

            ui.divider()

            ui.heading("Mode 3 — Both", level=3)
            both = SignaturePadClient(key="both")
            m3 = ui.signature_pad(value=both.sig)
            with ui.hstack(gap="sm", align="center"):
                ui.button("Effacer", variant="outline",
                          on_click=m3.clear())
                ui.text(
                    ClientExpression(
                        "'octets = ' + "
                        "(($bz.state.SignaturePadClient.both.sig "
                        "|| '').length)"
                    ),
                    color="muted", size="sm", classes="font-mono",
                )

            ui.divider()

            emitted_html_block(
                "Emitted HTML — la root porte bz-on:bz-clear, le "
                "récepteur vers lequel .clear() dispatche.",
                serialize_html(ui.signature_pad(value=both.sig)),
            )

        # ── Card 10 — Client events ─────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Client events", level=2)
            ui.text("change wired to a client expression that pushes "
                    "the payload SIZE onto a ClientState list. Zero "
                    "network — et on pousse la taille, pas la "
                    "data-URL : un log de PNG en base64 est illisible.",
                    color="muted", size="sm")
            cevents = SignaturePadClientEvents()
            _size = ClientExpression("($event.target.value || '').length")
            ui.signature_pad(on_change=cevents.log.push(_size))

            ui.divider()

            with ui.hstack(justify="between", align="center"):
                ui.text("Live log (client-reactive)",
                        color="muted", size="sm")
                ui.button("Clear", variant="ghost", size="xs",
                          on_click=cevents.log.clear())

            ui.divider()

            log_text = ClientExpression(
                '($bz.state.SignaturePadClientEvents.default.log'
                ' || []).join("\\n") || "(no events yet)"'
            )
            ui.text(log_text,
                    color="muted", size="sm",
                    classes="font-mono whitespace-pre")

            ui.divider()

            emitted_html_block(
                "Emitted HTML — le handler bz-on:change est relocalisé "
                "sur l'input caché, dont le bz-effect re-tire un change "
                "à chaque lever de stylo.",
                serialize_html(
                    ui.signature_pad(on_change=cevents.log.push(_size))
                ),
            )
