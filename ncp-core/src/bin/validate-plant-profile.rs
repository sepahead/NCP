use ncp_core::PlantProfile;
use std::path::PathBuf;

fn main() {
    let paths: Vec<PathBuf> = std::env::args_os().skip(1).map(PathBuf::from).collect();
    if paths.is_empty() {
        eprintln!("usage: validate-plant-profile <profile.json> [...]");
        std::process::exit(2);
    }
    for path in paths {
        let bytes = std::fs::read(&path).unwrap_or_else(|error| {
            panic!("cannot read {}: {error}", path.display());
        });
        ncp_core::bounded_json::preflight(&bytes).unwrap_or_else(|error| {
            panic!("{} fails bounded JSON preflight: {error}", path.display());
        });
        let profile: PlantProfile = serde_json::from_slice(&bytes).unwrap_or_else(|error| {
            panic!("{} is not a PlantProfile: {error}", path.display());
        });
        profile.validate().unwrap_or_else(|error| {
            panic!("{} is not a valid plant profile: {error}", path.display());
        });
        println!("OK {} {}", path.display(), profile.profile_digest_sha256);
    }
}
