# Local NCP Python SDK

This independent SDK implements the candidate `ncp.local-lockstep.v1` profile.
It uses Python's standard library. It does not call Rust or an FFI extension.

The run owner installs one immutable binding before launch.
The binding fixes the run, endpoint generation, role, and exact profile digest.
An inherited private channel connects each endpoint to that run owner.

Install this package with `python -m pip install ./local/python` from the NCP repository.
Run its native controls with `python -m unittest discover -s local/python/tests -v`.
Set `PYTHONPATH=local/python` when testing the source tree without installation.

```python
from ncp_local import LocalBinding, LocalClient, LocalOwner, serve_local

# The run owner creates this binding once and supplies it to both sides.
binding = LocalBinding.fresh("neural")

# Use the already launched endpoint's unbuffered private subprocess pipes.
client = LocalClient(binding, process.stdout, process.stdin, timeout_s=10)
response = client.call("prepare", prepared_data)
if response["outcome"] != "committed":
    raise RuntimeError(response["code"])

# The child installs its fixed backend before serving any request.
owner = LocalOwner(binding, installed_backend)
serve_local(owner, input_pipe, output_pipe)
```

`call` returns the complete verified response and acknowledges its exact digest.
Use `request`, `result`, and `acknowledge` when capture must precede acknowledgement.
Only one unacknowledged result can exist per endpoint.

Validation failure occurs before backend execution. It does not consume a sequence.
An execution exception or unrepresentable result consumes the sequence and retires the generation.
Its outcome is `indeterminate`; the SDK does not claim rollback.

A timeout, broken channel, or invalid response retires the client.
The run owner must retire all coupled endpoints and terminate their processes.
The client never retries a mutation after channel loss.
Fresh endpoint generations are required for a new launch.

The parser rejects duplicate decoded keys and invalid Unicode before object decoding.
It checks depth, structural budgets, safe integer spellings, and finite number magnitude.
Floating negative zero retains its binary64 sign in digests.
Sequence fields reject negative zero and non-integer spellings.

The modular codec scans complete unescaped ASCII strings in bounded runs.
It uses the unchanged reference scanner for other strings, including escapes and Unicode.
Both paths check decoded key identity and byte limits before generic object decoding.
The modular JSON tests compare their admission, error positions, counters, and decoded values.

The frame ceiling is 65,536 bytes. Each frame starts with its four-byte big-endian length.
Responses reserve retained-wire capacity before execution; digest staging has separate bounded allocations.
This Python implementation does not promise allocation-free execution or real-time scheduling.

The selected profile excludes remote listeners, physical actuation, crash resume, and arbitrary executable models.
Protocol success does not establish scientific validity or calibrated posterior inference.
