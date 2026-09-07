//! Development primitives for owned modular payloads, without a protocol owner.
//!
//! Host context is a trusted local seam, not proof of request verification.
//! The future closed request owner must verify identity before calling this API.
//! Logical byte bounds exclude allocator headers, application state, and GPU memory.

use std::collections::BTreeMap;
use std::fmt;

use serde::{Deserialize, Serialize};

use crate::bounded_json::preflight;
use crate::canonical_digest::{canonical_projection, sha256_hex};

pub const FRAME_BYTES: usize = 65_536;
pub const CHUNK_BYTES: usize = 32_768;
pub const BUFFER_BYTES: usize = 8_388_608;
pub const ENDPOINT_BYTES: usize = 67_108_864;
pub const COMPOSITION_BYTES: usize = 268_435_456;
pub const LIVE_SLOTS: usize = 24;
pub const INCOMPLETE_SLOTS: usize = 12;
pub const ENDPOINTS: usize = 16;
pub const MANIFEST_BYTES: usize = 4_096;
pub const SEMANTIC_SLOTS: usize = 64;
pub const METADATA_BYTES: usize = 131_072;
pub const INPUT_SPEC_BYTES: usize = 256;
pub const INPUT_METADATA_BYTES: usize = 16_384;
pub const DIGEST_STAGING_BYTES: usize = 131_072;
pub const MAX_ID: u64 = 9_007_199_254_740_991;
const ALPHABET: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

/// A local primitive failure. This is not a remote execution disposition.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BufferError {
    Wire,
    Binding,
    Capacity,
    Conflict,
    Unavailable,
    State,
}

impl fmt::Display for BufferError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "modular buffer error: {self:?}")
    }
}
impl std::error::Error for BufferError {}

fn digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

fn uuid(value: &str) -> bool {
    value.len() == 36
        && value.as_bytes()[14] == b'4'
        && matches!(value.as_bytes()[19], b'8' | b'9' | b'a' | b'b')
        && value.bytes().enumerate().all(|(i, b)| {
            if matches!(i, 8 | 13 | 18 | 23) {
                b == b'-'
            } else {
                b.is_ascii_digit() || (b'a'..=b'f').contains(&b)
            }
        })
}

/// Encode one nonempty bounded chunk under standard padded base64.
pub fn encode_chunk(bytes: &[u8]) -> Result<String, BufferError> {
    if bytes.is_empty() || bytes.len() > CHUNK_BYTES {
        return Err(BufferError::Capacity);
    }
    let mut output = String::with_capacity(bytes.len().div_ceil(3) * 4);
    for row in bytes.chunks(3) {
        let a = row[0];
        let b = row.get(1).copied().unwrap_or(0);
        let c = row.get(2).copied().unwrap_or(0);
        output.push(ALPHABET[(a >> 2) as usize] as char);
        output.push(ALPHABET[(((a & 3) << 4) | (b >> 4)) as usize] as char);
        output.push(if row.len() > 1 {
            ALPHABET[(((b & 15) << 2) | (c >> 6)) as usize] as char
        } else {
            '='
        });
        output.push(if row.len() > 2 {
            ALPHABET[(c & 63) as usize] as char
        } else {
            '='
        });
    }
    Ok(output)
}

/// Decode only canonical padded base64, including exact unused padding bits.
pub fn decode_chunk(text: &str) -> Result<Vec<u8>, BufferError> {
    if text.is_empty() || text.len() > CHUNK_BYTES.div_ceil(3) * 4 || !text.len().is_multiple_of(4)
    {
        return Err(BufferError::Wire);
    }
    let padding = text.bytes().rev().take_while(|b| *b == b'=').count();
    if padding > 2 || text.len() / 4 * 3 - padding > CHUNK_BYTES {
        return Err(BufferError::Wire);
    }
    let mut output = Vec::with_capacity(text.len() / 4 * 3 - padding);
    for (index, row) in text.as_bytes().chunks_exact(4).enumerate() {
        let last = index + 1 == text.len() / 4;
        let value = |b: u8| -> Result<u8, BufferError> {
            match b {
                b'A'..=b'Z' => Ok(b - b'A'),
                b'a'..=b'z' => Ok(b - b'a' + 26),
                b'0'..=b'9' => Ok(b - b'0' + 52),
                b'+' => Ok(62),
                b'/' => Ok(63),
                _ => Err(BufferError::Wire),
            }
        };
        let a = value(row[0])?;
        let b = value(row[1])?;
        output.push((a << 2) | (b >> 4));
        if row[2] == b'=' {
            if !last || row[3] != b'=' || b & 15 != 0 {
                return Err(BufferError::Wire);
            }
        } else {
            let c = value(row[2])?;
            output.push((b << 4) | (c >> 2));
            if row[3] == b'=' {
                if !last || c & 3 != 0 {
                    return Err(BufferError::Wire);
                }
            } else {
                output.push((c << 6) | value(row[3])?);
            }
        }
        if output.len() > CHUNK_BYTES {
            return Err(BufferError::Wire);
        }
    }
    if encode_chunk(&output)? != text {
        return Err(BufferError::Wire);
    }
    Ok(output)
}

