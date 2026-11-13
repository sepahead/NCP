//! Transcripts: records of the frames that one program sent and received (section 10).
//!
//! A verified transcript is internally consistent: it shows which frames the recorder sent and
//! received, and in which order, as far as the file can be trusted. Without a key, anyone can
//! write a transcript that verifies. With a key (section 13.2), only a holder of the key can.

use crate::frame::{self, digest_of, same_digest, FrameError, Key, Verify, MAX_BOUND};
use crate::messages::{check_request, check_response, check_stream_message, kind};
use crate::owner::IMPLEMENTATION;
use serde_json::{json, Value};
use std::collections::{HashMap, HashSet};
use std::fs::File;
use std::io::{self, BufReader, BufWriter, Read, Write};
use std::path::Path;
use std::sync::Mutex;
use std::time::{Instant, SystemTime, UNIX_EPOCH};

/// The first 8 bytes of a transcript file of version 2.
pub const FILE_MAGIC: [u8; 8] = *b"NCPT\x00\x00\x00\x02";
/// The first 8 bytes of a transcript file of version 1.
pub const FILE_MAGIC_V1: [u8; 8] = *b"NCPT\x00\x00\x00\x01";
/// Record kind of a sent frame.
pub const SENT: u8 = 1;
/// Record kind of a received frame.
pub const RECEIVED: u8 = 2;
/// Record kind of the end record.
pub const END: u8 = 3;
/// The largest transcript header.
pub const MAX_HEADER: usize = 4096;

fn rfc3339_now() -> String {
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default();
    let (seconds, nanos) = (now.as_secs() as i64, now.subsec_nanos());
    let days = seconds.div_euclid(86_400);
    let rest = seconds.rem_euclid(86_400);
    // Civil date from days since 1970-01-01 (Howard Hinnant's algorithm).
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z.rem_euclid(146_097);
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = if mp < 10 { mp + 3 } else { mp - 9 };
    let year = yoe + era * 400 + i64::from(month <= 2);
    format!(
        "{year:04}-{month:02}-{day:02}T{:02}:{:02}:{:02}.{nanos:09}Z",
        rest / 3600,
        rest % 3600 / 60,
        rest % 60
    )
}

struct TapState {
    file: BufWriter<File>,
    chain: [u8; 32],
    count: u64,
    closed: bool,
}

/// Append every frame that a channel sends or receives to a transcript file (section 10).
///
/// A tap from [`Tap::create`] gives each record to the operating system at once, so the
/// transcript keeps every record up to a crash of this program. A tap from
/// [`Tap::create_buffered`] collects records in a buffer of 1 MiB: one system call fewer for each
/// frame, but a crash loses the records in the buffer. [`Tap::close`] writes the end record; a
/// tap that is dropped closes itself.
pub struct Tap {
    state: Mutex<TapState>,
    origin: Instant,
    buffered: bool,
    key: Option<Key>,
}

impl std::fmt::Debug for Tap {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Tap")
            .field("buffered", &self.buffered)
            .finish_non_exhaustive()
    }
}

/// Options of a new transcript.
#[derive(Debug, Default, Clone)]
pub struct TapOptions {
    /// The name of the recorder, at most 256 characters.
    pub recorder: String,
    /// Collect records in a buffer of 1 MiB.
    pub buffered: bool,
    /// The key of an authenticated session: the chain then uses HMAC-SHA-256 (section 13.2).
    pub key: Option<Key>,
    /// The start time to write, instead of now (for reproducible files).
    pub started: Option<String>,
}

impl Tap {
    /// Create a new transcript file that receives each record at once. Fails if the file exists.
    pub fn create(path: impl AsRef<Path>) -> io::Result<Tap> {
        Tap::with_options(path, TapOptions::default())
    }

    /// Create a new transcript file whose records collect in a buffer of 1 MiB.
    pub fn create_buffered(path: impl AsRef<Path>) -> io::Result<Tap> {
        Tap::with_options(
            path,
            TapOptions {
                buffered: true,
                ..TapOptions::default()
            },
        )
    }

