// Build revision-bound npm artifacts without changing the checked-in generated
// identity. The normal source tree and `regen` path must always retain the
// non-certifying `unreleased-worktree` sentinel.
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import {
  closeSync,
  copyFileSync,
  chmodSync,
  cpSync,
  existsSync,
  fstatSync,
  lstatSync,
  linkSync,
  mkdirSync,
  mkdtempSync,
  openSync,
  readFileSync,
  readSync,
  readdirSync,
  renameSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from 'node:fs'
import { dirname, isAbsolute, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const ncpTsRoot = join(here, '..')
const repositoryRoot = join(ncpTsRoot, '..')
const SENTINEL_BUILD_IDENTITY = 'unreleased-worktree'
const SOURCE_REVISION = /^[0-9a-f]{40}$/
const IDENTITY_DECLARATION = /^export const NCP_BUILD_IDENTITY = .*$/gm
const MAX_GIT_TREE_FILES = 10_000
const MAX_GIT_BLOB_BYTES = 64 * 1024 * 1024
const MAX_GIT_TREE_BYTES = 1024 * 1024 * 1024
const MAX_RELEASE_ORCHESTRATION_BYTES = 256 * 1024
const RELEASE_ORCHESTRATION_PATHS = ['ncp-ts/scripts/build-release.mjs']
const TYPESCRIPT_CONTROL_PATH = 'security/toolchains/typescript-5.9.2.v1.json'
const TYPESCRIPT_CONTROL_SCHEMA = 'ncp.reviewed-npm-build-tool.v1'
const TYPESCRIPT_REGISTRY_TARBALL_EVIDENCE =
  'REVIEWED_EXPECTED_DIGEST_NOT_BUILD_OBSERVED'
const NPM_UNREVIEWED_PACKAGE_GRAPH_FIELDS = [
  'dependencies',
  'optionalDependencies',
  'peerDependencies',
  'peerDependenciesMeta',
  'bundleDependencies',
  'bundledDependencies',
  'workspaces',
  'overrides',
  'resolutions',
  'trustedDependencies',
  'patchedDependencies',
  'catalog',
  'catalogs',
  'packageExtensions',
]
const MAX_TYPESCRIPT_CONTROL_BYTES = 64 * 1024
const MAX_TYPESCRIPT_PACKAGE_FILES = 1_000
const MAX_TYPESCRIPT_PACKAGE_ENTRIES = 2_000
const MAX_TYPESCRIPT_PACKAGE_DEPTH = 16
const MAX_TYPESCRIPT_PACKAGE_PATH_BYTES = 512
const MAX_TYPESCRIPT_PACKAGE_FILE_BYTES = 64 * 1024 * 1024
const MAX_TYPESCRIPT_PACKAGE_BYTES = 256 * 1024 * 1024
const MAX_NODE_EXECUTABLE_BYTES = 256 * 1024 * 1024
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

function gitEnvironment() {
  return {
    PATH: process.env.PATH ?? '/usr/bin:/bin',
    LANG: 'C',
    LC_ALL: 'C',
    GIT_ATTR_NOSYSTEM: '1',
    GIT_CONFIG_GLOBAL: '/dev/null',
    GIT_CONFIG_SYSTEM: '/dev/null',
    GIT_CONFIG_NOSYSTEM: '1',
    GIT_NO_REPLACE_OBJECTS: '1',
    GIT_OPTIONAL_LOCKS: '0',
    GIT_TERMINAL_PROMPT: '0',
    GIT_ASKPASS: '/usr/bin/false',
    GCM_INTERACTIVE: 'never',
  }
}

function git(args, options = {}) {
  return execFileSync('git', args, {
    cwd: repositoryRoot,
    env: gitEnvironment(),
    maxBuffer: MAX_GIT_BLOB_BYTES + 1024,
    ...options,
  })
}

function safeTreePath(encoded) {
  const value = encoded.toString('utf8')
  if (
    !Buffer.from(value, 'utf8').equals(encoded) ||
    !value ||
    value.startsWith('/') ||
    value.includes('\\') ||
    value.split('/').some((part) => !part || part === '.' || part === '..') ||
    [...value].some((character) => character.codePointAt(0) < 32 || character.codePointAt(0) === 127)
  ) {
    fail(`exact Git tree contains an unsafe path ${JSON.stringify(value)}`)
  }
  return value
}

function materializeExactTree(revision, destination) {
  const objectFormat = git(['rev-parse', '--show-object-format'], { encoding: 'ascii' }).trim()
  const objectLengths = new Map([
    ['sha1', 40],
    ['sha256', 64],
  ])
  if (!objectLengths.has(objectFormat)) fail(`unsupported Git object format ${objectFormat}`)
  const tree = git(['ls-tree', '-r', '-z', '--full-tree', revision])
  const records = tree.subarray(0, tree.length - (tree.at(-1) === 0 ? 1 : 0)).toString('binary').split('\0')
  if (!records.length || records.length > MAX_GIT_TREE_FILES) {
    fail(`exact Git tree file count is outside 1..${MAX_GIT_TREE_FILES}`)
  }
  let totalBytes = 0
  const seen = new Set()
  for (const binaryRecord of records) {
    const record = Buffer.from(binaryRecord, 'binary')
    const separator = record.indexOf(0x09)
    if (separator < 1) fail('exact Git tree contains malformed metadata')
    const [mode, type, objectId] = record.subarray(0, separator).toString('ascii').split(' ')
    const path = safeTreePath(record.subarray(separator + 1))
    if (
      type !== 'blob' ||
      !['100644', '100755'].includes(mode) ||
      !new RegExp(`^[0-9a-f]{${objectLengths.get(objectFormat)}}$`).test(objectId)
    ) {
      fail(`exact Git tree contains a link, submodule, or unsupported entry: ${path}`)
    }
    if (seen.has(path)) fail(`exact Git tree repeats ${path}`)
    seen.add(path)
    const sizeText = git(['cat-file', '-s', objectId], { encoding: 'ascii' }).trim()
    if (!/^[0-9]+$/.test(sizeText)) fail(`exact Git blob size is malformed: ${path}`)
    const size = Number(sizeText)
    if (!Number.isSafeInteger(size) || size > MAX_GIT_BLOB_BYTES) {
      fail(`exact Git blob exceeds its byte limit: ${path}`)
    }
    totalBytes += size
    if (totalBytes > MAX_GIT_TREE_BYTES) fail('exact Git tree exceeds its byte limit')
    const body = git(['cat-file', 'blob', objectId])
    if (body.length !== size) fail(`exact Git blob size changed while reading: ${path}`)
    const digest = createHash(objectFormat)
      .update(Buffer.from(`blob ${body.length}\0`, 'ascii'))
      .update(body)
      .digest('hex')
    if (digest !== objectId) fail(`exact Git blob identity differs for ${path}`)
    const output = join(destination, ...path.split('/'))
    mkdirSync(dirname(output), { recursive: true })
    writeFileSync(output, body, { flag: 'wx' })
    chmodSync(output, mode === '100755' ? 0o755 : 0o644)
  }
}

function assertNoCargoConfigAncestors(path) {
  let current = resolve(path)
  while (true) {
    for (const name of ['config', 'config.toml']) {
      const candidate = join(current, '.cargo', name)
      if (existsSync(candidate)) fail(`release build inherits Cargo configuration: ${candidate}`)
    }
    const parent = dirname(current)
    if (parent === current) return
    current = parent
  }
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

function sameFileIdentity(left, right) {
  return ['dev', 'ino', 'mode', 'nlink', 'size', 'mtimeMs', 'ctimeMs'].every(
    (key) => left[key] === right[key],
  )
}

function boundedRegularFile(path, context, maximumBytes) {
  let pathBefore
  try {
    pathBefore = lstatSync(path)
  } catch (error) {
    fail(`${context} is unavailable: ${error.message}`)
  }
  if (!pathBefore.isFile() || pathBefore.isSymbolicLink()) {
    fail(`${context} is not one bounded unaliased regular file`)
  }
  if (pathBefore.nlink !== 1) {
    const remediation = context.startsWith('TypeScript package file ')
      ? '; reinstall with bun install --frozen-lockfile --backend=copyfile --force'
      : ''
    fail(`${context} has ${pathBefore.nlink} filesystem links${remediation}`)
  }
  if (
    !Number.isSafeInteger(pathBefore.size) ||
    pathBefore.size < 0 ||
    pathBefore.size > maximumBytes
  ) {
    fail(`${context} is not one bounded unaliased regular file`)
  }

  let descriptor
  try {
    descriptor = openSync(path, 'r')
    const opened = fstatSync(descriptor)
    if (!sameFileIdentity(pathBefore, opened)) {
      fail(`${context} changed while it was opened`)
    }
    const body = Buffer.alloc(pathBefore.size)
    let offset = 0
    while (offset < body.length) {
      const count = readSync(descriptor, body, offset, body.length - offset, offset)
      if (count === 0) fail(`${context} ended before its declared size`)
      offset += count
    }
    const overflow = Buffer.alloc(1)
    if (readSync(descriptor, overflow, 0, 1, offset) !== 0) {
      fail(`${context} grew beyond its declared size`)
    }
    const openedAfter = fstatSync(descriptor)
    const pathAfter = lstatSync(path)
    if (
      !sameFileIdentity(opened, openedAfter) ||
      !sameFileIdentity(openedAfter, pathAfter)
    ) {
      fail(`${context} changed while it was read`)
    }
    return body
  } finally {
    if (descriptor !== undefined) closeSync(descriptor)
  }
}

function readUniqueJsonObject(
  path,
  context,
  maximumBytes = MAX_TYPESCRIPT_CONTROL_BYTES,
) {
  const body = boundedRegularFile(path, context, maximumBytes)
  const raw = body.toString('utf8')
  if (!Buffer.from(raw, 'utf8').equals(body)) fail(`${context} is not UTF-8`)
  return { body, raw, value: parseUniqueJsonObject(raw, context) }
}

function safePackagePath(encoded, parent) {
  const name = encoded.toString('utf8')
  if (
    !Buffer.from(name, 'utf8').equals(encoded) ||
    !name ||
    name === '.' ||
    name === '..' ||
    name.includes('/') ||
    name.includes('\\') ||
    !/^[\x20-\x7e]+$/.test(name) ||
    [...name].some(
      (character) => character.codePointAt(0) < 32 || character.codePointAt(0) === 127,
    )
  ) {
    fail('TypeScript package tree contains an unsafe entry name')
  }
  const path = parent ? `${parent}/${name}` : name
  if (Buffer.byteLength(path, 'utf8') > MAX_TYPESCRIPT_PACKAGE_PATH_BYTES) {
    fail(`TypeScript package path exceeds its byte limit: ${path}`)
  }
  return { name, path }
}

function canonicalSha512Integrity(value, context) {
  if (!/^sha512-[A-Za-z0-9+/]+={0,2}$/.test(value ?? '')) {
    fail(`${context} is not a canonical SHA-512 SRI value`)
  }
  const encoded = value.slice('sha512-'.length)
  const digest = Buffer.from(encoded, 'base64')
  if (digest.length !== 64 || digest.toString('base64') !== encoded) {
    fail(`${context} does not encode exactly 64 SHA-512 bytes`)
  }
  return value
}

function rejectDuplicateJsonObjectKeys(text, context) {
  let index = 0
  const maximumDepth = 64
  const skipWhitespace = () => {
    while (index < text.length && /\s/.test(text[index])) index += 1
  }
  const parseString = () => {
    const start = index
    index += 1
    let escaped = false
    while (index < text.length) {
      const character = text[index]
      index += 1
      if (escaped) escaped = false
      else if (character === '\\') escaped = true
      else if (character === '"') return JSON.parse(text.slice(start, index))
    }
    fail(`${context} has an unterminated string`)
  }
  const scanValue = (depth) => {
    if (depth > maximumDepth) fail(`${context} exceeds the JSON nesting limit`)
    skipWhitespace()
    const character = text[index]
    if (character === '{') {
      index += 1
      const keys = new Set()
      skipWhitespace()
      if (text[index] === '}') {
        index += 1
        return
      }
      while (index < text.length) {
        skipWhitespace()
        if (text[index] !== '"') fail(`${context} has a non-string object key`)
        const key = parseString()
        if (keys.has(key)) {
          fail(`${context} contains duplicate object key ${JSON.stringify(key)}`)
        }
        keys.add(key)
        skipWhitespace()
        if (text[index] !== ':') fail(`${context} has a malformed object member`)
        index += 1
        scanValue(depth + 1)
        skipWhitespace()
        if (text[index] === '}') {
          index += 1
          return
        }
        if (text[index] !== ',') fail(`${context} has a malformed object separator`)
        index += 1
      }
      fail(`${context} has an unterminated object`)
    }
    if (character === '[') {
      index += 1
      skipWhitespace()
      if (text[index] === ']') {
        index += 1
        return
      }
      while (index < text.length) {
        scanValue(depth + 1)
        skipWhitespace()
        if (text[index] === ']') {
          index += 1
          return
        }
        if (text[index] !== ',') fail(`${context} has a malformed array separator`)
        index += 1
      }
      fail(`${context} has an unterminated array`)
    }
    if (character === '"') {
      parseString()
      return
    }
    const start = index
    while (index < text.length && !/[\s,\]}]/.test(text[index])) index += 1
    if (index === start) fail(`${context} has a malformed scalar`)
  }

  scanValue(0)
  skipWhitespace()
  if (index !== text.length) fail(`${context} has trailing JSON content`)
}

function parseUniqueJsonObject(raw, context) {
  let value
  try {
    value = JSON.parse(raw)
  } catch (error) {
    fail(`${context} is not valid JSON: ${error.message}`)
  }
  rejectDuplicateJsonObjectKeys(raw, context)
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    fail(`${context} must contain one object`)
  }
  return value
}

