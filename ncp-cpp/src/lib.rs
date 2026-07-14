#![doc = include_str!("../README.md")]
#![cfg_attr(docsrs, feature(doc_cfg))]
//!
//! # API notes
//!
//! String returns are heap-allocated UTF-8 C strings the caller must release with
//! [`ncp_string_free`]; `NULL` signals malformed input or an internal error.
//! Inputs are NUL-terminated UTF-8; JSON arguments/returns match the NCP wire
//! exactly.
//!
//! ## Unwind safety
//! Every `extern "C"` body is wrapped in [`std::panic::catch_unwind`], so an
//! unwinding Rust panic is caught before it can cross the C ABI. With
//! `panic=unwind` the function returns its NULL/-1 sentinel; `panic=abort` still
//! terminates the process and cannot be caught.

use ncp_core::{
    valid_id_segment, ActionBuffer, AuthorityLease, CodecSpec, CommandFrame, Keys, Map, Mode,
    SafetyGovernor, SafetyLimits, SensorFrame, WireFrame,
};
use std::ffi::{CStr, CString};
use std::os::raw::c_char;
use std::panic::{catch_unwind, AssertUnwindSafe};

/// Run an FFI body, returning `sentinel` if it unwinds (so no unwind crosses the
/// C ABI). Callers must discard a mutable opaque handle after an internal panic:
/// catching an unwind cannot promise that partially-mutated external state is
/// reusable.
fn ffi_guard<T>(sentinel: T, body: impl FnOnce() -> T) -> T {
    catch_unwind(AssertUnwindSafe(body)).unwrap_or(sentinel)
}

/// Borrow an optional C string as UTF-8, preserving the difference between a
/// documented NULL/default and malformed non-NULL bytes.
///
/// # Safety
/// `p` must be NULL or a valid NUL-terminated C string for the call's duration.
unsafe fn cstr_in<'a>(p: *const c_char) -> Result<Option<&'a str>, ()> {
    if p.is_null() {
        Ok(None)
    } else {
        // SAFETY: caller guarantees `p` is a valid NUL-terminated C string.
        CStr::from_ptr(p).to_str().map(Some).map_err(|_| ())
    }
}

/// Borrow a required UTF-8 C string.
///
/// # Safety
/// `p` must be NULL or a valid NUL-terminated C string for the call's duration.
unsafe fn required_cstr<'a>(p: *const c_char) -> Result<&'a str, ()> {
    cstr_in(p)?.ok_or(())
}

