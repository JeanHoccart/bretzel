"""features/settings — écran 10 : les préférences, et la validation.

Ce que cet écran met sous contrainte : ``ui.form`` + ``ui.form_field`` +
validation + ``ui.toggle_group`` + ``ui.select`` **en densité** — dix champs
dans une page, pas un champ dans une carte de démo. C'est là qu'on voit si
les hauteurs s'alignent quand un `switch`, un `select`, un `toggle_group` et
un `input` se suivent dans la même grille.

La validation est le second sujet. Un validateur qui **lève** peuple
``form.errors``, et un ``ui.form_field`` sans ``error=`` déduit son champ de
l'entrée qu'il enveloppe et affiche le message tout seul. Le seul câblage à
faire au call-site est de ne pas écrire quand ``form.errors`` n'est pas vide.
"""

from __future__ import annotations

from bretzel import Feature, page, refreshable, ui
from bretzel.state import UserState, field, validator
from bretzel.theme import ColorScheme
from examples.crm.features.shell import shell

DENSITIES: tuple[tuple[str, str], ...] = (
    ("sm", "Compacte"), ("md", "Normale"), ("lg", "Aérée"),
)
#: Les trois modes que le socle comprend. ``"system"`` suit la préférence
#: du système d'exploitation ; ``"auto"`` en est un alias hérité, non
#: proposé ici — une seule façon de faire chaque chose.
SCHEMES: tuple[tuple[str, str], ...] = (
    ("light", "Clair"), ("dark", "Sombre"), ("system", "Système"),
)
LANDINGS: tuple[tuple[str, str], ...] = (
    ("/", "Pipeline"), ("/comptes", "Comptes"), ("/contacts", "Contacts"),
    ("/activites", "Activités"), ("/rapports", "Rapports"),
)
PER_PAGE: tuple[tuple[str, str], ...] = (
    ("10", "10 lignes"), ("25", "25 lignes"), ("50", "50 lignes"),
    ("100", "100 lignes"),
)
#: Multi-sélection : ce sont des canaux, pas des modes. Un `toggle_group`
#: `multiple=True` dit ça mieux qu'une rangée de `switch`, qui laisserait
#: croire que les trois sont indépendants de la même façon qu'un réglage.
CHANNELS: tuple[tuple[str, str], ...] = (
    ("app", "Dans l'app"), ("mail", "Par email"), ("digest", "Résumé quotidien"),
)


class Preferences(UserState):
    """Ce que l'utilisateur a choisi.

    ``UserState`` depuis l'ajout des comptes — c'était un ``SessionState``
    tant que l'app n'avait pas de connexion. Le changement n'est pas
    cosmétique : les réglages suivent maintenant la PERSONNE, donc ils
    survivent au changement de navigateur et ne suivent PAS le poste. Se
    déconnecter fait tourner la session, ce qui aurait effacé des
    préférences portées par elle.

    ⚠️ Un ``UserState`` lève ``AuthRequiredError`` (401) hors connexion.
    Cette classe est lue par la liste de contacts (« lignes par page ») :
    tout ce qui la touche est donc derrière la garde, par construction.
    """

    densite: str = field(default='md')
    atterrissage: str = field(default='/')
    par_page: str = field(default='25')
    #: ``list``, parce qu'une sélection multiple EST une liste. Le champ
    #: caché du composant reposte du JSON, et le socle le décode au passage
    #: (``_coerce_composite``) — l'app n'a plus rien à défaire. Elle l'a eu
    #: à faire : c'était le finding 19 du chantier, réparé depuis.
    canaux: list = field(default_factory=lambda: ["app"])
    email_rapport: str = field(default='')
    signature: str = field(default='')
    archiver_perdus: bool = field(default=True)

    @validator("canaux")
    def _canaux(cls, value: list) -> list:
        """Ne garde que des canaux connus. Le décodage JSON, lui, est fait
        par le socle avant d'arriver ici."""
        keys = {k for k, _label in CHANNELS}
        return [v for v in value if v in keys]

    @validator("email_rapport")
    def _email(cls, value: str) -> str:
        """Lève sur une adresse invalide — ``form.errors`` la recueille et le
        ``form_field`` qui enveloppe l'entrée l'affiche sans câblage."""
        clean = (value or "").strip().lower()[:120]
        if not clean:
            return ""
        if "@" not in clean or clean.startswith("@") or clean.endswith("@"):
            raise ValueError("Adresse invalide — il manque un @ ou un domaine.")
        if "." not in clean.rsplit("@", 1)[-1]:
            raise ValueError("Le domaine doit contenir un point.")
        return clean

    @validator("signature")
    def _signature(cls, value: str) -> str:
        clean = (value or "").strip()
        if len(clean) > 240:
            raise ValueError("240 caractères au plus — c'est un pied de mail.")
        return clean

    @validator("densite")
    def _densite(cls, value: str) -> str:
        return value if value in {k for k, _l in DENSITIES} else "md"

    @validator("par_page")
    def _par_page(cls, value: str) -> str:
        return value if value in {k for k, _l in PER_PAGE} else "25"


def save_preferences(form: Preferences) -> None:
    """Le garde tient en une ligne : rien n'est confirmé si un champ a levé.

    Les valeurs valides SONT déjà écrites (chaque ``__set__`` a réussi) — ce
    que ce garde empêche, c'est de dire « enregistré » alors que deux champs
    sur dix ont été refusés.
    """
    if form.errors:
        ui.notification("Corrige les champs en rouge.", variant="error",
                        duration_ms=2500)
        return
    ui.notification("Préférences enregistrées", variant="success",
                    duration_ms=2000)