function parseJsoncObject(raw, context) {
  const stripped = [...raw]
  let inString = false
  let escaped = false
  for (let index = 0; index < stripped.length; index += 1) {
    const character = stripped[index]
    if (inString) {
      if (escaped) escaped = false
      else if (character === '\\') escaped = true
      else if (character === '"') inString = false
      continue
    }
    if (character === '"') {
      inString = true
      continue
    }
    if (character !== '/' || index + 1 >= stripped.length) continue
    const marker = stripped[index + 1]
    if (marker === '/') {
      stripped[index] = stripped[index + 1] = ' '
      index += 2
      while (index < stripped.length && !['\r', '\n'].includes(stripped[index])) {
        stripped[index] = ' '
        index += 1
      }
      index -= 1
      continue
    }
    if (marker === '*') {
      stripped[index] = stripped[index + 1] = ' '
      index += 2
      while (
        index + 1 < stripped.length &&
        !(stripped[index] === '*' && stripped[index + 1] === '/')
      ) {
        if (!['\r', '\n'].includes(stripped[index])) stripped[index] = ' '
        index += 1
      }
      if (index + 1 >= stripped.length) fail(`${context} has an unterminated comment`)
      stripped[index] = stripped[index + 1] = ' '
      index += 1
    }
  }
  if (inString) fail(`${context} has an unterminated string`)

  const withoutTrailingCommas = []
  inString = false
  escaped = false
  for (let index = 0; index < stripped.length; index += 1) {
    const character = stripped[index]
    if (inString) {
      withoutTrailingCommas.push(character)
      if (escaped) escaped = false
      else if (character === '\\') escaped = true
      else if (character === '"') inString = false
      continue
    }
    if (character === '"') {
      inString = true
      withoutTrailingCommas.push(character)
      continue
    }
    if (character === ',') {
      let lookahead = index + 1
      while (lookahead < stripped.length && /\s/.test(stripped[lookahead])) lookahead += 1
      if (lookahead < stripped.length && ['}', ']'].includes(stripped[lookahead])) continue
    }
    withoutTrailingCommas.push(character)
  }
  const normalized = withoutTrailingCommas.join('')
  let value
  try {
    value = JSON.parse(normalized)
  } catch (error) {
    fail(`${context} is not valid JSONC: ${error.message}`)
  }
  rejectDuplicateJsonObjectKeys(normalized, context)
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    fail(`${context} must contain one object`)
  }
  return value
}

