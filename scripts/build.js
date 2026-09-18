#!/usr/bin/env node
/**
 * Copy design tokens and brand assets from @lsst-sqre/rubin-style-dictionary
 * into the rubin-observatory template set.
 *
 * Docverse fetches template sets directly from this repository, so the
 * built outputs are committed. Run `npm run build` after upgrading the
 * rubin-style-dictionary dependency and commit the result. `npm run check`
 * verifies the committed files match the installed package (used in CI).
 */
const fs = require('node:fs');
const path = require('node:path');

const repoRoot = path.resolve(__dirname, '..');
const rsdRoot = path.dirname(
  require.resolve('@lsst-sqre/rubin-style-dictionary/package.json')
);
const rsdVersion = require('@lsst-sqre/rubin-style-dictionary/package.json')
  .version;

// Destination directory (relative to a template set) for rsd outputs.
const outDirName = 'rsd';

// Files to copy from the package into each template set, keyed by
// template set directory. Paths are relative to the package root.
const templateSets = {
  'rubin-observatory': [
    'dist/tokens.css',
    'assets/favicon/rubin-favicon-transparent-32px.png',
    'assets/partner-logos/rubin-partners.png',
  ],
};

// Derived outputs: {dest basename: (package root) => content}. These are
// transformations of package files rather than straight copies.
const derived = {
  'rubin-observatory': {
    // The package's dark tokens key off a `body.dark` class or a
    // `[data-theme='dark']` attribute, i.e. a user-controlled toggle. The
    // dashboards follow the system colour-scheme preference only, so rewrite
    // the selector to plain `body` and wrap the block in a
    // prefers-color-scheme media query.
    'tokens.dark-scheme.css': (root) => {
      const src = fs.readFileSync(path.join(root, 'dist/tokens.dark.css'), 'utf8');
      const body = src.replace(/^[^{]+\{/, 'body {').trimEnd();
      return (
        '/* Derived from rubin-style-dictionary dist/tokens.dark.css by\n' +
        ' * scripts/build.js: dark tokens applied on system preference. */\n' +
        '@media (prefers-color-scheme: dark) {\n' +
        body.replace(/^/gm, '  ') +
        '\n}\n'
      );
    },
  },
};

const checkMode = process.argv.includes('--check');
let stale = [];

for (const [setName, files] of Object.entries(templateSets)) {
  const outDir = path.join(repoRoot, setName, outDirName);
  fs.mkdirSync(outDir, { recursive: true });

  const outputs = files.map((rel) => ({
    src: path.join(rsdRoot, rel),
    dest: path.join(outDir, path.basename(rel)),
  }));
  for (const [name, make] of Object.entries(derived[setName] ?? {})) {
    outputs.push({ content: make(rsdRoot), dest: path.join(outDir, name) });
  }
  outputs.push({
    content: `${rsdVersion}\n`,
    dest: path.join(outDir, 'VERSION'),
  });

  for (const out of outputs) {
    const next = out.content ?? fs.readFileSync(out.src);
    const relDest = path.relative(repoRoot, out.dest);
    if (checkMode) {
      const current = fs.existsSync(out.dest) ? fs.readFileSync(out.dest) : null;
      if (current === null || Buffer.compare(Buffer.from(next), current) !== 0) {
        stale.push(relDest);
      }
    } else {
      fs.writeFileSync(out.dest, next);
      console.log(`wrote ${relDest}`);
    }
  }
}

if (checkMode) {
  if (stale.length > 0) {
    console.error(
      'Built rubin-style-dictionary outputs are out of date. Run `npm run build` and commit:\n' +
        stale.map((f) => `  ${f}`).join('\n')
    );
    process.exit(1);
  }
  console.log(`rsd outputs are up to date (rubin-style-dictionary ${rsdVersion}).`);
}
