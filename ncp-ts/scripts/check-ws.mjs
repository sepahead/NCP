// Deterministic WebSocket transport regressions. No server or timing-sensitive
// network setup is involved: the transport sees the same DOM callback surface it
// uses in production through this controllable fake.
import assert from 'node:assert/strict'

import { WebSocketNeuroSim } from '../dist/index.js'

class FakeWebSocket {
  static instances = []

  onopen = null
  onmessage = null
  onerror = null
  onclose = null
  sent = []
  closeCalls = 0

  constructor(url) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }

  send(payload) {
    this.sent.push(payload)
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
    await Promise.resolve()
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
    await Promise.resolve()
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
    await Promise.resolve()
    socket.reply(new ArrayBuffer(8))
    await rejectsPromptly(send, /binary WebSocket replies are not canonical/)
  }
  {
    const transport = new WebSocketNeuroSim('ws://oversized-binary-reply')
    const socket = latestSocket()
    socket.open()
    const send = transport.send({ request: 'oversized-binary-reply' })
    await Promise.resolve()
    socket.reply(new ArrayBuffer(1_048_577))
    await rejectsPromptly(send, /NCP-LIMIT-001/)
  }
} finally {
  if (originalWebSocket === undefined) delete globalThis.WebSocket
  else globalThis.WebSocket = originalWebSocket
}

console.log('WebSocket transport smoke: 7 scenarios passed')
