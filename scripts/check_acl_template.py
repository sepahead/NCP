#!/usr/bin/env python3
"""Structural guard for deploy/zenoh-access-control.json5 (ROADMAP P0, #7).

The per-plane ACL is the one concrete mitigation for the world-writable action
plane, so a template that zenohd silently refuses (or that grants command-put to
the wrong subject) is worse than none — it reads as "secured" while doing nothing.
This guard runs in CI without a Zenoh runtime and fails closed on:

  1. an invalid `messages` token (e.g. the `get` that zenohd rejects — the real
     token for the querier/get side is `query`), and
  2. any mismatch in the exact subject/message/flow/plane matrix. Zenoh applies
     ingress policy to a source client link and egress policy to each destination
     client link, so safe publication and functional delivery are separate grants;
  3. a violation of PUT authority: only `commander` may send command ingress,
     while only `body` may send sensor or exact-observation ingress;
  4. a violation of lifecycle-RPC direction: only `commander` may send query
     ingress and only `body` may send queryable declarations/replies ingress; and
  5. loss of the observer's read-only subscription and delivery coverage.

On every run it also self-tests (a tampered template MUST be rejected) so the
guard cannot silently rot into a no-op.

It is intentionally a lightweight stdlib-only parse (no json5 dep): it strips `//`
comments, quotes bare keys, and drops trailing commas, which is sufficient for this
template. zenohd remains the authority on the live config; this only catches the
mechanical drift class the review found.

This guard proves router configuration only. It cannot expose an authenticated
remote principal to an NCP callback or bind that principal to ``IdentityClaim``.
"""
from __future__ import annotations

import json
import copy
import re
import sys
from pathlib import Path

from render_acl_template import render, valid_realm

# Valid Zenoh 1.x access-control `messages` tokens. `get` is deliberately ABSENT:
# the get/querier side is `query`. Keep this in sync with zenoh's AclMessage.
VALID_TOKENS = {
    "put",
    "delete",
    "declare_subscriber",
    "declare_queryable",
    "query",
    "reply",
    "liveliness_token",
    "declare_liveliness_subscriber",
    "liveliness_query",
}
PLANE_COMMAND = "command"
PLANE_SENSOR = "sensor"
PLANE_OBSERVATION = "observation"
PLANE_RPC = "rpc"


def _matrix(
    subject: str, flow: str, messages: set[str], planes: set[str]
) -> set[tuple[str, str, str, str]]:
    return {
        (subject, flow, message, plane)
        for message in messages
        for plane in planes
    }


# Exact effective allow matrix for this minimal profile. Ingress grants what an
# authenticated remote may send to the router; egress grants what the router may
# deliver to that remote. Egress PUT/DELETE is read delivery, never publish power.
EXPECTED_MATRIX = set().union(
    _matrix("commander", "ingress", {"put", "delete"}, {PLANE_COMMAND}),
    _matrix(
        "commander", "egress", {"declare_subscriber"}, {PLANE_COMMAND}
    ),
    _matrix(
        "commander",
        "ingress",
        {"declare_subscriber"},
        {PLANE_SENSOR, PLANE_OBSERVATION},
    ),
    _matrix(
        "commander",
        "egress",
        {"put", "delete"},
        {PLANE_SENSOR, PLANE_OBSERVATION},
    ),
    _matrix("commander", "ingress", {"query"}, {PLANE_RPC}),
    _matrix(
        "commander", "egress", {"declare_queryable", "reply"}, {PLANE_RPC}
    ),
    _matrix(
        "body",
        "ingress",
        {"put", "delete"},
        {PLANE_SENSOR, PLANE_OBSERVATION},
    ),
    _matrix(
        "body",
        "egress",
        {"declare_subscriber"},
        {PLANE_SENSOR, PLANE_OBSERVATION},
    ),
    _matrix("body", "ingress", {"declare_subscriber"}, {PLANE_COMMAND}),
    _matrix("body", "egress", {"put", "delete"}, {PLANE_COMMAND}),
    _matrix(
        "body", "ingress", {"declare_queryable", "reply"}, {PLANE_RPC}
    ),
    _matrix("body", "egress", {"query"}, {PLANE_RPC}),
    _matrix(
        "observer",
        "ingress",
        {"declare_subscriber"},
        {PLANE_SENSOR, PLANE_COMMAND, PLANE_OBSERVATION},
    ),
    _matrix(
        "observer",
        "egress",
        {"put", "delete"},
        {PLANE_SENSOR, PLANE_COMMAND, PLANE_OBSERVATION},
    ),
)

