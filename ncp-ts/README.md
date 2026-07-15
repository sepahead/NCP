# `@sepahead/ncp`

This is the TypeScript package for the unreleased, release-blocked NCP
`1.0.0-rc.1` candidate. Generated wire types come from the Rust reference, while
bounded JSON parsing, semantic validation, reply correlation, and plant-side safety
decisions are implemented independently in TypeScript.

The package exports wire `NCP_VERSION = "1.0"` and compact proto hash
`NCP_CONTRACT_HASH = "163acc57d8a62b66"`, plus `NCP_PACKAGE_VERSION`,
`NCP_NORMATIVE_CONTRACT_DIGEST`, and `NCP_BUILD_IDENTITY`. Checked-in RC source and
ordinary builds honestly use `unreleased-worktree`; it is not a source commit or
release identity.

`NeuroSimClient` requires precommitted negotiation state. The stable production
profile additionally requires a transport adapter to bind that state to the
authenticated peer; the loopback development profile below is intentionally
unauthenticated:

```ts
import { NeuroSimClient, WebSocketNeuroSim } from '@sepahead/ncp'
import type { ClientNegotiation, MutationInput } from '@sepahead/ncp'

// Supply the lowercase SHA-256 emitted for the exact validated deployment profile;
// never substitute a zero or invented placeholder digest.
declare const validatedSecurityStateDigest: string

// WebSocket is experimental, so the deployment supplies its explicit endpoint.
const ws = new WebSocketNeuroSim('wss://control.example/ncp')
const negotiation: ClientNegotiation = {
  identity: {
    principal_id: 'commander-1',
    entity_id: 'controller-1',
    role: 'commander',
    plane: 'control',
  },
  security_profile: 'dev-loopback-insecure',
  security_state_digest: validatedSecurityStateDigest,
  gateway_permitted: false,
}
const client = new NeuroSimClient(ws.send, negotiation)
```

The insecure profile shown above is valid only on loopback/UDS and is not a
production example. `open()` validates the returned session generation, responder
identity claim and security-state fields, compact-hash advisory, and scientific
boundary.
`step()`, `run()`, and `close()` require a `MutationInput` carrying a canonical
operation context and matching authority lease; their replies require structurally
valid receipts correlated to the operation ID and request digest. Payload identity
in a session reply or receipt does not authenticate itself: the transport adapter
must bind the reply to the verified responder. The client computes and seals
`request-digest-v1` over the
complete request. A caller-supplied digest is accepted only when it already matches;
placeholders and payload/digest divergence fail before transport. A successful open
must also preserve the precommitted security profile, security-state digest,
gateway permission, and gateway attribution.

Session generations are process-local client state. A newly constructed client
cannot mutate a session until its own successful `open()`. Starting a reopen retires
the previous local generation before the transport wait, so an unavailable reopen
outcome cannot fall back to stale state; a correlated terminal `close()` likewise
retires the generation before another mutation can be sent. Concurrent opens are
attempt-fenced, and a mutation reply is rechecked against the current client-local
generation after its transport wait, so a late old result cannot overwrite or
complete against a newer opening. Generations observed by that client instance are
retained in a bounded non-evicting fence and cannot be revived during the same
instance lifetime. Step/run observations bind the
fresh generation to one stream epoch: the first reply must use sequence 1, later
positions must advance the high-water mark, forward gaps are tolerated, and only a
full-reply-fingerprint-identical terminal retry may repeat a retained position. The
generation and observation fences each fail closed at 4096 globally retained
entries, and at most 4096 unresolved openings may exist at once.

The client validates `result_digest` syntax and uses it in replay correlation but
does not independently recompute it. This candidate has no normative nonrecursive
result projection that an independent TypeScript implementation can hash without
inventing wire semantics. That remains an open release blocker; receipt correlation
alone is not result-body certification.

`WebSocketNeuroSim` is an experimental FIFO-correlated binding. It uses the bounded
parser, rejects binary and malformed replies, preflights outbound JSON against the
1 MiB frame ceiling, and caps outstanding requests at the control-plane capacity of
128. Connection, browser write-buffer drain, reply read, and overall request waits
have finite defaults exposed by `WEBSOCKET_TRANSPORT_DEFAULTS`; smaller or otherwise
deployment-specific positive timer-safe values may be supplied as the constructor's
second argument. A timeout after a send closes the FIFO transport so a late reply
cannot satisfy a later request. Its UTF-8 byte gate counts without allocating a
second full reply buffer; the browser WebSocket API itself delivers a complete
message, so the server and deployment proxy must also enforce the normative frame
ceiling before browser allocation. WebSocket is not a stable 1.0 transport; the
stable binding is Zenoh. A deployment endpoint cannot answer this client natively
until its full negotiation, lifecycle, authority, digest, and receipt contract
passes retained integration evidence.

The package also exports `parseBoundedJson`, `assertNcpMessage`,
`canonicalizeNcpJson`/`canonicalizeNcpMessage`,
`NCP_ERROR_CODES`/`NcpErrorCode`, `SafetyGovernor`, `CommandWatchdog`,
`ActionBuffer`, and shared safety constants. `assertNcpMessage` rejects an
`ErrorFrame` whose required `code` is absent or outside the registry. Active commands
require a valid authority lease. `CommandWatchdog` and `ActionBuffer` never accept a
lower sequence after expiry or switch epochs in place. `ActionBuffer.reset()` is a
local primitive for an already-authorized generation cut: it clears the latch and
permanently retires that buffer, so a fresh session generation needs a fresh object;
the method does not authenticate an operator or restore remote authority.
`assertNcpMessage` also requires positive status-stream positions and coherent
`LinkStatus` observation high-water fields. These controls are not physical safety
certification.

The canonicalization helpers validate first, then independently reproduce the
Rust reference's typed round trip: serde defaults are materialized, unknown members
are removed, map keys are UTF-8 ordered, integer values remain in the exact JSON
safe range, and binary64 spelling is deterministic. They do not make TypeScript an
independent live transport peer or add another normative contract layer.

Regenerate and verify with:

```bash
bun install --frozen-lockfile
bun run regen
bun run check:behavior
bun run check:integers
bun run check:ws
bun run check:package
```

`dist/` is committed and must reproduce exactly from `src/` plus generated types.
This candidate has independent decision code but has not completed the required
independent installed live-peer security/fault certification.

Release packaging is a separate, fail-closed path. Ordinary `regen` has no identity
injection input: it consumes the checked-in `unreleased-worktree` sentinel and
ignores `NCP_BUILD_IDENTITY` for TypeScript. Package/version checks fail if source,
runtime, or declarations stop carrying that sentinel. From a checkout whose exact
`HEAD` is the intended source commit, run:

```bash
revision="$(git rev-parse --verify 'HEAD^{commit}')"
node ncp-ts/scripts/build-release.mjs \
  --source-revision "$revision" \
  --output /new/path/ncp-npm-artifacts
```

The revision must be exactly 40 lowercase hexadecimal characters, must equal
`HEAD`, and the running builder must match that commit. The builder packages a
`git archive` rather than mutable worktree bytes, injects the same revision through
the Rust compile-time identity probe and staged TypeScript build, installs and
checks both the repository-root and nested `ncp-ts` tarballs, then atomically emits
them with `npm-release-build-receipt.json` and their SHA-256 digests. The output path
must not already exist. This command does not tag, sign, publish, or certify a
release.
