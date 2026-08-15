use serde_json::Value;

use crate::error::{EngineError, EngineResult};
use crate::model::{validate_patch_path, Patch, PatchOperation};

pub(crate) fn apply_patch(target: &mut Value, patch: &Patch) -> EngineResult<()> {
    validate_patch_path(&patch.path)?;
    let tokens = decode_pointer(&patch.path)?;
    if tokens.is_empty() {
        return apply_at_root(target, patch);
    }
    let (last, parents) = tokens
        .split_last()
        .ok_or_else(|| EngineError::semantic("non-empty JSON Pointer lost its final token"))?;
    let mut parent = target;
    for token in parents {
        parent = descend(parent, token)?;
    }
    apply_at_parent(parent, last, patch)
}

fn apply_at_root(target: &mut Value, patch: &Patch) -> EngineResult<()> {
    let _ = target;
    let _ = patch;
    Err(EngineError::corpus(
        "mutating the complete document or fixture is forbidden",
    ))
}

fn descend<'value>(value: &'value mut Value, token: &str) -> EngineResult<&'value mut Value> {
    match value {
        Value::Object(object) => object.get_mut(token).ok_or_else(|| {
            EngineError::corpus(format!(
                "JSON Pointer parent member {token:?} does not exist"
            ))
        }),
        Value::Array(array) => {
            let index = parse_array_index(token, false)?;
            array.get_mut(index).ok_or_else(|| {
                EngineError::corpus(format!("JSON Pointer parent index {index} does not exist"))
            })
        }
        Value::Null | Value::Bool(_) | Value::Number(_) | Value::String(_) => Err(
            EngineError::corpus("JSON Pointer traverses through a scalar value"),
        ),
    }
}

fn apply_at_parent(parent: &mut Value, token: &str, patch: &Patch) -> EngineResult<()> {
    match parent {
        Value::Object(object) => match patch.op {
            PatchOperation::Add => {
                let value = patch
                    .value
                    .as_ref()
                    .ok_or_else(|| EngineError::corpus("ADD patch is missing value"))?;
                if object.contains_key(token) {
                    return Err(EngineError::corpus(format!(
                        "ADD target member {token:?} already exists"
                    )));
                }
                object.insert(token.to_owned(), value.clone());
                Ok(())
            }
            PatchOperation::Remove => object.remove(token).map_or_else(
                || {
                    Err(EngineError::corpus(format!(
                        "REMOVE target member {token:?} does not exist"
                    )))
                },
                |_| Ok(()),
            ),
            PatchOperation::Replace => {
                let value = patch
                    .value
                    .as_ref()
                    .ok_or_else(|| EngineError::corpus("REPLACE patch is missing value"))?;
                let slot = object.get_mut(token).ok_or_else(|| {
                    EngineError::corpus(format!("REPLACE target member {token:?} does not exist"))
                })?;
                *slot = value.clone();
                Ok(())
            }
        },
        Value::Array(array) => match patch.op {
            PatchOperation::Add => {
                let value = patch
                    .value
                    .as_ref()
                    .ok_or_else(|| EngineError::corpus("ADD patch is missing value"))?;
                if token == "-" {
                    array.push(value.clone());
                    return Ok(());
                }
                let index = parse_array_index(token, false)?;
                if index > array.len() {
                    return Err(EngineError::corpus(format!(
                        "ADD target index {index} exceeds array length {}",
                        array.len()
                    )));
                }
                array.insert(index, value.clone());
                Ok(())
            }
            PatchOperation::Remove => {
                let index = parse_array_index(token, false)?;
                if index >= array.len() {
                    return Err(EngineError::corpus(format!(
                        "REMOVE target index {index} does not exist"
                    )));
                }
                array.remove(index);
                Ok(())
            }
            PatchOperation::Replace => {
                let index = parse_array_index(token, false)?;
                let value = patch
                    .value
                    .as_ref()
                    .ok_or_else(|| EngineError::corpus("REPLACE patch is missing value"))?;
                let slot = array.get_mut(index).ok_or_else(|| {
                    EngineError::corpus(format!("REPLACE target index {index} does not exist"))
                })?;
                *slot = value.clone();
                Ok(())
            }
        },
        Value::Null | Value::Bool(_) | Value::Number(_) | Value::String(_) => Err(
            EngineError::corpus("JSON Pointer final parent is a scalar value"),
        ),
    }
}

