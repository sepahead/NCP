use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

use serde_json::{Map, Value};

use crate::error::{EngineError, EngineResult};
use crate::model::{Corpus, DecisionSetBinding, Source};
use crate::sha256::sha256_hex;
use crate::source::{read_bounded, resolve_regular_relative_file};
use crate::strict_json::{canonicalize, parse_strict};

const REVIEW_PACKET_LIFECYCLE_SCHEMA: &str = "ncp.b01-review-packet-lifecycle.v1";

pub(crate) struct VerifiedDecisionSet {
    pub(crate) binding: DecisionSetBinding,
    sources: BTreeMap<String, DecisionSource>,
}

struct DecisionSource {
    path: String,
    byte_length: usize,
    sha256: String,
}

impl VerifiedDecisionSet {
    pub(crate) fn verify_source(&self, source: &Source) -> EngineResult<()> {
        let expected = self.sources.get(&source.adr).ok_or_else(|| {
            EngineError::corpus(format!(
                "case source uses a decision id absent from the bound registry: {:?}",
                source.adr
            ))
        })?;
        if source.path != expected.path
            || source.adr_byte_length != expected.byte_length
            || source.adr_sha256 != expected.sha256
        {
            return Err(EngineError::corpus(format!(
                "case source {:?} differs from its bound decision-registry identity",
                source.adr
            )));
        }
        Ok(())
    }
}

pub(crate) fn verify_decision_set(
    root: &Path,
    corpus: &Corpus,
) -> EngineResult<VerifiedDecisionSet> {
    let binding = &corpus.decision_set_binding;
    let registry_path = resolve_regular_relative_file(root, &binding.registry_path)?;
    let registry_bytes = read_bounded(&registry_path, corpus.limits.maximum_corpus_bytes)?;
    let registry = parse_strict(
        &registry_bytes,
        corpus.limits.json(corpus.limits.maximum_corpus_bytes),
    )
    .map_err(|error| EngineError::corpus(format!("invalid decision registry JSON: {error}")))?;
    let (projection, sources) = build_projection(&registry, binding)?;
    let projection = canonicalize(&projection);
    let projection_bytes = serde_json::to_vec(&projection).map_err(|error| {
        EngineError::json(format!(
            "serializing canonical decision projection: {error}"
        ))
    })?;
    if projection_bytes.len() != binding.projection_byte_length {
        return Err(EngineError::corpus(format!(
            "decision projection has {} bytes; expected {}",
            projection_bytes.len(),
            binding.projection_byte_length
        )));
    }
    if sha256_hex(&projection_bytes) != binding.projection_sha256 {
        return Err(EngineError::corpus(
            "decision projection plain SHA-256 does not match the corpus binding",
        ));
    }

    let domain = decode_hex(&binding.domain_hex)?;
    let projection_length = u64::try_from(projection_bytes.len())
        .map_err(|_| EngineError::corpus("decision projection length does not fit u64"))?;
    let mut subject = Vec::with_capacity(
        domain
            .len()
            .saturating_add(8)
            .saturating_add(projection_bytes.len()),
    );
    subject.extend_from_slice(&domain);
    subject.extend_from_slice(&projection_length.to_be_bytes());
    subject.extend_from_slice(&projection_bytes);
    if sha256_hex(&subject) != binding.sha256 {
        return Err(EngineError::corpus(
            "domain-separated decision-set SHA-256 does not match the corpus binding",
        ));
    }
    Ok(VerifiedDecisionSet {
        binding: binding.clone(),
        sources,
    })
}

