// Copy the ts-rs-generated bindings (ncp-core/bindings/*.ts, generated from the
// ncp-core reference types, which conform to the normative proto/ncp.proto wire
// contract) into this package's src/generated/ so the package is self-contained
// for git / npm consumption.
//
// Run after regenerating the bindings:
//   cargo test -p ncp-core --features ts   # rewrites ncp-core/bindings/*.ts
//   node ncp-ts/scripts/sync-bindings.mjs  # mirrors them here
//   tsc -p ncp-ts/tsconfig.json            # rebuilds ncp-ts/dist
// (or just `npm run regen` from the repo root, which chains all three).
import { readdirSync, readFileSync, rmSync, mkdirSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url)) // ncp-ts/scripts
const src = join(here, '..', '..', 'ncp-core', 'bindings') // ncp-core/bindings
const dst = join(here, '..', 'src', 'generated') // ncp-ts/src/generated

rmSync(dst, { recursive: true, force: true })
mkdirSync(dst, { recursive: true })
const files = readdirSync(src).filter((f) => f.endsWith('.ts'))
for (const f of files) {
  const source = readFileSync(join(src, f), 'utf8')
  // ts-rs emits extensionless relative imports. They work through bundlers but
  // are invalid in the native Node ESM loader and under TypeScript NodeNext.
  // TypeScript resolves a `.js` source specifier back to the sibling `.ts` file
  // and preserves it in both emitted JavaScript and declaration files.
  const nodeEsmSource = source.replace(
    /(\bfrom\s+['"])(\.\.?\/[^'"]+)(['"])/g,
    (_match, prefix, specifier, suffix) =>
      `${prefix}${specifier.endsWith('.js') ? specifier : `${specifier}.js`}${suffix}`,
  )
  writeFileSync(join(dst, f), nodeEsmSource)
}

// ts-rs writes one file per exported type but does not maintain its barrel file.
// Rebuild the destination barrel from the actual files so a newly added wire type
// cannot exist on disk yet remain unreachable from the published package.
const types = files
  .filter((f) => f !== 'index.ts')
  .map((f) => f.slice(0, -3))
  .sort()
const barrel = [
  '// Canonical NCP TypeScript types — GENERATED from the Rust ncp-core types via',
  '// ts-rs. Do not edit by hand; run `bun run regen` from the repository root.',
  ...types.map((name) => `export type { ${name} } from './${name}.js';`),
  '',
].join('\n')
writeFileSync(join(dst, 'index.ts'), barrel)

console.log(`synced ${types.length} bindings: ncp-core/bindings -> ncp-ts/src/generated`)
