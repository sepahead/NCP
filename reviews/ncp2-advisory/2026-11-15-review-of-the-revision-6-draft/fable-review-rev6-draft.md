# NCP 2 revision 6 — independent review (DRAFT, in progress)

Status: advisory, non-normative, certifies nothing. Read-only review.
Base: `c42e346`; revision 6 is the uncommitted diff in `.ncp2-hardening`.

## Plan
1. Read the diff (`git diff c42e346`) and the untracked `model/lockstep.py`.
2. Read `spec/NCP-2.md` (7.1.8, 7.3.12, 11.1, 14, 15, 17) and `spec/NCP-2-LOCKSTEP.md` rev 4.
3. Read `python/ncp/{owner,lockstep,messages}.py`, `rust/src/{owner,lockstep,messages,lib}.rs`.
4. Copy python/model/spec/conformance/rust/bindings to a scratch dir; run probes there.
5. Q1 edge cases: take in a session that holds ticks; lost take response (Zenoh resend);
   owner restart with/without restored clock+term; largest term; feature operation names;
   declined bodies; Zenoh servers with feature operations; transcripts holding takes.
6. Q2 parity: behaviour, detail texts, error kinds, API.
7. Q3 model: run `model/lockstep.py` with 1 fault + self-test; look for vacuous properties.
8. Q4 claims in docs vs code and runs.
9. Q5 remaining gaps.

Marks: [C] confirmed (read or ran), [S] suspected.

## Findings so far
(none yet)

## Checkpoint 1 (16:50) — snapshot and first runs
- Snapshot: `git diff c42e346` sha256 `d1ba4ef8…f6f92` at 16:41 CET; the worktree is live (new since my first look: `rust/examples/lockstep_owner.rs`, `rust/Cargo.toml`, `bindings/zenoh/python/tests/test_zenoh.py`, `docs/release/NCP-2.0.0.md`).
- Scratch copy; `python3 -I -B model/lockstep.py --faults 1`: 426,777 worlds (171,174 / 119,967 / 119,587 / 16,049), all hold [C]. Self-test: 9 of 9 [C]. Logs: `ls_f1.log`, `ls_selftest.log`.
- Read so far: spec diff, profile rev 4, python lockstep/owner/messages, rust lockstep/owner diff, model/lockstep.py.

### Candidate findings (to verify by probe)
- declined body with large / non-JSON `ncp.` members: encode failure escapes `step` as FrameError (both SDKs?) -> binding blames the client.
- Rust `open` locks the shared mutex, so it waits for an executing step; Python `open` does not (doc claim "does not wait").
- profile 6.2 vs largest term: declined take with `ncp.lockstep` and the same term; text says "another take ran".
- rule 3.4 "the client then ends the session": SDKs raise and leave the session open.
- recover(): after "no verdict" the LockstepClient is unusable (Python keeps the dead client; Rust drops the new client which holds the ticks).
- Lockstep() default state None, not handler.state(): restart at tick 0 with another world gives "did not run".
- Rust `restored(tick=u64::MAX)`: tick + 1 overflow; Python tick unbounded above 2^53-1.
- model: S4 excused when other/rewound; S6 excused when other; check vacuity; mutants caught for the right reason?
