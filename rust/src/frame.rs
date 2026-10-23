//! Frames: the unit of transfer (specification sections 3 to 5).

use serde::de::{DeserializeSeed, Deserializer, Error as _, MapAccess, SeqAccess, Visitor};
use serde_json::{Map, Number, Value};
use sha2::{Digest, Sha256};
use std::fmt;
use std::sync::Arc;

/// The frame magic: `"NCP"` and the protocol version 2.
pub const MAGIC: [u8; 4] = *b"NCP\x02";
/// Header size in bytes.
pub const HEADER_BYTES: usize = 12;
/// Digest size in bytes.
pub const DIGEST_BYTES: usize = 32;
/// The bound before `open` completes.
pub const HANDSHAKE_BOUND: usize = 65_536;
/// The largest session bound.
pub const MAX_BOUND: usize = 67_108_864;
/// The default session bound of the reference SDKs.
pub const DEFAULT_BOUND: usize = 1_048_576;
/// Deepest nesting of objects and arrays, the top object included.
pub const MAX_DEPTH: usize = 64;
/// Largest integer magnitude.
pub const MAX_INTEGER: u64 = (1 << 53) - 1;
/// Most attachments in a frame.
pub const MAX_ATTACHMENTS: usize = 1024;
/// The member name of an array reference.
pub const ARRAY_KEY: &str = "ncp.array";

/// A frame that violates sections 3 to 6. The receiver treats it as a bad frame.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FrameError(pub String);

impl fmt::Display for FrameError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "bad frame: {}", self.0)
    }
}

impl std::error::Error for FrameError {}

fn bad<T>(reason: &str) -> Result<T, FrameError> {
    Err(FrameError(reason.to_owned()))
}

/// The element type of an array.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[allow(missing_docs)]
pub enum Dtype {
    U8,
    I8,
    U16,
    I16,
    U32,
    I32,
    U64,
    I64,
    F32,
    F64,
}

impl Dtype {
    /// The wire name, for example `"u32"`.
    pub fn name(self) -> &'static str {
        match self {
            Dtype::U8 => "u8",
            Dtype::I8 => "i8",
            Dtype::U16 => "u16",
            Dtype::I16 => "i16",
            Dtype::U32 => "u32",
            Dtype::I32 => "i32",
            Dtype::U64 => "u64",
            Dtype::I64 => "i64",
            Dtype::F32 => "f32",
            Dtype::F64 => "f64",
        }
    }

    /// Element size in bytes.
    pub fn size(self) -> usize {
        match self {
            Dtype::U8 | Dtype::I8 => 1,
            Dtype::U16 | Dtype::I16 => 2,
            Dtype::U32 | Dtype::I32 | Dtype::F32 => 4,
            Dtype::U64 | Dtype::I64 | Dtype::F64 => 8,
        }
    }

    /// Parse a wire name.
    pub fn parse(name: &str) -> Option<Dtype> {
        Some(match name {
            "u8" => Dtype::U8,
            "i8" => Dtype::I8,
            "u16" => Dtype::U16,
            "i16" => Dtype::I16,
            "u32" => Dtype::U32,
            "i32" => Dtype::I32,
            "u64" => Dtype::U64,
            "i64" => Dtype::I64,
            "f32" => Dtype::F32,
            "f64" => Dtype::F64,
            _ => return None,
        })
    }
}

/// An array to send: element type, shape, and little-endian element bytes.
#[derive(Debug, Clone, PartialEq)]
pub struct Array {
    /// Element type.
    pub dtype: Dtype,
    /// Shape in row-major order.
    pub shape: Vec<u64>,
    /// Little-endian element bytes.
    pub data: Vec<u8>,
}

macro_rules! from_slice {
    ($name:ident, $t:ty, $dtype:expr) => {
        #[doc = concat!("A one-dimensional array of `", stringify!($t), "` values.")]
        pub fn $name(values: &[$t]) -> Array {
            let mut data = Vec::with_capacity(values.len() * std::mem::size_of::<$t>());
            for value in values {
                data.extend_from_slice(&value.to_le_bytes());
            }
            Array {
                dtype: $dtype,
                shape: vec![values.len() as u64],
                data,
            }
        }
    };
}

