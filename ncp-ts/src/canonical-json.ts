/** Deterministic NCP message round-trip bytes.
 *
 * The Rust reference materializes serde defaults, drops unknown object members,
 * emits struct fields in declaration order, orders map keys by UTF-8 bytes, and
 * uses serde_json/ryu spelling for binary64 values. This module mirrors that
 * projection independently for the stable message set so the mandatory corpus
 * can compare emitted bytes rather than merely reparsed values.
 */

import { parseBoundedJson } from './bounded-json.js'
import { assertNcpMessage, NCP_CONTRACT_HASH } from './client.js'

type JsonObject = Record<string, unknown>

const MISSING = Symbol('missing')
const encoder = new TextEncoder()

function record(value: unknown, path: string): JsonObject {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${path} must be an object`)
  }
  return value as JsonObject
}

function member(
  value: JsonObject,
  key: string,
  fallback: unknown | typeof MISSING = MISSING,
): unknown {
  if (Object.hasOwn(value, key) && value[key] !== undefined) return value[key]
  if (fallback !== MISSING) return fallback
  throw new Error(`canonical NCP projection is missing ${JSON.stringify(key)}`)
}

function utf8Compare(left: string, right: string): number {
  const a = encoder.encode(left)
  const b = encoder.encode(right)
  const length = Math.min(a.byteLength, b.byteLength)
  for (let index = 0; index < length; index++) {
    if (a[index] !== b[index]) return a[index]! - b[index]!
  }
  return a.byteLength - b.byteLength
}

function object(entries: Array<readonly [string, string]>): string {
  return `{${entries.map(([key, value]) => `${JSON.stringify(key)}:${value}`).join(',')}}`
}

function array(value: unknown, path: string, encode: (item: unknown, path: string) => string): string {
  if (!Array.isArray(value)) throw new Error(`${path} must be an array`)
  return `[${value.map((item, index) => encode(item, `${path}[${index}]`)).join(',')}]`
}

function map(value: unknown, path: string, encode: (item: unknown, path: string) => string): string {
  const entries = Object.entries(record(value, path)).sort(([left], [right]) =>
    utf8Compare(left, right),
  )
  return object(
    entries.map(([key, item]) => [key, encode(item, `${path}[${JSON.stringify(key)}]`)] as const),
  )
}

function string(value: unknown, path: string): string {
  if (typeof value !== 'string') throw new Error(`${path} must be a string`)
  return JSON.stringify(value)
}

function boolean(value: unknown, path: string): string {
  if (typeof value !== 'boolean') throw new Error(`${path} must be a boolean`)
  return value ? 'true' : 'false'
}

function integer(value: unknown, path: string): string {
  if (typeof value !== 'number' || !Number.isSafeInteger(value)) {
    throw new Error(`${path} must be an exact JSON-safe integer`)
  }
  return String(Object.is(value, -0) ? 0 : value)
}

/** Match serde_json's finite-f64 spelling (ryu thresholds included). */
function number(value: unknown, path: string): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error(`${path} must be a finite binary64 number`)
  }
  if (Object.is(value, -0)) return '-0.0'
  if (value === 0) return '0.0'
  const magnitude = Math.abs(value)
  if (magnitude < 1e-5 || magnitude >= 1e16) {
    return value
      .toExponential()
      .replace(/e([+-]?)0+(\d+)/u, (_match, sign: string, exponent: string) =>
        `e${sign}${exponent}`,
      )
  }
  const rendered = value.toString()
  return Number.isInteger(value) ? `${rendered}.0` : rendered
}

function nullable(
  value: unknown,
  path: string,
  encode: (item: unknown, path: string) => string,
): string {
  return value === null ? 'null' : encode(value, path)
}

const strings = (value: unknown, path: string): string => array(value, path, string)
const integers = (value: unknown, path: string): string => array(value, path, integer)
const numbers = (value: unknown, path: string): string => array(value, path, number)

function sessionRef(value: unknown, path: string): string {
  const input = record(value, path)
  return object([['generation', string(member(input, 'generation'), `${path}.generation`)]])
}

function streamPosition(value: unknown, path: string): string {
  const input = record(value, path)
  return object([
    ['epoch', string(member(input, 'epoch'), `${path}.epoch`)],
    ['seq', integer(member(input, 'seq'), `${path}.seq`)],
  ])
}

function identityClaim(value: unknown, path: string): string {
  const input = record(value, path)
  return object([
    ['principal_id', string(member(input, 'principal_id'), `${path}.principal_id`)],
    ['entity_id', string(member(input, 'entity_id'), `${path}.entity_id`)],
    ['role', string(member(input, 'role'), `${path}.role`)],
    ['plane', string(member(input, 'plane'), `${path}.plane`)],
  ])
}

function gatewayAttribution(value: unknown, path: string): string {
  const input = record(value, path)
  return object([
    ['gateway_id', string(member(input, 'gateway_id'), `${path}.gateway_id`)],
    ['source_wire', string(member(input, 'source_wire'), `${path}.source_wire`)],
  ])
}

function authorityLease(value: unknown, path: string): string {
  const input = record(value, path)
  return object([
    ['session_epoch', string(member(input, 'session_epoch'), `${path}.session_epoch`)],
    ['term', integer(member(input, 'term'), `${path}.term`)],
    ['lease_id', string(member(input, 'lease_id'), `${path}.lease_id`)],
    [
      'issuer_principal_id',
      string(member(input, 'issuer_principal_id'), `${path}.issuer_principal_id`),
    ],
    [
      'holder_principal_id',
      string(member(input, 'holder_principal_id'), `${path}.holder_principal_id`),
    ],
    [
      'holder_entity_id',
      string(member(input, 'holder_entity_id'), `${path}.holder_entity_id`),
    ],
    [
      'issued_at_utc_ms',
      integer(member(input, 'issued_at_utc_ms'), `${path}.issued_at_utc_ms`),
    ],
    [
      'expires_at_utc_ms',
      integer(member(input, 'expires_at_utc_ms'), `${path}.expires_at_utc_ms`),
    ],
  ])
}

function operationContext(value: unknown, path: string): string {
  const input = record(value, path)
  return object([
    ['operation_id', string(member(input, 'operation_id'), `${path}.operation_id`)],
    ['request_digest', string(member(input, 'request_digest'), `${path}.request_digest`)],
    ['session_epoch', string(member(input, 'session_epoch'), `${path}.session_epoch`)],
    [
      'expected_state_version',
      integer(member(input, 'expected_state_version'), `${path}.expected_state_version`),
    ],
    ['deadline_utc_ms', integer(member(input, 'deadline_utc_ms'), `${path}.deadline_utc_ms`)],
    ['retry', boolean(member(input, 'retry'), `${path}.retry`)],
  ])
}

function responderReceipt(value: unknown, path: string): string {
  const input = record(value, path)
  return object([
    ['operation_id', string(member(input, 'operation_id'), `${path}.operation_id`)],
    ['request_digest', string(member(input, 'request_digest'), `${path}.request_digest`)],
    ['result_digest', string(member(input, 'result_digest'), `${path}.result_digest`)],
    ['outcome', string(member(input, 'outcome'), `${path}.outcome`)],
    ['state_version', integer(member(input, 'state_version'), `${path}.state_version`)],
    [
      'committed_at_utc_ms',
      integer(member(input, 'committed_at_utc_ms'), `${path}.committed_at_utc_ms`),
    ],
    [
      'responder_principal_id',
      string(member(input, 'responder_principal_id'), `${path}.responder_principal_id`),
    ],
    [
      'responder_entity_id',
      string(member(input, 'responder_entity_id'), `${path}.responder_entity_id`),
    ],
  ])
}

function channelValue(value: unknown, path: string): string {
  const input = record(value, path)
  return object([
    ['data', numbers(member(input, 'data', []), `${path}.data`)],
    ['unit', nullable(member(input, 'unit', null), `${path}.unit`, string)],
  ])
}

function channelMap(value: unknown, path: string): string {
  return map(value, path, channelValue)
}

function networkRef(value: unknown, path: string): string {
  const input = record(value, path)
  return object([
    ['kind', string(member(input, 'kind'), `${path}.kind`)],
    ['ref', string(member(input, 'ref'), `${path}.ref`)],
    ['model_name', nullable(member(input, 'model_name', null), `${path}.model_name`, string)],
    [
      'population_sizes',
      map(member(input, 'population_sizes', {}), `${path}.population_sizes`, integer),
    ],
    ['params', map(member(input, 'params', {}), `${path}.params`, number)],
  ])
}

function recordTarget(value: unknown, path: string): string {
  const input = record(value, path)
  return object([
    ['port', string(member(input, 'port'), `${path}.port`)],
    ['target', string(member(input, 'target'), `${path}.target`)],
    ['observable', string(member(input, 'observable'), `${path}.observable`)],
    ['ids', integers(member(input, 'ids', []), `${path}.ids`)],
    ['cadence_ms', number(member(input, 'cadence_ms', 1), `${path}.cadence_ms`)],
    ['recordables', strings(member(input, 'recordables', []), `${path}.recordables`)],
  ])
}

function recordSpec(value: unknown, path: string): string {
  const input = record(value, path)
  return object([
    ['targets', array(member(input, 'targets', []), `${path}.targets`, recordTarget)],
  ])
}

function stimulusTarget(value: unknown, path: string): string {
  const input = record(value, path)
  return object([
    ['port', string(member(input, 'port'), `${path}.port`)],
    ['target', string(member(input, 'target'), `${path}.target`)],
    ['kind', string(member(input, 'kind'), `${path}.kind`)],
    ['ids', integers(member(input, 'ids', []), `${path}.ids`)],
    ['params', map(member(input, 'params', {}), `${path}.params`, number)],
  ])
}

function stimulusSpec(value: unknown, path: string): string {
  const input = record(value, path)
  return object([
    ['targets', array(member(input, 'targets', []), `${path}.targets`, stimulusTarget)],
  ])
}

function simConfig(value: unknown, path: string): string {
  const input = record(value, path)
  return object([
    ['dt_ms', number(member(input, 'dt_ms', 0.1), `${path}.dt_ms`)],
    ['chunk_ms', number(member(input, 'chunk_ms', 10), `${path}.chunk_ms`)],
    ['seed', nullable(member(input, 'seed', null), `${path}.seed`, integer)],
    ['mode', string(member(input, 'mode', 'stream'), `${path}.mode`)],
    ['duration_ms', nullable(member(input, 'duration_ms', null), `${path}.duration_ms`, number)],
  ])
}

function entityRef(value: unknown, path: string): string {
  const input = record(value, path)
  return object([
    ['path', string(member(input, 'path'), `${path}.path`)],
    ['role', string(member(input, 'role'), `${path}.role`)],
    ['meta', map(member(input, 'meta', {}), `${path}.meta`, string)],
  ])
}

function entityBinding(value: unknown, path: string): string {
  const input = record(value, path)
  return object([
    ['entity', entityRef(member(input, 'entity'), `${path}.entity`)],
    ['port', string(member(input, 'port'), `${path}.port`)],
    ['direction', string(member(input, 'direction', 'stimulus'), `${path}.direction`)],
  ])
}

function simProvenance(value: unknown, path: string): string {
  const input = record(value, path)
  return object([
    ['network_ref', string(member(input, 'network_ref'), `${path}.network_ref`)],
    ['backend', string(member(input, 'backend'), `${path}.backend`)],
    ['seed', nullable(member(input, 'seed', null), `${path}.seed`, integer)],
    [
      'calibrated_posterior',
      boolean(member(input, 'calibrated_posterior'), `${path}.calibrated_posterior`),
    ],
    [
      'is_simulation_output',
      boolean(member(input, 'is_simulation_output'), `${path}.is_simulation_output`),
    ],
    ['advisory_only', boolean(member(input, 'advisory_only'), `${path}.advisory_only`)],
    ['note', nullable(member(input, 'note', null), `${path}.note`, string)],
  ])
}

function observation(value: unknown, path: string): string {
  const input = record(value, path)
  return object([
    ['port', string(member(input, 'port'), `${path}.port`)],
    ['target', string(member(input, 'target'), `${path}.target`)],
    ['observable', string(member(input, 'observable'), `${path}.observable`)],
    ['times', numbers(member(input, 'times', []), `${path}.times`)],
    ['values', numbers(member(input, 'values', []), `${path}.values`)],
    ['senders', integers(member(input, 'senders', []), `${path}.senders`)],
    ['unit', nullable(member(input, 'unit', null), `${path}.unit`, string)],
    ['recordable', nullable(member(input, 'recordable', null), `${path}.recordable`, string)],
  ])
}

function channelSpec(value: unknown, path: string): string {
  const input = record(value, path)
  return object([
    ['name', string(member(input, 'name'), `${path}.name`)],
    ['kind', string(member(input, 'kind'), `${path}.kind`)],
    ['unit', nullable(member(input, 'unit', null), `${path}.unit`, string)],
    ['size', nullable(member(input, 'size', null), `${path}.size`, integer)],
    ['requirement', string(member(input, 'requirement'), `${path}.requirement`)],
    ['description', nullable(member(input, 'description', null), `${path}.description`, string)],
  ])
}

function safetyLimits(value: unknown, path: string): string {
  const input = record(value, path)
  return object([
    ['max_speed_mps', nullable(member(input, 'max_speed_mps', null), `${path}.max_speed_mps`, number)],
    ['max_tilt_rad', nullable(member(input, 'max_tilt_rad', null), `${path}.max_tilt_rad`, number)],
    [
      'geofence_radius_m',
      nullable(member(input, 'geofence_radius_m', null), `${path}.geofence_radius_m`, number),
    ],
    [
      'command_timeout_ms',
      number(member(input, 'command_timeout_ms', 500), `${path}.command_timeout_ms`),
    ],
  ])
}

function stimulusFrame(value: unknown, path: string): string {
  const input = record(value, path)
  return object([
    ['ncp_version', string(member(input, 'ncp_version'), `${path}.ncp_version`)],
    ['kind', string(member(input, 'kind'), `${path}.kind`)],
    ['session_id', string(member(input, 'session_id'), `${path}.session_id`)],
    ['t', number(member(input, 't', 0), `${path}.t`)],
    ['values', channelMap(member(input, 'values', {}), `${path}.values`)],
    ['session', sessionRef(member(input, 'session'), `${path}.session`)],
  ])
}

function canonicalMessage(value: JsonObject): string {
  const kind = value.kind as string
  switch (kind) {
    case 'open_session':
      return object([
        ['ncp_version', string(member(value, 'ncp_version'), 'open_session.ncp_version')],
        ['kind', string(kind, 'open_session.kind')],
        ['session_id', string(member(value, 'session_id'), 'open_session.session_id')],
        ['network', networkRef(member(value, 'network'), 'open_session.network')],
        ['record', recordSpec(member(value, 'record', { targets: [] }), 'open_session.record')],
        [
          'stimulus',
          stimulusSpec(member(value, 'stimulus', { targets: [] }), 'open_session.stimulus'),
        ],
        [
          'sim',
          simConfig(
            member(value, 'sim', {
              dt_ms: 0.1,
              chunk_ms: 10,
              seed: null,
              mode: 'stream',
              duration_ms: null,
            }),
            'open_session.sim',
          ),
        ],
        ['bindings', array(member(value, 'bindings', []), 'open_session.bindings', entityBinding)],
        [
          'contract_hash',
          nullable(member(value, 'contract_hash', NCP_CONTRACT_HASH), 'open_session.contract_hash', string),
        ],
        ['identity', identityClaim(member(value, 'identity'), 'open_session.identity')],
        [
          'security_profile',
          string(member(value, 'security_profile'), 'open_session.security_profile'),
        ],
        [
          'security_state_digest',
          string(member(value, 'security_state_digest'), 'open_session.security_state_digest'),
        ],
        [
          'gateway_permitted',
          boolean(member(value, 'gateway_permitted'), 'open_session.gateway_permitted'),
        ],
        [
          'gateway',
          nullable(member(value, 'gateway', null), 'open_session.gateway', gatewayAttribution),
        ],
      ])
    case 'session_opened':
      return object([
        ['ncp_version', string(member(value, 'ncp_version'), 'session_opened.ncp_version')],
        ['kind', string(kind, 'session_opened.kind')],
        ['session_id', string(member(value, 'session_id'), 'session_opened.session_id')],
        ['ok', boolean(member(value, 'ok'), 'session_opened.ok')],
        ['backend', string(member(value, 'backend'), 'session_opened.backend')],
        ['resolved', map(member(value, 'resolved', {}), 'session_opened.resolved', integer)],
        [
          'provenance',
          nullable(member(value, 'provenance', null), 'session_opened.provenance', simProvenance),
        ],
        ['error', nullable(member(value, 'error', 'session not opened'), 'session_opened.error', string)],
        [
          'contract_hash',
          nullable(member(value, 'contract_hash', NCP_CONTRACT_HASH), 'session_opened.contract_hash', string),
        ],
        ['session', nullable(member(value, 'session', null), 'session_opened.session', sessionRef)],
        ['state_version', integer(member(value, 'state_version'), 'session_opened.state_version')],
        ['identity', identityClaim(member(value, 'identity'), 'session_opened.identity')],
        [
          'security_profile',
          string(member(value, 'security_profile'), 'session_opened.security_profile'),
        ],
        [
          'security_state_digest',
          string(member(value, 'security_state_digest'), 'session_opened.security_state_digest'),
        ],
        [
          'gateway_permitted',
          boolean(member(value, 'gateway_permitted'), 'session_opened.gateway_permitted'),
        ],
        [
          'gateway',
          nullable(member(value, 'gateway', null), 'session_opened.gateway', gatewayAttribution),
        ],
      ])
    case 'stimulus_frame':
      return stimulusFrame(value, 'stimulus_frame')
    case 'step_request':
      return object([
        ['ncp_version', string(member(value, 'ncp_version'), 'step_request.ncp_version')],
        ['kind', string(kind, 'step_request.kind')],
        ['session_id', string(member(value, 'session_id'), 'step_request.session_id')],
        ['advance_ms', nullable(member(value, 'advance_ms', null), 'step_request.advance_ms', number)],
        [
          'stimulus',
          nullable(member(value, 'stimulus', null), 'step_request.stimulus', stimulusFrame),
        ],
        ['session', sessionRef(member(value, 'session'), 'step_request.session')],
        ['operation', operationContext(member(value, 'operation'), 'step_request.operation')],
        ['authority', authorityLease(member(value, 'authority'), 'step_request.authority')],
      ])
    case 'run_request':
      return object([
        ['ncp_version', string(member(value, 'ncp_version'), 'run_request.ncp_version')],
        ['kind', string(kind, 'run_request.kind')],
        ['session_id', string(member(value, 'session_id'), 'run_request.session_id')],
        ['duration_ms', number(member(value, 'duration_ms'), 'run_request.duration_ms')],
        [
          'stimulus',
          nullable(member(value, 'stimulus', null), 'run_request.stimulus', stimulusFrame),
        ],
        ['session', sessionRef(member(value, 'session'), 'run_request.session')],
        ['operation', operationContext(member(value, 'operation'), 'run_request.operation')],
        ['authority', authorityLease(member(value, 'authority'), 'run_request.authority')],
      ])
    case 'observation_frame':
      return object([
        ['ncp_version', string(member(value, 'ncp_version'), 'observation_frame.ncp_version')],
        ['kind', string(kind, 'observation_frame.kind')],
        ['session_id', string(member(value, 'session_id'), 'observation_frame.session_id')],
        ['t', number(member(value, 't', 0), 'observation_frame.t')],
        ['sim_time_ms', number(member(value, 'sim_time_ms', 0), 'observation_frame.sim_time_ms')],
        ['records', map(member(value, 'records'), 'observation_frame.records', observation)],
        [
          'calibrated_posterior',
          boolean(member(value, 'calibrated_posterior'), 'observation_frame.calibrated_posterior'),
        ],
        [
          'is_simulation_output',
          boolean(member(value, 'is_simulation_output'), 'observation_frame.is_simulation_output'),
        ],
        ['stream', streamPosition(member(value, 'stream'), 'observation_frame.stream')],
        [
          'source',
          nullable(member(value, 'source', null), 'observation_frame.source', streamPosition),
        ],
        ['source_t', number(member(value, 'source_t', 0), 'observation_frame.source_t')],
        ['session', sessionRef(member(value, 'session'), 'observation_frame.session')],
        [
          'receipt',
          nullable(member(value, 'receipt', null), 'observation_frame.receipt', responderReceipt),
        ],
      ])
    case 'close_session':
      return object([
        ['ncp_version', string(member(value, 'ncp_version'), 'close_session.ncp_version')],
        ['kind', string(kind, 'close_session.kind')],
        ['session_id', string(member(value, 'session_id'), 'close_session.session_id')],
        ['session', sessionRef(member(value, 'session'), 'close_session.session')],
        ['operation', operationContext(member(value, 'operation'), 'close_session.operation')],
        ['authority', authorityLease(member(value, 'authority'), 'close_session.authority')],
      ])
    case 'session_closed':
      return object([
        ['ncp_version', string(member(value, 'ncp_version'), 'session_closed.ncp_version')],
        ['kind', string(kind, 'session_closed.kind')],
        ['session_id', string(member(value, 'session_id'), 'session_closed.session_id')],
        ['ok', boolean(member(value, 'ok'), 'session_closed.ok')],
        ['session', sessionRef(member(value, 'session'), 'session_closed.session')],
        ['receipt', responderReceipt(member(value, 'receipt'), 'session_closed.receipt')],
      ])
    case 'error':
      return object([
        ['ncp_version', string(member(value, 'ncp_version'), 'error.ncp_version')],
        ['kind', string(kind, 'error.kind')],
        ['code', string(member(value, 'code'), 'error.code')],
        ['error', string(member(value, 'error'), 'error.error')],
        ['session_id', nullable(member(value, 'session_id', null), 'error.session_id', string)],
        ['request_kind', nullable(member(value, 'request_kind', null), 'error.request_kind', string)],
        ['session', nullable(member(value, 'session', null), 'error.session', sessionRef)],
        ['receipt', nullable(member(value, 'receipt', null), 'error.receipt', responderReceipt)],
      ])
    case 'capabilities':
      return object([
        ['ncp_version', string(member(value, 'ncp_version'), 'capabilities.ncp_version')],
        ['kind', string(kind, 'capabilities.kind')],
        ['controller_id', string(member(value, 'controller_id'), 'capabilities.controller_id')],
        ['role', string(member(value, 'role'), 'capabilities.role')],
        ['control_rate_hz', number(member(value, 'control_rate_hz'), 'capabilities.control_rate_hz')],
        [
          'sensor_channels',
          array(member(value, 'sensor_channels'), 'capabilities.sensor_channels', channelSpec),
        ],
        [
          'command_channels',
          array(member(value, 'command_channels'), 'capabilities.command_channels', channelSpec),
        ],
        ['codec_id', nullable(member(value, 'codec_id', null), 'capabilities.codec_id', string)],
        ['safety', safetyLimits(member(value, 'safety'), 'capabilities.safety')],
        ['identity', identityClaim(member(value, 'identity'), 'capabilities.identity')],
        [
          'security_profile',
          string(member(value, 'security_profile'), 'capabilities.security_profile'),
        ],
        [
          'security_state_digest',
          string(member(value, 'security_state_digest'), 'capabilities.security_state_digest'),
        ],
        ['stable_capabilities', strings(member(value, 'stable_capabilities'), 'capabilities.stable_capabilities')],
        [
          'gateway_permitted',
          boolean(member(value, 'gateway_permitted'), 'capabilities.gateway_permitted'),
        ],
        [
          'plant_profile_digest',
          nullable(member(value, 'plant_profile_digest', null), 'capabilities.plant_profile_digest', string),
        ],
        ['gateway', nullable(member(value, 'gateway', null), 'capabilities.gateway', gatewayAttribution)],
      ])
    case 'sensor_frame':
      return object([
        ['ncp_version', string(member(value, 'ncp_version'), 'sensor_frame.ncp_version')],
        ['kind', string(kind, 'sensor_frame.kind')],
        ['t', number(member(value, 't', 0), 'sensor_frame.t')],
        ['frame_id', string(member(value, 'frame_id', 'world'), 'sensor_frame.frame_id')],
        ['channels', channelMap(member(value, 'channels', {}), 'sensor_frame.channels')],
        ['stream', streamPosition(member(value, 'stream'), 'sensor_frame.stream')],
        ['session', sessionRef(member(value, 'session'), 'sensor_frame.session')],
        ['session_id', string(member(value, 'session_id'), 'sensor_frame.session_id')],
      ])
    case 'command_frame':
      return object([
        ['ncp_version', string(member(value, 'ncp_version'), 'command_frame.ncp_version')],
        ['kind', string(kind, 'command_frame.kind')],
        ['t', number(member(value, 't', 0), 'command_frame.t')],
        ['frame_id', string(member(value, 'frame_id', 'world'), 'command_frame.frame_id')],
        ['mode', string(member(value, 'mode', 'hold'), 'command_frame.mode')],
        ['ttl_ms', number(member(value, 'ttl_ms'), 'command_frame.ttl_ms')],
        ['channels', channelMap(member(value, 'channels', {}), 'command_frame.channels')],
        [
          'horizon',
          array(member(value, 'horizon', []), 'command_frame.horizon', channelMap),
        ],
        [
          'horizon_dt_ms',
          nullable(member(value, 'horizon_dt_ms', null), 'command_frame.horizon_dt_ms', number),
        ],
        ['stream', streamPosition(member(value, 'stream'), 'command_frame.stream')],
        ['source', nullable(member(value, 'source', null), 'command_frame.source', streamPosition)],
        ['source_t', number(member(value, 'source_t', 0), 'command_frame.source_t')],
        ['session', sessionRef(member(value, 'session'), 'command_frame.session')],
        ['session_id', string(member(value, 'session_id'), 'command_frame.session_id')],
        [
          'authority',
          nullable(member(value, 'authority', null), 'command_frame.authority', authorityLease),
        ],
      ])
    case 'control_status':
      return object([
        ['ncp_version', string(member(value, 'ncp_version'), 'control_status.ncp_version')],
        ['kind', string(kind, 'control_status.kind')],
        ['t', number(member(value, 't'), 'control_status.t')],
        ['mode', string(member(value, 'mode'), 'control_status.mode')],
        ['sim_time_ms', number(member(value, 'sim_time_ms', 0), 'control_status.sim_time_ms')],
        [
          'loop_latency_ms',
          number(member(value, 'loop_latency_ms'), 'control_status.loop_latency_ms'),
        ],
        ['safety_ok', boolean(member(value, 'safety_ok'), 'control_status.safety_ok')],
        ['note', nullable(member(value, 'note', null), 'control_status.note', string)],
        ['stream', streamPosition(member(value, 'stream'), 'control_status.stream')],
        ['session', sessionRef(member(value, 'session'), 'control_status.session')],
        ['session_id', string(member(value, 'session_id'), 'control_status.session_id')],
      ])
    case 'link_status':
      return object([
        ['ncp_version', string(member(value, 'ncp_version'), 'link_status.ncp_version')],
        ['kind', string(kind, 'link_status.kind')],
        ['session_id', string(member(value, 'session_id'), 'link_status.session_id')],
        ['t', number(member(value, 't'), 'link_status.t')],
        ['received', integer(member(value, 'received'), 'link_status.received')],
        ['lost', integer(member(value, 'lost'), 'link_status.lost')],
        ['loss_rate', number(member(value, 'loss_rate'), 'link_status.loss_rate')],
        ['burst', boolean(member(value, 'burst'), 'link_status.burst')],
        ['stream', streamPosition(member(value, 'stream'), 'link_status.stream')],
        [
          'observed_stream',
          nullable(member(value, 'observed_stream', null), 'link_status.observed_stream', streamPosition),
        ],
        [
          'last_arrival_seq',
          nullable(member(value, 'last_arrival_seq', null), 'link_status.last_arrival_seq', integer),
        ],
        ['session', sessionRef(member(value, 'session'), 'link_status.session')],
      ])
    default:
      throw new Error(`unknown NCP message kind ${JSON.stringify(kind)}`)
  }
}

/** Validate a programmatic TypeScript message and emit Rust-reference-identical bytes. */
export function canonicalizeNcpMessage(value: unknown, expectedKind?: string): string {
  assertNcpMessage(value, expectedKind)
  return canonicalMessage(value)
}

/** Apply bounded raw-JSON ingress before producing deterministic message bytes. */
export function canonicalizeNcpJson(input: string, expectedKind?: string): string {
  return canonicalizeNcpMessage(parseBoundedJson(input), expectedKind)
}
