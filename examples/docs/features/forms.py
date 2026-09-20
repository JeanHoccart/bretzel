"""TOPIC — Forms and their validation.

A Bretzel form is not a separate object: it is a ``ui.form`` around
ordinary fields, and the validation lives on the STATE, not on the view.

That is the point to grasp before all the rest. A `@validator` is
attached to a typed state field, so it applies whatever the write's
provenance — a form, a CSV import, a handler called by another. A
validation set on the view would only protect the path going through the
view.
"""

from __future__ import annotations

from bretzel import page, ui
from examples.docs.features.shell import shell
from examples.docs.lib.i18n import tr

PATH = "/forms"


@page(PATH, layout=shell, title="Formulaires")
def forms_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading(tr('Forms',
                          'Les formulaires'), level=1, size="3xl")
            ui.text(
                tr('Fields, a `ui.form` around them, and the validation on '
                   'the STATE — not on the view. That last point is what '
                   'makes the difference between “the form refuses” and “the '
                   'data cannot be wrong”.',
                   'Des champs, un `ui.form` autour, et la validation sur '
                   "l'ÉTAT — pas sur la vue. C'est ce dernier point qui fait "
                   'la différence entre « le formulaire refuse » et « la '
                   'donnée ne peut pas être fausse ».'),
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('The skeleton',
                                  'Le squelette'), level=2)
                    ui.text(
                        tr('`ui.form` is a container: its children are '
                           'written inside a `with`. `on_submit=` receives '
                           "the form's values.",
                           '`ui.form` est un conteneur : ses enfants '
                           "s'écrivent dans un `with`. `on_submit=` reçoit "
                           'les valeurs du formulaire.'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        tr('def register(name: str, email: str) -> None:\n    Account().create(name=name, email=email)\n\nwith ui.form(on_submit=register):\n    with ui.form_field(label="Name", required=True):\n        ui.input(name="name")\n    with ui.form_field(label="Email",\n                       hint="A work address, preferably"):\n        ui.input(name="email", type="email")\n    ui.button("Create", type="submit", color="primary")\n',
                           'def enregistrer(nom: str, email: str) -> None:\n    Compte().creer(nom=nom, email=email)\n\nwith ui.form(on_submit=enregistrer):\n    with ui.form_field(label="Nom", required=True):\n        ui.input(name="nom")\n    with ui.form_field(label="Email",\n                       hint="Professionnel de préférence"):\n        ui.input(name="email", type="email")\n    ui.button("Créer", type="submit", color="primary")\n'),
                        lang="python",
                    )
                    ui.text(
                        tr('`ui.form_field` carries the label above, the '
                           'field in the middle, the hint or the error '
                           'underneath. It also sets the accessibility links '
                           '— a screen reader announces the error with the '
                           'field, without anyone writing it.',
                           '`ui.form_field` porte le libellé au-dessus, le '
                           "champ au milieu, l'indice ou l'erreur en dessous."
                           " Il pose aussi les liens d'accessibilité — un "
                           "lecteur d'écran annonce l'erreur avec le champ, "
                           "sans qu'on l'écrive."),
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('Validation lives on the STATE',
                                  "La validation vit sur l'ÉTAT"), level=2)
                    ui.text(
                        tr('A `@validator` attaches to a typed state field. '
                           'It runs on EVERY assignment — so from the form as'
                           ' much as from an import, a handler, a script.',
                           "Un `@validator` s'attache à un champ d'état typé."
                           ' Il tourne à CHAQUE affectation — donc aussi bien'
                           ' depuis le formulaire que depuis un import, un '
                           'handler, un script.'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        tr('from bretzel.state import SessionState, field, validator\n\nclass Signup(SessionState):\n    email: str = field(default="")\n    age: int = field(default=0)\n\n    @validator("email")\n    def _valid_email(self, value: str) -> str:\n        """A FIELD validator: it receives the value and\n        returns the one we keep — so it can normalise\n        too."""\n        value = value.strip().lower()\n        if "@" not in value:\n            raise ValueError("Invalid address.")\n        return value\n\n    @validator\n    def _consistent(self) -> None:\n        """An INSTANCE validator: it runs after any\n        mutation, and sees every field."""\n        if self.age < 18 and self.email.endswith(".pro"):\n            raise FormError("Business account: 18 minimum.")\n',
                           'from bretzel.state import SessionState, field, validator\n\nclass Inscription(SessionState):\n    email: str = field(default="")\n    age: int = field(default=0)\n\n    @validator("email")\n    def _email_valide(self, valeur: str) -> str:\n        """Un validateur de CHAMP : il reçoit la\n        valeur et rend celle qu\'on garde — donc il\n        peut aussi normaliser."""\n        valeur = valeur.strip().lower()\n        if "@" not in valeur:\n            raise ValueError("Adresse invalide.")\n        return valeur\n\n    @validator\n    def _coherent(self) -> None:\n        """Un validateur d\'INSTANCE : il tourne après\n        toute mutation, et voit tous les champs."""\n        if self.age < 18 and self.email.endswith(".pro"):\n            raise FormError("Compte pro : 18 ans minimum.")\n'),
                        lang="python",
                    )
                    ui.table(
                        columns=[
                            ui.column("forme", label="Forme"),
                            ui.column("quand", label="Quand elle tourne"),
                            ui.column("recoit", label=tr('What it receives',
                                                         "Ce qu'elle reçoit")),
                        ],
                        rows=[
                            {"forme": "@validator(\"champ\")",
                             "quand": tr('on every assignment to THIS field',
                                         'à chaque affectation de CE champ'),
                             "recoit": tr('`(self, value)` — and returns the '
                                          'value to keep',
                                          '`(self, valeur)` — et rend la '
                                          'valeur à garder')},
                            {"forme": "@validator",
                             "quand": tr('after any mutation of the instance',
                                         "après toute mutation de l'instance"),
                             "recoit": tr('`(self)` — it sees every field, '
                                          'and raises to refuse',
                                          '`(self)` — il voit tous les '
                                          'champs, et lève pour refuser')},
                        ],
                        size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Montrer l'erreur", level=2)
                    ui.text(
                        tr('`ui.form_field(error=…)` shows the message under '
                           'the field AND sets `aria-invalid` — the two go '
                           'together, otherwise the error exists on screen '
                           'and not for a screen reader.',
                           '`ui.form_field(error=…)` affiche le message sous '
                           'le champ ET pose `aria-invalid` — les deux vont '
                           "ensemble, sinon l'erreur existe à l'écran et pas "
                           "pour un lecteur d'écran."),
                        color="muted", size="sm",
                    )
                    ui.code(
                        "etat = Inscription()\n"
                        "with ui.form_field(label=\"Email\",\n"
                        "                   error=etat.erreurs.get(\"email\")):\n"
                        "    ui.input(name=\"email\", value=etat.email)\n",
                        lang="python",
                    )
                    ui.alert(
                        tr('`FormError` is the raise meant to TRAVEL BACK to '
                           'the form — that is what distinguishes it from a '
                           'bare `ValueError`, which says “this value is '
                           'impossible” and comes back as a server error.',
                           '`FormError` est la levée destinée à REMONTER '
                           "jusqu'au formulaire — c'est ce qui la distingue "
                           "d'un `ValueError` nu, qui dit « cette valeur est "
                           'impossible » et remonte comme une erreur serveur.'),
                        color="info", title=tr('Two ways of refusing',
                                               'Deux façons de refuser'),
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('Why not on the view',
                                  'Pourquoi pas sur la vue'), level=2)
                    ui.text(
                        tr('Because an app has several write routes and one '
                           'form. A CSV import, a handler called from another'
                           ' page, a data migration: all write into the same '
                           'state, none goes through the view. A rule placed '
                           'on the field covers them all; a rule placed on '
                           'the form covers one.',
                           "Parce qu'une app a plusieurs chemins d'écriture "
                           'et un seul formulaire. Un import CSV, un handler '
                           'appelé depuis une autre page, une reprise de '
                           'données : tous écrivent dans le même état, aucun '
                           'ne passe par la vue. Une règle posée sur le champ'
                           ' les couvre tous ; une règle posée sur le '
                           "formulaire n'en couvre qu'un."),
                        color="muted", size="sm",
                    )

            with ui.card(color="surface"):
                with ui.hstack(gap="sm", wrap=True, align="baseline"):
                    ui.text(tr('Typed state, its four scopes, and the fields:',
                               "L'état typé, ses quatre portées, et les "
                               'champs :'), color="muted", size="sm")
                    ui.link(tr('Server state →',
                               'État serveur →'), href="/state-server")
                    ui.link("Actions serveur →", href="/actions-server")
