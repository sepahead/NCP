// Build revision-bound npm artifacts without changing the checked-in generated
// identity. The normal source tree and `regen` path must always retain the
// non-certifying `unreleased-worktree` sentinel.
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import {
  copyFileSync,
  cpSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  renameSync,
  rmSync,
  writeFileSync,
} from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const ncpTsRoot = join(here, '..')
const repositoryRoot = join(ncpTsRoot, '..')
const SENTINEL_BUILD_IDENTITY = 'unreleased-worktree'
const SOURCE_REVISION = /^[0-9a-f]{40}$/
const IDENTITY_DECLARATION = /^export const NCP_BUILD_IDENTITY = .*$/gm
const SENTINEL_DECLARATION =
  `export const NCP_BUILD_IDENTITY = '${SENTINEL_BUILD_IDENTITY}'`

function fail(message) {
  throw new Error(message)
}

function validateSourceRevision(revision) {
  if (!SOURCE_REVISION.test(revision ?? '')) {
    fail('source revision must be exactly 40 lowercase hexadecimal characters')
  }
  return revision
}

function parseArguments(argv) {
  if (argv.length === 1 && argv[0] === '--self-test') return { selfTest: true }
  if (argv.length !== 4) {
    fail(
      'usage: build-release.mjs --source-revision <40-lowercase-hex> ' +
        '--output <new-directory>',
    )
  }
  const values = new Map()
  for (let index = 0; index < argv.length; index += 2) {
    const option = argv[index]
    const value = argv[index + 1]
    if (!['--source-revision', '--output'].includes(option)) {
      fail(`unknown release-build option ${JSON.stringify(option)}`)
    }
    if (values.has(option)) fail(`duplicate release-build option ${option}`)
    values.set(option, value)
  }
  const revision = validateSourceRevision(values.get('--source-revision'))
  const requestedOutput = values.get('--output')
  if (!requestedOutput) fail('release build requires --output')
  const output = resolve(requestedOutput)
  if (existsSync(output)) fail(`release output already exists: ${output}`)
  return { selfTest: false, revision, output }
}

function exactTypeScriptCompiler(sourceRoot) {
  const manifest = JSON.parse(readFileSync(join(sourceRoot, 'package.json'), 'utf8'))
  const requestedVersion = manifest.devDependencies?.typescript
  if (!/^\d+\.\d+\.\d+$/.test(requestedVersion ?? '')) {
    fail('root package.json must pin TypeScript to one exact x.y.z version')
  }
  const installedManifestPath = join(repositoryRoot, 'node_modules', 'typescript', 'package.json')
  if (!existsSync(installedManifestPath)) {
    fail('pinned TypeScript is not installed; run bun install --frozen-lockfile first')
  }
  const installedVersion = JSON.parse(readFileSync(installedManifestPath, 'utf8')).version
  if (installedVersion !== requestedVersion) {
    fail(`installed TypeScript ${installedVersion} != source pin ${requestedVersion}`)
  }
  const compiler = join(repositoryRoot, 'node_modules', 'typescript', 'bin', 'tsc')
  if (!existsSync(compiler)) fail(`TypeScript compiler is missing: ${compiler}`)
  return { compiler, version: installedVersion }
}

function injectBuildIdentity(sourceRoot, revision) {
  validateSourceRevision(revision)
  const identityPath = join(sourceRoot, 'ncp-ts', 'src', 'contract-identity.ts')
  const source = readFileSync(identityPath, 'utf8')
  const declarations = source.match(IDENTITY_DECLARATION) ?? []
  if (declarations.length !== 1 || declarations[0] !== SENTINEL_DECLARATION) {
    fail(
      'generated TypeScript identity must contain exactly one checked-in ' +
        `${JSON.stringify(SENTINEL_DECLARATION)} declaration`,
    )
  }
  const injected = source.replace(
    SENTINEL_DECLARATION,
    `export const NCP_BUILD_IDENTITY = '${revision}'`,
  )
  writeFileSync(identityPath, injected, 'utf8')
}

function sha256(path) {
  return createHash('sha256').update(readFileSync(path)).digest('hex')
}

function artifactRecord(artifactRoot, packageRoot) {
  const directory = join(artifactRoot, packageRoot)
  const tarballs = readdirSync(directory).filter((name) => name.endsWith('.tgz'))
  if (tarballs.length !== 1) {
    fail(`${packageRoot} package smoke emitted ${tarballs.length} tarballs instead of one`)
  }
  const path = join(directory, tarballs[0])
  return {
    package_root: packageRoot,
    path: relative(artifactRoot, path).split('\\').join('/'),
    sha256: sha256(path),
  }
}

