# Local convergence and external handoff

`local-convergence.v1.json` is the deterministic boundary between work that this
repository can reproduce and qualification that requires deployment, installed
independent implementations, package registries, consumer repositories, or an
independent reproducer.

Generate or verify it with:

```bash
python3 scripts/generate_convergence_manifest.py --self-test --check
```

The manifest intentionally remains `NO_GO`. It preserves the fail-closed Zenoh
authenticated-principal prerequisite, all ten non-local pre-release gates as
`NOT_RUN`, and both post-publication validations. It is a handoff inventory, not
evidence that any listed campaign ran.
