// Smoke the exact package artifacts consumers receive. This checks both supported
// package roots: repository-root git dependencies and direct ncp-ts npm packaging.
// No arguments means the checked-in sentinel build. Only the release builder passes
// an explicit canonical source revision and persistent artifact destination.
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import {
  mkdtempSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  statSync,
  writeFileSync,
} from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const ncpTsRoot = join(here, '..')
const repositoryRoot = join(ncpTsRoot, '..')
const rootManifest = JSON.parse(readFileSync(join(repositoryRoot, 'package.json'), 'utf8'))
const nestedManifest = JSON.parse(readFileSync(join(ncpTsRoot, 'package.json'), 'utf8'))

const SENTINEL_BUILD_IDENTITY = 'unreleased-worktree'
const SOURCE_REVISION = /^[0-9a-f]{40}$/

function parseOptions(argv) {
  if (argv.length === 0) {
    return { expectedBuildIdentity: SENTINEL_BUILD_IDENTITY, packDestination: null }
  }
  if (argv.length !== 4) {
    throw new Error(
      'release package smoke requires exactly --release-source-revision <40-lowercase-hex> ' +
        '--pack-destination <empty-directory>',
    )
  }
  const values = new Map()
  for (let index = 0; index < argv.length; index += 2) {
    const option = argv[index]
    const value = argv[index + 1]
    if (!['--release-source-revision', '--pack-destination'].includes(option)) {
      throw new Error(`unknown package-smoke option ${JSON.stringify(option)}`)
    }
    if (values.has(option)) throw new Error(`duplicate package-smoke option ${option}`)
    values.set(option, value)
  }
  const expectedBuildIdentity = values.get('--release-source-revision')
  const destination = values.get('--pack-destination')
  if (!SOURCE_REVISION.test(expectedBuildIdentity ?? '')) {
    throw new Error('release source revision must be exactly 40 lowercase hexadecimal characters')
  }
  if (!destination) throw new Error('release package smoke requires --pack-destination')
  const packDestination = resolve(destination)
  let destinationStat
  try {
    destinationStat = statSync(packDestination)
  } catch {
    throw new Error(`pack destination does not exist: ${packDestination}`)
  }
  if (!destinationStat.isDirectory()) {
    throw new Error(`pack destination is not a directory: ${packDestination}`)
  }
  if (readdirSync(packDestination).length !== 0) {
    throw new Error(`pack destination must be empty: ${packDestination}`)
  }
  return { expectedBuildIdentity, packDestination }
}

const { expectedBuildIdentity, packDestination } = parseOptions(process.argv.slice(2))
const typescriptBin = process.env.NCP_TYPESCRIPT_BIN
  ? resolve(process.env.NCP_TYPESCRIPT_BIN)
  : join(repositoryRoot, 'node_modules', 'typescript', 'bin', 'tsc')

assert.ok(Number(process.versions.node.split('.')[0]) >= 18, 'package smoke requires Node >=18')

for (const key of [
  'name',
  'version',
  'description',
  'license',
  'type',
  'repository',
  'homepage',
  'sideEffects',
  'engines',
]) {
  assert.deepEqual(nestedManifest[key], rootManifest[key], `package metadata differs at ${key}`)
}
assert.match(rootManifest.description, /canonical-JSON/)
assert.match(rootManifest.description, /normative registries/)
assert.doesNotMatch(rootManifest.description, /proto-native|normative proto/i)
assert.equal(rootManifest.engines?.node, '>=18')
assert.equal(rootManifest.exports?.['.']?.import, './ncp-ts/dist/index.js')
assert.equal(rootManifest.exports?.['.']?.types, './ncp-ts/dist/index.d.ts')
assert.equal(nestedManifest.exports?.['.']?.import, './dist/index.js')
assert.equal(nestedManifest.exports?.['.']?.types, './dist/index.d.ts')

function filesBelow(root) {
  const paths = []
  for (const name of readdirSync(root)) {
    const path = join(root, name)
    if (statSync(path).isDirectory()) paths.push(...filesBelow(path))
    else paths.push(path)
  }
  return paths
}

// NodeNext source specifiers must survive into both runtime JavaScript and the
// declaration graph. A direct Node import only detects the runtime half.
const relativeImport = /\bfrom\s+['"](\.\.?\/[^'"]+)['"]/g
for (const path of filesBelow(join(ncpTsRoot, 'dist')).filter(
  (name) => name.endsWith('.js') || name.endsWith('.d.ts'),
)) {
  const source = readFileSync(path, 'utf8')
  for (const match of source.matchAll(relativeImport)) {
    assert.ok(match[1].endsWith('.js'), `${path} has non-Node ESM specifier ${match[1]}`)
  }
}

const direct = await import(new URL('../dist/index.js', import.meta.url))
assert.match(direct.NCP_VERSION, /^\d+\.\d+$/)
assert.equal(direct.NCP_PACKAGE_VERSION, rootManifest.version)
assert.match(direct.NCP_NORMATIVE_CONTRACT_DIGEST, /^[0-9a-f]{64}$/)
assert.equal(direct.NCP_BUILD_IDENTITY, expectedBuildIdentity)
assert.equal(typeof direct.NeuroSimClient, 'function')
assert.equal(typeof direct.WebSocketNeuroSim, 'function')

