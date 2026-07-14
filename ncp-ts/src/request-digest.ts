/** NCP request-digest-v1 semantic projection and SHA-256.
 *
 * This is an independent TypeScript implementation of the normative typed,
 * length-prefixed projection. It deliberately does not call the Rust FFI.
 */

export const REQUEST_DIGEST_DOMAIN_V1 = 'ncp.request-digest.v1\0'
export const MAX_REQUEST_PROJECTION_BYTES = 2_097_152
const MAX_NESTING_DEPTH = 32
const MAX_FINITE_NUMBER_MAGNITUDE = 1e300

const TAG_NULL = 0x00
const TAG_FALSE = 0x01
const TAG_TRUE = 0x02
const TAG_NUMBER = 0x03
const TAG_STRING = 0x04
const TAG_ARRAY = 0x05
const TAG_OBJECT = 0x06

type Location = 'root' | 'operation' | 'nested'

export class RequestDigestError extends Error {
  constructor(detail: string) {
    super(`NCP-OP-001: ${detail}`)
    this.name = 'RequestDigestError'
  }
}

function utf8(value: string): Uint8Array {
  for (let index = 0; index < value.length; index++) {
    const unit = value.charCodeAt(index)
    if (unit >= 0xd800 && unit <= 0xdbff) {
      const next = value.charCodeAt(index + 1)
      if (!(next >= 0xdc00 && next <= 0xdfff)) {
        throw new RequestDigestError('canonical request contains an unpaired high surrogate')
      }
      index++
    } else if (unit >= 0xdc00 && unit <= 0xdfff) {
      throw new RequestDigestError('canonical request contains an unpaired low surrogate')
    }
  }
  return new TextEncoder().encode(value)
}

class Writer {
  private readonly bytes: number[] = []

  pushByte(value: number): void {
    this.reserve(1)
    this.bytes.push(value)
  }

  push(values: Uint8Array): void {
    this.reserve(values.byteLength)
    for (const value of values) this.bytes.push(value)
  }

  pushLength(value: number): void {
    if (!Number.isSafeInteger(value) || value < 0) {
      throw new RequestDigestError('canonical projection length is not a safe integer')
    }
    const bytes = new Uint8Array(8)
    new DataView(bytes.buffer).setBigUint64(0, BigInt(value), false)
    this.push(bytes)
  }

  finish(): Uint8Array {
    return Uint8Array.from(this.bytes)
  }

  private reserve(count: number): void {
    if (this.bytes.length + count > MAX_REQUEST_PROJECTION_BYTES) {
      throw new RequestDigestError('canonical request projection exceeds its byte budget')
    }
  }
}

function encodeString(writer: Writer, value: string): void {
  const bytes = utf8(value)
  writer.pushByte(TAG_STRING)
  writer.pushLength(bytes.byteLength)
  writer.push(bytes)
}

function compareUtf8(left: string, right: string): number {
  const a = utf8(left)
  const b = utf8(right)
  const length = Math.min(a.byteLength, b.byteLength)
  for (let index = 0; index < length; index++) {
    if (a[index] !== b[index]) return a[index]! - b[index]!
  }
  return a.byteLength - b.byteLength
}

function excluded(location: Location, key: string): boolean {
  return (
    (location === 'root' && key === 'authority') ||
    (location === 'operation' && (key === 'request_digest' || key === 'retry'))
  )
}

function encodeValue(writer: Writer, value: unknown, depth: number, location: Location): void {
  if (depth > MAX_NESTING_DEPTH) {
    throw new RequestDigestError('canonical request projection exceeds the nesting-depth budget')
  }
  if (value === null) {
    writer.pushByte(TAG_NULL)
    return
  }
  if (value === false) {
    writer.pushByte(TAG_FALSE)
    return
  }
  if (value === true) {
    writer.pushByte(TAG_TRUE)
    return
  }
  if (typeof value === 'number') {
    if (!Number.isFinite(value) || Math.abs(value) > MAX_FINITE_NUMBER_MAGNITUDE) {
      throw new RequestDigestError('canonical request contains an out-of-budget number')
    }
    const bytes = new Uint8Array(8)
    new DataView(bytes.buffer).setFloat64(0, value, false)
    writer.pushByte(TAG_NUMBER)
    writer.push(bytes)
    return
  }
  if (typeof value === 'string') {
    encodeString(writer, value)
    return
  }
  if (Array.isArray(value)) {
    writer.pushByte(TAG_ARRAY)
    writer.pushLength(value.length)
    for (const child of value) encodeValue(writer, child, depth + 1, 'nested')
    return
  }
  if (typeof value !== 'object' || value === undefined) {
    throw new RequestDigestError(`canonical request contains unsupported ${typeof value} value`)
  }
  const prototype = Object.getPrototypeOf(value)
  if (prototype !== Object.prototype && prototype !== null) {
    throw new RequestDigestError('canonical request contains a non-JSON object')
  }
  const object = value as Record<string, unknown>
  const entries = Object.entries(object)
    .filter(([key]) => !excluded(location, key))
    .sort(([left], [right]) => compareUtf8(left, right))
  writer.pushByte(TAG_OBJECT)
  writer.pushLength(entries.length)
  for (const [key, child] of entries) {
    encodeString(writer, key)
    const childLocation = location === 'root' && key === 'operation' ? 'operation' : 'nested'
    encodeValue(writer, child, depth + 1, childLocation)
  }
}