/// Fixed host-selected endpoint identity. Its fields are not discovery authority.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct BufferBinding {
    pub profile_digest: String,
    pub application_digest: String,
    pub run_id: String,
    pub endpoint_id: String,
    pub generation: String,
}

impl BufferBinding {
    pub fn validate(&self) -> Result<(), BufferError> {
        if !digest(&self.profile_digest)
            || !digest(&self.application_digest)
            || !uuid(&self.run_id)
            || !uuid(&self.endpoint_id)
            || !uuid(&self.generation)
        {
            return Err(BufferError::Binding);
        }
        Ok(())
    }
}

/// Trusted local seam, deliberately not serializable or named verified context.
///
/// The host must obtain these fields from its already verified complete request.
/// This constructor checks representation only. It cannot attest that host action.
#[derive(Debug)]
pub struct TrustedHostCreationContext {
    binding: BufferBinding,
    request_digest: String,
    predecessor: Option<String>,
}

impl TrustedHostCreationContext {
    pub fn new(
        binding: BufferBinding,
        request_digest: String,
        predecessor: Option<String>,
    ) -> Result<Self, BufferError> {
        binding.validate()?;
        if !digest(&request_digest) || predecessor.as_ref().is_some_and(|p| !digest(p)) {
            return Err(BufferError::Binding);
        }
        Ok(Self {
            binding,
            request_digest,
            predecessor,
        })
    }
}

/// A generation-scoped handle. Unknown handles grant no release receipt.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct BufferRef {
    pub generation: String,
    pub buffer_id: u64,
}

/// Closed immutable manifest. The enclosing result digest is intentionally absent.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct BufferManifest {
    pub schema: String,
    pub binding: BufferBinding,
    pub buffer_id: u64,
    pub creating_request_digest: String,
    pub causal_predecessor: Option<String>,
    pub semantic_digest: String,
    pub byte_length: usize,
    pub payload_sha256: String,
    pub chunk_bytes: usize,
    pub chunk_count: usize,
    pub imported_manifest_digest: Option<String>,
    pub manifest_digest: String,
}

impl BufferManifest {
    pub fn reference(&self) -> BufferRef {
        BufferRef {
            generation: self.binding.generation.clone(),
            buffer_id: self.buffer_id,
        }
    }

    fn calculate_digest(&self) -> Result<String, BufferError> {
        let mut value = serde_json::to_value(self).map_err(|_| BufferError::Wire)?;
        value
            .as_object_mut()
            .ok_or(BufferError::Wire)?
            .remove("manifest_digest");
        let bytes = canonical_projection(b"ncp.modular.buffer-manifest.v1\0", &value)
            .map_err(|_| BufferError::Wire)?;
        if bytes.len() > DIGEST_STAGING_BYTES {
            return Err(BufferError::Capacity);
        }
        Ok(sha256_hex(&bytes))
    }

    /// Verify bounded shape, the declared source binding, and typed digest.
    pub fn verify(&self, expected: &BufferBinding) -> Result<(), BufferError> {
        self.binding.validate()?;
        if &self.binding != expected {
            return Err(BufferError::Binding);
        }
        if self.schema != "ncp.modular.buffer-manifest.v1"
            || self.buffer_id == 0
            || self.buffer_id > MAX_ID
            || !digest(&self.creating_request_digest)
            || !digest(&self.semantic_digest)
            || !digest(&self.payload_sha256)
            || !digest(&self.manifest_digest)
            || self.causal_predecessor.as_ref().is_some_and(|p| !digest(p))
            || self
                .imported_manifest_digest
                .as_ref()
                .is_some_and(|p| !digest(p))
            || self.byte_length == 0
            || self.byte_length > BUFFER_BYTES
            || self.chunk_bytes != CHUNK_BYTES
            || self.chunk_count != self.byte_length.div_ceil(CHUNK_BYTES)
        {
            return Err(BufferError::Wire);
        }
        // All serialized fields now have bounded lengths and cardinalities.
        if serde_json::to_vec(self)
            .map_err(|_| BufferError::Wire)?
            .len()
            > MANIFEST_BYTES
        {
            return Err(BufferError::Capacity);
        }
        if self.calculate_digest()? != self.manifest_digest {
            return Err(BufferError::Conflict);
        }
        Ok(())
    }

    pub fn from_json(bytes: &[u8], expected: &BufferBinding) -> Result<Self, BufferError> {
        if bytes.is_empty() || bytes.len() > MANIFEST_BYTES {
            return Err(BufferError::Capacity);
        }
        preflight(bytes).map_err(|_| BufferError::Wire)?;
        let result: Self = serde_json::from_slice(bytes).map_err(|_| BufferError::Wire)?;
        result.verify(expected)?;
        Ok(result)
    }
}

/// One explicit indexed chunk. It contains no path, address, or executable handle.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct BufferChunk {
    pub schema: String,
    pub manifest_digest: String,
    pub index: usize,
    pub offset: usize,
    pub decoded_length: usize,
    pub chunk_sha256: String,
    pub data_base64: String,
}

