# ncp-cpp

[![License: MIT OR Apache-2.0](https://img.shields.io/badge/license-MIT%20OR%20Apache--2.0-blue.svg)](#license)

The **C ABI** for the NCP Rust core: a stable `extern "C"` surface so **C and C++**
projects use the canonical Rust implementation of the Neuro-Cybernetic Protocol
(version guard, key scheme, rate codec, action-plane safety governor, message
validation) rather than reimplementing the wire — the same guarantee `ncp-python`
gives Python and `ncp-ts` gives TypeScript.

This is the **C/C++ peer** in NCP's polyglot SDK. All peers conform to one normative
protocol spec, [`NEURO_CYBERNETIC_PROTOCOL.md`](../NEURO_CYBERNETIC_PROTOCOL.md), so
the JSON arguments and returns here match the NCP wire exactly.

## Use

The C header is [`include/ncp.h`](include/ncp.h); a worked example is
[`examples/demo.cpp`](examples/demo.cpp). Link against `ncp_cpp` (staticlib or
cdylib):

```text
cargo build -p ncp-cpp        # produces libncp_cpp.a / libncp_cpp.{so,dylib}
```

```c
#include "ncp.h"

char *v = ncp_version();          /* heap-allocated UTF-8 C string */
/* ... use v ... */
ncp_string_free(v);               /* caller MUST free every char* return */
```

Notes (see the header and `src/lib.rs` for the full contract):

- Every `char*` return is a heap-allocated UTF-8 C string the caller MUST release
  with `ncp_string_free`. A `NULL` return signals malformed input or an internal
  error; string arguments are NUL-terminated UTF-8.
- Every `extern "C"` body is wrapped in `std::panic::catch_unwind` and returns its
  `NULL`/`-1` sentinel on panic — no unwind ever crosses the C ABI.

## Coverage

The C ABI exposes JSON-string wrappers for the core decision functions — version
guard, contract hash, key-expression builders (the four primary plane keys),
rate codec (`encode`/`decode`), safety governor (`govern`), and message
validation. This covers the wire-level operations a C/C++ peer needs to be
wire-identical to the Rust/Python/TS peers.

The following `ncp-core` modules are **not** exposed through the C ABI (use
`ncp-core` directly from Rust for full API access): the full key-scheme
(`sensor_named`, `command_named`, `*_glob`, `fleet_glob`), `SafetyGovernor` /
`CommandWatchdog` as typed structs (only the one-shot `ncp_govern` JSON wrapper
is exposed), the bulk column codec (`ncp-core::bulk`), the in-process bus
(`LocalBus`), the control-loop runner (`NeuroControlLoop`), and the resilience
layer (`ActionBuffer`, `LinkMonitor`). These are transport-internal or
Rust-ergonomic APIs not naturally expressed over a C ABI; the JSON wire surface
is the interop boundary.

## License

Licensed under either of [MIT](../LICENSE-MIT) or [Apache-2.0](../LICENSE-APACHE) at your option.