function exactTypeScriptBunLock(lock, version, reviewedIntegrity) {
  if (lock.includes('\r')) fail('Bun lockfile must use canonical LF line endings')
  canonicalSha512Integrity(reviewedIntegrity, 'reviewed TypeScript registry integrity')
  const escapedVersion = version.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const pinPattern = new RegExp(
    `^\\s*"typescript"\\s*:\\s*"${escapedVersion}"[,]?\\s*$`,
  )
  const packagePattern = new RegExp(
    `^\\s*"typescript"\\s*:\\s*\\["typescript@${escapedVersion}"[^\\r\\n]*?` +
      `"(sha512-[A-Za-z0-9+/]+={0,2})"\\][,]?\\s*$`,
  )
  const lines = lock.split('\n')
  const mentions = lines.filter((line) => line.includes('"typescript"'))
  const pins = mentions.filter((line) => pinPattern.test(line))
  const packages = mentions.map((line) => line.match(packagePattern)).filter(Boolean)
  if (
    mentions.length !== 2 ||
    pins.length !== 1 ||
    packages.length !== 1 ||
    canonicalSha512Integrity(packages[0][1], 'Bun TypeScript registry integrity') !==
      reviewedIntegrity
  ) {
    fail('Bun lockfile does not contain the one exact reviewed TypeScript package record')
  }
  const parsed = parseJsoncObject(lock, 'Bun lockfile')
  exactObjectKeys(
    parsed,
    ['configVersion', 'lockfileVersion', 'packages', 'workspaces'],
    'Bun lockfile',
  )
  exactObjectKeys(parsed.workspaces, [''], 'Bun lockfile workspaces')
  exactObjectKeys(parsed.packages, ['typescript'], 'Bun lockfile packages')
  const workspace = parsed.workspaces['']
  exactObjectKeys(workspace, ['devDependencies', 'name'], 'Bun root workspace')
  exactObjectKeys(
    workspace.devDependencies,
    ['typescript'],
    'Bun root development dependencies',
  )
  const record = parsed.packages.typescript
  if (
    parsed.lockfileVersion !== 1 ||
    parsed.configVersion !== 1 ||
    workspace.name !== '@sepahead/ncp' ||
    workspace.devDependencies.typescript !== version ||
    !Array.isArray(record) ||
    record.length !== 4 ||
    record[0] !== `typescript@${version}` ||
    record[1] !== '' ||
    JSON.stringify(record[2]) !==
      JSON.stringify({ bin: { tsc: 'bin/tsc', tsserver: 'bin/tsserver' } }) ||
    record[3] !== reviewedIntegrity
  ) {
    fail('Bun lockfile TypeScript package structure differs from its reviewed form')
  }
}