impl BufferChunk {
    pub fn from_json(bytes: &[u8]) -> Result<Self, BufferError> {
        if bytes.is_empty() || bytes.len() > FRAME_BYTES {
            return Err(BufferError::Capacity);
        }
        preflight(bytes).map_err(|_| BufferError::Wire)?;
        let result: Self = serde_json::from_slice(bytes).map_err(|_| BufferError::Wire)?;
        result.decoded()?;
        Ok(result)
    }

    /// Return a caller-owned bounded copy after complete chunk validation.
    pub fn decoded(&self) -> Result<Vec<u8>, BufferError> {
        if self.schema != "ncp.modular.buffer-chunk.v1"
            || !digest(&self.manifest_digest)
            || !digest(&self.chunk_sha256)
            || self.index >= BUFFER_BYTES.div_ceil(CHUNK_BYTES)
            || self.offset != self.index * CHUNK_BYTES
            || self.decoded_length == 0
            || self.decoded_length > CHUNK_BYTES
        {
            return Err(BufferError::Wire);
        }
        let bytes = decode_chunk(&self.data_base64)?;
        if bytes.len() != self.decoded_length || sha256_hex(&bytes) != self.chunk_sha256 {
            return Err(BufferError::Conflict);
        }
        Ok(bytes)
    }

    pub fn to_json(&self) -> Result<Vec<u8>, BufferError> {
        self.decoded()?;
        // The closed validated shape has at most 43,692 base64 bytes plus fixed fields.
        let result = serde_json::to_vec(self).map_err(|_| BufferError::Wire)?;
        if result.len() > FRAME_BYTES {
            return Err(BufferError::Capacity);
        }
        Ok(result)
    }
}

struct Entry {
    manifest: BufferManifest,
    bytes: Vec<u8>,
    // None identifies sealed data. Some is the accepted import prefix length.
    prefix: Option<usize>,
}

/// Exact logical allocation state, useful for pre-mutation admission controls.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct BufferUsage {
    pub reserved_bytes: usize,
    pub live_slots: usize,
    pub incomplete_slots: usize,
    pub next_id: u64,
}

/// Synchronous owned payload storage, with no network or remote retry semantics.
pub struct BufferPool {
    binding: BufferBinding,
    semantics: Vec<String>,
    entries: BTreeMap<u64, Entry>,
    reserved: usize,
    next_id: u64,
}

impl BufferPool {
    pub fn new(binding: BufferBinding, semantics: Vec<String>) -> Result<Self, BufferError> {
        binding.validate()?;
        if semantics.is_empty()
            || semantics.len() > SEMANTIC_SLOTS
            || semantics.iter().any(|s| !digest(s))
            || semantics.windows(2).any(|pair| pair[0] >= pair[1])
        {
            return Err(BufferError::Binding);
        }
        Ok(Self {
            binding,
            semantics,
            entries: BTreeMap::new(),
            reserved: 0,
            next_id: 1,
        })
    }

    pub fn usage(&self) -> BufferUsage {
        BufferUsage {
            reserved_bytes: self.reserved,
            live_slots: self.entries.len(),
            incomplete_slots: self.entries.values().filter(|e| e.prefix.is_some()).count(),
            next_id: self.next_id,
        }
    }

    fn admit(
        &self,
        context: &TrustedHostCreationContext,
        semantic: &str,
        length: usize,
        incomplete: bool,
    ) -> Result<(), BufferError> {
        if context.binding != self.binding
            || self
                .semantics
                .binary_search_by(|s| s.as_str().cmp(semantic))
                .is_err()
        {
            return Err(BufferError::Binding);
        }
        if length == 0
            || length > BUFFER_BYTES
            || self.next_id > MAX_ID
            || self.entries.len() >= LIVE_SLOTS
            || length > ENDPOINT_BYTES - self.reserved
            || (incomplete && self.usage().incomplete_slots >= INCOMPLETE_SLOTS)
        {
            return Err(BufferError::Capacity);
        }
        Ok(())
    }

    fn manifest(
        &self,
        context: &TrustedHostCreationContext,
        semantic: &str,
        length: usize,
        payload: String,
        imported: Option<String>,
    ) -> Result<BufferManifest, BufferError> {
        self.manifest_at(self.next_id, context, semantic, length, payload, imported)
    }

    fn manifest_at(
        &self,
        id: u64,
        context: &TrustedHostCreationContext,
        semantic: &str,
        length: usize,
        payload: String,
        imported: Option<String>,
    ) -> Result<BufferManifest, BufferError> {
        let mut result = BufferManifest {
            schema: "ncp.modular.buffer-manifest.v1".into(),
            binding: self.binding.clone(),
            buffer_id: id,
            creating_request_digest: context.request_digest.clone(),
            causal_predecessor: context.predecessor.clone(),
            semantic_digest: semantic.into(),
            byte_length: length,
            payload_sha256: payload,
            chunk_bytes: CHUNK_BYTES,
            chunk_count: length.div_ceil(CHUNK_BYTES),
            imported_manifest_digest: imported,
            manifest_digest: String::new(),
        };
        result.manifest_digest = result.calculate_digest()?;
        result.verify(&self.binding)?;
        Ok(result)
    }