ACL_PATH = Path(__file__).resolve().parent.parent / "deploy" / "zenoh-access-control.json5"
ZENOH_MANIFEST = Path(__file__).resolve().parent.parent / "ncp-zenoh" / "Cargo.toml"


def load_json5(text: str) -> dict:
    # Strip // line comments (none of this template's strings contain `//`).
    text = re.sub(r"//[^\n]*", "", text)
    # Quote bare object keys: `{ id:` / `, messages:` -> `{ "id":`.
    text = re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:', r'\1"\2":', text)
    # Drop trailing commas before } or ].
    text = re.sub(r',(\s*[}\]])', r'\1', text)
    return json.loads(text)


def _nested(cfg: dict, *path: str):
    value = cfg
    for part in path:
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _endpoint_strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for value in value for item in _endpoint_strings(value)]
    if isinstance(value, dict):
        return [item for value in value.values() for item in _endpoint_strings(value)]
    return []


def _classify_key(key: object) -> tuple[str, str] | None:
    """Return ``(realm, plane)`` only for an audited exact template shape.

    Rejecting broader expressions is load-bearing: a rule on ``session/**`` would
    intersect every data plane but evade substring-only authority checks.
    """
    if not isinstance(key, str) or not key:
        return None
    if "/session/" in key:
        realm, suffix = key.split("/session/", 1)
        plane = {
            "*/command/**": PLANE_COMMAND,
            "*/sensor/**": PLANE_SENSOR,
            "*/observation": PLANE_OBSERVATION,
        }.get(suffix)
        return (realm, plane) if plane is not None else None
    if "/rpc/" in key:
        realm, suffix = key.split("/rpc/", 1)
        return (realm, PLANE_RPC) if suffix == "*" else None
    return None