    /// Create a new transcript file with options.
    pub fn with_options(path: impl AsRef<Path>, options: TapOptions) -> io::Result<Tap> {
        let recorder: String = options.recorder.chars().take(256).collect();
        let header = json!({
            "recorder": recorder,
            "implementation": IMPLEMENTATION,
            "started": options.started.unwrap_or_else(rfc3339_now),
            "chain": if options.key.is_some() { "hmac-sha256" } else { "sha256" },
        });
        let header = serde_json::to_vec(&header).map_err(io::Error::other)?;
        if header.len() > MAX_HEADER {
            return Err(io::Error::other("the transcript header exceeds 4096 bytes"));
        }
        let file = File::options().write(true).create_new(true).open(path)?;
        let mut writer = BufWriter::with_capacity(1 << 20, file);
        let mut start = FILE_MAGIC.to_vec();
        start.extend_from_slice(&(header.len() as u32).to_be_bytes());
        start.extend_from_slice(&header);
        writer.write_all(&start)?;
        if !options.buffered {
            writer.flush()?;
        }
        Ok(Tap {
            state: Mutex::new(TapState {
                file: writer,
                chain: digest_of(options.key.as_ref(), &[&start]),
                count: 0,
                closed: false,
            }),
            origin: Instant::now(),
            buffered: options.buffered,
            key: options.key,
        })
    }

    /// Record one frame. A failure to write is an error, so that a session never runs on
    /// without its record.
    pub fn record(&self, kind: u8, frame: &[u8]) -> io::Result<()> {
        if kind != SENT && kind != RECEIVED {
            return Err(io::Error::other("kind must be SENT or RECEIVED"));
        }
        let nanos = self.origin.elapsed().as_nanos() as u64;
        let mut head = [0u8; 13];
        head[0] = kind;
        head[1..9].copy_from_slice(&nanos.to_be_bytes());
        head[9..13].copy_from_slice(&(frame.len() as u32).to_be_bytes());
        let mut state = self
            .state
            .lock()
            .map_err(|_| io::Error::other("tap lock"))?;
        if state.closed {
            return Err(io::Error::other("the transcript is closed"));
        }
        let tail = &frame[frame.len().saturating_sub(frame::DIGEST_BYTES)..];
        state.chain = digest_of(self.key.as_ref(), &[&state.chain, &head, tail]);
        let chain = state.chain;
        state.file.write_all(&head)?;
        state.file.write_all(frame)?;
        state.file.write_all(&chain)?;
        state.count += 1;
        if !self.buffered {
            state.file.flush()?;
        }
        Ok(())
    }

    /// Write the records that are still in the buffer.
    pub fn flush(&self) -> io::Result<()> {
        self.state
            .lock()
            .map_err(|_| io::Error::other("tap lock"))?
            .file
            .flush()
    }

    /// Write the end record and flush.
    pub fn close(&self) -> io::Result<()> {
        let mut state = self
            .state
            .lock()
            .map_err(|_| io::Error::other("tap lock"))?;
        if state.closed {
            return Ok(());
        }
        state.closed = true;
        let nanos = self.origin.elapsed().as_nanos() as u64;
        let mut head = [0u8; 13];
        head[0] = END;
        head[1..9].copy_from_slice(&nanos.to_be_bytes());
        let count = state.count.to_be_bytes();
        state.chain = digest_of(self.key.as_ref(), &[&state.chain, &head, &count]);
        let chain = state.chain;
        state.file.write_all(&head)?;
        state.file.write_all(&chain)?;
        state.file.flush()
    }
}

impl Drop for Tap {
    fn drop(&mut self) {
        let _ = self.close();
    }
}

/// One transcript record.
#[derive(Debug, Clone)]
pub struct Record {
    /// SENT or RECEIVED.
    pub kind: u8,
    /// Nanoseconds since the recorder started.
    pub time_ns: u64,
    /// The frame bytes.
    pub frame: Vec<u8>,
    /// The chain value (version 2).
    pub chain: Option<[u8; 32]>,
}

