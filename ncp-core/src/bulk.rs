//! Packed little-endian **columnar codec** for bulk numeric observation data (#6).
//!
//! Observation/analysis data can contain large numeric arrays — spike trains
//! (`senders`), `V_m`/`g_ex`/`w` traces (`values`), and their `times`. Encoding
//! those as protobuf `repeated double` or JSON is parse+serialize work that scales
//! with the event count. This module carries them as a **self-describing
//! little-endian column block** for bounded local or offline storage and
//! conformance fixtures. Fixed-width decoding avoids a numeric tokenizer. A
//! column directory supplies byte offsets for random access, which is the useful
//! property of Arrow IPC or Cap'n Proto here without adding either dependency.
//!
//! ## Boundary
//!
//! This codec is reserved for observation/analysis data. It is **not currently a
//! transported NCP plane payload**: every shipped plane carries a complete JSON
//! message, and a bare NCPB block lacks session, sequence, timestamp, and
//! provenance. The small, latency-critical control-loop frames
//! ([`SensorFrame`](crate::SensorFrame) / [`CommandFrame`](crate::CommandFrame) /
//! [`StimulusFrame`](crate::StimulusFrame)) stay JSON and **never** ride this
//! codec. A future negotiated `BulkObservation` envelope must ship in every SDK
//! before transport use; JSON [`ObservationFrame`](crate::ObservationFrame) is
//! the only implemented observation-plane frame.
//!
//! ## Binary layout (all integers little-endian)
//!
//! ```text
//! offset  size  field
//! 0       4     magic   = b"NCPB"
//! 4       1     version = 1
//! 5       1     flags   = 0          (bit0: 0 = little-endian; reserved otherwise)
//! 6       2     n_cols  : u16
//! 8       4     total_len : u32      (== bytes.len(); guards truncation/over-read)
//! 12      16*n  column directory (one 16-byte entry per column):
//!                 0  4  name_off : u32   (offset from block start to the name bytes)
//!                 4  2  name_len : u16
//!                 6  1  dtype    : u8    (1=f32, 2=f64, 3=i32, 4=i64)
//!                 7  1  _pad     : u8 = 0
//!                 8  4  n_rows   : u32    (element count of this column)
//!                 12 4  data_off : u32   (offset from block start to column data)
//! ...           name pool (concatenated utf-8 names), then column data blocks
//! ```
//!
//! Decoding is **fully bounds-checked** against untrusted bytes: a bad magic,
//! unsupported version/flags/dtype, an out-of-range offset/length, an
//! allocation-bomb `n_rows`, or a `total_len` that disagrees with the buffer all
//! fail closed with [`BulkError`] rather than panic or over-read.

use crate::messages::{
    Observable, Observation, ObservationFrame, SessionRef, StreamPosition, WireFrame,
};

/// Magic prefix identifying an NCP bulk column block.
pub const BULK_MAGIC: [u8; 4] = *b"NCPB";
/// Binary format version for [`BulkBlock`].
pub const BULK_VERSION: u8 = 1;
/// Maximum accepted encoded block size. Bulk observations are analytical data,
/// not an unbounded file-transfer channel; bounding them limits per-message memory
/// and keeps hostile local or future envelope inputs from monopolizing a process.
/// The motivating 50k-spike payload is under 1 MiB.
pub const BULK_MAX_BYTES: usize = 64 * 1024 * 1024;
/// Maximum directory width accepted by the local/offline bulk codec. Real NCP
/// observations use a handful of parallel columns; 4096 is intentionally
/// generous while bounding per-column metadata and adversarial parser work.
pub const BULK_MAX_COLUMNS: usize = 4096;

const HEADER_LEN: usize = 12;
const DIR_ENTRY_LEN: usize = 16;

const DTYPE_F32: u8 = 1;
const DTYPE_F64: u8 = 2;
const DTYPE_I32: u8 = 3;
const DTYPE_I64: u8 = 4;

/// A single typed numeric column. `f32`/`i32` are the compact widths the issue
/// calls for (halving trace/sender bytes); `f64`/`i64` are lossless and match the
/// [`Observation`] field types exactly.
#[derive(Clone, PartialEq, Debug)]
pub enum Column {
    F32(Vec<f32>),
    F64(Vec<f64>),
    I32(Vec<i32>),
    I64(Vec<i64>),
}

impl Column {
    fn width(dtype: u8) -> usize {
        match dtype {
            DTYPE_F32 | DTYPE_I32 => 4,
            DTYPE_F64 | DTYPE_I64 => 8,
            _ => 0,
        }
    }
    /// Element count.
    pub fn len(&self) -> usize {
        match self {
            Column::F32(v) => v.len(),
            Column::F64(v) => v.len(),
            Column::I32(v) => v.len(),
            Column::I64(v) => v.len(),
        }
    }
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
    fn as_ref(&self) -> ColumnRef<'_> {
        match self {
            Column::F32(values) => ColumnRef::F32(values),
            Column::F64(values) => ColumnRef::F64(values),
            Column::I32(values) => ColumnRef::I32(values),
            Column::I64(values) => ColumnRef::I64(values),
        }
    }
    /// View as `f64` (for analog columns, regardless of stored width). Exact for
    /// the f32/f64/i32 arms; the i64 arm rounds magnitudes above 2^53 (not hit by
    /// the codec round-trip, which only feeds analog data through f32/f64).
    pub fn as_f64(&self) -> Vec<f64> {
        match self {
            Column::F32(v) => v.iter().map(|&x| x as f64).collect(),
            Column::F64(v) => v.clone(),
            Column::I32(v) => v.iter().map(|&x| x as f64).collect(),
            Column::I64(v) => v.iter().map(|&x| x as f64).collect(),
        }
    }
    /// View as `i64` (for integer columns like spike senders). Exact for the
    /// i32/i64 arms; the f32/f64 arms truncate toward zero (not hit by the codec
    /// round-trip, which only feeds integer data through i32/i64).
    pub fn as_i64(&self) -> Vec<i64> {
        match self {
            Column::I32(v) => v.iter().map(|&x| x as i64).collect(),
            Column::I64(v) => v.clone(),
            Column::F32(v) => v.iter().map(|&x| x as i64).collect(),
            Column::F64(v) => v.iter().map(|&x| x as i64).collect(),
        }
    }
}

