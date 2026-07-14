//! Universal bounded-JSON preflight for every NCP 1.0 ingress.
//!
//! `serde_json` correctly rejects malformed JSON, but its default `Value` decoder
//! accepts duplicate object keys (last value wins) and only discovers aggregate
//! resource use while allocating. NCP runs this bounded structural pass before
//! semantic decoding so every transport and FFI entry point shares one rejection
//! boundary. The limits mirror `contract/limits.v1.json` and are intentionally
//! constants rather than deployment knobs: changing one changes the contract.

use serde_json::Value;
use std::collections::HashSet;
use std::fmt;

pub const MAX_FRAME_BYTES: usize = 1_048_576;
pub const MAX_NESTING_DEPTH: usize = 32;
pub const MAX_OBJECTS: usize = 4_096;
pub const MAX_ARRAYS: usize = 4_096;
pub const MAX_TOTAL_MEMBERS: usize = 16_384;
pub const MAX_TOTAL_ARRAY_ITEMS: usize = 262_144;
pub const MAX_OBJECT_MEMBERS: usize = 4_096;
pub const MAX_ARRAY_ITEMS: usize = 65_536;
pub const MAX_KEY_BYTES: usize = 128;
pub const MAX_STRING_BYTES: usize = 65_536;
pub const MAX_TOTAL_STRING_BYTES: usize = 1_048_576;
pub const MAX_FINITE_NUMBER_MAGNITUDE: f64 = 1e300;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum JsonLimitCode {
    FrameBytes,
    NestingDepth,
    ObjectBudget,
    ArrayBudget,
    StringBudget,
    NumericBudget,
    DuplicateKey,
    InvalidUnicode,
    Malformed,
}

impl JsonLimitCode {
    pub const fn stable_code(self) -> &'static str {
        match self {
            Self::FrameBytes => "NCP-LIMIT-001",
            Self::NestingDepth => "NCP-LIMIT-002",
            Self::ObjectBudget => "NCP-LIMIT-003",
            Self::ArrayBudget => "NCP-LIMIT-004",
            Self::StringBudget => "NCP-LIMIT-005",
            Self::NumericBudget => "NCP-LIMIT-006",
            Self::DuplicateKey => "NCP-LIMIT-007",
            Self::InvalidUnicode => "NCP-LIMIT-008",
            Self::Malformed => "NCP-LIMIT-009",
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct BoundedJsonError {
    pub code: JsonLimitCode,
    pub offset: usize,
    pub detail: &'static str,
}

impl fmt::Display for BoundedJsonError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "{} at byte {}: {}",
            self.code.stable_code(),
            self.offset,
            self.detail
        )
    }
}

impl std::error::Error for BoundedJsonError {}

#[derive(Default)]
struct Counts {
    objects: usize,
    arrays: usize,
    members: usize,
    array_items: usize,
    string_bytes: usize,
}

struct Scanner<'a> {
    input: &'a [u8],
    position: usize,
    counts: Counts,
}

impl<'a> Scanner<'a> {
    fn error(&self, code: JsonLimitCode, detail: &'static str) -> BoundedJsonError {
        BoundedJsonError {
            code,
            offset: self.position,
            detail,
        }
    }

    fn skip_whitespace(&mut self) {
        while self
            .input
            .get(self.position)
            .is_some_and(|byte| matches!(byte, b' ' | b'\n' | b'\r' | b'\t'))
        {
            self.position += 1;
        }
    }

    fn expect(&mut self, expected: u8) -> Result<(), BoundedJsonError> {
        if self.input.get(self.position) != Some(&expected) {
            return Err(self.error(JsonLimitCode::Malformed, "unexpected token"));
        }
        self.position += 1;
        Ok(())
    }

    fn parse_value(&mut self, depth: usize) -> Result<(), BoundedJsonError> {
        self.skip_whitespace();
        if depth > MAX_NESTING_DEPTH {
            return Err(self.error(JsonLimitCode::NestingDepth, "JSON nesting depth exceeded"));
        }
        match self.input.get(self.position).copied() {
            Some(b'{') => self.parse_object(depth + 1),
            Some(b'[') => self.parse_array(depth + 1),
            Some(b'"') => self.parse_string(false).map(drop),
            Some(b't') => self.parse_literal(b"true"),
            Some(b'f') => self.parse_literal(b"false"),
            Some(b'n') => self.parse_literal(b"null"),
            Some(b'-' | b'0'..=b'9') => self.parse_number(),
            _ => Err(self.error(JsonLimitCode::Malformed, "expected a JSON value")),
        }
    }