/// A transcript file as read: its version, header, records, and how it ends.
#[derive(Debug, Clone, Default)]
pub struct Transcript {
    /// 1 or 2.
    pub version: u8,
    /// The header (version 2).
    pub header: Option<Value>,
    /// The records.
    pub records: Vec<Record>,
    /// Whether it ends with an end record.
    pub closed: bool,
    /// The offset of a record that ends before its length.
    pub truncated_at: Option<u64>,
    /// Whether every chain value matched; None for version 1 or a keyed chain without the key.
    pub chain_ok: Option<bool>,
    /// Problems of the file.
    pub problems: Vec<String>,
}

fn read_exact_or_short<R: Read>(reader: &mut R, buffer: &mut [u8]) -> io::Result<usize> {
    let mut filled = 0;
    while filled < buffer.len() {
        match reader.read(&mut buffer[filled..])? {
            0 => break,
            n => filled += n,
        }
    }
    Ok(filled)
}

/// Read a transcript record by record, calling `visit` for each record.
pub fn iterate(
    path: impl AsRef<Path>,
    key: Option<&Key>,
    mut visit: impl FnMut(Record),
) -> Result<Transcript, FrameError> {
    let file = File::open(path).map_err(|e| FrameError(e.to_string()))?;
    let mut reader = BufReader::with_capacity(1 << 20, file);
    let io_error = |e: io::Error| FrameError(e.to_string());
    let mut magic = [0u8; 8];
    if read_exact_or_short(&mut reader, &mut magic).map_err(io_error)? != 8 {
        return Err(FrameError("transcript magic".into()));
    }
    let mut out = Transcript::default();
    let mut offset = 8u64;
    let (version, start) = if magic == FILE_MAGIC_V1 {
        (1u8, Vec::new())
    } else if magic == FILE_MAGIC {
        let mut length = [0u8; 4];
        if read_exact_or_short(&mut reader, &mut length).map_err(io_error)? != 4 {
            return Err(FrameError("transcript header length".into()));
        }
        let size = u32::from_be_bytes(length) as usize;
        if size > MAX_HEADER {
            return Err(FrameError("transcript header length".into()));
        }
        let mut text = vec![0u8; size];
        if read_exact_or_short(&mut reader, &mut text).map_err(io_error)? != size {
            return Err(FrameError("transcript header".into()));
        }
        let header = frame::loads(&text)?;
        let chain = header.get("chain").and_then(Value::as_str);
        if !header.is_object() || !matches!(chain, Some("sha256" | "hmac-sha256")) {
            return Err(FrameError("transcript header members".into()));
        }
        out.header = Some(header);
        offset += 4 + size as u64;
        let mut start = magic.to_vec();
        start.extend_from_slice(&length);
        start.extend_from_slice(&text);
        (2u8, start)
    } else {
        return Err(FrameError("transcript magic".into()));
    };
    out.version = version;
    let keyed = out.header.as_ref().and_then(|h| h["chain"].as_str()) == Some("hmac-sha256");
    if key.is_some() && !keyed {
        out.problems
            .push("a key was given, but the transcript is not authenticated".into());
    }
    let check = version == 2 && (!keyed || key.is_some());
    let chain_key = if keyed { key } else { None };
    if version == 2 {
        if check {
            out.chain_ok = Some(true);
        } else {
            out.problems.push(
                "the chain and the frames are authenticated: verify them with the key".into(),
            );
        }
    }
    let mut chain = if version == 2 {
        digest_of(chain_key, &[&start])
    } else {
        [0; 32]
    };
    let mut count = 0u64;
    loop {
        let mut head = [0u8; 13];
        let got = read_exact_or_short(&mut reader, &mut head).map_err(io_error)?;
        if got == 0 {
            break;
        }
        if got != 13 {
            out.truncated_at = Some(offset);
            break;
        }
        let kind = head[0];
        let time_ns = u64::from_be_bytes(head[1..9].try_into().unwrap_or_default());
        let length = u32::from_be_bytes(head[9..13].try_into().unwrap_or_default()) as usize;
        if kind == END && version == 2 {
            let mut value = [0u8; 32];
            if length != 0 || read_exact_or_short(&mut reader, &mut value).map_err(io_error)? != 32
            {
                out.truncated_at = Some(offset);
                break;
            }
            if check {
                chain = digest_of(chain_key, &[&chain, &head, &count.to_be_bytes()]);
                if !same_digest(&chain, &value) {
                    out.chain_ok = Some(false);
                    out.problems.push(format!(
                        "record {count}: the end record's chain value differs"
                    ));
                }
            }
            out.closed = true;
            let mut extra = [0u8; 1];
            if read_exact_or_short(&mut reader, &mut extra).map_err(io_error)? != 0 {
                out.problems.push("data after the end record".into());
            }
            break;
        }
        if kind != SENT && kind != RECEIVED {
            out.problems.push(format!(
                "record {count} at offset {offset}: unknown kind {kind}"
            ));
            out.truncated_at = Some(offset);
            break;
        }
        let mut frame_bytes = vec![0u8; length];
        if read_exact_or_short(&mut reader, &mut frame_bytes).map_err(io_error)? != length {
            out.truncated_at = Some(offset);
            break;
        }
        let mut value = None;
        if version == 2 {
            let mut recorded = [0u8; 32];
            if read_exact_or_short(&mut reader, &mut recorded).map_err(io_error)? != 32 {
                out.truncated_at = Some(offset);
                break;
            }
            if check {
                let tail = &frame_bytes[frame_bytes.len().saturating_sub(frame::DIGEST_BYTES)..];
                chain = digest_of(chain_key, &[&chain, &head, tail]);
                if !same_digest(&chain, &recorded) {
                    out.chain_ok = Some(false);
                    out.problems.push(format!(
                        "record {count}: the chain value differs; the file changed at or before it"
                    ));
                    chain = recorded; // report each break once, and go on from the recorded value
                }
            }
            value = Some(recorded);
        }
        offset += 13 + length as u64 + if version == 2 { 32 } else { 0 };
        count += 1;
        visit(Record {
            kind,
            time_ns,
            frame: frame_bytes,
            chain: value,
        });
    }
    Ok(out)
}

