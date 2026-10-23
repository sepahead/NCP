//! Decode a corpus of frames for conformance/fuzz.py: decode_corpus CORPUS BOUND.
//! The corpus is a sequence of (u32 big-endian length, frame bytes). For each frame, prints one
//! JSON line: {"ok":false} or {"ok":true,"identity":...,"message":...,"arrays":[hex...]}.
use serde_json::json;
use std::io::{BufWriter, Write};

fn main() -> std::io::Result<()> {
    let args: Vec<String> = std::env::args().collect();
    let corpus = std::fs::read(&args[1])?;
    let bound: usize = args[2].parse().map_err(std::io::Error::other)?;
    let mut out = BufWriter::new(std::io::stdout().lock());
    let mut at = 0;
    while at + 4 <= corpus.len() {
        let length = u32::from_be_bytes([corpus[at], corpus[at + 1], corpus[at + 2], corpus[at + 3]]) as usize;
        let frame = corpus[at + 4..at + 4 + length].to_vec();
        at += 4 + length;
        let line = match ncp::frame::decode(frame, bound) {
            Err(error) => json!({"ok": false, "error": error.0}),
            Ok(decoded) => {
                let arrays: Vec<String> = (0..decoded.arrays.len()).map(|i| ncp::frame::hex(decoded.array_bytes(i).unwrap_or_default())).collect();
                json!({"ok": true, "identity": decoded.identity, "message": decoded.message, "arrays": arrays})
            }
        };
        serde_json::to_writer(&mut out, &line)?;
        out.write_all(b"\n")?;
    }
    out.flush()
}
