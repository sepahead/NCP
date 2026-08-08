use std::collections::BTreeMap;

use serde_json::{Map, Number, Value};

use crate::error::{EngineError, EngineResult};

const MAX_LANGUAGE_NEUTRAL_INTEGER: u64 = 9_007_199_254_740_991;

#[derive(Clone, Copy, Debug)]
pub(crate) struct JsonLimits {
    pub(crate) maximum_input_bytes: usize,
    pub(crate) maximum_json_depth: usize,
    pub(crate) maximum_json_nodes: usize,
    pub(crate) maximum_object_members: usize,
    pub(crate) maximum_array_items: usize,
    pub(crate) maximum_key_utf8_bytes: usize,
    pub(crate) maximum_string_utf8_bytes: usize,
    pub(crate) maximum_total_string_utf8_bytes: usize,
    pub(crate) maximum_integer_characters: usize,
    pub(crate) allow_floats: bool,
}

impl JsonLimits {
    pub(crate) const fn corpus_bootstrap() -> Self {
        Self {
            maximum_input_bytes: 262_144,
            maximum_json_depth: 32,
            maximum_json_nodes: 100_000,
            maximum_object_members: 4_096,
            maximum_array_items: 4_096,
            maximum_key_utf8_bytes: 256,
            maximum_string_utf8_bytes: 65_536,
            maximum_total_string_utf8_bytes: 131_072,
            maximum_integer_characters: 32,
            allow_floats: false,
        }
    }
}

pub(crate) fn parse_strict(input: &[u8], limits: JsonLimits) -> EngineResult<Value> {
    if input.is_empty() {
        return Err(EngineError::json("input is empty"));
    }
    if input.len() > limits.maximum_input_bytes {
        return Err(EngineError::json(format!(
            "input has {} bytes; limit is {}",
            input.len(),
            limits.maximum_input_bytes
        )));
    }
    if input.starts_with(&[0xef, 0xbb, 0xbf]) {
        return Err(EngineError::json("UTF-8 BOM is forbidden"));
    }
    std::str::from_utf8(input)
        .map_err(|error| EngineError::json(format!("input is not UTF-8: {error}")))?;
    if limits.allow_floats {
        return Err(EngineError::json(
            "this engine's closed profile requires allow_floats=false",
        ));
    }

    let mut parser = Parser {
        input,
        position: 0,
        limits,
        nodes: 0,
        total_string_bytes: 0,
    };
    parser.skip_whitespace();
    let value = parser.parse_value(1)?;
    parser.skip_whitespace();
    if parser.position != input.len() {
        return Err(parser.error("trailing non-whitespace content"));
    }
    Ok(value)
}

struct Parser<'input> {
    input: &'input [u8],
    position: usize,
    limits: JsonLimits,
    nodes: usize,
    total_string_bytes: usize,
}

