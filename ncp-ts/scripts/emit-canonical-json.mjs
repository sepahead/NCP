#!/usr/bin/env node
/** Machine-readable TypeScript producer/consumer for the cross-language
 * canonical-byte matrix. Human diagnostics go to stderr; stdout is one report. */

import { readFileSync, readdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { canonicalizeNcpJson } from '../dist/index.js'

const here = dirname(fileURLToPath(import.meta.url))
const repository = join(here, '..', '..')
const vectorsDirectory = join(repository, 'conformance', 'vectors')
const manifest = JSON.parse(
  readFileSync(join(repository, 'conformance', 'manifest.v1.json'), 'utf8'),
)
const requiredIds = new Set(
  manifest.vectors
    .filter(
      (vector) =>
        vector.required === true &&
        vector.stability === 'stable-1.0' &&
        vector.suite === 'wire-shape' &&
        vector.applicability?.implementations?.includes('typescript'),
    )
    .map((vector) => vector.id),
)

const exactKeys = (actual, expected, label) => {
  const got = [...actual].sort()
  const want = [...expected].sort()
  if (JSON.stringify(got) !== JSON.stringify(want)) {
    throw new Error(`${label}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`)
  }
}

const kindFromId = (id) => {
  const match = /^wire\/([^/]+)\/canonical$/u.exec(id)
  if (match === null) throw new Error(`invalid canonical wire id ${JSON.stringify(id)}`)
  return match[1]
}

const emitOwnVectors = () => {
  const vectors = {}
  for (const filename of readdirSync(vectorsDirectory).filter((name) => name.endsWith('.json')).sort()) {
    const raw = readFileSync(join(vectorsDirectory, filename), 'utf8')
    const parsed = JSON.parse(raw)
    const id = `wire/${parsed.kind}/canonical`
    if (Object.hasOwn(vectors, id)) throw new Error(`duplicate TypeScript vector ${id}`)
    vectors[id] = canonicalizeNcpJson(raw, parsed.kind)
  }
  exactKeys(Object.keys(vectors), requiredIds, 'TypeScript producer required vector set')
  return {
    schema: 'ncp.canonical-json-emission-report.v1',
    implementation: 'typescript',
    vectors,
  }
}

const consumeProducerMatrix = () => {
  const input = JSON.parse(readFileSync(0, 'utf8'))
  const expectedProducers = new Set(['rust', 'python-ffi', 'cpp-ffi', 'typescript'])
  exactKeys(Object.keys(input.producers ?? {}), expectedProducers, 'TypeScript consumer producer set')
  const producers = {}
  for (const [producer, vectors] of Object.entries(input.producers)) {
    exactKeys(Object.keys(vectors), requiredIds, `TypeScript consumer ${producer} vector set`)
    const consumed = {}
    for (const [id, encoded] of Object.entries(vectors)) {
      const kind = kindFromId(id)
      consumed[id] = canonicalizeNcpJson(encoded, kind)
    }
    producers[producer] = consumed
  }
  return {
    schema: 'ncp.canonical-json-consumer-report.v1',
    consumer: 'typescript',
    producers,
  }
}

const report = process.argv.includes('--consume') ? consumeProducerMatrix() : emitOwnVectors()
process.stdout.write(JSON.stringify(report))
