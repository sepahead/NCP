// Deterministic WebSocket transport regressions. No server or network setup is
// involved: the transport sees its DOM callback surface through this fake.
import assert from 'node:assert/strict'

import {
  JSON_LIMITS,
  WebSocketNeuroSim,
  WEBSOCKET_TRANSPORT_DEFAULTS,
} from '../dist/index.js'

class FakeWebSocket {
  static instances = []

  onopen = null
  onmessage = null
  onerror = null
  onclose = null
  sent = []
  closeCalls = 0
  bufferedAmount = 0
  stallWrites = false
  throwOnSend = false

  constructor(url) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }

  send(payload) {
    if (this.throwOnSend) throw new Error('injected send failure')
    this.sent.push(payload)
    if (this.stallWrites) this.bufferedAmount += new TextEncoder().encode(payload).byteLength
  }

  close() {
    this.closeCalls++
  }

  open() {
    this.onopen?.({})
  }

  reply(payload) {
    this.onmessage?.({ data: payload })
  }

  error() {
    this.onerror?.({})
  }

  peerClose() {
    this.onclose?.({})
  }
}

const latestSocket = () => FakeWebSocket.instances.at(-1)
const realSetTimeout = globalThis.setTimeout
const realClearTimeout = globalThis.clearTimeout

async function rejectsPromptly(promise, pattern) {
  let timer
  const timeout = new Promise((_, reject) => {
    timer = realSetTimeout(() => reject(new Error('WebSocket request did not settle')), 500)
  })
  try {
    await assert.rejects(Promise.race([promise, timeout]), pattern)
  } finally {
    realClearTimeout(timer)
  }
}

async function withFakeTimers(run) {
  const timers = new Map()
  let now = 0
  let nextId = 0
  globalThis.setTimeout = (callback, delay = 0, ...args) => {
    const id = ++nextId
    timers.set(id, { due: now + delay, callback: () => callback(...args) })
    return id
  }
  globalThis.clearTimeout = (id) => timers.delete(id)
  const advance = (milliseconds) => {
    const target = now + milliseconds
    let callbacks = 0
    while (true) {
      const next = [...timers].sort((left, right) => left[1].due - right[1].due)[0]
      if (!next || next[1].due > target) break
      assert.ok(++callbacks <= 10_000, 'fake timer callback budget exceeded')
      timers.delete(next[0])
      now = next[1].due
      next[1].callback()
    }
    now = target
  }
  try {
    await run(advance)
    assert.equal(timers.size, 0, 'settled transports must release every timer')
  } finally {
    globalThis.setTimeout = realSetTimeout
    globalThis.clearTimeout = realClearTimeout
  }
}

function messageWithBytes(payloadBytes, unit = 'x') {
  const chunks = Array.from({ length: 16 }, () => '')
  let remaining = payloadBytes - JSON.stringify({ chunks }).length
  const unitBytes = new TextEncoder().encode(unit).byteLength
  for (let index = 0; index < chunks.length; index++) {
    const length = Math.min(JSON_LIMITS.maxStringBytes, remaining)
    chunks[index] = unit.repeat(Math.floor(length / unitBytes)) + 'x'.repeat(length % unitBytes)
    remaining -= length
  }
  assert.equal(remaining, 0)
  assert.equal(new TextEncoder().encode(JSON.stringify({ chunks })).byteLength, payloadBytes)
  return { chunks }
}

const asciiMessageAtFrameLimit = () => messageWithBytes(JSON_LIMITS.maxFrameBytes)

const originalWebSocket = globalThis.WebSocket
globalThis.WebSocket = FakeWebSocket

