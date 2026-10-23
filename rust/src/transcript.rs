//! Transcripts: records of the frames that one program sent and received (section 10).

use crate::exchange::{check_request, check_response};
use crate::frame::{self, FrameError, MAX_BOUND};
use std::collections::HashMap;
use std::fs::File;
use std::io::{self, BufWriter, Read, Write};
use std::path::Path;
use std::sync::Mutex;
use std::time::Instant;

/// The first 8 bytes of a transcript file.
pub const FILE_MAGIC: [u8; 8] = *b"NCPT\x00\x00\x00\x01";
/// Record kind of a sent frame.
pub const SENT: u8 = 1;
/// Record kind of a received frame.
pub const RECEIVED: u8 = 2;

/// Append every frame that a channel sends or receives to a transcript file.
#[derive(Debug)]
pub struct Tap {
    file: Mutex<BufWriter<File>>,
    origin: Instant,
}

impl Tap {
    /// Create a new transcript file. Fails if the file exists.
    pub fn create(path: impl AsRef<Path>) -> io::Result<Tap> {
        let file = File::options().write(true).create_new(true).open(path)?;
        let mut writer = BufWriter::with_capacity(1 << 20, file);
        writer.write_all(&FILE_MAGIC)?;
        Ok(Tap {
            file: Mutex::new(writer),
            origin: Instant::now(),
        })
    }

    /// Record one frame.
    pub fn record(&self, kind: u8, frame: &[u8]) {
        let nanos = self.origin.elapsed().as_nanos() as u64;
        if let Ok(mut file) = self.file.lock() {
            let _ = file.write_all(&[kind]);
            let _ = file.write_all(&nanos.to_be_bytes());
            let _ = file.write_all(&(frame.len() as u32).to_be_bytes());
            let _ = file.write_all(frame);
        }
    }

    /// Flush the file.
    pub fn flush(&self) -> io::Result<()> {
        self.file
            .lock()
            .map_err(|_| io::Error::other("tap lock"))?
            .flush()
    }
}

/// One transcript record.
#[derive(Debug, Clone)]
pub struct Record {
    /// SENT or RECEIVED.
    pub kind: u8,
    /// Monotonic time in nanoseconds.
    pub time_ns: u64,
    /// The frame bytes.
    pub frame: Vec<u8>,
}

/// Read all records of a transcript file.
pub fn read(path: impl AsRef<Path>) -> Result<Vec<Record>, FrameError> {
    let mut data = Vec::new();
    File::open(path)
        .and_then(|mut f| f.read_to_end(&mut data))
        .map_err(|e| FrameError(e.to_string()))?;
    if data.len() < 8 || data[..8] != FILE_MAGIC {
        return Err(FrameError("transcript magic".into()));
    }
    let mut records = Vec::new();
    let mut at = 8;
    while at < data.len() {
        if data.len() - at < 13 {
            return Err(FrameError("truncated transcript record".into()));
        }
        let kind = data[at];
        let time_ns = u64::from_be_bytes(data[at + 1..at + 9].try_into().unwrap_or_default());
        let length =
            u32::from_be_bytes(data[at + 9..at + 13].try_into().unwrap_or_default()) as usize;
        at += 13;
        if data.len() - at < length || !(kind == SENT || kind == RECEIVED) {
            return Err(FrameError("truncated or unknown transcript record".into()));
        }
        records.push(Record {
            kind,
            time_ns,
            frame: data[at..at + length].to_vec(),
        });
        at += length;
    }
    Ok(records)
}

/// The verification result of one session.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct SessionReport {
    /// "client" or "owner", from the direction of the open request.
    pub role: String,
    /// Distinct requests.
    pub requests: usize,
    /// Whether the transcript has the open request, a response to every request, and the
    /// response to close.
    pub complete: bool,
    /// The code of an ending response, if any.
    pub ended: Option<String>,
    /// Problems found.
    pub problems: Vec<String>,
}

/// Verify every exchange session of a transcript (section 10): frame digests, sequence numbers,
/// request identities, and the hash chain.
pub fn verify(path: impl AsRef<Path>) -> Result<HashMap<String, SessionReport>, FrameError> {
    let mut sessions: HashMap<String, SessionReport> = HashMap::new();
    let mut pending: HashMap<String, (u64, String, String)> = HashMap::new();
    let mut last_response: HashMap<String, String> = HashMap::new();
    let mut next_seq: HashMap<String, u64> = HashMap::new();
    for record in read(path)? {
        let decoded = match frame::decode(record.frame.clone(), MAX_BOUND) {
            Ok(decoded) => decoded,
            Err(error) => {
                sessions
                    .entry("?".into())
                    .or_default()
                    .problems
                    .push(format!("{error}"));
                continue;
            }
        };
        let message = &decoded.message;
        if message.get("op").is_some() {
            check_request(message)?;
            let session = message["session"].as_str().unwrap_or_default().to_owned();
            let seq = message["seq"].as_u64().unwrap_or_default();
            let report = sessions
                .entry(session.clone())
                .or_insert_with(|| SessionReport {
                    role: if record.kind == SENT {
                        "client".into()
                    } else {
                        "owner".into()
                    },
                    ..SessionReport::default()
                });
            if let Some((pending_seq, pending_id, _)) = pending.get(&session) {
                if *pending_seq == seq {
                    if *pending_id != decoded.identity {
                        report.problems.push(format!("seq {seq}: changed request"));
                    }
                    continue;
                }
            }
            let expected = next_seq.get(&session).copied().unwrap_or(0);
            if seq != expected {
                report
                    .problems
                    .push(format!("seq {seq}: expected {expected}"));
            }
            if seq == 0 {
                if message["op"] != "open" || !message["ack"].is_null() {
                    report
                        .problems
                        .push("seq 0 is not an open without ack".into());
                }
            } else if message["ack"].as_str() != last_response.get(&session).map(String::as_str) {
                report.problems.push(format!(
                    "seq {seq}: ack does not name the previous response"
                ));
            }
            pending.insert(
                session,
                (
                    seq,
                    decoded.identity.clone(),
                    message["op"].as_str().unwrap_or_default().to_owned(),
                ),
            );
            report.requests += 1;
        } else if message.get("outcome").is_some() {
            check_response(message)?;
            let Some(session) = message["session"].as_str().map(str::to_owned) else {
                let code = message["code"].as_str().unwrap_or_default().to_owned();
                for report in sessions.values_mut() {
                    if report.ended.is_none() {
                        report.ended = Some(code.clone());
                    }
                }
                continue;
            };
            let report = sessions.entry(session.clone()).or_default();
            let Some((seq, request_id, op)) = pending.get(&session).cloned() else {
                if last_response.get(&session) != Some(&decoded.identity) {
                    report
                        .problems
                        .push(format!("seq {}: response without request", message["seq"]));
                }
                continue;
            };
            if message["seq"] != seq || message["request"] != request_id.as_str() {
                report.problems.push(format!(
                    "seq {}: response names another request",
                    message["seq"]
                ));
                continue;
            }
            pending.remove(&session);
            match message["outcome"].as_str() {
                Some("rejected") => continue,
                Some("ended") => report.ended = message["code"].as_str().map(str::to_owned),
                _ => {
                    if op == "close" {
                        report.complete = true;
                    }
                }
            }
            last_response.insert(session.clone(), decoded.identity.clone());
            next_seq.insert(session, seq + 1);
        }
    }
    for (session, (seq, _, _)) in pending {
        sessions
            .entry(session)
            .or_default()
            .problems
            .push(format!("seq {seq}: no response"));
    }
    Ok(sessions)
}