/// Borrowed numeric storage used by the encoder. The view lets an
/// [`Observation`] encode its existing arrays directly instead of cloning the
/// complete payload into an intermediate [`BulkBlock`].
#[derive(Clone, Copy)]
enum ColumnRef<'a> {
    F32(&'a [f32]),
    F64(&'a [f64]),
    I32(&'a [i32]),
    I64(&'a [i64]),
}

impl ColumnRef<'_> {
    fn dtype(self) -> u8 {
        match self {
            ColumnRef::F32(_) => DTYPE_F32,
            ColumnRef::F64(_) => DTYPE_F64,
            ColumnRef::I32(_) => DTYPE_I32,
            ColumnRef::I64(_) => DTYPE_I64,
        }
    }

    fn len(self) -> usize {
        match self {
            ColumnRef::F32(values) => values.len(),
            ColumnRef::F64(values) => values.len(),
            ColumnRef::I32(values) => values.len(),
            ColumnRef::I64(values) => values.len(),
        }
    }

    fn encode_data(self, out: &mut Vec<u8>) {
        match self {
            ColumnRef::F32(values) => values
                .iter()
                .for_each(|value| out.extend_from_slice(&value.to_le_bytes())),
            ColumnRef::F64(values) => values
                .iter()
                .for_each(|value| out.extend_from_slice(&value.to_le_bytes())),
            ColumnRef::I32(values) => values
                .iter()
                .for_each(|value| out.extend_from_slice(&value.to_le_bytes())),
            ColumnRef::I64(values) => values
                .iter()
                .for_each(|value| out.extend_from_slice(&value.to_le_bytes())),
        }
    }
}

/// Why a [`BulkBlock::decode`] of untrusted bytes was rejected.
#[derive(Clone, PartialEq, Eq, Debug)]
pub enum BulkError {
    TooShort,
    BadMagic,
    UnsupportedVersion(u8),
    UnsupportedFlags(u8),
    UnsupportedPadding(u8),
    LengthMismatch {
        declared: usize,
        actual: usize,
    },
    BadDtype(u8),
    /// An offset/length in the directory points outside the block.
    OutOfBounds,
    /// `n_rows * width` would overflow `usize` (allocation bomb).
    Overflow,
    /// A column name was not valid utf-8.
    BadName,
    DuplicateName,
    OverlappingRegion,
    /// Directory offsets do not describe the contiguous name-pool-then-data
    /// layout for the declared directory order. This includes gaps, aliases,
    /// overlaps, and reordered regions.
    NonCanonicalLayout,
    ConflictingPayloadColumns,
    InvalidObservationColumnType(&'static str),
    UnknownObservationColumn(String),
    InvalidObservationData,
    /// The parallel numeric columns (`times`/`values`/`senders`) disagree in
    /// length — they index the same events/samples, so a mismatch is corrupt.
    ColumnLengthMismatch {
        a: &'static str,
        a_len: usize,
        b: &'static str,
        b_len: usize,
    },
    /// A format/resource ceiling was exceeded while encoding or decoding.
    LimitExceeded(&'static str),
    /// The allocator could not reserve a bounded output or decoded column.
    AllocationFailed(&'static str),
}

impl std::fmt::Display for BulkError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            BulkError::TooShort => write!(f, "bulk block shorter than header"),
            BulkError::BadMagic => write!(f, "bulk block has wrong magic (expected NCPB)"),
            BulkError::UnsupportedVersion(v) => write!(f, "unsupported bulk version {v}"),
            BulkError::UnsupportedFlags(x) => write!(f, "unsupported bulk flags {x:#x}"),
            BulkError::UnsupportedPadding(x) => {
                write!(f, "unsupported non-zero bulk directory padding {x:#x}")
            }
            BulkError::LengthMismatch { declared, actual } => {
                write!(f, "bulk total_len {declared} != buffer {actual}")
            }
            BulkError::BadDtype(d) => write!(f, "unknown bulk dtype {d}"),
            BulkError::OutOfBounds => write!(f, "bulk directory offset out of bounds"),
            BulkError::Overflow => write!(f, "bulk column size overflow"),
            BulkError::BadName => {
                write!(f, "bulk column name must be non-empty control-free UTF-8")
            }
            BulkError::DuplicateName => write!(f, "bulk column names must be unique"),
            BulkError::OverlappingRegion => {
                write!(
                    f,
                    "bulk name/data regions overlap or enter the header/directory"
                )
            }
            BulkError::NonCanonicalLayout => {
                write!(f, "bulk directory does not use the canonical contiguous layout")
            }
            BulkError::ConflictingPayloadColumns => {
                write!(f, "bulk observation cannot carry both values and senders")
            }
            BulkError::InvalidObservationColumnType(name) => write!(
                f,
                "bulk observation column {name} uses an incompatible numeric dtype"
            ),
            BulkError::UnknownObservationColumn(name) => {
                write!(f, "bulk observation contains unknown column {name:?}")
            }
            BulkError::InvalidObservationData => write!(
                f,
                "bulk observation metadata or numeric arrays violate the canonical ObservationFrame contract"
            ),
            BulkError::ColumnLengthMismatch { a, a_len, b, b_len } => write!(
                f,
                "bulk parallel columns disagree: {a} has {a_len}, {b} has {b_len}"
            ),
            BulkError::LimitExceeded(limit) => write!(f, "bulk limit exceeded: {limit}"),
            BulkError::AllocationFailed(allocation) => {
                write!(f, "bulk allocation failed: {allocation}")
            }
        }
    }
}

impl std::error::Error for BulkError {}

/// An ordered set of named typed columns. The fixed-width representation avoids
/// a numeric tokenizer but still requires the bounded directory validation below.
#[derive(Clone, PartialEq, Debug, Default)]
pub struct BulkBlock {
    pub columns: Vec<(String, Column)>,
}

impl BulkBlock {
    pub fn new() -> Self {
        BulkBlock::default()
    }

    /// Append a named column (builder style).
    pub fn with(mut self, name: impl Into<String>, col: Column) -> Self {
        self.columns.push((name.into(), col));
        self
    }

    /// Look up a column by name.
    pub fn get(&self, name: &str) -> Option<&Column> {
        self.columns.iter().find(|(n, _)| n == name).map(|(_, c)| c)
    }

    /// The payload column names `values` and `senders` are mutually exclusive,
    /// even when one column is empty. Every present, non-empty numeric column
    /// indexes the same events or samples and must therefore agree in length.
    /// A mismatch is a corrupt or hostile block.
    pub fn check_parallel(&self) -> Result<(), BulkError> {
        if self.get("values").is_some() && self.get("senders").is_some() {
            return Err(BulkError::ConflictingPayloadColumns);
        }
        let mut expected: Option<(&'static str, usize)> = None;
        for name in ["times", "values", "senders"] {
            let n = match self.get(name) {
                Some(c) => c.len(),
                None => continue,
            };
            if n == 0 {
                continue;
            }
            match expected {
                None => expected = Some((name, n)),
                Some((a, a_len)) if a_len != n => {
                    return Err(BulkError::ColumnLengthMismatch {
                        a,
                        a_len,
                        b: name,
                        b_len: n,
                    });
                }
                _ => {}
            }
        }
        Ok(())
    }

    /// Serialize to the packed little-endian block.
    ///
    /// Limits (far above the observation-plane envelope): at most 4096 columns,
    /// 65535 bytes per name, `u32::MAX` rows per column, and 64 MiB total. Every
    /// narrowing conversion and length calculation is checked. The hard byte
    /// ceiling bounds allocator demand before the final buffer is reserved.
    pub fn encode(&self) -> Result<Vec<u8>, BulkError> {
        self.check_parallel()?;
        encode_columns(self.columns.len(), |index| {
            let (name, column) = &self.columns[index];
            (name.as_str(), column.as_ref())
        })
    }

    /// Parse a packed block. Fully bounds-checked against untrusted input.
    pub fn decode(bytes: &[u8]) -> Result<BulkBlock, BulkError> {
        if bytes.len() < HEADER_LEN {
            return Err(BulkError::TooShort);
        }
        if bytes[0..4] != BULK_MAGIC {
            return Err(BulkError::BadMagic);
        }
        if bytes[4] != BULK_VERSION {
            return Err(BulkError::UnsupportedVersion(bytes[4]));
        }
        if bytes[5] != 0 {
            return Err(BulkError::UnsupportedFlags(bytes[5]));
        }
        let n_cols = u16::from_le_bytes([bytes[6], bytes[7]]) as usize;
        if n_cols > BULK_MAX_COLUMNS {
            return Err(BulkError::LimitExceeded("more than 4096 columns"));
        }
        let total_len = u32::from_le_bytes([bytes[8], bytes[9], bytes[10], bytes[11]]) as usize;
        if total_len != bytes.len() {
            return Err(BulkError::LengthMismatch {
                declared: total_len,
                actual: bytes.len(),
            });
        }
        if total_len > BULK_MAX_BYTES {
            return Err(BulkError::LimitExceeded("encoded block exceeds 64 MiB"));
        }
        // The directory itself must fit.
        let dir_end = HEADER_LEN
            .checked_add(
                n_cols
                    .checked_mul(DIR_ENTRY_LEN)
                    .ok_or(BulkError::Overflow)?,
            )
            .ok_or(BulkError::Overflow)?;
        if dir_end > bytes.len() {
            return Err(BulkError::OutOfBounds);
        }

        struct PendingColumn<'a> {
            name: &'a str,
            dtype: u8,
            n_rows: usize,
            data_off: usize,
            data_end: usize,
        }

        let mut pending = Vec::new();
        pending
            .try_reserve_exact(n_cols)
            .map_err(|_| BulkError::AllocationFailed("directory metadata"))?;
        let mut unique_names = std::collections::HashSet::new();
        unique_names
            .try_reserve(n_cols)
            .map_err(|_| BulkError::AllocationFailed("column-name index"))?;
        // The decoder accepts exactly the encoder's single representation. Names
        // are contiguous in directory order immediately after the directory.
        // Data is then contiguous in the same order through total_len. The O(n)
        // prefix check rejects gaps, aliases, overlaps, and reordered regions
        // before any numeric column allocation.
        let mut expected_name_off = dir_end;
        for i in 0..n_cols {
            let base = HEADER_LEN + i * DIR_ENTRY_LEN;
            let e = &bytes[base..base + DIR_ENTRY_LEN];
            let name_off = u32::from_le_bytes([e[0], e[1], e[2], e[3]]) as usize;
            let name_len = u16::from_le_bytes([e[4], e[5]]) as usize;
            let dtype = e[6];
            if e[7] != 0 {
                return Err(BulkError::UnsupportedPadding(e[7]));
            }
            let n_rows = u32::from_le_bytes([e[8], e[9], e[10], e[11]]) as usize;
            let data_off = u32::from_le_bytes([e[12], e[13], e[14], e[15]]) as usize;

            // Name slice in bounds.
            let name_end = name_off.checked_add(name_len).ok_or(BulkError::Overflow)?;
            if name_off < dir_end || name_end < name_off {
                return Err(BulkError::OverlappingRegion);
            }
            if name_off != expected_name_off {
                return Err(BulkError::NonCanonicalLayout);
            }
            let name_bytes = bytes
                .get(name_off..name_end)
                .ok_or(BulkError::OutOfBounds)?;
            let name = std::str::from_utf8(name_bytes).map_err(|_| BulkError::BadName)?;
            if name.is_empty() || name.chars().any(char::is_control) {
                return Err(BulkError::BadName);
            }
            if !unique_names.insert(name) {
                return Err(BulkError::DuplicateName);
            }
            expected_name_off = name_end;

            let width = Column::width(dtype);
            if width == 0 {
                return Err(BulkError::BadDtype(dtype));
            }
            let data_len = n_rows.checked_mul(width).ok_or(BulkError::Overflow)?;
            let data_end = data_off.checked_add(data_len).ok_or(BulkError::Overflow)?;
            if data_off < dir_end || data_end < data_off {
                return Err(BulkError::OverlappingRegion);
            }
            bytes
                .get(data_off..data_end)
                .ok_or(BulkError::OutOfBounds)?;
            pending.push(PendingColumn {
                name,
                dtype,
                n_rows,
                data_off,
                data_end,
            });
        }

        let mut expected_data_off = expected_name_off;
        for entry in &pending {
            if entry.data_off != expected_data_off {
                return Err(BulkError::NonCanonicalLayout);
            }
            expected_data_off = entry.data_end;
        }
        if expected_data_off != total_len {
            return Err(BulkError::NonCanonicalLayout);
        }

        // Only allocate owned names and numeric columns after the complete
        // directory has passed the canonical prefix check.
        let mut columns = Vec::new();
        columns
            .try_reserve_exact(n_cols)
            .map_err(|_| BulkError::AllocationFailed("decoded column directory"))?;
        for entry in pending {
            let data = &bytes[entry.data_off..entry.data_end];
            let col = decode_column(entry.dtype, data, entry.n_rows)?;
            let mut name = String::new();
            name.try_reserve_exact(entry.name.len())
                .map_err(|_| BulkError::AllocationFailed("decoded column name"))?;
            name.push_str(entry.name);
            columns.push((name, col));
        }
        let block = BulkBlock { columns };
        block.check_parallel()?;
        Ok(block)
    }
}

fn encode_columns<'a, F>(n_cols: usize, column_at: F) -> Result<Vec<u8>, BulkError>
where
    F: Fn(usize) -> (&'a str, ColumnRef<'a>),
{
    if n_cols > BULK_MAX_COLUMNS {
        return Err(BulkError::LimitExceeded("more than 4096 columns"));
    }

    // Preflight every narrowing conversion and length before reserving. The
    // callback returns borrowed slices, so large numeric arrays never need an
    // intermediate copy merely to construct the final block. A bounded hash
    // index holds borrowed column-name references during duplicate detection.
    let dir_len = n_cols
        .checked_mul(DIR_ENTRY_LEN)
        .ok_or(BulkError::Overflow)?;
    let mut name_pool_len = 0usize;
    let mut data_len = 0usize;
    let mut unique_names = std::collections::HashSet::new();
    unique_names
        .try_reserve(n_cols)
        .map_err(|_| BulkError::AllocationFailed("column-name index"))?;
    for index in 0..n_cols {
        let (name, column) = column_at(index);
        if name.is_empty() || name.chars().any(char::is_control) {
            return Err(BulkError::BadName);
        }
        if !unique_names.insert(name) {
            return Err(BulkError::DuplicateName);
        }
        u16::try_from(name.len())
            .map_err(|_| BulkError::LimitExceeded("column name longer than 65535 bytes"))?;
        u32::try_from(column.len())
            .map_err(|_| BulkError::LimitExceeded("column has more than u32::MAX rows"))?;
        name_pool_len = name_pool_len
            .checked_add(name.len())
            .ok_or(BulkError::Overflow)?;
        data_len = data_len
            .checked_add(
                column
                    .len()
                    .checked_mul(Column::width(column.dtype()))
                    .ok_or(BulkError::Overflow)?,
            )
            .ok_or(BulkError::Overflow)?;
    }
    let total_len = HEADER_LEN
        .checked_add(dir_len)
        .and_then(|length| length.checked_add(name_pool_len))
        .and_then(|length| length.checked_add(data_len))
        .ok_or(BulkError::Overflow)?;
    if total_len > BULK_MAX_BYTES {
        return Err(BulkError::LimitExceeded("encoded block exceeds 64 MiB"));
    }
    let n_cols_wire = u16::try_from(n_cols)
        .map_err(|_| BulkError::LimitExceeded("more than u16::MAX columns"))?;
    let total_len_wire = u32::try_from(total_len)
        .map_err(|_| BulkError::LimitExceeded("encoded block exceeds u32::MAX bytes"))?;
    let name_pool_start = HEADER_LEN.checked_add(dir_len).ok_or(BulkError::Overflow)?;
    let data_start = name_pool_start
        .checked_add(name_pool_len)
        .ok_or(BulkError::Overflow)?;

    let mut out = Vec::new();
    out.try_reserve_exact(total_len)
        .map_err(|_| BulkError::AllocationFailed("encoded block"))?;
    out.extend_from_slice(&BULK_MAGIC);
    out.push(BULK_VERSION);
    out.push(0);
    out.extend_from_slice(&n_cols_wire.to_le_bytes());
    out.extend_from_slice(&total_len_wire.to_le_bytes());

    // The directory uses checked running prefixes. No offset vectors, name
    // staging buffer, or data staging buffer coexist with the final output.
    let mut next_name_off = name_pool_start;
    let mut next_data_off = data_start;
    for index in 0..n_cols {
        let (name, column) = column_at(index);
        let name_off_wire = u32::try_from(next_name_off).map_err(|_| BulkError::Overflow)?;
        let name_len_wire = u16::try_from(name.len())
            .map_err(|_| BulkError::LimitExceeded("column name longer than 65535 bytes"))?;
        let row_count_wire = u32::try_from(column.len())
            .map_err(|_| BulkError::LimitExceeded("column has more than u32::MAX rows"))?;
        let data_off_wire = u32::try_from(next_data_off).map_err(|_| BulkError::Overflow)?;
        out.extend_from_slice(&name_off_wire.to_le_bytes());
        out.extend_from_slice(&name_len_wire.to_le_bytes());
        out.push(column.dtype());
        out.push(0);
        out.extend_from_slice(&row_count_wire.to_le_bytes());
        out.extend_from_slice(&data_off_wire.to_le_bytes());
        next_name_off = next_name_off
            .checked_add(name.len())
            .ok_or(BulkError::Overflow)?;
        next_data_off = next_data_off
            .checked_add(
                column
                    .len()
                    .checked_mul(Column::width(column.dtype()))
                    .ok_or(BulkError::Overflow)?,
            )
            .ok_or(BulkError::Overflow)?;
    }
    debug_assert_eq!(next_name_off, data_start);
    debug_assert_eq!(next_data_off, total_len);
    for index in 0..n_cols {
        out.extend_from_slice(column_at(index).0.as_bytes());
    }
    for index in 0..n_cols {
        column_at(index).1.encode_data(&mut out);
    }
    debug_assert_eq!(out.len(), total_len);
    Ok(out)
}

fn decode_column(dtype: u8, data: &[u8], n_rows: usize) -> Result<Column, BulkError> {
    macro_rules! read {
        ($ty:ty, $variant:ident, $w:expr) => {{
            let mut v = Vec::new();
            v.try_reserve_exact(n_rows)
                .map_err(|_| BulkError::AllocationFailed("decoded numeric column"))?;
            for chunk in data.chunks_exact($w) {
                let mut buf = [0u8; $w];
                buf.copy_from_slice(chunk);
                v.push(<$ty>::from_le_bytes(buf));
            }
            Ok(Column::$variant(v))
        }};
    }
    match dtype {
        DTYPE_F32 => read!(f32, F32, 4),
        DTYPE_F64 => read!(f64, F64, 8),
        DTYPE_I32 => read!(i32, I32, 4),
        DTYPE_I64 => read!(i64, I64, 8),
        _ => unreachable!("dtype validated by caller"),
    }
}

struct ObservationColumns<'a> {
    observation: &'a Observation,
}

impl<'a> ObservationColumns<'a> {
    fn len(&self) -> usize {
        usize::from(!self.observation.times.is_empty())
            + usize::from(!self.observation.values.is_empty())
            + usize::from(!self.observation.senders.is_empty())
    }

    fn get(&self, mut index: usize) -> (&'static str, ColumnRef<'a>) {
        if !self.observation.times.is_empty() {
            if index == 0 {
                return ("times", ColumnRef::F64(&self.observation.times));
            }
            index -= 1;
        }
        if !self.observation.values.is_empty() {
            if index == 0 {
                return ("values", ColumnRef::F64(&self.observation.values));
            }
            index -= 1;
        }
        if !self.observation.senders.is_empty() && index == 0 {
            return ("senders", ColumnRef::I64(&self.observation.senders));
        }
        unreachable!("encoder indexes only the reported observation columns")
    }

    fn check_parallel(&self) -> Result<(), BulkError> {
        if !self.observation.values.is_empty() && !self.observation.senders.is_empty() {
            return Err(BulkError::ConflictingPayloadColumns);
        }
        let (payload_name, payload_len) = if !self.observation.values.is_empty() {
            ("values", self.observation.values.len())
        } else if !self.observation.senders.is_empty() {
            ("senders", self.observation.senders.len())
        } else {
            ("payload", 0)
        };
        let times_len = self.observation.times.len();
        if times_len != payload_len && (times_len > 0 || payload_len > 0) {
            return Err(BulkError::ColumnLengthMismatch {
                a: "times",
                a_len: times_len,
                b: payload_name,
                b_len: payload_len,
            });
        }
        Ok(())
    }
}

impl Observation {
    /// Pack this observation's bulk numeric arrays into a [`BulkBlock`]
    /// (lossless: `times`/`values` as f64, `senders` as i64). Only non-empty
    /// arrays become columns, so a spike port (times+senders) and an analog port
    /// (times+values) each pack just their two populated columns.
    pub fn to_bulk_block(&self) -> BulkBlock {
        let mut b = BulkBlock::new();
        if !self.times.is_empty() {
            b = b.with("times", Column::F64(self.times.clone()));
        }
        if !self.values.is_empty() {
            b = b.with("values", Column::F64(self.values.clone()));
        }
        if !self.senders.is_empty() {
            b = b.with("senders", Column::I64(self.senders.clone()));
        }
        b
    }

    /// Replace this observation's bulk arrays from a decoded [`BulkBlock`]
    /// (the inverse of [`Observation::to_bulk_block`]; tolerant of compact
    /// f32/i32 widths). Columns absent from the block are cleared.
    pub fn apply_bulk_block(&mut self, b: &BulkBlock) {
        self.times = b.get("times").map(Column::as_f64).unwrap_or_default();
        self.values = b.get("values").map(Column::as_f64).unwrap_or_default();
        self.senders = b.get("senders").map(Column::as_i64).unwrap_or_default();
    }

    /// Encode the existing arrays directly for local/offline use or a
    /// conformance fixture. This path borrows the numeric slices and allocates
    /// one final bulk-data buffer plus a small duplicate-name index. It does not
    /// clone the numeric arrays. [`Observation::to_bulk_block`] remains available
    /// when the caller explicitly needs an owned, mutable column representation.
    pub fn to_bulk_bytes(&self) -> Result<Vec<u8>, BulkError> {
        let columns = ObservationColumns { observation: self };
        columns.check_parallel()?;
        encode_columns(columns.len(), |index| columns.get(index))
    }
}

/// Reconstruct an [`Observation`] from metadata plus a local packed block. The
/// result is checked against the canonical ObservationFrame semantics; this is
/// not permission to publish the bare block on an NCP plane.
pub fn observation_from_bulk(
    port: impl Into<String>,
    target: impl Into<String>,
    observable: Observable,
    unit: Option<String>,
    recordable: Option<String>,
    block: &[u8],
) -> Result<Observation, BulkError> {
    let b = BulkBlock::decode(block)?;
    b.check_parallel()?; // cross-column length invariant: fail closed on a corrupt block
    if let Some((name, _)) = b
        .columns
        .iter()
        .find(|(name, _)| !matches!(name.as_str(), "times" | "values" | "senders"))
    {
        return Err(BulkError::UnknownObservationColumn(name.clone()));
    }
    if b.get("times")
        .is_some_and(|column| !matches!(column, Column::F32(_) | Column::F64(_)))
    {
        return Err(BulkError::InvalidObservationColumnType("times"));
    }
    if b.get("values")
        .is_some_and(|column| !matches!(column, Column::F32(_) | Column::F64(_)))
    {
        return Err(BulkError::InvalidObservationColumnType("values"));
    }
    if b.get("senders")
        .is_some_and(|column| !matches!(column, Column::I32(_) | Column::I64(_)))
    {
        return Err(BulkError::InvalidObservationColumnType("senders"));
    }
    let port = port.into();
    let mut obs = Observation {
        port: port.clone(),
        target: target.into(),
        observable,
        unit,
        recordable,
        ..Default::default()
    };
    obs.apply_bulk_block(&b);
    // Local records validation only: give the envelope fixed valid candidate
    // identity so validate_wire exercises the record and finite-value checks
    // rather than rejecting on identity that the caller supplies at publish.
    let frame = ObservationFrame {
        session_id: "bulk-local-validation".into(),
        stream: StreamPosition {
            epoch: "00000000-0000-4000-8000-000000000001".into(),
            seq: 1,
        },
        session: SessionRef {
            generation: "00000000-0000-4000-8000-0000000000a2".into(),
        },
        records: [(port, obs.clone())].into_iter().collect(),
        ..Default::default()
    };
    frame
        .validate_wire()
        .map_err(|_| BulkError::InvalidObservationData)?;
    Ok(obs)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn roundtrip_all_dtypes() {
        let b = BulkBlock::new()
            .with("a_f32", Column::F32(vec![1.5, -2.25, f32::MAX]))
            .with("b_f64", Column::F64(vec![1.0, 2.0, 3.5, -4.0]))
            .with("c_i32", Column::I32(vec![-1, 0, 7, i32::MIN]))
            .with("d_i64", Column::I64(vec![0, -9_000_000_000, i64::MAX]));
        let bytes = b.encode().unwrap();
        let back = BulkBlock::decode(&bytes).unwrap();
        assert_eq!(b, back);
    }

    #[test]
    fn roundtrip_empty_block_and_empty_columns() {
        let empty = BulkBlock::new();
        assert_eq!(BulkBlock::decode(&empty.encode().unwrap()).unwrap(), empty);

        let with_empty = BulkBlock::new()
            .with("times", Column::F64(vec![]))
            .with("senders", Column::I64(vec![]));
        assert_eq!(
            BulkBlock::decode(&with_empty.encode().unwrap()).unwrap(),
            with_empty
        );
    }

    #[test]
    fn decode_rejects_amplifying_overlap() {
        // Two columns whose data regions overlap and together declare more
        // payload than the input holds. Each slice is individually in bounds.
        // The canonical running-prefix check must reject the second alias before
        // any numeric column allocation.
        let total: usize = 2048;
        let mut b = vec![0u8; total];
        b[0..4].copy_from_slice(&BULK_MAGIC);
        b[4] = BULK_VERSION;
        b[5] = 0;
        b[6..8].copy_from_slice(&2u16.to_le_bytes()); // n_cols = 2
        b[8..12].copy_from_slice(&(total as u32).to_le_bytes());
        let names_off = HEADER_LEN + 2 * DIR_ENTRY_LEN;
        b[names_off..names_off + 2].copy_from_slice(b"ab");
        let data_off = (names_off + 2) as u32;
        let n_rows: u32 = 250;
        for i in 0..2u32 {
            let base = 12 + (i as usize) * 16;
            let name_off = (names_off + i as usize) as u32;
            b[base..base + 4].copy_from_slice(&name_off.to_le_bytes());
            b[base + 4..base + 6].copy_from_slice(&1u16.to_le_bytes());
            b[base + 6] = 2; // DTYPE_F64
            b[base + 8..base + 12].copy_from_slice(&n_rows.to_le_bytes());
            b[base + 12..base + 16].copy_from_slice(&data_off.to_le_bytes());
        }
        assert_eq!(
            BulkBlock::decode(&b),
            Err(BulkError::NonCanonicalLayout),
            "the second aliased data region must fail the canonical prefix check"
        );
    }

    #[test]
    fn decode_rejects_amplifying_overlapping_names() {
        // Two directory entries alias the same 1024-byte name. Each slice is in
        // bounds, but copying it twice would allocate more name data than the
        // entire input. The shared allocation budget must reject before the second
        // String allocation (the 65k-column form was a multi-GiB OOM vector).
        let name_len = 1024usize;
        let name_off = HEADER_LEN + 2 * DIR_ENTRY_LEN;
        let total = name_off + name_len;
        let mut bytes = vec![0; total];
        bytes[0..4].copy_from_slice(&BULK_MAGIC);
        bytes[4] = BULK_VERSION;
        bytes[5] = 0;
        bytes[6..8].copy_from_slice(&2u16.to_le_bytes());
        bytes[8..12].copy_from_slice(&(total as u32).to_le_bytes());
        for i in 0..2 {
            let base = HEADER_LEN + i * DIR_ENTRY_LEN;
            bytes[base..base + 4].copy_from_slice(&(name_off as u32).to_le_bytes());
            bytes[base + 4..base + 6].copy_from_slice(&(name_len as u16).to_le_bytes());
            bytes[base + 6] = DTYPE_F64;
            bytes[base + 8..base + 12].copy_from_slice(&0u32.to_le_bytes());
            bytes[base + 12..base + 16].copy_from_slice(&(total as u32).to_le_bytes());
        }
        bytes[name_off..].fill(b'a');
        assert_eq!(
            BulkBlock::decode(&bytes),
            Err(BulkError::NonCanonicalLayout)
        );
    }

    #[test]
    fn bulk_column_ceiling_bounds_directory_work() {
        let block = BulkBlock {
            columns: (0..=BULK_MAX_COLUMNS)
                .map(|index| (format!("c{index}"), Column::F64(Vec::new())))
                .collect(),
        };
        assert!(matches!(
            block.encode(),
            Err(BulkError::LimitExceeded("more than 4096 columns"))
        ));

        // The decode gate runs before allocating/parsing the directory.
        let n_cols = BULK_MAX_COLUMNS + 1;
        let total_len = HEADER_LEN + n_cols * DIR_ENTRY_LEN;
        let mut hostile = vec![0; total_len];
        hostile[0..4].copy_from_slice(&BULK_MAGIC);
        hostile[4] = BULK_VERSION;
        hostile[6..8].copy_from_slice(&(n_cols as u16).to_le_bytes());
        hostile[8..12].copy_from_slice(&(total_len as u32).to_le_bytes());
        assert_eq!(
            BulkBlock::decode(&hostile),
            Err(BulkError::LimitExceeded("more than 4096 columns"))
        );

        // A maximum-width valid directory still round-trips. Canonical prefix
        // checking is O(n), not the former pairwise O(n^2) scan.
        let max = BulkBlock {
            columns: (0..BULK_MAX_COLUMNS)
                .map(|index| (format!("c{index}"), Column::F64(Vec::new())))
                .collect(),
        };
        let encoded = max.encode().expect("maximum-width block encodes");
        assert_eq!(
            BulkBlock::decode(&encoded)
                .expect("maximum-width block decodes")
                .columns
                .len(),
            BULK_MAX_COLUMNS
        );
    }

    #[test]
    fn decode_rejects_unequal_parallel_columns() {
        // times has 3, senders has 2 -> corrupt parallel block -> fail closed.
        let bad = BulkBlock::new()
            .with("times", Column::F64(vec![0.0, 1.0, 2.0]))
            .with("senders", Column::I64(vec![1, 2]));
        let err = bad.encode().unwrap_err();
        assert!(
            matches!(err, BulkError::ColumnLengthMismatch { .. }),
            "unequal parallel columns must fail closed, got {err:?}"
        );
        let mut hostile = BulkBlock::new()
            .with("aaaaa", Column::F64(vec![0.0, 1.0, 2.0]))
            .with("xxxxxxx", Column::I64(vec![1, 2]))
            .encode()
            .unwrap();
        for (index, replacement) in [(0usize, b"times".as_slice()), (1, b"senders".as_slice())] {
            let base = HEADER_LEN + index * DIR_ENTRY_LEN;
            let name_off = u32::from_le_bytes(hostile[base..base + 4].try_into().unwrap()) as usize;
            hostile[name_off..name_off + replacement.len()].copy_from_slice(replacement);
        }
        assert!(matches!(
            BulkBlock::decode(&hostile),
            Err(BulkError::ColumnLengthMismatch { .. })
        ));
        // Equal lengths still round-trip cleanly.
        let ok = BulkBlock::new()
            .with("times", Column::F64(vec![0.0, 1.0]))
            .with("senders", Column::I64(vec![1, 2]));
        assert!(observation_from_bulk(
            "spk",
            "pop",
            Observable::Spikes,
            None,
            None,
            &ok.encode().unwrap(),
        )
        .is_ok());
    }

    #[test]
    fn preserves_non_finite_f64() {
        let b = BulkBlock::new().with(
            "vm",
            Column::F64(vec![f64::NAN, f64::INFINITY, f64::NEG_INFINITY, 0.0]),
        );
        let back = BulkBlock::decode(&b.encode().unwrap()).unwrap();
        if let Some(Column::F64(v)) = back.get("vm") {
            assert!(v[0].is_nan());
            assert_eq!(v[1], f64::INFINITY);
            assert_eq!(v[2], f64::NEG_INFINITY);
            assert_eq!(v[3], 0.0);
        } else {
            panic!("vm column missing/wrong type");
        }
    }

    #[test]
    fn observation_spike_and_analog_roundtrip() {
        // Spike port: times + senders, no values.
        let spk = Observation {
            port: "spk".into(),
            target: "exc".into(),
            observable: Observable::Spikes,
            times: vec![1.0, 1.2, 5.7, 9.9],
            senders: vec![3, 3, 7, 12],
            ..Default::default()
        };
        let bytes = spk.to_bulk_bytes().unwrap();
        let rebuilt =
            observation_from_bulk("spk", "exc", Observable::Spikes, None, None, &bytes).unwrap();
        assert_eq!(rebuilt.times, spk.times);
        assert_eq!(rebuilt.senders, spk.senders);
        assert!(rebuilt.values.is_empty());

        // Analog port: times + values, no senders.
        let vm = Observation {
            port: "vm".into(),
            target: "exc".into(),
            observable: Observable::Vm,
            times: vec![0.0, 1.0, 2.0],
            values: vec![-70.0, -69.5, -55.0],
            unit: Some("mV".into()),
            ..Default::default()
        };
        let mut back = BulkBlock::new();
        back = BulkBlock::decode(&vm.to_bulk_bytes().unwrap()).unwrap_or(back);
        let mut rebuilt_vm = Observation::default();
        rebuilt_vm.apply_bulk_block(&back);
        assert_eq!(rebuilt_vm.times, vm.times);
        assert_eq!(rebuilt_vm.values, vm.values);
        assert!(rebuilt_vm.senders.is_empty());
    }

    #[test]
    fn borrowed_observation_encoder_rejects_missing_or_orphan_times() {
        let missing_times = Observation {
            port: "vm".into(),
            target: "exc".into(),
            observable: Observable::Vm,
            values: vec![-65.0],
            ..Default::default()
        };
        assert!(matches!(
            missing_times.to_bulk_bytes(),
            Err(BulkError::ColumnLengthMismatch {
                a: "times",
                a_len: 0,
                b: "values",
                b_len: 1,
            })
        ));

        let orphan_times = Observation {
            port: "spk".into(),
            target: "exc".into(),
            observable: Observable::Spikes,
            times: vec![1.0],
            ..Default::default()
        };
        assert!(matches!(
            orphan_times.to_bulk_bytes(),
            Err(BulkError::ColumnLengthMismatch {
                a: "times",
                a_len: 1,
                b: "payload",
                b_len: 0,
            })
        ));
    }

    #[test]
    fn observation_reconstruction_rejects_type_confusion_and_invalid_arrays() {
        let unknown = BulkBlock::new()
            .with("times", Column::F64(vec![1.0]))
            .with("values", Column::F64(vec![-65.0]))
            .with("hidden", Column::F64(vec![1.0]))
            .encode()
            .unwrap();
        assert_eq!(
            observation_from_bulk("vm", "pop", Observable::Vm, None, None, &unknown),
            Err(BulkError::UnknownObservationColumn("hidden".into()))
        );

        let float_senders = BulkBlock::new()
            .with("times", Column::F64(vec![1.0]))
            .with("senders", Column::F64(vec![1.0]))
            .encode()
            .unwrap();
        assert_eq!(
            observation_from_bulk("spk", "pop", Observable::Spikes, None, None, &float_senders,),
            Err(BulkError::InvalidObservationColumnType("senders"))
        );

        let missing_times = BulkBlock::new()
            .with("values", Column::F64(vec![-65.0]))
            .encode()
            .unwrap();
        assert_eq!(
            observation_from_bulk(
                "vm",
                "pop",
                Observable::Vm,
                Some("mV".into()),
                None,
                &missing_times,
            ),
            Err(BulkError::InvalidObservationData)
        );

        let nonfinite = BulkBlock::new()
            .with("times", Column::F64(vec![1.0]))
            .with("values", Column::F64(vec![f64::NAN]))
            .encode()
            .unwrap();
        assert_eq!(
            observation_from_bulk("vm", "pop", Observable::Vm, None, None, &nonfinite,),
            Err(BulkError::InvalidObservationData)
        );
    }

    #[test]
    fn compact_f32_widths_halve_senders_and_values() {
        // The issue's f32-values + i32-senders compaction path.
        let block = BulkBlock::new()
            .with("analog", Column::F32(vec![1.0, 2.0, 3.0]))
            .with("ids", Column::I32(vec![1, 2, 3]));
        let bytes = block.encode().unwrap();
        let decoded = BulkBlock::decode(&bytes).unwrap();
        assert_eq!(decoded.get("analog").unwrap().as_f64(), vec![1.0, 2.0, 3.0]);
        assert_eq!(decoded.get("ids").unwrap().as_i64(), vec![1, 2, 3]);
    }

    #[test]
    fn rejects_duplicate_names_nonzero_padding_and_conflicting_payloads() {
        let mut duplicate = BulkBlock::new()
            .with("aaaa", Column::F64(vec![1.0]))
            .with("bbbb", Column::F64(vec![2.0]))
            .encode()
            .unwrap();
        let second = HEADER_LEN + DIR_ENTRY_LEN;
        let second_name_off =
            u32::from_le_bytes(duplicate[second..second + 4].try_into().unwrap()) as usize;
        duplicate[second_name_off..second_name_off + 4].copy_from_slice(b"aaaa");
        assert_eq!(BulkBlock::decode(&duplicate), Err(BulkError::DuplicateName));

        let mut padded = BulkBlock::new()
            .with("x", Column::F64(vec![1.0]))
            .encode()
            .unwrap();
        padded[HEADER_LEN + 7] = 1;
        assert_eq!(
            BulkBlock::decode(&padded),
            Err(BulkError::UnsupportedPadding(1))
        );

        let duplicate_builder = BulkBlock::new()
            .with("x", Column::F64(vec![]))
            .with("x", Column::F64(vec![]));
        assert_eq!(duplicate_builder.encode(), Err(BulkError::DuplicateName));

        // Column presence is semantic. An empty values column cannot coexist
        // with senders and create a second byte representation of one spike
        // observation.
        let mixed_payload_kinds = BulkBlock::new()
            .with("times", Column::F64(vec![1.0]))
            .with("values", Column::F64(vec![]))
            .with("senders", Column::I64(vec![7]));
        assert_eq!(
            mixed_payload_kinds.encode(),
            Err(BulkError::ConflictingPayloadColumns)
        );

        // Encode under neutral names, then mutate the same-length name bytes to
        // the mutually-exclusive observation columns.
        let mut conflicting = BulkBlock::new()
            .with("values", Column::F64(vec![1.0]))
            .with("xxxxxxx", Column::I64(vec![1]))
            .encode()
            .unwrap();
        let second_name_off =
            u32::from_le_bytes(conflicting[second..second + 4].try_into().unwrap()) as usize;
        conflicting[second_name_off..second_name_off + 7].copy_from_slice(b"senders");
        assert_eq!(
            BulkBlock::decode(&conflicting),
            Err(BulkError::ConflictingPayloadColumns)
        );
    }

    #[test]
    fn rejects_disjoint_but_reordered_data_regions() {
        let mut bytes = BulkBlock::new()
            .with("left", Column::I64(vec![1]))
            .with("right", Column::I64(vec![2]))
            .encode()
            .unwrap();
        let first_data = HEADER_LEN + 12;
        let second_data = HEADER_LEN + DIR_ENTRY_LEN + 12;
        let first_offset: [u8; 4] = bytes[first_data..first_data + 4].try_into().unwrap();
        let second_offset: [u8; 4] = bytes[second_data..second_data + 4].try_into().unwrap();
        bytes[first_data..first_data + 4].copy_from_slice(&second_offset);
        bytes[second_data..second_data + 4].copy_from_slice(&first_offset);
        assert_eq!(
            BulkBlock::decode(&bytes),
            Err(BulkError::NonCanonicalLayout)
        );
    }

    #[test]
    fn rejects_bad_magic() {
        let mut bytes = BulkBlock::new()
            .with("x", Column::F64(vec![1.0]))
            .encode()
            .unwrap();
        bytes[0] = b'X';
        assert_eq!(BulkBlock::decode(&bytes), Err(BulkError::BadMagic));
    }

    #[test]
    fn rejects_truncation() {
        let bytes = BulkBlock::new()
            .with("x", Column::F64(vec![1.0, 2.0, 3.0]))
            .encode()
            .unwrap();
        // Drop the last 4 bytes: total_len no longer matches the buffer.
        let truncated = &bytes[..bytes.len() - 4];
        assert!(matches!(
            BulkBlock::decode(truncated),
            Err(BulkError::LengthMismatch { .. })
        ));
    }

    #[test]
    fn rejects_too_short() {
        assert_eq!(BulkBlock::decode(&[]), Err(BulkError::TooShort));
        assert_eq!(BulkBlock::decode(b"NCP"), Err(BulkError::TooShort));
    }

    #[test]
    fn rejects_allocation_bomb_nrows() {
        // Hand-craft a header claiming a single column with a huge n_rows but a
        // tiny buffer: the data-slice bounds check must reject it (no OOM).
        let mut bytes = Vec::new();
        bytes.extend_from_slice(&BULK_MAGIC);
        bytes.push(BULK_VERSION);
        bytes.push(0);
        bytes.extend_from_slice(&1u16.to_le_bytes()); // n_cols = 1
        let total_len = (HEADER_LEN + DIR_ENTRY_LEN + 1) as u32;
        bytes.extend_from_slice(&total_len.to_le_bytes());
        // directory entry: one-byte name immediately after the directory,
        // n_rows=u32::MAX, data_off=total_len
        bytes.extend_from_slice(&(total_len - 1).to_le_bytes()); // name_off
        bytes.extend_from_slice(&1u16.to_le_bytes()); // name_len
        bytes.push(DTYPE_F64);
        bytes.push(0);
        bytes.extend_from_slice(&u32::MAX.to_le_bytes()); // n_rows
        bytes.extend_from_slice(&total_len.to_le_bytes()); // data_off (== end)
        bytes.push(b'x');
        assert_eq!(bytes.len(), total_len as usize);
        // n_rows*8 points way past the buffer -> OutOfBounds, never an allocation.
        assert_eq!(BulkBlock::decode(&bytes), Err(BulkError::OutOfBounds));
    }

    #[test]
    fn rejects_bad_dtype() {
        let mut bytes = BulkBlock::new()
            .with("x", Column::F64(vec![1.0]))
            .encode()
            .unwrap();
        // dtype byte sits at directory entry offset 6.
        bytes[HEADER_LEN + 6] = 99;
        assert_eq!(BulkBlock::decode(&bytes), Err(BulkError::BadDtype(99)));
    }

    /// Cross-language byte stability for the local/offline format. The Rust
    /// encoder must produce the exact committed fixture bytes. The fixture pins
    /// this binary layout without making the bare block an NCP plane payload.
    #[test]
    fn matches_committed_golden_vector() {
        let golden = include_bytes!(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/testdata/conformance/vectors/bulk_observation.bin"
        ));
        let block = BulkBlock::new()
            .with("times", Column::F64(vec![1.5, 2.5, 9.0]))
            .with("senders", Column::I64(vec![7, 7, 9]));
        assert_eq!(
            block.encode().unwrap().as_slice(),
            &golden[..],
            "Rust bulk encoding drifted from the committed golden vector"
        );
        assert_eq!(BulkBlock::decode(golden).unwrap(), block);
    }

    #[test]
    fn fifty_k_spikes_roundtrip() {
        // The motivating payload: 50k spikes (times + senders).
        let n = 50_000;
        let times: Vec<f64> = (0..n).map(|i| i as f64 * 0.1).collect();
        let senders: Vec<i64> = (0..n).map(|i| (i % 128) as i64).collect();
        let block = BulkBlock::new()
            .with("times", Column::F64(times.clone()))
            .with("senders", Column::I64(senders.clone()));
        let bytes = block.encode().unwrap();
        // Header + dir + names + 50k*8 (times) + 50k*8 (senders).
        assert_eq!(bytes.len(), HEADER_LEN + 2 * DIR_ENTRY_LEN + 5 + 7 + n * 16);
        let back = BulkBlock::decode(&bytes).unwrap();
        assert_eq!(back.get("times").unwrap().as_f64(), times);
        assert_eq!(back.get("senders").unwrap().as_i64(), senders);
    }
}
