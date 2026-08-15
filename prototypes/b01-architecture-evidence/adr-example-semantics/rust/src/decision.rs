use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

use serde_json::{Map, Value};

use crate::error::{EngineError, EngineResult};
use crate::model::{Corpus, DecisionSetBinding, Source};
use crate::sha256::sha256_hex;
use crate::source::{read_bounded, resolve_regular_relative_file};
use crate::strict_json::parse_strict;

const REVIEW_PACKET_LIFECYCLE_SCHEMA: &str = "ncp.b01-review-packet-lifecycle.v1";
const ADR_SOURCE_SET_SCHEMA: &str = "ncp.b01-adr-source-set.v1";
const ADR_SOURCE_SET_DIGEST_ALGORITHM: &str =
    "sha256(domain || u64be(projection_bytes) || projection)";
const ADR_SOURCE_SET_DOMAIN_HEX: &str = "6e63702e6230312d6164722d736f757263652d7365742e763100";
const MAXIMUM_ADR_MODULES_PER_DECISION: usize = 8;

pub(crate) struct VerifiedDecisionSet {
    pub(crate) binding: DecisionSetBinding,
    sources: BTreeMap<String, DecisionSource>,
}

#[derive(Clone)]
pub(crate) struct DecisionSource {
    pub(crate) path: String,
    pub(crate) byte_length: usize,
    pub(crate) sha256: String,
}

impl VerifiedDecisionSet {
    pub(crate) fn source(&self, source: &Source) -> EngineResult<&DecisionSource> {
        self.sources.get(&source.adr).ok_or_else(|| {
            EngineError::corpus(format!(
                "case source uses a decision id absent from the bound registry: {:?}",
                source.adr
            ))
        })
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
    let (projection, sources, all_sources) =
        build_projection(&registry, binding, corpus.limits.maximum_adr_bytes)?;
    verify_bound_artifact(
        root,
        &binding.semantic_closure,
        "source",
        &binding.registry_path,
        corpus.limits.maximum_corpus_bytes,
    )?;
    verify_bound_artifact(
        root,
        &binding.semantic_closure,
        "json_schema",
        &binding.registry_path,
        corpus.limits.maximum_corpus_bytes,
    )?;
    verify_projected_sources(
        root,
        &all_sources,
        corpus.limits.maximum_aggregate_adr_bytes,
    )?;
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
    maximum_source_bytes: usize,
) -> EngineResult<(Value, BTreeMap<String, DecisionSource>, Vec<DecisionSource>)> {
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
    let mut all_sources = Vec::new();
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
        if byte_length > maximum_source_bytes {
            return Err(EngineError::corpus(
                "decision source exceeds the individual ADR byte bound",
            ));
        }
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
        let main_source = DecisionSource {
            path: path.to_owned(),
            byte_length,
            sha256: sha256.to_owned(),
        };
        sources.insert(id.to_owned(), main_source.clone());
        validate_source_set(
            selected.get("source_set"),
            selected.get("module_paths"),
            id,
            &main_source,
            maximum_source_bytes,
            &mut all_sources,
        )?;
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
    Ok((Value::Object(projection), sources, all_sources))
}

fn valid_kebab_markdown_path(path: &str, prefix: &str) -> bool {
    let Some(slug) = path
        .strip_prefix(prefix)
        .and_then(|value| value.strip_suffix(".md"))
    else {
        return false;
    };
    !slug.is_empty()
        && slug.split('-').all(|segment| {
            !segment.is_empty()
                && segment
                    .bytes()
                    .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit())
        })
}

fn valid_main_adr_path(path: &str, decision_number: u16) -> bool {
    valid_kebab_markdown_path(path, &format!("docs/adr/{decision_number:04}-"))
}

fn valid_module_adr_path(path: &str, decision_id: &str) -> bool {
    valid_kebab_markdown_path(
        path,
        &format!("docs/adr/modules/{}-", decision_id.to_ascii_lowercase()),
    )
}