try {
  // A peer close before `open` must release sends waiting on readiness.
  {
    const transport = new WebSocketNeuroSim('ws://pre-open-close')
    const send = transport.send({ request: 'pre-open-close' })
    latestSocket().peerClose()
    await rejectsPromptly(send, /NCP WebSocket closed/)
    await rejectsPromptly(transport.send({ request: 'after-close' }), /NCP WebSocket closed/)
  }

  // An error can arrive before the caller sends anything. It must not create an
  // unhandled readiness rejection, and the later send must fail immediately.
  {
    const transport = new WebSocketNeuroSim('ws://pre-open-error')
    latestSocket().error()
    await rejectsPromptly(transport.send({ request: 'after-error' }), /NCP WebSocket error/)
  }

  // Client-initiated close has the same pre-open settlement requirement.
  {
    const transport = new WebSocketNeuroSim('ws://client-close')
    const socket = latestSocket()
    const send = transport.send({ request: 'client-close' })
    transport.close()
    assert.equal(socket.closeCalls, 1)
    await rejectsPromptly(send, /NCP WebSocket closed by client/)
    await rejectsPromptly(
      transport.send({ request: 'after-client-close' }),
      /NCP WebSocket closed by client/,
    )
  }

  // Keep the healthy FIFO path pinned while exercising the same public entrypoint.
  {
    const transport = new WebSocketNeuroSim('ws://healthy')
    const socket = latestSocket()
    socket.open()
    const send = transport.send({ request: 'healthy' })
    assert.deepEqual(socket.sent, [JSON.stringify({ request: 'healthy' })])
    socket.reply(JSON.stringify({ ok: true }))
    assert.deepEqual(await send, { ok: true })
  }

  // A record-level toJSON hook cannot replace the message with a primitive or
  // array and still reserve a FIFO position.
  {
    const transport = new WebSocketNeuroSim('ws://hostile-to-json')
    const socket = latestSocket()
    socket.open()
    await rejectsPromptly(
      transport.send({ toJSON: () => null }),
      /message did not serialize to a JSON object/,
    )
    assert.equal(socket.sent.length, 0)
    transport.close()
  }

  // Serialization can consume the final request slot through a reentrant send.
  // Only the inner message is admitted, and its reply remains correctly ordered.
  {
    const transport = new WebSocketNeuroSim('ws://reentrant-count-capacity')
    const socket = latestSocket()
    const pending = Array.from(
      { length: WEBSOCKET_TRANSPORT_DEFAULTS.maxPendingRequests - 1 },
      (_, index) => transport.send({ request: index }),
    )
    await rejectsPromptly(
      transport.send({
        toJSON() {
          pending.push(transport.send({ request: 'inner' }))
          return { request: 'outer' }
        },
      }),
      /pending request capacity exceeded \(128\)/,
    )
    assert.equal(socket.sent.length, 0)
    socket.open()
    assert.equal(socket.sent.length, WEBSOCKET_TRANSPORT_DEFAULTS.maxPendingRequests)
    assert.deepEqual(JSON.parse(socket.sent.at(-1)), { request: 'inner' })
    pending.forEach((_, index) => socket.reply(JSON.stringify({ response: index })))
    assert.deepEqual(await Promise.all(pending), pending.map((_, index) => ({ response: index })))
    const next = transport.send({ request: 'after-drain' })
    socket.reply('{"ok":true}')
    assert.deepEqual(await next, { ok: true })
    transport.close()
  }

  // A toJSON hook may close the transport. Serialization cannot reopen it or
  // reserve an outer request after the inner close has rejected existing work.
  {
    const transport = new WebSocketNeuroSim('ws://reentrant-close')
    const socket = latestSocket()
    const pending = transport.send({ request: 'before-close' })
    const rejected = rejectsPromptly(pending, /closed by client/)
    await rejectsPromptly(
      transport.send({
        toJSON() {
          transport.close()
          return { request: 'outer' }
        },
      }),
      /closed by client/,
    )
    await rejected
    socket.open()
    await rejectsPromptly(transport.send({ request: 'after-close' }), /closed by client/)
    transport.close()
    assert.equal(socket.sent.length, 0)
    assert.equal(socket.closeCalls, 1)
  }

  // A serialization failure owns no reservation and cannot release the inner
  // request's slot or payload. The inner and next requests remain usable.
  {
    const transport = new WebSocketNeuroSim('ws://reentrant-serialization-failure')
    const socket = latestSocket()
    let inner
    await rejectsPromptly(
      transport.send({
        toJSON() {
          inner = transport.send({ request: 'inner' })
          throw new Error('injected serialization failure')
        },
      }),
      /injected serialization failure/,
    )
    socket.open()
    assert.deepEqual(socket.sent, ['{"request":"inner"}'])
    socket.reply('{"response":"inner"}')
    assert.deepEqual(await inner, { response: 'inner' })
    const next = transport.send({ request: 'next' })
    socket.reply('{"response":"next"}')
    assert.deepEqual(await next, { response: 'next' })
    transport.close()
  }

  // A post-open transport failure must still reject every queued request.
  {
    const transport = new WebSocketNeuroSim('ws://in-flight-error')
    const socket = latestSocket()
    socket.open()
    const send = transport.send({ request: 'in-flight-error' })
    socket.error()
    await rejectsPromptly(send, /NCP WebSocket error/)
  }

  // Canonical NCP uses WebSocket text frames. Binary frames are rejected without
  // conversion/copy; an oversized ArrayBuffer retains the exact frame-limit code.
  {
    const transport = new WebSocketNeuroSim('ws://binary-reply')
    const socket = latestSocket()
    assert.equal(socket.binaryType, 'arraybuffer')
    socket.open()
    const send = transport.send({ request: 'binary-reply' })
    socket.reply(new ArrayBuffer(8))
    await rejectsPromptly(send, /binary WebSocket replies are not canonical/)
    assert.equal(socket.closeCalls, 1)
    await rejectsPromptly(
      transport.send({ request: 'after-binary-reply' }),
      /binary WebSocket replies are not canonical/,
    )
  }
  {
    const transport = new WebSocketNeuroSim('ws://oversized-binary-reply')
    const socket = latestSocket()
    socket.open()
    const send = transport.send({ request: 'oversized-binary-reply' })
    socket.reply(new ArrayBuffer(JSON_LIMITS.maxFrameBytes + 1))
    await rejectsPromptly(send, /NCP-LIMIT-001/)
  }

  // Malformed and unsolicited replies terminate the FIFO transport so no late
  // frame can be misassigned to a different request.
  {
    const transport = new WebSocketNeuroSim('ws://malformed-reply')
    const socket = latestSocket()
    socket.open()
    const first = transport.send({ request: 'first' })
    const second = transport.send({ request: 'second' })
    socket.reply('{')
    await rejectsPromptly(first, /not valid JSON/)
    await rejectsPromptly(second, /not valid JSON/)
    assert.equal(socket.closeCalls, 1)
  }
  {
    const transport = new WebSocketNeuroSim('ws://unsolicited-reply')
    const socket = latestSocket()
    socket.open()
    socket.reply('{}')
    assert.equal(socket.closeCalls, 1)
    await rejectsPromptly(
      transport.send({ request: 'after-unsolicited-reply' }),
      /unsolicited NCP WebSocket reply/,
    )
  }

  // A synchronous browser send failure is terminal; accepting more FIFO work
  // after it would leave delivery and correlation indeterminate.
  {
    const transport = new WebSocketNeuroSim('ws://send-failure')
    const socket = latestSocket()
    socket.throwOnSend = true
    socket.open()
    await rejectsPromptly(transport.send({ request: 'send-failure' }), /injected send failure/)
    assert.equal(socket.closeCalls, 1)
    await rejectsPromptly(
      transport.send({ request: 'after-send-failure' }),
      /injected send failure/,
    )
  }

  // The normative control queue rejects the 129th outstanding request.
  {
    const transport = new WebSocketNeuroSim('ws://pre-open-pending-capacity')
    const socket = latestSocket()
    const pending = Array.from(
      { length: WEBSOCKET_TRANSPORT_DEFAULTS.maxPendingRequests },
      (_, index) => transport.send({ request: index }),
    )
    const settlements = Promise.allSettled(pending)
    await rejectsPromptly(transport.send({ request: 'overflow' }), /capacity exceeded \(128\)/)
    assert.equal(socket.sent.length, 0)
    transport.close()
    await settlements
  }

  {
    assert.equal(WEBSOCKET_TRANSPORT_DEFAULTS.maxPendingRequests, 128)
    const transport = new WebSocketNeuroSim('ws://pending-capacity')
    const socket = latestSocket()
    socket.open()
    const pending = Array.from(
      { length: WEBSOCKET_TRANSPORT_DEFAULTS.maxPendingRequests },
      (_, index) => transport.send({ request: index }),
    )
    const settlements = Promise.allSettled(pending)
    await rejectsPromptly(transport.send({ request: 'overflow' }), /capacity exceeded \(128\)/)
    transport.close()
    const outcomes = await settlements
    assert.equal(outcomes.filter(({ status }) => status === 'rejected').length, pending.length)
  }

  // Count and exact UTF-8 bytes are reserved together before an unopened socket
  // can retain a payload. Eight maximum-sized frames fit the experimental local
  // byte budget exactly; the ninth is rejected without consuming a FIFO slot.
  {
    assert.equal(
      WEBSOCKET_TRANSPORT_DEFAULTS.maxPendingPayloadBytes,
      8 * JSON_LIMITS.maxFrameBytes,
    )
    const transport = new WebSocketNeuroSim('ws://pre-open-payload-capacity')
    const socket = latestSocket()
    const message = asciiMessageAtFrameLimit()
    const pending = Array.from({ length: 8 }, () => transport.send(message))
    const settlements = Promise.allSettled(pending)
    await rejectsPromptly(
      transport.send(message),
      /queued payload capacity exceeded \(8388608 bytes\)/,
    )
    assert.equal(socket.sent.length, 0)
    transport.close()
    await settlements
  }

  // Multibyte payloads reach B-1 and B retained bytes exactly. At B-1, the
  // smallest object adds two bytes and must reject the attempted B+1 state.
  for (const remainingByte of [1, 0]) {
    const transport = new WebSocketNeuroSim(`ws://utf8-payload-capacity-${remainingByte}`)
    const socket = latestSocket()
    const full = messageWithBytes(JSON_LIMITS.maxFrameBytes, '🧠')
    const last = messageWithBytes(JSON_LIMITS.maxFrameBytes - remainingByte, '🧠')
    const messages = [...Array(7).fill(full), last]
    const expected = messages.map((message) => JSON.stringify(message))
    assert.equal(
      expected.reduce((total, payload) => total + new TextEncoder().encode(payload).byteLength, 0),
      WEBSOCKET_TRANSPORT_DEFAULTS.maxPendingPayloadBytes - remainingByte,
    )
    assert.ok(expected[0].length < JSON_LIMITS.maxFrameBytes)
    const pending = messages.map((message) => transport.send(message))
    await rejectsPromptly(transport.send({}), /queued payload capacity exceeded/)
    assert.equal(socket.sent.length, 0)
    socket.open()
    assert.deepEqual(socket.sent, expected)
    pending.forEach((_, index) => socket.reply(JSON.stringify({ response: index })))
    assert.deepEqual(await Promise.all(pending), pending.map((_, index) => ({ response: index })))
    const next = transport.send(full)
    socket.reply('{"ok":true}')
    assert.deepEqual(await next, { ok: true })
    transport.close()
  }

  // A toJSON hook can fill the byte budget while the outer message serializes.
  // Its accepted inner payload must stay intact when the outer request rejects.
  {
    const transport = new WebSocketNeuroSim('ws://reentrant-payload-capacity')
    const socket = latestSocket()
    const message = messageWithBytes(JSON_LIMITS.maxFrameBytes, '🧠')
    const pending = Array.from({ length: 7 }, () => transport.send(message))
    await rejectsPromptly(
      transport.send({
        toJSON() {
          pending.push(transport.send(message))
          return {}
        },
      }),
      /queued payload capacity exceeded/,
    )
    socket.open()
    assert.equal(socket.sent.length, 8)
    assert.ok(socket.sent.every((payload) => payload === JSON.stringify(message)))
    pending.forEach(() => socket.reply('{}'))
    assert.deepEqual(await Promise.all(pending), Array.from({ length: 8 }, () => ({})))
    transport.close()
  }

  // The exact 1 MiB JSON boundary is accepted; one additional byte is rejected
  // before WebSocket.send or FIFO reservation.
  {
    const transport = new WebSocketNeuroSim('ws://outbound-frame-boundary')
    const socket = latestSocket()
    socket.open()
    const message = asciiMessageAtFrameLimit()
    const send = transport.send(message)
    assert.equal(socket.sent[0].length, JSON_LIMITS.maxFrameBytes)
    socket.reply('{}')
    assert.deepEqual(await send, {})
  }
  {
    const transport = new WebSocketNeuroSim('ws://oversized-outbound-frame')
    const socket = latestSocket()
    socket.open()
    const message = asciiMessageAtFrameLimit()
    message.chunks[message.chunks.length - 1] += 'x'
    await rejectsPromptly(transport.send(message), /NCP-LIMIT-001/)
    assert.equal(socket.sent.length, 0)
  }

  // The frame ceiling also counts UTF-8 bytes, including complete surrogate
  // pairs. Exercise F-1, F, and F+1 while every string stays within its limit.
  for (const offset of [-1, 0, 1]) {
    const transport = new WebSocketNeuroSim(`ws://utf8-frame-boundary-${offset}`)
    const socket = latestSocket()
    socket.open()
    const message = messageWithBytes(JSON_LIMITS.maxFrameBytes + offset, '🧠')
    const send = transport.send(message)
    if (offset > 0) {
      await rejectsPromptly(send, /NCP-LIMIT-001/)
      assert.equal(socket.sent.length, 0)
    } else {
      assert.equal(
        new TextEncoder().encode(socket.sent[0]).byteLength,
        JSON_LIMITS.maxFrameBytes + offset,
      )
      socket.reply('{}')
      assert.deepEqual(await send, {})
    }
    transport.close()
  }

  // Every phase and the whole request have independent finite deadlines.
  {
    const transport = new WebSocketNeuroSim('ws://connect-timeout', {
      connectTimeoutMs: 5,
      requestTimeoutMs: 100,
    })
    const socket = latestSocket()
    await rejectsPromptly(transport.send({ request: 'connect-timeout' }), /connect timeout/)
    assert.equal(socket.closeCalls, 1)
  }

  {
    const transport = new WebSocketNeuroSim('ws://write-timeout', {
      writeTimeoutMs: 5,
      readTimeoutMs: 100,
      requestTimeoutMs: 100,
    })
    const socket = latestSocket()
    socket.stallWrites = true
    socket.open()
    await rejectsPromptly(transport.send({ request: 'write-timeout' }), /write timeout/)
    assert.equal(socket.closeCalls, 1)
  }
  {
    const transport = new WebSocketNeuroSim('ws://read-timeout', {
      readTimeoutMs: 5,
      requestTimeoutMs: 100,
    })
    const socket = latestSocket()
    socket.open()
    await rejectsPromptly(transport.send({ request: 'read-timeout' }), /read timeout/)
    assert.equal(socket.closeCalls, 1)
  }
  {
    const transport = new WebSocketNeuroSim('ws://request-timeout', {
      readTimeoutMs: 100,
      requestTimeoutMs: 5,
    })
    const socket = latestSocket()
    socket.open()
    await rejectsPromptly(transport.send({ request: 'request-timeout' }), /request timeout/)
    assert.equal(socket.closeCalls, 1)
  }

  // Expiry while a previous write is stalled retires the whole FIFO. Draining
  // later must never transmit the queued request whose deadline has passed.
  await withFakeTimers(async (advance) => {
    const transport = new WebSocketNeuroSim('ws://queued-request-timeout', {
      writeTimeoutMs: 100,
      readTimeoutMs: 100,
      requestTimeoutMs: 5,
    })
    const socket = latestSocket()
    socket.stallWrites = true
    socket.open()
    const first = transport.send({ request: 'first' })
    socket.reply('{"ok":true}')
    assert.deepEqual(await first, { ok: true })
    const queued = transport.send({ request: 'queued' })
    const rejected = rejectsPromptly(queued, /request timeout after 5 ms/)
    advance(4)
    assert.deepEqual(socket.sent, ['{"request":"first"}'])
    assert.equal(socket.closeCalls, 0)
    advance(1)
    await rejected
    socket.bufferedAmount = 0
    advance(100)
    assert.deepEqual(socket.sent, ['{"request":"first"}'])
    await rejectsPromptly(transport.send({ request: 'after-expiry' }), /request timeout/)
    assert.equal(socket.closeCalls, 1)
  })

  // A late reply cannot revive an expired FIFO or satisfy a new transport.
  // The replacement resolves only after its own socket supplies its response.
  await withFakeTimers(async (advance) => {
    const transport = new WebSocketNeuroSim('ws://late-reply', {
      readTimeoutMs: 100,
      requestTimeoutMs: 5,
    })
    const socket = latestSocket()
    socket.open()
    const rejected = rejectsPromptly(transport.send({ request: 'expired' }), /request timeout/)
    advance(5)
    await rejected
    await rejectsPromptly(transport.send({ request: 'after-expiry' }), /request timeout/)
    const replacement = new WebSocketNeuroSim('ws://replacement')
    const replacementSocket = latestSocket()
    replacementSocket.open()
    let settled = false
    const next = replacement.send({ request: 'replacement' }).then((value) => {
      settled = true
      return value
    })
    socket.reply('{"response":"expired"}')
    await Promise.resolve()
    assert.equal(settled, false)
    assert.equal(socket.closeCalls, 1)
    replacementSocket.reply('{"response":"replacement"}')
    assert.deepEqual(await next, { response: 'replacement' })
    transport.close()
    replacement.close()
    assert.equal(socket.closeCalls, 1)
  })

  // Invalid timer values fail before a socket is opened.
  {
    const socketCount = FakeWebSocket.instances.length
    assert.throws(
      () => new WebSocketNeuroSim('ws://invalid-timeout', { readTimeoutMs: 0 }),
      /positive timer-safe integer/,
    )
    assert.equal(FakeWebSocket.instances.length, socketCount)
  }
} finally {
  if (originalWebSocket === undefined) delete globalThis.WebSocket
  else globalThis.WebSocket = originalWebSocket
}

console.log('WebSocket transport smoke: 32 scenarios passed')