function writeReceipt(
  sourceRoot,
  artifactRoot,
  revision,
  typescriptVersion,
  rustBuildIdentityProbePassed,
) {
  const manifest = JSON.parse(readFileSync(join(sourceRoot, 'package.json'), 'utf8'))
  const identitySource = readFileSync(
    join(sourceRoot, 'ncp-ts', 'src', 'contract-identity.ts'),
    'utf8',
  )
  const digest = identitySource.match(
    /^export const NCP_NORMATIVE_CONTRACT_DIGEST = '([0-9a-f]{64})'$/m,
  )?.[1]
  if (!digest) fail('staged package has no canonical normative contract digest')
  const receipt = {
    schema: 'ncp.npm-release-build-receipt.v1',
    package_name: manifest.name,
    package_version: manifest.version,
    source_revision: revision,
    build_identity: revision,
    normative_contract_digest_sha256: digest,
    node_version: process.version,
    typescript_version: typescriptVersion,
    rust_build_identity_probe_passed: rustBuildIdentityProbePassed,
    artifacts: [
      artifactRecord(artifactRoot, 'repository-root'),
      artifactRecord(artifactRoot, 'ncp-ts'),
    ],
  }
  writeFileSync(
    join(artifactRoot, 'npm-release-build-receipt.json'),
    `${JSON.stringify(receipt, null, 2)}\n`,
    { encoding: 'utf8', flag: 'wx' },
  )
  return receipt
}

function compileAndVerify(
  sourceRoot,
  artifactRoot,
  revision,
  rustBuildIdentityProbePassed = false,
) {
  injectBuildIdentity(sourceRoot, revision)
  const { compiler, version } = exactTypeScriptCompiler(sourceRoot)
  execFileSync(process.execPath, [compiler, '-p', join(sourceRoot, 'ncp-ts', 'tsconfig.json')], {
    cwd: sourceRoot,
    stdio: 'inherit',
  })
  mkdirSync(artifactRoot)
  execFileSync(
    process.execPath,
    [
      join(sourceRoot, 'ncp-ts', 'scripts', 'check-package.mjs'),
      '--release-source-revision',
      revision,
      '--pack-destination',
      artifactRoot,
    ],
    {
      cwd: sourceRoot,
      env: { ...process.env, NCP_TYPESCRIPT_BIN: compiler },
      stdio: 'inherit',
    },
  )
  return writeReceipt(
    sourceRoot,
    artifactRoot,
    revision,
    version,
    rustBuildIdentityProbePassed,
  )
}

function verifyRustBuildIdentity(sourceRoot, targetRoot, revision) {
  validateSourceRevision(revision)
  const output = execFileSync(
    'cargo',
    [
      'test',
      '--locked',
      '-p',
      'ncp-core',
      'contract_identity::tests::build_identity_matches_release_builder_expectation',
      '--',
      '--exact',
    ],
    {
      cwd: sourceRoot,
      env: {
        ...process.env,
        CARGO_TARGET_DIR: targetRoot,
        NCP_BUILD_IDENTITY: revision,
        NCP_EXPECTED_BUILD_IDENTITY: revision,
      },
      encoding: 'utf8',
      stdio: ['inherit', 'pipe', 'inherit'],
    },
  )
  process.stdout.write(output)
  if (
    !output.includes(
      'test contract_identity::tests::build_identity_matches_release_builder_expectation ... ok',
    ) ||
    !/test result: ok\. 1 passed; 0 failed;/.test(output)
  ) {
    fail('Rust build-identity probe did not execute exactly once and pass')
  }
}

function exactHeadRevision(revision) {
  const head = execFileSync('git', ['rev-parse', '--verify', 'HEAD^{commit}'], {
    cwd: repositoryRoot,
    encoding: 'utf8',
  }).trim()
  if (head !== revision) {
    fail(`source revision ${revision} is not exact HEAD ${head}`)
  }

  // The orchestration code itself must be the version committed at the source
  // revision. Package bytes come exclusively from `git archive` below.
  const scriptRelativePath = 'ncp-ts/scripts/build-release.mjs'
  let committedScript
  try {
    committedScript = execFileSync('git', ['show', `${revision}:${scriptRelativePath}`], {
      cwd: repositoryRoot,
    })
  } catch {
    fail(`${scriptRelativePath} is absent from source revision ${revision}`)
  }
  const runningScript = readFileSync(fileURLToPath(import.meta.url))
  if (!runningScript.equals(committedScript)) {
    fail(`running ${scriptRelativePath} differs from source revision ${revision}`)
  }
}

function buildRelease(revision, output) {
  exactHeadRevision(revision)
  const outputParent = dirname(output)
  mkdirSync(outputParent, { recursive: true })
  if (existsSync(output)) fail(`release output already exists: ${output}`)

  const temporaryRoot = mkdtempSync(join(outputParent, '.ncp-npm-release-'))
  const archive = join(temporaryRoot, 'source.tar')
  const sourceRoot = join(temporaryRoot, 'source')
  const artifactRoot = join(temporaryRoot, 'artifacts')
  mkdirSync(sourceRoot)
  try {
    execFileSync(
      'git',
      ['archive', '--format=tar', '--output', archive, revision],
      { cwd: repositoryRoot, stdio: 'inherit' },
    )
    execFileSync('tar', ['-xf', archive, '-C', sourceRoot], { stdio: 'inherit' })

    // These checks run from archived source, not the mutable checkout.
    execFileSync(join(sourceRoot, 'scripts', 'check-version-coherence.sh'), [], {
      cwd: sourceRoot,
      stdio: 'inherit',
    })
    execFileSync('python3', [join(sourceRoot, 'scripts', 'generate_contract_manifest.py')], {
      cwd: sourceRoot,
      stdio: 'inherit',
    })

    verifyRustBuildIdentity(sourceRoot, join(temporaryRoot, 'rust-target'), revision)
    const receipt = compileAndVerify(sourceRoot, artifactRoot, revision, true)
    renameSync(artifactRoot, output)
    console.log(`npm release artifacts: ${output}`)
    console.log(`source/build identity: ${receipt.source_revision}`)
  } finally {
    rmSync(temporaryRoot, { recursive: true, force: true })
  }
}