    /// Copy admitted producer bytes before hashing and publishing the immutable manifest.
    pub fn publish(
        &mut self,
        context: &TrustedHostCreationContext,
        semantic: &str,
        payload: &[u8],
    ) -> Result<BufferManifest, BufferError> {
        self.admit(context, semantic, payload.len(), false)?;
        let mut bytes = Vec::new();
        bytes
            .try_reserve_exact(payload.len())
            .map_err(|_| BufferError::Capacity)?;
        bytes.extend_from_slice(payload);
        let manifest = self.manifest(context, semantic, bytes.len(), sha256_hex(&bytes), None)?;
        self.reserved += bytes.len();
        self.entries.insert(
            self.next_id,
            Entry {
                manifest: manifest.clone(),
                bytes,
                prefix: None,
            },
        );
        self.next_id += 1;
        Ok(manifest)
    }

    /// Reserve full destination bytes from an exact host-declared source manifest.
    pub fn begin_import(
        &mut self,
        context: &TrustedHostCreationContext,
        source: &BufferManifest,
        expected_source: &BufferBinding,
    ) -> Result<BufferRef, BufferError> {
        source.verify(expected_source)?;
        self.admit(context, &source.semantic_digest, source.byte_length, true)?;
        let mut bytes = Vec::new();
        bytes
            .try_reserve_exact(source.byte_length)
            .map_err(|_| BufferError::Capacity)?;
        bytes.resize(source.byte_length, 0);
        let manifest = self.manifest(
            context,
            &source.semantic_digest,
            source.byte_length,
            source.payload_sha256.clone(),
            Some(source.manifest_digest.clone()),
        )?;
        let reference = manifest.reference();
        self.reserved += bytes.len();
        self.entries.insert(
            self.next_id,
            Entry {
                manifest,
                bytes,
                prefix: Some(0),
            },
        );
        self.next_id += 1;
        Ok(reference)
    }

    fn check_ref(&self, reference: &BufferRef) -> Result<(), BufferError> {
        if reference.generation != self.binding.generation {
            return Err(BufferError::Binding);
        }
        if reference.buffer_id == 0 || reference.buffer_id > MAX_ID {
            return Err(BufferError::Wire);
        }
        Ok(())
    }

    /// Append one exact next chunk. Replays under a new operation do not append twice.
    pub fn append(
        &mut self,
        reference: &BufferRef,
        chunk: &BufferChunk,
    ) -> Result<(), BufferError> {
        self.check_ref(reference)?;
        let entry = self
            .entries
            .get_mut(&reference.buffer_id)
            .ok_or(BufferError::Unavailable)?;
        let bytes = chunk.decoded()?;
        let prefix = entry.prefix.ok_or(BufferError::State)?;
        if entry.manifest.imported_manifest_digest.as_ref() != Some(&chunk.manifest_digest)
            || chunk.offset != prefix
            || bytes.len() != (entry.bytes.len() - prefix).min(CHUNK_BYTES)
        {
            return Err(BufferError::Conflict);
        }
        let end = prefix + bytes.len();
        entry.bytes[prefix..end].copy_from_slice(&bytes);
        entry.prefix = Some(end);
        Ok(())
    }

    /// Seal only the complete exact payload, without allocating a second payload copy.
    pub fn seal(&mut self, reference: &BufferRef) -> Result<BufferManifest, BufferError> {
        self.check_ref(reference)?;
        let entry = self
            .entries
            .get_mut(&reference.buffer_id)
            .ok_or(BufferError::Unavailable)?;
        if entry.prefix != Some(entry.bytes.len()) {
            return Err(BufferError::State);
        }
        if sha256_hex(&entry.bytes) != entry.manifest.payload_sha256 {
            return Err(BufferError::Conflict);
        }
        entry.prefix = None;
        Ok(entry.manifest.clone())
    }

    /// Read a bounded owned copy from a sealed buffer.
    pub fn read(&self, reference: &BufferRef, index: usize) -> Result<BufferChunk, BufferError> {
        self.check_read(reference, index)?;
        let entry = self
            .entries
            .get(&reference.buffer_id)
            .ok_or(BufferError::Unavailable)?;
        if entry.prefix.is_some() || index >= entry.manifest.chunk_count {
            return Err(BufferError::State);
        }
        let offset = index * CHUNK_BYTES;
        let bytes = &entry.bytes[offset..entry.bytes.len().min(offset + CHUNK_BYTES)];
        Ok(BufferChunk {
            schema: "ncp.modular.buffer-chunk.v1".into(),
            manifest_digest: entry.manifest.manifest_digest.clone(),
            index,
            offset,
            decoded_length: bytes.len(),
            chunk_sha256: sha256_hex(bytes),
            data_base64: encode_chunk(bytes)?,
        })
    }

    /// Validate a read without decoding or allocating a chunk.
    pub fn check_read(&self, reference: &BufferRef, index: usize) -> Result<(), BufferError> {
        self.check_ref(reference)?;
        let entry = self
            .entries
            .get(&reference.buffer_id)
            .ok_or(BufferError::Unavailable)?;
        if entry.prefix.is_some() || index >= entry.manifest.chunk_count {
            return Err(BufferError::State);
        }
        Ok(())
    }

