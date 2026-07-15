#!/usr/bin/env node
/** Schema-complete proof that stable JSON integers remain exact in TypeScript.
 *
 * Every reachable integer path is discovered from the complete stable schema
 * set. Each path must carry the universal safe bounds, survive the exact safe
 * boundary through bounded parsing, reject an unsafe token before JSON.parse,
 * and reject the same unsafe value when supplied as a programmatic JS object.
 */

import { createHash } from 'node:crypto'
import { readFileSync, readdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  assertNcpMessage,
  BoundedJsonError,
  JSON_LIMITS,
  parseBoundedJson,
} from '../dist/index.js'

const here = dirname(fileURLToPath(import.meta.url))
const repository = join(here, '..', '..')
const schemasDirectory = join(repository, 'schemas')
const vectorsDirectory = join(repository, 'conformance', 'vectors')
const surface = JSON.parse(readFileSync(join(repository, 'contract', 'surface.v1.json'), 'utf8'))
const schemaIndex = JSON.parse(readFileSync(join(schemasDirectory, 'index.json'), 'utf8'))
const stableKinds = new Set(surface.messages['stable-1.0'])
const indexedKinds = new Set(schemaIndex.messages)
const schemaFiles = readdirSync(schemasDirectory)
  .filter((name) => name.endsWith('.schema.json'))
  .sort()
const schemaKinds = new Set(schemaFiles.map((name) => name.slice(0, -'.schema.json'.length)))

const failures = []
const check = (condition, message) => {
  if (!condition) failures.push(message)
}
const exactSet = (left, right, label) => {
  const a = [...left].sort()
  const b = [...right].sort()
  check(JSON.stringify(a) === JSON.stringify(b), `${label}: got ${JSON.stringify(a)}, want ${JSON.stringify(b)}`)
}

exactSet(stableKinds, indexedKinds, 'stable surface vs schema index')
exactSet(stableKinds, schemaKinds, 'stable surface vs schema files')

const decodePointer = (part) => part.replaceAll('~1', '/').replaceAll('~0', '~')
const resolve = (node, root) => {
  if (typeof node?.$ref !== 'string') return node
  if (!node.$ref.startsWith('#/')) throw new Error(`non-local schema ref ${node.$ref}`)
  let current = root
  for (const part of node.$ref.slice(2).split('/')) current = current[decodePointer(part)]
  if (current === undefined) throw new Error(`unresolved schema ref ${node.$ref}`)
  return current
}
const isIntegerNode = (node) =>
  node?.type === 'integer' || (Array.isArray(node?.type) && node.type.includes('integer'))

const property = (name) => ({ type: 'property', name })
const arrayItem = Object.freeze({ type: 'array' })
const mapValue = Object.freeze({ type: 'map' })
const pathName = (kind, segments) =>
  `${kind}${segments
    .map((segment) =>
      segment.type === 'property'
        ? `.${segment.name}`
        : segment.type === 'array'
          ? '[]'
          : '{*}',
    )
    .join('')}`

function walkIntegers(node, root, segments, activeRefs = new Set()) {
  if (typeof node?.$ref === 'string') {
    if (activeRefs.has(node.$ref)) throw new Error(`recursive stable schema ref ${node.$ref}`)
    const next = new Set(activeRefs)
    next.add(node.$ref)
    return walkIntegers(resolve(node, root), root, segments, next)
  }
  if (isIntegerNode(node)) return [{ segments, node }]
  const found = []
  for (const keyword of ['anyOf', 'oneOf']) {
    if (Array.isArray(node?.[keyword])) {
      for (const branch of node[keyword]) found.push(...walkIntegers(branch, root, segments, activeRefs))
    }
  }
  if (node?.type === 'object' || node?.properties !== undefined) {
    for (const [name, child] of Object.entries(node.properties ?? {})) {
      found.push(...walkIntegers(child, root, [...segments, property(name)], activeRefs))
    }
    if (node.additionalProperties !== null && typeof node.additionalProperties === 'object') {
      found.push(...walkIntegers(node.additionalProperties, root, [...segments, mapValue], activeRefs))
    }
  }
  if ((node?.type === 'array' || node?.items !== undefined) && typeof node.items === 'object') {
    found.push(...walkIntegers(node.items, root, [...segments, arrayItem], activeRefs))
  }
  return found
}

const vectorByKind = new Map()
for (const kind of stableKinds) {
  const value = JSON.parse(readFileSync(join(vectorsDirectory, `${kind}.json`), 'utf8'))
  if (value.kind !== kind) throw new Error(`${kind}.json carries kind ${JSON.stringify(value.kind)}`)
  vectorByKind.set(kind, value)
}

// The canonical corpus intentionally omits several optional integer members.
// Materialize valid representatives so every discovered schema path executes.
const receiptSource = structuredClone(vectorByKind.get('session_closed').receipt)
function augmented(kind) {
  const value = structuredClone(vectorByKind.get(kind))
  if (kind === 'open_session') {
    value.sim.seed = 1
    value.record.targets[0].ids = [1]
    value.stimulus.targets[0].ids = [1]
  } else if (kind === 'observation_frame') {
    value.receipt = structuredClone(receiptSource)
    value.records['0_integer_probe'] = {
      port: 'integer_probe',
      target: 'integer_probe',
      observable: 'spikes',
      times: [0],
      values: [],
      senders: [1],
      unit: null,
      recordable: null,
    }
  } else if (kind === 'error') {
    const closed = vectorByKind.get('session_closed')
    value.session_id = closed.session_id
    value.session = structuredClone(closed.session)
    value.receipt = { ...structuredClone(receiptSource), outcome: 'rejected' }
  }
  return value
}

