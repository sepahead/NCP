use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, File, OpenOptions};
use std::io::Read;
use std::path::{Component, Path, PathBuf};

#[cfg(unix)]
use std::os::unix::fs::MetadataExt;
#[cfg(any(target_os = "android", target_os = "linux"))]
use std::os::unix::fs::OpenOptionsExt;
#[cfg(any(
    target_os = "dragonfly",
    target_os = "freebsd",
    target_os = "ios",
    target_os = "macos",
    target_os = "netbsd",
    target_os = "openbsd"
))]
use std::os::unix::fs::OpenOptionsExt;
#[cfg(windows)]
use std::os::windows::fs::OpenOptionsExt;

use serde_json::Value;

use crate::error::{EngineError, EngineResult};
use crate::model::{Limits, Source};
use crate::sha256::sha256_hex;
use crate::strict_json::parse_strict;

pub(crate) struct SourceRepository<'root> {
    root: &'root Path,
    limits: Limits,
    aggregate_adr_bytes: usize,
    loaded: BTreeMap<String, LoadedAdr>,
}

struct LoadedAdr {
    adr: String,
    byte_length: usize,
    sha256: String,
    json_fences: Vec<Vec<u8>>,
    covered_ordinals: BTreeSet<usize>,
}

impl<'root> SourceRepository<'root> {
    pub(crate) fn new(root: &'root Path, limits: Limits) -> EngineResult<Self> {
        let metadata = fs::metadata(root)
            .map_err(|error| EngineError::io(format!("reading repository root {root:?}"), error))?;
        if !metadata.is_dir() {
            return Err(EngineError::input(format!(
                "repository root {root:?} is not a directory"
            )));
        }
        Ok(Self {
            root,
            limits,
            aggregate_adr_bytes: 0,
            loaded: BTreeMap::new(),
        })
    }

    pub(crate) fn load_document(&mut self, source: &Source) -> EngineResult<Value> {
        if !self.loaded.contains_key(&source.path) {
            let loaded = self.load_adr(source)?;
            self.loaded.insert(source.path.clone(), loaded);
        }
        let loaded = self
            .loaded
            .get_mut(&source.path)
            .ok_or_else(|| EngineError::semantic("loaded ADR cache lost an entry"))?;
        if loaded.adr != source.adr
            || loaded.byte_length != source.adr_byte_length
            || loaded.sha256 != source.adr_sha256
        {
            return Err(EngineError::corpus(format!(
                "source metadata is inconsistent across cases for {:?}",
                source.path
            )));
        }
        let index = source
            .json_fence_ordinal
            .checked_sub(1)
            .ok_or_else(|| EngineError::corpus("JSON fence ordinal must be positive"))?;
        let fence = loaded.json_fences.get(index).ok_or_else(|| {
            EngineError::corpus(format!(
                "source {:?} has no JSON fence ordinal {}",
                source.path, source.json_fence_ordinal
            ))
        })?;
        if fence.len() != source.fence_byte_length {
            return Err(EngineError::corpus(format!(
                "JSON fence byte length mismatch for {:?} ordinal {}: got {}, expected {}",
                source.path,
                source.json_fence_ordinal,
                fence.len(),
                source.fence_byte_length
            )));
        }
        let actual_hash = sha256_hex(fence);
        if actual_hash != source.fence_sha256 {
            return Err(EngineError::corpus(format!(
                "JSON fence SHA-256 mismatch for {:?} ordinal {}",
                source.path, source.json_fence_ordinal
            )));
        }
        let document = parse_strict(
            fence,
            self.limits.json(self.limits.maximum_json_fence_bytes),
        )
        .map_err(|error| {
            EngineError::corpus(format!(
                "invalid JSON fence {:?} ordinal {}: {error}",
                source.path, source.json_fence_ordinal
            ))
        })?;
        if !loaded.covered_ordinals.insert(source.json_fence_ordinal) {
            return Err(EngineError::corpus(format!(
                "source {:?} JSON fence ordinal {} was bound more than once",
                source.path, source.json_fence_ordinal
            )));
        }
        Ok(document)
    }

