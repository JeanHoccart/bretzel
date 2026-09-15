"""Bench app for the FileUpload V3 probe (port 8954).

Run :  py tests/probes/bench_fileupload.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, ui

app = Bretzel(
    secret_key="dev-fileupload-bench-secret-key",
    title="Bretzel · FileUpload V3 bench",
    mode="dev",
)


@page("/")
def home() -> None:
    with ui.vstack(gap="xl", align="start", classes="p-8"):
        ui.text("FileUpload V3 bench", size="2xl", weight="bold")
        ui.file_upload(
            label="Drop files here",
            multiple=True,
            max_files=3,
            max_size_mb=5,
            id="uploader",
        )


app.include(__name__)

if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8954))