def check(cfg: dict) -> list[str]:
    """Return router/mTLS/ACL problems (empty == OK). Pure and self-testable."""
    ac = cfg.get("access_control", {})
    rules = ac.get("rules", [])
    subjects_cfg = ac.get("subjects", [])
    policies = ac.get("policies", [])
    errors: list[str] = []

    # The advertised asset must be a complete fail-closed router, not an ACL
    # fragment that can accidentally be opened over plaintext/default discovery.
    if cfg.get("mode") != "router":
        errors.append('secure router must set mode="router"')
    listeners = _endpoint_strings(_nested(cfg, "listen", "endpoints"))
    if not listeners or any(not endpoint.startswith("tls/") for endpoint in listeners):
        errors.append("router listen endpoints must be non-empty and exclusively tls/")
    if _endpoint_strings(_nested(cfg, "connect", "endpoints")):
        errors.append("standalone secure router template must not connect to upstream endpoints")
    for path in (("scouting", "multicast", "enabled"), ("scouting", "gossip", "enabled")):
        if _nested(cfg, *path) is not False:
            errors.append(f"secure router requires {'/'.join(path)}=false")
    tls = _nested(cfg, "transport", "link", "tls") or {}
    if tls.get("enable_mtls") is not True:
        errors.append("secure router requires transport/link/tls/enable_mtls=true")
    if tls.get("close_link_on_expiration") is not True:
        errors.append("secure router requires transport/link/tls/close_link_on_expiration=true")
    if _nested(cfg, "listen", "exit_on_failure") is not True:
        errors.append("secure router requires listen/exit_on_failure=true")
    for field in ("root_ca_certificate", "listen_certificate", "listen_private_key"):
        if not isinstance(tls.get(field), str) or not tls[field].strip():
            errors.append(f"secure router requires a non-empty TLS {field}")

    if ac.get("enabled") is not True:
        errors.append("access_control.enabled must be true")
    if ac.get("default_permission") != "deny":
        errors.append('access_control.default_permission must be "deny"')

    rule_ids = [rule.get("id") for rule in rules]
    subject_ids = [subject.get("id") for subject in subjects_cfg]
    if None in rule_ids or len(set(rule_ids)) != len(rule_ids):
        errors.append("ACL rule ids must be present and unique")
    if None in subject_ids or len(set(subject_ids)) != len(subject_ids):
        errors.append("ACL subject ids must be present and unique")
    known_rules, known_subjects = set(rule_ids), set(subject_ids)
    expected_subjects = {"commander", "body", "observer"}
    if known_subjects != expected_subjects:
        errors.append(
            "minimal ACL subjects must equal exactly "
            f"{sorted(expected_subjects)}, got {sorted(known_subjects)}"
        )

    # Certificate subject selectors must be explicit, exact, and globally unique.
    # Mapping one certificate CN to two subjects collapses role separation.
    cn_subject: dict[str, str] = {}
    for subject in subjects_cfg:
        subject_id = subject.get("id")
        cns = subject.get("cert_common_names")
        if not isinstance(cns, list) or not cns:
            errors.append(f"subject {subject_id!r} needs explicit certificate CNs")
            continue
        for cn in cns:
            if not isinstance(cn, str) or not cn.strip() or any(c in cn for c in "*$#?"):
                errors.append(f"subject {subject_id!r} has unsafe/non-exact CN {cn!r}")
            elif cn in cn_subject:
                errors.append(
                    f"certificate CN {cn!r} is assigned to both {cn_subject[cn]!r} "
                    f"and {subject_id!r}"
                )
            else:
                cn_subject[cn] = subject_id

    rule_subjects: dict[str, set[str]] = {rid: set() for rid in known_rules}
    for policy in policies:
        p_rules = set(policy.get("rules", []))
        p_subjects = set(policy.get("subjects", []))
        for missing in p_rules - known_rules:
            errors.append(f"policy references unknown rule {missing!r}")
        for missing in p_subjects - known_subjects:
            errors.append(f"policy references unknown subject {missing!r}")
        for rid in p_rules & known_rules:
            rule_subjects[rid].update(p_subjects)

    effective_matrix: set[tuple[str, str, str, str]] = set()
    realms: set[str] = set()
    for rule in rules:
        rid = rule.get("id", "<unnamed>")
        message_list = rule.get("messages", [])
        flow_list = rule.get("flows", [])
        messages = set(message_list) if isinstance(message_list, list) else set()
        flows = set(flow_list) if isinstance(flow_list, list) else set()
        keys = rule.get("key_exprs", [])
        if rule.get("permission") != "allow":
            errors.append(f"rule {rid!r} must be an explicit allow rule")
        if not flows or not flows <= {"ingress", "egress"}:
            errors.append(f"rule {rid!r} must contain valid explicit flows")
        if isinstance(flow_list, list) and len(flow_list) != len(flows):
            errors.append(f"rule {rid!r} contains a duplicate flow")
        if not messages:
            errors.append(f"rule {rid!r} must contain at least one messages token")
        if isinstance(message_list, list) and len(message_list) != len(messages):
            errors.append(f"rule {rid!r} contains a duplicate messages token")
        if not isinstance(keys, list) or not keys:
            errors.append(f"rule {rid!r} must contain at least one key expression")
            keys = []
        elif len(keys) != len(set(keys)):
            errors.append(f"rule {rid!r} contains a duplicate key expression")
        for token in messages:
            if token not in VALID_TOKENS:
                errors.append(
                    f"rule {rid!r}: invalid messages token {token!r} "
                    f"(zenohd would reject the config; did you mean 'query'?)"
                )
        planes: set[str] = set()
        for key in keys:
            classified = _classify_key(key)
            if classified is None:
                errors.append(
                    f"rule {rid!r} has an unaudited or overly broad NCP key {key!r}"
                )
                continue
            realm, plane = classified
            realms.add(realm)
            planes.add(plane)
        subjects = rule_subjects.get(rid, set())
        if not subjects:
            errors.append(f"rule {rid!r} is not bound to an authenticated subject")
        effective_matrix.update(
            (subject, flow, message, plane)
            for subject in subjects
            for flow in flows
            for message in messages
            for plane in planes
        )

    if len(realms) != 1 or not realms or not valid_realm(next(iter(realms), "")):
        errors.append(f"all ACL keys must share one valid exact realm, got {sorted(realms)}")

    missing_matrix = EXPECTED_MATRIX - effective_matrix
    extra_matrix = effective_matrix - EXPECTED_MATRIX
    if missing_matrix:
        errors.append(
            "ACL effective matrix is missing: "
            + ", ".join("/".join(item) for item in sorted(missing_matrix))
        )
    if extra_matrix:
        errors.append(
            "ACL effective matrix grants unexpected authority/delivery: "
            + ", ".join("/".join(item) for item in sorted(extra_matrix))
        )

    return errors