impl Array {
    /// An array from raw little-endian bytes. Fails if the length does not fit the shape.
    pub fn new(dtype: Dtype, shape: Vec<u64>, data: Vec<u8>) -> Result<Array, FrameError> {
        let count = shape.iter().try_fold(1u64, |acc, &n| acc.checked_mul(n));
        match count.and_then(|c| c.checked_mul(dtype.size() as u64)) {
            Some(bytes) if bytes == data.len() as u64 => Ok(Array { dtype, shape, data }),
            _ => bad("array length differs from shape and dtype"),
        }
    }

    from_slice!(from_u8, u8, Dtype::U8);
    from_slice!(from_i8, i8, Dtype::I8);
    from_slice!(from_u16, u16, Dtype::U16);
    from_slice!(from_i16, i16, Dtype::I16);
    from_slice!(from_u32, u32, Dtype::U32);
    from_slice!(from_i32, i32, Dtype::I32);
    from_slice!(from_u64, u64, Dtype::U64);
    from_slice!(from_i64, i64, Dtype::I64);
    from_slice!(from_f32, f32, Dtype::F32);
    from_slice!(from_f64, f64, Dtype::F64);

    /// The JSON value that refers to this array as attachment `index` (section 5).
    pub fn reference(&self, index: usize) -> Value {
        let mut spec = Map::new();
        spec.insert("dtype".into(), Value::from(self.dtype.name()));
        spec.insert("shape".into(), Value::from(self.shape.clone()));
        spec.insert("att".into(), Value::from(index as u64));
        let mut outer = Map::new();
        outer.insert(ARRAY_KEY.into(), Value::Object(spec));
        Value::Object(outer)
    }
}

/// The identity of a frame: its digest field as 64 lowercase hexadecimal characters.
///
/// # Panics
///
/// If `frame` is shorter than the digest field. Every frame is longer.
pub fn identity(frame: &[u8]) -> String {
    hex(&frame[frame.len() - DIGEST_BYTES..])
}

/// Lowercase hexadecimal of bytes.
pub fn hex(bytes: &[u8]) -> String {
    const DIGITS: &[u8; 16] = b"0123456789abcdef";
    let mut text = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        text.push(DIGITS[(byte >> 4) as usize] as char);
        text.push(DIGITS[(byte & 15) as usize] as char);
    }
    text
}

/// Encode one message as a frame. `message` must be an object without `att`; the encoder sets
/// `att` from `arrays`, whose references the caller placed in the message with
/// [`Array::reference`].
pub fn encode(message: &Value, arrays: &[Array]) -> Result<Vec<u8>, FrameError> {
    let object = match message {
        Value::Object(object) => object,
        _ => return bad("message is not an object"),
    };
    if object.contains_key("att") {
        return bad("the encoder sets att");
    }
    if arrays.len() > MAX_ATTACHMENTS {
        return bad("too many attachments");
    }
    check_tree(message, 1)?;
    check_references(message, arrays)?;
    let mut text = serde_json::to_vec(message).map_err(|e| FrameError(e.to_string()))?;
    if !arrays.is_empty() {
        text.pop(); // the closing brace of the object
        if !object.is_empty() {
            text.push(b',');
        }
        text.extend_from_slice(b"\"att\":[");
        for (index, array) in arrays.iter().enumerate() {
            if index > 0 {
                text.push(b',');
            }
            text.extend_from_slice(array.data.len().to_string().as_bytes());
        }
        text.extend_from_slice(b"]}");
    }
    let padding = (8 - (HEADER_BYTES + text.len()) % 8) % 8;
    let json_length = text.len() + padding;
    let mut attachment_length = 0usize;
    for (index, array) in arrays.iter().enumerate() {
        if index > 0 {
            attachment_length = attachment_length.next_multiple_of(8);
        }
        attachment_length += array.data.len();
    }
    let total = HEADER_BYTES + json_length + attachment_length + DIGEST_BYTES;
    if json_length > u32::MAX as usize || attachment_length > u32::MAX as usize {
        return bad("frame too large");
    }
    let mut frame = Vec::with_capacity(total);
    frame.extend_from_slice(&MAGIC);
    frame.extend_from_slice(&(json_length as u32).to_be_bytes());
    frame.extend_from_slice(&(attachment_length as u32).to_be_bytes());
    frame.extend_from_slice(&text);
    frame.resize(HEADER_BYTES + json_length, b' ');
    let start = frame.len();
    for (index, array) in arrays.iter().enumerate() {
        if index > 0 {
            let aligned = start + (frame.len() - start).next_multiple_of(8);
            frame.resize(aligned, 0);
        }
        frame.extend_from_slice(&array.data);
    }
    let digest = Sha256::digest(&frame);
    frame.extend_from_slice(&digest);
    Ok(frame)
}

