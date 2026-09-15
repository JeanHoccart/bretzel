"""SUJET — Les formulaires et leur validation.

Un formulaire Bretzel n'est pas un objet à part : c'est un ``ui.form``
autour de champs ordinaires, et la validation vit sur l'ÉTAT, pas sur la
vue.

C'est le point à comprendre avant tout le reste. Un `@validator` est
attaché à un champ d'état typé, donc il s'applique quelle que soit la
provenance de l'écriture — un formulaire, un import CSV, un handler
appelé par un autre. Une validation posée sur la vue ne protégerait que
le chemin qui passe par la vue.
"""

from __future__ import annotations

from bretzel import page, ui
from examples.docs.features.shell import shell

PATH = "/forms"


@page(PATH, layout=shell, title="Formulaires")
def forms_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("Les formulaires", level=1, size="3xl")
            ui.text(
                "Des champs, un `ui.form` autour, et la validation sur "
                "l'ÉTAT — pas sur la vue. C'est ce dernier point qui "
                "fait la différence entre « le formulaire refuse » et "
                "« la donnée ne peut pas être fausse ».",
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Le squelette", level=2)
                    ui.text(
                        "`ui.form` est un conteneur : ses enfants "
                        "s'écrivent dans un `with`. `on_submit=` reçoit "
                        "les valeurs du formulaire.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "def enregistrer(nom: str, email: str) -> None:\n"
                        "    Compte().creer(nom=nom, email=email)\n"
                        "\n"
                        "with ui.form(on_submit=enregistrer):\n"
                        "    with ui.form_field(label=\"Nom\", required=True):\n"
                        "        ui.input(name=\"nom\")\n"
                        "    with ui.form_field(label=\"Email\",\n"
                        "                       hint=\"Professionnel de préférence\"):\n"
                        "        ui.input(name=\"email\", type=\"email\")\n"
                        "    ui.button(\"Créer\", type=\"submit\", color=\"primary\")\n",
                        lang="python",
                    )
                    ui.text(
                        "`ui.form_field` porte le libellé au-dessus, le "
                        "champ au milieu, l'indice ou l'erreur en "
                        "dessous. Il pose aussi les liens "
                        "d'accessibilité — un lecteur d'écran annonce "
                        "l'erreur avec le champ, sans qu'on l'écrive.",
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("La validation vit sur l'ÉTAT", level=2)
                    ui.text(
                        "Un `@validator` s'attache à un champ d'état "
                        "typé. Il tourne à CHAQUE affectation — donc "
                        "aussi bien depuis le formulaire que depuis un "
                        "import, un handler, un script.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "from bretzel.state import SessionState, field, validator\n"
                        "\n"
                        "class Inscription(SessionState):\n"
                        "    email: str = field(default=\"\")\n"
                        "    age: int = field(default=0)\n"
                        "\n"
                        "    @validator(\"email\")\n"
                        "    def _email_valide(self, valeur: str) -> str:\n"
                        "        \"\"\"Un validateur de CHAMP : il reçoit la\n"
                        "        valeur et rend celle qu'on garde — donc il\n"
                        "        peut aussi normaliser.\"\"\"\n"
                        "        valeur = valeur.strip().lower()\n"
                        "        if \"@\" not in valeur:\n"
                        "            raise ValueError(\"Adresse invalide.\")\n"
                        "        return valeur\n"
                        "\n"
                        "    @validator\n"
                        "    def _coherent(self) -> None:\n"
                        "        \"\"\"Un validateur d'INSTANCE : il tourne après\n"
                        "        toute mutation, et voit tous les champs.\"\"\"\n"
                        "        if self.age < 18 and self.email.endswith(\".pro\"):\n"
                        "            raise FormError(\"Compte pro : 18 ans minimum.\")\n",
                        lang="python",
                    )
                    ui.table(
                        columns=[
                            ui.column("forme", label="Forme"),
                            ui.column("quand", label="Quand elle tourne"),
                            ui.column("recoit", label="Ce qu'elle reçoit"),
                        ],
                        rows=[
                            {"forme": "@validator(\"champ\")",
                             "quand": "à chaque affectation de CE champ",
                             "recoit": "`(self, valeur)` — et rend la "
                                       "valeur à garder"},
                            {"forme": "@validator",
                             "quand": "après toute mutation de l'instance",
                             "recoit": "`(self)` — il voit tous les "
                                       "champs, et lève pour refuser"},
                        ],
                        size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Montrer l'erreur", level=2)
                    ui.text(
                        "`ui.form_field(error=…)` affiche le message "
                        "sous le champ ET pose `aria-invalid` — les deux "
                        "vont ensemble, sinon l'erreur existe à l'écran "
                        "et pas pour un lecteur d'écran.",
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
                        "`FormError` est la levée destinée à REMONTER "
                        "jusqu'au formulaire — c'est ce qui la distingue "
                        "d'un `ValueError` nu, qui dit « cette valeur est "
                        "impossible » et remonte comme une erreur "
                        "serveur.",
                        color="info", title="Deux façons de refuser",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Pourquoi pas sur la vue", level=2)
                    ui.text(
                        "Parce qu'une app a plusieurs chemins d'écriture "
                        "et un seul formulaire. Un import CSV, un "
                        "handler appelé depuis une autre page, une "
                        "reprise de données : tous écrivent dans le même "
                        "état, aucun ne passe par la vue. Une règle "
                        "posée sur le champ les couvre tous ; une règle "
                        "posée sur le formulaire n'en couvre qu'un.",
                        color="muted", size="sm",
                    )

            with ui.card(color="surface"):
                with ui.hstack(gap="sm", wrap=True, align="baseline"):
                    ui.text("L'état typé, ses quatre portées, et les "
                            "champs :", color="muted", size="sm")
                    ui.link("État serveur →", href="/state-server")
                    ui.link("Actions serveur →", href="/actions-server")