    fn parse_literal(&mut self, literal: &[u8]) -> Result<(), BoundedJsonError> {
        let end = self.position.saturating_add(literal.len());
        if self.input.get(self.position..end) != Some(literal) {
            return Err(self.error(JsonLimitCode::Malformed, "invalid JSON literal"));
        }
        self.position = end;
        Ok(())
    }

    fn parse_number(&mut self) -> Result<(), BoundedJsonError> {
        let start = self.position;
        while self
            .input
            .get(self.position)
            .is_some_and(|byte| matches!(byte, b'0'..=b'9' | b'-' | b'+' | b'.' | b'e' | b'E'))
        {
            self.position += 1;
        }
        let number: serde_json::Number = serde_json::from_slice(&self.input[start..self.position])
            .map_err(|_| self.error(JsonLimitCode::Malformed, "invalid JSON number"))?;
        let value = number
            .as_f64()
            .ok_or_else(|| self.error(JsonLimitCode::NumericBudget, "number is not finite"))?;
        if !value.is_finite() || value.abs() > MAX_FINITE_NUMBER_MAGNITUDE {
            return Err(self.error(
                JsonLimitCode::NumericBudget,
                "number exceeds the finite magnitude budget",
            ));
        }
        Ok(())
    }

    fn parse_string(&mut self, key: bool) -> Result<String, BoundedJsonError> {
        let start = self.position;
        self.expect(b'"')?;
        let mut escaped = false;
        loop {
            let Some(byte) = self.input.get(self.position).copied() else {
                return Err(self.error(JsonLimitCode::Malformed, "unterminated JSON string"));
            };
            self.position += 1;
            if escaped {
                escaped = false;
                continue;
            }
            match byte {
                b'\\' => escaped = true,
                b'"' => break,
                0x00..=0x1f => {
                    return Err(self.error(
                        JsonLimitCode::InvalidUnicode,
                        "unescaped control byte in JSON string",
                    ))
                }
                _ => {}
            }
        }
        let decoded: String =
            serde_json::from_slice(&self.input[start..self.position]).map_err(|_| {
                self.error(
                    JsonLimitCode::InvalidUnicode,
                    "invalid JSON string or Unicode",
                )
            })?;
        let limit = if key { MAX_KEY_BYTES } else { MAX_STRING_BYTES };
        if decoded.len() > limit {
            return Err(self.error(
                JsonLimitCode::StringBudget,
                "JSON string exceeds byte limit",
            ));
        }
        self.counts.string_bytes = self
            .counts
            .string_bytes
            .checked_add(decoded.len())
            .ok_or_else(|| self.error(JsonLimitCode::StringBudget, "string budget overflow"))?;
        if self.counts.string_bytes > MAX_TOTAL_STRING_BYTES {
            return Err(self.error(
                JsonLimitCode::StringBudget,
                "aggregate JSON string budget exceeded",
            ));
        }
        Ok(decoded)
    }

    fn parse_object(&mut self, depth: usize) -> Result<(), BoundedJsonError> {
        if depth > MAX_NESTING_DEPTH {
            return Err(self.error(JsonLimitCode::NestingDepth, "JSON nesting depth exceeded"));
        }
        self.counts.objects += 1;
        if self.counts.objects > MAX_OBJECTS {
            return Err(self.error(JsonLimitCode::ObjectBudget, "object count exceeded"));
        }
        self.expect(b'{')?;
        self.skip_whitespace();
        if self.input.get(self.position) == Some(&b'}') {
            self.position += 1;
            return Ok(());
        }
        let mut keys = HashSet::new();
        loop {
            self.skip_whitespace();
            let key = self.parse_string(true)?;
            if !keys.insert(key) {
                return Err(self.error(JsonLimitCode::DuplicateKey, "duplicate JSON object key"));
            }
            self.counts.members += 1;
            if keys.len() > MAX_OBJECT_MEMBERS || self.counts.members > MAX_TOTAL_MEMBERS {
                return Err(
                    self.error(JsonLimitCode::ObjectBudget, "object member budget exceeded")
                );
            }
            self.skip_whitespace();
            self.expect(b':')?;
            self.parse_value(depth)?;
            self.skip_whitespace();
            match self.input.get(self.position) {
                Some(b',') => self.position += 1,
                Some(b'}') => {
                    self.position += 1;
                    return Ok(());
                }
                _ => return Err(self.error(JsonLimitCode::Malformed, "expected ',' or '}'")),
            }
        }
    }

