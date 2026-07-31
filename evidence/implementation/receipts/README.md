# Implementation receipt artifact policy

This directory contains immutable task-receipt artifacts. A receipt records
bounded evidence for one exact Git cut. A receipt does not authorize a release.

## Current admission rule

The implementation-ledger checker resolves each artifact from the receipt
evidence commit. The checker verifies the declared byte count and SHA-256 digest.
It then applies a bounded content scan.

New passing and coordination artifacts must not contain sensitive host data.
The checker rejects recognized credential and private-key patterns. It also
rejects an unqualified slash-root string, local file or editor URI, network
share path, Windows drive path, or Windows UNC path. This rule is conservative:
it also rejects a root-relative URI path or JSON Pointer unless the value is in
a complete network URL.
The checker applies the same path classifier to string metadata in the ledger.

Reviewers must inspect the full artifact for sensitive values that no finite
pattern set can identify. The checker supports only these representations:

- strict UTF-8 text with `.log`, `.txt`, `.md`, `.json`, `.jsonl`, `.csv`, or
  `.tsv`
- one no-option gzip member with a supported lowercase inner text suffix
- a bounded PNG subset with explicit text metadata

An unrecognized suffix and each recognized alternate/container signature fail
until the checker has a bounded decoder. The scanner does not decode arbitrary
embeddings such as a Base64 data URI in Markdown. Reviewers must inspect those
embeddings or remove them. It also does not infer a multi-line structured
document from surrounding unstructured log text.
The text scanner rejects terminal and invisible format controls. It enforces
line-count and line-length limits without creating a list of all lines. JSON and
JSONL artifacts receive a bounded semantic parse. A complete JSON document and
each independently valid JSON record in another text format also receive this
parse. The scan follows bounded nested JSON strings, enforces one aggregate
100,000-node budget, rejects duplicate keys in recognized JSON, and scans both
raw text and decoded string escapes.

The gzip decoder rejects optional header fields, nested, concatenated, trailing,
truncated, and over-limit streams. The PNG subset permits `IHDR`, consecutive
`IDAT`, `IEND`, and `tEXt`, `zTXt`, or `iTXt` chunks only. It excludes palette
images. The parser checks chunk order and checksums, the image-header contract,
bounded raster decompression, exact scanline length, filter identifiers, and
each text field. Width and height cannot exceed 8,192 pixels, and the image
cannot exceed 16,777,216 pixels. The parser rejects animated PNG and opaque
metadata such as EXIF and color profiles.
It permits at most 64 text chunks and 1 MiB of decoded text metadata. JSON text
inside those chunks receives the same semantic scan.

The checker does not inspect text that is visible only in PNG pixels. Reviewers
must inspect each retained image for private data before admission. This visual
review does not detect steganographic content.

## Immutable pre-policy classification

Six logs entered passing B00 or B04 receipts before this content policy existed.
The logs contain absolute paths from the machine that ran the local checks. The
logs contain no token or private-key pattern that the current checker recognizes.

These files are local-only and non-portable evidence. Do not edit, recompress,
copy, or reuse them in a new receipt. Their exception requires the exact task,
source commit, evidence commit, path, stored identity, and decoded identity.

The `private-home lines` column counts decoded lines that contain a `/Users/` or
`/home/` root. The `host-path lines` column counts all decoded lines that the
current host-path policy detects. A line can contain more than one path.

