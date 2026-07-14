/*
 * ncp.h — C / C++ ABI for the Neuro-Cybernetic Protocol (NCP) Rust core.
 *
 * So C and C++ projects use the canonical Rust implementation (version guard,
 * key scheme, rate codec, action-plane safety governor, message validation)
 * rather than reimplementing the wire — the same guarantee the Python (PyO3) and
 * TypeScript (ts-rs) bindings give. Link against `ncp_cpp` (staticlib or cdylib
 * built by `cargo build -p ncp-cpp`).
 *
 * Memory: every `char*` return is a heap-allocated UTF-8 C string the caller
 * MUST release with `ncp_string_free`. A NULL return signals malformed input or
 * an internal error. String arguments are NUL-terminated UTF-8; JSON args/returns
 * match the NCP wire exactly (see ncp.proto / schemas). Every JSON argument is
 * structurally preflighted against the normative byte/depth/node/string/number
 * budgets and duplicate-key rule before typed decoding; a violation returns the
 * function's documented NULL/-1 fail-safe sentinel.
 */
#ifndef NCP_H
#define NCP_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Release any string returned by an ncp_* function. NULL is ignored. */
void ncp_string_free(char *s);

/* Protocol wire version ("1.0" for this candidate). Caller frees. */
char *ncp_version(void);

/* Coordinated installable-package SemVer ("1.0.0-rc.1" for this candidate). */
char *ncp_package_version(void);

/* SHA-256 of the complete normative contract set; distinct from the compact
 * protobuf-only ncp_contract_hash compatibility hint. Caller frees. */
char *ncp_normative_contract_digest(void);

/* Immutable release-builder identity, or "unreleased-worktree" for this
 * non-certifying RC build. Caller frees. */
char *ncp_build_identity(void);

/* Default realm — the neutral ncp_core::DEFAULT_REALM (a deployment sets its own). Caller frees. */
char *ncp_default_realm(void);

/* 1 if major-compatible, 0 if not, -1 if unparseable/NULL. */
int32_t ncp_check_version(const char *version, bool strict);

/* This peer's contract hash (ncp_core::CONTRACT_HASH). Caller frees. */
char *ncp_contract_hash(void);

/* Advisory contract-hash status vs ours: 1=match, 0=not advertised (NULL),
 * 2=MISMATCH, -1=invalid. ADVISORY (a mismatch is a signal, not a rejection;
 * ncp_check_version is the hard gate). */
int32_t ncp_contract_status(const char *peer_hash);

/* Normative request-digest-v1 SHA-256 for a step/run/close JSON request.
 * Authority and retry-attempt metadata are excluded by the protocol projection.
 * NULL on malformed/non-mutation input. Caller frees. */
char *ncp_request_digest(const char *request_json);

/* Key-expression builders. Caller frees. */
/* ncp_key_rpc returns the control-plane prefix. Wire 1.0 requests use the exact
 * key returned by ncp_key_rpc_kind (NULL for a non-lifecycle request kind). */
char *ncp_key_rpc(const char *realm);
char *ncp_key_rpc_kind(const char *realm, const char *request_kind);
char *ncp_key_rpc_glob(const char *realm);
char *ncp_key_sensor(const char *realm, const char *session_id);
char *ncp_key_command(const char *realm, const char *session_id);
char *ncp_key_observation(const char *realm, const char *session_id);

/* Rate codec. JSON in / JSON out. A supplied SensorFrame must carry a complete
 * wire-valid kind/version/seq envelope. NULL on malformed input or internal
 * error. Caller frees. */
char *ncp_encode_rates(const char *codec_json, const char *sensor_json);
/* Rate-decode to a CommandFrame. The caller owns the wire-1.0 identity: `epoch`
 * (a canonical lowercase UUIDv4 stream epoch) with a monotonically increasing
 * wire-safe seq (1..2^53-1), plus `session_generation` (a canonical UUIDv4) and
 * `session_id`; all three are required (NULL => NULL). `frame_id` NULL => "world";
 * `mode` is one of "init"/"active"/"hold"/"estop" (NULL => fail-safe "hold"); an
 * unknown mode returns NULL. `authority_json` is required for active mode and may
 * be NULL otherwise. The caller owns a finite timestamp; invalid metadata,
 * a non-canonical epoch/generation, or an invalid generated command returns NULL. */