impl Parser<'_> {
    fn parse_value(&mut self, depth: usize) -> EngineResult<Value> {
        if depth > self.limits.maximum_json_depth {
            return Err(self.error("maximum JSON depth exceeded"));
        }
        self.nodes = self
            .nodes
            .checked_add(1)
            .ok_or_else(|| self.error("JSON node count overflow"))?;
        if self.nodes > self.limits.maximum_json_nodes {
            return Err(self.error("maximum JSON node count exceeded"));
        }

        match self.peek() {
            Some(b'{') => self.parse_object(depth),
            Some(b'[') => self.parse_array(depth),
            Some(b'"') => self.parse_string(false).map(Value::String),
            Some(b't') => self.parse_literal(b"true", Value::Bool(true)),
            Some(b'f') => self.parse_literal(b"false", Value::Bool(false)),
            Some(b'n') => self.parse_literal(b"null", Value::Null),
            Some(b'-' | b'0'..=b'9') => self.parse_integer(),
            Some(_) => Err(self.error("invalid JSON value")),
            None => Err(self.error("unexpected end of input")),
        }
    }

    fn parse_object(&mut self, depth: usize) -> EngineResult<Value> {
        self.consume_exact(b'{')?;
        self.skip_whitespace();
        let mut object = Map::new();
        if self.consume_if(b'}') {
            return Ok(Value::Object(object));
        }

        loop {
            if object.len() >= self.limits.maximum_object_members {
                return Err(self.error("maximum object member count exceeded"));
            }
            if self.peek() != Some(b'"') {
                return Err(self.error("object key must be a string"));
            }
            let key = self.parse_string(true)?;
            if object.contains_key(&key) {
                return Err(self.error(format!("duplicate object key {key:?}")));
            }
            self.skip_whitespace();
            self.consume_exact(b':')?;
            self.skip_whitespace();
            let value = self.parse_value(depth.saturating_add(1))?;
            object.insert(key, value);
            self.skip_whitespace();
            if self.consume_if(b'}') {
                return Ok(Value::Object(object));
            }
            self.consume_exact(b',')?;
            self.skip_whitespace();
        }
    }

    fn parse_array(&mut self, depth: usize) -> EngineResult<Value> {
        self.consume_exact(b'[')?;
        self.skip_whitespace();
        let mut array = Vec::new();
        if self.consume_if(b']') {
            return Ok(Value::Array(array));
        }

        loop {
            if array.len() >= self.limits.maximum_array_items {
                return Err(self.error("maximum array item count exceeded"));
            }
            array.push(self.parse_value(depth.saturating_add(1))?);
            self.skip_whitespace();
            if self.consume_if(b']') {
                return Ok(Value::Array(array));
            }
            self.consume_exact(b',')?;
            self.skip_whitespace();
        }
    }

    fn parse_string(&mut self, is_key: bool) -> EngineResult<String> {
        self.consume_exact(b'"')?;
        let mut decoded = Vec::new();

        loop {
            let byte = self
                .next()
                .ok_or_else(|| self.error("unterminated JSON string"))?;
            match byte {
                b'"' => break,
                b'\\' => self.parse_escape(&mut decoded)?,
                0x00..=0x1f => {
                    return Err(self.error("unescaped control character in JSON string"));
                }
                _ => decoded.push(byte),
            }
        }

        let value = String::from_utf8(decoded)
            .map_err(|error| self.error(format!("invalid UTF-8 string: {error}")))?;
        let individual_limit = if is_key {
            self.limits.maximum_key_utf8_bytes
        } else {
            self.limits.maximum_string_utf8_bytes
        };
        if value.len() > individual_limit {
            return Err(self.error(if is_key {
                "maximum key UTF-8 byte count exceeded"
            } else {
                "maximum string UTF-8 byte count exceeded"
            }));
        }
        self.total_string_bytes = self
            .total_string_bytes
            .checked_add(value.len())
            .ok_or_else(|| self.error("total string UTF-8 byte count overflow"))?;
        if self.total_string_bytes > self.limits.maximum_total_string_utf8_bytes {
            return Err(self.error("maximum total string UTF-8 byte count exceeded"));
        }
        Ok(value)
    }

    fn parse_escape(&mut self, decoded: &mut Vec<u8>) -> EngineResult<()> {
        let escaped = self
            .next()
            .ok_or_else(|| self.error("truncated JSON escape"))?;
        match escaped {
            b'"' | b'\\' | b'/' => decoded.push(escaped),
            b'b' => decoded.push(0x08),
            b'f' => decoded.push(0x0c),
            b'n' => decoded.push(b'\n'),
            b'r' => decoded.push(b'\r'),
            b't' => decoded.push(b'\t'),
            b'u' => {
                let first = self.parse_hex_quad()?;
                let scalar = if (0xd800..=0xdbff).contains(&first) {
                    self.consume_exact(b'\\')?;
                    self.consume_exact(b'u')?;
                    let second = self.parse_hex_quad()?;
                    if !(0xdc00..=0xdfff).contains(&second) {
                        return Err(self.error("high surrogate is not followed by a low surrogate"));
                    }
                    0x1_0000 + ((u32::from(first) - 0xd800) << 10) + (u32::from(second) - 0xdc00)
                } else if (0xdc00..=0xdfff).contains(&first) {
                    return Err(self.error("unpaired low surrogate"));
                } else {
                    u32::from(first)
                };
                let character = char::from_u32(scalar)
                    .ok_or_else(|| self.error("invalid Unicode scalar value"))?;
                let mut buffer = [0_u8; 4];
                decoded.extend_from_slice(character.encode_utf8(&mut buffer).as_bytes());
            }
            _ => return Err(self.error("invalid JSON escape")),
        }
        Ok(())
    }

    fn parse_hex_quad(&mut self) -> EngineResult<u16> {
        let mut value = 0_u16;
        for _ in 0..4 {
            let byte = self
                .next()
                .ok_or_else(|| self.error("truncated Unicode escape"))?;
            let digit = match byte {
                b'0'..=b'9' => u16::from(byte - b'0'),
                b'a'..=b'f' => u16::from(byte - b'a') + 10,
                b'A'..=b'F' => u16::from(byte - b'A') + 10,
                _ => return Err(self.error("invalid hexadecimal digit in Unicode escape")),
            };
            value = (value << 4) | digit;
        }
        Ok(value)
    }

    fn parse_integer(&mut self) -> EngineResult<Value> {
        let start = self.position;
        let negative = self.consume_if(b'-');
        match self.peek() {
            Some(b'0') => {
                self.position += 1;
                if matches!(self.peek(), Some(b'0'..=b'9')) {
                    return Err(self.error("integer has a leading zero"));
                }
                if negative {
                    return Err(self.error("negative zero is forbidden"));
                }
            }
            Some(b'1'..=b'9') => {
                self.position += 1;
                while matches!(self.peek(), Some(b'0'..=b'9')) {
                    self.position += 1;
                }
            }
            _ => return Err(self.error("invalid integer")),
        }
        if matches!(self.peek(), Some(b'.' | b'e' | b'E')) {
            return Err(self.error("floating-point JSON numbers are forbidden"));
        }
        let token = &self.input[start..self.position];
        if token.len() > self.limits.maximum_integer_characters {
            return Err(self.error("maximum integer character count exceeded"));
        }
        let token_text = std::str::from_utf8(token)
            .map_err(|error| self.error(format!("invalid integer token: {error}")))?;
        if negative {
            let parsed = token_text
                .parse::<i64>()
                .map_err(|error| self.error(format!("integer is out of range: {error}")))?;
            if parsed.unsigned_abs() > MAX_LANGUAGE_NEUTRAL_INTEGER {
                return Err(self.error("integer exceeds the language-neutral exact range"));
            }
            Ok(Value::Number(Number::from(parsed)))
        } else {
            let parsed = token_text
                .parse::<u64>()
                .map_err(|error| self.error(format!("integer is out of range: {error}")))?;
            if parsed > MAX_LANGUAGE_NEUTRAL_INTEGER {
                return Err(self.error("integer exceeds the language-neutral exact range"));
            }
            Ok(Value::Number(Number::from(parsed)))
        }
    }

    fn parse_literal(&mut self, expected: &[u8], value: Value) -> EngineResult<Value> {
        let end = self
            .position
            .checked_add(expected.len())
            .ok_or_else(|| self.error("literal position overflow"))?;
        if self.input.get(self.position..end) != Some(expected) {
            return Err(self.error("invalid JSON literal"));
        }
        self.position = end;
        Ok(value)
    }

    fn skip_whitespace(&mut self) {
        while matches!(self.peek(), Some(b' ' | b'\n' | b'\r' | b'\t')) {
            self.position += 1;
        }
    }

    fn consume_exact(&mut self, expected: u8) -> EngineResult<()> {
        if self.consume_if(expected) {
            Ok(())
        } else {
            Err(self.error(format!("expected byte {:?}", char::from(expected))))
        }
    }

    fn consume_if(&mut self, expected: u8) -> bool {
        if self.peek() == Some(expected) {
            self.position += 1;
            true
        } else {
            false
        }
    }

    fn peek(&self) -> Option<u8> {
        self.input.get(self.position).copied()
    }

    fn next(&mut self) -> Option<u8> {
        let byte = self.peek()?;
        self.position += 1;
        Some(byte)
    }

    fn error(&self, detail: impl Into<String>) -> EngineError {
        EngineError::json(format!("byte {}: {}", self.position, detail.into()))
    }
}