function typeScriptPackageTree(packageRoot) {
  let rootIdentity
  try {
    rootIdentity = lstatSync(packageRoot)
  } catch (error) {
    fail(`installed TypeScript package is unavailable: ${error.message}`)
  }
  if (!rootIdentity.isDirectory() || rootIdentity.isSymbolicLink()) {
    fail('installed TypeScript package root is linked or not a directory')
  }

  const files = []
  const seen = new Set()
  let entries = 0
  let totalBytes = 0
  function walk(directory, parent, depth) {
    if (depth > MAX_TYPESCRIPT_PACKAGE_DEPTH) {
      fail('TypeScript package tree exceeds its depth limit')
    }
    const names = readdirSync(directory, { encoding: 'buffer' }).sort(Buffer.compare)
    for (const encoded of names) {
      entries += 1
      if (entries > MAX_TYPESCRIPT_PACKAGE_ENTRIES) {
        fail('TypeScript package tree exceeds its entry limit')
      }
      const { name, path } = safePackagePath(encoded, parent)
      if (seen.has(path)) fail(`TypeScript package tree repeats ${path}`)
      seen.add(path)
      const absolute = join(directory, name)
      const identity = lstatSync(absolute)
      if (identity.isSymbolicLink()) {
        fail(`TypeScript package tree contains a symbolic link: ${path}`)
      }
      if (identity.isDirectory()) {
        walk(absolute, path, depth + 1)
        continue
      }
      if (!identity.isFile()) {
        fail(`TypeScript package tree contains a special file: ${path}`)
      }
      if (files.length >= MAX_TYPESCRIPT_PACKAGE_FILES) {
        fail('TypeScript package tree exceeds its file-count limit')
      }
      const body = boundedRegularFile(
        absolute,
        `TypeScript package file ${path}`,
        MAX_TYPESCRIPT_PACKAGE_FILE_BYTES,
      )
      totalBytes += body.length
      if (totalBytes > MAX_TYPESCRIPT_PACKAGE_BYTES) {
        fail('TypeScript package tree exceeds its aggregate byte limit')
      }
      files.push({
        path,
        size_bytes: body.length,
        sha256: createHash('sha256').update(body).digest('hex'),
      })
    }
  }
  walk(packageRoot, '', 0)
  if (!files.length) fail('TypeScript package tree contains no regular files')
  return {
    file_count: files.length,
    total_bytes: totalBytes,
    manifest_sha256: createHash('sha256').update(JSON.stringify(files)).digest('hex'),
    files,
  }
}