char *ncp_decode_command(const char *codec_json, const char *rates_json,
                         double t, const char *epoch, int64_t seq,
                         const char *session_generation, const char *session_id,
                         const char *frame_id, const char *mode,
                         const char *authority_json);

/* Action-plane safety governor, ONE-SHOT: a fresh governor per call, so the
 * ESTOP latch cannot persist across calls (stateless/corpus use only — a real
 * plant must hold a persistent NcpGovernor, below). last_sensor_s < 0 =>
 * "no sensor yet" (HOLD). NULL on malformed input. Caller frees. */
char *ncp_govern(const char *limits_json, const char *command_json, double now_s,
                 const char *sensor_json, double last_sensor_s);

/* PERSISTENT (latching) safety governor: a geofence breach / inbound ESTOP /
 * link collapse keeps every later ncp_governor_govern at ESTOP until a local
 * ncp_governor_reset after external operator/interlock authorization. The
 * method does not authenticate or restore session authority. NOT thread-safe:
 * synchronize access to one handle. Free with ncp_governor_free. */
typedef struct NcpGovernor NcpGovernor;
NcpGovernor *ncp_governor_new(const char *limits_json);
/* Same argument semantics as ncp_govern; NULL on NULL handle/malformed input.
 * Caller frees the returned string. */
char *ncp_governor_govern(NcpGovernor *gov, const char *command_json,
                          double now_s, const char *sensor_json,
                          double last_sensor_s);
void ncp_governor_reset(NcpGovernor *gov);
/* 1 latched / 0 not / -1 NULL handle. */
int32_t ncp_governor_is_estopped(const NcpGovernor *gov);
void ncp_governor_note_link(NcpGovernor *gov, bool burst);
/* 1 safe / 0 not / -1 NULL handle. */
int32_t ncp_governor_safety_ok(const NcpGovernor *gov);
void ncp_governor_free(NcpGovernor *gov);

/* Body-local command deadline/replay/horizon buffer. A live actuator needs this
 * in addition to NcpGovernor: Governor checks sensor/geofence/speed policy;
 * ActionBuffer enforces command ttl_ms, seq/replay rejection, bounded predictive
 * horizon replay, and its own ESTOP latch. This is not a remote ingress gate;
 * authenticate actor/plane and bind the exact live route/session generation first.
 * NOT thread-safe: synchronize access to one handle. */
typedef struct NcpActionBuffer NcpActionBuffer;
NcpActionBuffer *ncp_action_buffer_new(void);
/* 0 = parsed/processed (the core may safely ignore an invalid/replayed frame),
 * -1 = NULL handle or malformed/non-UTF-8 JSON. */
int32_t ncp_action_buffer_on_command(NcpActionBuffer *buffer, double now_s,
                                     const char *command_json);
/* Returns an allocated channel-map JSON object or the JSON literal `null` when
 * HOLD is required. A NULL C pointer is an error and must also be treated as
 * HOLD. Caller frees a non-NULL return. */
char *ncp_action_buffer_active(const NcpActionBuffer *buffer, double now_s);
/* 1 HOLD / 0 active / -1 NULL handle. */
int32_t ncp_action_buffer_should_hold(const NcpActionBuffer *buffer,
                                      double now_s);
/* Clears the local latch and permanently retires this generation-bound buffer;
 * does not authenticate an operator or restore remote authority. */
void ncp_action_buffer_reset(NcpActionBuffer *buffer);
/* 1 latched / 0 not / -1 NULL handle. */
int32_t ncp_action_buffer_is_estopped(const NcpActionBuffer *buffer);
/* 1 retired / 0 live / -1 NULL handle. */
int32_t ncp_action_buffer_is_retired(const NcpActionBuffer *buffer);
void ncp_action_buffer_free(NcpActionBuffer *buffer);

/* Validate an NCP message of `kind` (parse->reserialize). NULL on malformed/
 * unknown kind. Caller frees. */
char *ncp_validate(const char *kind, const char *json);

#ifdef __cplusplus
} /* extern "C" */
#endif

#endif /* NCP_H */