pub(crate) fn canonicalize(value: &Value) -> Value {
    match value {
        Value::Array(items) => Value::Array(items.iter().map(canonicalize).collect()),
        Value::Object(object) => {
            let sorted = object
                .iter()
                .map(|(key, value)| (key.clone(), canonicalize(value)))
                .collect::<BTreeMap<_, _>>();
            let canonical = sorted.into_iter().collect::<Map<_, _>>();
            Value::Object(canonical)
        }
        other => other.clone(),
    }
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::{parse_strict, JsonLimits};

    fn limits() -> JsonLimits {
        JsonLimits::corpus_bootstrap()
    }

    #[test]
    fn parse_strict_should_decode_surrogate_pair_and_reject_duplicate_decoded_key() {
        let parsed = parse_strict(br#"{"emoji":"\uD83D\uDE00"}"#, limits());
        assert_eq!(parsed.ok(), Some(json!({"emoji": "😀"})));

        let duplicate = parse_strict(br#"{"a":1,"\u0061":2}"#, limits());
        assert!(duplicate.is_err());
    }

    #[test]
    fn parse_strict_should_reject_floats_negative_zero_and_large_integer() {
        assert!(parse_strict(b"1.0", limits()).is_err());
        assert!(parse_strict(b"-0", limits()).is_err());
        assert!(parse_strict(b"9007199254740992", limits()).is_err());
    }

    #[test]
    fn parse_strict_should_enforce_depth_nodes_members_and_strings() {
        let mut bounded = limits();
        bounded.maximum_json_depth = 2;
        assert!(parse_strict(br#"{"a":{"b":1}}"#, bounded).is_err());

        bounded = limits();
        bounded.maximum_json_nodes = 2;
        assert!(parse_strict(br#"[1,2]"#, bounded).is_err());

        bounded = limits();
        bounded.maximum_object_members = 1;
        assert!(parse_strict(br#"{"a":1,"b":2}"#, bounded).is_err());

        bounded = limits();
        bounded.maximum_string_utf8_bytes = 1;
        assert!(parse_strict(br#""ab""#, bounded).is_err());
    }
}
