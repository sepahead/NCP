//! Test-only process probe for independent modular primitive parity.
//! It is not an application endpoint or an NCP command envelope.

use std::io::{self, Read, Write};

use ncp_core::local::{read_local_frame, write_local_frame};
use ncp_core::modular_buffer::*;
use serde::Deserialize;
use serde_json::{json, Value};

#[derive(Deserialize)]
#[serde(tag = "operation", rename_all = "snake_case", deny_unknown_fields)]
enum Probe {
    Bounds,
    Decode {
        data_base64: String,
    },
    Chunk {
        wire: String,
    },
    Manifest {
        wire: String,
        binding: BufferBinding,
    },
    Transfer {
        data_hex: String,
        binding: BufferBinding,
        target: BufferBinding,
        request_digest: String,
        predecessor: Option<String>,
        semantic_digest: String,
    },
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

fn unhex(text: &str) -> Result<Vec<u8>, BufferError> {
    if !text.len().is_multiple_of(2) || text.len() > (CHUNK_BYTES + 7) * 2 {
        return Err(BufferError::Wire);
    }
    text.as_bytes()
        .chunks_exact(2)
        .map(|pair| {
            let value = |b: u8| match b {
                b'0'..=b'9' => Ok(b - b'0'),
                b'a'..=b'f' => Ok(b - b'a' + 10),
                _ => Err(BufferError::Wire),
            };
            Ok(value(pair[0])? * 16 + value(pair[1])?)
        })
        .collect()
}

fn run(probe: Probe) -> Result<Value, BufferError> {
    match probe {
        Probe::Bounds => Ok(
            json!({"FRAME_BYTES": FRAME_BYTES, "CHUNK_BYTES": CHUNK_BYTES,
            "BUFFER_BYTES": BUFFER_BYTES, "ENDPOINT_BYTES": ENDPOINT_BYTES, "COMPOSITION_BYTES": COMPOSITION_BYTES,
            "LIVE_SLOTS": LIVE_SLOTS, "INCOMPLETE_SLOTS": INCOMPLETE_SLOTS, "ENDPOINTS": ENDPOINTS,
            "MANIFEST_BYTES": MANIFEST_BYTES, "SEMANTIC_SLOTS": SEMANTIC_SLOTS, "METADATA_BYTES": METADATA_BYTES,
            "DIGEST_STAGING_BYTES": DIGEST_STAGING_BYTES, "MAX_ID": MAX_ID}),
        ),
        Probe::Decode { data_base64 } => Ok(json!({"hex": hex(&decode_chunk(&data_base64)?)})),
        Probe::Chunk { wire } => Ok(json!({"chunk": BufferChunk::from_json(wire.as_bytes())?})),
        Probe::Manifest { wire, binding } => {
            Ok(json!({"manifest": BufferManifest::from_json(wire.as_bytes(), &binding)?}))
        }
        Probe::Transfer {
            data_hex,
            binding,
            target,
            request_digest,
            predecessor,
            semantic_digest,
        } => {
            let data = unhex(&data_hex)?;
            let source_context = TrustedHostCreationContext::new(
                binding.clone(),
                request_digest.clone(),
                predecessor.clone(),
            )?;
            let target_context =
                TrustedHostCreationContext::new(target.clone(), request_digest, predecessor)?;
            let mut producer = BufferPool::new(binding.clone(), vec![semantic_digest.clone()])?;
            let mut receiver = BufferPool::new(target, vec![semantic_digest.clone()])?;
            let source = producer.publish(&source_context, &semantic_digest, &data)?;
            let handle = receiver.begin_import(&target_context, &source, &binding)?;
            for index in 0..source.chunk_count {
                let wire = producer.read(&source.reference(), index)?.to_json()?;
                receiver.append(&handle, &BufferChunk::from_json(&wire)?)?;
            }
            let destination = receiver.seal(&handle)?;
            let mut restored = Vec::new();
            for index in 0..destination.chunk_count {
                restored.extend(receiver.read(&handle, index)?.decoded()?);
            }
            if restored != data {
                return Err(BufferError::Conflict);
            }
            Ok(json!({"source": source, "destination": destination,
                "source_reserved_bytes": producer.usage().reserved_bytes,
                "destination_reserved_bytes": receiver.usage().reserved_bytes}))
        }
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    if std::env::args().nth(1).as_deref() == Some("--maximum-import-control") {
        return maximum_import_control();
    }
    let mut input = Vec::new();
    io::stdin().take(262_145).read_to_end(&mut input)?;
    let result = if input.len() > 262_144 {
        Err(BufferError::Capacity)
    } else {
        serde_json::from_slice::<Probe>(&input)
            .map_err(|_| BufferError::Wire)
            .and_then(run)
    };
    let output = match result {
        Ok(value) => json!({"ok": value}),
        Err(error) => json!({"error": match error {
            BufferError::Wire => "wire", BufferError::Binding => "binding", BufferError::Capacity => "capacity",
            BufferError::Conflict => "conflict", BufferError::Unavailable => "unavailable", BufferError::State => "state",
        }}),
    };
    serde_json::to_writer(io::stdout(), &output)?;
    Ok(())
}

fn emit(writer: &mut impl Write, value: &Value) -> Result<(), Box<dyn std::error::Error>> {
    write_local_frame(writer, &serde_json::to_vec(value)?)?;
    Ok(())
}

fn usage(value: BufferUsage) -> Value {
    json!({"reserved_bytes": value.reserved_bytes, "live_slots": value.live_slots,
        "incomplete_slots": value.incomplete_slots, "next_id": value.next_id})
}

/// Separately selected maximum structural case. All ingress frames remain bounded.
/// This fixture mode has no application role, command execution, or release claim.
fn maximum_import_control() -> Result<(), Box<dyn std::error::Error>> {
    let source_binding = BufferBinding {
        profile_digest: "1".repeat(64),
        application_digest: "2".repeat(64),
        run_id: "10000000-0000-4000-8000-000000000001".into(),
        endpoint_id: "10000000-0000-4000-8000-000000000002".into(),
        generation: "10000000-0000-4000-8000-000000000003".into(),
    };
    let target_binding = BufferBinding {
        generation: "10000000-0000-4000-8000-000000000004".into(),
        ..source_binding.clone()
    };
    let context = TrustedHostCreationContext::new(
        target_binding.clone(),
        "3".repeat(64),
        Some("4".repeat(64)),
    )?;
    let mut pool = BufferPool::new(target_binding, vec!["5".repeat(64)])?;
    let mut reader = io::stdin().lock();
    let mut writer = io::stdout().lock();
    let wire = read_local_frame(&mut reader)?.ok_or(BufferError::Wire)?;
    let source = BufferManifest::from_json(&wire, &source_binding)?;
    if source.byte_length != BUFFER_BYTES || source.chunk_count != BUFFER_BYTES / CHUNK_BYTES {
        return Err(BufferError::Wire.into());
    }
    let reference = pool.begin_import(&context, &source, &source_binding)?;
    emit(&mut writer, &json!({"reservation": usage(pool.usage())}))?;
    for index in 0..source.chunk_count {
        let wire = read_local_frame(&mut reader)?.ok_or(BufferError::Wire)?;
        let chunk = BufferChunk::from_json(&wire)?;
        pool.append(&reference, &chunk)?;
        emit(
            &mut writer,
            &json!({"accepted_index": index, "accepted_bytes": (index + 1) * CHUNK_BYTES}),
        )?;
    }
    let before = pool.usage();
    match pool.seal(&reference) {
        Ok(manifest) => {
            emit(
                &mut writer,
                &json!({"sealed": manifest, "usage": usage(pool.usage())}),
            )?;
            for index in 0..manifest.chunk_count {
                write_local_frame(&mut writer, &pool.read(&reference, index)?.to_json()?)?;
            }
            pool.release(&reference)?;
            let duplicate_unavailable = pool.release(&reference) == Err(BufferError::Unavailable);
            emit(
                &mut writer,
                &json!({"released": usage(pool.usage()), "duplicate_release_unavailable": duplicate_unavailable}),
            )?;
        }
        Err(BufferError::Conflict) => {
            if pool.usage() != before || pool.read(&reference, 0) != Err(BufferError::State) {
                return Err(BufferError::State.into());
            }
            emit(
                &mut writer,
                &json!({"seal_error": "conflict", "usage": usage(pool.usage())}),
            )?;
            pool.abort_import(&reference)?;
            emit(&mut writer, &json!({"aborted": usage(pool.usage())}))?;
        }
        Err(error) => return Err(error.into()),
    }
    Ok(())
}
