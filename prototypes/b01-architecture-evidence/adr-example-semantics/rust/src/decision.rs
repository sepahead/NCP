use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

use serde_json::{Map, Value};

use crate::error::{EngineError, EngineResult};
use crate::model::{Corpus, DecisionSetBinding, Source};
use crate::sha256::sha256_hex;
use crate::source::{read_bounded, resolve_regular_relative_file};
use crate::strict_json::{canonicalize, parse_strict};

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
    if registry_object.get("decision_set") != Some(&registered_identity)
        || registry.pointer("/review_packet_subject/decision_set") != Some(&registered_identity)
    {
        return Err(EngineError::corpus(
            "decision registry and review subject do not carry the bound identity",
        ));
    }
    let mut projection = Map::new();
    for member in &binding.projection_members {
        if member == "decisions" {
            continue;
        }
        if member == "schema" {
            projection.insert(member.clone(), Value::String(binding.schema.clone()));
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