/// Read all records of a transcript into memory. For large files, use [`iterate`].
pub fn read(path: impl AsRef<Path>) -> Result<Transcript, FrameError> {
    let mut records = Vec::new();
    let mut out = iterate(path, None, |record| records.push(record))?;
    out.records = records;
    Ok(out)
}

/// The verification result of one session.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct SessionReport {
    /// The session identifier.
    pub session: String,
    /// "client" or "owner", from the direction of the open request.
    pub role: String,
    /// Admitted requests: ok, declined, or ended with a request named.
    pub requests: usize,
    /// Declined requests.
    pub declined: usize,
    /// Rejected frames.
    pub rejected: usize,
    /// Copies of a request, and copies of a response.
    pub repeats: usize,
    /// Whether the transcript has the open request, a response to every request, and the
    /// `ok` response to close.
    pub complete: bool,
    /// The code of an ending response, if any.
    pub ended: Option<String>,
    /// Problems found.
    pub problems: Vec<String>,
}

/// The verification result of one stream.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct StreamReport {
    /// Accepted messages.
    pub accepted: usize,
    /// Messages lost before an accepted one.
    pub lost: u64,
    /// Whether the stream ended.
    pub ended: bool,
    /// Problems found.
    pub problems: Vec<String>,
}

/// The verification of one transcript (section 10.3).
#[derive(Debug, Clone, Default)]
pub struct Report {
    /// 1 or 2.
    pub version: u8,
    /// The header (version 2).
    pub header: Option<Value>,
    /// The number of records.
    pub records: usize,
    /// Whether the file ends with an end record.
    pub closed: bool,
    /// The offset of a record that ends before its length.
    pub truncated_at: Option<u64>,
    /// Whether every chain value matched; None for version 1 or a keyed chain without the key.
    pub chain_ok: Option<bool>,
    /// The sessions, in the order of their first record.
    pub sessions: Vec<SessionReport>,
    /// The streams.
    pub streams: HashMap<String, StreamReport>,
    /// Problems of the file.
    pub problems: Vec<String>,
}

