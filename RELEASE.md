# Releasing Bretzel

The first public release is an alpha. Publishing is intentionally a separate,
explicit action after the candidate has passed CI.

## One-time setup

1. Make the GitHub repository public.
2. Create or reserve the `bretzel` project on PyPI.
3. In PyPI, add a Trusted Publisher for this repository, workflow
   `.github/workflows/publish.yml`, environment `pypi`.
4. Create a protected GitHub environment named `pypi` and require approval.
5. Point `bretzel.dev` at the public documentation or landing page.

No PyPI password or API token belongs in GitHub secrets. The publish workflow
uses GitHub's short-lived OIDC identity.

## Every release

1. Start from a clean worktree on `main`.
2. Set the same version in `pyproject.toml` and the source-tree fallback in
   `bretzel/__init__.py`.
3. Move the release notes from Unreleased into a dated `CHANGELOG.md` section.
4. Rebuild the runtime: `python -m bretzel.runtime._build`.
5. Run `python -m pytest` and the browser suites required by the change.
6. Build locally with `python -m build` and inspect with
   `python -m twine check dist/*`.
7. Push, wait for CI, then create GitHub Release `v<version>`.
8. Approve the protected `pypi` environment. The workflow builds and publishes
   the distributions only if the tag exactly matches the package version.
9. Install the public wheel in a new environment and run the README quickstart.

## First-alpha announcement draft

> Bretzel `0.1.0a1` is out: a Server-Driven UI framework for Python with typed
> state, partial updates, realtime broadcast and no application JavaScript or
> npm pipeline to maintain.
>
> The first alpha includes 80+ UI components, a small in-house browser
> runtime, FastAPI integration, authentication primitives, SSE, drag-and-drop,
> server-rendered charts and framework-aware inspection tools.
>
> Try it:
>
> ```bash
> pip install bretzel
> bretzel new hello
> cd hello
> pip install -e .
> bretzel dev
> ```
>
> This is deliberately an alpha. I am looking for developers willing to build
> one small internal application and report where the model, API or documentation
> becomes unclear.

Pair the announcement with a short recording of the Kanban demo in two browser
windows and links to the quickstart, live demo, documentation and issue tracker.
