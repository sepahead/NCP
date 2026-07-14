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

async function rejectsPromptly(promise, pattern) {
  let timer
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error('WebSocket request did not settle')), 500)
  })
  try {
    await assert.rejects(Promise.race([promise, timeout]), pattern)
  } finally {
    clearTimeout(timer)
  }
}

function asciiMessageAtFrameLimit() {
  const chunks = Array.from({ length: 16 }, () => '')
  let remaining = JSON_LIMITS.maxFrameBytes - JSON.stringify({ chunks }).length
  for (let index = 0; index < chunks.length; index++) {
    const length = Math.min(JSON_LIMITS.maxStringBytes, remaining)
    chunks[index] = 'x'.repeat(length)
    remaining -= length
  }
  assert.equal(remaining, 0)
  return { chunks }
}

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

console.log('WebSocket transport smoke: 19 scenarios passed')