impl Report {
    /// No problem in the file, in any session, or in any stream, and the chain checked.
    pub fn ok(&self) -> bool {
        self.problems.is_empty()
            && self.truncated_at.is_none()
            && self.chain_ok != Some(false)
            && self.sessions.iter().all(|s| s.problems.is_empty())
            && self.streams.values().all(|s| s.problems.is_empty())
    }
}

/// Whether a response answers an admitted request, so that its owner keeps it: every outcome
/// except `rejected`, and `ended` with `session_expired` (rule 7.3.3) or `shutdown` (rule 7.3.10).
fn admits(message: &Value) -> bool {
    match message["outcome"].as_str() {
        Some("rejected") => false,
        Some("ended") => !matches!(
            message["code"].as_str(),
            Some("session_expired" | "shutdown")
        ),
        _ => true,
    }
}

/// A request that the verifier waits to see answered: its seq, identity, op, and whether it
/// follows the order of its session.
type Pending = (u64, String, String, bool);

#[derive(Default)]
struct Verifier {
    report: Report,
    index: HashMap<String, usize>,
    pending: HashMap<String, Pending>,
    /// The identity of the kept response to each request.
    answers: HashMap<String, String>,
    last: HashMap<String, String>,
    next_seq: HashMap<String, u64>,
    seen: HashMap<String, HashSet<String>>,
    streams: HashMap<String, (u64, String, bool)>,
    previous_time: Option<u64>,
}

impl Verifier {
    fn session(&mut self, session: &str, role: &str) -> &mut SessionReport {
        let position = match self.index.get(session) {
            Some(&position) => position,
            None => {
                self.report.sessions.push(SessionReport {
                    session: session.to_owned(),
                    role: role.to_owned(),
                    ..SessionReport::default()
                });
                self.index
                    .insert(session.to_owned(), self.report.sessions.len() - 1);
                self.report.sessions.len() - 1
            }
        };
        &mut self.report.sessions[position]
    }

    fn record(&mut self, index: usize, record: Record, verify: Verify<'_>) {
        self.report.records += 1;
        if self.previous_time.is_some_and(|t| record.time_ns < t) {
            self.report.problems.push(format!(
                "record {index}: its time is earlier than the record before it"
            ));
        }
        self.previous_time = Some(record.time_ns);
        let decoded = match frame::decode_verified(record.frame, MAX_BOUND, verify) {
            Ok(decoded) => decoded,
            Err(error) => {
                self.report
                    .problems
                    .push(format!("record {index}: bad frame: {}", error.0));
                return;
            }
        };
        let message = &decoded.message;
        let what = kind(message);
        let checked = match what {
            "request" => check_request(message),
            "response" => check_response(message),
            "stream" => check_stream_message(message),
            _ => Ok(()),
        };
        if let Err(error) = checked {
            self.report
                .problems
                .push(format!("record {index}: {}", error.0));
            return;
        }
        match what {
            "request" => self.request(index, record.kind, &decoded),
            "response" => self.response(index, record.kind, &decoded),
            "stream" => self.stream(&decoded),
            _ => self
                .report
                .problems
                .push(format!("record {index}: not an NCP message")),
        }
    }