const temporaryRoot = mkdtempSync(join(tmpdir(), 'ncp-package-smoke-'))
try {
  for (const packageRoot of [repositoryRoot, ncpTsRoot]) {
    const label = packageRoot === repositoryRoot ? 'repository-root' : 'ncp-ts'
    const packRoot = packDestination
      ? join(packDestination, label)
      : join(temporaryRoot, `${label}-pack`)
    const installRoot = join(temporaryRoot, `${label}-install`)
    const npmCache = join(temporaryRoot, `${label}-npm-cache`)
    mkdirSync(packRoot)
    mkdirSync(installRoot)
    mkdirSync(npmCache)

    const env = {
      ...process.env,
      npm_config_cache: npmCache,
      npm_config_audit: 'false',
      npm_config_fund: 'false',
      npm_config_update_notifier: 'false',
    }
    const packed = JSON.parse(
      execFileSync(
        'npm',
        ['pack', '--json', '--ignore-scripts', '--pack-destination', packRoot],
        { cwd: packageRoot, env, encoding: 'utf8' },
      ),
    )[0]
    assert.equal(packed.name, '@sepahead/ncp')
    assert.equal(packed.version, rootManifest.version)

    const expectedEntrypoint =
      label === 'repository-root' ? 'ncp-ts/dist/index.js' : 'dist/index.js'
    const expectedIdentitySource =
      label === 'repository-root'
        ? 'ncp-ts/src/contract-identity.ts'
        : 'src/contract-identity.ts'
    const expectedIdentityRuntime =
      label === 'repository-root'
        ? 'ncp-ts/dist/contract-identity.js'
        : 'dist/contract-identity.js'
    const expectedIdentityDeclaration =
      label === 'repository-root'
        ? 'ncp-ts/dist/contract-identity.d.ts'
        : 'dist/contract-identity.d.ts'
    assert.ok(
      packed.files.some(({ path }) => path === expectedEntrypoint),
      `${label} tarball omitted ${expectedEntrypoint}`,
    )
    for (const identityPath of [
      expectedIdentitySource,
      expectedIdentityRuntime,
      expectedIdentityDeclaration,
    ]) {
      assert.ok(
        packed.files.some(({ path }) => path === identityPath),
        `${label} tarball omitted ${identityPath}`,
      )
    }
    for (const license of ['LICENSE-MIT', 'LICENSE-APACHE']) {
      assert.ok(
        packed.files.some(({ path }) => path === license),
        `${label} tarball omitted ${license}`,
      )
    }

    const tarball = join(packRoot, packed.filename)
    writeFileSync(
      join(installRoot, 'package.json'),
      JSON.stringify({ name: `ncp-${label}-smoke`, private: true, type: 'module' }),
    )
    execFileSync(
      'npm',
      [
        'install',
        '--ignore-scripts',
        '--no-audit',
        '--no-fund',
        '--package-lock=false',
        tarball,
      ],
      { cwd: installRoot, env, stdio: 'pipe' },
    )
    const installedPackage = join(installRoot, 'node_modules', '@sepahead', 'ncp')
    for (const [identityPath, declaration] of [
      [expectedIdentitySource, `NCP_BUILD_IDENTITY = '${expectedBuildIdentity}'`],
      [expectedIdentityRuntime, `NCP_BUILD_IDENTITY = '${expectedBuildIdentity}'`],
      [expectedIdentityDeclaration, `NCP_BUILD_IDENTITY = "${expectedBuildIdentity}"`],
    ]) {
      assert.ok(
        readFileSync(join(installedPackage, identityPath), 'utf8').includes(declaration),
        `${label} tarball ${identityPath} does not expose the expected build identity`,
      )
    }
    for (const license of ['LICENSE-MIT', 'LICENSE-APACHE']) {
      assert.deepEqual(
        readFileSync(join(installedPackage, license)),
        readFileSync(join(repositoryRoot, license)),
        `${label} tarball changed ${license}`,
      )
    }
    writeFileSync(
      join(installRoot, 'smoke.mjs'),
      [
        "import assert from 'node:assert/strict'",
        "import * as ncp from '@sepahead/ncp'",
        `assert.equal(ncp.NCP_VERSION, ${JSON.stringify(direct.NCP_VERSION)})`,
        `assert.equal(ncp.NCP_PACKAGE_VERSION, ${JSON.stringify(rootManifest.version)})`,
        `assert.equal(ncp.NCP_NORMATIVE_CONTRACT_DIGEST, ${JSON.stringify(direct.NCP_NORMATIVE_CONTRACT_DIGEST)})`,
        `assert.equal(ncp.NCP_BUILD_IDENTITY, ${JSON.stringify(direct.NCP_BUILD_IDENTITY)})`,
        "assert.equal(typeof ncp.NeuroSimClient, 'function')",
        "assert.equal(typeof ncp.WebSocketNeuroSim, 'function')",
        '',
      ].join('\n'),
    )
    execFileSync(process.execPath, ['smoke.mjs'], { cwd: installRoot, env, stdio: 'pipe' })

    // Resolve the installed declaration graph under the same NodeNext rules the
    // package source uses. This catches a `.d.ts` edge that a runtime import cannot.
    writeFileSync(
      join(installRoot, 'smoke.ts'),
      [
        "import { NCP_VERSION } from '@sepahead/ncp'",
        "import type { OpenSession } from '@sepahead/ncp'",
        'const version: string = NCP_VERSION',
        'declare const request: OpenSession',
        'void version',
        'void request',
        '',
      ].join('\n'),
    )
    writeFileSync(
      join(installRoot, 'tsconfig.json'),
      JSON.stringify({
        compilerOptions: {
          target: 'ES2022',
          module: 'NodeNext',
          moduleResolution: 'NodeNext',
          strict: true,
          noEmit: true,
        },
        include: ['smoke.ts'],
      }),
    )
    execFileSync(
      process.execPath,
      [typescriptBin, '-p', 'tsconfig.json'],
      { cwd: installRoot, env, stdio: 'pipe' },
    )
  }
} finally {
  rmSync(temporaryRoot, { recursive: true, force: true })
}

console.log(
  `npm package smoke: dist + root tarball + ncp-ts tarball passed ` +
    `(build identity ${expectedBuildIdentity})`,
)
