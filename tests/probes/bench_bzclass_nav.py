"""Banc : `bz-class` retire-t-il sa classe apres une NAVIGATION ? (:8982)

Reproduit le bug du 2026-08-16 : apres un partial-nav d'une page a une
autre, l'entree de sidebar quittee gardait son fond `bg-primary` alors
que son `data-active` etait bien repasse a `false`. Mesure a l'epoque
sur `examples/todo`, monte depuis le 2026-09-07 sur `examples/docs` :
l'app d'origine est partie a l'elagage des exemples, et le sujet est le
mecanisme de re-bind, pas l'app qui l'exhibe.

Racine : `bindEl` commence par `disposeEl`, donc chaque re-bind recapture
`base = new Set(el.classList)` — et l'ancien effet laissait ses classes en
place, si bien qu'elles entraient dans la nouvelle baseline et devenaient
irretirables.

Monte l'app sur un port dedie : celle que l'utilisateur fait tourner
sert un bundle runtime plus ancien, donc elle ne testerait rien.

Run :  py tests/probes/bench_bzclass_nav.py
"""

from __future__ import annotations

from examples.docs.main import app

if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8982))
