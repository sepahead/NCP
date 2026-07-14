use ncp_core::PlantProfile;
use std::fs::File;
use std::io::{self, Read};
use std::path::PathBuf;

const MAX_PROFILE_BYTES: usize = ncp_core::bounded_json::MAX_FRAME_BYTES;

fn read_bounded(reader: impl Read) -> io::Result<Vec<u8>> {
    let mut bytes = Vec::new();
    reader
        .take((MAX_PROFILE_BYTES + 1) as u64)
        .read_to_end(&mut bytes)?;
    if bytes.len() > MAX_PROFILE_BYTES {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            format!("plant profile exceeds the {MAX_PROFILE_BYTES}-byte JSON frame limit"),
        ));
    }
    Ok(bytes)
}

fn validate_path(path: &PathBuf) -> Result<String, String> {
    let file =
        File::open(path).map_err(|error| format!("cannot read {}: {error}", path.display()))?;
    let bytes =
        read_bounded(file).map_err(|error| format!("cannot read {}: {error}", path.display()))?;
    ncp_core::bounded_json::preflight(&bytes)
        .map_err(|error| format!("{} fails bounded JSON preflight: {error}", path.display()))?;
    let profile: PlantProfile = serde_json::from_slice(&bytes)
        .map_err(|error| format!("{} is not a PlantProfile: {error}", path.display()))?;
    profile
        .validate()
        .map_err(|error| format!("{} is not a valid plant profile: {error}", path.display()))?;
    Ok(profile.profile_digest_sha256)
}

fn main() {
    let paths: Vec<PathBuf> = std::env::args_os().skip(1).map(PathBuf::from).collect();
    if paths.is_empty() {
        eprintln!("usage: validate-plant-profile <profile.json> [...]");
        std::process::exit(2);
    }
    let mut failed = false;
    for path in paths {
        match validate_path(&path) {
            Ok(digest) => println!("OK {} {digest}", path.display()),
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
        let input = vec![b' '; MAX_PROFILE_BYTES];
        assert_eq!(
            read_bounded(Cursor::new(input)).unwrap().len(),
            MAX_PROFILE_BYTES
        );
    }

    #[test]
    fn bounded_reader_rejects_before_unbounded_allocation() {
        let input = vec![b' '; MAX_PROFILE_BYTES + 1];
        let error = read_bounded(Cursor::new(input)).unwrap_err();
        assert_eq!(error.kind(), io::ErrorKind::InvalidData);
        assert!(error.to_string().contains("JSON frame limit"));
    }
}