function mutationObject(request: unknown): Record<string, unknown> {
  if (request === null || typeof request !== 'object' || Array.isArray(request)) {
    throw new RequestDigestError('mutation request must be a JSON object')
  }
  const object = request as Record<string, unknown>
  if (!['step_request', 'run_request', 'close_session'].includes(String(object.kind))) {
    throw new RequestDigestError(
      `request kind ${JSON.stringify(object.kind)} is not a state-mutating lifecycle request`,
    )
  }
  if (object.operation === null || typeof object.operation !== 'object' || Array.isArray(object.operation)) {
    throw new RequestDigestError('mutation request operation must be an object')
  }
  return object
}

/** Exact request-digest-v1 projection bytes. */
export function canonicalRequestProjection(request: unknown): Uint8Array {
  const object = mutationObject(request)
  const writer = new Writer()
  writer.push(utf8(REQUEST_DIGEST_DOMAIN_V1))
  encodeValue(writer, object, 0, 'root')
  return writer.finish()
}

// SHA-256 (FIPS 180-4), kept dependency-free so the SDK works in browsers and
// Node without an ambient crypto API. All additions are reduced to uint32.
const SHA256_K = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
  0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
  0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
  0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
  0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
  0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
  0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
  0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
  0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
])

function rotateRight(value: number, count: number): number {
  return (value >>> count) | (value << (32 - count))
}

function sha256(input: Uint8Array): Uint8Array {
  const bitLength = BigInt(input.byteLength) * 8n
  const paddedLength = Math.ceil((input.byteLength + 9) / 64) * 64
  const padded = new Uint8Array(paddedLength)
  padded.set(input)
  padded[input.byteLength] = 0x80
  new DataView(padded.buffer).setBigUint64(paddedLength - 8, bitLength, false)

  let h0 = 0x6a09e667
  let h1 = 0xbb67ae85
  let h2 = 0x3c6ef372
  let h3 = 0xa54ff53a
  let h4 = 0x510e527f
  let h5 = 0x9b05688c
  let h6 = 0x1f83d9ab
  let h7 = 0x5be0cd19
  const words = new Uint32Array(64)
  const view = new DataView(padded.buffer)

  for (let offset = 0; offset < paddedLength; offset += 64) {
    for (let index = 0; index < 16; index++) words[index] = view.getUint32(offset + index * 4, false)
    for (let index = 16; index < 64; index++) {
      const x = words[index - 15]!
      const y = words[index - 2]!
      const s0 = rotateRight(x, 7) ^ rotateRight(x, 18) ^ (x >>> 3)
      const s1 = rotateRight(y, 17) ^ rotateRight(y, 19) ^ (y >>> 10)
      words[index] = (words[index - 16]! + s0 + words[index - 7]! + s1) >>> 0
    }
    let a = h0
    let b = h1
    let c = h2
    let d = h3
    let e = h4
    let f = h5
    let g = h6
    let h = h7
    for (let index = 0; index < 64; index++) {
      const s1 = rotateRight(e, 6) ^ rotateRight(e, 11) ^ rotateRight(e, 25)
      const choice = (e & f) ^ (~e & g)
      const t1 = (h + s1 + choice + SHA256_K[index]! + words[index]!) >>> 0
      const s0 = rotateRight(a, 2) ^ rotateRight(a, 13) ^ rotateRight(a, 22)
      const majority = (a & b) ^ (a & c) ^ (b & c)
      const t2 = (s0 + majority) >>> 0
      h = g
      g = f
      f = e
      e = (d + t1) >>> 0
      d = c
      c = b
      b = a
      a = (t1 + t2) >>> 0
    }
    h0 = (h0 + a) >>> 0
    h1 = (h1 + b) >>> 0
    h2 = (h2 + c) >>> 0
    h3 = (h3 + d) >>> 0
    h4 = (h4 + e) >>> 0
    h5 = (h5 + f) >>> 0
    h6 = (h6 + g) >>> 0
    h7 = (h7 + h) >>> 0
  }

  const output = new Uint8Array(32)
  const outputView = new DataView(output.buffer)
  ;[h0, h1, h2, h3, h4, h5, h6, h7].forEach((value, index) => {
    outputView.setUint32(index * 4, value, false)
  })
  return output
}

/** Lowercase SHA-256 of the request-digest-v1 projection. */
export function requestDigest(request: unknown): string {
  return Array.from(sha256(canonicalRequestProjection(request)), (byte) =>
    byte.toString(16).padStart(2, '0'),
  ).join('')
}

/** Verify the embedded operation.request_digest. */
export function verifyRequestDigest(request: unknown): void {
  const object = mutationObject(request)
  const operation = object.operation as Record<string, unknown>
  if (typeof operation.request_digest !== 'string') {
    throw new RequestDigestError('operation.request_digest is required')
  }
  if (operation.request_digest !== requestDigest(object)) {
    throw new RequestDigestError('operation.request_digest does not cover the canonical request')
  }
}
