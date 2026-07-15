//! Direct Rust-reference canonical-byte coverage for every mandatory stable
//! wire-shape vector. The optional report path is consumed by the repository's
//! cross-language harness; normal `cargo test` remains filesystem-independent.

use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

fn corpus_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("testdata/conformance")
}

fn required_wire_ids(root: &Path) -> BTreeSet<String> {
    let manifest: Value =
        serde_json::from_slice(&std::fs::read(root.join("manifest.v1.json")).unwrap()).unwrap();
    manifest["vectors"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|vector| vector["required"].as_bool() == Some(true))
        .filter(|vector| vector["stability"].as_str() == Some("stable-1.0"))
        .filter(|vector| vector["suite"].as_str() == Some("wire-shape"))
        .filter(|vector| {
            vector["applicability"]["implementations"]
                .as_array()
                .is_some_and(|implementations| {
                    implementations
                        .iter()
                        .any(|implementation| implementation.as_str() == Some("rust"))
                })
        })
        .map(|vector| vector["id"].as_str().unwrap().to_owned())
        .collect()
}

#[test]
fn mandatory_wire_vectors_emit_deterministic_canonical_bytes() {
    let root = corpus_root();
    let mut emitted = BTreeMap::new();

    for entry in std::fs::read_dir(root.join("vectors")).unwrap() {
        let path = entry.unwrap().path();
        if path.extension().and_then(|extension| extension.to_str()) != Some("json") {
            continue;
        }
        let source = std::fs::read(&path).unwrap();
        let value: Value = serde_json::from_slice(&source).unwrap();
        let kind = value["kind"].as_str().unwrap();
        let id = format!("wire/{kind}/canonical");
        let canonical =
            ncp_core::canonicalize_message_json(kind, &source).unwrap_or_else(|error| {
                panic!("{id}: Rust reference rejected canonical input: {error}")
            });
        let second = ncp_core::canonicalize_message_json(kind, canonical.as_bytes())
            .unwrap_or_else(|error| panic!("{id}: canonical output did not round-trip: {error}"));
        assert_eq!(
            canonical, second,
            "{id}: canonical emission is not idempotent"
        );
        assert!(
            emitted.insert(id.clone(), canonical).is_none(),
            "duplicate canonical vector id {id}"
        );
    }

    assert_eq!(
        emitted.keys().cloned().collect::<BTreeSet<_>>(),
        required_wire_ids(&root),
        "Rust canonical-byte harness must execute the exact mandatory stable wire-shape set"
    );
    assert_eq!(emitted.len(), 14, "stable wire-shape count changed");

    if let Some(path) = std::env::var_os("NCP_CANONICAL_JSON_REPORT") {
        let report = serde_json::json!({
            "schema": "ncp.canonical-json-emission-report.v1",
            "implementation": "rust",
            "vectors": emitted,
        });
        std::fs::write(path, serde_json::to_vec(&report).unwrap()).unwrap();
    }
}

#[test]
fn optional_cross_language_producer_matrix_round_trips_through_rust() {
    let Some(input_path) = std::env::var_os("NCP_CANONICAL_JSON_MATRIX_INPUT") else {
        return;
    };
    let output_path = std::env::var_os("NCP_CANONICAL_JSON_MATRIX_REPORT")
        .expect("matrix input requires NCP_CANONICAL_JSON_MATRIX_REPORT");
    let input: Value = serde_json::from_slice(&std::fs::read(input_path).unwrap()).unwrap();
    let producers = input["producers"]
        .as_object()
        .expect("matrix input carries a producers object");
    let expected_producers = ["cpp-ffi", "python-ffi", "rust", "typescript"]
        .into_iter()
        .map(str::to_owned)
        .collect::<BTreeSet<_>>();
    assert_eq!(
        producers.keys().cloned().collect::<BTreeSet<_>>(),
        expected_producers,
        "Rust matrix consumer requires the exact supported producer set"
    );

    let required = required_wire_ids(&corpus_root());
    let mut results = BTreeMap::<String, BTreeMap<String, String>>::new();
    for (producer, vectors) in producers {
        let vectors = vectors
            .as_object()
            .unwrap_or_else(|| panic!("producer {producer:?} vectors must be an object"));
        assert_eq!(
            vectors.keys().cloned().collect::<BTreeSet<_>>(),
            required,
            "Rust matrix consumer received an incomplete vector set from {producer}"
        );
        let mut consumed = BTreeMap::new();
        for (id, encoded) in vectors {
            let encoded = encoded
                .as_str()
                .unwrap_or_else(|| panic!("{producer}->{id}: payload must be a JSON string"));
            let kind = id
                .strip_prefix("wire/")
                .and_then(|value| value.strip_suffix("/canonical"))
                .unwrap_or_else(|| panic!("invalid wire vector id {id:?}"));
            let canonical = ncp_core::canonicalize_message_json(kind, encoded.as_bytes())
                .unwrap_or_else(|error| panic!("{producer}->rust {id}: rejected: {error}"));
            consumed.insert(id.clone(), canonical);
        }
        results.insert(producer.clone(), consumed);
    }

    let report = serde_json::json!({
        "schema": "ncp.canonical-json-consumer-report.v1",
        "consumer": "rust",
        "producers": results,
    });
    std::fs::write(output_path, serde_json::to_vec(&report).unwrap()).unwrap();
}