fn decode_pointer(pointer: &str) -> EngineResult<Vec<String>> {
    if pointer.is_empty() {
        return Ok(Vec::new());
    }
    let tail = pointer.strip_prefix('/').ok_or_else(|| {
        EngineError::corpus(format!(
            "JSON Pointer must be empty or begin with '/': {pointer:?}"
        ))
    })?;
    tail.split('/').map(decode_pointer_token).collect()
}

fn decode_pointer_token(token: &str) -> EngineResult<String> {
    let mut decoded = String::with_capacity(token.len());
    let mut characters = token.chars();
    while let Some(character) = characters.next() {
        if character != '~' {
            decoded.push(character);
            continue;
        }
        match characters.next() {
            Some('0') => decoded.push('~'),
            Some('1') => decoded.push('/'),
            Some(other) => {
                return Err(EngineError::corpus(format!(
                    "invalid JSON Pointer escape ~{other}"
                )));
            }
            None => return Err(EngineError::corpus("truncated JSON Pointer escape")),
        }
    }
    Ok(decoded)
}

fn parse_array_index(token: &str, allow_dash: bool) -> EngineResult<usize> {
    if allow_dash && token == "-" {
        return Err(EngineError::semantic(
            "dash array index must be handled by the ADD operation",
        ));
    }
    if token.is_empty()
        || (token.len() > 1 && token.starts_with('0'))
        || !token.bytes().all(|byte| byte.is_ascii_digit())
    {
        return Err(EngineError::corpus(format!(
            "array index is not canonical: {token:?}"
        )));
    }
    token
        .parse::<usize>()
        .map_err(|error| EngineError::corpus(format!("array index is out of range: {error}")))
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use crate::model::{Patch, PatchOperation, PatchTarget};

    use super::apply_patch;

    fn patch(op: PatchOperation, path: &str, value: Option<Value>) -> Patch {
        Patch {
            target: PatchTarget::Document,
            op,
            path: path.to_owned(),
            value,
        }
    }

    use serde_json::Value;

    #[test]
    fn apply_patch_should_decode_pointer_and_apply_one_operation() {
        let mut value = json!({"a/b": {"~key": [1]}});
        let operation = patch(PatchOperation::Add, "/a~1b/~0key/-", Some(json!(2)));
        assert!(apply_patch(&mut value, &operation).is_ok());
        assert_eq!(value, json!({"a/b": {"~key": [1, 2]}}));
    }

    #[test]
    fn apply_patch_should_reject_missing_replace_and_noncanonical_array_index() {
        let mut value = json!({"array": [1]});
        let missing = patch(PatchOperation::Replace, "/missing", Some(json!(2)));
        assert!(apply_patch(&mut value, &missing).is_err());
        let index = patch(PatchOperation::Remove, "/array/00", None);
        assert!(apply_patch(&mut value, &index).is_err());
    }

    #[test]
    fn apply_patch_should_reject_root_mutation_and_existing_object_add() {
        let mut value = json!({"existing": 1});
        let root = patch(PatchOperation::Replace, "", Some(json!({"other": 2})));
        assert!(apply_patch(&mut value, &root).is_err());
        let oversized = patch(
            PatchOperation::Remove,
            &format!("/{}", "x".repeat(512)),
            None,
        );
        assert!(apply_patch(&mut value, &oversized).is_err());
        let existing = patch(PatchOperation::Add, "/existing", Some(json!(2)));
        assert!(apply_patch(&mut value, &existing).is_err());
        assert_eq!(value, json!({"existing": 1}));
    }
}