/// The rules of section 4 that `serde_json::Value` does not guarantee: integers within
/// 2^53 - 1 and at most MAX_DEPTH levels of nesting.
fn check_tree(value: &Value, depth: usize) -> Result<(), FrameError> {
    // Only objects and arrays count as levels, as in the decoder's scan.
    let too_deep = || {
        if depth > MAX_DEPTH {
            bad("nesting depth")
        } else {
            Ok(())
        }
    };
    match value {
        Value::Number(number) => {
            let magnitude = number
                .as_u64()
                .or_else(|| number.as_i64().map(i64::unsigned_abs));
            if magnitude.is_some_and(|m| m > MAX_INTEGER) {
                return bad("integer magnitude");
            }
        }
        Value::Array(items) => {
            too_deep()?;
            items
                .iter()
                .try_for_each(|item| check_tree(item, depth + 1))?;
        }
        Value::Object(object) => {
            too_deep()?;
            object
                .values()
                .try_for_each(|item| check_tree(item, depth + 1))?;
        }
        _ => {}
    }
    Ok(())
}

/// Every array is referred to exactly once, with its own dtype and shape (section 5).
fn check_references(message: &Value, arrays: &[Array]) -> Result<(), FrameError> {
    let mut references = Vec::new();
    collect_references(message, &mut references)?;
    if references.len() != arrays.len() {
        return bad("each array needs exactly one reference in the message");
    }
    let mut used = vec![false; arrays.len()];
    for (dtype, shape, index) in references {
        let array = arrays
            .get(index)
            .ok_or_else(|| FrameError("array reference index".into()))?;
        if used[index] {
            return bad("each array needs exactly one reference in the message");
        }
        used[index] = true;
        let count = shape
            .iter()
            .try_fold(1u64, |acc, &n| acc.checked_mul(n))
            .and_then(|c| c.checked_mul(dtype.size() as u64));
        if dtype != array.dtype || shape != array.shape || count != Some(array.data.len() as u64) {
            return bad("array reference differs from the array");
        }
    }
    Ok(())
}

/// Check a frame header (section 3) and return the number of bytes that follow it.
pub fn remaining_length(header: &[u8], bound: usize) -> Result<usize, FrameError> {
    if header.len() < HEADER_BYTES {
        return bad("short header");
    }
    if header[..4] != MAGIC {
        return bad("magic");
    }
    let json_length = u32::from_be_bytes([header[4], header[5], header[6], header[7]]) as usize;
    let attachment_length =
        u32::from_be_bytes([header[8], header[9], header[10], header[11]]) as usize;
    if json_length < 2 || !(HEADER_BYTES + json_length).is_multiple_of(8) {
        return bad("json region length");
    }
    if HEADER_BYTES + DIGEST_BYTES + json_length + attachment_length > bound {
        return bad("frame exceeds the bound");
    }
    Ok(json_length + attachment_length + DIGEST_BYTES)
}

/// A received array: element type, shape, and its byte range in the frame.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ArrayRef {
    /// Element type.
    pub dtype: Dtype,
    /// Shape in row-major order.
    pub shape: Vec<u64>,
    start: usize,
    end: usize,
}