    /// Join a caller-held manifest identity without copying its complete record.
    pub fn check_manifest(&self, reference: &BufferRef, expected: &str) -> Result<(), BufferError> {
        self.check_ref(reference)?;
        let entry = self
            .entries
            .get(&reference.buffer_id)
            .ok_or(BufferError::Unavailable)?;
        if entry.manifest.manifest_digest != expected {
            return Err(BufferError::Conflict);
        }
        Ok(())
    }

    fn remove(&mut self, reference: &BufferRef, incomplete: bool) -> Result<(), BufferError> {
        self.check_ref(reference)?;
        let entry = self
            .entries
            .get(&reference.buffer_id)
            .ok_or(BufferError::Unavailable)?;
        if entry.prefix.is_some() != incomplete {
            return Err(BufferError::State);
        }
        self.reserved -= entry.bytes.len();
        self.entries.remove(&reference.buffer_id);
        Ok(())
    }

    /// Discard only this exact owned incomplete import.
    pub fn abort_import(&mut self, reference: &BufferRef) -> Result<(), BufferError> {
        self.remove(reference, true)
    }

    /// Release only this exact sealed buffer. The monotonic ID is never reused.
    pub fn release(&mut self, reference: &BufferRef) -> Result<(), BufferError> {
        self.remove(reference, false)
    }

    /// Immutable complete-import inspection for admission before sequence consumption.
    pub fn inspect_import(
        &self,
        reference: &BufferRef,
    ) -> Result<(&BufferManifest, &[u8]), BufferError> {
        self.check_ref(reference)?;
        let entry = self
            .entries
            .get(&reference.buffer_id)
            .ok_or(BufferError::Unavailable)?;
        if entry.prefix != Some(entry.bytes.len()) {
            return Err(BufferError::State);
        }
        if sha256_hex(&entry.bytes) != entry.manifest.payload_sha256 {
            return Err(BufferError::Conflict);
        }
        Ok((&entry.manifest, &entry.bytes))
    }

    /// Check one append without changing its prefix or copying its complete payload.
    pub fn check_append(
        &self,
        reference: &BufferRef,
        chunk: &BufferChunk,
    ) -> Result<(), BufferError> {
        self.check_ref(reference)?;
        let entry = self
            .entries
            .get(&reference.buffer_id)
            .ok_or(BufferError::Unavailable)?;
        let bytes = chunk.decoded()?;
        let prefix = entry.prefix.ok_or(BufferError::State)?;
        if entry.manifest.imported_manifest_digest.as_ref() != Some(&chunk.manifest_digest)
            || chunk.offset != prefix
            || bytes.len() != (entry.bytes.len() - prefix).min(CHUNK_BYTES)
        {
            return Err(BufferError::Conflict);
        }
        Ok(())
    }

    /// Check a named release category without releasing any bytes.
    pub fn check_release(
        &self,
        reference: &BufferRef,
        incomplete: bool,
    ) -> Result<(), BufferError> {
        self.check_ref(reference)?;
        let entry = self
            .entries
            .get(&reference.buffer_id)
            .ok_or(BufferError::Unavailable)?;
        if entry.prefix.is_some() != incomplete {
            return Err(BufferError::State);
        }
        Ok(())
    }