fn build_projection(
    registry: &Value,
    binding: &DecisionSetBinding,
) -> EngineResult<(Value, BTreeMap<String, DecisionSource>)> {
    let registry_object = registry
        .as_object()
        .ok_or_else(|| EngineError::corpus("decision registry root must be an object"))?;
    if registry_object.get("normative") != Some(&Value::Bool(false))
        || registry_object.get("promotion_blocked") != Some(&Value::Bool(true))
    {
        return Err(EngineError::corpus(
            "decision registry must be non-normative and promotion-blocked",
        ));
    }
    let registered_identity = decision_identity(binding);
    if registry_object.get("decision_set") != Some(&registered_identity) {
        return Err(EngineError::corpus(
            "decision registry does not carry the bound identity",
        ));
    }
    let registry_decision_set = registry_object
        .get("decision_set")
        .and_then(Value::as_object)
        .ok_or_else(|| EngineError::corpus("decision registry decision_set must be an object"))?;
    validate_review_packet_binding(registry_object, &registered_identity)?;
    let mut projection = Map::new();
    for member in &binding.projection_members {
        if member == "decisions" {
            continue;
        }
        if member == "schema" {
            projection.insert(member.clone(), Value::String(binding.schema.clone()));
        } else if member == "semantic_closure" {
            let value = registry_decision_set.get(member).ok_or_else(|| {
                EngineError::corpus("decision registry decision_set lacks semantic_closure")
            })?;
            projection.insert(member.clone(), value.clone());
        } else {
            let value = registry_object.get(member).ok_or_else(|| {
                EngineError::corpus(format!("decision registry is missing member {member:?}"))
            })?;
            projection.insert(member.clone(), value.clone());
        }
    }

    let decisions = registry_object
        .get("decisions")
        .and_then(Value::as_array)
        .ok_or_else(|| EngineError::corpus("decision registry decisions must be an array"))?;
    let mut decision_projection = Vec::with_capacity(decisions.len());
    let mut ids = BTreeSet::new();
    let mut sources = BTreeMap::new();
    for (index, decision) in decisions.iter().enumerate() {
        let decision_object = decision.as_object().ok_or_else(|| {
            EngineError::corpus(format!("decision registry entry {index} must be an object"))
        })?;
        let mut selected = Map::new();
        for member in &binding.decision_members {
            let value = decision_object.get(member).ok_or_else(|| {
                EngineError::corpus(format!(
                    "decision registry entry {index} is missing member {member:?}"
                ))
            })?;
            selected.insert(member.clone(), value.clone());
        }
        let id = selected
            .get("id")
            .and_then(Value::as_str)
            .ok_or_else(|| EngineError::corpus("decision id must be a string"))?;
        if !ids.insert(id.to_owned()) {
            return Err(EngineError::corpus(format!("duplicate decision id {id:?}")));
        }
        let path = selected
            .get("path")
            .and_then(Value::as_str)
            .ok_or_else(|| EngineError::corpus("decision path must be a string"))?;
        let byte_length = selected
            .get("bytes")
            .and_then(Value::as_u64)
            .and_then(|value| usize::try_from(value).ok())
            .filter(|value| *value > 0)
            .ok_or_else(|| EngineError::corpus("decision bytes must be a positive integer"))?;
        let sha256 = selected
            .get("content_sha256")
            .and_then(Value::as_str)
            .filter(|digest| {
                digest.len() == 64
                    && digest
                        .bytes()
                        .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
            })
            .ok_or_else(|| {
                EngineError::corpus("decision content SHA-256 must be lowercase hexadecimal")
            })?;
        sources.insert(
            id.to_owned(),
            DecisionSource {
                path: path.to_owned(),
                byte_length,
                sha256: sha256.to_owned(),
            },
        );
        decision_projection.push(Value::Object(selected));
    }
    let expected_ids = (1..=11)
        .map(|number| format!("ADR-{number:03}"))
        .collect::<BTreeSet<_>>();
    if ids != expected_ids {
        return Err(EngineError::corpus(
            "decision registry does not cover exactly ADR-001 through ADR-011",
        ));
    }
    projection.insert("decisions".to_owned(), Value::Array(decision_projection));
    Ok((Value::Object(projection), sources))
}

