# `ncp-cpp`

`ncp-cpp` exposes the Rust reference implementation through a panic-contained C ABI
for C and C++. It currently identifies the unreleased, release-blocked NCP
`1.0.0-rc.1` candidate (wire `1.0`, compact proto hash
`163acc57d8a62b66`). Because decisions execute in Rust, this binding does not count
as an independent C/C++ implementation.

Build and link the static or dynamic `ncp_cpp` library:

```bash
cargo build -p ncp-cpp
c++ -std=c++17 -I ncp-cpp/include ncp-cpp/examples/demo.cpp \
  -L target/debug -lncp_cpp -Wl,-rpath,"$PWD/target/debug" -o ncp-demo
```

```c
#include "ncp.h"

char *version = ncp_version();
/* version is "1.0" */
ncp_string_free(version);

char *package = ncp_package_version();
char *digest = ncp_normative_contract_digest();
char *build = ncp_build_identity();
/* package is "1.0.0-rc.1"; build is the non-certifying
 * "unreleased-worktree" RC sentinel; digest is 64 lowercase hex. */
ncp_string_free(package);
ncp_string_free(digest);
ncp_string_free(build);
```

Every returned `char *` is owned by the caller and must be released with
`ncp_string_free`; `NULL` or `-1` is an error/fail-safe result. Handles are not
thread-safe. A live body uses both a persistent `NcpGovernor` and
`NcpActionBuffer`; the one-shot governor cannot preserve an ESTOP latch between
calls.

`NcpActionBuffer` is declaration-bound: equal/lower sequence remains rejected after
TTL expiry, and a foreign epoch requires a fresh handle. The C ABI's
`ncp_action_buffer_reset` is a body-local primitive for an already-authorized
session-generation cut. It clears the latch and permanently retires that handle;
`ncp_action_buffer_is_retired` reports the state. It does not authenticate an
authorized operator or restore authority. Allocate a new buffer only for the new
`SessionOpened` generation.

Every JSON argument first passes the canonical universal bounded-JSON preflight
(1 MiB frame ceiling, nesting/node/string/number budgets, valid Unicode, and
duplicate-key rejection) before typed decoding. This includes request digests,
codec and rate maps, optional sensors and authority leases, governor configuration
and frames, the action buffer, and `ncp_validate`; a violation returns that
function's existing `NULL` or `-1` fail-safe sentinel. `ncp_validate` then applies
the reference semantic validator, including safe integers, session generations,
active authority, operations/receipts, and scientific flags. The ABI itself does
not bind a cryptographic transport principal, and a caller must still enforce the
deployment authority manifest, exact route/session-generation admission before the
local action buffer, and the plant-owned safety case.

The header is [`include/ncp.h`](include/ncp.h). These accessors are package
introspection, not provenance certification; the complete normative digest and
exact source list are in
[`../contract/manifest.v1.json`](../contract/manifest.v1.json). Candidate libraries
are not published, signed, ABI-certified across platforms, or independently
live-certified.

Licensed under either [MIT](../LICENSE-MIT) or
[Apache-2.0](../LICENSE-APACHE).