/// A decoded frame: its message, arrays, identity, and exact bytes.
#[derive(Debug, Clone)]
pub struct Decoded {
    /// The JSON message. Array references stay in place as `{"ncp.array": ...}` objects.
    pub message: Value,
    /// Arrays by attachment index.
    pub arrays: Vec<ArrayRef>,
    /// The identity of the frame.
    pub identity: String,
    /// The exact frame bytes, shared without copying.
    pub frame: Arc<Vec<u8>>,
}

macro_rules! to_vec {
    ($name:ident, $t:ty, $dtype:expr) => {
        #[doc = concat!("The elements of array `index` as `", stringify!($t), "` values.")]
        pub fn $name(&self, index: usize) -> Option<Vec<$t>> {
            let array = self.arrays.get(index)?;
            if array.dtype != $dtype {
                return None;
            }
            const SIZE: usize = std::mem::size_of::<$t>();
            Some(
                self.frame[array.start..array.end]
                    .chunks_exact(SIZE)
                    .map(|chunk| {
                        let mut bytes = [0u8; SIZE];
                        bytes.copy_from_slice(chunk);
                        <$t>::from_le_bytes(bytes)
                    })
                    .collect(),
            )
        }
    };
}

impl Decoded {
    /// The little-endian bytes of array `index`, without a copy.
    pub fn array_bytes(&self, index: usize) -> Option<&[u8]> {
        self.arrays
            .get(index)
            .map(|array| &self.frame[array.start..array.end])
    }

    to_vec!(array_u8, u8, Dtype::U8);
    to_vec!(array_i8, i8, Dtype::I8);
    to_vec!(array_u16, u16, Dtype::U16);
    to_vec!(array_i16, i16, Dtype::I16);
    to_vec!(array_u32, u32, Dtype::U32);
    to_vec!(array_i32, i32, Dtype::I32);
    to_vec!(array_u64, u64, Dtype::U64);
    to_vec!(array_i64, i64, Dtype::I64);
    to_vec!(array_f32, f32, Dtype::F32);
    to_vec!(array_f64, f64, Dtype::F64);

    /// The arrays as owned values, for example to send them on.
    pub fn owned_arrays(&self) -> Vec<Array> {
        self.arrays
            .iter()
            .map(|a| Array {
                dtype: a.dtype,
                shape: a.shape.clone(),
                data: self.frame[a.start..a.end].to_vec(),
            })
            .collect()
    }
}

/// Check and decode one complete frame. Fails with FrameError for a bad frame.
pub fn decode(frame: Vec<u8>, bound: usize) -> Result<Decoded, FrameError> {
    decode_with(frame, bound, true)
}

/// As [`decode`]. With `check_digest` false, the digest field is not compared with the frame
/// bytes, and the identity is the digest field as received. Use it only on a pipe pair or a
/// Unix domain socket with no other program between the two endpoints (spec section 3, rule 4).
pub fn decode_with(
    frame: Vec<u8>,
    bound: usize,
    check_digest: bool,
) -> Result<Decoded, FrameError> {
    let frame = Arc::new(frame);
    let rest = remaining_length(&frame, bound)?;
    if frame.len() != HEADER_BYTES + rest {
        return bad("frame length");
    }
    let json_length = u32::from_be_bytes([frame[4], frame[5], frame[6], frame[7]]) as usize;
    let attachment_length = u32::from_be_bytes([frame[8], frame[9], frame[10], frame[11]]) as usize;
    let end = HEADER_BYTES + json_length + attachment_length;
    if check_digest && Sha256::digest(&frame[..end]).as_slice() != &frame[end..] {
        return bad("digest");
    }
    let json = &frame[HEADER_BYTES..HEADER_BYTES + json_length];
    scan(json)?;
    let mut deserializer = serde_json::Deserializer::from_slice(json);
    let message = StrictSeed
        .deserialize(&mut deserializer)
        .map_err(|e| FrameError(format!("json: {e}")))?;
    deserializer
        .end()
        .map_err(|e| FrameError(format!("json: {e}")))?;
    if !message.is_object() {
        return bad("json value is not an object");
    }
    let arrays = bind_arrays(
        &message,
        HEADER_BYTES + json_length,
        attachment_length,
        &frame,
    )?;
    Ok(Decoded {
        message,
        arrays,
        identity: hex(&frame[end..]),
        frame,
    })
}

