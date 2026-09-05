//! Independent Python bit patterns and actual Galadriel output qualify JSON parsing.

use ncp_core::local::local_digest;
use serde::Deserialize;
use serde_json::Value;

#[derive(Deserialize)]
struct Vectors {
    schema: String,
    domain: String,
    cases: Vec<Case>,
}

#[derive(Deserialize)]
struct Case {
    id: String,
    decimal: String,
    bits: String,
    digest: String,
}

#[test]
fn independent_binary64_vectors_preserve_numeric_bits_and_complete_digests() {
    let vectors: Vectors =
        serde_json::from_str(include_str!("fixtures/local-binary64.json")).unwrap();
    assert_eq!(vectors.schema, "ncp.local.binary64-vectors.v1");
    let mut failures = Vec::new();
    for case in vectors.cases {
        let expected = u64::from_str_radix(&case.bits, 16).unwrap();
        let decoded: Value = serde_json::from_str(&case.decimal).unwrap();
        let observed = decoded.as_f64().unwrap().to_bits();
        if observed != expected {
            failures.push(format!(
                "{} decimal={} expected={expected:016x} observed={observed:016x}",
                case.id, case.decimal
            ));
        }
        let original = serde_json::to_value(f64::from_bits(expected)).unwrap();
        assert_eq!(
            local_digest(&vectors.domain, &original).unwrap(),
            case.digest,
            "{} independent typed digest",
            case.id
        );
        let wire = serde_json::to_vec(&original).unwrap();
        let reparsed: Value = serde_json::from_slice(&wire).unwrap();
        if local_digest(&vectors.domain, &reparsed).unwrap() != case.digest {
            failures.push(format!(
                "{} serialized JSON changed its typed digest",
                case.id
            ));
        }
    }
    assert!(failures.is_empty(), "{}", failures.join("\n"));
}