    pub(crate) fn verify_exact_fence_coverage(&self) -> EngineResult<()> {
        for (path, loaded) in &self.loaded {
            if !coverage_is_exact(loaded.json_fences.len(), &loaded.covered_ordinals) {
                return Err(EngineError::corpus(format!(
                    "source {path:?} JSON fence coverage is not exact and contiguous"
                )));
            }
        }
        Ok(())
    }

    fn load_adr(&mut self, source: &Source) -> EngineResult<LoadedAdr> {
        if source.adr_byte_length == 0 || source.adr_byte_length > self.limits.maximum_adr_bytes {
            return Err(EngineError::corpus(format!(
                "declared ADR byte length is outside bounds for {:?}",
                source.path
            )));
        }
        if source.fence_byte_length == 0
            || source.fence_byte_length > self.limits.maximum_json_fence_bytes
        {
            return Err(EngineError::corpus(format!(
                "declared fence byte length is outside bounds for {:?}",
                source.path
            )));
        }
        let path = resolve_regular_relative_file(self.root, &source.path)?;
        let bytes = read_bounded(&path, self.limits.maximum_adr_bytes)?;
        if bytes.len() != source.adr_byte_length {
            return Err(EngineError::corpus(format!(
                "ADR byte length mismatch for {:?}: got {}, expected {}",
                source.path,
                bytes.len(),
                source.adr_byte_length
            )));
        }
        let actual_hash = sha256_hex(&bytes);
        if actual_hash != source.adr_sha256 {
            return Err(EngineError::corpus(format!(
                "ADR SHA-256 mismatch for {:?}",
                source.path
            )));
        }
        self.aggregate_adr_bytes = self
            .aggregate_adr_bytes
            .checked_add(bytes.len())
            .ok_or_else(|| EngineError::corpus("aggregate ADR byte count overflow"))?;
        if self.aggregate_adr_bytes > self.limits.maximum_aggregate_adr_bytes {
            return Err(EngineError::corpus(
                "aggregate distinct ADR bytes exceed the declared limit",
            ));
        }
        let json_fences = extract_json_fences(&bytes)?;
        Ok(LoadedAdr {
            adr: source.adr.clone(),
            byte_length: bytes.len(),
            sha256: actual_hash,
            json_fences,
            covered_ordinals: BTreeSet::new(),
        })
    }
}

fn coverage_is_exact(fence_count: usize, covered_ordinals: &BTreeSet<usize>) -> bool {
    fence_count == covered_ordinals.len() && covered_ordinals.iter().copied().eq(1..=fence_count)
}

pub(crate) fn resolve_regular_relative_file(root: &Path, relative: &str) -> EngineResult<PathBuf> {
    let relative_path = Path::new(relative);
    if relative_path.as_os_str().is_empty()
        || relative_path
            .components()
            .any(|component| !matches!(component, Component::Normal(_)))
    {
        return Err(EngineError::input(format!(
            "path must be a non-empty normalized relative path: {relative:?}"
        )));
    }

    let mut resolved = root.to_path_buf();
    let component_count = relative_path.components().count();
    for (index, component) in relative_path.components().enumerate() {
        let Component::Normal(name) = component else {
            return Err(EngineError::input("relative path changed during traversal"));
        };
        resolved.push(name);
        let metadata = fs::symlink_metadata(&resolved).map_err(|error| {
            EngineError::io(format!("inspecting source path {resolved:?}"), error)
        })?;
        if metadata.file_type().is_symlink() {
            return Err(EngineError::input(format!(
                "symlink path component is forbidden: {resolved:?}"
            )));
        }
        let final_component = index + 1 == component_count;
        if final_component && !metadata.is_file() {
            return Err(EngineError::input(format!(
                "source path is not a regular file: {resolved:?}"
            )));
        }
        if !final_component && !metadata.is_dir() {
            return Err(EngineError::input(format!(
                "source parent is not a directory: {resolved:?}"
            )));
        }
    }
    Ok(resolved)
}

