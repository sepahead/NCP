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
- Every `extern "C"` body is wrapped in `std::panic::catch_unwind`; under
  `panic=unwind`, an internal panic returns the documented `NULL`/`-1` sentinel
  instead of crossing the C ABI. A `panic=abort` build still terminates, as Rust
  cannot catch an abort.

## Coverage

The C ABI exposes JSON-string wrappers for the core decision functions — version
guard, contract hash, key-expression builders (the four primary plane keys),
rate codec (`encode`/`decode`), the safety governor, and message validation. The
governor comes in two forms: the one-shot `ncp_govern` JSON wrapper, and a persistent,
**latching** handle — `ncp_governor_new` / `ncp_governor_govern` / `ncp_governor_reset` /
`ncp_governor_is_estopped` / `ncp_governor_note_link` / `ncp_governor_safety_ok` /
`ncp_governor_free`. The one-shot form is stateless and **cannot** hold an ESTOP latch
across calls (it stays for stateless/corpus use).

A live actuator needs **both** persistent safety layers:

- `NcpGovernor` enforces sensor freshness, geofence, speed limits, and the safety
  ESTOP latch.
- `NcpActionBuffer` (`ncp_action_buffer_*`) enforces command `ttl_ms`, monotonic
  seq/replay rejection, bounded predictive-horizon replay, and its own ESTOP latch.

Using the Governor alone does not enforce command-arrival deadlines. Together these
opaque handles expose the canonical Rust decisions instead of requiring C/C++ plants
to reimplement action-plane safety.

The following `ncp-core` modules are **not** exposed through the C ABI (use
`ncp-core` directly from Rust for full API access): the full key-scheme
(`sensor_named`, `command_named`, `*_glob`, `fleet_glob`), the `SafetyGovernor` /
`CommandWatchdog` typed structs themselves (the governor's behavior is reached through
the one-shot `ncp_govern` and the persistent `ncp_governor_*` handle above), the bulk
column codec (`ncp-core::bulk`), the in-process bus
(`LocalBus`), the control-loop runner (`NeuroControlLoop`), and the resilience
monitor (`LinkMonitor`; `ActionBuffer` is exposed through `NcpActionBuffer`). These are transport-internal or
Rust-ergonomic APIs not naturally expressed over a C ABI; the JSON wire surface
is the interop boundary.

## License

Licensed under either of [MIT](../LICENSE-MIT) or [Apache-2.0](../LICENSE-APACHE) at your option.