    fn request(&mut self, index: usize, record_kind: u8, decoded: &frame::Decoded) {
        let message = &decoded.message;
        let session = message["session"].as_str().unwrap_or_default().to_owned();
        let seq = message["seq"].as_u64().unwrap_or_default();
        let role = if record_kind == SENT {
            "client"
        } else {
            "owner"
        };
        let identity = decoded.identity.clone();
        let pending = self.pending.get(&session).cloned();
        let known = self
            .seen
            .get(&session)
            .is_some_and(|seen| seen.contains(&identity));
        let expected = self.next_seq.get(&session).copied().unwrap_or(0);
        let last = self.last.get(&session).cloned();
        let entry = self.session(&session, role);
        if entry.role != role {
            entry.problems.push(format!(
                "record {index}: a request in the direction of the other role"
            ));
        }
        if let Some((pending_seq, pending_id, _, _)) = pending {
            if pending_seq == seq {
                if pending_id != identity {
                    entry
                        .problems
                        .push(format!("seq {seq}: two different requests outstanding"));
                } else {
                    entry.repeats += 1;
                }
                return;
            }
        }
        if known {
            entry.repeats += 1; // a delayed copy of an earlier request
            return;
        }
        let mut disorder = Vec::new();
        if seq != expected {
            disorder.push(format!("seq {seq}: expected {expected}"));
        }
        if seq == 0 {
            if message["op"] != "open" || !message["ack"].is_null() {
                disorder.push("seq 0 is not an open without ack".to_owned());
            }
        } else if message["ack"].as_str() != last.as_deref() {
            disorder.push(format!(
                "seq {seq}: ack does not name the previous response"
            ));
        }
        let in_order = disorder.is_empty();
        if role == "client" {
            entry.problems.extend(disorder); // the recorder's own request
        }
        // An owner receives what a client sends; it must not admit a request out of order, and
        // response() checks that.
        self.seen
            .entry(session.clone())
            .or_default()
            .insert(identity.clone());
        let op = message["op"].as_str().unwrap_or_default().to_owned();
        self.pending.insert(session, (seq, identity, op, in_order));
    }

    fn response(&mut self, index: usize, record_kind: u8, decoded: &frame::Decoded) {
        let message = &decoded.message;
        let Some(session) = message["session"].as_str().map(str::to_owned) else {
            // A response that names no request: the bad-frame or shutdown response.
            let code = message["code"].as_str().unwrap_or_default().to_owned();
            if self.pending.len() != 1 {
                self.report.problems.push(format!(
                    "record {index}: a {code} response that no single session awaits"
                ));
                return;
            }
            let owner = self.pending.keys().next().cloned().unwrap_or_default();
            self.pending.remove(&owner);
            self.session(&owner, "client").ended = Some(code);
            return;
        };
        if !self.index.contains_key(&session) {
            let role = if record_kind == RECEIVED {
                "client"
            } else {
                "owner"
            };
            self.session(&session, role).problems.push(format!(
                "record {index}: a response before any request of the session"
            ));
            return;
        }
        let identity = decoded.identity.clone();
        let names_seen = message["request"]
            .as_str()
            .is_some_and(|r| self.seen.get(&session).is_some_and(|s| s.contains(r)));
        let is_last = self.last.get(&session) == Some(&identity);
        let pending = self.pending.get(&session).cloned();
        let admitted = admits(message);
        let earlier = message["request"]
            .as_str()
            .and_then(|r| self.answers.get(r))
            .cloned();
        let entry = self.session(&session, "client");
        let expected_kind = if entry.role == "client" {
            RECEIVED
        } else {
            SENT
        };
        if record_kind != expected_kind {
            entry.problems.push(format!(
                "record {index}: a response in the direction of the other role"
            ));
        }
        if admitted && earlier.as_ref().is_some_and(|earlier| *earlier != identity) {
            // The owner sends a kept response again byte for byte (rule 7.3.5).
            entry.problems.push(format!(
                "seq {}: two different responses to one admitted request",
                message["seq"]
            ));
            return;
        }
        let Some((seq, request_id, op, in_order)) = pending else {
            if is_last || names_seen {
                entry.repeats += 1;
            } else {
                entry
                    .problems
                    .push(format!("seq {}: response without request", message["seq"]));
            }
            return;
        };
        if message["seq"] != seq || message["request"] != request_id.as_str() {
            if names_seen {
                entry.repeats += 1;
            } else {
                entry.problems.push(format!(
                    "seq {}: response names another request",
                    message["seq"]
                ));
            }
            return;
        }
        if admitted && !in_order && entry.role == "owner" {
            entry.problems.push(format!(
                "seq {seq}: the owner admitted a request out of order"
            ));
        }
        let outcome = message["outcome"].as_str().unwrap_or_default().to_owned();
        match outcome.as_str() {
            "rejected" => {
                entry.rejected += 1;
            }
            "declined" => {
                entry.requests += 1;
                entry.declined += 1;
            }
            "ended" => {
                entry.requests += 1;
                entry.ended = message["code"].as_str().map(str::to_owned);
            }
            _ => {
                entry.requests += 1;
                if op == "close" {
                    entry.complete = true;
                }
            }
        }
        self.pending.remove(&session);
        if admitted {
            self.answers.insert(request_id.clone(), identity.clone());
        }
        if outcome == "rejected" {
            if let Some(seen) = self.seen.get_mut(&session) {
                seen.remove(&request_id); // a corrected request may follow with the same seq
            }
            return;
        }
        self.last.insert(session.clone(), identity);
        self.next_seq.insert(session, seq + 1);
    }