def _selftest() -> list[str]:
    """Negative self-tests (stdlib-only): a tampered template MUST be rejected, so
    the guard cannot silently rot into a no-op. Run on every invocation."""
    failures: list[str] = []
    base_text = ACL_PATH.read_text(encoding="utf-8")
    base = load_json5(base_text)
    if check(base):
        return ["the untampered template does not pass the guard"]

    cases: list[tuple[str, dict]] = []
    wrong_command = copy.deepcopy(base)
    next(
        policy
        for policy in wrong_command["access_control"]["policies"]
        if "commander-command-ingress" in policy["rules"]
    )["subjects"] = ["body"]
    cases.append(("a non-commander command-put policy", wrong_command))

    no_sensor_authority = copy.deepcopy(base)
    next(
        rule
        for rule in no_sensor_authority["access_control"]["rules"]
        if rule["id"] == "body-data-ingress"
    )["messages"].remove("put")
    cases.append(("missing sensor-put authority", no_sensor_authority))

    wrong_observation = copy.deepcopy(base)
    next(
        policy
        for policy in wrong_observation["access_control"]["policies"]
        if "body-data-ingress" in policy["rules"]
    )["subjects"] = ["body", "commander"]
    cases.append(("non-body observation-put authority", wrong_observation))

    no_observation_authority = copy.deepcopy(base)
    publisher_rule = next(
        rule
        for rule in no_observation_authority["access_control"]["rules"]
        if rule["id"] == "body-data-ingress"
    )
    publisher_rule["key_exprs"].remove("ncp/session/*/observation")
    cases.append(("missing observation-put authority", no_observation_authority))

    broad_observation = copy.deepcopy(base)
    publisher_rule = next(
        rule
        for rule in broad_observation["access_control"]["rules"]
        if rule["id"] == "body-data-ingress"
    )
    publisher_rule["key_exprs"][-1] = "ncp/session/**"
    cases.append(("an over-broad session write expression", broad_observation))

    invalid_token = copy.deepcopy(base)
    invalid_token["access_control"]["rules"][0]["messages"].append("get")
    cases.append(("an invalid 'get' messages token", invalid_token))

    no_mtls = copy.deepcopy(base)
    no_mtls["transport"]["link"]["tls"]["enable_mtls"] = False
    cases.append(("a router with mTLS disabled", no_mtls))

    observer_rpc = copy.deepcopy(base)
    observer_rpc["access_control"]["policies"].append(
        {"rules": ["commander-rpc-query-ingress"], "subjects": ["observer"]}
    )
    cases.append(("observer lifecycle-RPC query authority", observer_rpc))

    commander_serves_rpc = copy.deepcopy(base)
    commander_serves_rpc["access_control"]["policies"].append(
        {"rules": ["body-rpc-serve-ingress"], "subjects": ["commander"]}
    )
    cases.append(("commander lifecycle-RPC serve/reply authority", commander_serves_rpc))

    no_rpc_query = copy.deepcopy(base)
    next(
        rule
        for rule in no_rpc_query["access_control"]["rules"]
        if rule["id"] == "commander-rpc-query-ingress"
    )["messages"].clear()
    cases.append(("missing lifecycle-RPC query authority", no_rpc_query))

    no_rpc_queryable = copy.deepcopy(base)
    next(
        rule
        for rule in no_rpc_queryable["access_control"]["rules"]
        if rule["id"] == "body-rpc-serve-ingress"
    )["messages"].remove("declare_queryable")
    cases.append(("missing lifecycle-RPC queryable authority", no_rpc_queryable))

    no_rpc_reply = copy.deepcopy(base)
    next(
        rule
        for rule in no_rpc_reply["access_control"]["rules"]
        if rule["id"] == "body-rpc-serve-ingress"
    )["messages"].remove("reply")
    cases.append(("missing lifecycle-RPC reply authority", no_rpc_reply))

    no_command_delivery = copy.deepcopy(base)
    next(
        policy
        for policy in no_command_delivery["access_control"]["policies"]
        if "body-command-data-egress" in policy["rules"]
    )["rules"].remove("body-command-data-egress")
    cases.append(("missing body command delivery", no_command_delivery))

    unsafe_both_flows = copy.deepcopy(base)
    next(
        rule
        for rule in unsafe_both_flows["access_control"]["rules"]
        if rule["id"] == "body-command-data-egress"
    )["flows"].append("ingress")
    cases.append(("egress delivery widened into publish ingress", unsafe_both_flows))

    unsupported_token = copy.deepcopy(base)
    next(
        rule
        for rule in unsupported_token["access_control"]["rules"]
        if rule["id"] == "commander-rpc-query-ingress"
    )["messages"].append("declare_querier")
    cases.append(("unsupported declare_querier token", unsupported_token))

    missing_observer_sensor = copy.deepcopy(base)
    observer_rule = next(
        rule
        for rule in missing_observer_sensor["access_control"]["rules"]
        if rule["id"] == "observer-subscription-ingress"
    )
    observer_rule["key_exprs"].remove("ncp/session/*/sensor/**")
    cases.append(("observer without sensor-plane read coverage", missing_observer_sensor))

    missing_observer_command = copy.deepcopy(base)
    observer_rule = next(
        rule
        for rule in missing_observer_command["access_control"]["rules"]
        if rule["id"] == "observer-subscription-ingress"
    )
    observer_rule["key_exprs"].remove("ncp/session/*/command/**")
    cases.append(("observer without command-plane read coverage", missing_observer_command))

    missing_observer_observation = copy.deepcopy(base)
    observer_rule = next(
        rule
        for rule in missing_observer_observation["access_control"]["rules"]
        if rule["id"] == "observer-subscription-ingress"
    )
    observer_rule["key_exprs"].remove("ncp/session/*/observation")
    cases.append(
        ("observer without observation-plane read coverage", missing_observer_observation)
    )

    observer_write = copy.deepcopy(base)
    observer_write["access_control"]["policies"].append(
        {"rules": ["body-data-ingress"], "subjects": ["observer"]}
    )
    cases.append(("observer sensor-plane write authority", observer_write))

    shared_cn = copy.deepcopy(base)
    next(
        subject
        for subject in shared_cn["access_control"]["subjects"]
        if subject["id"] == "observer"
    )["cert_common_names"].append("commander")
    cases.append(("one certificate CN mapped to multiple roles", shared_cn))

    no_expiration_close = copy.deepcopy(base)
    no_expiration_close["transport"]["link"]["tls"]["close_link_on_expiration"] = False
    cases.append(("a router retaining expired TLS links", no_expiration_close))

    for description, cfg in cases:
        if not check(cfg):
            failures.append(f"{description} was NOT rejected")

    # Realm rendering is part of deployment correctness, and malformed realm input
    # must never widen a key expression.
    rendered = render(base_text, "engram/ncp")
    rendered_cfg = load_json5(rendered)
    if check(rendered_cfg):
        failures.append("a valid multi-segment rendered realm was rejected")
    mixed_template = base_text.replace(
        '"ncp/session/*/observation"', '"other/session/*/observation"', 1
    )
    try:
        render(mixed_template, "engram/ncp")
    except ValueError:
        pass
    else:
        failures.append("a template with mixed realms was NOT rejected")
    for bad in ["", "ncp/**", "/ncp", "ncp/", "ncp//fleet", "ncp\ncommand"]:
        try:
            render(base_text, bad)
        except ValueError:
            pass
        else:
            failures.append(f"unsafe rendered realm {bad!r} was NOT rejected")
    return failures


def main() -> int:
    self_failures = _selftest()
    if self_failures:
        print("FAIL: ACL guard self-test failed (the guard is broken):", file=sys.stderr)
        for f in self_failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    text = ACL_PATH.read_text(encoding="utf-8")
    try:
        cfg = load_json5(text)
    except json.JSONDecodeError as e:  # pragma: no cover - structural failure
        print(f"FAIL: could not parse {ACL_PATH.name}: {e}", file=sys.stderr)
        return 1

    errors = check(cfg)
    manifest = ZENOH_MANIFEST.read_text(encoding="utf-8")
    if '"transport_tls"' not in manifest:
        errors.append(
            "ncp-zenoh does not compile Zenoh's transport_tls feature; the documented "
            "mTLS deployment would be impossible in the standalone SDK"
        )
    if errors:
        print("FAIL: ACL template guard found problems:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    n_rules = len(cfg.get("access_control", {}).get("rules", []))
    print(
        f"OK: {ACL_PATH.name} — {n_rules} rules, tokens valid, "
        f"{len(EXPECTED_MATRIX)} exact subject/message/flow/plane grants, "
        "functional source/destination directions, TLS transport compiled; "
        "router-config "
        "preflight only (NCP peer/IdentityClaim binding unavailable)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