function exactObjectKeys(value, expected, context) {
  if (
    !value ||
    typeof value !== 'object' ||
    Array.isArray(value) ||
    JSON.stringify(Object.keys(value).sort()) !== JSON.stringify([...expected].sort())
  ) {
    fail(`${context} has an unexpected shape`)
  }
}

function exactNpmDependencySurface(manifest, context) {
  const unexpected = NPM_UNREVIEWED_PACKAGE_GRAPH_FIELDS.filter((field) =>
    Object.prototype.hasOwnProperty.call(manifest, field),
  )
  if (unexpected.length) {
    fail(`${context} contains unreviewed dependency or package-graph fields: ${unexpected.join(', ')}`)
  }
  exactObjectKeys(
    manifest.devDependencies,
    ['typescript'],
    `${context} development dependencies`,
  )
  const version = manifest.devDependencies.typescript
  if (!/^\d+\.\d+\.\d+$/.test(version ?? '')) {
    fail(`${context} must pin TypeScript to one exact x.y.z version`)
  }
  return version
}

function typeScriptControl(sourceRoot) {
  const path = join(sourceRoot, ...TYPESCRIPT_CONTROL_PATH.split('/'))
  const { body, raw, value: control } = readUniqueJsonObject(
    path,
    'TypeScript source control',
  )
  if (`${JSON.stringify(control, null, 2)}\n` !== raw) {
    fail('TypeScript source control is not canonical JSON')
  }
  exactObjectKeys(
    control,
    ['claim_boundary', 'normalized_package_tree', 'package', 'registry', 'schema', 'version'],
    'TypeScript source control',
  )
  exactObjectKeys(
    control.normalized_package_tree,
    ['file_count', 'manifest_sha256', 'record_shape', 'total_bytes'],
    'TypeScript normalized-tree control',
  )
  exactObjectKeys(
    control.registry,
    ['integrity_sha512', 'tarball_bytes_retained', 'tarball_sha256'],
    'TypeScript registry control',
  )
  if (
    control.schema !== TYPESCRIPT_CONTROL_SCHEMA ||
    control.package !== 'typescript' ||
    !/^\d+\.\d+\.\d+$/.test(control.version ?? '') ||
    canonicalSha512Integrity(
      control.registry.integrity_sha512,
      'TypeScript source-control registry integrity',
    ) !== control.registry.integrity_sha512 ||
    control.registry.tarball_bytes_retained !== false ||
    !/^[0-9a-f]{64}$/.test(control.registry.tarball_sha256 ?? '') ||
    control.normalized_package_tree.record_shape.join('\0') !==
      ['path', 'size_bytes', 'sha256'].join('\0') ||
    !Number.isSafeInteger(control.normalized_package_tree.file_count) ||
    control.normalized_package_tree.file_count < 1 ||
    control.normalized_package_tree.file_count > MAX_TYPESCRIPT_PACKAGE_FILES ||
    !Number.isSafeInteger(control.normalized_package_tree.total_bytes) ||
    control.normalized_package_tree.total_bytes < 1 ||
    control.normalized_package_tree.total_bytes > MAX_TYPESCRIPT_PACKAGE_BYTES ||
    !/^[0-9a-f]{64}$/.test(control.normalized_package_tree.manifest_sha256 ?? '') ||
    typeof control.claim_boundary !== 'string' ||
    !control.claim_boundary
  ) {
    fail('TypeScript source control identity is malformed')
  }
  return {
    ...control,
    sha256: createHash('sha256').update(body).digest('hex'),
  }
}

function assertTypeScriptTreeMatches(observed, expected, context) {
  if (
    observed.file_count !== expected.file_count ||
    observed.total_bytes !== expected.total_bytes ||
    observed.manifest_sha256 !== expected.manifest_sha256
  ) {
    fail(`${context} differs from the reviewed TypeScript package tree`)
  }
}

function exactNodeRuntime() {
  if (!isAbsolute(process.execPath)) fail('Node executable path is not absolute')
  const body = boundedRegularFile(
    process.execPath,
    'Node executable',
    MAX_NODE_EXECUTABLE_BYTES,
  )
  return {
    version: process.version,
    executable_sha256: createHash('sha256').update(body).digest('hex'),
  }
}