    fn stream(&mut self, decoded: &frame::Decoded) {
        let message = &decoded.message;
        let name = message["stream"].as_str().unwrap_or_default().to_owned();
        let seq = message["seq"].as_u64().unwrap_or_default();
        let end = message["body"].get("ncp.end").is_some();
        let entry = self.report.streams.entry(name.clone()).or_default();
        let Some((last_seq, last_identity, ended)) = self.streams.get(&name).cloned() else {
            self.streams
                .insert(name, (seq, decoded.identity.clone(), end));
            entry.accepted += 1;
            entry.ended = end;
            return;
        };
        if seq <= last_seq {
            if seq == last_seq && decoded.identity != last_identity {
                entry
                    .problems
                    .push(format!("seq {seq}: two different messages"));
            }
            return;
        }
        if ended {
            entry
                .problems
                .push(format!("seq {seq}: a message after the end of the stream"));
            return;
        }
        if seq == last_seq + 1 && message["prev"].as_str() != Some(last_identity.as_str()) {
            entry.problems.push(format!("seq {seq}: broken chain"));
            return;
        }
        entry.lost += seq - last_seq - 1;
        entry.accepted += 1;
        entry.ended = end;
        self.streams
            .insert(name, (seq, decoded.identity.clone(), end));
    }
}

/// Verify every exchange session and stream of a transcript (section 10.3). With `key`, the
/// transcript must be authenticated with it.
pub fn verify(path: impl AsRef<Path>, key: Option<&Key>) -> Result<Report, FrameError> {
    let path = path.as_ref();
    // The frames of a keyed transcript are authenticated with the same key (section 13.2).
    let probe = iterate(path, None, |_| {}).map(|t| {
        t.header
            .as_ref()
            .and_then(|h| h["chain"].as_str().map(|c| c == "hmac-sha256"))
            .unwrap_or(false)
    })?;
    let verify = match (probe, key) {
        (true, Some(key)) => Verify::Key(key),
        (true, None) => Verify::Trust,
        (false, _) => Verify::Digest,
    };
    let mut verifier = Verifier::default();
    let mut index = 0usize;
    let out = iterate(path, key, |record| {
        verifier.record(index, record, verify);
        index += 1;
    })?;
    let mut report = verifier.report;
    report.version = out.version;
    report.header = out.header;
    report.closed = out.closed;
    report.truncated_at = out.truncated_at;
    report.chain_ok = out.chain_ok;
    report.problems.extend(out.problems);
    if out.version == 2 && !out.closed && out.truncated_at.is_none() {
        report
            .problems
            .push("no end record: the recorder did not close the transcript".into());
    }
    if let Some(offset) = out.truncated_at {
        report
            .problems
            .push(format!("the transcript is truncated at offset {offset}"));
    }
    for (session, (seq, _, _, _)) in &verifier.pending {
        if let Some(&position) = verifier.index.get(session) {
            report.sessions[position]
                .problems
                .push(format!("seq {seq}: no response"));
        }
    }
    Ok(report)
}