pub(crate) fn read_bounded(path: &Path, maximum_bytes: usize) -> EngineResult<Vec<u8>> {
    let read_limit = maximum_bytes
        .checked_add(1)
        .ok_or_else(|| EngineError::input("file byte limit cannot be usize::MAX"))?;
    let mut file = open_readonly_no_follow(path)?;
    let before = file
        .metadata()
        .map_err(|error| EngineError::io(format!("inspecting open file {path:?}"), error))?;
    if !before.is_file() {
        return Err(EngineError::input(format!(
            "input must be a regular non-symlink file: {path:?}"
        )));
    }
    let declared_length = usize::try_from(before.len())
        .map_err(|_| EngineError::input(format!("file length cannot fit usize for {path:?}")))?;
    if declared_length > maximum_bytes {
        return Err(EngineError::input(format!(
            "file {path:?} has {declared_length} bytes; limit is {maximum_bytes}"
        )));
    }
    let mut bytes = Vec::with_capacity(declared_length.min(maximum_bytes));
    file.by_ref()
        .take(u64::try_from(read_limit).map_err(|_| {
            EngineError::input(format!("file read limit cannot fit u64 for {path:?}"))
        })?)
        .read_to_end(&mut bytes)
        .map_err(|error| EngineError::io(format!("reading open file {path:?}"), error))?;
    if bytes.len() > maximum_bytes {
        return Err(EngineError::input(format!(
            "file {path:?} grew beyond its {maximum_bytes}-byte limit while reading"
        )));
    }
    let after = file.metadata().map_err(|error| {
        EngineError::io(
            format!("re-inspecting open file {path:?} after read"),
            error,
        )
    })?;
    if metadata_changed(&before, &after) || u64::try_from(bytes.len()) != Ok(after.len()) {
        return Err(EngineError::input(format!(
            "file {path:?} changed while it was read"
        )));
    }
    Ok(bytes)
}

fn open_readonly_no_follow(path: &Path) -> EngineResult<File> {
    let mut options = OpenOptions::new();
    options.read(true);
    #[cfg(any(target_os = "android", target_os = "linux"))]
    options.custom_flags(0x20_000);
    #[cfg(any(
        target_os = "dragonfly",
        target_os = "freebsd",
        target_os = "ios",
        target_os = "macos",
        target_os = "netbsd",
        target_os = "openbsd"
    ))]
    options.custom_flags(0x100);
    #[cfg(windows)]
    options.custom_flags(0x0020_0000);
    options.open(path).map_err(|error| {
        EngineError::io(
            format!("opening file without following its leaf path {path:?}"),
            error,
        )
    })
}

#[cfg(unix)]
fn metadata_changed(before: &fs::Metadata, after: &fs::Metadata) -> bool {
    before.dev() != after.dev()
        || before.ino() != after.ino()
        || before.len() != after.len()
        || before.mtime() != after.mtime()
        || before.mtime_nsec() != after.mtime_nsec()
        || before.ctime() != after.ctime()
        || before.ctime_nsec() != after.ctime_nsec()
        || !after.is_file()
}

#[cfg(not(unix))]
fn metadata_changed(before: &fs::Metadata, after: &fs::Metadata) -> bool {
    before.len() != after.len()
        || before.modified().ok() != after.modified().ok()
        || before.created().ok() != after.created().ok()
        || !after.is_file()
}

