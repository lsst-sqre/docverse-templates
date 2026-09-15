# docverse-templates

Docverse dashboard, 404, and metadata asset templates for Rubin Observatory's Docverse organizations.

For background on how Docverse loads template sets from GitHub, see the [Dashboard templating system](https://sqr-112.lsst.io/#dashboard-templating-system) section of [SQR-112](https://sqr-112.lsst.io/).

## Template sets

Each top-level directory is a template set that a Docverse organization can point at (`repo=lsst-sqre/docverse-templates`, `path=<directory>`).
A set contains a `template.toml` that declares the dashboard and 404 templates and the CSS, JS, and image assets Docverse inlines into them.

| Directory | Purpose |
| --- | --- |
| `rubin-observatory/` | Rubin Observatory visual identity, built on the Rubin Style Dictionary design tokens. |
| `demo/` | Deliberately distinct demo set for verifying the GitHub template sync path end-to-end. |

## Rubin Style Dictionary

The `rubin-observatory` set gets its colours and brand assets (imagotype, favicon) from [`@lsst-sqre/rubin-style-dictionary`](https://github.com/lsst-sqre/squareone/tree/main/packages/rubin-style-dictionary), published to GitHub Packages.
Because Docverse fetches template sets straight from this repository, the token CSS and assets are copied into `rubin-observatory/rsd/` and committed.
Never edit files in `rsd/` by hand.

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
2. Run `npm run build` to refresh `rubin-observatory/rsd/`.
3. Commit the result.

CI runs `npm run check`, which fails if the committed `rsd/` files differ from what the installed package would produce.
The list of files copied from the package is in `scripts/build.js`.