    fn parse_array(&mut self, depth: usize) -> Result<(), BoundedJsonError> {
        if depth > MAX_NESTING_DEPTH {
            return Err(self.error(JsonLimitCode::NestingDepth, "JSON nesting depth exceeded"));
        }
        self.counts.arrays += 1;
        if self.counts.arrays > MAX_ARRAYS {
            return Err(self.error(JsonLimitCode::ArrayBudget, "array count exceeded"));
        }
        self.expect(b'[')?;
        self.skip_whitespace();
        if self.input.get(self.position) == Some(&b']') {
            self.position += 1;
            return Ok(());
        }
        let mut local_items = 0usize;
        loop {
            local_items += 1;
            self.counts.array_items += 1;
            if local_items > MAX_ARRAY_ITEMS || self.counts.array_items > MAX_TOTAL_ARRAY_ITEMS {
                return Err(self.error(JsonLimitCode::ArrayBudget, "array item budget exceeded"));
            }
            self.parse_value(depth)?;
            self.skip_whitespace();
            match self.input.get(self.position) {
                Some(b',') => self.position += 1,
                Some(b']') => {
                    self.position += 1;
                    return Ok(());
                }
                _ => return Err(self.error(JsonLimitCode::Malformed, "expected ',' or ']'")),
            }
        }
    }
}

/// Verify all universal budgets without constructing the message value.
pub fn preflight(input: &[u8]) -> Result<(), BoundedJsonError> {
    if input.len() > MAX_FRAME_BYTES {
        return Err(BoundedJsonError {
            code: JsonLimitCode::FrameBytes,
            offset: MAX_FRAME_BYTES,
            detail: "JSON frame byte limit exceeded",
        });
    }
    let mut scanner = Scanner {
        input,
        position: 0,
        counts: Counts::default(),
    };
    scanner.parse_value(0)?;
    scanner.skip_whitespace();
    if scanner.position != input.len() {
        return Err(scanner.error(JsonLimitCode::Malformed, "trailing bytes after JSON value"));
    }
    Ok(())
}

/// Preflight and then decode exactly once into a `serde_json::Value`.
pub fn parse_value(input: &[u8]) -> Result<Value, BoundedJsonError> {
    preflight(input)?;
    serde_json::from_slice(input).map_err(|_| BoundedJsonError {
        code: JsonLimitCode::Malformed,
        offset: 0,
        detail: "JSON decode failed after structural preflight",
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_duplicate_keys_before_semantic_decode() {
        let error = parse_value(br#"{"kind":"command_frame","kind":"sensor_frame"}"#)
            .expect_err("duplicate keys are ambiguous across implementations");
        assert_eq!(error.code, JsonLimitCode::DuplicateKey);
    }

    #[test]
    fn enforces_depth_string_number_and_frame_boundaries() {
        let at_depth = format!(
            "{}0{}",
            "[".repeat(MAX_NESTING_DEPTH),
            "]".repeat(MAX_NESTING_DEPTH)
        );
        assert!(preflight(at_depth.as_bytes()).is_ok());
        let over_depth = format!(
            "{}0{}",
            "[".repeat(MAX_NESTING_DEPTH + 1),
            "]".repeat(MAX_NESTING_DEPTH + 1)
        );
        assert_eq!(
            preflight(over_depth.as_bytes()).unwrap_err().code,
            JsonLimitCode::NestingDepth
        );

        let at_string = serde_json::to_vec(&"x".repeat(MAX_STRING_BYTES)).unwrap();
        assert!(preflight(&at_string).is_ok());
        let over_string = serde_json::to_vec(&"x".repeat(MAX_STRING_BYTES + 1)).unwrap();
        assert_eq!(
            preflight(&over_string).unwrap_err().code,
            JsonLimitCode::StringBudget
        );
        assert_eq!(
            preflight(b"1e301").unwrap_err().code,
            JsonLimitCode::NumericBudget
        );
        assert_eq!(
            preflight(&vec![b' '; MAX_FRAME_BYTES + 1])
                .unwrap_err()
                .code,
            JsonLimitCode::FrameBytes
        );
    }

    #[test]
    fn escaped_key_identity_is_compared_after_decoding() {
        let error = preflight(br#"{"a":1,"\u0061":2}"#).unwrap_err();
        assert_eq!(error.code, JsonLimitCode::DuplicateKey);
    }
}