    /// Allocate all output storage before an engine mutation. Dropping an unentered
    /// reservation cancels only core-owned bytes; it performs no external cleanup.
    pub fn reserve_outputs(
        &mut self,
        specs: &[OutputSpec],
    ) -> Result<OutputReservation<'_>, BufferError> {
        self.reserve_outputs_inner(specs, None)
    }

    /// Reserve selected sealed inputs and outputs before execution. Inputs borrow
    /// existing immutable payloads; only their closed bounded roster is copied.
    pub fn reserve_execution(
        &mut self,
        inputs: &[InputSpec],
        outputs: &[OutputSpec],
    ) -> Result<OutputReservation<'_>, BufferError> {
        self.reserve_execution_inner(inputs, outputs, None)
    }

    fn sealed_input(&self, spec: &InputSpec) -> Result<InputView<'_>, BufferError> {
        self.check_ref(&spec.reference)?;
        if !digest(&spec.expected_manifest_digest) {
            return Err(BufferError::Wire);
        }
        let entry = self
            .entries
            .get(&spec.reference.buffer_id)
            .ok_or(BufferError::Unavailable)?;
        if entry.prefix.is_some() {
            return Err(BufferError::State);
        }
        if entry.manifest.manifest_digest != spec.expected_manifest_digest {
            return Err(BufferError::Conflict);
        }
        Ok(InputView {
            manifest: &entry.manifest,
            bytes: &entry.bytes,
        })
    }

    fn reserve_outputs_inner(
        &mut self,
        specs: &[OutputSpec],
        fail_at: Option<usize>,
    ) -> Result<OutputReservation<'_>, BufferError> {
        self.reserve_execution_inner(&[], specs, fail_at)
    }

    fn reserve_execution_inner(
        &mut self,
        inputs: &[InputSpec],
        specs: &[OutputSpec],
        fail_at: Option<usize>,
    ) -> Result<OutputReservation<'_>, BufferError> {
        if inputs.len() > LIVE_SLOTS {
            return Err(BufferError::Capacity);
        }
        for (index, input) in inputs.iter().enumerate() {
            self.sealed_input(input)?;
            // The closed fields are bounded before encoding this metadata row.
            if serde_json::to_vec(input)
                .map_err(|_| BufferError::Wire)?
                .len()
                > INPUT_SPEC_BYTES
            {
                return Err(BufferError::Capacity);
            }
            if inputs[..index]
                .iter()
                .any(|prior| prior.reference == input.reference)
            {
                return Err(BufferError::Conflict);
            }
        }
        let mut selected = Vec::new();
        selected
            .try_reserve_exact(inputs.len())
            .map_err(|_| BufferError::Capacity)?;
        selected.extend_from_slice(inputs);
        if specs.len() > LIVE_SLOTS - self.entries.len()
            || (!specs.is_empty()
                && self
                    .next_id
                    .checked_add(specs.len() as u64 - 1)
                    .is_none_or(|id| id > MAX_ID))
        {
            return Err(BufferError::Capacity);
        }
        let mut total = 0usize;
        for spec in specs {
            if spec.byte_length == 0
                || spec.byte_length > BUFFER_BYTES
                || self.semantics.binary_search(&spec.semantic_digest).is_err()
            {
                return Err(BufferError::Capacity);
            }
            total = total
                .checked_add(spec.byte_length)
                .ok_or(BufferError::Capacity)?;
        }
        if total > ENDPOINT_BYTES - self.reserved {
            return Err(BufferError::Capacity);
        }
        let mut slots = Vec::new();
        slots
            .try_reserve_exact(specs.len())
            .map_err(|_| BufferError::Capacity)?;
        for (index, spec) in specs.iter().enumerate() {
            if fail_at == Some(index) {
                return Err(BufferError::Capacity);
            }
            let mut bytes = Vec::new();
            bytes
                .try_reserve_exact(spec.byte_length)
                .map_err(|_| BufferError::Capacity)?;
            bytes.resize(spec.byte_length, 0);
            slots.push(OutputSlot {
                spec: spec.clone(),
                bytes: Some(bytes),
                prefix: 0,
                id: 0,
            });
        }
        if fail_at == Some(specs.len()) {
            return Err(BufferError::Capacity);
        }
        Ok(OutputReservation {
            pool: self,
            slots,
            inputs: selected,
            context: None,
            failed: false,
        })
    }

    /// Reserve an entire import before the owner consumes its operation sequence.
    pub fn reserve_import<'a>(
        &'a mut self,
        context: &TrustedHostCreationContext,
        source: &BufferManifest,
        expected: &BufferBinding,
    ) -> Result<ImportReservation<'a>, BufferError> {
        source.verify(expected)?;
        self.admit(context, &source.semantic_digest, source.byte_length, true)?;
        let manifest = self.manifest(
            context,
            &source.semantic_digest,
            source.byte_length,
            source.payload_sha256.clone(),
            Some(source.manifest_digest.clone()),
        )?;
        let mut bytes = Vec::new();
        bytes
            .try_reserve_exact(source.byte_length)
            .map_err(|_| BufferError::Capacity)?;
        bytes.resize(source.byte_length, 0);
        Ok(ImportReservation {
            pool: self,
            manifest,
            bytes,
        })
    }
}

/// One closed bounded producer slot. This is local demand, never a peer method.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct OutputSpec {
    pub semantic_digest: String,
    pub byte_length: usize,
}

/// One local sealed-buffer selection. It grants no producer authenticity.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct InputSpec {
    pub reference: BufferRef,
    pub expected_manifest_digest: String,
}

/// Immutable payload access tied to the exclusive execution-ticket borrow.
pub struct InputView<'a> {
    manifest: &'a BufferManifest,
    bytes: &'a [u8],
}
impl InputView<'_> {
    pub fn manifest(&self) -> &BufferManifest {
        self.manifest
    }
    pub fn bytes(&self) -> &[u8] {
        self.bytes
    }
}

struct OutputSlot {
    spec: OutputSpec,
    bytes: Option<Vec<u8>>,
    prefix: usize,
    id: u64,
}

/// Exclusive local ticket. No application destructor or fallible external cleanup
/// runs when it is canceled. Published outputs remain owned by the pool.
pub struct OutputReservation<'a> {
    pool: &'a mut BufferPool,
    slots: Vec<OutputSlot>,
    inputs: Vec<InputSpec>,
    context: Option<TrustedHostCreationContext>,
    failed: bool,
}