fn validate_review_packet_binding(
    registry: &Map<String, Value>,
    registered_identity: &Value,
) -> EngineResult<()> {
    let review_records = registry
        .get("review_records")
        .and_then(Value::as_array)
        .ok_or_else(|| EngineError::corpus("review records must be an array"))?;
    let lifecycle = registry
        .get("review_packet_lifecycle")
        .and_then(Value::as_object)
        .ok_or_else(|| EngineError::corpus("review packet lifecycle must be an object"))?;
    if lifecycle.len() != 2
        || lifecycle.get("schema")
            != Some(&Value::String(REVIEW_PACKET_LIFECYCLE_SCHEMA.to_owned()))
    {
        return Err(EngineError::corpus(
            "review packet lifecycle has an invalid schema or member set",
        ));
    }
    let state = lifecycle
        .get("state")
        .and_then(Value::as_str)
        .ok_or_else(|| EngineError::corpus("review packet lifecycle state must be a string"))?;
    match state {
        "CURRENT" => {
            let subject = registry
                .get("review_packet_subject")
                .and_then(Value::as_object)
                .ok_or_else(|| {
                    EngineError::corpus("CURRENT review packet subject must be an object")
                })?;
            if subject.get("decision_set") != Some(registered_identity) {
                return Err(EngineError::corpus(
                    "CURRENT review packet subject does not carry the bound identity",
                ));
            }
        }
        "SUPERSEDED" | "TEMPLATE" => {
            if registry.get("review_packet_subject") != Some(&Value::Null) {
                return Err(EngineError::corpus(
                    "non-current review packet subject must be null",
                ));
            }
            if !review_records.is_empty() {
                return Err(EngineError::corpus(
                    "non-current review packet cannot retain review records",
                ));
            }
        }
        _ => {
            return Err(EngineError::corpus(
                "review packet lifecycle state is not recognized",
            ));
        }
    }
    Ok(())
}

