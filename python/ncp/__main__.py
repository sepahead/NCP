"""The `ncp` command: `python -m ncp COMMAND`.

  verify FILE        verify a transcript (section 10.3); exit status 1 on any problem
  inspect FILE       print the records of a transcript, or one frame, in readable form
  id CONTRACT        check a contract document and print its identity (section 11)
  call ...           send one request to an owner and print the result
  conformance ...    run the conformance vectors against this SDK or another implementation
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from typing import Any

from . import conformance as K
from . import frame as F
from . import transcript as T
from .binding import connect_tcp, connect_unix, spawn
from .client import Client
from .contract import Contract, ContractError
from .frame import FrameError
from .messages import CallError


def _key(path: str | None) -> bytes | None:
    if path is None:
        return None
    with open(path, "rb") as handle:
        return F.check_key(handle.read())


def _readable(value: Any) -> Any:
    if isinstance(value, F.Array):
        values = value.tolist()
        shown = values[:8] + (["..."] if len(values) > 8 else [])
        return {"ncp.array": {"dtype": value.dtype, "shape": list(value.shape), "values": shown}}
    if isinstance(value, dict):
        return {k: _readable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_readable(v) for v in value]
    return value


def _show(message: dict[str, Any], limit: int) -> str:
    text = json.dumps(_readable({k: v for k, v in message.items() if k != "att"}), ensure_ascii=False)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def verify(arguments: argparse.Namespace) -> int:
    report = T.verify(arguments.file, key=_key(arguments.key_file))
    if arguments.json:
        print(json.dumps(K.transcript_summary(report) | {"problems": report.problems}, indent=1))
        return 0 if report.ok else 1
    print(f"transcript version {report.version}, {report.records} records, "
          f"{'closed' if report.closed else 'not closed'}, chain "
          f"{ {True: 'verified', False: 'BROKEN', None: 'not checked'}[report.chain_ok] }")
    for problem in report.problems:
        print(f"  problem: {problem}")
    for session in report.sessions.values():
        state = "complete" if session.complete else f"ended {session.ended}" if session.ended else "incomplete"
        print(f"session {session.session} ({session.role}): {session.requests} admitted, {session.declined} declined, "
              f"{session.rejected} rejected, {session.repeats} repeats, {state}")
        for problem in session.problems:
            print(f"  problem: {problem}")
    for stream in report.streams.values():
        print(f"stream {stream.stream}: {stream.accepted} accepted, {stream.lost} lost{', ended' if stream.ended else ''}")
        for problem in stream.problems:
            print(f"  problem: {problem}")
    print("verified" if report.ok else "NOT VERIFIED")
    return 0 if report.ok else 1


def inspect(arguments: argparse.Namespace) -> int:
    key = _key(arguments.key_file)
    with open(arguments.file, "rb") as handle:
        start = handle.read(8)
    if start in (T.MAGIC, T.MAGIC_V1):
        out, records = T.iterate(arguments.file, key=key)
        if out.header:
            print(f"header: {json.dumps(out.header)}")
        for index, record in enumerate(records):
            kind = {T.SENT: "sent", T.RECEIVED: "received"}[record.kind]
            try:
                decoded = F.decode(record.frame, F.MAX_BOUND, key=key, check_digest=key is not None or out.header is None
                                   or out.header.get("chain") == "sha256")
                text = _show(decoded.message, arguments.limit)
            except FrameError as error:
                text = f"BAD FRAME ({error})"
            print(f"{index:6d} {record.time_ns / 1e6:12.3f} ms {kind:8s} {len(record.frame):8d} B  {text}")
        if out.truncated_at is not None:
            print(f"truncated at offset {out.truncated_at}")
        print("end record" if out.closed else "no end record")
        return 0
    with open(arguments.file, "rb") as handle:
        frame = handle.read()
    try:
        decoded = F.decode(frame, F.MAX_BOUND, key=key)
        print(f"identity {decoded.identity}")
    except FrameError as error:
        print(f"bad frame: {error}")
        try:
            decoded = F.decode(frame, F.MAX_BOUND, check_digest=False)
        except FrameError:
            return 1
        print("content, without the digest comparison:")
    print(_show(decoded.message, arguments.limit))
    return 0


def contract_id(arguments: argparse.Namespace) -> int:
    try:
        contract = Contract.load(arguments.contract)
    except ContractError as error:
        print(f"not a valid contract: {error}")
        return 1
    print(contract.identity)
    print(f"application {contract.application}, version {contract.version}")
    print(f"operations: {', '.join(sorted(contract.operations)) or '(none)'}")
    print(f"streams: {', '.join(sorted(contract.streams)) or '(none)'}")
    return 0


def call(arguments: argparse.Namespace) -> int:
    contract = Contract.load(arguments.contract)
    key = _key(arguments.key_file)
    if arguments.unix:
        channel: Any = connect_unix(arguments.unix)
    elif arguments.tcp:
        host, _, port = arguments.tcp.rpartition(":")
        channel = connect_tcp(host, int(port), allow_remote=arguments.allow_remote)
    else:
        channel = spawn(shlex.split(arguments.spawn))
    body = json.loads(arguments.body) if arguments.body else {}
    client = Client(channel, contract, key=key, timeout=arguments.timeout)
    try:
        client.open()
        result = client.call(arguments.op, body)
        print(json.dumps(_readable(result.body), ensure_ascii=False, indent=1))
        client.close()
    except CallError as error:
        print(f"{type(error).__name__}: {error}")
        return 1
    return 0


def conformance(arguments: argparse.Namespace) -> int:
    vectors = K.load(arguments.vectors)
    results: dict[str, list[str]] = {}
    if arguments.decoder:
        results["frames (decoder program)"] = K.run_frames_with_program(vectors, shlex.split(arguments.decoder))
    if arguments.owner:
        failures, skipped = K.run_scenarios(vectors, K.program_owner(shlex.split(arguments.owner)))
        results[f"scenarios (owner program, {skipped} skipped: they need an interface to stop the owner)"] = failures
    if not arguments.decoder and not arguments.owner:
        results = K.run_all(vectors)
    failed = 0
    for part, failures in results.items():
        print(f"{part}: {'pass' if not failures else f'{len(failures)} failures'}")
        for failure in failures[:20]:
            print(f"  {failure}")
        failed += len(failures)
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ncp", description="Tools for NCP 2 (spec/NCP-2.md).")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("verify", help="verify a transcript")
    p.add_argument("file")
    p.add_argument("--key-file", help="the key of an authenticated transcript (section 13.2)")
    p.add_argument("--json", action="store_true", help="print the result as JSON")
    p.set_defaults(run=verify)
    p = commands.add_parser("inspect", help="print a transcript or a frame")
    p.add_argument("file")
    p.add_argument("--key-file")
    p.add_argument("--limit", type=int, default=160, help="characters of each message to print")
    p.set_defaults(run=inspect)
    p = commands.add_parser("id", help="check a contract and print its identity")
    p.add_argument("contract")
    p.set_defaults(run=contract_id)
    p = commands.add_parser("call", help="send one request to an owner")
    where = p.add_mutually_exclusive_group(required=True)
    where.add_argument("--unix", help="the path of the owner's Unix domain socket")
    where.add_argument("--tcp", help="HOST:PORT of the owner")
    where.add_argument("--spawn", help="the command of an owner that serves standard input and output")
    p.add_argument("--allow-remote", action="store_true")
    p.add_argument("--contract", required=True)
    p.add_argument("--key-file")
    p.add_argument("--timeout", type=float, default=30.0)
    p.add_argument("op")
    p.add_argument("body", nargs="?", help="the request body as JSON")
    p.set_defaults(run=call)
    p = commands.add_parser("conformance", help="run the conformance vectors")
    p.add_argument("--vectors", help="the vectors file (default: the copy in this package)")
    p.add_argument("--decoder", help="a decoder program, as one command line")
    p.add_argument("--owner", help="an owner program that serves standard input and output, as one command line")
    p.set_defaults(run=conformance)
    arguments = parser.parse_args(argv)
    return int(arguments.run(arguments))


if __name__ == "__main__":
    sys.exit(main())
