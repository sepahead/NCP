# Claude Code guide for NCP

@AGENTS.md

[`AGENTS.md`](AGENTS.md), imported above, is the durable repository policy. It takes
precedence over this guide.

## Start here

1. Read `README.md` and the required owner documents for the change.
2. Read `DOCUMENTATION_STYLE.md` before you change maintained prose.
3. Inspect the owning source, generator, tests, and current evidence.
4. Preserve unrelated work in each dirty repository.

## Reminders

- The owner authorizes unsigned commits, pushes, and merges to `main` after the
  applicable complete gate.
- Do not add AI attribution or co-author trailers to commits or pull requests.
- Start only a dependency-ready ledger task.
- Treat a change as wire-visible unless you can prove that it is not.
- Regenerate the tracked-file audit inventory after each tracked change.
- Keep every unexecuted external gate at **NOT RUN**.
- Model review is optional, read-only advice. It is not certification evidence.
  Give an external model only the context that its focused question requires.

Run [`scripts/check.sh`](scripts/check.sh) when the task requires the complete local
gate. Report the exact local result and each gate that remains **NOT RUN**.