/// One pass over the JSON text outside strings: integer literals within 2^53 - 1, nesting depth
/// within MAX_DEPTH, no byte order mark. serde_json reports integer literals beyond 64 bits as
/// floats, so this check must look at the text.
fn scan(json: &[u8]) -> Result<(), FrameError> {
    if json.starts_with(&[0xEF, 0xBB, 0xBF]) {
        return bad("byte order mark");
    }
    let mut depth = 0usize;
    let mut index = 0usize;
    while index < json.len() {
        match json[index] {
            b'"' => {
                index += 1;
                while index < json.len() && json[index] != b'"' {
                    index += if json[index] == b'\\' { 2 } else { 1 };
                }
                index += 1;
            }
            b'{' | b'[' => {
                depth += 1;
                if depth > MAX_DEPTH {
                    return bad("nesting depth");
                }
                index += 1;
            }
            b'}' | b']' => {
                depth = depth.saturating_sub(1);
                index += 1;
            }
            b'-' | b'0'..=b'9' => {
                let start = index;
                while index < json.len()
                    && matches!(json[index], b'-' | b'+' | b'.' | b'e' | b'E' | b'0'..=b'9')
                {
                    index += 1;
                }
                let token = &json[start..index];
                if token == b"-0" {
                    // serde_json reads it as the float -0.0, other decoders as the integer 0.
                    return bad("negative zero integer");
                }
                if !token.iter().any(|b| matches!(b, b'.' | b'e' | b'E')) {
                    let digits = token.strip_prefix(b"-").unwrap_or(token);
                    if digits.len() > 16 {
                        let value: u128 = std::str::from_utf8(digits)
                            .ok()
                            .filter(|d| d.len() <= 38)
                            .and_then(|d| d.parse().ok())
                            .ok_or_else(|| FrameError("integer magnitude".into()))?;
                        if value > MAX_INTEGER as u128 {
                            return bad("integer magnitude");
                        }
                    }
                }
            }
            _ => index += 1,
        }
    }
    Ok(())
}

struct StrictSeed;

impl<'de> DeserializeSeed<'de> for StrictSeed {
    type Value = Value;
    fn deserialize<D: Deserializer<'de>>(self, deserializer: D) -> Result<Value, D::Error> {
        deserializer.deserialize_any(StrictVisitor)
    }
}

struct StrictVisitor;

impl<'de> Visitor<'de> for StrictVisitor {
    type Value = Value;

    fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("a JSON value")
    }
    fn visit_bool<E>(self, v: bool) -> Result<Value, E> {
        Ok(Value::Bool(v))
    }
    fn visit_i64<E: serde::de::Error>(self, v: i64) -> Result<Value, E> {
        if v.unsigned_abs() > MAX_INTEGER {
            return Err(E::custom("integer magnitude"));
        }
        Ok(Value::from(v))
    }
    fn visit_u64<E: serde::de::Error>(self, v: u64) -> Result<Value, E> {
        if v > MAX_INTEGER {
            return Err(E::custom("integer magnitude"));
        }
        Ok(Value::from(v))
    }
    fn visit_f64<E: serde::de::Error>(self, v: f64) -> Result<Value, E> {
        Number::from_f64(v)
            .map(Value::Number)
            .ok_or_else(|| E::custom("number outside the binary64 range"))
    }
    fn visit_str<E>(self, v: &str) -> Result<Value, E> {
        Ok(Value::String(v.to_owned()))
    }
    fn visit_string<E>(self, v: String) -> Result<Value, E> {
        Ok(Value::String(v))
    }
    fn visit_unit<E>(self) -> Result<Value, E> {
        Ok(Value::Null)
    }
    fn visit_seq<A: SeqAccess<'de>>(self, mut seq: A) -> Result<Value, A::Error> {
        let mut items = Vec::new();
        while let Some(item) = seq.next_element_seed(StrictSeed)? {
            items.push(item);
        }
        Ok(Value::Array(items))
    }
    fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<Value, A::Error> {
        let mut object = Map::new();
        while let Some(key) = map.next_key::<String>()? {
            if object.contains_key(&key) {
                return Err(A::Error::custom("duplicate member name"));
            }
            let value = map.next_value_seed(StrictSeed)?;
            object.insert(key, value);
        }
        Ok(Value::Object(object))
    }
}

