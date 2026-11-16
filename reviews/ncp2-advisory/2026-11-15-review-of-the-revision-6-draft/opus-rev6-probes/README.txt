Probes of the third review of NCP 2 revision 6 (advisory; certifies nothing).
Run against a scratch copy of the frozen snapshot (SNAP = a copy holding python/, rust/, model/):
  python3 -I -B probe_a.py SNAP        (a) declined bodies with large or invalid ncp. members, Python
  python3 -I -B probe_a2.py SNAP       (a) open response with handler feature parameters above 65,536 bytes
  python3 -I -B probe_py.py SNAP       (b) to (g), and the Python side of N1
  python3 -I -B probe_41.py SNAP       N3: rule 4.1, the term of a re-take
  python3 -I -B probe_n7.py SNAP       N7: a wrapper that declines after Lockstep.validate blocks every take
  python3 -I -B model_probe.py SNAP trace|noL1|noS6|extra|fresh_restart   model investigations
  cp opus_probes.rs SNAP/rust/examples/ && (cd SNAP/rust && CARGO_TARGET_DIR=... cargo run --offline --locked --example opus_probes)
Logs: model-selftest.log, model-f1.log (gate setting), model-f2-*.log (two faults, --max-worlds 12000000), rust-sessions.log.
