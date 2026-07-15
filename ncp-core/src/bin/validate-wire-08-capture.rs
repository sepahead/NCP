use ncp_core::{bounded_json, validate_wire_0_8_capture};
use std::fs::File;
use std::io::{self, Read};
use std::path::PathBuf;

const MAX_CAPTURE_BYTES: usize = bounded_json::MAX_FRAME_BYTES;

fn read_bounded(reader: impl Read) -> io::Result<Vec<u8>> {
    let mut bytes = Vec::new();
    reader
        .take((MAX_CAPTURE_BYTES + 1) as u64)
        .read_to_end(&mut bytes)?;
    if bytes.len() > MAX_CAPTURE_BYTES {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            format!(
                "wire-0.8 capture exceeds the {MAX_CAPTURE_BYTES}-byte validation envelope limit"
            ),
        ));
    }
    Ok(bytes)
}

fn validate_path(path: &PathBuf) -> Result<String, String> {
    let file =
        File::open(path).map_err(|error| format!("cannot read {}: {error}", path.display()))?;
    let bytes =
        read_bounded(file).map_err(|error| format!("cannot read {}: {error}", path.display()))?;
    let report = validate_wire_0_8_capture(&bytes)
        .map_err(|error| format!("{}: {error}", path.display()))?;
    serde_json::to_string(&report)
        .map_err(|error| format!("cannot encode report for {}: {error}", path.display()))
}

fn main() {
    let paths: Vec<PathBuf> = std::env::args_os().skip(1).map(PathBuf::from).collect();
    if paths.is_empty() {
        eprintln!("usage: validate-wire-08-capture <capture.json> [...]");
        std::process::exit(2);
    }
    let mut failed = false;
    for path in paths {
        match validate_path(&path) {
            Ok(report) => println!("{report}"),
            Err(error) => {
                eprintln!("ERROR: {error}");
                failed = true;
            }
        }
    }
    if failed {
        std::process::exit(1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    #[test]
    fn bounded_reader_accepts_exact_limit() {
        let input = vec![b' '; MAX_CAPTURE_BYTES];
        assert_eq!(
            read_bounded(Cursor::new(input)).unwrap().len(),
            MAX_CAPTURE_BYTES
        );
    }

    #[test]
    fn bounded_reader_rejects_before_unbounded_allocation() {
        let input = vec![b' '; MAX_CAPTURE_BYTES + 1];
        let error = read_bounded(Cursor::new(input)).unwrap_err();
        assert_eq!(error.kind(), io::ErrorKind::InvalidData);
        assert!(error.to_string().contains("validation envelope limit"));
    }
}
