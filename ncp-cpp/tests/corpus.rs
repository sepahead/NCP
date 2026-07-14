//! Cross-language conformance: every golden JSON vector in the shared corpus
//! (`conformance/vectors/*.json`) must validate through the C ABI `ncp_validate`.
//! This proves the C++ SDK agrees with the SAME language-agnostic vectors the
//! Python `validate` and the Rust serde/schema guards check — so a divergence in
//! any one binding's wire handling fails CI, not a downstream integration.

use ncp_cpp::{ncp_request_digest, ncp_string_free, ncp_validate};
use std::collections::BTreeSet;
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

unsafe fn request_digest(json: &str) -> Option<String> {
    let json = CString::new(json).unwrap();
    let out = ncp_request_digest(json.as_ptr());
    if out.is_null() {
        return None;
    }
    let digest = CStr::from_ptr(out).to_str().unwrap().to_owned();
    ncp_string_free(out);
    Some(digest)
}

fn apply_digest_case(base: &serde_json::Value, case: &serde_json::Value) -> serde_json::Value {
    let mut request = base.clone();
    for patch in case["patch"].as_array().unwrap() {
        let path = patch["path"].as_array().unwrap();
        let mut parent = &mut request;
        for segment in &path[..path.len() - 1] {
            parent = parent
                .as_object_mut()
                .unwrap()
                .get_mut(segment.as_str().unwrap())
                .unwrap();
        }
        let leaf = path.last().unwrap().as_str().unwrap();
        let object = parent.as_object_mut().unwrap();
        match patch["op"].as_str().unwrap() {
            "set" => {
                object.insert(leaf.to_owned(), patch["value"].clone());
            }
            "remove" => {
                object.remove(leaf).unwrap();
            }
            operation => panic!("unknown request-digest patch operation {operation:?}"),
        }
    }
    request
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
        "expected the complete wire-1.0 JSON corpus (14 vectors); update this pin deliberately when the contract grows"
    );
}

#[test]
fn request_digest_vectors_execute_through_the_c_abi() {
    let path =
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("testdata/conformance/request-digest.json");
    let corpus: serde_json::Value = serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap();
    for case in corpus["cases"].as_array().unwrap() {
        let request = apply_digest_case(&corpus["base_request"], case);
        let json = serde_json::to_string(&request).unwrap();
        assert_eq!(
            unsafe { request_digest(&json) }.as_deref(),
            case["expected_digest"].as_str(),
            "request-digest case {}",
            case["id"].as_str().unwrap()
        );
    }
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
    // Wire 1.0: a post-open mutation targets a live incarnation and must carry
    // both explicit idempotency context and a matching authority lease.
    let good = format!(
        r#"{{"kind":"step_request","ncp_version":"{ver}","session_id":"s1","session":{{"generation":"00000000-0000-4000-8000-0000000000a2"}},"operation":{{"operation_id":"10000000-0000-4000-8000-000000000001","request_digest":"ccab282b4796e57af583ce5eb81145ca93c9c14e4b6178215d682cb19951e67e","session_epoch":"00000000-0000-4000-8000-0000000000a2","expected_state_version":1,"deadline_utc_ms":1700000030000,"retry":false}},"authority":{{"session_epoch":"00000000-0000-4000-8000-0000000000a2","term":1,"lease_id":"20000000-0000-4000-8000-000000000001","issuer_principal_id":"authority","holder_principal_id":"controller","holder_entity_id":"controller","issued_at_utc_ms":1700000000000,"expires_at_utc_ms":1700000030000}}}}"#
    );
    assert!(unsafe { validate("step_request", &good) }.is_some());
    // Wire 0.6: the version itself is now required — its absence alone rejects.
    let versionless = r#"{"kind":"step_request","session_id":"s1"}"#;
    assert!(
        unsafe { validate("step_request", versionless) }.is_none(),
        "a version-less message must be rejected through the C ABI"
    );
}

#[test]
fn mandatory_cpp_manifest_set_is_exact() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("testdata/conformance");
    let manifest: serde_json::Value =
        serde_json::from_slice(&std::fs::read(root.join("manifest.v1.json")).unwrap()).unwrap();
    let behavior: serde_json::Value =
        serde_json::from_slice(&std::fs::read(root.join("behavior/vectors.json")).unwrap())
            .unwrap();
    let mut executed = BTreeSet::new();
    for (family, cases) in behavior["cases"].as_object().unwrap() {
        for case in cases.as_array().unwrap() {
            executed.insert(format!(
                "behavior/{family}/{}",
                case["name"].as_str().unwrap()
            ));
        }
    }
    let request_digest: serde_json::Value =
        serde_json::from_slice(&std::fs::read(root.join("request-digest.json")).unwrap()).unwrap();
    for case in request_digest["cases"].as_array().unwrap() {
        executed.insert(format!("request-digest/{}", case["id"].as_str().unwrap()));
    }
    for entry in std::fs::read_dir(root.join("vectors")).unwrap() {
        let path = entry.unwrap().path();
        if path.extension().and_then(|value| value.to_str()) != Some("json") {
            continue;
        }
        let value: serde_json::Value =
            serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap();
        executed.insert(format!(
            "wire/{}/canonical",
            value["kind"].as_str().unwrap()
        ));
    }
    let required = manifest["vectors"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|vector| vector["required"].as_bool() == Some(true))
        .filter(|vector| vector["stability"].as_str() == Some("stable-1.0"))
        .filter(|vector| {
            vector["applicability"]["implementations"]
                .as_array()
                .is_some_and(|implementations| {
                    implementations
                        .iter()
                        .any(|implementation| implementation.as_str() == Some("cpp-ffi"))
                })
        })
        .map(|vector| vector["id"].as_str().unwrap().to_owned())
        .collect::<BTreeSet<_>>();
    assert_eq!(
        executed, required,
        "C++ FFI conformance must execute the exact required manifest set"
    );
}