function concretePath(root, segments, label) {
  const result = []
  let current = root
  for (const segment of segments) {
    if (segment.type === 'property') {
      if (current === null || typeof current !== 'object' || !(segment.name in current)) {
        throw new Error(`${label}: missing property ${segment.name}`)
      }
      result.push(segment.name)
      current = current[segment.name]
    } else if (segment.type === 'array') {
      if (!Array.isArray(current) || current.length === 0) {
        throw new Error(`${label}: no representative array element`)
      }
      result.push(0)
      current = current[0]
    } else {
      if (current === null || typeof current !== 'object' || Array.isArray(current)) {
        throw new Error(`${label}: map representative is not an object`)
      }
      const keys = Object.keys(current).sort()
      if (keys.length === 0) throw new Error(`${label}: no representative map member`)
      result.push(keys[0])
      current = current[keys[0]]
    }
  }
  return result
}

function setPath(root, path, value) {
  let current = root
  for (const segment of path.slice(0, -1)) current = current[segment]
  current[path.at(-1)] = value
}

function getPath(root, path) {
  let current = root
  for (const segment of path) current = current[segment]
  return current
}

const inventory = []
for (const filename of schemaFiles) {
  const schema = JSON.parse(readFileSync(join(schemasDirectory, filename), 'utf8'))
  const kind = schema.properties?.kind?.const
  if (!stableKinds.has(kind)) throw new Error(`${filename}: non-stable or missing kind ${JSON.stringify(kind)}`)
  const discovered = walkIntegers(schema, schema, [])
  const signatures = new Set()
  const base = augmented(kind)
  try {
    assertNcpMessage(base, kind)
  } catch (error) {
    failures.push(`${kind}: integer-coverage representative is invalid: ${String(error)}`)
  }

  for (const { segments, node } of discovered) {
    const label = pathName(kind, segments)
    check(!signatures.has(label), `${label}: duplicate reachable integer schema path`)
    signatures.add(label)
    check(node.maximum === JSON_LIMITS.safeIntegerMax, `${label}: maximum is not JSON safe max`)
    check(
      Number.isSafeInteger(node.minimum) && node.minimum >= JSON_LIMITS.safeIntegerMin,
      `${label}: minimum is absent or outside JSON safe range`,
    )
    check(node.format === 'int64' || node.format === 'uint64', `${label}: missing int64/uint64 format`)

    let concrete
    try {
      concrete = concretePath(base, segments, label)
    } catch (error) {
      failures.push(String(error))
      continue
    }

    const safe = structuredClone(base)
    setPath(safe, concrete, JSON_LIMITS.safeIntegerMax)
    try {
      const parsed = parseBoundedJson(JSON.stringify(safe))
      check(
        getPath(parsed, concrete) === JSON_LIMITS.safeIntegerMax,
        `${label}: safe maximum did not parse exactly`,
      )
    } catch (error) {
      failures.push(`${label}: safe maximum rejected by bounded parser: ${String(error)}`)
    }

    const unsafe = structuredClone(base)
    setPath(unsafe, concrete, JSON_LIMITS.safeIntegerMax + 1)
    try {
      parseBoundedJson(JSON.stringify(unsafe))
      failures.push(`${label}: unsafe integer token reached JSON.parse`)
    } catch (error) {
      check(
        error instanceof BoundedJsonError && error.code === 'NCP-LIMIT-006',
        `${label}: unsafe raw token returned wrong failure ${String(error)}`,
      )
    }
    try {
      assertNcpMessage(unsafe, kind)
      failures.push(`${label}: unsafe programmatic Number passed semantic validation`)
    } catch (error) {
      check(
        String(error).includes('exact JSON integer'),
        `${label}: unsafe programmatic Number was rejected by the wrong guard: ${String(error)}`,
      )
    }

    inventory.push({
      kind,
      path: label,
      format: node.format,
      minimum: node.minimum,
      maximum: node.maximum,
    })
  }
}

inventory.sort((left, right) => left.path.localeCompare(right.path))
check(inventory.length === 45, `stable integer inventory count changed: got ${inventory.length}, want 45`)
check(new Set(inventory.map(({ path }) => path)).size === inventory.length, 'integer inventory paths are not unique')

if (failures.length > 0) {
  console.error(`FAIL TypeScript stable integer safety: ${failures.length} divergence(s)`)
  for (const failure of failures) console.error(`  - ${failure}`)
  process.exit(1)
}

const digest = createHash('sha256')
  .update(JSON.stringify(inventory))
  .digest('hex')
console.log(
  `OK TypeScript stable integer safety: ${inventory.length} schema-complete paths; ` +
    `${inventory.length} exact-boundary parses + ${inventory.length * 2} unsafe-path rejections; ` +
    `inventory_sha256=${digest}`,
)