fn extract_json_fences(markdown: &[u8]) -> EngineResult<Vec<Vec<u8>>> {
    std::str::from_utf8(markdown)
        .map_err(|error| EngineError::corpus(format!("ADR Markdown is not UTF-8: {error}")))?;

    enum Fence {
        Json { content_start: usize },
        Other,
    }

    let mut fences = Vec::new();
    let mut state: Option<Fence> = None;
    let mut line_start = 0_usize;
    while line_start < markdown.len() {
        let newline_offset = markdown[line_start..]
            .iter()
            .position(|byte| *byte == b'\n');
        let line_end = newline_offset
            .map(|offset| line_start + offset)
            .unwrap_or(markdown.len());
        let mut logical_end = line_end;
        if markdown.get(logical_end.wrapping_sub(1)) == Some(&b'\r') {
            logical_end -= 1;
        }
        let line = &markdown[line_start..logical_end];
        let next_line = if line_end < markdown.len() {
            line_end + 1
        } else {
            markdown.len()
        };

        match &state {
            None if line == b"```json" => {
                if line_end == markdown.len() {
                    return Err(EngineError::corpus(
                        "JSON fence opener has no following content line",
                    ));
                }
                state = Some(Fence::Json {
                    content_start: next_line,
                });
            }
            None if line.starts_with(b"```") => state = Some(Fence::Other),
            Some(Fence::Json { content_start }) if line == b"```" => {
                let mut content_end = line_start;
                if content_end > *content_start && markdown[content_end - 1] == b'\n' {
                    content_end -= 1;
                    if content_end > *content_start && markdown[content_end - 1] == b'\r' {
                        content_end -= 1;
                    }
                }
                fences.push(markdown[*content_start..content_end].to_vec());
                state = None;
            }
            Some(Fence::Other) if line == b"```" => state = None,
            None | Some(Fence::Json { .. }) | Some(Fence::Other) => {}
        }
        line_start = next_line;
    }
    if state.is_some() {
        return Err(EngineError::corpus(
            "ADR contains an unclosed Markdown fence",
        ));
    }
    Ok(fences)
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeSet;

    #[cfg(unix)]
    use std::fs;
    #[cfg(unix)]
    use std::os::unix::fs::symlink;
    #[cfg(unix)]
    use std::time::{SystemTime, UNIX_EPOCH};

    use super::{coverage_is_exact, extract_json_fences, read_bounded};

    #[test]
    fn extract_json_fences_should_ignore_other_languages_and_trim_one_terminal_newline() {
        let markdown = b"before\n```text\n{not json}\n```\n```json\n{\"a\":1}\n```\nafter\n";
        let result = extract_json_fences(markdown);
        assert!(result.is_ok());
        assert_eq!(result.ok(), Some(vec![br#"{"a":1}"#.to_vec()]));
    }

    #[test]
    fn extract_json_fences_should_reject_unclosed_fence() {
        assert!(extract_json_fences(b"```json\n{}\n").is_err());
    }

    #[test]
    fn fence_coverage_must_include_every_ordinal_once() {
        assert!(coverage_is_exact(3, &BTreeSet::from([1, 2, 3])));
        assert!(!coverage_is_exact(3, &BTreeSet::from([1, 3])));
        assert!(!coverage_is_exact(2, &BTreeSet::from([1, 2, 3])));
    }

    #[cfg(unix)]
    #[test]
    fn bounded_read_enforces_the_cap_and_rejects_a_leaf_symlink() {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_or(0, |duration| duration.as_nanos());
        let directory = std::env::temp_dir().join(format!(
            "ncp-b01-rust-source-test-{}-{nonce}",
            std::process::id()
        ));
        let target = directory.join("target.json");
        let link = directory.join("link.json");
        assert!(fs::create_dir(&directory).is_ok());
        assert!(fs::write(&target, b"ncp").is_ok());
        assert_eq!(read_bounded(&target, 3).ok(), Some(b"ncp".to_vec()));
        assert!(read_bounded(&target, 2).is_err());
        assert!(symlink(&target, &link).is_ok());
        assert!(read_bounded(&link, 3).is_err());
        assert!(fs::remove_dir_all(&directory).is_ok());
    }
}