fn bind_arrays(
    message: &Value,
    region_start: usize,
    attachment_length: usize,
    frame: &[u8],
) -> Result<Vec<ArrayRef>, FrameError> {
    let mut references = Vec::new();
    collect_references(message, &mut references)?;
    let lengths: Vec<usize> = match message.get("att") {
        None => Vec::new(),
        Some(Value::Array(items)) => {
            if items.len() > MAX_ATTACHMENTS {
                return bad("att");
            }
            let mut lengths = Vec::with_capacity(items.len());
            for item in items {
                match item.as_u64() {
                    Some(n) if item.is_u64() || item.is_i64() => lengths.push(n as usize),
                    _ => return bad("att"),
                }
            }
            lengths
        }
        Some(_) => return bad("att"),
    };
    if lengths.is_empty() {
        if attachment_length != 0 || !references.is_empty() {
            return bad("attachments without att");
        }
        return Ok(Vec::new());
    }
    let mut offsets = Vec::with_capacity(lengths.len());
    let mut offset = 0usize;
    for (index, length) in lengths.iter().enumerate() {
        if index > 0 && !offset.is_multiple_of(8) {
            let padded = offset.next_multiple_of(8);
            if padded > attachment_length
                || frame[region_start + offset..region_start + padded]
                    .iter()
                    .any(|&b| b != 0)
            {
                return bad("nonzero attachment padding");
            }
            offset = padded;
        }
        offsets.push(offset);
        offset = offset
            .checked_add(*length)
            .ok_or_else(|| FrameError("att".into()))?;
    }
    if offset != attachment_length {
        return bad("attachment region length");
    }
    let mut arrays: Vec<Option<ArrayRef>> = vec![None; lengths.len()];
    for (dtype, shape, index) in references {
        if index >= lengths.len() || arrays[index].is_some() {
            return bad("array attachment index");
        }
        let expected = shape
            .iter()
            .try_fold(1u64, |acc, &n| acc.checked_mul(n))
            .and_then(|count| count.checked_mul(dtype.size() as u64));
        if expected != Some(lengths[index] as u64) {
            return bad("array length differs from shape and dtype");
        }
        let start = region_start + offsets[index];
        arrays[index] = Some(ArrayRef {
            dtype,
            shape,
            start,
            end: start + lengths[index],
        });
    }
    arrays
        .into_iter()
        .map(|a| a.ok_or_else(|| FrameError("attachment without array".into())))
        .collect()
}

fn collect_references(
    value: &Value,
    out: &mut Vec<(Dtype, Vec<u64>, usize)>,
) -> Result<(), FrameError> {
    match value {
        Value::Object(object) => {
            if let Some(spec) = object.get(ARRAY_KEY) {
                if object.len() != 1 {
                    return bad("array object with other members");
                }
                let spec = match spec {
                    Value::Object(spec) if spec.len() == 3 => spec,
                    _ => return bad("array members"),
                };
                let dtype = spec
                    .get("dtype")
                    .and_then(Value::as_str)
                    .and_then(Dtype::parse);
                let shape = spec
                    .get("shape")
                    .and_then(Value::as_array)
                    .and_then(|items| {
                        items
                            .iter()
                            .map(|n| if n.is_u64() { n.as_u64() } else { None })
                            .collect::<Option<Vec<u64>>>()
                    });
                let index = spec
                    .get("att")
                    .filter(|n| n.is_u64())
                    .and_then(Value::as_u64);
                match (dtype, shape, index) {
                    (Some(dtype), Some(shape), Some(index)) => {
                        out.push((dtype, shape, index as usize))
                    }
                    (None, _, _) => return bad("array dtype"),
                    _ => return bad("array members"),
                }
                return Ok(());
            }
            for child in object.values() {
                collect_references(child, out)?;
            }
        }
        Value::Array(items) => {
            for child in items {
                collect_references(child, out)?;
            }
        }
        _ => {}
    }
    Ok(())
}
