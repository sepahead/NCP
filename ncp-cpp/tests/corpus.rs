//! Cross-language conformance: every golden JSON vector in the shared corpus
//! (`conformance/vectors/*.json`) must validate through the C ABI `ncp_validate`.
//! This proves the C++ SDK agrees with the SAME language-agnostic vectors the
//! Python `validate` and the Rust serde/schema guards check — so a divergence in
//! any one binding's wire handling fails CI, not a downstream integration.

use ncp_cpp::{ncp_string_free, ncp_validate};
use std::ffi::{CStr, CString};
use std::path::PathBuf;

/// Drive one (kind, json) pair through the C ABI; `Some(canonical_json)` on
/// accept, `None` on the NULL sentinel (reject), freeing via the FFI path.
unsafe fn validate(kind: &str, json: &str) -> Option<String> {
    let k = CString::new(kind).unwrap();
    let j = CString::new(json).unwrap();
    let out = ncp_validate(k.as_ptr(), j.as_ptr());
    if out.is_null() {
        return None;
    }
    let s = CStr::from_ptr(out).to_str().unwrap().to_string();
    ncp_string_free(out);
    Some(s)
}

fn vectors_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("testdata/conformance/vectors")
}

#[test]
fn every_json_vector_validates_through_the_c_abi() {
    let dir = vectors_dir();
    let mut n = 0;
    for entry in std::fs::read_dir(&dir).expect("packaged conformance vectors readable") {
        let path = entry.unwrap().path();
        if path.extension().and_then(|e| e.to_str()) != Some("json") {
            continue; // skip the binary bulk vectors (*.bin)
        }
        let json = std::fs::read_to_string(&path).unwrap();
        let v: serde_json::Value = serde_json::from_str(&json).unwrap();
        let kind = v["kind"].as_str().expect("vector carries a string `kind`");
        let out = unsafe { validate(kind, &json) };
        assert!(
            out.is_some(),
            "vector {:?} (kind {kind}) must validate through ncp_validate",
            path.file_name().unwrap()
        );
        n += 1;
    }
    assert_eq!(
        n, 14,
        "expected the complete wire-0.7 JSON corpus (14 vectors); update this pin deliberately when the contract grows"
    );
}

#[test]
fn tampered_scientific_boundary_is_rejected_through_the_c_abi() {
    // A frame asserting it is a calibrated posterior must be rejected by the C++
    // SDK exactly as by the Rust reference (the ncp_core::validate value-pin).
    // Both frames carry the same wire-0.8 identity envelope so the boundary pin is
    // the only thing that differs between them.
    let ver = ncp_core::NCP_VERSION;
    // Own stream position (seq >= 1) + live session, no `source`: the legal
    // pull/RPC-reply form is distinguished by source ABSENCE, not by seq 0.
    let ident = r#""session_id":"s1","stream":{"epoch":"00000000-0000-4000-8000-000000000001","seq":1},"session":{"generation":"00000000-0000-4000-8000-0000000000a2"}"#;
    let lie = format!(
        r#"{{"kind":"observation_frame","ncp_version":"{ver}",{ident},"records":{{}},"calibrated_posterior":true,"is_simulation_output":true}}"#
    );
    assert!(
        unsafe { validate("observation_frame", &lie) }.is_none(),
        "calibrated_posterior=true must be rejected through the C ABI"
    );
    let honest = format!(
        r#"{{"kind":"observation_frame","ncp_version":"{ver}",{ident},"records":{{}},"calibrated_posterior":false,"is_simulation_output":true}}"#
    );
    assert!(unsafe { validate("observation_frame", &honest) }.is_some());
}

#[test]
fn missing_required_is_rejected_through_the_c_abi() {
    // A step_request without its required session_id must reject (the canonical
    // ncp_core::validate check the typed round-trip alone would silently default).
    let ver = ncp_core::NCP_VERSION;
    let bad = format!(r#"{{"kind":"step_request","ncp_version":"{ver}","advance_ms":1.0}}"#);
    assert!(unsafe { validate("step_request", &bad) }.is_none());
    // Wire 0.8: a post-open request also targets a live incarnation, so `session`
    // (the server-issued generation) is required alongside `session_id`.
    let good = format!(
        r#"{{"kind":"step_request","ncp_version":"{ver}","session_id":"s1","session":{{"generation":"00000000-0000-4000-8000-0000000000a2"}}}}"#
    );
    assert!(unsafe { validate("step_request", &good) }.is_some());
    // Wire 0.6: the version itself is now required — its absence alone rejects.
    let versionless = r#"{"kind":"step_request","session_id":"s1"}"#;
    assert!(
        unsafe { validate("step_request", versionless) }.is_none(),
        "a version-less message must be rejected through the C ABI"
    );
}
