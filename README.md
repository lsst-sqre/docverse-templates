# docverse-templates

Docverse dashboard, 404, and metadata asset templates for Rubin Observatory's Docverse organizations.

For background on how Docverse loads template sets from GitHub, see the [Dashboard templating system](https://sqr-112.lsst.io/#dashboard-templating-system) section of [SQR-112](https://sqr-112.lsst.io/).

## Template sets

Each top-level directory is a template set that a Docverse organization can point at (`repo=lsst-sqre/docverse-templates`, `path=<directory>`).
A set contains a `template.toml` that declares the dashboard and 404 templates, the CSS, JS, and image assets Docverse inlines into them, and optionally a Jinja template that renders the version switcher JSON.

| Directory | Purpose |
| --- | --- |
| `rubin-observatory/` | Rubin Observatory visual identity, built on the Rubin Style Dictionary design tokens. |
| `pipelines/` | A copy of `rubin-observatory/` for [pipelines.lsst.io](https://pipelines.lsst.io), whose editions are named by EUPS tags. The dashboard shows the latest release, weekly, and daily editions under Current and groups the rest into Releases, Weekly releases, Daily releases, and Drafts; `switcher.json.jinja` renders a switcher of the latest release, weekly, daily, every release, and the four newest weeklies. |
| `demo/` | Deliberately distinct demo set for verifying the GitHub template sync path end-to-end. |

## Previewing templates locally

A small preview server renders every template set against mock project data with live reload.
It needs [uv](https://docs.astral.sh/uv/) (dependencies are declared inline in the script):

```
npm run preview
```

Then open <http://127.0.0.1:8790/>.
The index links to the dashboard, 404 page, and switcher JSON for each template set and each mock scenario.
A file watcher pushes reload events to open pages over Server-Sent Events, so the browser reloads as soon as a template, asset, or mock file changes (the switcher JSON has no reload script; refresh it by hand). Render errors are shown in the browser, including a switcher template whose output Docverse would reject.

To render everything once without serving, as CI does:

```
npm run check-render
```

Mock scenarios live in `dev/mocks/*.toml`, one file per project shape:

| Scenario | Models |
| --- | --- |
| `main-only` | A project with only a main edition. |
| `phalanx` | Main edition plus draft editions from ticket branches. |
| `safir` | Main edition, semantic version releases, and drafts. |
| `rsp` | Main edition, alternate deployments, and drafts. |
| `pipelines` | Main edition on an EUPS release, `weekly` and `daily` editions, numbered releases (including legacy `v17_0` and `13-0`), weekly releases (including legacy `w-2018-06`), daily drafts, a release candidate, and a ticket draft. |

Add a new `.toml` file to `dev/mocks/` to add a scenario; the server picks it up without a restart.
The preview mirrors Docverse's edition grouping (including `editions.by_slug` and the EUPS-aware ordering of releases), asset inlining, and switcher rendering and validation (see `dev/preview.py`), but the authoritative behaviour is in [Docverse](https://github.com/lsst-sqre/docverse) itself.

## Rubin Style Dictionary

The `rubin-observatory` and `pipelines` sets get their colours and brand assets (imagotype, favicon) from [`@lsst-sqre/rubin-style-dictionary`](https://github.com/lsst-sqre/squareone/tree/main/packages/rubin-style-dictionary), published to GitHub Packages.
Because Docverse fetches template sets straight from this repository, the token CSS and assets are copied into each set's `rsd/` directory and committed.
Never edit files in `rsd/` by hand.

Most files are straight copies. `tokens.dark-scheme.css` is derived: the package's dark tokens key off a `body.dark` class or `data-theme` attribute (a user toggle), whereas the dashboards follow the system colour-scheme preference only, so `scripts/build.js` rewrites that file to apply under a `prefers-color-scheme: dark` media query.

### Set up

The package lives on GitHub Packages, so npm needs a token with `read:packages` scope.
The repository's `.npmrc` maps the `@lsst-sqre` scope to GitHub Packages; add the credential to your user-level `~/.npmrc`:

```
//npm.pkg.github.com/:_authToken=<GitHub personal access token>
```

Then install with the Node version in `.nvmrc`:

```
npm install
```

### Updating tokens and assets

1. Bump `@lsst-sqre/rubin-style-dictionary` in `package.json` (Dependabot opens these PRs automatically).
2. Run `npm run build` to refresh every set's `rsd/` directory.
3. Commit the result.

CI runs `npm run check`, which fails if the committed `rsd/` files differ from what the installed package would produce.
The list of files copied from the package, and the sets they are copied into, is in `scripts/build.js`.
