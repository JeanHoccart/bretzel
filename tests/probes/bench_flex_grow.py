"""Bench app pour le probe de ``grow=`` (port 8984).

Quatre barres dans un cadre de LARGEUR FIXE, parce que le defaut ne se
voit qu'a une largeur donnee : c'est le rapport entre la place et la base
des enfants qui decide si la ligne se partage ou se replie.

  temoin   ``wrap=True`` seul          → la barre est une PILE (le defaut)
  repare   ``wrap=True, grow="16rem"`` → une BARRE
  egal     ``grow=True``               → parts strictement egales
  etroit   la meme barre reparee dans 420 px → elle se replie, et c'est
           le comportement voulu : ``wrap`` fait son travail une fois que
           les enfants ont une base.

Le temoin est indispensable. Sans lui, on ne peut pas dire si la barre
reparee est correcte ou si les champs ont toujours ete comme ca.

Tier-1 user code only. Run :  py tests/probes/bench_flex_grow.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, ui

app = Bretzel(
    secret_key="dev-flex-grow-bench-secret-key",
    title="Bretzel - flex grow bench",
    mode="dev",
)

STATUSES = [("all", "All statuses"), ("live", "Live"), ("draft", "Draft")]


def three_buttons() -> None:
    """Trois enfants de largeurs INTRINSEQUES differentes.

    Des ``form_field`` ne conviendraient pas : leur racine porte
    ``w-full``, donc leur contenu n'exerce aucune pression et
    ``basis-0`` ne se distingue pas d'une base.
    """
    for label in ("OK", "Enregistrer", "Exporter au format CSV"):
        ui.button(label)


def two_fields(long_label: bool = False) -> None:
    with ui.form_field(label="Search"):
        ui.input(placeholder="Search name, email, company...", icon_left="search")
    with ui.form_field(label="Status" if not long_label else "Status of the record"):
        ui.select(options=STATUSES, value="all")


@page("/", title="Flex grow bench")
def home() -> None:
    with ui.vstack(gap="lg", classes="p-6"):
        # 860 px, et la mesure du probe : 860 px par champ empile
        # contre 422 px cote a cote.
        with ui.vstack(id="temoin", classes="w-[860px]"):
            with ui.hstack(gap="md", align="end", wrap=True):
                two_fields()

        with ui.vstack(id="repare", classes="w-[860px]"):
            with ui.hstack(gap="md", align="end", wrap=True, grow="16rem"):
                two_fields()

        # ⚠️ Ce couple est la SEULE chose qui distingue ``equal`` d'une
        # base, et la premiere version ne le faisait pas : deux champs
        # dans 860 px rendent 422 px chacun avec ``grow=True`` COMME avec
        # ``grow="16rem"``, donc l'assertion serait passee meme si
        # ``equal`` valait ``basis-64``. Il faut une place trop etroite
        # pour les bases : trois enfants dans 600 px, ou 3 x 16rem plus
        # les gouttieres ne tiennent pas.
        #
        #   equal  → basis-0,  le contenu ne pese rien  → UNE ligne
        #   16rem  → basis-64, minimum avant repli      → DEUX lignes
        # ⚠️ 400 px et non 600 depuis le 2026-09-13. Le repli ne dépend pas
        # de la BASE seule : un enfant `flex` se rétrécit jusqu'à sa largeur
        # minimale de CONTENU avant de passer à la ligne. Quand l'échelle du
        # framework est descendue à 3 px le cran, ce contenu a maigri, les
        # trois boutons ont tenu sur une ligne dans 600 px, et le témoin a
        # cessé de distinguer `equal` d'une base — en silence.
        with ui.vstack(id="egal", classes="w-[400px]"):
            with ui.hstack(gap="md", align="end", wrap=True, grow=True):
                three_buttons()

        with ui.vstack(id="base", classes="w-[400px]"):
            with ui.hstack(gap="md", align="end", wrap=True, grow="16rem"):
                three_buttons()

        # 300 px ne peut pas tenir deux bases de 16rem (256 px) plus le
        # gap, NI deux fois la largeur minimale de leur contenu : la barre
        # DOIT se replier. (420 px suffisait avant que l'échelle maigrisse.)
        with ui.vstack(id="etroit", classes="w-[300px]"):
            with ui.hstack(gap="md", align="end", wrap=True, grow="16rem"):
                two_fields()


app.include(home)


if __name__ == "__main__":
    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    app.run(port=bench_port(8984))