function copySelfTestSource(destination) {
  mkdirSync(destination)
  for (const name of ['package.json', 'LICENSE-MIT', 'LICENSE-APACHE']) {
    copyFileSync(join(repositoryRoot, name), join(destination, name))
  }
  cpSync(ncpTsRoot, join(destination, 'ncp-ts'), { recursive: true })
}

function createRustProbeFixture(destination) {
  mkdirSync(join(destination, 'src'), { recursive: true })
  writeFileSync(
    join(destination, 'Cargo.toml'),
    [
      '[package]',
      'name = "ncp-core"',
      'version = "1.0.0"',
      'edition = "2021"',
      '',
      '[workspace]',
      '',
    ].join('\n'),
  )
  writeFileSync(
    join(destination, 'src', 'lib.rs'),
    [
      'pub mod contract_identity {',
      '    pub const BUILD_IDENTITY: &str = match option_env!("NCP_BUILD_IDENTITY") {',
      '        Some(identity) => identity,',
      '        None => "unreleased-worktree",',
      '    };',
      '',
      '    #[cfg(test)]',
      '    mod tests {',
      '        #[test]',
      '        fn build_identity_matches_release_builder_expectation() {',
      '            let expected = option_env!("NCP_EXPECTED_BUILD_IDENTITY")',
      '                .unwrap_or("unreleased-worktree");',
      '            assert_eq!(super::BUILD_IDENTITY, expected);',
      '        }',
      '    }',
      '}',
      '',
    ].join('\n'),
  )
  execFileSync('cargo', ['generate-lockfile', '--offline'], {
    cwd: destination,
    stdio: 'pipe',
  })
}

function selfTest() {
  const revision = '0123456789abcdef0123456789abcdef01234567'
  for (const invalid of [
    undefined,
    '',
    SENTINEL_BUILD_IDENTITY,
    revision.slice(0, -1),
    `${revision}0`,
    revision.toUpperCase(),
    ` ${revision}`,
    'g'.repeat(40),
  ]) {
    assert.throws(() => validateSourceRevision(invalid))
  }
  assert.equal(validateSourceRevision(revision), revision)
  assert.throws(() => parseArguments([]))
  assert.throws(() => parseArguments(['--source-revision', revision]))
  assert.throws(() =>
    parseArguments([
      '--source-revision',
      revision,
      '--output',
      repositoryRoot,
    ]),
  )
  assert.throws(() =>
    execFileSync(
      process.execPath,
      [
        join(ncpTsRoot, 'scripts', 'check-package.mjs'),
        '--release-source-revision',
        'UNSET',
        '--pack-destination',
        repositoryRoot,
      ],
      { stdio: 'pipe' },
    ),
  )

  const temporaryRoot = mkdtempSync(join(repositoryRoot, '.ncp-npm-release-self-test-'))
  const sourceRoot = join(temporaryRoot, 'source')
  const artifactRoot = join(temporaryRoot, 'artifacts')
  const rustProbeRoot = join(temporaryRoot, 'rust-probe')
  const originalIdentity = readFileSync(
    join(repositoryRoot, 'ncp-ts', 'src', 'contract-identity.ts'),
  )
  try {
    createRustProbeFixture(rustProbeRoot)
    verifyRustBuildIdentity(rustProbeRoot, join(temporaryRoot, 'rust-target'), revision)
    copySelfTestSource(sourceRoot)
    const receipt = compileAndVerify(sourceRoot, artifactRoot, revision, true)
    assert.equal(receipt.source_revision, revision)
    assert.equal(receipt.build_identity, revision)
    assert.equal(receipt.rust_build_identity_probe_passed, true)
    assert.equal(receipt.artifacts.length, 2)
    assert.ok(receipt.artifacts.every(({ sha256: digest }) => /^[0-9a-f]{64}$/.test(digest)))
    assert.deepEqual(
      JSON.parse(
        readFileSync(join(artifactRoot, 'npm-release-build-receipt.json'), 'utf8'),
      ),
      receipt,
    )
    assert.deepEqual(
      readFileSync(join(repositoryRoot, 'ncp-ts', 'src', 'contract-identity.ts')),
      originalIdentity,
      'self-test changed the checked-in sentinel source',
    )
  } finally {
    rmSync(temporaryRoot, { recursive: true, force: true })
  }
  console.log('npm release build self-test: strict revision + root/nested artifacts passed')
}

const options = parseArguments(process.argv.slice(2))
if (options.selfTest) selfTest()
else buildRelease(options.revision, options.output)