def reset_preferences() -> None:
    prefs = Preferences()
    prefs.densite, prefs.atterrissage, prefs.par_page = "md", "/", "25"
    prefs.canaux = ["app"]
    prefs.email_rapport, prefs.signature = "", ""
    prefs.archiver_perdus = True
    ui.notification("Préférences remises à zéro", variant="info",
                    duration_ms=2000)


@refreshable(deps=[Preferences])
def preferences_form() -> None:
    prefs = Preferences()
    with ui.form(on_submit=save_preferences):
        with ui.vstack(gap="lg"):
            with ui.card(padding="md"):
                with ui.vstack(gap="md"):
                    ui.heading("Affichage", level=2, size="md")
                    # ``min_col`` et non des paliers de fenêtre : un
                    # préfixe ``xl:`` lit la largeur du VIEWPORT, pas
                    # celle que la grille a vraiment. Sous cette coque,
                    # la barre latérale prend 256 px — donc sur une
                    # fenêtre de 1440 la grille n'a que ~1024 px, restait
                    # à quatre colonnes, et chaque cellule tombait à
                    # 244 px pour un ``ui.toggle_group`` qui en demande
                    # 256. Mesuré : 11,9 px par-dessus le voisin.
                    with ui.grid(min_col="16rem", gap="md"):
                        # ⚠️ Le SEUL réglage de cette page qui ne passe pas
                        # par le serveur. ``ColorScheme`` est un
                        # ``ClientState`` du framework, persisté en
                        # ``localStorage`` : le ``toggle_group`` s'y lie
                        # directement (``$bz.state.ColorScheme.default.mode``),
                        # donc le thème bascule sans aller-retour et sans
                        # « Enregistrer ». Il n'est pas dans ``Preferences``
                        # pour cette raison — l'y mettre le ferait attendre
                        # une soumission de formulaire pour changer une
                        # couleur.
                        with ui.form_field(
                            label="Thème",
                            hint="Suivi du système par défaut.",
                        ):
                            ui.toggle_group(value=ColorScheme().mode,
                                            options=list(SCHEMES),
                                            size=prefs.densite)
                        with ui.form_field(
                            label="Densité",
                            hint="S'applique aux tableaux et aux listes.",
                        ):
                            ui.toggle_group(value=prefs.densite,
                                            options=list(DENSITIES),
                                            size=prefs.densite)
                        with ui.form_field(label="Page d'accueil"):
                            ui.select(value=prefs.atterrissage,
                                      options=list(LANDINGS),
                                      size=prefs.densite)
                        with ui.form_field(label="Lignes par page"):
                            ui.select(value=prefs.par_page,
                                      options=list(PER_PAGE),
                                      size=prefs.densite)

            with ui.card(padding="md"):
                with ui.vstack(gap="md"):
                    ui.heading("Notifications", level=2, size="md")
                    with ui.grid(min_col="16rem", gap="md"):
                        with ui.form_field(
                            label="Canaux",
                            hint="Plusieurs choix possibles.",
                        ):
                            ui.toggle_group(value=prefs.canaux,
                                            options=list(CHANNELS),
                                            multiple=True, size=prefs.densite)
                        with ui.form_field(
                            label="Email de rapport",
                            hint="Vide = pas d'envoi.",
                        ):
                            ui.input(value=prefs.email_rapport, type="email",
                                     icon_left="mail", size=prefs.densite,
                                     placeholder="moi@exemple.fr")
                        with ui.form_field(label="Affaires perdues"):
                            # Pas de ``on_change=`` : une case décochée ne
                            # poste rien en HTML, mais le socle émet
                            # désormais un compagnon caché qui porte le
                            # ``false``. C'était le finding 20 du chantier —
                            # il fallait un handler pour qu'un interrupteur
                            # puisse s'éteindre.
                            ui.switch(checked=prefs.archiver_perdus,
                                      label="Archiver automatiquement",
                                      size=prefs.densite)

            with ui.card(padding="md"):
                with ui.vstack(gap="md"):
                    ui.heading("Signature", level=2, size="md")
                    # ⚠️ « Propriétaire par défaut » a été RETIRÉ avec
                    # l'arrivée des comptes : pour un commercial le seul
                    # choix légal est lui-même, et pour la direction c'est
                    # le sélecteur de la barre latérale. Un réglage qui ne
                    # peut prendre qu'une valeur n'est pas un réglage.
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        with ui.form_field(
                            label="Pied de message",
                            hint="240 caractères au plus.",
                        ):
                            ui.textarea(value=prefs.signature, rows=3,
                                        size=prefs.densite,
                                        placeholder="Cordialement,…")

            with ui.hstack(justify="end", gap="sm"):
                ui.button("Remettre à zéro", variant="ghost",
                          icon_left="rotate-ccw", on_click=reset_preferences)
                ui.button("Enregistrer", type="submit", color="primary",
                          icon_left="save")


@page("/parametres", layout=shell, title="Paramètres")
def settings_page() -> None:
    with ui.vstack(gap="lg"):
        ui.heading("Paramètres", level=1, size="2xl")
        preferences_form()


feature = Feature(
    name="settings",
    kind="page",
    provides=[settings_page, Preferences],
    uses=[],
)
