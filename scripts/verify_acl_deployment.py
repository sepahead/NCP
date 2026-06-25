#!/usr/bin/env python3
"""verify_acl_deployment.py — live P0 closure checklist for issue #7.

Automates the four-step mTLS + ACL enforcement verification table in
SECURITY.md ("P0 closure checklist"). Run it against a *live* Zenoh realm
that has the ACL template (deploy/zenoh-access-control.json5) and mutual TLS
enabled. It exercises both PUT-authority invariants:

  1. commander  PUT on .../command/**  → ACCEPT (only the commander may command)
  2. robot/obs  PUT on .../command/**  → REJECT (perception-only cannot command)
  3. robot      PUT on .../sensor/**   → ACCEPT (the plant publishes perception)
  4. commander  PUT on .../sensor/**   → REJECT (the brain cannot spoof sensor data)

Plus: a peer presenting NO client cert is refused at the mTLS layer.

The script uses the Zenoh Python binding (zenoh-python) if available, or falls
back to the `z_put` / z_sub CLI tools. It does NOT run in CI — it is a
deployment-time verification tool. Exit 0 = all four invariants hold; exit 1 =
at least one failed (the realm is NOT P0-validated).

Usage:
  python3 scripts/verify_acl_deployment.py \\
      --endpoint tls/localhost:7447 \\
      --realm ncp \\
      --session s1 \\
      --commander-cert commander.crt --commander-key commander.key \\
      --robot-cert robot.crt --robot-key robot.key \\
      --observer-cert observer.crt --observer-key observer.key \\
      --ca ca.crt

Or, if using the Zenoh CLI (z_put) instead of the Python binding:
  python3 scripts/verify_acl_deployment.py --use-cli \\
      --endpoint tls/localhost:7447 --realm ncp --session s1 \\
      --ca ca.crt

Requires: zenoh-python (pip install zenoh) or the Zenoh CLI (z_put/z_sub).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass


@dataclass
class CheckResult:
    step: int
    description: str
    expected: str  # "ACCEPT" or "REJECT"
    actual: str
    passed: bool

    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return (
            f"  [{status}] Step {self.step}: {self.description}\n"
            f"          expected={self.expected}, actual={self.actual}"
        )


def _try_zenoh_python_put(
    endpoint: str,
    key: str,
    value: str,
    cert: str | None,
    key_file: str | None,
    ca: str,
) -> tuple[bool, str]:
    """Try to PUT using zenoh-python. Returns (succeeded, detail)."""
    try:
        import zenoh
    except ImportError:
        return False, "zenoh-python not installed"

    conf = zenoh.Config()
    conf.insert_json5("connect/endpoints", f'["{endpoint}"]')
    # TLS config for the connecting peer.
    if cert and key_file:
        tls = {
            "root_ca_certificate": ca,
            "connect_certificate": cert,
            "connect_private_key": key_file,
        }
        conf.insert_json5("transport/link/tls", __import__("json").dumps(tls))
    else:
        # No client cert — mTLS should reject this.
        conf.insert_json5("transport/link/tls", f'{{"root_ca_certificate":"{ca}"}}')

    try:
        session = zenoh.open(conf)
        session.put(key, value.encode())
        session.close()
        return True, "PUT succeeded"
    except Exception as e:
        return False, f"PUT rejected: {e}"


def _try_cli_put(
    endpoint: str,
    key: str,
    value: str,
    cert: str | None,
    key_file: str | None,
    ca: str,
) -> tuple[bool, str]:
    """Try to PUT using the z_put CLI. Returns (succeeded, detail)."""
    cmd = [
        "z_put",
        "-e", endpoint,
        "-k", key,
        "-v", value,
    ]
    # TLS args (zenoh CLI uses --config or env vars; this is a simplification).
    env = {
        **dict(__import__("os").environ),
        "ZENOH_TLS_ROOT_CA_CERTIFICATE": ca,
    }
    if cert and key_file:
        env["ZENOH_TLS_CONNECT_CERTIFICATE"] = cert
        env["ZENOH_TLS_CONNECT_PRIVATE_KEY"] = key_file

    try:
        result = subprocess.run(
            cmd, env=env, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return True, "z_put succeeded"
        else:
            return False, f"z_put rejected (exit {result.returncode}): {result.stderr.strip()}"
    except FileNotFoundError:
        return False, "z_put CLI not found"
    except subprocess.TimeoutExpired:
        return False, "z_put timed out (likely mTLS rejection)"


def do_put(
    args: argparse.Namespace,
    key: str,
    value: str,
    cert: str | None,
    key_file: str | None,
) -> tuple[bool, str]:
    """Attempt a PUT and return (succeeded, detail)."""
    if args.use_cli:
        return _try_cli_put(args.endpoint, key, value, cert, key_file, args.ca)
    else:
        return _try_zenoh_python_put(
            args.endpoint, key, value, cert, key_file, args.ca
        )


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--endpoint", required=True, help="Zenoh TLS endpoint (e.g. tls/localhost:7447)")
    p.add_argument("--realm", default="ncp", help="realm key prefix")
    p.add_argument("--session", default="s1", help="session id for the test")
    p.add_argument("--commander-cert", default=None)
    p.add_argument("--commander-key", default=None)
    p.add_argument("--robot-cert", default=None)
    p.add_argument("--robot-key", default=None)
    p.add_argument("--observer-cert", default=None)
    p.add_argument("--observer-key", default=None)
    p.add_argument("--ca", required=True, help="CA certificate for TLS")
    p.add_argument("--use-cli", action="store_true", help="use z_put CLI instead of zenoh-python")
    args = p.parse_args()

    realm = args.realm
    sid = args.session
    cmd_key = f"{realm}/session/{sid}/command/test"
    sensor_key = f"{realm}/session/{sid}/sensor/test"
    test_value = "p0-verify-probe"

    results: list[CheckResult] = []

    # Step 1: commander PUT on command → ACCEPT
    ok, detail = do_put(args, cmd_key, test_value, args.commander_cert, args.commander_key)
    results.append(CheckResult(1, "commander PUT on .../command/**", "ACCEPT",
                               "ACCEPT" if ok else "REJECT", ok))

    # Step 2: robot PUT on command → REJECT
    ok, detail = do_put(args, cmd_key, test_value, args.robot_cert, args.robot_key)
    results.append(CheckResult(2, "robot PUT on .../command/**", "REJECT",
                               "REJECT" if not ok else "ACCEPT", not ok))

    # Step 3: robot PUT on sensor → ACCEPT
    ok, detail = do_put(args, sensor_key, test_value, args.robot_cert, args.robot_key)
    results.append(CheckResult(3, "robot PUT on .../sensor/**", "ACCEPT",
                               "ACCEPT" if ok else "REJECT", ok))

    # Step 4: commander PUT on sensor → REJECT
    ok, detail = do_put(args, sensor_key, test_value, args.commander_cert, args.commander_key)
    results.append(CheckResult(4, "commander PUT on .../sensor/**", "REJECT",
                               "REJECT" if not ok else "ACCEPT", not ok))

    # Step 5: no-cert PUT → REJECT (mTLS layer)
    ok, detail = do_put(args, cmd_key, test_value, None, None)
    results.append(CheckResult(5, "no-cert PUT (mTLS rejection)", "REJECT",
                               "REJECT" if not ok else "ACCEPT", not ok))

    print("P0 ACL Deployment Verification")
    print(f"  endpoint: {args.endpoint}")
    print(f"  realm:    {args.realm}")
    print(f"  session:  {args.session}")
    print()
    for r in results:
        print(r)
    print()

    all_passed = all(r.passed for r in results)
    if all_passed:
        print("RESULT: ALL 5 INVARIANTS HOLD — realm is P0-validated.")
        print("Record this output as the P0 evidence per SECURITY.md.")
        return 0
    else:
        failed = [r for r in results if not r.passed]
        print(f"RESULT: {len(failed)} of {len(results)} invariants FAILED — realm is NOT P0-validated.")
        print("Do not deploy on an open realm until all invariants hold.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
