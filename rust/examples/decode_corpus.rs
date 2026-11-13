//! Decode a corpus of frames for `python -m ncp conformance --decoder` and conformance/fuzz.py:
//! decode_corpus CORPUS. The corpus holds entries of a 4-byte big-endian bound, a 4-byte
//! big-endian length, and that many frame bytes. For each entry, prints one JSON line:
//! {"ok":false,"error":...} or {"ok":true,"identity":...,"message":...,"arrays":[hex...]}, and,
//! for a decoded frame, the result of the member checks of section 6 under "shapes".
use ncp::messages::{check_request, check_response, check_stream_message, foreign};
use serde_json::json;
use std::io::{BufWriter, Write};

fn main() -> std::io::Result<()> {
    let path = std::env::args()
        .nth(1)
        .expect("usage: decode_corpus CORPUS");
    let corpus = std::fs::read(path)?;
    let mut out = BufWriter::new(std::io::stdout().lock());
    let mut at = 0;
    while at + 8 <= corpus.len() {
        let word = |i: usize| {
            u32::from_be_bytes([corpus[i], corpus[i + 1], corpus[i + 2], corpus[i + 3]]) as usize
        };
        let (bound, length) = (word(at), word(at + 4));
        let frame = corpus[at + 8..at + 8 + length].to_vec();
        at += 8 + length;
        let line = match ncp::frame::decode(frame, bound) {
            Err(error) => json!({"ok": false, "error": error.0}),
            Ok(decoded) => {
                let arrays: Vec<String> = (0..decoded.arrays.len())
                    .map(|i| ncp::frame::hex(decoded.array_bytes(i).unwrap_or_default()))
                    .collect();
                let shapes = json!({
                    "request": check_request(&decoded.message).is_ok(),
                    "response": check_response(&decoded.message).is_ok(),
                    "stream": check_stream_message(&decoded.message).is_ok(),
                    "foreign": foreign(&decoded.message),
                });
                json!({"ok": true, "identity": decoded.identity, "message": decoded.message,
                       "arrays": arrays, "shapes": shapes})
            }
        };
        serde_json::to_writer(&mut out, &line)?;
        out.write_all(b"\n")?;
    }
    out.flush()
}