function exactTypeScriptCompiler(sourceRoot) {
  const { value: manifest } = readUniqueJsonObject(
    join(sourceRoot, 'package.json'),
    'root package.json',
  )
  const { value: nestedManifest } = readUniqueJsonObject(
    join(sourceRoot, 'ncp-ts', 'package.json'),
    'ncp-ts/package.json',
  )
  const requestedVersion = exactNpmDependencySurface(manifest, 'root package.json')
  const nestedVersion = exactNpmDependencySurface(
    nestedManifest,
    'ncp-ts/package.json',
  )
  if (
    nestedManifest.name !== manifest.name ||
    nestedManifest.version !== manifest.version ||
    nestedVersion !== requestedVersion
  ) {
    fail('root and nested npm package identities are incoherent')
  }
  const control = typeScriptControl(sourceRoot)
  if (requestedVersion !== control.version) {
    fail(`source TypeScript ${requestedVersion} has no matching reviewed control`)
  }

  const lockPath = join(sourceRoot, 'bun.lock')
  const lockBody = boundedRegularFile(lockPath, 'Bun lockfile', MAX_TYPESCRIPT_CONTROL_BYTES)
  const lock = lockBody.toString('utf8')
  if (!Buffer.from(lock, 'utf8').equals(lockBody)) fail('Bun lockfile is not UTF-8')
  exactTypeScriptBunLock(lock, requestedVersion, control.registry.integrity_sha512)

  const packageRoot = join(repositoryRoot, 'node_modules', 'typescript')
  const tree = typeScriptPackageTree(packageRoot)
  assertTypeScriptTreeMatches(
    tree,
    control.normalized_package_tree,
    'installed TypeScript package',
  )
  const records = new Map(tree.files.map((record) => [record.path, record]))
  const installedManifestPath = join(packageRoot, 'package.json')
  const { value: installedManifest } = readUniqueJsonObject(
    installedManifestPath,
    'installed TypeScript package manifest',
  )
  if (installedManifest.version !== requestedVersion) {
    fail(`installed TypeScript ${installedManifest.version} != source pin ${requestedVersion}`)
  }
  const compiler = join(packageRoot, 'bin', 'tsc')
  const compilerRecord = records.get('bin/tsc')
  const manifestRecord = records.get('package.json')
  if (!compilerRecord || !manifestRecord) {
    fail('reviewed TypeScript package lacks its compiler launcher or package manifest')
  }
  return {
    compiler,
    version: installedManifest.version,
    compilerLauncherSha256: compilerRecord.sha256,
    packageManifestSha256: manifestRecord.sha256,
    lockfileSha256: createHash('sha256').update(lockBody).digest('hex'),
    control,
    tree,
  }
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
  typescript,
  nodeRuntime,
  rustBuildIdentityProbePassed,
) {
  const { value: manifest } = readUniqueJsonObject(
    join(sourceRoot, 'package.json'),
    'root package.json',
  )
  const identitySource = readFileSync(
    join(sourceRoot, 'ncp-ts', 'src', 'contract-identity.ts'),
    'utf8',
  )
  const digest = identitySource.match(
    /^export const NCP_NORMATIVE_CONTRACT_DIGEST = '([0-9a-f]{64})'$/m,
  )?.[1]
  if (!digest) fail('staged package has no canonical normative contract digest')
  const receipt = {
    schema: 'ncp.npm-release-build-receipt.v2',
    package_name: manifest.name,
    package_version: manifest.version,
    source_revision: revision,
    build_identity: revision,
    normative_contract_digest_sha256: digest,
    node_version: nodeRuntime.version,
    node_executable_sha256: nodeRuntime.executable_sha256,
    node_executable_pre_post_match: true,
    typescript_version: typescript.version,
    typescript_control_path: TYPESCRIPT_CONTROL_PATH,
    typescript_control_sha256: typescript.control.sha256,
    typescript_control_claim_boundary: typescript.control.claim_boundary,
    typescript_lockfile_sha256: typescript.lockfileSha256,
    typescript_registry_integrity_sha512: typescript.control.registry.integrity_sha512,
    typescript_registry_tarball_sha256: typescript.control.registry.tarball_sha256,
    typescript_registry_tarball_bytes_retained:
      typescript.control.registry.tarball_bytes_retained,
    typescript_registry_tarball_evidence: TYPESCRIPT_REGISTRY_TARBALL_EVIDENCE,
    typescript_compiler_launcher_sha256: typescript.compilerLauncherSha256,
    typescript_package_manifest_sha256: typescript.packageManifestSha256,
    typescript_package_tree: typescript.tree,
    typescript_package_tree_pre_post_match: true,
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
  const nodeRuntime = exactNodeRuntime()
  const typescript = exactTypeScriptCompiler(sourceRoot)
  execFileSync(process.execPath, [typescript.compiler, '-p', join(sourceRoot, 'ncp-ts', 'tsconfig.json')], {
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
      env: { ...process.env, NCP_TYPESCRIPT_BIN: typescript.compiler },
      stdio: 'inherit',
    },
  )
  const typescriptAfter = exactTypeScriptCompiler(sourceRoot)
  const nodeRuntimeAfter = exactNodeRuntime()
  if (JSON.stringify(typescriptAfter) !== JSON.stringify(typescript)) {
    fail('TypeScript package or source control changed during the npm build')
  }
  if (JSON.stringify(nodeRuntimeAfter) !== JSON.stringify(nodeRuntime)) {
    fail('Node executable changed during the npm build')
  }
  return writeReceipt(
    sourceRoot,
    artifactRoot,
    revision,
    typescript,
    nodeRuntime,
    rustBuildIdentityProbePassed,
  )
}

function verifyRustBuildIdentity(sourceRoot, targetRoot, revision) {
  validateSourceRevision(revision)
  assertNoCargoConfigAncestors(sourceRoot)
  const output = execFileSync(
    'cargo',
    [
      'test',
      '--locked',
      '--offline',
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

function assertExactOrchestrationBytes(running, committed, relativePath) {
  if (!running.equals(committed)) {
    fail(`running ${relativePath} differs from source revision`)
  }
}

function exactHeadRevision(revision) {
  const head = git(['rev-parse', '--verify', 'HEAD^{commit}'], { encoding: 'utf8' }).trim()
  if (head !== revision) {
    fail(`source revision ${revision} is not exact HEAD ${head}`)
  }

  // Every local orchestration module must be the version committed at the source
  // revision. Package bytes come exclusively from exact tree materialization below.
  for (const relativePath of RELEASE_ORCHESTRATION_PATHS) {
    let committed
    try {
      committed = git(['show', `${revision}:${relativePath}`])
    } catch {
      fail(`${relativePath} is absent from source revision ${revision}`)
    }
    const running = boundedRegularFile(
      join(repositoryRoot, ...relativePath.split('/')),
      `running ${relativePath}`,
      MAX_RELEASE_ORCHESTRATION_BYTES,
    )
    try {
      assertExactOrchestrationBytes(running, committed, relativePath)
    } catch {
      fail(`running ${relativePath} differs from source revision ${revision}`)
    }
  }
}

function buildRelease(revision, output) {
  exactHeadRevision(revision)
  const outputParent = dirname(output)
  mkdirSync(outputParent, { recursive: true })
  if (existsSync(output)) fail(`release output already exists: ${output}`)

  const temporaryRoot = mkdtempSync(join(outputParent, '.ncp-npm-release-'))
  const sourceRoot = join(temporaryRoot, 'source')
  const artifactRoot = join(temporaryRoot, 'artifacts')
  mkdirSync(sourceRoot)
  try {
    materializeExactTree(revision, sourceRoot)

    // These checks run from exact materialized source, not the mutable checkout.
    execFileSync(join(sourceRoot, 'scripts', 'check-version-coherence.sh'), [], {
      cwd: sourceRoot,
      stdio: 'inherit',
    })
    execFileSync('python3', ['-I', join(sourceRoot, 'scripts', 'generate_contract_manifest.py')], {
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
  for (const name of ['package.json', 'bun.lock', 'LICENSE-MIT', 'LICENSE-APACHE']) {
    copyFileSync(join(repositoryRoot, name), join(destination, name))
  }
  const controlDestination = join(destination, 'security', 'toolchains')
  mkdirSync(controlDestination, { recursive: true })
  copyFileSync(
    join(repositoryRoot, ...TYPESCRIPT_CONTROL_PATH.split('/')),
    join(controlDestination, 'typescript-5.9.2.v1.json'),
  )
  cpSync(ncpTsRoot, join(destination, 'ncp-ts'), { recursive: true })
}

function verifyTypeScriptMutationGuard(destination) {
  const packageRoot = join(destination, 'typescript-fixture')
  mkdirSync(join(packageRoot, 'bin'), { recursive: true })
  mkdirSync(join(packageRoot, 'lib'), { recursive: true })
  writeFileSync(join(packageRoot, 'bin', 'tsc'), '#!/usr/bin/env node\nrequire("../lib/_tsc.js")\n')
  writeFileSync(join(packageRoot, 'package.json'), '{"name":"typescript","version":"0.0.0"}\n')
  writeFileSync(join(packageRoot, 'lib', '_tsc.js'), 'export const marker = "before"\n')
  const before = typeScriptPackageTree(packageRoot)
  const launcherBefore = before.files.find(({ path }) => path === 'bin/tsc')?.sha256
  const manifestBefore = before.files.find(({ path }) => path === 'package.json')?.sha256
  writeFileSync(join(packageRoot, 'lib', '_tsc.js'), 'export const marker = "after"\n')
  const after = typeScriptPackageTree(packageRoot)
  assert.equal(after.files.find(({ path }) => path === 'bin/tsc')?.sha256, launcherBefore)
  assert.equal(
    after.files.find(({ path }) => path === 'package.json')?.sha256,
    manifestBefore,
  )
  assert.throws(() =>
    assertTypeScriptTreeMatches(after, before, 'mutated TypeScript package fixture'),
  )
}

function verifyTypeScriptTreeBoundaryGuards(destination) {
  const linkedRoot = join(destination, 'typescript-linked-fixture')
  mkdirSync(linkedRoot)
  writeFileSync(join(linkedRoot, 'target.js'), 'export const value = 1\n')
  symlinkSync('target.js', join(linkedRoot, 'linked.js'))
  assert.throws(() => typeScriptPackageTree(linkedRoot))
  rmSync(linkedRoot, { recursive: true, force: true })

  const hardlinkedRoot = join(destination, 'typescript-hardlinked-fixture')
  mkdirSync(hardlinkedRoot)
  writeFileSync(join(hardlinkedRoot, 'target.js'), 'export const value = 1\n')
  linkSync(join(hardlinkedRoot, 'target.js'), join(hardlinkedRoot, 'alias.js'))
  assert.throws(
    () => typeScriptPackageTree(hardlinkedRoot),
    /reinstall with bun install --frozen-lockfile --backend=copyfile --force/,
  )
  rmSync(hardlinkedRoot, { recursive: true, force: true })

  const nonAsciiRoot = join(destination, 'typescript-non-ascii-fixture')
  mkdirSync(nonAsciiRoot)
  writeFileSync(join(nonAsciiRoot, 'café.js'), 'export const value = 1\n')
  assert.throws(() => typeScriptPackageTree(nonAsciiRoot))
  rmSync(nonAsciiRoot, { recursive: true, force: true })
}

function verifyTypeScriptLockGuards() {
  const version = '5.9.2'
  const integrity =
    'sha512-CWBzXQrc/qOkhidw1OzBTQuYRbfyxDXJMVJ1XNwUHGROVmuaeiEm3OslpZ1RV96d7SKKjZKrSJu3+t/xlw3R9A=='
  const valid = readFileSync(join(repositoryRoot, 'bun.lock'), 'utf8')
  const packageLine = valid
    .split('\n')
    .find((line) => line.includes(`"typescript@${version}"`))
  assert.ok(packageLine)
  assert.doesNotThrow(() => exactTypeScriptBunLock(valid, version, integrity))
  for (const hostile of [
    valid.replace(packageLine, `// ${packageLine}`),
    valid.replace(packageLine, `${packageLine}\n${packageLine}`),
    valid.replace(integrity, 'sha512-YQ=='),
    valid.replace('"typescript": "5.9.2"', '"typescript": "5.9.3"'),
    valid.replace('  "packages": {\n', '  "packages": {},\n  "packages": {\n'),
    valid.replace(
      '      "name": "@sepahead/ncp",',
      '      "name": "attacker",\n      "name": "@sepahead/ncp",',
    ),
    valid.replace('{ "bin": {', '{ "bin": {}, "bin": {'),
  ]) {
    assert.throws(() => exactTypeScriptBunLock(hostile, version, integrity))
  }
  assert.throws(() => canonicalSha512Integrity('sha512-YQ==', 'hostile SRI'))
}

function verifyNpmManifestDependencyGuards() {
  for (const [path, context] of [
    [join(repositoryRoot, 'package.json'), 'root package.json'],
    [join(ncpTsRoot, 'package.json'), 'ncp-ts/package.json'],
  ]) {
    const { value: manifest } = readUniqueJsonObject(path, context)
    assert.equal(exactNpmDependencySurface(manifest, context), '5.9.2')
    for (const field of NPM_UNREVIEWED_PACKAGE_GRAPH_FIELDS) {
      const hostile = JSON.parse(JSON.stringify(manifest))
      hostile[field] = ['bundleDependencies', 'bundledDependencies'].includes(field)
        ? ['evil']
        : { evil: '1.0.0' }
      assert.throws(() => exactNpmDependencySurface(hostile, context))
    }
    const extraDevelopmentDependency = JSON.parse(JSON.stringify(manifest))
    extraDevelopmentDependency.devDependencies.evil = '1.0.0'
    assert.throws(() => exactNpmDependencySurface(extraDevelopmentDependency, context))
  }
  assert.throws(() =>
    parseUniqueJsonObject(
      '{"devDependencies":{},"devDependencies":{"typescript":"5.9.2"}}',
      'hostile package.json',
    ),
  )
}

function verifyOrchestrationSourceGuard() {
  const committed = Buffer.from('export const strict = true\n')
  const hostile = Buffer.from(committed)
  hostile[0] ^= 1
  assert.doesNotThrow(() =>
    assertExactOrchestrationBytes(committed, committed, 'fixture.mjs'),
  )
  assert.throws(() =>
    assertExactOrchestrationBytes(hostile, committed, 'fixture.mjs'),
  )
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
    verifyTypeScriptMutationGuard(temporaryRoot)
    verifyTypeScriptTreeBoundaryGuards(temporaryRoot)
    verifyTypeScriptLockGuards()
    verifyNpmManifestDependencyGuards()
    verifyOrchestrationSourceGuard()
    copySelfTestSource(sourceRoot)
    const receipt = compileAndVerify(sourceRoot, artifactRoot, revision, true)
    assert.equal(receipt.schema, 'ncp.npm-release-build-receipt.v2')
    assert.equal(receipt.source_revision, revision)
    assert.equal(receipt.build_identity, revision)
    assert.equal(receipt.rust_build_identity_probe_passed, true)
    assert.match(receipt.node_executable_sha256, /^[0-9a-f]{64}$/)
    assert.equal(receipt.node_executable_pre_post_match, true)
    assert.match(receipt.typescript_control_sha256, /^[0-9a-f]{64}$/)
    assert.match(receipt.typescript_lockfile_sha256, /^[0-9a-f]{64}$/)
    assert.equal(
      receipt.typescript_registry_tarball_evidence,
      TYPESCRIPT_REGISTRY_TARBALL_EVIDENCE,
    )
    assert.match(receipt.typescript_compiler_launcher_sha256, /^[0-9a-f]{64}$/)
    assert.match(receipt.typescript_package_manifest_sha256, /^[0-9a-f]{64}$/)
    assert.equal(receipt.typescript_package_tree.file_count, 132)
    assert.equal(receipt.typescript_package_tree.total_bytes, 23_622_869)
    assert.equal(
      receipt.typescript_package_tree.manifest_sha256,
      '93e852b782eb0932c565b026f4d24173d127359f1283cb41cecea12a7b1286e1',
    )
    assert.equal(receipt.typescript_package_tree.files.length, 132)
    assert.equal(receipt.typescript_package_tree_pre_post_match, true)
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