| Task | Artifact | Stored bytes | Stored SHA-256 | Decoded bytes | Decoded SHA-256 | Private-home lines | Host-path lines |
|---|---|---:|---|---:|---|---:|---:|
| B00 | `B00/full-preflight-6381d2a.log.gz` | 56,414 | `c68796b52218a659cac4fd837200f2daa5006c07ec88d2cd8d7373ca07196cda` | 519,748 | `2f715761cc4a45399a47d7957eb7c8669c01caa3c21f17c24ae47b8af2a38310` | 61 | 110 |
| B04 | `B04/current-rustsec-gate-focused-e37e5f8.log.gz` | 19,167 | `62c0e655db9bfbc864bae7d18c44677ca901dd921d1fcd7c884d063008f8594b` | 349,847 | `eb277b1b34d6544709ae99f1f29d72da46b7acf91830a56cb5f8298c88dbe56c` | 46 | 48 |
| B04 | `B04/failed-preflight-current-rustsec-fetch-e37e5f8.log.gz` | 35,746 | `974aae06292472bc0c0fce5f3db9e81f5a5ec995d8965072f785e23815779800` | 168,618 | `e37449e63545b52c9e407269065926372712f24e9b84ba374768ca2804470b6a` | 15 | 60 |
| B04 | `B04/failed-preflight-repository-log-e37e5f8.log.gz` | 23,514 | `e466665f6e4c860637be00f204a61afc2603e289f45102a0c1c03a0d84460ffe` | 106,527 | `041c40bbbcbdfd283d351cda8526ace84e42ad175648b68998511210a8fcfb61` | 4 | 14 |
| B04 | `B04/focused-prototypes-3754635.log` | 12,931 | `301fbf984c1825d13e5675459f9989e7238c8b3d9a24cc5cba96c7faa6bfe3a1` | 12,931 | `301fbf984c1825d13e5675459f9989e7238c8b3d9a24cc5cba96c7faa6bfe3a1` | 7 | 7 |
| B04 | `B04/full-preflight-3754635.log.gz` | 56,238 | `57036718d4e1599250cdbe1aff5b6163557d067b36100269e90a01a9ac243c68` | 519,967 | `21283dd1f59c405db83482c2cf4795fc618c951f96a5c2e9dc8724f8596ff4bd` | 61 | 110 |

The exact B00 cut is:

- source commit `6381d2a7cc82f442a538df7616758dd1348714e6`
- evidence commit `cb8a22311ca7c06ef0d3bcbd77b99ceb830053f1`

The exact B04 cut is:

- source commit `3754635404f362bb700c324f4dba613a3b73b3eb`
- evidence commit `9aaf667e2aecdc3c5b898e6430e9b33a5d7e76a1`

The exception preserves historical evidence bytes only. It does not make the
files portable. It grants no external, independent, security, safety,
interoperability, publication, or release authority.

## B01 working-artifact disposition

The B01 working directory is outside this receipt directory. Its files are
historical, non-passing inputs. A content-scan pass does not promote a working
file or satisfy a B01 evidence floor.

| Working artifact | Stored bytes | Stored SHA-256 | Content-scan result |
|---|---:|---|---|
| `../working/B01/full-check-a9e0f48.log.gz` | 56,772 | `11042f9980566d0dbc5687957c2045f6dc902e7a2d212d9769dbc9d834e4b67a` | **REJECT:** 110 detected host-path lines, including 61 private-home lines |
| `../working/B01/preliminary-architecture-541e1e7.log.gz` | 4,894 | `3aaaf4384afe267290de3961704b74ccf0e5dbd62c83f719f31c5a856941ffbe` | PASS for the content scan only |
| `../working/B01/preliminary-architecture-541e1e7.v1.json` | 15,244 | `e42f4b89d679102f8101c248d9882cf591f307937eb2380a5eeac375b40ecde4` | PASS for the content scan only |
| `../working/B01/preliminary-architecture-8194195.log.gz` | 5,326 | `eb885f3c430e41f3386a860fc9cd74e23b4a1244ed94d03db281d7565d371603` | PASS for the content scan only |
| `../working/B01/preliminary-architecture-8194195.v1.json` | 17,538 | `3f140dad12147500048644899f69893c1dd985d0001c900ec66b18143be51fe7` | PASS for the content scan only |

The rejected full-check log has no recognized secret pattern. It must not enter
a passing receipt. Do not copy or sanitize this immutable working artifact.
Create a new path-sanitized result from a new exact source run.