impl OutputReservation<'_> {
    /// Only the pre-admitted input roster is readable during this execution.
    pub fn input(&self, index: usize) -> Result<InputView<'_>, BufferError> {
        if self.failed || self.context.is_none() {
            return Err(BufferError::State);
        }
        self.pool
            .sealed_input(self.inputs.get(index).ok_or(BufferError::Unavailable)?)
    }

    pub fn usage(&self) -> BufferUsage {
        let mut usage = self.pool.usage();
        for slot in &self.slots {
            if let Some(bytes) = &slot.bytes {
                usage.reserved_bytes += bytes.len();
                usage.live_slots += 1;
            }
        }
        usage
    }

    /// Consume IDs only after the host crosses its verified execution boundary.
    pub fn enter(&mut self, context: TrustedHostCreationContext) -> Result<(), BufferError> {
        if self.failed || self.context.is_some() || context.binding != self.pool.binding {
            self.failed = true;
            return Err(BufferError::Binding);
        }
        for slot in &mut self.slots {
            slot.id = self.pool.next_id;
            self.pool.next_id += 1;
        }
        self.context = Some(context);
        Ok(())
    }

    /// Write one contiguous bounded portion into already reserved owned storage.
    /// Errors latch, so ignoring a failed call cannot create a complete result.
    pub fn write(&mut self, index: usize, offset: usize, input: &[u8]) -> Result<(), BufferError> {
        let result = (|| {
            if self.failed
                || self.context.is_none()
                || input.is_empty()
                || input.len() > CHUNK_BYTES
            {
                return Err(BufferError::State);
            }
            let slot = self.slots.get_mut(index).ok_or(BufferError::Unavailable)?;
            let bytes = slot.bytes.as_mut().ok_or(BufferError::State)?;
            if offset != slot.prefix || input.len() > bytes.len() - slot.prefix {
                return Err(BufferError::Conflict);
            }
            let end = offset + input.len();
            bytes[offset..end].copy_from_slice(input);
            slot.prefix = end;
            Ok(())
        })();
        if result.is_err() {
            self.failed = true;
        }
        result
    }

    /// Publish the same owned allocation only after every byte is present.
    pub fn seal(&mut self, index: usize) -> Result<BufferManifest, BufferError> {
        let result = (|| {
            if self.failed {
                return Err(BufferError::State);
            }
            let context = self.context.as_ref().ok_or(BufferError::State)?;
            let slot = self.slots.get_mut(index).ok_or(BufferError::Unavailable)?;
            let bytes = slot.bytes.as_ref().ok_or(BufferError::State)?;
            if slot.prefix != bytes.len() {
                return Err(BufferError::State);
            }
            let manifest = self.pool.manifest_at(
                slot.id,
                context,
                &slot.spec.semantic_digest,
                bytes.len(),
                sha256_hex(bytes),
                None,
            )?;
            let bytes = slot.bytes.take().ok_or(BufferError::State)?;
            self.pool.reserved += bytes.len();
            self.pool.entries.insert(
                slot.id,
                Entry {
                    manifest: manifest.clone(),
                    bytes,
                    prefix: None,
                },
            );
            Ok(manifest)
        })();
        if result.is_err() {
            self.failed = true;
        }
        result
    }

    /// Every promised output is sealed, and no ignored error occurred.
    pub fn complete(&self) -> bool {
        self.context.is_some() && !self.failed && self.slots.iter().all(|slot| slot.bytes.is_none())
    }
}

/// Full import allocation awaiting the host's operation execution boundary.
pub struct ImportReservation<'a> {
    pool: &'a mut BufferPool,
    manifest: BufferManifest,
    bytes: Vec<u8>,
}

impl ImportReservation<'_> {
    pub fn commit(self) -> BufferRef {
        let reference = self.manifest.reference();
        self.pool.reserved += self.bytes.len();
        self.pool.entries.insert(
            reference.buffer_id,
            Entry {
                manifest: self.manifest,
                bytes: self.bytes,
                prefix: Some(0),
            },
        );
        self.pool.next_id += 1;
        reference
    }
}

/// Check host-declared endpoint reservations, counting source and destination independently.
pub fn admit_composition(reservations: &[usize]) -> Result<usize, BufferError> {
    if reservations.is_empty() || reservations.len() > ENDPOINTS {
        return Err(BufferError::Capacity);
    }
    let mut sum = 0;
    for &bytes in reservations {
        if bytes > ENDPOINT_BYTES || bytes > COMPOSITION_BYTES - sum {
            return Err(BufferError::Capacity);
        }
        sum += bytes;
    }
    Ok(sum)
}

#[cfg(test)]
mod counter_controls {
    use super::*;

    fn binding() -> BufferBinding {
        BufferBinding {
            profile_digest: "1".repeat(64),
            application_digest: "2".repeat(64),
            run_id: "10000000-0000-4000-8000-000000000001".into(),
            endpoint_id: "10000000-0000-4000-8000-000000000002".into(),
            generation: "10000000-0000-4000-8000-000000000003".into(),
        }
    }

    #[test]
    fn staged_allocation_failure_and_cancellation_preserve_every_pool_counter() {
        let mut pool = BufferPool::new(binding(), vec!["5".repeat(64)]).unwrap();
        let specs = vec![
            OutputSpec {
                semantic_digest: "5".repeat(64),
                byte_length: 17
            };
            3
        ];
        let before = pool.usage();
        for fail in 0..=specs.len() {
            assert!(pool.reserve_outputs_inner(&specs, Some(fail)).is_err());
            assert_eq!(pool.usage(), before);
        }
        {
            let ticket = pool.reserve_outputs(&specs).unwrap();
            assert_eq!(ticket.usage().reserved_bytes, 51);
            assert_eq!(ticket.usage().next_id, before.next_id);
        }
        assert_eq!(pool.usage(), before);
    }