pub(crate) fn review_packet_binding_self_test() -> EngineResult<usize> {
    let registered_identity = serde_json::json!({
        "digest_algorithm": "sha256(domain || u64be(projection_bytes) || projection)",
        "domain_hex": "00",
        "schema": "ncp.b01-decision-set.v1",
        "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    });
    let subject = serde_json::json!({"decision_set": registered_identity.clone()});
    let mismatched_subject = serde_json::json!({
        "decision_set": {
            "digest_algorithm": "sha256(domain || u64be(projection_bytes) || projection)",
            "domain_hex": "00",
            "schema": "ncp.b01-decision-set.v1",
            "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        }
    });
    let mut wrong_schema = review_packet_registry("SUPERSEDED", Value::Null, vec![]);
    lifecycle_mut(&mut wrong_schema)?.insert(
        "schema".to_owned(),
        Value::String("ncp.b01-review-packet-lifecycle.v0".to_owned()),
    );
    let mut extra_member = review_packet_registry("SUPERSEDED", Value::Null, vec![]);
    lifecycle_mut(&mut extra_member)?.insert("unexpected".to_owned(), Value::Bool(false));
    let mut missing_state = review_packet_registry("SUPERSEDED", Value::Null, vec![]);
    lifecycle_mut(&mut missing_state)?.remove("state");
    let mut missing_subject = review_packet_registry("SUPERSEDED", Value::Null, vec![]);
    missing_subject.remove("review_packet_subject");
    let mut missing_records = review_packet_registry("CURRENT", subject.clone(), vec![]);
    missing_records.remove("review_records");
    let controls = [
        validate_review_packet_binding(
            &review_packet_registry("CURRENT", subject.clone(), vec![serde_json::json!({})]),
            &registered_identity,
        )
        .is_ok(),
        validate_review_packet_binding(
            &review_packet_registry("SUPERSEDED", Value::Null, vec![]),
            &registered_identity,
        )
        .is_ok(),
        validate_review_packet_binding(
            &review_packet_registry("TEMPLATE", Value::Null, vec![]),
            &registered_identity,
        )
        .is_ok(),
        validate_review_packet_binding(
            &review_packet_registry("CURRENT", Value::Null, vec![]),
            &registered_identity,
        )
        .is_err(),
        validate_review_packet_binding(
            &review_packet_registry("CURRENT", mismatched_subject, vec![]),
            &registered_identity,
        )
        .is_err(),
        validate_review_packet_binding(
            &review_packet_registry("SUPERSEDED", subject.clone(), vec![]),
            &registered_identity,
        )
        .is_err(),
        validate_review_packet_binding(
            &review_packet_registry("TEMPLATE", subject, vec![]),
            &registered_identity,
        )
        .is_err(),
        validate_review_packet_binding(
            &review_packet_registry("SUPERSEDED", Value::Null, vec![serde_json::json!({})]),
            &registered_identity,
        )
        .is_err(),
        validate_review_packet_binding(
            &review_packet_registry("UNKNOWN", Value::Null, vec![]),
            &registered_identity,
        )
        .is_err(),
        validate_review_packet_binding(&wrong_schema, &registered_identity).is_err(),
        validate_review_packet_binding(&extra_member, &registered_identity).is_err(),
        validate_review_packet_binding(&missing_state, &registered_identity).is_err(),
        validate_review_packet_binding(&missing_subject, &registered_identity).is_err(),
        validate_review_packet_binding(&missing_records, &registered_identity).is_err(),
    ];
    let detected = controls.iter().filter(|detected| **detected).count();
    if detected != controls.len() {
        return Err(EngineError::corpus(format!(
            "review packet binding self-test detected {detected} of {} controls",
            controls.len()
        )));
    }
    Ok(detected)
}

fn review_packet_registry(
    state: &str,
    subject: Value,
    review_records: Vec<Value>,
) -> Map<String, Value> {
    Map::from_iter([
        (
            "review_packet_lifecycle".to_owned(),
            serde_json::json!({
                "schema": REVIEW_PACKET_LIFECYCLE_SCHEMA,
                "state": state
            }),
        ),
        ("review_packet_subject".to_owned(), subject),
        ("review_records".to_owned(), Value::Array(review_records)),
    ])
}

fn lifecycle_mut(registry: &mut Map<String, Value>) -> EngineResult<&mut Map<String, Value>> {
    registry
        .get_mut("review_packet_lifecycle")
        .and_then(Value::as_object_mut)
        .ok_or_else(|| EngineError::corpus("self-test lifecycle fixture is not an object"))
}

fn decision_identity(binding: &DecisionSetBinding) -> Value {
    let mut identity = Map::new();
    identity.insert("schema".to_owned(), Value::String(binding.schema.clone()));
    identity.insert(
        "digest_algorithm".to_owned(),
        Value::String(binding.digest_algorithm.clone()),
    );
    identity.insert(
        "domain_hex".to_owned(),
        Value::String(binding.domain_hex.clone()),
    );
    identity.insert("sha256".to_owned(), Value::String(binding.sha256.clone()));
    identity.insert(
        "semantic_closure".to_owned(),
        binding.semantic_closure.clone(),
    );
    Value::Object(identity)
}

fn decode_hex(value: &str) -> EngineResult<Vec<u8>> {
    if !value.len().is_multiple_of(2) {
        return Err(EngineError::corpus("hex value has odd length"));
    }
    value
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| {
            let high = hex_digit(pair[0])?;
            let low = hex_digit(pair[1])?;
            Ok((high << 4) | low)
        })
        .collect()
}

fn hex_digit(byte: u8) -> EngineResult<u8> {
    match byte {
        b'0'..=b'9' => Ok(byte - b'0'),
        b'a'..=b'f' => Ok(byte - b'a' + 10),
        _ => Err(EngineError::corpus(
            "hex value must use lowercase hexadecimal characters",
        )),
    }
}

#[cfg(test)]
mod tests {
    use super::decode_hex;

    #[test]
    fn decode_hex_should_reject_uppercase_and_odd_length() {
        assert_eq!(decode_hex("00ff").ok(), Some(vec![0, 255]));
        assert!(decode_hex("0").is_err());
        assert!(decode_hex("AA").is_err());
    }
}