fn validate_source_set(
    value: Option<&Value>,
    module_paths_value: Option<&Value>,
    decision_id: &str,
    main_source: &DecisionSource,
    maximum_source_bytes: usize,
    all_sources: &mut Vec<DecisionSource>,
) -> EngineResult<()> {
    let source_set = value
        .and_then(Value::as_object)
        .ok_or_else(|| EngineError::corpus("decision source_set must be an object"))?;
    let entries = source_set
        .get("sources")
        .and_then(Value::as_array)
        .ok_or_else(|| EngineError::corpus("decision source_set sources must be an array"))?;
    let expected_members = BTreeSet::from([
        "decision_id",
        "digest_algorithm",
        "domain_hex",
        "schema",
        "sha256",
        "sources",
    ]);
    let actual_members = source_set
        .keys()
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    if actual_members != expected_members
        || source_set.get("schema").and_then(Value::as_str) != Some(ADR_SOURCE_SET_SCHEMA)
        || source_set.get("decision_id").and_then(Value::as_str) != Some(decision_id)
        || source_set.get("digest_algorithm").and_then(Value::as_str)
            != Some(ADR_SOURCE_SET_DIGEST_ALGORITHM)
        || source_set.get("domain_hex").and_then(Value::as_str) != Some(ADR_SOURCE_SET_DOMAIN_HEX)
        || entries.is_empty()
        || entries.len() > MAXIMUM_ADR_MODULES_PER_DECISION + 1
    {
        return Err(EngineError::corpus(
            "decision source_set has an invalid identity or cardinality",
        ));
    }
    let module_paths = module_paths_value
        .and_then(Value::as_array)
        .ok_or_else(|| EngineError::corpus("decision module_paths must be an array"))?;
    if module_paths.len() + 1 != entries.len() {
        return Err(EngineError::corpus(
            "decision module_paths differs from its source_set cardinality",
        ));
    }
    let decision_number = decision_id
        .strip_prefix("ADR-")
        .and_then(|value| value.parse::<u16>().ok())
        .ok_or_else(|| EngineError::corpus("decision id is not canonical"))?;
    let mut paths = BTreeSet::new();
    for (index, entry) in entries.iter().enumerate() {
        let entry = entry
            .as_object()
            .ok_or_else(|| EngineError::corpus("source_set entry must be an object"))?;
        if entry.len() != 4
            || entry.get("kind").and_then(Value::as_str)
                != Some(if index == 0 { "main" } else { "module" })
        {
            return Err(EngineError::corpus(
                "source_set entry has an invalid member set or kind",
            ));
        }
        let path = entry
            .get("path")
            .and_then(Value::as_str)
            .ok_or_else(|| EngineError::corpus("source_set path must be a string"))?;
        let byte_length = entry
            .get("bytes")
            .and_then(Value::as_u64)
            .and_then(|value| usize::try_from(value).ok())
            .filter(|value| *value > 0)
            .ok_or_else(|| EngineError::corpus("source_set bytes must be positive"))?;
        if byte_length > maximum_source_bytes {
            return Err(EngineError::corpus(
                "source_set entry exceeds the individual ADR byte bound",
            ));
        }
        let sha256 = entry
            .get("sha256")
            .and_then(Value::as_str)
            .filter(|value| valid_sha256(value))
            .ok_or_else(|| EngineError::corpus("source_set SHA-256 is invalid"))?;
        if !paths.insert(path) {
            return Err(EngineError::corpus("source_set paths must be unique"));
        }
        if index == 0 {
            if !valid_main_adr_path(path, decision_number)
                || path != main_source.path
                || byte_length != main_source.byte_length
                || sha256 != main_source.sha256
            {
                return Err(EngineError::corpus(
                    "source_set main entry differs from the decision identity",
                ));
            }
        } else {
            if !valid_module_adr_path(path, decision_id) {
                return Err(EngineError::corpus(
                    "source_set module path is outside the decision namespace",
                ));
            }
            if module_paths.get(index - 1).and_then(Value::as_str) != Some(path) {
                return Err(EngineError::corpus(
                    "decision module_paths differs from its source_set",
                ));
            }
        }
        all_sources.push(DecisionSource {
            path: path.to_owned(),
            byte_length,
            sha256: sha256.to_owned(),
        });
    }
    let projection = serde_json::json!({
        "schema": ADR_SOURCE_SET_SCHEMA,
        "decision_id": decision_id,
        "sources": entries,
    });
    let projection_bytes = serde_json::to_vec(&projection).map_err(|error| {
        EngineError::json(format!(
            "serializing canonical ADR source-set projection: {error}"
        ))
    })?;
    let projection_length = u64::try_from(projection_bytes.len())
        .map_err(|_| EngineError::corpus("ADR source-set projection length does not fit u64"))?;
    let domain = decode_hex(ADR_SOURCE_SET_DOMAIN_HEX)?;
    let mut subject = Vec::with_capacity(domain.len() + 8 + projection_bytes.len());
    subject.extend_from_slice(&domain);
    subject.extend_from_slice(&projection_length.to_be_bytes());
    subject.extend_from_slice(&projection_bytes);
    let declared_digest = source_set
        .get("sha256")
        .and_then(Value::as_str)
        .filter(|value| valid_sha256(value))
        .ok_or_else(|| EngineError::corpus("source_set commitment is invalid"))?;
    if sha256_hex(&subject) != declared_digest {
        return Err(EngineError::corpus(
            "source_set commitment does not recompute",
        ));
    }
    Ok(())
}