    #[test]
    fn selected_inputs_survive_canceled_output_staging_and_require_entered_lease() {
        let mut pool = BufferPool::new(binding(), vec!["5".repeat(64)]).unwrap();
        let context = TrustedHostCreationContext::new(binding(), "3".repeat(64), None).unwrap();
        let manifest = pool.publish(&context, &"5".repeat(64), b"owned").unwrap();
        let inputs = [InputSpec {
            reference: manifest.reference(),
            expected_manifest_digest: manifest.manifest_digest.clone(),
        }];
        let outputs = [OutputSpec {
            semantic_digest: "5".repeat(64),
            byte_length: 17,
        }];
        let before = pool.usage();
        for fail in 0..=outputs.len() {
            assert!(pool
                .reserve_execution_inner(&inputs, &outputs, Some(fail))
                .is_err());
            assert_eq!(pool.usage(), before);
            assert_eq!(
                pool.read(&manifest.reference(), 0)
                    .unwrap()
                    .decoded()
                    .unwrap(),
                b"owned"
            );
        }
        {
            let mut ticket = pool.reserve_execution(&inputs, &[]).unwrap();
            assert!(ticket.input(0).is_err());
            ticket.enter(context).unwrap();
            let view = ticket.input(0).unwrap();
            assert_eq!(view.bytes(), b"owned");
            assert_eq!(view.manifest(), &manifest);
        }
        assert_eq!(pool.usage(), before);
        pool.release(&manifest.reference()).unwrap();
        assert!(pool.reserve_execution(&inputs, &[]).is_err());
    }

    #[test]
    fn reservation_publishes_owned_bytes_and_latches_ignored_write_errors() {
        let mut pool = BufferPool::new(binding(), vec!["5".repeat(64)]).unwrap();
        let specs = [OutputSpec {
            semantic_digest: "5".repeat(64),
            byte_length: 3,
        }];
        let manifest = {
            let mut ticket = pool.reserve_outputs(&specs).unwrap();
            ticket
                .enter(TrustedHostCreationContext::new(binding(), "3".repeat(64), None).unwrap())
                .unwrap();
            ticket.write(0, 0, b"abc").unwrap();
            let manifest = ticket.seal(0).unwrap();
            assert!(ticket.complete());
            assert_eq!(ticket.usage().live_slots, 1);
            manifest
        };
        assert_eq!(
            pool.read(&manifest.reference(), 0)
                .unwrap()
                .decoded()
                .unwrap(),
            b"abc"
        );
        pool.release(&manifest.reference()).unwrap();
        let mut ticket = pool.reserve_outputs(&specs).unwrap();
        ticket
            .enter(TrustedHostCreationContext::new(binding(), "4".repeat(64), None).unwrap())
            .unwrap();
        assert!(ticket.write(0, 1, b"x").is_err());
        assert!(ticket.write(0, 0, b"abc").is_err());
        assert!(!ticket.complete());
    }

    #[test]
    fn empty_ticket_cannot_publish_and_foreign_context_consumes_no_id() {
        let mut pool = BufferPool::new(binding(), vec!["5".repeat(64)]).unwrap();
        let before = pool.usage();
        {
            let mut ticket = pool.reserve_outputs(&[]).unwrap();
            let mut foreign = binding();
            foreign.generation = "20000000-0000-4000-8000-000000000003".into();
            assert!(ticket
                .enter(TrustedHostCreationContext::new(foreign, "3".repeat(64), None).unwrap())
                .is_err());
        }
        assert_eq!(pool.usage(), before);
        {
            let mut ticket = pool.reserve_outputs(&[]).unwrap();
            ticket
                .enter(TrustedHostCreationContext::new(binding(), "3".repeat(64), None).unwrap())
                .unwrap();
            assert!(ticket.complete());
            assert!(ticket.seal(0).is_err());
            assert!(!ticket.complete());
        }
        assert_eq!(pool.usage(), before);
    }

    #[test]
    fn final_representable_id_is_used_once_then_exhaustion_preserves_state() {
        let binding = BufferBinding {
            profile_digest: "1".repeat(64),
            application_digest: "2".repeat(64),
            run_id: "10000000-0000-4000-8000-000000000001".into(),
            endpoint_id: "10000000-0000-4000-8000-000000000002".into(),
            generation: "10000000-0000-4000-8000-000000000003".into(),
        };
        let context =
            TrustedHostCreationContext::new(binding.clone(), "3".repeat(64), None).unwrap();
        let mut pool = BufferPool::new(binding, vec!["5".repeat(64)]).unwrap();
        pool.next_id = MAX_ID;
        let last = pool.publish(&context, &"5".repeat(64), b"x").unwrap();
        assert_eq!(last.buffer_id, MAX_ID);
        pool.release(&last.reference()).unwrap();
        let before = pool.usage();
        assert_eq!(
            pool.publish(&context, &"5".repeat(64), b"x"),
            Err(BufferError::Capacity)
        );
        assert_eq!(pool.usage(), before);
    }
}