/// Allocate a C string the caller frees with [`ncp_string_free`]; NULL on interior-NUL.
fn cstr_out(s: String) -> *mut c_char {
    match CString::new(s) {
        Ok(c) => c.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

/// Apply the normative JSON resource and ambiguity limits before a typed decode.
fn preflight_json(json: &str) -> Result<(), ncp_core::bounded_json::BoundedJsonError> {
    ncp_core::bounded_json::preflight(json.as_bytes())
}

/// Free a string returned by any `ncp_*` function.
///
/// # Safety
/// `s` must be NULL or a pointer previously returned by this library and not yet freed.
#[no_mangle]
pub unsafe extern "C" fn ncp_string_free(s: *mut c_char) {
    ffi_guard((), || {
        if !s.is_null() {
            // SAFETY: `s` was produced by `CString::into_raw` in this library.
            drop(CString::from_raw(s));
        }
    })
}

/// The NCP protocol wire version (`"1.0"` for this candidate). Caller frees.
#[no_mangle]
pub extern "C" fn ncp_version() -> *mut c_char {
    ffi_guard(std::ptr::null_mut(), || {
        cstr_out(ncp_core::NCP_VERSION.to_string())
    })
}

/// This installable C ABI package's SemVer. Caller frees.
#[no_mangle]
pub extern "C" fn ncp_package_version() -> *mut c_char {
    ffi_guard(std::ptr::null_mut(), || {
        cstr_out(env!("CARGO_PKG_VERSION").to_string())
    })
}

/// Complete normative contract SHA-256 (not the compact proto hash). Caller frees.
#[no_mangle]
pub extern "C" fn ncp_normative_contract_digest() -> *mut c_char {
    ffi_guard(std::ptr::null_mut(), || {
        cstr_out(ncp_core::NORMATIVE_CONTRACT_DIGEST.to_string())
    })
}

/// Immutable release-builder identity, or the honest RC sentinel. Caller frees.
#[no_mangle]
pub extern "C" fn ncp_build_identity() -> *mut c_char {
    ffi_guard(std::ptr::null_mut(), || {
        cstr_out(ncp_core::BUILD_IDENTITY.to_string())
    })
}

/// The default realm — the neutral [`ncp_core::DEFAULT_REALM`] (a deployment sets its own). Caller frees.
#[no_mangle]
pub extern "C" fn ncp_default_realm() -> *mut c_char {
    ffi_guard(std::ptr::null_mut(), || {
        cstr_out(ncp_core::DEFAULT_REALM.to_string())
    })
}

/// 1 if `version` is major-compatible, 0 if not, -1 if unparseable/null.
///
/// # Safety
/// `version` must be NULL or a valid C string.
#[no_mangle]
pub unsafe extern "C" fn ncp_check_version(version: *const c_char, strict: bool) -> i32 {
    ffi_guard(-1, || match required_cstr(version) {
        Err(()) => -1,
        Ok(v) => match ncp_core::check_version(v, strict) {
            Ok(true) => 1,
            Ok(false) => 0,
            Err(_) => -1,
        },
    })
}

/// This peer's contract hash (`ncp_core::CONTRACT_HASH`). Caller frees.
#[no_mangle]
pub extern "C" fn ncp_contract_hash() -> *mut c_char {
    ffi_guard(std::ptr::null_mut(), || {
        cstr_out(ncp_core::CONTRACT_HASH.to_string())
    })
}

/// Advisory contract-hash status vs ours (mirrors `ncp_core::ContractStatus`):
/// `1` = match, `0` = not advertised (NULL), `2` = MISMATCH, `-1` = invalid input.
/// This is ADVISORY — a mismatch is a signal, not a rejection; `ncp_check_version`
/// is the hard compatibility gate.
///
/// # Safety
/// `peer_hash` must be NULL or a valid C string.
#[no_mangle]
pub unsafe extern "C" fn ncp_contract_status(peer_hash: *const c_char) -> i32 {
    ffi_guard(-1, || {
        let peer_hash = match cstr_in(peer_hash) {
            Ok(peer_hash) => peer_hash,
            Err(()) => return -1,
        };
        match ncp_core::contract_status(peer_hash) {
            ncp_core::ContractStatus::Match => 1,
            ncp_core::ContractStatus::NotAdvertised => 0,
            ncp_core::ContractStatus::Mismatch { .. } => 2,
        }
    })
}

/// Compute the normative request-digest-v1 SHA-256 for a step/run/close JSON
/// request. Caller frees the returned lowercase hexadecimal string.
///
/// # Safety
/// `request_json` must be NULL or a valid NUL-terminated UTF-8 C string.
#[no_mangle]
pub unsafe extern "C" fn ncp_request_digest(request_json: *const c_char) -> *mut c_char {
    ffi_guard(std::ptr::null_mut(), || {
        let Ok(request_json) = required_cstr(request_json) else {
            return std::ptr::null_mut();
        };
        let Ok(request) = ncp_core::bounded_json::parse_value(request_json.as_bytes()) else {
            return std::ptr::null_mut();
        };
        match ncp_core::request_digest(&request) {
            Ok(digest) => cstr_out(digest),
            Err(_) => std::ptr::null_mut(),
        }
    })
}

unsafe fn key_with(realm: *const c_char, f: impl FnOnce(&Keys) -> String) -> *mut c_char {
    let realm = match cstr_in(realm) {
        Ok(Some(realm)) => realm,
        Ok(None) => ncp_core::DEFAULT_REALM,
        Err(()) => return std::ptr::null_mut(),
    };
    let Ok(keys) = Keys::try_new(realm.to_string()) else {
        return std::ptr::null_mut();
    };
    cstr_out(f(&keys))
}

/// Control-plane prefix `{realm}/rpc`; wire-1.0 requests do not query this prefix.
/// Use [`ncp_key_rpc_kind`] for a request or [`ncp_key_rpc_glob`] for a server.
/// Caller frees.
/// # Safety
/// `realm` must be NULL or a valid C string.
#[no_mangle]
pub unsafe extern "C" fn ncp_key_rpc(realm: *const c_char) -> *mut c_char {
    ffi_guard(std::ptr::null_mut(), || key_with(realm, |k| k.rpc()))
}

/// Exact wire-1.0 lifecycle RPC key: `{realm}/rpc/{request_kind}`. Caller frees.
/// Returns NULL unless `request_kind` is open_session, step_request, run_request,
/// or close_session.
/// # Safety
/// `realm`/`request_kind` must be NULL or valid C strings.
#[no_mangle]
pub unsafe extern "C" fn ncp_key_rpc_kind(
    realm: *const c_char,
    request_kind: *const c_char,
) -> *mut c_char {
    ffi_guard(std::ptr::null_mut(), || {
        let Ok(kind) = required_cstr(request_kind) else {
            return std::ptr::null_mut();
        };
        let realm = match cstr_in(realm) {
            Ok(Some(realm)) => realm,
            Ok(None) => ncp_core::DEFAULT_REALM,
            Err(()) => return std::ptr::null_mut(),
        };
        let Ok(keys) = Keys::try_new(realm.to_string()) else {
            return std::ptr::null_mut();
        };
        match keys.rpc_for_kind(kind) {
            Ok(key) => cstr_out(key),
            Err(_) => std::ptr::null_mut(),
        }
    })
}

/// Wire-1.0 server queryable: `{realm}/rpc/*`. Caller frees.
/// # Safety
/// `realm` must be NULL or a valid C string.
#[no_mangle]
pub unsafe extern "C" fn ncp_key_rpc_glob(realm: *const c_char) -> *mut c_char {
    ffi_guard(std::ptr::null_mut(), || key_with(realm, |k| k.rpc_glob()))
}

/// `{realm}/session/{id}/sensor`. Caller frees.
/// # Safety
/// `realm`/`session_id` must be NULL or valid C strings.
#[no_mangle]
pub unsafe extern "C" fn ncp_key_sensor(
    realm: *const c_char,
    session_id: *const c_char,
) -> *mut c_char {
    ffi_guard(std::ptr::null_mut(), || {
        let Ok(sid) = required_cstr(session_id) else {
            return std::ptr::null_mut();
        };
        if !valid_id_segment(sid) {
            return std::ptr::null_mut();
        }
        key_with(realm, |k| k.sensor(sid))
    })
}

/// `{realm}/session/{id}/command`. Caller frees.
/// # Safety
/// `realm`/`session_id` must be NULL or valid C strings.
#[no_mangle]
pub unsafe extern "C" fn ncp_key_command(
    realm: *const c_char,
    session_id: *const c_char,
) -> *mut c_char {
    ffi_guard(std::ptr::null_mut(), || {
        let Ok(sid) = required_cstr(session_id) else {
            return std::ptr::null_mut();
        };
        if !valid_id_segment(sid) {
            return std::ptr::null_mut();
        }
        key_with(realm, |k| k.command(sid))
    })
}

/// `{realm}/session/{id}/observation`. Caller frees.
/// # Safety
/// `realm`/`session_id` must be NULL or valid C strings.
#[no_mangle]
pub unsafe extern "C" fn ncp_key_observation(
    realm: *const c_char,
    session_id: *const c_char,
) -> *mut c_char {
    ffi_guard(std::ptr::null_mut(), || {
        let Ok(sid) = required_cstr(session_id) else {
            return std::ptr::null_mut();
        };
        if !valid_id_segment(sid) {
            return std::ptr::null_mut();
        }
        key_with(realm, |k| k.observation(sid))
    })
}

/// Rate-encode a `SensorFrame` JSON to `{population: rate_hz}` JSON. `sensor_json`
/// may be NULL/"null"; a supplied frame must pass the complete wire gate. Returns
/// NULL on malformed input or invalid codec configuration. Caller frees.
/// # Safety
/// Arguments must be NULL or valid C strings.
#[no_mangle]
pub unsafe extern "C" fn ncp_encode_rates(
    codec_json: *const c_char,
    sensor_json: *const c_char,
) -> *mut c_char {
    ffi_guard(std::ptr::null_mut(), || {
        let Ok(codec_s) = required_cstr(codec_json) else {
            return std::ptr::null_mut();
        };
        let Ok(()) = preflight_json(codec_s) else {
            return std::ptr::null_mut();
        };
        let Ok(codec) = serde_json::from_str::<CodecSpec>(codec_s) else {
            return std::ptr::null_mut();
        };
        let sensor_json = match cstr_in(sensor_json) {
            Ok(sensor_json) => sensor_json,
            Err(()) => return std::ptr::null_mut(),
        };
        let sensor = match sensor_json {
            None => None,
            Some(s) => match preflight_json(s)
                .map_err(|_| ())
                .and_then(|()| serde_json::from_str::<Option<SensorFrame>>(s).map_err(|_| ()))
            {
                Ok(sensor) => sensor,
                Err(_) => return std::ptr::null_mut(),
            },
        };
        let Ok(rates) = codec.encode_checked(sensor.as_ref()) else {
            return std::ptr::null_mut();
        };
        match serde_json::to_string(&rates) {
            Ok(s) => cstr_out(s),
            Err(_) => std::ptr::null_mut(),
        }
    })
}

/// Parse an NCP mode string to [`Mode`]; `None` on an unknown mode.
fn parse_mode(s: &str) -> Option<Mode> {
    match s {
        "init" => Some(Mode::Init),
        "active" => Some(Mode::Active),
        "hold" => Some(Mode::Hold),
        "estop" => Some(Mode::Estop),
        _ => None,
    }
}

/// Parse an optional sensor JSON without conflating malformed JSON with an
/// intentionally absent sensor. A well-formed but wire-invalid frame is dropped
/// below; the caller's last accepted timestamp is retained so the reference
/// governor can escalate sustained silence while `sensor=None` still prevents
/// actuation.
fn parse_sensor_json(sensor_json: Option<&str>) -> Result<Option<SensorFrame>, ()> {
    match sensor_json {
        None => Ok(None),
        Some(s) => {
            preflight_json(s).map_err(|_| ())?;
            serde_json::from_str::<Option<SensorFrame>>(s).map_err(|_| ())
        }
    }
}

fn sanitize_govern_inputs(
    command: &mut CommandFrame,
    sensor: &mut Option<SensorFrame>,
    last_sensor_s: Option<f64>,
) -> Option<f64> {
    // Preserve explicit ESTOP authority even if its envelope is stale; every
    // other invalid command becomes a non-actuating HOLD.
    if command.mode != Mode::Estop && command.validate_wire().is_err() {
        command.mode = Mode::Hold;
    }
    let sensor_valid = sensor
        .as_ref()
        .is_some_and(|frame| frame.validate_wire().is_ok());
    if !sensor_valid {
        *sensor = None;
    }
    last_sensor_s
}

/// Rate-decode `{population: rate_hz}` JSON to a `CommandFrame` JSON. The caller
/// owns the wire-1.0 stream identity: `epoch` (a canonical lowercase UUIDv4
/// stream epoch) and a monotonically increasing wire-safe `seq` (1..2^53-1),
/// plus the session identity `session_generation` (a canonical UUIDv4) and the
/// `session_id`. `frame_id` may be NULL (=> "world"); `mode` is one of
/// init/active/hold/estop and may be NULL (=> "hold") — an unknown mode returns
/// NULL. `epoch`, `session_generation` and `session_id` are required (NULL =>
/// NULL). Returns NULL on malformed input, invalid codec configuration, or an
/// `authority_json` is required for Active mode and may be NULL otherwise. Returns
/// NULL on malformed input, invalid codec configuration, or an invalid generated
/// command (e.g. a non-canonical epoch, seq 0, or missing Active authority). Caller frees.
/// # Safety
/// Arguments must be NULL or valid C strings.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn ncp_decode_command(
    codec_json: *const c_char,
    rates_json: *const c_char,
    t: f64,
    epoch: *const c_char,
    seq: i64,
    session_generation: *const c_char,
    session_id: *const c_char,
    frame_id: *const c_char,
    mode: *const c_char,
    authority_json: *const c_char,
) -> *mut c_char {
    ffi_guard(std::ptr::null_mut(), || {
        let (Ok(codec_s), Ok(rates_s)) = (required_cstr(codec_json), required_cstr(rates_json))
        else {
            return std::ptr::null_mut();
        };
        if preflight_json(codec_s).is_err() || preflight_json(rates_s).is_err() {
            return std::ptr::null_mut();
        }
        // Stream/session identity is mandatory: a decoded command carries its own
        // position, so an absent epoch/generation/session_id cannot be coerced to
        // a wire-valid frame — fail closed rather than mint a placeholder identity.
        let (Ok(epoch), Ok(session_generation), Ok(session_id)) = (
            required_cstr(epoch),
            required_cstr(session_generation),
            required_cstr(session_id),
        ) else {
            return std::ptr::null_mut();
        };
        let (Ok(codec), Ok(rates)) = (
            serde_json::from_str::<CodecSpec>(codec_s),
            serde_json::from_str::<Map<f64>>(rates_s),
        ) else {
            return std::ptr::null_mut();
        };
        let frame_id = match cstr_in(frame_id) {
            Ok(Some(frame_id)) => frame_id,
            Ok(None) => "world",
            Err(()) => return std::ptr::null_mut(),
        };
        let mode = match cstr_in(mode) {
            Ok(Some(mode)) => mode,
            Ok(None) => "hold",
            Err(()) => return std::ptr::null_mut(),
        };
        let Some(mode) = parse_mode(mode) else {
            return std::ptr::null_mut();
        };
        let authority = match cstr_in(authority_json) {
            Ok(Some(value)) => match preflight_json(value).map_err(|_| ()).and_then(|()| {
                serde_json::from_str::<Option<AuthorityLease>>(value).map_err(|_| ())
            }) {
                Ok(authority) => authority,
                Err(()) => return std::ptr::null_mut(),
            },
            Ok(None) => None,
            Err(()) => return std::ptr::null_mut(),
        };
        let stream = ncp_core::StreamPosition {
            epoch: epoch.to_string(),
            seq,
        };
        let session = ncp_core::SessionRef {
            generation: session_generation.to_string(),
        };
        let Ok(cmd) = codec.decode_checked_with_authority(
            &rates, t, stream, frame_id, mode, session, session_id, authority,
        ) else {
            return std::ptr::null_mut();
        };
        match serde_json::to_string(&cmd) {
            Ok(s) => cstr_out(s),
            Err(_) => std::ptr::null_mut(),
        }
    })
}

/// Apply the action-plane safety governor to a `CommandFrame` JSON; returns the
/// governed JSON, or NULL on malformed input. `sensor_json` may be NULL.
/// `last_sensor_s < 0` means "no sensor yet" (forces HOLD). Caller frees.
/// # Safety
/// Arguments must be NULL or valid C strings.
#[no_mangle]
pub unsafe extern "C" fn ncp_govern(
    limits_json: *const c_char,
    command_json: *const c_char,
    now_s: f64,
    sensor_json: *const c_char,
    last_sensor_s: f64,
) -> *mut c_char {
    ffi_guard(std::ptr::null_mut(), || {
        let (Ok(lim_s), Ok(cmd_s)) = (required_cstr(limits_json), required_cstr(command_json))
        else {
            return std::ptr::null_mut();
        };
        if preflight_json(lim_s).is_err() || preflight_json(cmd_s).is_err() {
            return std::ptr::null_mut();
        }
        let (Ok(limits), Ok(mut command)) = (
            serde_json::from_str::<SafetyLimits>(lim_s),
            serde_json::from_str::<CommandFrame>(cmd_s),
        ) else {
            return std::ptr::null_mut();
        };
        let Ok(sensor_json) = cstr_in(sensor_json) else {
            return std::ptr::null_mut();
        };
        let Ok(mut sensor) = parse_sensor_json(sensor_json) else {
            return std::ptr::null_mut();
        };
        let last = if last_sensor_s < 0.0 {
            None
        } else {
            Some(last_sensor_s)
        };
        let last = sanitize_govern_inputs(&mut command, &mut sensor, last);
        // ONE-SHOT: a fresh governor per call, so the ESTOP latch cannot persist
        // across calls. Stateless/corpus use only — a real plant MUST hold a
        // persistent handle (`ncp_governor_new` + `ncp_governor_govern`) so a
        // latched ESTOP survives until a supervisor `ncp_governor_reset`.
        let mut gov = SafetyGovernor::new(limits);
        let out = gov.govern(&command, sensor.as_ref(), now_s, last);
        match serde_json::to_string(&out) {
            Ok(s) => cstr_out(s),
            Err(_) => std::ptr::null_mut(),
        }
    })
}

/// Opaque persistent action-plane safety governor — the **latching** form: a
/// geofence breach / inbound ESTOP / link collapse keeps every later
/// [`ncp_governor_govern`] at ESTOP until a supervisor [`ncp_governor_reset`].
/// (The one-shot [`ncp_govern`] cannot latch by construction.) NOT thread-safe:
/// the caller synchronizes access to one handle.
pub struct NcpGovernor(SafetyGovernor);

/// Create a persistent governor from a `SafetyLimits` JSON. NULL on malformed
/// input. Free with [`ncp_governor_free`].
/// # Safety
/// `limits_json` must be NULL or a valid C string.
#[no_mangle]
pub unsafe extern "C" fn ncp_governor_new(limits_json: *const c_char) -> *mut NcpGovernor {
    ffi_guard(std::ptr::null_mut(), || {
        let Ok(lim_s) = required_cstr(limits_json) else {
            return std::ptr::null_mut();
        };
        let Ok(()) = preflight_json(lim_s) else {
            return std::ptr::null_mut();
        };
        let Ok(limits) = serde_json::from_str::<SafetyLimits>(lim_s) else {
            return std::ptr::null_mut();
        };
        Box::into_raw(Box::new(NcpGovernor(SafetyGovernor::new(limits))))
    })
}

/// Govern one `CommandFrame` JSON through a persistent handle (the ESTOP latch
/// survives across calls). Same argument semantics as [`ncp_govern`]; NULL on a
/// NULL handle or malformed input. Caller frees the returned string.
/// # Safety
/// `gov` must be NULL or a live handle from [`ncp_governor_new`]; string
/// arguments must be NULL or valid C strings.
#[no_mangle]
pub unsafe extern "C" fn ncp_governor_govern(
    gov: *mut NcpGovernor,
    command_json: *const c_char,
    now_s: f64,
    sensor_json: *const c_char,
    last_sensor_s: f64,
) -> *mut c_char {
    ffi_guard(std::ptr::null_mut(), || {
        if gov.is_null() {
            return std::ptr::null_mut();
        }
        let Ok(cmd_s) = required_cstr(command_json) else {
            return std::ptr::null_mut();
        };
        let Ok(()) = preflight_json(cmd_s) else {
            return std::ptr::null_mut();
        };
        let Ok(mut command) = serde_json::from_str::<CommandFrame>(cmd_s) else {
            return std::ptr::null_mut();
        };
        let Ok(sensor_json) = cstr_in(sensor_json) else {
            return std::ptr::null_mut();
        };
        let Ok(mut sensor) = parse_sensor_json(sensor_json) else {
            return std::ptr::null_mut();
        };
        let last = if last_sensor_s < 0.0 {
            None
        } else {
            Some(last_sensor_s)
        };
        let last = sanitize_govern_inputs(&mut command, &mut sensor, last);
        // SAFETY: caller guarantees `gov` is a live, exclusively-held handle.
        let out = (*gov).0.govern(&command, sensor.as_ref(), now_s, last);
        match serde_json::to_string(&out) {
            Ok(s) => cstr_out(s),
            Err(_) => std::ptr::null_mut(),
        }
    })
}

/// Clear the governor's local ESTOP after external supervisor/interlock
/// authorization. This does not authenticate or restore session authority.
/// NULL is a no-op.
/// # Safety
/// `gov` must be NULL or a live handle from [`ncp_governor_new`].
#[no_mangle]
pub unsafe extern "C" fn ncp_governor_reset(gov: *mut NcpGovernor) {
    ffi_guard((), || {
        if !gov.is_null() {
            // SAFETY: caller guarantees `gov` is a live, exclusively-held handle.
            (*gov).0.reset();
        }
    })
}

/// 1 while ESTOP is latched, 0 when not, -1 on NULL.
/// # Safety
/// `gov` must be NULL or a live handle from [`ncp_governor_new`].
#[no_mangle]
pub unsafe extern "C" fn ncp_governor_is_estopped(gov: *const NcpGovernor) -> i32 {
    ffi_guard(-1, || {
        if gov.is_null() {
            return -1;
        }
        // SAFETY: caller guarantees `gov` is a live handle.
        i32::from((*gov).0.is_estopped())
    })
}

/// Latch ESTOP when a link monitor reports a sustained loss burst. NULL no-op.
/// # Safety
/// `gov` must be NULL or a live handle from [`ncp_governor_new`].
#[no_mangle]
pub unsafe extern "C" fn ncp_governor_note_link(gov: *mut NcpGovernor, burst: bool) {
    ffi_guard((), || {
        if !gov.is_null() {
            // SAFETY: caller guarantees `gov` is a live, exclusively-held handle.
            (*gov).0.note_link(burst);
        }
    })
}

/// 1 when safe (no latched ESTOP, no config fail-closed), 0 when not, -1 on NULL.
/// # Safety
/// `gov` must be NULL or a live handle from [`ncp_governor_new`].
#[no_mangle]
pub unsafe extern "C" fn ncp_governor_safety_ok(gov: *const NcpGovernor) -> i32 {
    ffi_guard(-1, || {
        if gov.is_null() {
            return -1;
        }
        // SAFETY: caller guarantees `gov` is a live handle.
        i32::from((*gov).0.safety_ok())
    })
}

/// Release a governor handle. NULL is ignored. The handle must not be used after.
/// # Safety
/// `gov` must be NULL or a handle from [`ncp_governor_new`] not yet freed.
#[no_mangle]
pub unsafe extern "C" fn ncp_governor_free(gov: *mut NcpGovernor) {
    ffi_guard((), || {
        if !gov.is_null() {
            // SAFETY: `gov` came from Box::into_raw in ncp_governor_new.
            drop(Box::from_raw(gov));
        }
    })
}

/// Opaque plant-side action buffer. This is the command-arrival deadline,
/// replay/ordering, predictive-horizon, and ESTOP-latch layer that complements
/// [`NcpGovernor`]. A live actuator needs both layers.
pub struct NcpActionBuffer(ActionBuffer);

/// Create an empty action buffer. Free with [`ncp_action_buffer_free`].
#[no_mangle]
pub extern "C" fn ncp_action_buffer_new() -> *mut NcpActionBuffer {
    ffi_guard(std::ptr::null_mut(), || {
        Box::into_raw(Box::new(NcpActionBuffer(ActionBuffer::new())))
    })
}

/// Ingest one command at the plant's local `now_s`.
///
/// Body-local API, not a remote ingress gate: the caller first binds authenticated
/// actor/plane and exact live route/session generation. Returns `0` when the JSON
/// was parsed and handed to the fail-closed core. The core may intentionally ignore
/// an invalid/replayed non-ESTOP frame; a locally admitted ESTOP latches before local
/// replay gates. Returns `-1` for a NULL handle, NULL/malformed/non-UTF-8 JSON, or an
/// internal panic.
///
/// # Safety
/// `buffer` must be a live, exclusively-held handle from
/// [`ncp_action_buffer_new`]; `command_json` must be NULL or a valid C string.
#[no_mangle]
pub unsafe extern "C" fn ncp_action_buffer_on_command(
    buffer: *mut NcpActionBuffer,
    now_s: f64,
    command_json: *const c_char,
) -> i32 {
    ffi_guard(-1, || {
        if buffer.is_null() {
            return -1;
        }
        let Ok(command_json) = required_cstr(command_json) else {
            return -1;
        };
        let Ok(()) = preflight_json(command_json) else {
            return -1;
        };
        let Ok(command) = serde_json::from_str::<CommandFrame>(command_json) else {
            return -1;
        };
        // SAFETY: caller guarantees `buffer` is live and exclusively held.
        (*buffer).0.on_command(now_s, command);
        0
    })
}

/// Return the active channel map as JSON, or the JSON literal `null` when the
/// plant must HOLD. A NULL C pointer signals an invalid handle/internal error and
/// must also be treated as HOLD. Caller frees a non-NULL return.
///
/// # Safety
/// `buffer` must be NULL or a live handle from [`ncp_action_buffer_new`].
#[no_mangle]
pub unsafe extern "C" fn ncp_action_buffer_active(
    buffer: *const NcpActionBuffer,
    now_s: f64,
) -> *mut c_char {
    ffi_guard(std::ptr::null_mut(), || {
        if buffer.is_null() {
            return std::ptr::null_mut();
        }
        // SAFETY: caller guarantees `buffer` is a live handle.
        match serde_json::to_string(&(*buffer).0.active(now_s)) {
            Ok(json) => cstr_out(json),
            Err(_) => std::ptr::null_mut(),
        }
    })
}

/// `1` when the plant must HOLD, `0` when an active setpoint exists, `-1` for a
/// NULL handle/internal panic.
///
/// # Safety
/// `buffer` must be NULL or a live handle from [`ncp_action_buffer_new`].
#[no_mangle]
pub unsafe extern "C" fn ncp_action_buffer_should_hold(
    buffer: *const NcpActionBuffer,
    now_s: f64,
) -> i32 {
    ffi_guard(-1, || {
        if buffer.is_null() {
            return -1;
        }
        // SAFETY: caller guarantees `buffer` is a live handle.
        i32::from((*buffer).0.should_hold(now_s))
    })
}

/// Clear the local ESTOP and permanently retire this generation-bound buffer. This
/// does not authenticate a supervisor or restore remote authority. NULL is a no-op.
///
/// # Safety
/// `buffer` must be NULL or a live, exclusively-held handle from
/// [`ncp_action_buffer_new`].
#[no_mangle]
pub unsafe extern "C" fn ncp_action_buffer_reset(buffer: *mut NcpActionBuffer) {
    ffi_guard((), || {
        if !buffer.is_null() {
            // SAFETY: caller guarantees `buffer` is live and exclusively held.
            (*buffer).0.reset();
        }
    })
}

/// `1` while ESTOP is latched, `0` otherwise, `-1` for a NULL handle/internal
/// panic.
///
/// # Safety
/// `buffer` must be NULL or a live handle from [`ncp_action_buffer_new`].
#[no_mangle]
pub unsafe extern "C" fn ncp_action_buffer_is_estopped(buffer: *const NcpActionBuffer) -> i32 {
    ffi_guard(-1, || {
        if buffer.is_null() {
            return -1;
        }
        // SAFETY: caller guarantees `buffer` is a live handle.
        i32::from((*buffer).0.is_estopped())
    })
}

/// `1` after reset permanently retired this generation-bound buffer, `0` while it
/// remains live, `-1` for a NULL handle/internal panic.
///
/// # Safety
/// `buffer` must be NULL or a live handle from [`ncp_action_buffer_new`].
#[no_mangle]
pub unsafe extern "C" fn ncp_action_buffer_is_retired(buffer: *const NcpActionBuffer) -> i32 {
    ffi_guard(-1, || {
        if buffer.is_null() {
            return -1;
        }
        // SAFETY: caller guarantees `buffer` is a live handle.
        i32::from((*buffer).0.is_retired())
    })
}

/// Release an action-buffer handle. NULL is ignored.
///
/// # Safety
/// `buffer` must be NULL or a handle from [`ncp_action_buffer_new`] not yet freed.
#[no_mangle]
pub unsafe extern "C" fn ncp_action_buffer_free(buffer: *mut NcpActionBuffer) {
    ffi_guard((), || {
        if !buffer.is_null() {
            // SAFETY: `buffer` came from Box::into_raw in ncp_action_buffer_new.
            drop(Box::from_raw(buffer));
        }
    })
}

/// Validate an NCP message JSON of a given `kind` (parse → re-serialize through the
/// Rust type). Returns canonical JSON, or NULL on malformed/unknown. Caller frees.
/// # Safety
/// Arguments must be NULL or valid C strings.
#[no_mangle]
pub unsafe extern "C" fn ncp_validate(kind: *const c_char, json: *const c_char) -> *mut c_char {
    use ncp_core::*;
    ffi_guard(std::ptr::null_mut(), || {
        let (Ok(kind), Ok(json)) = (required_cstr(kind), required_cstr(json)) else {
            return std::ptr::null_mut();
        };
        // The C ABI is an ingress boundary, not a trusted typed-conversion helper.
        // Apply the same byte/depth/node/string/number/duplicate-key preflight as
        // every other NCP 1.0 ingress before allocating a generic JSON value.
        let Ok(mut value) = ncp_core::bounded_json::parse_value(json.as_bytes()) else {
            return std::ptr::null_mut();
        };
        // Canonical kind-aware checks follow (required fields + scientific-boundary
        // value pins) — the typed round-trip alone would silently default a
        // missing required field and round-trip a tampered discriminator clean.
        match value.as_object_mut() {
            Some(m) => match m.get("kind") {
                Some(serde_json::Value::String(k)) if k == kind => {}
                _ => return std::ptr::null_mut(),
            },
            None => return std::ptr::null_mut(),
        }
        if ncp_core::validate(&value).is_err() {
            return std::ptr::null_mut();
        }
        // Round-trip the exact document that was validated. `kind` is mandatory
        // since wire 0.6 and must never be fabricated from the C API argument.
        macro_rules! rt {
            ($t:ty) => {
                match serde_json::from_value::<$t>(value.clone())
                    .map_err(|_| ())
                    .and_then(|v| serde_json::to_string(&v).map_err(|_| ()))
                {
                    Ok(s) => cstr_out(s),
                    Err(()) => std::ptr::null_mut(),
                }
            };
        }
        match kind {
            "open_session" => rt!(OpenSession),
            "session_opened" => rt!(SessionOpened),
            "step_request" => rt!(StepRequest),
            "run_request" => rt!(RunRequest),
            "stimulus_frame" => rt!(StimulusFrame),
            "observation_frame" => rt!(ObservationFrame),
            "close_session" => rt!(CloseSession),
            "session_closed" => rt!(SessionClosed),
            "sensor_frame" => rt!(SensorFrame),
            "command_frame" => rt!(CommandFrame),
            "control_status" => rt!(ControlStatus),
            "link_status" => rt!(LinkStatus),
            "capabilities" => rt!(Capabilities),
            "error" => rt!(ErrorFrame),
            _ => std::ptr::null_mut(),
        }
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Take ownership of a returned C string and free it via the FFI path.
    unsafe fn take(p: *mut c_char) -> Option<String> {
        if p.is_null() {
            None
        } else {
            let s = CStr::from_ptr(p).to_str().unwrap().to_string();
            ncp_string_free(p);
            Some(s)
        }
    }

    fn cstr(s: &str) -> CString {
        CString::new(s).unwrap()
    }

    // Canonical wire-1.0 stream/session identity for decode + action-buffer frames.
    const TEST_EPOCH: &str = "00000000-0000-4000-8000-000000000001";
    const TEST_GEN: &str = "00000000-0000-4000-8000-0000000000a2";

    fn authority() -> CString {
        cstr(
            r#"{"session_epoch":"00000000-0000-4000-8000-0000000000a2","term":1,"lease_id":"20000000-0000-4000-8000-000000000001","issuer_principal_id":"commander-principal-1","holder_principal_id":"commander-principal-1","holder_entity_id":"controller-1","issued_at_utc_ms":1000,"expires_at_utc_ms":2000}"#,
        )
    }

    #[derive(Clone, Copy)]
    enum HostileJson {
        DuplicateKey,
        Oversized,
        OverDepth,
    }

    struct HostileDocuments {
        object: String,
        rates: String,
        sensor: String,
        command: String,
        authority: String,
        request: String,
        error: String,
    }

    fn hostile_documents(hostile: HostileJson) -> HostileDocuments {
        let (member, rates) = match hostile {
            HostileJson::DuplicateKey => (
                r#""padding":0,"padding":1"#.to_string(),
                r#"{"p":150.0,"p":151.0}"#.to_string(),
            ),
            HostileJson::Oversized => {
                let padding = "x".repeat(ncp_core::bounded_json::MAX_FRAME_BYTES + 1);
                (
                    format!(r#""padding":"{padding}""#),
                    format!(r#"{{"p":150.0,"{padding}":0.0}}"#),
                )
            }
            HostileJson::OverDepth => {
                let arrays = "[".repeat(ncp_core::bounded_json::MAX_NESTING_DEPTH + 1);
                let closes = "]".repeat(ncp_core::bounded_json::MAX_NESTING_DEPTH + 1);
                let member = format!(r#""padding":{arrays}0{closes}"#);
                (member.clone(), format!(r#"{{"p":150.0,{member}}}"#))
            }
        };
        HostileDocuments {
            object: format!("{{{member}}}"),
            rates,
            sensor: format!(
                r#"{{"kind":"sensor_frame","ncp_version":"1.0","session_id":"s","stream":{{"epoch":"{TEST_EPOCH}","seq":1}},"session":{{"generation":"{TEST_GEN}"}},"t":0.0,"channels":{{"pose":{{"data":[0.5]}}}},{member}}}"#
            ),
            command: format!(
                r#"{{"kind":"command_frame","ncp_version":"1.0","session_id":"s","stream":{{"epoch":"{TEST_EPOCH}","seq":1}},"session":{{"generation":"{TEST_GEN}"}},"mode":"hold","ttl_ms":200.0,"channels":{{}},{member}}}"#
            ),
            authority: format!(
                r#"{{"session_epoch":"{TEST_GEN}","term":1,"lease_id":"20000000-0000-4000-8000-000000000001","issuer_principal_id":"commander-principal-1","holder_principal_id":"commander-principal-1","holder_entity_id":"controller-1","issued_at_utc_ms":1000,"expires_at_utc_ms":2000,{member}}}"#
            ),
            request: format!(r#"{{"kind":"step_request","operation":{{}},{member}}}"#),
            error: format!(
                r#"{{"kind":"error","ncp_version":"1.0","code":"NCP-WIRE-001","error":"rejected",{member}}}"#
            ),
        }
    }

    unsafe fn assert_every_json_ingress_rejects(hostile: HostileJson) {
        let documents = hostile_documents(hostile);
        let expected_code = match hostile {
            HostileJson::DuplicateKey => ncp_core::bounded_json::JsonLimitCode::DuplicateKey,
            HostileJson::Oversized => ncp_core::bounded_json::JsonLimitCode::FrameBytes,
            HostileJson::OverDepth => ncp_core::bounded_json::JsonLimitCode::NestingDepth,
        };
        for (label, json) in [
            ("object", documents.object.as_str()),
            ("rates", documents.rates.as_str()),
            ("sensor", documents.sensor.as_str()),
            ("command", documents.command.as_str()),
            ("authority", documents.authority.as_str()),
            ("request", documents.request.as_str()),
            ("error", documents.error.as_str()),
        ] {
            let Err(error) = preflight_json(json) else {
                panic!("{label} hostile document unexpectedly preflighted");
            };
            assert_eq!(error.code, expected_code, "{label} hostile document");
        }
        let object = cstr(&documents.object);
        let rates = cstr(&documents.rates);
        let sensor = cstr(&documents.sensor);
        let command = cstr(&documents.command);
        let hostile_authority = cstr(&documents.authority);
        let request = cstr(&documents.request);
        let error = cstr(&documents.error);

        let valid_codec = cstr(
            r#"{"encoder":[{"channel":"pose","population":"p","value_range":[-1,1]}],"decoder":[{"population":"p","command_channel":"velocity_setpoint","value_range":[-1,1]}]}"#,
        );
        let valid_rates = cstr(r#"{"p":150.0}"#);
        let valid_sensor = cstr(&format!(
            r#"{{"kind":"sensor_frame","ncp_version":"1.0","session_id":"s","stream":{{"epoch":"{TEST_EPOCH}","seq":1}},"session":{{"generation":"{TEST_GEN}"}},"t":0.0,"channels":{{"pose":{{"data":[0.5]}}}}}}"#
        ));
        let valid_command = cstr(&format!(
            r#"{{"kind":"command_frame","ncp_version":"1.0","session_id":"s","stream":{{"epoch":"{TEST_EPOCH}","seq":1}},"session":{{"generation":"{TEST_GEN}"}},"mode":"hold","ttl_ms":200.0,"channels":{{}}}}"#
        ));
        let valid_limits = cstr("{}");
        let epoch = cstr(TEST_EPOCH);
        let generation = cstr(TEST_GEN);
        let session_id = cstr("s");
        let hold = cstr("hold");
        let active = cstr("active");
        let error_kind = cstr("error");
        let mut accepted = Vec::new();

        macro_rules! reject_owned_string {
            ($label:literal, $call:expr) => {{
                let output = $call;
                if !output.is_null() {
                    let value = take(output).unwrap_or_else(|| "<invalid UTF-8>".to_string());
                    accepted.push(format!("{} returned {value}", $label));
                }
            }};
        }

        reject_owned_string!("request_digest", ncp_request_digest(request.as_ptr()));
        reject_owned_string!(
            "encode_rates.codec",
            ncp_encode_rates(object.as_ptr(), std::ptr::null())
        );
        reject_owned_string!(
            "encode_rates.sensor",
            ncp_encode_rates(valid_codec.as_ptr(), sensor.as_ptr())
        );
        reject_owned_string!(
            "decode_command.codec",
            ncp_decode_command(
                object.as_ptr(),
                valid_rates.as_ptr(),
                0.0,
                epoch.as_ptr(),
                1,
                generation.as_ptr(),
                session_id.as_ptr(),
                std::ptr::null(),
                hold.as_ptr(),
                std::ptr::null(),
            )
        );
        reject_owned_string!(
            "decode_command.rates",
            ncp_decode_command(
                valid_codec.as_ptr(),
                rates.as_ptr(),
                0.0,
                epoch.as_ptr(),
                1,
                generation.as_ptr(),
                session_id.as_ptr(),
                std::ptr::null(),
                hold.as_ptr(),
                std::ptr::null(),
            )
        );
        reject_owned_string!(
            "decode_command.authority",
            ncp_decode_command(
                valid_codec.as_ptr(),
                valid_rates.as_ptr(),
                0.0,
                epoch.as_ptr(),
                1,
                generation.as_ptr(),
                session_id.as_ptr(),
                std::ptr::null(),
                active.as_ptr(),
                hostile_authority.as_ptr(),
            )
        );
        reject_owned_string!(
            "govern.limits",
            ncp_govern(
                object.as_ptr(),
                valid_command.as_ptr(),
                1.0,
                valid_sensor.as_ptr(),
                1.0,
            )
        );
        reject_owned_string!(
            "govern.command",
            ncp_govern(
                valid_limits.as_ptr(),
                command.as_ptr(),
                1.0,
                valid_sensor.as_ptr(),
                1.0,
            )
        );
        reject_owned_string!(
            "govern.sensor",
            ncp_govern(
                valid_limits.as_ptr(),
                valid_command.as_ptr(),
                1.0,
                sensor.as_ptr(),
                1.0,
            )
        );

        let hostile_governor = ncp_governor_new(object.as_ptr());
        if !hostile_governor.is_null() {
            ncp_governor_free(hostile_governor);
            accepted.push("governor_new.limits returned a handle".to_string());
        }
        let governor = ncp_governor_new(valid_limits.as_ptr());
        if governor.is_null() {
            panic!("valid governor setup unexpectedly failed");
        }
        reject_owned_string!(
            "governor_govern.command",
            ncp_governor_govern(governor, command.as_ptr(), 1.0, valid_sensor.as_ptr(), 1.0,)
        );
        reject_owned_string!(
            "governor_govern.sensor",
            ncp_governor_govern(governor, valid_command.as_ptr(), 1.0, sensor.as_ptr(), 1.0,)
        );
        ncp_governor_free(governor);

        let buffer = ncp_action_buffer_new();
        if buffer.is_null() {
            panic!("valid action-buffer setup unexpectedly failed");
        }
        if ncp_action_buffer_on_command(buffer, 1.0, command.as_ptr()) != -1 {
            accepted.push("action_buffer_on_command.command returned success".to_string());
        }
        ncp_action_buffer_free(buffer);

        reject_owned_string!(
            "validate",
            ncp_validate(error_kind.as_ptr(), error.as_ptr())
        );
        assert!(
            accepted.is_empty(),
            "bounded-JSON ingress accepted hostile documents: {accepted:?}"
        );
    }

    #[test]
    fn contract_hash_and_status() {
        assert_eq!(
            unsafe { take(ncp_package_version()) }.as_deref(),
            Some(env!("CARGO_PKG_VERSION"))
        );
        assert_eq!(
            unsafe { take(ncp_normative_contract_digest()) }.as_deref(),
            Some(ncp_core::NORMATIVE_CONTRACT_DIGEST)
        );
        assert_eq!(
            unsafe { take(ncp_build_identity()) }.as_deref(),
            Some(ncp_core::BUILD_IDENTITY)
        );
        // The C ABI exposes the same CONTRACT_HASH as the Rust core (cross-language anchor).
        let h = unsafe { take(ncp_contract_hash()) }.unwrap();
        assert_eq!(h, ncp_core::CONTRACT_HASH);
        // Advisory status: 1=match, 0=not advertised (NULL), 2=mismatch.
        let ours = cstr(ncp_core::CONTRACT_HASH);
        assert_eq!(unsafe { ncp_contract_status(ours.as_ptr()) }, 1);
        assert_eq!(unsafe { ncp_contract_status(std::ptr::null()) }, 0);
        let bad = cstr("deadbeefdeadbeef");
        assert_eq!(unsafe { ncp_contract_status(bad.as_ptr()) }, 2);
    }

    #[test]
    fn rpc_keys_are_kind_scoped_and_realm_validated() {
        let realm = cstr("fleet/ncp");
        let open = cstr("open_session");
        let bad_kind = cstr("session_opened");
        assert_eq!(
            unsafe { take(ncp_key_rpc_kind(realm.as_ptr(), open.as_ptr())) }.as_deref(),
            Some("fleet/ncp/rpc/open_session")
        );
        assert_eq!(
            unsafe { take(ncp_key_rpc_glob(realm.as_ptr())) }.as_deref(),
            Some("fleet/ncp/rpc/*")
        );
        assert!(unsafe { ncp_key_rpc_kind(realm.as_ptr(), bad_kind.as_ptr()) }.is_null());

        let injected = cstr("ncp/*");
        assert!(unsafe { ncp_key_rpc(injected.as_ptr()) }.is_null());
        assert!(unsafe { ncp_key_rpc_glob(injected.as_ptr()) }.is_null());

        let bad_session = cstr("s1/*");
        assert!(unsafe { ncp_key_sensor(realm.as_ptr(), bad_session.as_ptr()) }.is_null());
        assert!(unsafe { ncp_key_command(realm.as_ptr(), bad_session.as_ptr()) }.is_null());
        assert!(unsafe { ncp_key_observation(realm.as_ptr(), bad_session.as_ptr()) }.is_null());
    }

    #[test]
    fn invalid_utf8_is_rejected_instead_of_defaulted() {
        let invalid = [0xff_u8, 0];
        let invalid = invalid.as_ptr().cast::<c_char>();
        assert_eq!(unsafe { ncp_contract_status(invalid) }, -1);
        assert!(unsafe { ncp_key_rpc(invalid) }.is_null());

        let codec = cstr("{}");
        let rates = cstr("{}");
        let (ep, gen, sid) = (cstr(TEST_EPOCH), cstr(TEST_GEN), cstr("s"));
        assert!(unsafe {
            ncp_decode_command(
                codec.as_ptr(),
                rates.as_ptr(),
                0.0,
                ep.as_ptr(),
                1,
                gen.as_ptr(),
                sid.as_ptr(),
                invalid,
                std::ptr::null(),
                std::ptr::null(),
            )
        }
        .is_null());

        let limits = cstr(r#"{"command_timeout_ms":500.0}"#);
        let command = cstr(
            r#"{"kind":"command_frame","ncp_version":"1.0","session_id":"s","stream":{"epoch":"00000000-0000-4000-8000-000000000001","seq":1},"session":{"generation":"00000000-0000-4000-8000-0000000000a2"},"mode":"hold","ttl_ms":200.0,"channels":{}}"#,
        );
        assert!(
            unsafe { ncp_govern(limits.as_ptr(), command.as_ptr(), 1.0, invalid, 1.0,) }.is_null()
        );
    }

    #[test]
    fn validate_accepts_typed_error_frame() {
        let kind = cstr("error");
        let body = cstr(&format!(
            r#"{{"kind":"error","ncp_version":"{}","code":"NCP-WIRE-001","error":"rejected","request_kind":"open_session"}}"#,
            ncp_core::NCP_VERSION
        ));
        assert!(unsafe { take(ncp_validate(kind.as_ptr(), body.as_ptr())) }.is_some());
    }

    #[test]
    fn validate_rejects_missing_or_unknown_error_code() {
        let kind = cstr("error");
        let missing = cstr(&format!(
            r#"{{"kind":"error","ncp_version":"{}","error":"rejected"}}"#,
            ncp_core::NCP_VERSION
        ));
        assert!(unsafe { ncp_validate(kind.as_ptr(), missing.as_ptr()) }.is_null());

        let unknown = cstr(&format!(
            r#"{{"kind":"error","ncp_version":"{}","code":"NCP-NOT-REGISTERED","error":"rejected"}}"#,
            ncp_core::NCP_VERSION
        ));
        assert!(unsafe { ncp_validate(kind.as_ptr(), unknown.as_ptr()) }.is_null());
    }

    #[test]
    fn validate_rejects_over_budget_and_duplicate_top_level_json() {
        let kind = cstr("error");

        // This is otherwise valid, semantically small ErrorFrame JSON. The large
        // unknown array would be ignored by the typed round-trip, so only a true
        // pre-deserialization ingress budget prevents the allocation.
        let mut oversized = format!(
            r#"{{"kind":"error","ncp_version":"{}","code":"NCP-WIRE-001","error":"rejected","padding":["#,
            ncp_core::NCP_VERSION
        );
        while oversized.len() <= ncp_core::bounded_json::MAX_FRAME_BYTES {
            oversized.push_str(r#""padding","#);
        }
        oversized.push_str(r#""tail"]}"#);
        assert!(oversized.len() > ncp_core::bounded_json::MAX_FRAME_BYTES);
        let oversized = cstr(&oversized);
        assert!(unsafe { ncp_validate(kind.as_ptr(), oversized.as_ptr()) }.is_null());

        // serde_json::Value normally keeps only the last duplicate. The universal
        // scanner must reject the ambiguity before that lossy deserialization.
        let duplicate = cstr(&format!(
            r#"{{"kind":"error","ncp_version":"{}","code":"NCP-WIRE-001","error":"first","error":"second"}}"#,
            ncp_core::NCP_VERSION
        ));
        assert!(unsafe { ncp_validate(kind.as_ptr(), duplicate.as_ptr()) }.is_null());
    }

    #[test]
    fn validate_rejects_over_depth_and_node_budget_json() {
        let kind = cstr("error");

        let nested = format!(
            r#"{{"kind":"error","ncp_version":"{}","code":"NCP-WIRE-001","error":"rejected","padding":{}0{}}}"#,
            ncp_core::NCP_VERSION,
            "[".repeat(ncp_core::bounded_json::MAX_NESTING_DEPTH),
            "]".repeat(ncp_core::bounded_json::MAX_NESTING_DEPTH)
        );
        let nested = cstr(&nested);
        assert!(unsafe { ncp_validate(kind.as_ptr(), nested.as_ptr()) }.is_null());

        let nodes = format!(
            r#"{{"kind":"error","ncp_version":"{}","code":"NCP-WIRE-001","error":"rejected","padding":[{}]}}"#,
            ncp_core::NCP_VERSION,
            std::iter::repeat_n("{}", ncp_core::bounded_json::MAX_OBJECTS)
                .collect::<Vec<_>>()
                .join(",")
        );
        let nodes = cstr(&nodes);
        assert!(unsafe { ncp_validate(kind.as_ptr(), nodes.as_ptr()) }.is_null());
    }

    #[test]
    fn every_json_ingress_rejects_duplicate_object_keys() {
        unsafe { assert_every_json_ingress_rejects(HostileJson::DuplicateKey) };
    }

    #[test]
    fn every_json_ingress_rejects_oversized_documents() {
        unsafe { assert_every_json_ingress_rejects(HostileJson::Oversized) };
    }

    #[test]
    fn every_json_ingress_rejects_over_depth_documents() {
        unsafe { assert_every_json_ingress_rejects(HostileJson::OverDepth) };
    }

    #[test]
    fn ffi_guard_catches_panic_and_returns_sentinel() {
        // A panicking body must NOT unwind across the (simulated) C ABI; it returns
        // the sentinel instead (FIX 8). Silence the default panic print for noise.
        let prev = std::panic::take_hook();
        std::panic::set_hook(Box::new(|_| {}));
        let out: *mut c_char = ffi_guard(std::ptr::null_mut(), || panic!("boom"));
        let code: i32 = ffi_guard(-1, || panic!("boom"));
        std::panic::set_hook(prev);
        assert!(out.is_null());
        assert_eq!(code, -1);
    }

    #[test]
    fn decode_command_emits_hold_and_estop_and_frame_id() {
        let codec = cstr("{}");
        let rates = cstr("{}");
        // SHOULD-FIX C decode completeness: the C path can now emit non-active modes
        // and a non-"world" frame id.
        let (ep, gen, sid) = (cstr(TEST_EPOCH), cstr(TEST_GEN), cstr("s"));
        for (mode, expect) in [
            ("hold", "\"mode\":\"hold\""),
            ("estop", "\"mode\":\"estop\""),
        ] {
            let m = cstr(mode);
            let fid = cstr("base_link");
            let out = unsafe {
                take(ncp_decode_command(
                    codec.as_ptr(),
                    rates.as_ptr(),
                    0.0,
                    ep.as_ptr(),
                    1,
                    gen.as_ptr(),
                    sid.as_ptr(),
                    fid.as_ptr(),
                    m.as_ptr(),
                    std::ptr::null(),
                ))
            }
            .expect("valid mode must decode");
            assert!(out.contains(expect), "mode {mode}: {out}");
            assert!(out.contains("base_link"), "frame_id missing: {out}");
        }
    }

    #[test]
    fn decode_command_defaults_are_world_and_hold() {
        let codec = cstr("{}");
        let rates = cstr("{}");
        // NULL frame_id => "world", NULL mode => fail-safe "hold".
        let (ep, gen, sid) = (cstr(TEST_EPOCH), cstr(TEST_GEN), cstr("s"));
        let out = unsafe {
            take(ncp_decode_command(
                codec.as_ptr(),
                rates.as_ptr(),
                0.0,
                ep.as_ptr(),
                1,
                gen.as_ptr(),
                sid.as_ptr(),
                std::ptr::null(),
                std::ptr::null(),
                std::ptr::null(),
            ))
        }
        .expect("defaults must decode");
        assert!(out.contains("\"mode\":\"hold\""), "{out}");
        assert!(out.contains("world"), "{out}");
    }

    #[test]
    fn codec_boundaries_require_complete_wire_frames_and_safe_decode_metadata() {
        let codec = cstr(
            r#"{"encoder":[{"channel":"pose","population":"p","value_range":[-1,1]}],"decoder":[{"population":"p","command_channel":"velocity_setpoint","value_range":[-1,1]}]}"#,
        );
        let valid_sensor = cstr(
            r#"{"kind":"sensor_frame","ncp_version":"1.0","session_id":"s","stream":{"epoch":"00000000-0000-4000-8000-000000000001","seq":1},"session":{"generation":"00000000-0000-4000-8000-0000000000a2"},"t":0.0,"channels":{"pose":{"data":[0.5]}}}"#,
        );
        assert!(unsafe { take(ncp_encode_rates(codec.as_ptr(), valid_sensor.as_ptr())) }.is_some());

        let versionless_sensor =
            cstr(r#"{"kind":"sensor_frame","seq":1,"t":0.0,"channels":{"pose":{"data":[0.5]}}}"#);
        assert!(unsafe { ncp_encode_rates(codec.as_ptr(), versionless_sensor.as_ptr()) }.is_null());

        let rates = cstr(r#"{"p":150.0}"#);
        let active = cstr("active");
        let authority = authority();
        let (ep, gen, sid) = (cstr(TEST_EPOCH), cstr(TEST_GEN), cstr("s"));
        assert!(unsafe {
            take(ncp_decode_command(
                codec.as_ptr(),
                rates.as_ptr(),
                0.0,
                ep.as_ptr(),
                1,
                gen.as_ptr(),
                sid.as_ptr(),
                std::ptr::null(),
                active.as_ptr(),
                authority.as_ptr(),
            ))
        }
        .is_some());
        // seq 0 is below the wire-safe floor: the generated command is rejected.
        assert!(unsafe {
            ncp_decode_command(
                codec.as_ptr(),
                rates.as_ptr(),
                0.0,
                ep.as_ptr(),
                0,
                gen.as_ptr(),
                sid.as_ptr(),
                std::ptr::null(),
                active.as_ptr(),
                authority.as_ptr(),
            )
        }
        .is_null());
        assert!(unsafe {
            ncp_decode_command(
                codec.as_ptr(),
                rates.as_ptr(),
                f64::NAN,
                ep.as_ptr(),
                1,
                gen.as_ptr(),
                sid.as_ptr(),
                std::ptr::null(),
                active.as_ptr(),
                authority.as_ptr(),
            )
        }
        .is_null());
    }

    #[test]
    fn malformed_sensor_is_rejected_instead_of_treated_as_fresh() {
        let limits = cstr(r#"{"command_timeout_ms":500.0}"#);
        let command = cstr(
            r#"{"kind":"command_frame","ncp_version":"1.0","session_id":"s","stream":{"epoch":"00000000-0000-4000-8000-000000000001","seq":1},"session":{"generation":"00000000-0000-4000-8000-0000000000a2"},"mode":"active","ttl_ms":200.0,"channels":{"velocity_setpoint":{"data":[1.0]}},"authority":{"session_epoch":"00000000-0000-4000-8000-0000000000a2","term":1,"lease_id":"20000000-0000-4000-8000-000000000001","issuer_principal_id":"commander-principal-1","holder_principal_id":"commander-principal-1","holder_entity_id":"controller-1","issued_at_utc_ms":1000,"expires_at_utc_ms":2000}}"#,
        );
        let malformed = cstr(r#"{"kind":"sensor_frame","channels":{"pose":{"data":"bad"}}}"#);

        let one_shot = unsafe {
            ncp_govern(
                limits.as_ptr(),
                command.as_ptr(),
                1.0,
                malformed.as_ptr(),
                1.0,
            )
        };
        assert!(
            one_shot.is_null(),
            "malformed sensor must not reach actuation"
        );

        let governor = unsafe { ncp_governor_new(limits.as_ptr()) };
        assert!(!governor.is_null());
        let persistent = unsafe {
            ncp_governor_govern(governor, command.as_ptr(), 1.0, malformed.as_ptr(), 1.0)
        };
        assert!(persistent.is_null(), "malformed sensor must be rejected");
        unsafe { ncp_governor_free(governor) };
    }

    #[test]
    fn validate_does_not_fabricate_a_missing_kind() {
        let kind = cstr("command_frame");
        let body = cstr(r#"{"ncp_version":"1.0","seq":1}"#);
        let out = unsafe { ncp_validate(kind.as_ptr(), body.as_ptr()) };
        assert!(out.is_null(), "wire-1.0 kind must be present in the body");
    }

    #[test]
    fn validate_preserves_fail_safe_additive_mode() {
        let kind = cstr("command_frame");
        let body = cstr(&format!(
            r#"{{"kind":"command_frame","ncp_version":"{}","stream":{{"epoch":"{}","seq":1}},"session":{{"generation":"{}"}},"session_id":"s","mode":"future_safe_mode"}}"#,
            ncp_core::NCP_VERSION,
            TEST_EPOCH,
            TEST_GEN,
        ));
        let out = unsafe { take(ncp_validate(kind.as_ptr(), body.as_ptr())) }
            .expect("an additive non-authorizing mode should validate");
        assert!(out.contains("\"mode\":\"future_safe_mode\""), "{out}");
    }

    #[test]
    fn decode_command_rejects_unknown_mode() {
        let codec = cstr("{}");
        let rates = cstr("{}");
        let bad = cstr("turbo");
        let (ep, gen, sid) = (cstr(TEST_EPOCH), cstr(TEST_GEN), cstr("s"));
        let out = unsafe {
            ncp_decode_command(
                codec.as_ptr(),
                rates.as_ptr(),
                0.0,
                ep.as_ptr(),
                1,
                gen.as_ptr(),
                sid.as_ptr(),
                std::ptr::null(),
                bad.as_ptr(),
                std::ptr::null(),
            )
        };
        assert!(out.is_null(), "unknown mode must return NULL");
    }

    #[test]
    fn action_buffer_enforces_horizon_drain_ttl_and_replay() {
        let buffer = ncp_action_buffer_new();
        assert!(!buffer.is_null());
        let command = cstr(
            r#"{"kind":"command_frame","ncp_version":"1.0","session_id":"s","stream":{"epoch":"00000000-0000-4000-8000-000000000001","seq":10},"session":{"generation":"00000000-0000-4000-8000-0000000000a2"},"t":0.0,"mode":"active","ttl_ms":200.0,"channels":{"velocity_setpoint":{"data":[0.1]}},"horizon":[{"velocity_setpoint":{"data":[0.2]}},{"velocity_setpoint":{"data":[0.3]}}],"horizon_dt_ms":50.0,"authority":{"session_epoch":"00000000-0000-4000-8000-0000000000a2","term":1,"lease_id":"20000000-0000-4000-8000-000000000001","issuer_principal_id":"commander-principal-1","holder_principal_id":"commander-principal-1","holder_entity_id":"controller-1","issued_at_utc_ms":1000,"expires_at_utc_ms":2000}}"#,
        );
        assert_eq!(
            unsafe { ncp_action_buffer_on_command(buffer, 1.0, command.as_ptr()) },
            0
        );
        let tick_one = unsafe { take(ncp_action_buffer_active(buffer, 1.06)) }.unwrap();
        let tick_one: serde_json::Value = serde_json::from_str(&tick_one).unwrap();
        assert_eq!(tick_one["velocity_setpoint"]["data"][0], 0.2);
        assert_eq!(
            unsafe { ncp_action_buffer_should_hold(buffer, 1.16) },
            1,
            "a drained horizon must HOLD before TTL expiry"
        );

        let duplicate = cstr(
            r#"{"kind":"command_frame","ncp_version":"1.0","session_id":"s","stream":{"epoch":"00000000-0000-4000-8000-000000000001","seq":10},"session":{"generation":"00000000-0000-4000-8000-0000000000a2"},"t":0.0,"mode":"active","ttl_ms":200.0,"channels":{"velocity_setpoint":{"data":[9.0]}},"authority":{"session_epoch":"00000000-0000-4000-8000-0000000000a2","term":1,"lease_id":"20000000-0000-4000-8000-000000000001","issuer_principal_id":"commander-principal-1","holder_principal_id":"commander-principal-1","holder_entity_id":"controller-1","issued_at_utc_ms":1000,"expires_at_utc_ms":2000}}"#,
        );
        assert_eq!(
            unsafe { ncp_action_buffer_on_command(buffer, 2.0, duplicate.as_ptr()) },
            0
        );
        assert_eq!(
            unsafe { ncp_action_buffer_should_hold(buffer, 2.0) },
            1,
            "an equal-seq replay must not revive an expired stream"
        );
        unsafe { ncp_action_buffer_free(buffer) };
    }

    #[test]
    fn local_action_buffer_reset_retires_generation_context() {
        let buffer = ncp_action_buffer_new();
        assert_eq!(unsafe { ncp_action_buffer_is_retired(buffer) }, 0);
        let estop = cstr(r#"{"mode":"estop"}"#);
        assert_eq!(
            unsafe { ncp_action_buffer_on_command(buffer, 0.0, estop.as_ptr()) },
            0
        );
        assert_eq!(unsafe { ncp_action_buffer_is_estopped(buffer) }, 1);
        assert_eq!(
            unsafe { take(ncp_action_buffer_active(buffer, 0.0)) }.as_deref(),
            Some("null")
        );
        unsafe { ncp_action_buffer_reset(buffer) };
        assert_eq!(unsafe { ncp_action_buffer_is_estopped(buffer) }, 0);
        assert_eq!(unsafe { ncp_action_buffer_is_retired(buffer) }, 1);
        unsafe { ncp_action_buffer_free(buffer) };
    }

    #[test]
    fn null_and_garbage_inputs_return_null_not_crash() {
        unsafe {
            assert!(ncp_encode_rates(std::ptr::null(), std::ptr::null()).is_null());
            assert!(ncp_encode_rates(cstr("{}").as_ptr(), cstr("").as_ptr()).is_null());
            assert!(ncp_validate(cstr("nope").as_ptr(), cstr("{}").as_ptr()).is_null());
            assert_eq!(ncp_check_version(std::ptr::null(), false), -1);
        }
    }
}