fn verify_bound_artifact(
    root: &Path,
    semantic_closure: &Value,
    member: &str,
    registry_path: &str,
    maximum_bytes: usize,
) -> EngineResult<()> {
    let identity = semantic_closure
        .get(member)
        .and_then(Value::as_object)
        .ok_or_else(|| EngineError::corpus("semantic closure identity must be an object"))?;
    let source = decision_source(identity)?;
    if source.path == registry_path {
        return Err(EngineError::corpus(
            "semantic closure artifact cannot alias the registry",
        ));
    }
    if source.byte_length > maximum_bytes {
        return Err(EngineError::corpus(
            "semantic closure artifact exceeds its registered byte bound",
        ));
    }
    verify_projected_source(root, &source)
}

fn verify_projected_sources(
    root: &Path,
    sources: &[DecisionSource],
    maximum_aggregate_bytes: usize,
) -> EngineResult<()> {
    let mut seen = BTreeSet::new();
    let mut aggregate = 0_usize;
    for source in sources {
        if !seen.insert(source.path.as_str()) {
            return Err(EngineError::corpus("projected source path is duplicate"));
        }
        aggregate = aggregate
            .checked_add(source.byte_length)
            .ok_or_else(|| EngineError::corpus("projected source byte count overflow"))?;
        if aggregate > maximum_aggregate_bytes {
            return Err(EngineError::corpus(
                "projected sources exceed the aggregate ADR byte bound",
            ));
        }
        verify_projected_source(root, source)?;
    }
    Ok(())
}

fn verify_projected_source(root: &Path, source: &DecisionSource) -> EngineResult<()> {
    let path = resolve_regular_relative_file(root, &source.path)?;
    let bytes = read_bounded(&path, source.byte_length)?;
    if bytes.len() != source.byte_length || sha256_hex(&bytes) != source.sha256 {
        return Err(EngineError::corpus(format!(
            "projected source {:?} differs from its decision binding",
            source.path
        )));
    }
    Ok(())
}

fn decision_source(identity: &Map<String, Value>) -> EngineResult<DecisionSource> {
    if identity.len() != 3 {
        return Err(EngineError::corpus(
            "artifact identity has an unexpected member set",
        ));
    }
    let path = identity
        .get("path")
        .and_then(Value::as_str)
        .ok_or_else(|| EngineError::corpus("artifact path must be a string"))?;
    let byte_length = identity
        .get("bytes")
        .and_then(Value::as_u64)
        .and_then(|value| usize::try_from(value).ok())
        .filter(|value| *value > 0)
        .ok_or_else(|| EngineError::corpus("artifact bytes must be positive"))?;
    let sha256 = identity
        .get("sha256")
        .and_then(Value::as_str)
        .filter(|value| valid_sha256(value))
        .ok_or_else(|| EngineError::corpus("artifact SHA-256 is invalid"))?;
    Ok(DecisionSource {
        path: path.to_owned(),
        byte_length,
        sha256: sha256.to_owned(),
    })
}

fn valid_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
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
            if subject.len() != 1 || subject.get("decision_set") != Some(registered_identity) {
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
    let mut extra_subject_member = review_packet_registry("CURRENT", subject.clone(), vec![]);
    extra_subject_member
        .get_mut("review_packet_subject")
        .and_then(Value::as_object_mut)
        .ok_or_else(|| EngineError::corpus("self-test review subject is not an object"))?
        .insert("unexpected".to_owned(), Value::Bool(false));
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
        validate_review_packet_binding(&extra_member, &registered_identity).is_err()
            && validate_review_packet_binding(&extra_subject_member, &registered_identity).is_err(),
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
    use super::{decode_hex, valid_main_adr_path, valid_module_adr_path};

    #[test]
    fn decision_binding_helpers_should_reject_noncanonical_input() {
        assert_eq!(decode_hex("00ff").ok(), Some(vec![0, 255]));
        assert!(decode_hex("0").is_err());
        assert!(decode_hex("AA").is_err());
        assert!(valid_main_adr_path("docs/adr/0001-canonical-main.md", 1));
        assert!(!valid_main_adr_path("docs/adr/0001-nested/subject.md", 1));
        assert!(!valid_main_adr_path("docs/adr/0001-double--hyphen.md", 1));
        assert!(!valid_main_adr_path("docs/adr/0001-wrong-decision.md", 2));
        assert!(valid_module_adr_path(
            "docs/adr/modules/adr-004-canonical-module.md",
            "ADR-004"
        ));
        assert!(!valid_module_adr_path(
            "docs/adr/modules/adr-004-nested/subject.md",
            "ADR-004"
        ));
        assert!(!valid_module_adr_path(
            "docs/adr/modules/adr-004-double--hyphen.md",
            "ADR-004"
        ));
        assert!(!valid_module_adr_path(
            "docs/adr/modules/adr-004-wrong-decision.md",
            "ADR-009"
        ));
    }
}
