# CLAUDE.md — NCP

**`AGENTS.md` is the source of truth for how to work in this repo.** Read it first;
this file only restates the few things most likely to cause silent, expensive damage,
plus Claude-Code-specific notes.

## The three rules you cannot get wrong

1. **Never silently break the wire.** NCP is a published, tag-pinned, cross-language
   wire contract. Classify every change as wire-invisible / additive / breaking
   (`AGENTS.md` §"The wire rule") and do the full 4-part update for a breaking one —
   `NCP_VERSION` in *both* `ncp-core/src/messages.rs` and `ncp-ts/src/client.ts`,
   proto + schemas + spec, `conformance.rs`, and regenerated `ncp-ts/dist`. When
   unsure whether something is wire-visible, assume it is.
2. **Safety fails CLOSED.** Every branch in `safety.rs`/`resilience.rs` must HOLD/reject
   on garbage/hostile/non-finite input, never actuate. Default `mode` is HOLD. A safety
   fix needs a regression test *and* a cross-language behavior-conformance vector.
3. **Tags are immutable.** Never move/delete a pushed `vX.Y.Z` tag; cut a new one. Follow
   the release runbook in `AGENTS.md` — everything green *before* the tag exists.

## Before you open a PR (CI enforces these)

```bash
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test -p ncp-core        # wire conformance MUST pass
scripts/check.sh              # full cross-language matrix
```

`cargo test -p ncp-python` fails locally with a `libpython*.dylib` rpath error — that
is an environment quirk (build via `maturin develop -m ncp-python/Cargo.toml`), **not**
a code failure. Everything else runs green with `cargo test --workspace --exclude ncp-python`.

## Claude-specific

- **No AI co-authors.** Do not add a `Co-Authored-By:` trailer, a "Generated with
  Claude Code" line, or a 🤖 marker to any commit or PR. (Global rule; restated here.)
- **Downstream lockstep.** `prisoma` and `crebain` pin NCP by tag. Before any
  wire-affecting change, check `../prisoma/crates/ncp-observer` and
  `../crebain/src-tauri/src/ncp/mod.rs` + `../crebain/src/neuro/` — crebain uses a broad
  Rust **and** TS surface, so a break hits it twice. `scripts/repin-ncp.sh <tag>` re-pins
  all consumers; `scripts/check-consumer-pins.sh` verifies agreement.
- **Keep `KNOWN_LIMITATIONS.md` honest.** It is the admitted-gaps ledger; if you fix a
  listed gap, move it out — do not leave stale "still broken" claims, and never
  understate a real limitation to look finished.
