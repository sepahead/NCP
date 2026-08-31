#!/usr/bin/env python3
"""Generate the non-authorizing B01 human-review request.

The request allocates the exact minimum reviewer and evidence slots from one
immutable CURRENT packet commit. It never emits a reviewer identity, review
decision, timestamp, URL, evidence digest, or task transition.

This module uses only the Python standard library. Its Git reader resolves
regular blobs without changing the worktree.
"""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import os
import re
import secrets
import selectors
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import zlib
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn

import immutable_git as immutable_git_module
from immutable_git import (
    ImmutableGitError,
    blob_snapshot,
)
from immutable_git import (
    commit_tree as immutable_commit_tree,
)
from immutable_git import (
    git_environment as immutable_git_environment,
)
from immutable_git import (
    read_commit as immutable_read_commit,
)
from immutable_git import (
    read_object as immutable_read_object,
)
from immutable_git import (
    read_tree_entry as immutable_read_tree_entry,
)
from immutable_git import (
    require_ancestor as immutable_require_ancestor,
)
from immutable_git import (
    require_unmodified_git_history as immutable_require_unmodified_git_history,
)
from immutable_git import (
    shared_operation as immutable_git_operation,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_RELATIVE = "scripts/generate_b01_review_request.py"
IMMUTABLE_GIT_RELATIVE = "scripts/immutable_git.py"
GENERATOR_SOURCE_RELATIVES = (SCRIPT_RELATIVE, IMMUTABLE_GIT_RELATIVE)
PACKET_RELATIVE = "docs/adr/B01_REVIEW_PACKET.md"
REGISTRY_RELATIVE = "docs/adr/decision-registry.proposed.v1.json"
SOURCE_RELATIVE = "docs/adr/decision-registry.source.v1.json"
OUTPUT_RELATIVE = "evidence/implementation/requests/B01/review-request.v1.json"
DEFAULT_AUTHORIZED_REF = "refs/remotes/origin/main"
LOCAL_MAIN_REF = "refs/heads/main"
REMOTE_NAME = "origin"
REMOTE_QUERY_REF = "refs/heads/main"
CANONICAL_REPOSITORY = "github.com/sepahead/NCP"
CANONICAL_HTTPS_URL = "https://github.com/sepahead/NCP.git"
CANONICAL_SSH_URL = "git@github.com:sepahead/NCP.git"
CANONICAL_ORIGIN_URLS = {
    CANONICAL_SSH_URL,
    CANONICAL_HTTPS_URL,
}
GITHUB_ED25519_KNOWN_HOST = (
    b"github.com ssh-ed25519 "
    b"AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl\n"
)
GITHUB_ED25519_KNOWN_HOST_SHA256 = (
    "6233fddbb0a29afc8c4e8c699733c1a188c3a41f2fb63a2640653dc4aea624ce"
)
GITHUB_ED25519_FINGERPRINT = "SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU"
REMOTE_TRANSPORT_PROFILE = "PINNED_GITHUB_ED25519_SSH_AGENT_V1"
SSH_BINARY = "/usr/bin/ssh"
GIT_BINARY = "/usr/bin/git"
SELF_TEST_AGENT_SOCKET = str(
    Path(tempfile.gettempdir()) / "ncp-b01-self-test-agent.sock"
)
SELF_TEST_KNOWN_HOSTS = str(
    Path(tempfile.gettempdir()) / "ncp-b01-self-test-known-hosts"
)
EFFECTIVE_TEST_AGENT_SOCKET = str(
    Path(tempfile.gettempdir()) / "ncp-b01-effective-agent.sock"
)
EFFECTIVE_TEST_KNOWN_HOSTS = str(
    Path(tempfile.gettempdir()) / "ncp-b01-effective-known-hosts"
)
HOSTILE_TEST_KNOWN_HOSTS = str(
    Path(tempfile.gettempdir()) / "ncp-b01-hostile-path-known-hosts"
)
REMOTE_OBSERVATION_STATE = "NON_AUTHORIZING_REMOTE_REF_OBSERVATION"
REMOTE_OBSERVATION_CLAIM_BOUNDARY = (
    "REMOTE_REF_OBSERVATION_ONLY_NO_REVIEWER_IDENTITY_REVIEW_DECISION_ROLE_"
    "AUTHORITY_PROTOCOL_AUTHORITY_TASK_AUTHORITY_RELEASE_AUTHORITY_OR_REMOTE_"
    "OWNER_AUTHENTICATION_OR_HISTORICAL_REMOTE_STATE_ATTESTATION"
)
REMOTE_OBSERVATION_POLICY = (
    "LIVE_CANONICAL_LS_REMOTE_MAIN_EQUALS_LOCAL_ORIGIN_MAIN_AND_LOCAL_MAIN_"
    "RETAINED_COMMIT_IS_AUDIT_IDENTITY_ONLY"
)
REMOTE_TIMEOUT_SECONDS = 15
MAX_REMOTE_CONFIG_BYTES = 1_024
MAX_LS_REMOTE_BYTES = 256
MAX_LOCAL_GIT_STDOUT_BYTES = 4 * 1024 * 1024
MAX_GIT_STDERR_BYTES = 4_096
AUTHORIZED_REF_POLICY = (
    "ISSUANCE_COMMIT_RETAINED_LIVE_CANONICAL_REMOTE_AND_LOCAL_MAIN_MUST_DESCEND_"
    "AND_PRESERVE_EXACT_CURRENT_ZERO_REVIEW_PACKET_SUBJECT"
)

REQUEST_SCHEMA = "ncp.b01-review-request.v1"
REQUEST_CLAIM_BOUNDARY = (
    "REQUEST_ONLY_UNFILLED_SLOTS_NO_REVIEWER_DECISION_ROLE_AUTHORITY_"
    "INDEPENDENCE_ADR_ACCEPTANCE_TASK_STATUS_PROTOCOL_CHANGE_OR_RELEASE_AUTHORITY"
)
REVIEW_SUBJECT_SCHEMA = "ncp.b01-review-subject.v1"
PACKET_LIFECYCLE_SCHEMA = "ncp.b01-review-packet-lifecycle.v1"
DECISION_SET_SCHEMA = "ncp.b01-decision-set.v1"
ADR_SOURCE_SET_SCHEMA = "ncp.b01-adr-source-set.v1"
REGISTRY_SCHEMA = "ncp.proposed-decision-registry.v1"
SOURCE_SCHEMA = "ncp.proposed-decision-registry-source.v1"
REVIEW_POLICY_SCHEMA = "ncp.b01-review-policy.v1"
REGISTRY_CLAIM_BOUNDARY = (
    "This generated registry records non-normative architecture decisions and "
    "structurally checked review claims. It cannot prove external authorship, role "
    "authority, or independence. It cannot satisfy B01 by itself, authorize the "
    "pre-release rebaseline or publication, or grant runtime identity, authority, "
    "plant action, safety, interoperability, or a scientific claim."
)
SOURCE_CLAIM_BOUNDARY = (
    "This source records non-normative architecture decisions and bounded review "
    "claims. Its structural checks cannot prove external authorship, role authority, "
    "or independence. It cannot change the normative contract, authorize a rebaseline "
    "or release, satisfy B01 by itself, or certify an implementation or deployment."
)
PROMOTION_TARGET = "contract/decision-registry.v1.json"
POLICY_GENERATOR_RELATIVE = "scripts/generate_decision_registry.py"
POLICY_SCHEMA_RELATIVE = "docs/adr/decision-registry.proposed.schema.v1.json"
CLOSURE_SOURCE_RELATIVE = "docs/adr/decision-closure.source.v1.json"
CLOSURE_SCHEMA_RELATIVE = "docs/adr/decision-closure.source.schema.v1.json"
SEMANTIC_CORPUS_RELATIVE = (
    "prototypes/b01-architecture-evidence/adr-example-semantics/corpus.v1.json"
)
CLOSURE_EVALUATION_SCHEMA = "ncp.b01-semantic-closure-evaluation.v1"
SEMANTIC_CORPUS_SCHEMA = "ncp.b01-adr-example-semantics-corpus.v1"
CLOSURE_SOURCE_SCHEMA = "ncp.b01-decision-closure-source.v1"
DECISION_SET_DOMAIN = b"ncp.b01-decision-set.v1\x00"
ADR_SOURCE_SET_DOMAIN = b"ncp.b01-adr-source-set.v1\x00"
DECISION_SET_DIGEST_ALGORITHM = (
    "sha256(domain || u64be(projection_bytes) || projection)"
)
EXPECTED_IDS = tuple(f"ADR-{number:03d}" for number in range(1, 12))
EXPECTED_COUNTS = {
    "decisions": 11,
    "role_obligations": 52,
    "minimum_identity_slots": 53,
    "independent_obligations": 5,
    "minimum_independent_identity_slots": 6,
    "minimum_evidence_requirements": 112,
}
EVIDENCE_PREFIX = "evidence/implementation/reviews/B01/"
EVIDENCE_KINDS = (
    "ROLE_AUTHORIZATION",
    "EXTERNAL_REVIEW_RECEIPT",
    "INDEPENDENCE_ASSESSMENT",
)
SOURCE_RECORD_FIELDS = (
    "review_id",
    "adr_id",
    "role_id",
    "reviewer",
    "subject",
    "decision",
    "conditions",
    "role_authorization",
    "independence_assessment",
    "external_receipt",
    "timestamp_utc",
    "supersedes",
)
EVIDENCE_REFERENCE_FIELDS = (
    "url",
    "path",
    "sha256",
    "bytes",
    "media_type",
)
DECISION_POPULATION = "HUMAN_REVIEWER_ONLY_MODEL_OR_AUTOMATION_FORBIDDEN"
EVIDENCE_POPULATION = "HUMAN_OR_AUTHENTICATED_NON_MODEL_SYSTEM_ONLY"

MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_PACKET_BYTES = 2 * 1024 * 1024
MAX_SOURCE_FILE_BYTES = 2 * 1024 * 1024
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_ANCESTRY_COMMITS = 4_096
MAX_ANCESTRY_EDGES = 16_384
MAX_JSON_DEPTH = 32
MAX_JSON_NODES = 100_000
MAX_JSON_STRING_BYTES = 2 * 1024 * 1024

HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
ROLE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SLOT_ID = re.compile(r"^adr-(?:00[1-9]|01[01])\.[a-z0-9]+(?:-[a-z0-9]+)*\.[0-9]{2}$")
EVIDENCE_ID = re.compile(
    r"^adr-(?:00[1-9]|01[01])\.[a-z0-9]+(?:-[a-z0-9]+)*\.[0-9]{2}\."
    r"(?:role-authorization|external-review-receipt|independence-assessment)$"
)


class RequestError(RuntimeError):
    """A fail-closed request generation error."""


def fail(message: str) -> NoReturn:
    raise RequestError(message)


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def generated_bytes(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def exact_keys(value: Any, expected: set[str], path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(f"{path} must be an object")
    actual = set(value)
    if actual != expected:
        fail(
            f"{path} has unexpected members: "
            f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
    return value


def bounded_string(
    value: Any,
    path: str,
    *,
    minimum: int = 1,
    maximum: int = 4096,
) -> str:
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        fail(f"{path} must be a string with {minimum}..{maximum} characters")
    return value


def bounded_integer(
    value: Any,
    path: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        fail(f"{path} must be an integer in {minimum}..{maximum}")
    return value


def validate_hex(value: Any, pattern: re.Pattern[str], path: str) -> str:
    text = bounded_string(value, path, maximum=64)
    if not pattern.fullmatch(text):
        fail(f"{path} must be lowercase hexadecimal with the exact length")
    return text


def relative_path(value: Any, path: str) -> str:
    text = bounded_string(value, path, maximum=512)
    candidate = PurePosixPath(text)
    if (
        candidate.is_absolute()
        or text != candidate.as_posix()
        or "\\" in text
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        fail(f"{path} must be one canonical repository-relative POSIX path")
    return text


def open_repository_parent(
    relative: str,
    label: str,
    *,
    root: Path | None = None,
    root_descriptor: int | None = None,
) -> tuple[int, str]:
    """Open a repository directory chain without following internal symlinks."""

    checked = relative_path(relative, label)
    parts = PurePosixPath(checked).parts
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    current: int | None = None
    try:
        if root_descriptor is None:
            repository_root = ROOT if root is None else root
            current = os.open(repository_root, directory_flags)
        else:
            current = os.dup(root_descriptor)
            if not stat.S_ISDIR(os.fstat(current).st_mode):
                fail(f"pinned repository root for {label} must be a directory")
    except RequestError:
        if current is not None:
            os.close(current)
        raise
    except OSError as error:
        if current is not None:
            os.close(current)
        fail(f"cannot open repository root for {label}: {error}")
    if current is None:
        fail(f"cannot open repository root for {label}")
    try:
        for component in parts[:-1]:
            next_directory = os.open(
                component,
                directory_flags,
                dir_fd=current,
            )
            os.close(current)
            current = next_directory
    except OSError as error:
        os.close(current)
        fail(f"cannot open repository directory chain for {label}: {error}")
    return current, parts[-1]


def read_repository_regular_file(
    relative: str,
    *,
    minimum: int,
    maximum: int,
    label: str,
    root: Path | None = None,
    root_descriptor: int | None = None,
) -> bytes:
    """Read one stable bounded repository file without following symlinks."""

    parent, leaf = open_repository_parent(
        relative,
        label,
        root=root,
        root_descriptor=root_descriptor,
    )
    descriptor: int | None = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(leaf, flags, dir_fd=parent)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            fail(f"{label} must be a regular file")
        if not minimum <= before.st_size <= maximum:
            fail(f"{label} byte size is outside {minimum}..{maximum}")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                fail(f"{label} ended before its retained byte size")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            fail(f"{label} grew while it was read")
        after = os.fstat(descriptor)
        observed = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
        stable_fields = ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns")
        if any(
            getattr(before, field) != getattr(after, field) for field in stable_fields
        ):
            fail(f"{label} changed while it was read")
        if any(
            getattr(after, field) != getattr(observed, field) for field in stable_fields
        ):
            fail(f"{label} path changed while it was read")
        content = b"".join(chunks)
        if len(content) != before.st_size:
            fail(f"{label} read returned the wrong byte count")
        return content
    except OSError as error:
        fail(f"cannot read {label}: {error}")
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent)


def require_repository_parent_identity(
    relative: str,
    expected_parent: os.stat_result,
    *,
    label: str,
) -> None:
    """Rejoin one open parent directory to its current repository path."""

    fresh_parent, _leaf = open_repository_parent(relative, label)
    try:
        observed = os.fstat(fresh_parent)
    except OSError as error:
        os.close(fresh_parent)
        fail(f"cannot rejoin repository parent for {label}: {error}")
    os.close(fresh_parent)
    stable_fields = ("st_dev", "st_ino", "st_mode")
    if any(
        getattr(observed, field) != getattr(expected_parent, field)
        for field in stable_fields
    ):
        fail(f"repository parent changed during {label}")


def parse_json_bytes(content: bytes, label: str) -> Any:
    if not 1 <= len(content) <= MAX_JSON_BYTES:
        fail(f"{label} byte size is outside 1..{MAX_JSON_BYTES}")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        fail(f"{label} must be UTF-8: {error}")

    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                fail(f"{label} contains duplicate object member {key!r}")
            result[key] = value
        return result

    def parse_integer(token: str) -> int:
        if len(token) > 128:
            fail(f"{label} contains an overlong integer")
        return int(token)

    def reject_float(token: str) -> NoReturn:
        fail(f"{label} contains unsupported floating-point value {token!r}")

    def reject_constant(token: str) -> NoReturn:
        fail(f"{label} contains non-JSON constant {token!r}")

    try:
        value = json.loads(
            text,
            object_pairs_hook=object_pairs,
            parse_int=parse_integer,
            parse_float=reject_float,
            parse_constant=reject_constant,
        )
    except json.JSONDecodeError as error:
        fail(f"{label} is invalid JSON: {error}")
    validate_json_tree(value, label)
    return value


def validate_json_tree(value: Any, label: str) -> None:
    stack: list[tuple[Any, int]] = [(value, 0)]
    nodes = 0
    string_bytes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES:
            fail(f"{label} exceeds {MAX_JSON_NODES} JSON nodes")
        if depth > MAX_JSON_DEPTH:
            fail(f"{label} exceeds JSON depth {MAX_JSON_DEPTH}")
        if isinstance(current, dict):
            if len(current) > 4096:
                fail(f"{label} contains an overlarge object")
            for key, child in current.items():
                if not isinstance(key, str):
                    fail(f"{label} contains a non-string object key")
                string_bytes += len(key.encode("utf-8"))
                stack.append((child, depth + 1))
        elif isinstance(current, list):
            if len(current) > 4096:
                fail(f"{label} contains an overlarge array")
            stack.extend((child, depth + 1) for child in current)
        elif isinstance(current, str):
            string_bytes += len(current.encode("utf-8"))
        elif current is None or isinstance(current, bool) or type(current) is int:
            pass
        else:
            fail(f"{label} contains an unsupported JSON value")
        if string_bytes > MAX_JSON_STRING_BYTES:
            fail(f"{label} exceeds the aggregate JSON string-byte limit")


def file_identity(path: str, content: bytes) -> dict[str, Any]:
    relative_path(path, f"file identity {path}")
    return {"path": path, "sha256": sha256_bytes(content), "bytes": len(content)}


def validate_file_identity(
    value: Any,
    path: str,
    *,
    expected_path: str,
    content: bytes,
) -> dict[str, Any]:
    identity = exact_keys(value, {"path", "sha256", "bytes"}, path)
    if relative_path(identity["path"], f"{path}.path") != expected_path:
        fail(f"{path}.path differs from {expected_path}")
    validate_hex(identity["sha256"], HEX64, f"{path}.sha256")
    bounded_integer(
        identity["bytes"],
        f"{path}.bytes",
        minimum=1,
        maximum=MAX_SOURCE_FILE_BYTES,
    )
    if identity != file_identity(expected_path, content):
        fail(f"{path} differs from the exact retained bytes")
    return identity


def extract_json_fences(content: bytes) -> list[dict[str, Any]]:
    if not 1 <= len(content) <= MAX_PACKET_BYTES:
        fail("review packet is outside its bounded byte range")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        fail(f"review packet must be UTF-8: {error}")
    fences: list[dict[str, Any]] = []
    current: list[str] | None = None
    for line_number, line in enumerate(text.splitlines(), start=1):
        if current is None:
            if line == "```json":
                current = []
            continue
        if line == "```":
            parsed = parse_json_bytes(
                ("\n".join(current) + "\n").encode("utf-8"),
                f"review packet JSON fence ending at line {line_number}",
            )
            if isinstance(parsed, dict):
                fences.append(parsed)
            current = None
        else:
            current.append(line)
    if current is not None:
        fail("review packet contains an unterminated JSON fence")
    return fences


def domain_digest(domain: bytes, projection: Any) -> str:
    payload = canonical_json_bytes(projection)
    return sha256_bytes(domain + len(payload).to_bytes(8, "big") + payload)


def validate_source_set(
    value: Any,
    path: str,
    *,
    decision_id: str,
    source_files: dict[str, bytes],
) -> dict[str, Any]:
    source_set = exact_keys(
        value,
        {
            "schema",
            "decision_id",
            "sources",
            "digest_algorithm",
            "domain_hex",
            "sha256",
        },
        path,
    )
    if source_set["schema"] != ADR_SOURCE_SET_SCHEMA:
        fail(f"{path}.schema is invalid")
    if source_set["decision_id"] != decision_id:
        fail(f"{path}.decision_id differs from {decision_id}")
    if source_set["digest_algorithm"] != DECISION_SET_DIGEST_ALGORITHM:
        fail(f"{path}.digest_algorithm is invalid")
    if source_set["domain_hex"] != ADR_SOURCE_SET_DOMAIN.hex():
        fail(f"{path}.domain_hex is invalid")
    sources = source_set["sources"]
    if not isinstance(sources, list) or not 1 <= len(sources) <= 9:
        fail(f"{path}.sources must contain 1..9 source identities")
    seen: set[str] = set()
    for index, source in enumerate(sources):
        source_path = f"{path}.sources[{index}]"
        source = exact_keys(source, {"kind", "path", "sha256", "bytes"}, source_path)
        expected_kind = "main" if index == 0 else "module"
        if source["kind"] != expected_kind:
            fail(f"{source_path}.kind must be {expected_kind}")
        relative = relative_path(source["path"], f"{source_path}.path")
        if relative in seen:
            fail(f"{path}.sources duplicates {relative}")
        seen.add(relative)
        content = source_files.get(relative)
        if content is None:
            fail(f"{source_path} is absent from the immutable source cut")
        validate_file_identity(
            {key: source[key] for key in ("path", "sha256", "bytes")},
            source_path,
            expected_path=relative,
            content=content,
        )
    projection = {
        "schema": ADR_SOURCE_SET_SCHEMA,
        "decision_id": decision_id,
        "sources": sources,
    }
    expected_digest = domain_digest(ADR_SOURCE_SET_DOMAIN, projection)
    if validate_hex(source_set["sha256"], HEX64, f"{path}.sha256") != expected_digest:
        fail(f"{path}.sha256 differs from the canonical source-set digest")
    return source_set


def validate_required_review(value: Any, path: str) -> dict[str, Any]:
    review = exact_keys(
        value,
        {"role_id", "label", "min_distinct_identities", "requires_independence"},
        path,
    )
    role_id = bounded_string(review["role_id"], f"{path}.role_id", maximum=64)
    if not ROLE_ID.fullmatch(role_id):
        fail(f"{path}.role_id must use canonical lowercase kebab case")
    bounded_string(review["label"], f"{path}.label", minimum=3, maximum=128)
    bounded_integer(
        review["min_distinct_identities"],
        f"{path}.min_distinct_identities",
        minimum=1,
        maximum=8,
    )
    if not isinstance(review["requires_independence"], bool):
        fail(f"{path}.requires_independence must be boolean")
    return review


def validate_review_policy_semantics(value: Any, path: str) -> dict[str, Any]:
    policy = exact_keys(
        value,
        {
            "schema",
            "source_schema",
            "output_schema",
            "generator",
            "output_json_schema",
        },
        path,
    )
    if policy["schema"] != REVIEW_POLICY_SCHEMA:
        fail(f"{path}.schema differs from the frozen non-authorizing policy")
    if policy["source_schema"] != SOURCE_SCHEMA:
        fail(f"{path}.source_schema differs from the frozen source schema")
    if policy["output_schema"] != REGISTRY_SCHEMA:
        fail(f"{path}.output_schema differs from the frozen output schema")
    validate_file_identity_shape(policy["generator"], f"{path}.generator")
    validate_file_identity_shape(
        policy["output_json_schema"], f"{path}.output_json_schema"
    )
    if policy["generator"]["path"] != POLICY_GENERATOR_RELATIVE:
        fail(f"{path}.generator identifies the wrong authority-constrained tool")
    if policy["output_json_schema"]["path"] != POLICY_SCHEMA_RELATIVE:
        fail(f"{path}.output_json_schema identifies the wrong closed schema")
    return policy


def validate_registry_authority_semantics(
    value: Any,
    path: str,
) -> dict[str, Any]:
    registry = exact_keys(
        value,
        {
            "schema",
            "normative",
            "candidate",
            "wire_version",
            "task",
            "claim_boundary",
            "generated_by",
            "source",
            "review_policy",
            "review_packet",
            "review_packet_lifecycle",
            "review_packet_subject",
            "decision_set",
            "semantic_closure_evaluation",
            "promotion_target",
            "promotion_blocked",
            "counts",
            "decisions",
            "review_records",
        },
        path,
    )
    if registry["schema"] != REGISTRY_SCHEMA:
        fail(f"{path}.schema differs from the proposed registry schema")
    if registry["normative"] is not False:
        fail(f"{path}.normative must remain false")
    if registry["candidate"] != "1.0.0-rc.1" or registry["wire_version"] != "1.0":
        fail(f"{path} candidate or wire differs from the frozen request")
    if registry["task"] != "B01":
        fail(f"{path}.task must remain B01")
    if registry["claim_boundary"] != REGISTRY_CLAIM_BOUNDARY:
        fail(f"{path}.claim_boundary differs from the non-authorizing boundary")
    if registry["generated_by"] != POLICY_GENERATOR_RELATIVE:
        fail(f"{path}.generated_by identifies the wrong generator")
    if registry["promotion_target"] != PROMOTION_TARGET:
        fail(f"{path}.promotion_target differs from the reviewed target")
    if registry["promotion_blocked"] is not True:
        fail(f"{path}.promotion_blocked must remain true")
    if registry["counts"] != {"decisions": len(EXPECTED_IDS)}:
        fail(f"{path}.counts must retain exactly eleven decisions")
    if registry["review_records"] != []:
        fail(f"{path}.review_records must remain empty for request issuance")
    validate_review_policy_semantics(registry["review_policy"], f"{path}.review_policy")
    return registry


def validate_source_authority_semantics(value: Any, path: str) -> dict[str, Any]:
    source = exact_keys(
        value,
        {
            "schema",
            "normative",
            "candidate",
            "wire_version",
            "task",
            "claim_boundary",
            "promotion_target",
            "promotion_blocked",
            "decisions",
            "review_records",
        },
        path,
    )
    if source["schema"] != SOURCE_SCHEMA:
        fail(f"{path}.schema differs from the proposed source schema")
    if source["normative"] is not False:
        fail(f"{path}.normative must remain false")
    if source["candidate"] != "1.0.0-rc.1" or source["wire_version"] != "1.0":
        fail(f"{path} candidate or wire differs from the frozen request")
    if source["task"] != "B01":
        fail(f"{path}.task must remain B01")
    if source["claim_boundary"] != SOURCE_CLAIM_BOUNDARY:
        fail(f"{path}.claim_boundary differs from the non-authorizing boundary")
    if source["promotion_target"] != PROMOTION_TARGET:
        fail(f"{path}.promotion_target differs from the reviewed target")
    if source["promotion_blocked"] is not True:
        fail(f"{path}.promotion_blocked must remain true")
    if source["review_records"] != []:
        fail(f"{path}.review_records must remain empty for request issuance")
    return source


def validate_decision(
    value: Any,
    path: str,
    *,
    expected_id: str,
    source_files: dict[str, bytes],
) -> dict[str, Any]:
    decision = exact_keys(
        value,
        {
            "id",
            "title",
            "path",
            "module_paths",
            "content_sha256",
            "bytes",
            "source_set",
            "required_reviews",
            "defect_ids",
        },
        path,
    )
    if decision["id"] != expected_id:
        fail(f"{path}.id differs from {expected_id}")
    bounded_string(decision["title"], f"{path}.title", minimum=8, maximum=160)
    main_path = relative_path(decision["path"], f"{path}.path")
    module_paths = decision["module_paths"]
    if not isinstance(module_paths, list) or len(module_paths) > 8:
        fail(f"{path}.module_paths must contain at most 8 paths")
    checked_modules = [
        relative_path(module, f"{path}.module_paths[{index}]")
        for index, module in enumerate(module_paths)
    ]
    if len(checked_modules) != len(set(checked_modules)):
        fail(f"{path}.module_paths contains duplicates")
    source_set = validate_source_set(
        decision["source_set"],
        f"{path}.source_set",
        decision_id=expected_id,
        source_files=source_files,
    )
    expected_paths = [main_path, *checked_modules]
    observed_paths = [source["path"] for source in source_set["sources"]]
    if observed_paths != expected_paths:
        fail(f"{path}.source_set differs from its main and module path roster")
    main_source = source_set["sources"][0]
    if (
        decision["content_sha256"] != main_source["sha256"]
        or decision["bytes"] != main_source["bytes"]
    ):
        fail(f"{path} main content identity differs from its source set")
    reviews = decision["required_reviews"]
    if not isinstance(reviews, list) or not 2 <= len(reviews) <= 16:
        fail(f"{path}.required_reviews must contain 2..16 obligations")
    role_ids: list[str] = []
    for index, review in enumerate(reviews):
        checked = validate_required_review(review, f"{path}.required_reviews[{index}]")
        role_ids.append(checked["role_id"])
    if len(role_ids) != len(set(role_ids)):
        fail(f"{path}.required_reviews contains duplicate role IDs")
    defects = decision["defect_ids"]
    if (
        not isinstance(defects, list)
        or not 1 <= len(defects) <= 8
        or len(defects) != len(set(defects))
        or any(not isinstance(item, str) for item in defects)
    ):
        fail(f"{path}.defect_ids is invalid")
    return decision


def validate_acceptance_blockers(
    value: Any,
    required_reviews: list[dict[str, Any]],
    path: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        fail(f"{path} must contain one blocker for every required review")
    checked: list[dict[str, Any]] = []
    for index, blocker in enumerate(value):
        checked.append(
            exact_keys(
                blocker,
                {"code", "role_id", "review_ids", "detail"},
                f"{path}[{index}]",
            )
        )
    expected = [
        {
            "code": "MISSING_ROLE_ACCEPTANCE",
            "role_id": review["role_id"],
            "review_ids": [],
            "detail": (
                f"requires {review['min_distinct_identities']} distinct "
                "qualifying identities; observed 0"
            ),
        }
        for review in required_reviews
    ]
    if checked != expected:
        fail(f"{path} differs from the canonical required-review blocker roster")
    return checked


def semantic_corpus_counts(content: bytes) -> tuple[int, int]:
    """Derive the bounded maintained corpus counts from its exact source bytes."""

    corpus = exact_keys(
        parse_json_bytes(content, "semantic closure corpus"),
        {
            "schema",
            "schema_version",
            "candidate",
            "wire_version",
            "task",
            "claim_boundary",
            "source_binding",
            "decision_set_binding",
            "diagnostic_registry",
            "closed_values",
            "limits",
            "cases",
        },
        "semantic closure corpus",
    )
    if corpus["schema"] != SEMANTIC_CORPUS_SCHEMA:
        fail("semantic closure corpus has the wrong schema")
    limits = exact_keys(
        corpus["limits"],
        {
            "maximum_corpus_bytes",
            "maximum_aggregate_adr_bytes",
            "maximum_adr_bytes",
            "maximum_json_fence_bytes",
            "maximum_fixture_bytes",
            "maximum_json_depth",
            "maximum_json_nodes",
            "maximum_object_members",
            "maximum_array_items",
            "maximum_key_utf8_bytes",
            "maximum_string_utf8_bytes",
            "maximum_total_string_utf8_bytes",
            "maximum_integer_characters",
            "allow_floats",
            "expected_case_count",
            "expected_mutation_count",
            "minimum_mutations_per_case",
            "maximum_mutations_per_case",
            "maximum_engine_output_bytes",
            "engine_timeout_seconds",
        },
        "semantic closure corpus.limits",
    )
    cases = corpus["cases"]
    if not isinstance(cases, list) or not cases:
        fail("semantic closure corpus.cases must be a nonempty array")
    case_ids: list[str] = []
    mutation_ids: list[str] = []
    minimum = bounded_integer(
        limits["minimum_mutations_per_case"],
        "semantic closure corpus.limits.minimum_mutations_per_case",
        minimum=1,
        maximum=4_096,
    )
    maximum = bounded_integer(
        limits["maximum_mutations_per_case"],
        "semantic closure corpus.limits.maximum_mutations_per_case",
        minimum=minimum,
        maximum=4_096,
    )
    for index, case in enumerate(cases):
        checked = exact_keys(
            case,
            {
                "id",
                "source",
                "scope",
                "profile",
                "polarity",
                "expected_profile_result",
                "production_admission",
                "bounded_fixture",
                "expected_diagnostics",
                "payload_interpreted",
                "mutations",
            },
            f"semantic closure corpus.cases[{index}]",
        )
        case_ids.append(
            bounded_string(
                checked["id"],
                f"semantic closure corpus.cases[{index}].id",
                maximum=256,
            )
        )
        mutations = checked["mutations"]
        if not isinstance(mutations, list) or not minimum <= len(mutations) <= maximum:
            fail(
                f"semantic closure corpus.cases[{index}].mutations "
                "violates its maintained bounds"
            )
        for mutation_index, mutation in enumerate(mutations):
            checked_mutation = exact_keys(
                mutation,
                {
                    "id",
                    "purpose",
                    "patch",
                    "expected_profile_result",
                    "production_admission",
                    "expected_diagnostics",
                    "payload_interpreted",
                },
                (f"semantic closure corpus.cases[{index}].mutations[{mutation_index}]"),
            )
            mutation_ids.append(
                bounded_string(
                    checked_mutation["id"],
                    (
                        f"semantic closure corpus.cases[{index}]"
                        f".mutations[{mutation_index}].id"
                    ),
                    maximum=256,
                )
            )
    if len(case_ids) != len(set(case_ids)):
        fail("semantic closure corpus contains duplicate case IDs")
    if len(mutation_ids) != len(set(mutation_ids)):
        fail("semantic closure corpus contains duplicate mutation IDs")
    expected_cases = bounded_integer(
        limits["expected_case_count"],
        "semantic closure corpus.limits.expected_case_count",
        minimum=1,
        maximum=4_096,
    )
    expected_mutations = bounded_integer(
        limits["expected_mutation_count"],
        "semantic closure corpus.limits.expected_mutation_count",
        minimum=1,
        maximum=100_000,
    )
    if len(cases) != expected_cases or len(mutation_ids) != expected_mutations:
        fail("semantic closure corpus counts differ from its maintained limits")
    maximum_corpus_bytes = bounded_integer(
        limits["maximum_corpus_bytes"],
        "semantic closure corpus.limits.maximum_corpus_bytes",
        minimum=1,
        maximum=MAX_SOURCE_FILE_BYTES,
    )
    if len(content) > maximum_corpus_bytes:
        fail("semantic closure corpus exceeds its maintained byte limit")
    return expected_cases, expected_mutations


def deferred_b03_counts(content: bytes) -> tuple[int, int]:
    """Derive exact B03 question and validated-envelope counts from source bytes."""

    closure = exact_keys(
        parse_json_bytes(content, "decision closure source"),
        {
            "schema",
            "normative",
            "candidate",
            "wire_version",
            "task",
            "claim_boundary",
            "excluded_no_edge_components",
            "semantic_example_contract",
            "b03_parameter_contract",
            "decisions",
        },
        "decision closure source",
    )
    if closure["schema"] != CLOSURE_SOURCE_SCHEMA:
        fail("decision closure source has the wrong schema")
    decisions = closure["decisions"]
    if not isinstance(decisions, list) or len(decisions) != len(EXPECTED_IDS):
        fail("decision closure source must contain exactly eleven decisions")
    question_ids: list[str] = []
    deferred = 0
    validated = 0
    envelope_keys = {
        "owner_task",
        "owner_role_id",
        "parameters",
        "identity_eligibility_universes",
        "identity_eligibility_required",
        "equality_at_minimum",
        "equality_at_maximum",
        "below_minimum",
        "above_maximum",
        "arithmetic_overflow",
        "permissive_default",
        "failure_behavior",
        "meaning_change",
        "source_anchor",
        "validation_state",
    }
    for decision_index, decision in enumerate(decisions):
        checked_decision = exact_keys(
            decision,
            {"id", "adr_source_set_sha256", "questions", "example_requirements"},
            f"decision closure source.decisions[{decision_index}]",
        )
        if checked_decision["id"] != EXPECTED_IDS[decision_index]:
            fail("decision closure source decision roster is noncanonical")
        questions = checked_decision["questions"]
        if not isinstance(questions, list) or not questions:
            fail("decision closure source decision has no questions")
        for question_index, question in enumerate(questions):
            path = (
                f"decision closure source.decisions[{decision_index}]"
                f".questions[{question_index}]"
            )
            checked_question = exact_keys(
                question,
                {
                    "question_id",
                    "question_anchor",
                    "statement",
                    "state",
                    "resolution",
                    "resolution_anchor",
                    "b03_deferral",
                },
                path,
            )
            question_ids.append(
                bounded_string(
                    checked_question["question_id"],
                    f"{path}.question_id",
                    maximum=64,
                )
            )
            if checked_question["state"] != "DEFERRED_B03":
                continue
            deferred += 1
            if (
                checked_question["resolution"] is not None
                or checked_question["resolution_anchor"] is not None
            ):
                fail(f"{path} has a resolution despite its B03 deferral")
            envelope = exact_keys(
                checked_question["b03_deferral"], envelope_keys, f"{path}.b03_deferral"
            )
            if (
                envelope["owner_task"] != "B03"
                or envelope["validation_state"] != "VALIDATED"
                or envelope["identity_eligibility_required"] is not True
                or envelope["permissive_default"] is not False
                or envelope["failure_behavior"] != "REJECT_BEFORE_ALLOCATION"
                or envelope["meaning_change"] != "FORBIDDEN"
                or not isinstance(envelope["parameters"], list)
                or not envelope["parameters"]
            ):
                fail(f"{path}.b03_deferral is not one validated fail-closed envelope")
            validated += 1
    if len(question_ids) != len(set(question_ids)):
        fail("decision closure source contains duplicate question IDs")
    if deferred == 0 or validated != deferred:
        fail("decision closure source does not validate every B03 deferral")
    return deferred, validated


def validate_semantic_closure_evaluation(
    decision_set: dict[str, Any],
    evaluation: Any,
    source_files: dict[str, bytes],
) -> dict[str, Any]:
    semantic_closure = exact_keys(
        decision_set["semantic_closure"],
        {"source", "json_schema"},
        "packet subject decision_set.semantic_closure",
    )
    checked = exact_keys(
        evaluation,
        {
            "schema",
            "decision_set_sha256",
            "state",
            "source",
            "json_schema",
            "semantic_corpus",
            "b03_deferrals",
        },
        "registry.semantic_closure_evaluation",
    )
    if (
        checked["schema"] != CLOSURE_EVALUATION_SCHEMA
        or checked["state"] != "CLOSED"
        or checked["decision_set_sha256"] != decision_set["sha256"]
    ):
        fail("registry semantic closure is not CLOSED for the exact decision set")
    if (
        checked["source"] != semantic_closure["source"]
        or checked["json_schema"] != semantic_closure["json_schema"]
    ):
        fail("registry semantic closure identities differ from the decision set")
    for name, expected_path in (
        ("source", CLOSURE_SOURCE_RELATIVE),
        ("json_schema", CLOSURE_SCHEMA_RELATIVE),
    ):
        content = source_files.get(expected_path)
        if content is None:
            fail(f"semantic closure {name} is absent from the source cut")
        validate_file_identity(
            checked[name],
            f"registry.semantic_closure_evaluation.{name}",
            expected_path=expected_path,
            content=content,
        )
    corpus = exact_keys(
        checked["semantic_corpus"],
        {
            "required_path",
            "required_status",
            "observed_status",
            "observed_identity",
            "case_count",
            "mutation_count",
        },
        "registry.semantic_closure_evaluation.semantic_corpus",
    )
    if (
        corpus["required_path"] != SEMANTIC_CORPUS_RELATIVE
        or corpus["required_status"] != "COMPLETE_CURRENT"
        or corpus["observed_status"] != "COMPLETE_CURRENT"
    ):
        fail("registry semantic corpus is not the required COMPLETE_CURRENT corpus")
    corpus_content = source_files.get(SEMANTIC_CORPUS_RELATIVE)
    if corpus_content is None:
        fail("semantic closure corpus is absent from the source cut")
    validate_file_identity(
        corpus["observed_identity"],
        "registry.semantic_closure_evaluation.semantic_corpus.observed_identity",
        expected_path=SEMANTIC_CORPUS_RELATIVE,
        content=corpus_content,
    )
    case_count, mutation_count = semantic_corpus_counts(corpus_content)
    if corpus["case_count"] != case_count or corpus["mutation_count"] != mutation_count:
        fail("registry semantic corpus counts differ from the bound corpus bytes")
    deferrals = exact_keys(
        checked["b03_deferrals"],
        {"required_question_count", "validated_question_count", "observed_status"},
        "registry.semantic_closure_evaluation.b03_deferrals",
    )
    closure_content = source_files[CLOSURE_SOURCE_RELATIVE]
    required_count, validated_count = deferred_b03_counts(closure_content)
    if (
        deferrals["required_question_count"] != required_count
        or deferrals["validated_question_count"] != validated_count
        or deferrals["observed_status"] != "COMPLETE_ENVELOPES_VERIFIED"
    ):
        fail("registry B03 deferral counts differ from the bound closure source")
    return checked


def validate_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    packet_commit = validate_hex(snapshot["packet_commit"], HEX40, "packet commit")
    packet_tree = validate_hex(snapshot["packet_tree"], HEX40, "packet tree")
    authorized_ref = validate_authorized_ref(
        snapshot["authorized_ref"], "authorized ref"
    )
    authorized_commit = validate_hex(
        snapshot["authorized_commit"], HEX40, "authorized ref commit"
    )
    authorized_tree = validate_hex(
        snapshot["authorized_tree"], HEX40, "authorized ref tree"
    )
    local_main_commit = validate_hex(
        snapshot["local_main_commit"], HEX40, "local main ref commit"
    )
    local_main_tree = validate_hex(
        snapshot["local_main_tree"], HEX40, "local main ref tree"
    )
    remote_observed_commit = validate_hex(
        snapshot["remote_observed_commit"],
        HEX40,
        "canonical remote main commit",
    )
    validate_remote_ref_join(
        remote_observed_commit,
        authorized_commit,
        local_main_commit,
    )
    if authorized_tree != local_main_tree:
        fail("local origin/main and local main resolve to different trees")
    issuance_commit = validate_hex(
        snapshot["issuance_commit"], HEX40, "retained issuance commit"
    )
    issuance_tree = validate_hex(
        snapshot["issuance_tree"], HEX40, "retained issuance tree"
    )
    retained_tool_identity = validate_generator_source_identities(
        snapshot.get("issuance_tool_identity"),
        "snapshot.issuance_tool_identity",
    )
    reopened_tool_identity = current_tool_identity(issuance_commit, root=ROOT)
    if retained_tool_identity != reopened_tool_identity:
        fail(
            "snapshot issuance generator sources differ from the literal issuance blobs"
        )
    registry = snapshot["registry"]
    packet_content = snapshot["packet_content"]
    source = snapshot["source"]
    source_files = snapshot["source_files"]

    if (
        parse_json_bytes(snapshot["registry_content"], "snapshot registry bytes")
        != registry
    ):
        fail("snapshot registry object differs from its exact retained bytes")
    if parse_json_bytes(snapshot["source_content"], "snapshot source bytes") != source:
        fail("snapshot source object differs from its exact retained bytes")
    if (
        parse_json_bytes(
            snapshot["authorized_registry_content"],
            "authorized-ref registry bytes",
        )
        != snapshot["authorized_registry"]
    ):
        fail("authorized-ref registry object differs from its exact retained bytes")
    if (
        parse_json_bytes(
            snapshot["issuance_registry_content"],
            "retained issuance registry bytes",
        )
        != snapshot["issuance_registry"]
    ):
        fail("retained issuance registry object differs from its exact retained bytes")

    registry = validate_registry_authority_semantics(registry, "registry")

    packet_identity = validate_file_identity(
        registry.get("review_packet"),
        "registry.review_packet",
        expected_path=PACKET_RELATIVE,
        content=packet_content,
    )
    lifecycle = registry.get("review_packet_lifecycle")
    exact_keys(lifecycle, {"schema", "state"}, "registry.review_packet_lifecycle")
    if lifecycle != {"schema": PACKET_LIFECYCLE_SCHEMA, "state": "CURRENT"}:
        fail("review packet lifecycle must be CURRENT")
    packet_subject = registry.get("review_packet_subject")
    exact_keys(
        packet_subject,
        {
            "schema",
            "state",
            "normative",
            "claim_boundary",
            "promotion_blocked",
            "decision_set",
            "review_policy",
            "source",
            "decisions",
        },
        "registry.review_packet_subject",
    )
    if (
        packet_subject["schema"] != REVIEW_SUBJECT_SCHEMA
        or packet_subject["state"] != "CURRENT"
        or packet_subject["normative"] is not False
        or packet_subject["promotion_blocked"] is not True
    ):
        fail("review packet subject is not the current non-normative subject")
    if packet_subject["claim_boundary"] != REGISTRY_CLAIM_BOUNDARY:
        fail("review packet subject claim_boundary is not the accepted boundary")
    validate_review_policy_semantics(
        packet_subject["review_policy"], "registry.review_packet_subject.review_policy"
    )

    packet_fences = extract_json_fences(packet_content)
    packet_lifecycles = [
        value
        for value in packet_fences
        if value.get("schema") == PACKET_LIFECYCLE_SCHEMA
    ]
    packet_subjects = [
        value for value in packet_fences if value.get("schema") == REVIEW_SUBJECT_SCHEMA
    ]
    if packet_lifecycles != [lifecycle] or packet_subjects != [packet_subject]:
        fail("packet JSON blocks differ from the generated registry")

    source_binding = exact_keys(
        packet_subject["source"],
        {"commit", "tree", "decision_source"},
        "packet subject source",
    )
    source_commit = validate_hex(
        source_binding["commit"], HEX40, "packet subject source.commit"
    )
    source_tree = validate_hex(
        source_binding["tree"], HEX40, "packet subject source.tree"
    )
    if (
        source_commit != snapshot["source_commit"]
        or source_tree != snapshot["source_tree"]
    ):
        fail("packet source commit or tree differs from the resolved immutable cut")
    source_content = snapshot["source_content"]
    validate_file_identity(
        source_binding["decision_source"],
        "packet subject source.decision_source",
        expected_path=SOURCE_RELATIVE,
        content=source_content,
    )
    validate_file_identity(
        registry["source"],
        "registry.source",
        expected_path=SOURCE_RELATIVE,
        content=source_content,
    )
    source = validate_source_authority_semantics(source, "packet source")
    if (
        source["candidate"] != registry["candidate"]
        or source["wire_version"] != registry["wire_version"]
    ):
        fail("packet decision source identity is inconsistent")

    decision_set = packet_subject["decision_set"]
    exact_keys(
        decision_set,
        {"schema", "digest_algorithm", "domain_hex", "sha256", "semantic_closure"},
        "packet subject decision_set",
    )
    if (
        decision_set["schema"] != DECISION_SET_SCHEMA
        or decision_set["digest_algorithm"] != DECISION_SET_DIGEST_ALGORITHM
        or decision_set["domain_hex"] != DECISION_SET_DOMAIN.hex()
    ):
        fail("packet decision-set digest contract is invalid")
    if decision_set != registry.get("decision_set"):
        fail("packet and generated registry decision sets differ")
    if packet_subject["review_policy"] != registry.get("review_policy"):
        fail("packet and generated registry review policies differ")
    validate_review_policy_semantics(
        registry["review_policy"], "registry.review_policy"
    )

    closure_evaluation = validate_semantic_closure_evaluation(
        decision_set,
        registry["semantic_closure_evaluation"],
        source_files,
    )

    bound_identities = [
        packet_subject["review_policy"].get("generator"),
        packet_subject["review_policy"].get("output_json_schema"),
        decision_set["semantic_closure"].get("source"),
        decision_set["semantic_closure"].get("json_schema"),
    ]
    for index, identity in enumerate(bound_identities):
        if not isinstance(identity, dict):
            fail(f"packet bound file identity {index} must be an object")
        relative = relative_path(
            identity.get("path"), f"packet bound file {index}.path"
        )
        content = source_files.get(relative)
        if content is None:
            fail(f"packet bound file {relative} is absent from the source cut")
        validate_file_identity(
            identity,
            f"packet bound file {index}",
            expected_path=relative,
            content=content,
        )

    packet_decisions = packet_subject["decisions"]
    source_decisions = source.get("decisions")
    registry_decisions = registry.get("decisions")
    rosters = (packet_decisions, source_decisions, registry_decisions)
    if not all(isinstance(items, list) for items in rosters):
        fail("decision rosters must be arrays")
    if any(len(items) != len(EXPECTED_IDS) for items in rosters):
        fail(
            "packet, source, and registry rosters must each contain "
            "exactly 11 decisions"
        )

    checked_decisions: list[dict[str, Any]] = []
    source_projection_fields = {
        "id",
        "title",
        "path",
        "module_paths",
        "required_reviews",
        "defect_ids",
    }
    packet_projection_fields = source_projection_fields | {
        "content_sha256",
        "bytes",
        "source_set",
    }
    for index, expected_id in enumerate(EXPECTED_IDS):
        decision = validate_decision(
            packet_decisions[index],
            f"packet decisions[{index}]",
            expected_id=expected_id,
            source_files=source_files,
        )
        checked_decisions.append(decision)
        source_decision = source_decisions[index]
        exact_keys(
            source_decision, source_projection_fields, f"source decisions[{index}]"
        )
        if source_decision != {key: decision[key] for key in source_projection_fields}:
            fail(f"source decision {expected_id} differs from the packet")
        registry_decision = exact_keys(
            registry_decisions[index],
            packet_projection_fields | {"status", "acceptance_blockers"},
            f"registry decisions[{index}]",
        )
        if registry_decision.get("status") != "PROPOSED":
            fail(f"registry decision {expected_id} must remain PROPOSED")
        validate_acceptance_blockers(
            registry_decision["acceptance_blockers"],
            decision["required_reviews"],
            f"registry decisions[{index}].acceptance_blockers",
        )
        if {
            key: registry_decision.get(key) for key in packet_projection_fields
        } != decision:
            fail(f"registry decision {expected_id} differs from the packet")

    projection = {
        "schema": DECISION_SET_SCHEMA,
        "candidate": registry["candidate"],
        "wire_version": registry["wire_version"],
        "review_policy": packet_subject["review_policy"],
        "semantic_closure": decision_set["semantic_closure"],
        "decisions": checked_decisions,
    }
    expected_set_digest = domain_digest(DECISION_SET_DOMAIN, projection)
    if (
        validate_hex(decision_set["sha256"], HEX64, "decision_set.sha256")
        != expected_set_digest
    ):
        fail("decision-set SHA-256 differs from the canonical projection")

    counts = calculate_counts(checked_decisions)
    if counts != EXPECTED_COUNTS:
        fail(f"review burden differs from the exact current counts: {counts}")

    authorized_registry = validate_registry_authority_semantics(
        snapshot["authorized_registry"], "authorized-ref registry"
    )
    authorized_packet_content = snapshot["authorized_packet_content"]
    if authorized_packet_content != packet_content:
        fail("authorized ref does not retain the exact CURRENT review packet bytes")
    validate_file_identity(
        authorized_registry["review_packet"],
        "authorized-ref registry.review_packet",
        expected_path=PACKET_RELATIVE,
        content=packet_content,
    )
    if authorized_registry["review_packet_lifecycle"] != lifecycle:
        fail("authorized ref does not retain the CURRENT packet lifecycle")
    if authorized_registry["review_packet_subject"] != packet_subject:
        fail("authorized ref review subject drifted from the immutable packet subject")
    if authorized_registry["decision_set"] != decision_set:
        fail("authorized ref decision set drifted from the immutable packet")
    if authorized_registry["review_policy"] != registry["review_policy"]:
        fail("authorized ref review policy drifted from the immutable packet")
    if authorized_registry["source"] != registry["source"]:
        fail("authorized ref source binding drifted from the immutable packet")
    if authorized_registry["semantic_closure_evaluation"] != closure_evaluation:
        fail("authorized ref semantic closure drifted from the immutable packet")
    if authorized_registry["decisions"] != registry_decisions:
        fail("authorized ref decision roster drifted from the immutable packet")

    issuance_registry = validate_registry_authority_semantics(
        snapshot["issuance_registry"], "retained issuance registry"
    )
    if snapshot["issuance_packet_content"] != packet_content:
        fail("retained issuance cut does not contain the exact CURRENT packet bytes")
    validate_file_identity(
        issuance_registry["review_packet"],
        "retained issuance registry.review_packet",
        expected_path=PACKET_RELATIVE,
        content=packet_content,
    )
    if issuance_registry["review_packet_lifecycle"] != lifecycle:
        fail("retained issuance cut does not contain the CURRENT packet lifecycle")
    if issuance_registry["review_packet_subject"] != packet_subject:
        fail("retained issuance subject drifted from the immutable packet subject")
    if issuance_registry["decision_set"] != decision_set:
        fail("retained issuance decision set drifted from the immutable packet")
    if issuance_registry["review_policy"] != registry["review_policy"]:
        fail("retained issuance policy drifted from the immutable packet")
    if issuance_registry["source"] != registry["source"]:
        fail("retained issuance source binding drifted from the immutable packet")
    if issuance_registry["semantic_closure_evaluation"] != closure_evaluation:
        fail("retained issuance semantic closure drifted from the immutable packet")
    if issuance_registry["decisions"] != registry_decisions:
        fail("retained issuance decision roster drifted from the immutable packet")

    return {
        "packet_commit": packet_commit,
        "packet_tree": packet_tree,
        "packet_identity": packet_identity,
        "registry_identity": file_identity(
            REGISTRY_RELATIVE, snapshot["registry_content"]
        ),
        "source_commit": source_commit,
        "source_tree": source_tree,
        "decision_set_sha256": decision_set["sha256"],
        "decisions": checked_decisions,
        "authorized_ref": authorized_ref,
        "authorized_commit": authorized_commit,
        "authorized_tree": authorized_tree,
        "local_main_commit": local_main_commit,
        "local_main_tree": local_main_tree,
        "remote_observed_commit": remote_observed_commit,
        "issuance_commit": issuance_commit,
        "issuance_tree": issuance_tree,
        "tool_identity": reopened_tool_identity,
    }


def calculate_counts(decisions: list[dict[str, Any]]) -> dict[str, int]:
    obligations = [
        requirement
        for decision in decisions
        for requirement in decision["required_reviews"]
    ]
    slots = sum(requirement["min_distinct_identities"] for requirement in obligations)
    independent = [
        requirement
        for requirement in obligations
        if requirement["requires_independence"]
    ]
    independent_slots = sum(
        requirement["min_distinct_identities"] for requirement in independent
    )
    return {
        "decisions": len(decisions),
        "role_obligations": len(obligations),
        "minimum_identity_slots": slots,
        "independent_obligations": len(independent),
        "minimum_independent_identity_slots": independent_slots,
        "minimum_evidence_requirements": slots * 2 + independent_slots,
    }


def review_subject(
    decision: dict[str, Any], validated: dict[str, Any]
) -> dict[str, Any]:
    return {
        "decision_set_sha256": validated["decision_set_sha256"],
        "adr_content_sha256": decision["content_sha256"],
        "adr_bytes": decision["bytes"],
        "adr_source_set": copy.deepcopy(decision["source_set"]),
        "source_commit": validated["source_commit"],
        "source_tree": validated["source_tree"],
        "review_packet_sha256": validated["packet_identity"]["sha256"],
    }


def derive_roster(
    validated: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    decisions = validated["decisions"]
    if (
        not isinstance(decisions, list)
        or len(decisions) != len(EXPECTED_IDS)
        or [decision.get("id") for decision in decisions] != list(EXPECTED_IDS)
    ):
        fail("validated request roster must retain ordered ADR-001 through ADR-011")
    slots: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    kind_suffixes = {
        "ROLE_AUTHORIZATION": "role-authorization",
        "EXTERNAL_REVIEW_RECEIPT": "external-review-receipt",
        "INDEPENDENCE_ASSESSMENT": "independence-assessment",
    }
    for decision in decisions:
        decision_slug = decision["id"].lower()
        subject = review_subject(decision, validated)
        for requirement in decision["required_reviews"]:
            group_id = f"{decision_slug}.{requirement['role_id']}"
            for ordinal in range(1, requirement["min_distinct_identities"] + 1):
                slot_id = f"{group_id}.{ordinal:02d}"
                required_kinds = [
                    "ROLE_AUTHORIZATION",
                    "EXTERNAL_REVIEW_RECEIPT",
                ]
                if requirement["requires_independence"]:
                    required_kinds.append("INDEPENDENCE_ASSESSMENT")
                requirement_ids = [
                    f"{slot_id}.{kind_suffixes[kind]}" for kind in required_kinds
                ]
                slots.append(
                    {
                        "slot_id": slot_id,
                        "distinct_identity_group": group_id,
                        "identity_ordinal": ordinal,
                        "adr_id": decision["id"],
                        "role_id": requirement["role_id"],
                        "role_label": requirement["label"],
                        "requires_independence": requirement["requires_independence"],
                        "state": "UNFILLED",
                        "subject": copy.deepcopy(subject),
                        "required_evidence_ids": requirement_ids,
                    }
                )
                for kind, requirement_id in zip(
                    required_kinds, requirement_ids, strict=True
                ):
                    evidence.append(
                        {
                            "evidence_requirement_id": requirement_id,
                            "review_slot_id": slot_id,
                            "kind": kind,
                            "exclusive": True,
                            "required_path_prefix": EVIDENCE_PREFIX,
                            "state": "UNFILLED",
                        }
                    )
    return slots, evidence


def expected_remote_observation(
    authorized_ref: str,
    retained_observed_commit: str,
) -> dict[str, Any]:
    return {
        "state": REMOTE_OBSERVATION_STATE,
        "authorizing": False,
        "claim_boundary": REMOTE_OBSERVATION_CLAIM_BOUNDARY,
        "repository": CANONICAL_REPOSITORY,
        "configured_remote": REMOTE_NAME,
        "queried_url": CANONICAL_SSH_URL,
        "queried_ref": REMOTE_QUERY_REF,
        "transport_profile": REMOTE_TRANSPORT_PROFILE,
        "host_key_line_sha256": GITHUB_ED25519_KNOWN_HOST_SHA256,
        "host_key_fingerprint": GITHUB_ED25519_FINGERPRINT,
        "local_tracking_ref": authorized_ref,
        "local_main_ref": LOCAL_MAIN_REF,
        "retained_observed_commit": retained_observed_commit,
        "policy": REMOTE_OBSERVATION_POLICY,
    }


def validate_remote_observation_identity(
    value: Any,
    *,
    authorized_ref: str,
    retained_observed_commit: str,
    path: str,
) -> dict[str, Any]:
    observation = exact_keys(
        value,
        {
            "state",
            "authorizing",
            "claim_boundary",
            "repository",
            "configured_remote",
            "queried_url",
            "queried_ref",
            "transport_profile",
            "host_key_line_sha256",
            "host_key_fingerprint",
            "local_tracking_ref",
            "local_main_ref",
            "retained_observed_commit",
            "policy",
        },
        path,
    )
    validate_hex(
        observation["retained_observed_commit"],
        HEX40,
        f"{path}.retained_observed_commit",
    )
    expected = expected_remote_observation(
        authorized_ref,
        retained_observed_commit,
    )
    if observation != expected:
        fail(f"{path} differs from the non-authorizing issuance observation")
    return observation


def expected_subject_cut(validated: dict[str, Any]) -> dict[str, Any]:
    return {
        "packet_commit": validated["packet_commit"],
        "packet_tree": validated["packet_tree"],
        "review_packet": validated["packet_identity"],
        "proposed_registry": validated["registry_identity"],
        "decision_set_sha256": validated["decision_set_sha256"],
        "zero_review_source_commit": validated["source_commit"],
        "zero_review_source_tree": validated["source_tree"],
        "issuance_currentness": {
            "authorized_ref": validated["authorized_ref"],
            "policy": AUTHORIZED_REF_POLICY,
            "resolved_commit": validated["issuance_commit"],
            "resolved_tree": validated["issuance_tree"],
            "remote_observation": expected_remote_observation(
                validated["authorized_ref"],
                validated["issuance_commit"],
            ),
        },
    }


def expected_human_response_contract() -> dict[str, Any]:
    return {
        "source_record_fields": list(SOURCE_RECORD_FIELDS),
        "evidence_reference_fields": list(EVIDENCE_REFERENCE_FIELDS),
        "decision_population": DECISION_POPULATION,
        "evidence_population": EVIDENCE_POPULATION,
        "conditional_or_superseding_evidence": "ADDITIONAL_AND_NOT_PREALLOCATED",
    }


def build_request(
    snapshot: dict[str, Any], tool_identity: list[dict[str, Any]]
) -> dict[str, Any]:
    validated = validate_snapshot(snapshot)
    if tool_identity != validated["tool_identity"]:
        fail("request generator identity differs from the issuance source blobs")
    slots, evidence = derive_roster(validated)
    request = {
        "schema": REQUEST_SCHEMA,
        "normative": False,
        "authorizing": False,
        "claim_boundary": REQUEST_CLAIM_BOUNDARY,
        "generated_by": tool_identity,
        "subject_cut": expected_subject_cut(validated),
        "counts": copy.deepcopy(EXPECTED_COUNTS),
        "ordering": (
            "PACKET_DECISION_ORDER_THEN_REQUIRED_REVIEW_ORDER_THEN_"
            "ONE_BASED_IDENTITY_ORDINAL"
        ),
        "minimum_only": True,
        "human_response_contract": expected_human_response_contract(),
        "review_slots": slots,
        "evidence_requirements": evidence,
    }
    validate_request(request, validated=validated, tool_identity=tool_identity)
    return request


def validate_request(
    value: Any,
    *,
    validated: dict[str, Any],
    tool_identity: list[dict[str, Any]],
) -> dict[str, Any]:
    request = exact_keys(
        value,
        {
            "schema",
            "normative",
            "authorizing",
            "claim_boundary",
            "generated_by",
            "subject_cut",
            "counts",
            "ordering",
            "minimum_only",
            "human_response_contract",
            "review_slots",
            "evidence_requirements",
        },
        "request",
    )
    if (
        request["schema"] != REQUEST_SCHEMA
        or request["normative"] is not False
        or request["authorizing"] is not False
        or request["claim_boundary"] != REQUEST_CLAIM_BOUNDARY
        or request["minimum_only"] is not True
    ):
        fail("request claim or authority boundary is invalid")
    validate_generator_source_identities(
        request["generated_by"], "request.generated_by"
    )
    if request["generated_by"] != tool_identity:
        fail("request.generated_by differs from the exact issuing source bytes")
    subject_cut = exact_keys(
        request["subject_cut"],
        {
            "packet_commit",
            "packet_tree",
            "review_packet",
            "proposed_registry",
            "decision_set_sha256",
            "zero_review_source_commit",
            "zero_review_source_tree",
            "issuance_currentness",
        },
        "request.subject_cut",
    )
    for field in (
        "packet_commit",
        "packet_tree",
        "zero_review_source_commit",
        "zero_review_source_tree",
    ):
        validate_hex(subject_cut[field], HEX40, f"request.subject_cut.{field}")
    validate_hex(
        subject_cut["decision_set_sha256"],
        HEX64,
        "request.subject_cut.decision_set_sha256",
    )
    validate_file_identity_shape(subject_cut["review_packet"], "subject review packet")
    validate_file_identity_shape(subject_cut["proposed_registry"], "subject registry")
    if subject_cut["review_packet"]["path"] != PACKET_RELATIVE:
        fail("request subject identifies the wrong review packet")
    if subject_cut["proposed_registry"]["path"] != REGISTRY_RELATIVE:
        fail("request subject identifies the wrong proposed registry")
    issuance = exact_keys(
        subject_cut["issuance_currentness"],
        {
            "authorized_ref",
            "policy",
            "resolved_commit",
            "resolved_tree",
            "remote_observation",
        },
        "request.subject_cut.issuance_currentness",
    )
    checked_authorized_ref = validate_authorized_ref(
        issuance["authorized_ref"],
        "request.subject_cut.issuance_currentness.authorized_ref",
    )
    if issuance["policy"] != AUTHORIZED_REF_POLICY:
        fail("request issuance currentness policy is invalid")
    validate_hex(
        issuance["resolved_commit"],
        HEX40,
        "request.subject_cut.issuance_currentness.resolved_commit",
    )
    validate_hex(
        issuance["resolved_tree"],
        HEX40,
        "request.subject_cut.issuance_currentness.resolved_tree",
    )
    validate_remote_observation_identity(
        issuance["remote_observation"],
        authorized_ref=checked_authorized_ref,
        retained_observed_commit=issuance["resolved_commit"],
        path="request.subject_cut.issuance_currentness.remote_observation",
    )
    if subject_cut != expected_subject_cut(validated):
        fail("request subject_cut differs from the exact validated issuance cut")
    if request["counts"] != EXPECTED_COUNTS:
        fail("request counts differ from the exact current burden")
    if request["ordering"] != (
        "PACKET_DECISION_ORDER_THEN_REQUIRED_REVIEW_ORDER_THEN_"
        "ONE_BASED_IDENTITY_ORDINAL"
    ):
        fail("request ordering contract is invalid")
    response_contract = exact_keys(
        request["human_response_contract"],
        {
            "source_record_fields",
            "evidence_reference_fields",
            "decision_population",
            "evidence_population",
            "conditional_or_superseding_evidence",
        },
        "request.human_response_contract",
    )
    if response_contract != expected_human_response_contract():
        fail("human response contract is invalid")

    slots = request["review_slots"]
    evidence = request["evidence_requirements"]
    if (
        not isinstance(slots, list)
        or len(slots) != EXPECTED_COUNTS["minimum_identity_slots"]
    ):
        fail("request does not contain exactly 53 review slots")
    if (
        not isinstance(evidence, list)
        or len(evidence) != EXPECTED_COUNTS["minimum_evidence_requirements"]
    ):
        fail("request does not contain exactly 112 evidence requirements")
    forbidden_slot_keys = {
        "review_id",
        "reviewer",
        "decision",
        "conditions",
        "role_authorization",
        "independence_assessment",
        "external_receipt",
        "timestamp_utc",
        "supersedes",
    }
    slot_ids: list[str] = []
    slot_evidence_ids: list[str] = []
    independent_slots = 0
    group_identities: dict[str, list[int]] = {}
    for index, slot in enumerate(slots):
        path = f"request.review_slots[{index}]"
        slot = exact_keys(
            slot,
            {
                "slot_id",
                "distinct_identity_group",
                "identity_ordinal",
                "adr_id",
                "role_id",
                "role_label",
                "requires_independence",
                "state",
                "subject",
                "required_evidence_ids",
            },
            path,
        )
        if forbidden_slot_keys.intersection(slot):
            fail(f"{path} contains a human response field")
        slot_id = bounded_string(slot["slot_id"], f"{path}.slot_id", maximum=160)
        if not SLOT_ID.fullmatch(slot_id):
            fail(f"{path}.slot_id is invalid")
        role_id = bounded_string(slot["role_id"], f"{path}.role_id", maximum=64)
        if not ROLE_ID.fullmatch(role_id):
            fail(f"{path}.role_id is invalid")
        expected_group = f"{slot['adr_id'].lower()}.{role_id}"
        if slot["distinct_identity_group"] != expected_group:
            fail(f"{path}.distinct_identity_group is invalid")
        ordinal = bounded_integer(
            slot["identity_ordinal"],
            f"{path}.identity_ordinal",
            minimum=1,
            maximum=8,
        )
        group_identities.setdefault(expected_group, []).append(ordinal)
        if slot["state"] != "UNFILLED":
            fail(f"{path}.state must be UNFILLED")
        if not isinstance(slot["requires_independence"], bool):
            fail(f"{path}.requires_independence must be boolean")
        independent_slots += int(slot["requires_independence"])
        validate_review_subject_shape(slot["subject"], f"{path}.subject")
        required = slot["required_evidence_ids"]
        expected_length = 3 if slot["requires_independence"] else 2
        if not isinstance(required, list) or len(required) != expected_length:
            fail(f"{path}.required_evidence_ids has the wrong cardinality")
        for evidence_id in required:
            if not isinstance(evidence_id, str) or not EVIDENCE_ID.fullmatch(
                evidence_id
            ):
                fail(f"{path}.required_evidence_ids contains an invalid ID")
        slot_ids.append(slot_id)
        slot_evidence_ids.extend(required)
    if len(slot_ids) != len(set(slot_ids)):
        fail("request review slots contain duplicate IDs")
    if independent_slots != EXPECTED_COUNTS["minimum_independent_identity_slots"]:
        fail("request contains the wrong independent-slot count")
    for group, ordinals in group_identities.items():
        if ordinals != list(range(1, len(ordinals) + 1)):
            fail(f"request identity ordinals are noncanonical for {group}")

    evidence_ids: list[str] = []
    slot_id_set = set(slot_ids)
    kinds: dict[str, int] = {kind: 0 for kind in EVIDENCE_KINDS}
    kind_suffixes = {
        "ROLE_AUTHORIZATION": "role-authorization",
        "EXTERNAL_REVIEW_RECEIPT": "external-review-receipt",
        "INDEPENDENCE_ASSESSMENT": "independence-assessment",
    }
    for index, requirement in enumerate(evidence):
        path = f"request.evidence_requirements[{index}]"
        requirement = exact_keys(
            requirement,
            {
                "evidence_requirement_id",
                "review_slot_id",
                "kind",
                "exclusive",
                "required_path_prefix",
                "state",
            },
            path,
        )
        evidence_id = bounded_string(
            requirement["evidence_requirement_id"],
            f"{path}.evidence_requirement_id",
            maximum=192,
        )
        if not EVIDENCE_ID.fullmatch(evidence_id):
            fail(f"{path}.evidence_requirement_id is invalid")
        slot_id = bounded_string(
            requirement["review_slot_id"], f"{path}.review_slot_id", maximum=160
        )
        if slot_id not in slot_id_set:
            fail(f"{path}.review_slot_id is unknown")
        kind = requirement["kind"]
        if kind not in kinds:
            fail(f"{path}.kind is invalid")
        kinds[kind] += 1
        if requirement["exclusive"] is not True:
            fail(f"{path}.exclusive must be true")
        if requirement["required_path_prefix"] != EVIDENCE_PREFIX:
            fail(f"{path}.required_path_prefix is invalid")
        if requirement["state"] != "UNFILLED":
            fail(f"{path}.state must be UNFILLED")
        expected_evidence_id = f"{slot_id}.{kind_suffixes[kind]}"
        if evidence_id != expected_evidence_id:
            fail(f"{path}.evidence_requirement_id differs from its slot and kind")
        evidence_ids.append(evidence_id)
    if len(evidence_ids) != len(set(evidence_ids)):
        fail("request evidence requirements contain duplicate IDs")
    if evidence_ids != slot_evidence_ids:
        fail("request evidence requirements differ from the slot projections")
    if kinds != {
        "ROLE_AUTHORIZATION": 53,
        "EXTERNAL_REVIEW_RECEIPT": 53,
        "INDEPENDENCE_ASSESSMENT": 6,
    }:
        fail(f"request evidence-kind counts are invalid: {kinds}")
    expected_slots, expected_evidence = derive_roster(validated)
    if slots != expected_slots:
        fail("request review slots differ from the frozen 11-decision roster")
    if evidence != expected_evidence:
        fail("request evidence rows differ from the frozen 11-decision roster")
    return request


def validate_file_identity_shape(value: Any, path: str) -> None:
    identity = exact_keys(value, {"path", "sha256", "bytes"}, path)
    relative_path(identity["path"], f"{path}.path")
    validate_hex(identity["sha256"], HEX64, f"{path}.sha256")
    bounded_integer(
        identity["bytes"], f"{path}.bytes", minimum=1, maximum=MAX_SOURCE_FILE_BYTES
    )


def validate_generator_source_identities(
    value: Any,
    path: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) != len(GENERATOR_SOURCE_RELATIVES):
        fail(f"{path} must contain the exact ordered generator sources")
    for index, (identity, expected_path) in enumerate(
        zip(value, GENERATOR_SOURCE_RELATIVES, strict=True)
    ):
        validate_file_identity_shape(identity, f"{path}[{index}]")
        if identity["path"] != expected_path:
            fail(f"{path} identifies the wrong ordered generator source")
    return value


def validate_review_subject_shape(value: Any, path: str) -> None:
    subject = exact_keys(
        value,
        {
            "decision_set_sha256",
            "adr_content_sha256",
            "adr_bytes",
            "adr_source_set",
            "source_commit",
            "source_tree",
            "review_packet_sha256",
        },
        path,
    )
    for field in (
        "decision_set_sha256",
        "adr_content_sha256",
        "review_packet_sha256",
    ):
        validate_hex(subject[field], HEX64, f"{path}.{field}")
    for field in ("source_commit", "source_tree"):
        validate_hex(subject[field], HEX40, f"{path}.{field}")
    bounded_integer(
        subject["adr_bytes"], f"{path}.adr_bytes", minimum=1, maximum=262_144
    )
    if not isinstance(subject["adr_source_set"], dict):
        fail(f"{path}.adr_source_set must be an object")


def git_environment() -> dict[str, str]:
    return immutable_git_environment()


def remote_git_environment() -> dict[str, str]:
    environment = git_environment()
    environment["PATH"] = "/usr/bin:/bin"
    environment["GIT_DIR"] = os.devnull
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment["GCM_INTERACTIVE"] = "Never"
    environment["GIT_SSH_VARIANT"] = "ssh"
    environment["GIT_ALLOW_PROTOCOL"] = "ssh"
    return environment


def trusted_fixed_executable_metadata(mode: int, uid: int) -> bool:
    return bool(stat.S_ISREG(mode) and uid == 0 and mode & 0o022 == 0 and mode & 0o111)


def fixed_executable_identity(path: str, label: str) -> tuple[int, ...]:
    try:
        metadata = os.lstat(path)
    except OSError as error:
        fail(f"cannot inspect {label}: {error}")
    if stat.S_ISLNK(metadata.st_mode) or not trusted_fixed_executable_metadata(
        metadata.st_mode, metadata.st_uid
    ):
        fail(
            f"{label} must be one root-owned executable regular file that is "
            "not writable by group or world"
        )
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def require_fixed_executable_unchanged(
    path: str, expected: tuple[int, ...], label: str
) -> None:
    if fixed_executable_identity(path, label) != expected:
        fail(f"{label} changed during canonical remote observation")


def terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    """Kill one dedicated process group and reap its leader."""

    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError:
        if process.poll() is None:
            process.kill()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def collect_bounded_process(
    process: subprocess.Popen[bytes],
    *,
    stdout_limit: int,
    stderr_limit: int,
    deadline: float,
    label: str,
) -> subprocess.CompletedProcess[bytes]:
    if process.stdout is None or process.stderr is None:
        terminate_process_group(process)
        fail(f"cannot open bounded process streams for {label}")
    selector = selectors.DefaultSelector()
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    limits = {"stdout": stdout_limit, "stderr": stderr_limit}
    streams = {process.stdout.fileno(): "stdout", process.stderr.fileno(): "stderr"}
    for descriptor in streams:
        selector.register(descriptor, selectors.EVENT_READ)
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                terminate_process_group(process)
                fail(f"{label} exceeded its process deadline")
            events = selector.select(remaining)
            if not events:
                terminate_process_group(process)
                fail(f"{label} exceeded its process deadline")
            for key, _mask in events:
                descriptor = key.fd
                name = streams[descriptor]
                allowance = limits[name] - len(buffers[name])
                chunk = os.read(descriptor, min(64 * 1024, allowance + 1))
                if not chunk:
                    selector.unregister(descriptor)
                    continue
                buffers[name].extend(chunk)
                if len(buffers[name]) > limits[name]:
                    terminate_process_group(process)
                    fail(f"{label} {name} exceeds its byte bound")
        remaining = max(0.001, deadline - time.monotonic())
        try:
            return_code = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            terminate_process_group(process)
            fail(f"{label} exceeded its process deadline")
        return subprocess.CompletedProcess(
            process.args,
            return_code,
            stdout=bytes(buffers["stdout"]),
            stderr=bytes(buffers["stderr"]),
        )
    except OSError as error:
        terminate_process_group(process)
        fail(f"cannot collect bounded process bytes for {label}: {error}")
    finally:
        selector.close()


def run_bounded_command(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    timeout_seconds: int,
    stdout_limit: int,
    stderr_limit: int,
    label: str,
) -> subprocess.CompletedProcess[bytes]:
    try:
        process = subprocess.Popen(  # noqa: S603
            command,
            cwd=cwd,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as error:
        fail(f"cannot start {label}: {error}")
    return collect_bounded_process(
        process,
        stdout_limit=stdout_limit,
        stderr_limit=stderr_limit,
        deadline=time.monotonic() + timeout_seconds,
        label=label,
    )


def run_git(arguments: list[str], description: str, *, root: Path = ROOT) -> bytes:
    identity = fixed_executable_identity(GIT_BINARY, "fixed Git executable")
    try:
        result = run_bounded_command(
            [GIT_BINARY, "--no-replace-objects", *arguments],
            cwd=root,
            environment=git_environment(),
            timeout_seconds=REMOTE_TIMEOUT_SECONDS,
            stdout_limit=MAX_LOCAL_GIT_STDOUT_BYTES,
            stderr_limit=MAX_GIT_STDERR_BYTES,
            label=description,
        )
    except BaseException as primary:
        try:
            require_fixed_executable_unchanged(
                GIT_BINARY, identity, "fixed Git executable"
            )
        except RequestError as fence_error:
            primary.add_note(f"fixed Git final fence also failed: {fence_error}")
        raise
    require_fixed_executable_unchanged(GIT_BINARY, identity, "fixed Git executable")
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        fail(f"{description} failed: {detail or 'git returned nonzero'}")
    return result.stdout


def git_metadata_path(relative: str, *, root: Path = ROOT) -> Path:
    """Resolve one fixed Git metadata path without consulting replacement objects."""

    if relative not in {"info/grafts", "objects/info/alternates", "shallow"}:
        fail("unsupported Git metadata path")
    raw = run_git(
        ["rev-parse", "--path-format=absolute", "--git-path", relative],
        f"resolve Git metadata path {relative}",
        root=root,
    )
    if not 1 <= len(raw) <= 4096 or raw.count(b"\n") > 1:
        fail(f"Git metadata path {relative} is malformed")
    try:
        rendered = raw.decode("utf-8").rstrip("\n")
    except UnicodeDecodeError as error:
        fail(f"Git metadata path {relative} is not UTF-8: {error}")
    if not rendered or "\n" in rendered or "\x00" in rendered:
        fail(f"Git metadata path {relative} is malformed")
    return Path(rendered)


def require_unmodified_git_history(*, root: Path = ROOT) -> None:
    """Reject repository-local mechanisms that can rewrite the commit graph."""
    try:
        immutable_require_unmodified_git_history(root=root)
    except ImmutableGitError as error:
        fail(str(error))


def validate_authorized_ref(value: Any, path: str) -> str:
    ref = bounded_string(value, path, maximum=512)
    if not ref.isascii() or ref != ref.strip():
        fail(f"{path} must be canonical printable ASCII")
    if ref != DEFAULT_AUTHORIZED_REF:
        fail(f"{path} must be exactly {DEFAULT_AUTHORIZED_REF}")
    return ref


def validate_origin_url(value: Any, path: str) -> str:
    url = bounded_string(value, path, maximum=512)
    if not url.isascii() or url != url.strip():
        fail(f"{path} must be canonical printable ASCII")
    if url not in CANONICAL_ORIGIN_URLS:
        fail(f"{path} must be canonical sepahead/NCP SSH or credential-free HTTPS")
    return url


def parse_origin_url_output(content: bytes) -> str:
    if not 1 <= len(content) <= MAX_REMOTE_CONFIG_BYTES:
        fail(f"remote {REMOTE_NAME} URL output is outside the byte limit")
    if content.count(b"\n") != 1 or not content.endswith(b"\n") or b"\r" in content:
        fail(f"remote {REMOTE_NAME} must have exactly one LF-terminated fetch URL")
    try:
        value = content[:-1].decode("ascii", errors="strict")
    except UnicodeDecodeError as error:
        fail(f"remote {REMOTE_NAME} URL is not canonical ASCII: {error}")
    if any(byte < 0x20 or byte == 0x7F for byte in content[:-1]):
        fail(f"remote {REMOTE_NAME} URL contains a control byte")
    return validate_origin_url(value, f"remote {REMOTE_NAME} URL")


def read_origin_url() -> str:
    content = run_git(
        ["config", "--local", "--get-all", f"remote.{REMOTE_NAME}.url"],
        f"read {REMOTE_NAME} URL",
    )
    return parse_origin_url_output(content)


def parse_ls_remote_output(content: Any) -> str:
    if not isinstance(content, bytes):
        fail("canonical origin ls-remote response must be bytes")
    if not 1 <= len(content) <= MAX_LS_REMOTE_BYTES:
        fail("canonical origin ls-remote response is outside the byte limit")
    match = re.fullmatch(
        rb"([0-9a-f]{40})\trefs/heads/main\n",
        content,
    )
    if match is None:
        fail("canonical origin ls-remote response is malformed or names the wrong ref")
    return match.group(1).decode("ascii")


def validate_github_host_key_pin() -> None:
    if hashlib.sha256(GITHUB_ED25519_KNOWN_HOST).hexdigest() != (
        GITHUB_ED25519_KNOWN_HOST_SHA256
    ):
        fail("checked GitHub Ed25519 known-host line has a stale digest")
    fields = GITHUB_ED25519_KNOWN_HOST.rstrip(b"\n").split(b" ")
    if len(fields) != 3 or fields[:2] != [b"github.com", b"ssh-ed25519"]:
        fail("checked GitHub Ed25519 known-host line is malformed")
    try:
        key = base64.b64decode(fields[2], validate=True)
    except ValueError as error:
        fail(f"checked GitHub Ed25519 host key is invalid: {error}")
    fingerprint = "SHA256:" + base64.b64encode(hashlib.sha256(key).digest()).decode(
        "ascii"
    ).rstrip("=")
    if fingerprint != GITHUB_ED25519_FINGERPRINT:
        fail("checked GitHub Ed25519 host key has the wrong fingerprint")


def ssh_auth_socket_identity(value: Any = None) -> tuple[str, tuple[int, ...]]:
    candidate = os.environ.get("SSH_AUTH_SOCK") if value is None else value
    path = bounded_string(candidate, "SSH_AUTH_SOCK", maximum=4_096)
    try:
        encoded = path.encode("utf-8")
    except UnicodeEncodeError as error:
        fail(f"SSH_AUTH_SOCK is not UTF-8: {error}")
    if (
        not encoded
        or len(encoded) > 4_096
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in path)
        or not Path(path).is_absolute()
    ):
        fail("SSH_AUTH_SOCK must be one bounded absolute path")
    try:
        metadata = os.lstat(path)
    except OSError as error:
        fail(f"cannot inspect SSH_AUTH_SOCK: {error}")
    if not stat.S_ISSOCK(metadata.st_mode) or metadata.st_uid != os.getuid():
        fail("SSH_AUTH_SOCK must be a current-user Unix socket")
    return path, (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_ctime_ns,
    )


def require_ssh_auth_socket_unchanged(path: str, expected: tuple[int, ...]) -> None:
    current_path, current = ssh_auth_socket_identity(path)
    if current_path != path or current != expected:
        fail("SSH_AUTH_SOCK changed during canonical remote observation")


def github_ssh_arguments(known_hosts_path: str) -> list[str]:
    validate_github_host_key_pin()
    if (
        re.fullmatch(r"/[A-Za-z0-9._/-]+", known_hosts_path) is None
        or "//" in known_hosts_path
        or any(part in {"", ".", ".."} for part in Path(known_hosts_path).parts[1:])
    ):
        fail("owner-private known-hosts path is not shell-safe")
    options = (
        "Hostname=github.com",
        "Port=22",
        "User=git",
        "CanonicalizeHostname=no",
        "BatchMode=yes",
        "StrictHostKeyChecking=yes",
        f"UserKnownHostsFile={known_hosts_path}",
        "GlobalKnownHostsFile=/dev/null",
        "HostKeyAlgorithms=ssh-ed25519",
        "UpdateHostKeys=no",
        "VerifyHostKeyDNS=no",
        "CheckHostIP=no",
        "PreferredAuthentications=publickey",
        "PubkeyAuthentication=yes",
        "HostbasedAuthentication=no",
        "GSSAPIAuthentication=no",
        "PasswordAuthentication=no",
        "KbdInteractiveAuthentication=no",
        "NumberOfPasswordPrompts=0",
        "IdentityFile=none",
        "CertificateFile=none",
        "IdentityAgent=SSH_AUTH_SOCK",
        "IdentitiesOnly=no",
        "AddKeysToAgent=no",
        "ProxyCommand=none",
        "ProxyJump=none",
        "KnownHostsCommand=none",
        "ControlMaster=no",
        "ControlPath=none",
        "ControlPersist=no",
        "ClearAllForwardings=yes",
        "PermitLocalCommand=no",
        "ForwardAgent=no",
        "RequestTTY=no",
        "ConnectionAttempts=1",
        f"ConnectTimeout={REMOTE_TIMEOUT_SECONDS}",
    )
    arguments = [SSH_BINARY, "-F", "/dev/null"]
    for option in options:
        arguments.extend(("-o", option))
    return arguments


def github_ssh_command(known_hosts_path: str) -> str:
    return " ".join(github_ssh_arguments(known_hosts_path))


def validate_effective_ssh_config(
    known_hosts_path: str, environment: dict[str, str]
) -> None:
    arguments = github_ssh_arguments(known_hosts_path)
    command = [arguments[0], "-G", *arguments[1:], "github.com"]
    result = run_bounded_command(
        command,
        cwd=ROOT.parent,
        environment=environment,
        timeout_seconds=REMOTE_TIMEOUT_SECONDS,
        stdout_limit=256 * 1024,
        stderr_limit=MAX_GIT_STDERR_BYTES,
        label="effective pinned SSH configuration",
    )
    if result.returncode != 0 or b"\r" in result.stdout:
        fail("cannot resolve the effective pinned SSH configuration")
    values: dict[str, list[str]] = {}
    for raw_line in result.stdout.splitlines():
        try:
            line = raw_line.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            fail(f"effective SSH configuration is not UTF-8: {error}")
        key, separator, value = line.partition(" ")
        if not separator or not key or not value:
            fail("effective SSH configuration contains a malformed line")
        values.setdefault(key, []).append(value)
    expected = {
        "host": "github.com",
        "hostname": "github.com",
        "port": "22",
        "user": "git",
        "batchmode": "yes",
        "canonicalizehostname": "false",
        "checkhostip": "no",
        "controlmaster": "false",
        "clearallforwardings": "yes",
        "gssapiauthentication": "no",
        "hostbasedauthentication": "no",
        "identitiesonly": "no",
        "kbdinteractiveauthentication": "no",
        "passwordauthentication": "no",
        "permitlocalcommand": "no",
        "proxyusefdpass": "no",
        "pubkeyauthentication": "true",
        "requesttty": "false",
        "stricthostkeychecking": "true",
        "verifyhostkeydns": "false",
        "updatehostkeys": "false",
        "connectionattempts": "1",
        "numberofpasswordprompts": "0",
        "hostkeyalgorithms": "ssh-ed25519",
        "identityagent": "SSH_AUTH_SOCK",
        "preferredauthentications": "publickey",
        "identityfile": "none",
        "certificatefile": "none",
        "globalknownhostsfile": "/dev/null",
        "userknownhostsfile": known_hosts_path,
        "addkeystoagent": "false",
        "forwardagent": "no",
        "connecttimeout": str(REMOTE_TIMEOUT_SECONDS),
        "controlpersist": "no",
    }
    for key, expected_value in expected.items():
        if values.get(key) != [expected_value]:
            fail(f"effective SSH configuration has an unexpected {key} value")
    for forbidden in ("controlpath", "knownhostscommand", "proxycommand", "proxyjump"):
        if forbidden in values:
            fail(f"effective SSH configuration enables forbidden {forbidden}")


def write_private_known_hosts(
    directory: Path,
) -> tuple[Path, tuple[int, ...], tuple[int, ...]]:
    try:
        directory.chmod(0o700)
        directory_metadata = directory.stat()
    except OSError as error:
        fail(f"cannot inspect owner-private SSH directory: {error}")
    if (
        not stat.S_ISDIR(directory_metadata.st_mode)
        or stat.S_IMODE(directory_metadata.st_mode) != 0o700
        or directory_metadata.st_uid != os.getuid()
    ):
        fail("SSH known-hosts directory is not owner-private")
    path = directory / "known_hosts"
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor: int | None = None
    try:
        descriptor = os.open(path, flags, 0o600)
        remaining = memoryview(GITHUB_ED25519_KNOWN_HOST)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                fail("cannot write the complete GitHub known-host line")
            remaining = remaining[written:]
        os.fsync(descriptor)
        metadata = os.fstat(descriptor)
    except OSError as error:
        fail(f"cannot create owner-private GitHub known-hosts file: {error}")
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_uid != os.getuid()
        or metadata.st_size != len(GITHUB_ED25519_KNOWN_HOST)
    ):
        fail("GitHub known-hosts file identity is invalid")
    try:
        sealed_directory = directory.lstat()
    except OSError as error:
        fail(f"cannot seal owner-private SSH directory identity: {error}")
    directory_identity = (
        sealed_directory.st_dev,
        sealed_directory.st_ino,
        sealed_directory.st_mode,
        sealed_directory.st_uid,
        sealed_directory.st_gid,
        sealed_directory.st_mtime_ns,
        sealed_directory.st_ctime_ns,
    )
    return (
        path,
        (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_mode,
            metadata.st_uid,
            metadata.st_gid,
            metadata.st_size,
            metadata.st_mtime_ns,
            metadata.st_ctime_ns,
        ),
        directory_identity,
    )


def require_private_directory_unchanged(path: Path, expected: tuple[int, ...]) -> None:
    try:
        metadata = path.lstat()
    except OSError as error:
        fail(f"cannot reopen owner-private SSH directory: {error}")
    current = (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )
    if current != expected:
        fail("owner-private SSH directory changed during remote observation")


def require_known_hosts_unchanged(path: Path, expected: tuple[int, ...]) -> None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        chunks: list[bytes] = []
        remaining = len(GITHUB_ED25519_KNOWN_HOST) + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        closed = os.fstat(descriptor)
        current_path = path.lstat()
    except OSError as error:
        fail(f"cannot reopen GitHub known-hosts file: {error}")
    finally:
        if descriptor is not None:
            os.close(descriptor)
    identity = lambda value: (  # noqa: E731
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_uid,
        value.st_gid,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )
    if (
        identity(opened) != expected
        or identity(closed) != expected
        or identity(current_path) != expected
        or raw != GITHUB_ED25519_KNOWN_HOST
    ):
        fail("GitHub known-hosts file changed during remote observation")


def query_remote_main(origin_url: str, *, runner: Any | None = None) -> str:
    validate_origin_url(origin_url, f"remote {REMOTE_NAME} URL")
    git_identity = fixed_executable_identity(GIT_BINARY, "fixed Git executable")
    ssh_identity = fixed_executable_identity(SSH_BINARY, "fixed SSH executable")
    command = [
        GIT_BINARY,
        "--no-replace-objects",
        "ls-remote",
        "--exit-code",
        "--refs",
        CANONICAL_SSH_URL,
        REMOTE_QUERY_REF,
    ]
    if runner is not None:
        environment = remote_git_environment()
        environment["SSH_AUTH_SOCK"] = SELF_TEST_AGENT_SOCKET
        environment["GIT_SSH_COMMAND"] = github_ssh_command(SELF_TEST_KNOWN_HOSTS)
        try:
            result = runner(
                command,
                cwd=ROOT.parent,
                env=environment,
                capture_output=True,
                check=False,
                stdin=subprocess.DEVNULL,
                timeout=REMOTE_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            fail(
                "canonical origin ls-remote timed out after "
                f"{REMOTE_TIMEOUT_SECONDS} seconds"
            )
        except OSError as error:
            fail(f"cannot run canonical origin ls-remote: {error}")
    else:
        socket_path, socket_identity = ssh_auth_socket_identity()
        with tempfile.TemporaryDirectory(
            prefix="ncp-b01-ssh-", dir=ROOT.parent
        ) as directory:
            ssh_directory = Path(directory)
            (
                known_hosts,
                known_hosts_identity,
                ssh_directory_identity,
            ) = write_private_known_hosts(ssh_directory)
            environment = remote_git_environment()
            environment["SSH_AUTH_SOCK"] = socket_path
            environment["GIT_SSH_COMMAND"] = github_ssh_command(str(known_hosts))
            try:
                validate_effective_ssh_config(str(known_hosts), environment)
                result = run_bounded_command(
                    command,
                    cwd=ROOT.parent,
                    environment=environment,
                    timeout_seconds=REMOTE_TIMEOUT_SECONDS,
                    stdout_limit=MAX_LS_REMOTE_BYTES,
                    stderr_limit=MAX_GIT_STDERR_BYTES,
                    label="canonical origin ls-remote",
                )
            finally:
                require_ssh_auth_socket_unchanged(socket_path, socket_identity)
                require_known_hosts_unchanged(known_hosts, known_hosts_identity)
                require_private_directory_unchanged(
                    ssh_directory, ssh_directory_identity
                )
    if not isinstance(result, subprocess.CompletedProcess):
        fail("canonical origin ls-remote returned an invalid process result")
    if result.returncode != 0:
        detail = result.stderr
        if not isinstance(detail, bytes):
            fail("canonical origin ls-remote returned an invalid error response")
        rendered = detail[:1_024].decode("utf-8", errors="replace").strip()
        fail(f"canonical origin ls-remote failed: {rendered or 'git returned nonzero'}")
    require_fixed_executable_unchanged(GIT_BINARY, git_identity, "fixed Git executable")
    require_fixed_executable_unchanged(SSH_BINARY, ssh_identity, "fixed SSH executable")
    return parse_ls_remote_output(result.stdout)


def read_git_object(
    value: str,
    expected_type: str,
    *,
    maximum: int,
    label: str,
    root: Path = ROOT,
) -> bytes:
    """Read one bounded raw object and recompute its Git SHA-1 identity."""

    try:
        return immutable_read_object(
            value,
            expected_type,
            maximum=maximum,
            label=label,
            root=root,
        )
    except ImmutableGitError as error:
        fail(str(error))


def read_raw_commit(
    value: str, label: str, *, root: Path = ROOT
) -> tuple[str, list[str]]:
    """Read one raw commit object and return its tree and literal parents."""

    try:
        return immutable_read_commit(value, label=label, root=root)
    except ImmutableGitError as error:
        fail(str(error))


def resolve_commit(value: str, label: str, *, root: Path = ROOT) -> tuple[str, str]:
    commit = validate_hex(value, HEX40, label)
    try:
        tree = immutable_commit_tree(commit, root=root)
    except ImmutableGitError as error:
        fail(str(error))
    return commit, tree


def resolve_authorized_ref(value: str) -> tuple[str, str, str]:
    ref = validate_authorized_ref(value, "authorized ref")
    resolved = (
        run_git(
            ["rev-parse", "--verify", f"{ref}^{{commit}}"],
            f"resolve authorized ref {ref}",
        )
        .decode("ascii")
        .strip()
    )
    commit = validate_hex(resolved, HEX40, "authorized ref commit")
    _commit, tree = resolve_commit(commit, "authorized ref commit")
    return ref, commit, tree


def resolve_local_main() -> tuple[str, str]:
    resolved = (
        run_git(
            ["rev-parse", "--verify", f"{LOCAL_MAIN_REF}^{{commit}}"],
            f"resolve local main ref {LOCAL_MAIN_REF}",
        )
        .decode("ascii")
        .strip()
    )
    commit = validate_hex(resolved, HEX40, "local main ref commit")
    _commit, tree = resolve_commit(commit, "local main ref commit")
    return commit, tree


def resolve_checkout_head(*, root: Path = ROOT) -> tuple[str, str]:
    """Resolve the literal checked-out commit without requiring a local branch."""

    resolved = (
        run_git(
            ["rev-parse", "--verify", "HEAD^{commit}"],
            "resolve checked-out HEAD",
            root=root,
        )
        .decode("ascii")
        .strip()
    )
    commit = validate_hex(resolved, HEX40, "checked-out HEAD commit")
    _commit, tree = resolve_commit(commit, "checked-out HEAD commit", root=root)
    return commit, tree


def require_checkout_head_unchanged(expected_commit: str) -> None:
    current_commit, _current_tree = resolve_checkout_head()
    if current_commit != validate_hex(
        expected_commit, HEX40, "expected checked-out HEAD commit"
    ):
        fail("checked-out HEAD moved during hermetic request validation")


def validate_remote_ref_join(
    observed_commit: Any,
    tracking_commit: Any,
    local_main_commit: Any,
) -> None:
    observed = validate_hex(
        observed_commit,
        HEX40,
        "canonical remote main commit",
    )
    tracking = validate_hex(
        tracking_commit,
        HEX40,
        "local origin/main commit",
    )
    local_main = validate_hex(
        local_main_commit,
        HEX40,
        "local main commit",
    )
    if observed != tracking or observed != local_main:
        fail(
            "canonical remote main, local origin/main, and local main must "
            "resolve to one commit"
        )


def observe_official_main(authorized_ref_value: str) -> dict[str, str]:
    origin_url = read_origin_url()
    observed_commit = query_remote_main(origin_url)
    authorized_ref, authorized_commit, authorized_tree = resolve_authorized_ref(
        authorized_ref_value
    )
    local_main_commit, local_main_tree = resolve_local_main()
    validate_remote_ref_join(
        observed_commit,
        authorized_commit,
        local_main_commit,
    )
    return {
        "authorized_ref": authorized_ref,
        "authorized_commit": authorized_commit,
        "authorized_tree": authorized_tree,
        "local_main_commit": local_main_commit,
        "local_main_tree": local_main_tree,
        "remote_observed_commit": observed_commit,
    }


def require_local_refs_unchanged(expected_commit: str) -> None:
    _ref, tracking_commit, _tracking_tree = resolve_authorized_ref(
        DEFAULT_AUTHORIZED_REF
    )
    local_main_commit, _local_main_tree = resolve_local_main()
    validate_remote_ref_join(expected_commit, tracking_commit, local_main_commit)


def require_official_observation_unchanged(snapshot: dict[str, Any]) -> None:
    current = observe_official_main(snapshot["authorized_ref"])
    expected = {
        "authorized_ref": snapshot["authorized_ref"],
        "authorized_commit": snapshot["authorized_commit"],
        "authorized_tree": snapshot["authorized_tree"],
        "local_main_commit": snapshot["local_main_commit"],
        "local_main_tree": snapshot["local_main_tree"],
        "remote_observed_commit": snapshot["remote_observed_commit"],
    }
    if current != expected:
        fail("canonical remote or local main refs moved during request issuance")


def require_ancestor(
    ancestor: str,
    descendant: str,
    description: str,
    *,
    root: Path = ROOT,
    commit_bound: int = MAX_ANCESTRY_COMMITS,
    edge_bound: int = MAX_ANCESTRY_EDGES,
) -> None:
    """Prove ancestry from literal commit parents, without Git overlays."""

    try:
        immutable_require_ancestor(
            ancestor,
            descendant,
            root=root,
            allow_equal=True,
            label="raw Git ancestry",
            commit_bound=commit_bound,
            edge_bound=edge_bound,
        )
    except ImmutableGitError as error:
        if "does not establish the required ancestry" in str(error):
            fail(description)
        fail(str(error))


def read_raw_tree_entry(
    tree_id: str,
    component: bytes,
    *,
    label: str,
    root: Path = ROOT,
) -> tuple[str, str]:
    """Return one exact raw-tree mode and object ID for a path component."""

    try:
        return immutable_read_tree_entry(
            tree_id,
            component,
            label=label,
            root=root,
        )
    except ImmutableGitError as error:
        fail(str(error))


def read_git_blob(
    commit: str,
    relative: str,
    *,
    maximum: int,
    root: Path = ROOT,
) -> bytes:
    try:
        return blob_snapshot(
            commit,
            relative,
            maximum=maximum,
            root=root,
        ).raw
    except ImmutableGitError as error:
        fail(str(error))


def load_snapshot(
    packet_commit_value: str,
    authorized_ref_value: str,
    *,
    issuance_commit_value: str | None = None,
    live_currentness: bool,
) -> dict[str, Any]:
    with immutable_git_operation(root=ROOT):
        return _load_snapshot(
            packet_commit_value,
            authorized_ref_value,
            issuance_commit_value=issuance_commit_value,
            live_currentness=live_currentness,
        )


def _load_snapshot(
    packet_commit_value: str,
    authorized_ref_value: str,
    *,
    issuance_commit_value: str | None = None,
    live_currentness: bool,
) -> dict[str, Any]:
    packet_commit, packet_tree = resolve_commit(packet_commit_value, "packet commit")
    if live_currentness:
        observation = observe_official_main(authorized_ref_value)
    else:
        if issuance_commit_value is None:
            fail("hermetic request validation requires one retained issuance commit")
        authorized_ref = validate_authorized_ref(authorized_ref_value, "authorized ref")
        retained_commit, _retained_tree = resolve_commit(
            issuance_commit_value,
            "retained issuance commit",
        )
        checkout_commit, checkout_tree = resolve_checkout_head()
        require_ancestor(
            retained_commit,
            checkout_commit,
            "retained issuance commit is not an ancestor of checked-out HEAD",
        )
        observation = {
            "authorized_ref": authorized_ref,
            "authorized_commit": checkout_commit,
            "authorized_tree": checkout_tree,
            "local_main_commit": checkout_commit,
            "local_main_tree": checkout_tree,
            "remote_observed_commit": checkout_commit,
        }
    authorized_ref = observation["authorized_ref"]
    authorized_commit = observation["authorized_commit"]
    authorized_tree = observation["authorized_tree"]
    require_ancestor(
        packet_commit,
        authorized_commit,
        "packet commit is not an ancestor of the authorized ref",
    )
    if issuance_commit_value is None:
        issuance_commit = authorized_commit
        issuance_tree = authorized_tree
    else:
        issuance_commit, issuance_tree = resolve_commit(
            issuance_commit_value,
            "retained issuance commit",
        )
    require_ancestor(
        packet_commit,
        issuance_commit,
        "packet commit is not an ancestor of the retained issuance commit",
    )
    require_ancestor(
        issuance_commit,
        authorized_commit,
        "retained issuance commit is not an ancestor of the authorized ref",
    )
    packet_content = read_git_blob(
        packet_commit, PACKET_RELATIVE, maximum=MAX_PACKET_BYTES
    )
    registry_content = read_git_blob(
        packet_commit, REGISTRY_RELATIVE, maximum=MAX_JSON_BYTES
    )
    registry = parse_json_bytes(
        registry_content, f"{packet_commit}:{REGISTRY_RELATIVE}"
    )
    if not isinstance(registry, dict):
        fail("proposed registry must be an object")
    packet_subject = registry.get("review_packet_subject")
    if not isinstance(packet_subject, dict) or not isinstance(
        packet_subject.get("source"), dict
    ):
        fail("proposed registry lacks one CURRENT packet subject")
    source_commit_value = packet_subject["source"].get("commit")
    source_commit, source_tree = resolve_commit(
        source_commit_value, "zero-review source commit"
    )
    if packet_subject["source"].get("tree") != source_tree:
        fail("packet subject source tree differs from Git")
    if source_commit == packet_commit:
        fail("packet commit must follow the zero-review source commit")
    require_ancestor(
        source_commit,
        packet_commit,
        "zero-review source commit is not an ancestor of the packet commit",
    )

    source_content = read_git_blob(
        source_commit, SOURCE_RELATIVE, maximum=MAX_JSON_BYTES
    )
    source = parse_json_bytes(source_content, f"{source_commit}:{SOURCE_RELATIVE}")
    paths: set[str] = {SOURCE_RELATIVE}
    review_policy = packet_subject.get("review_policy")
    decision_set = packet_subject.get("decision_set")
    decisions = packet_subject.get("decisions")
    if not isinstance(review_policy, dict) or not isinstance(decision_set, dict):
        fail("packet subject lacks review-policy or decision-set bindings")
    if not isinstance(decisions, list) or len(decisions) != len(EXPECTED_IDS):
        fail("packet subject must contain exactly 11 decisions")
    semantic_closure = decision_set.get("semantic_closure")
    if not isinstance(semantic_closure, dict):
        fail("packet subject lacks one semantic-closure binding")
    closure_evaluation = registry.get("semantic_closure_evaluation")
    if not isinstance(closure_evaluation, dict):
        fail("proposed registry lacks one semantic-closure evaluation")
    semantic_corpus = closure_evaluation.get("semantic_corpus")
    if not isinstance(semantic_corpus, dict):
        fail("proposed registry lacks one semantic-corpus evaluation")
    for identity in (
        review_policy.get("generator"),
        review_policy.get("output_json_schema"),
        semantic_closure.get("source"),
        semantic_closure.get("json_schema"),
        semantic_corpus.get("observed_identity"),
    ):
        if not isinstance(identity, dict):
            fail("packet subject contains an invalid bound file identity")
        paths.add(relative_path(identity.get("path"), "packet bound file path"))
    for decision in decisions:
        if not isinstance(decision, dict) or not isinstance(
            decision.get("source_set"), dict
        ):
            fail("packet subject contains an invalid decision source set")
        sources = decision["source_set"].get("sources")
        if not isinstance(sources, list):
            fail("packet subject decision source set lacks sources")
        for identity in sources:
            if not isinstance(identity, dict):
                fail("packet subject contains an invalid ADR source identity")
            paths.add(relative_path(identity.get("path"), "ADR source identity path"))
    source_files = {
        relative: read_git_blob(source_commit, relative, maximum=MAX_SOURCE_FILE_BYTES)
        for relative in sorted(paths)
    }
    authorized_packet_content = read_git_blob(
        authorized_commit,
        PACKET_RELATIVE,
        maximum=MAX_PACKET_BYTES,
    )
    authorized_registry_content = read_git_blob(
        authorized_commit,
        REGISTRY_RELATIVE,
        maximum=MAX_JSON_BYTES,
    )
    authorized_registry = parse_json_bytes(
        authorized_registry_content,
        f"{authorized_commit}:{REGISTRY_RELATIVE}",
    )
    if not isinstance(authorized_registry, dict):
        fail("authorized-ref proposed registry must be an object")
    if issuance_commit == authorized_commit:
        issuance_packet_content = authorized_packet_content
        issuance_registry_content = authorized_registry_content
        issuance_registry = copy.deepcopy(authorized_registry)
    else:
        issuance_packet_content = read_git_blob(
            issuance_commit,
            PACKET_RELATIVE,
            maximum=MAX_PACKET_BYTES,
        )
        issuance_registry_content = read_git_blob(
            issuance_commit,
            REGISTRY_RELATIVE,
            maximum=MAX_JSON_BYTES,
        )
        issuance_registry = parse_json_bytes(
            issuance_registry_content,
            f"{issuance_commit}:{REGISTRY_RELATIVE}",
        )
        if not isinstance(issuance_registry, dict):
            fail("retained issuance registry must be an object")
    if live_currentness:
        require_local_refs_unchanged(authorized_commit)
    issuance_tool_identity = current_tool_identity(issuance_commit, root=ROOT)
    return {
        "packet_commit": packet_commit,
        "packet_tree": packet_tree,
        "packet_content": packet_content,
        "registry_content": registry_content,
        "registry": registry,
        "source_commit": source_commit,
        "source_tree": source_tree,
        "source_content": source_content,
        "source": source,
        "source_files": source_files,
        "authorized_ref": authorized_ref,
        "authorized_commit": authorized_commit,
        "authorized_tree": authorized_tree,
        "local_main_commit": observation["local_main_commit"],
        "local_main_tree": observation["local_main_tree"],
        "remote_observed_commit": observation["remote_observed_commit"],
        "authorized_packet_content": authorized_packet_content,
        "authorized_registry_content": authorized_registry_content,
        "authorized_registry": authorized_registry,
        "issuance_commit": issuance_commit,
        "issuance_tree": issuance_tree,
        "issuance_packet_content": issuance_packet_content,
        "issuance_registry_content": issuance_registry_content,
        "issuance_registry": issuance_registry,
        "issuance_tool_identity": issuance_tool_identity,
    }


def current_tool_identity(
    issuance_commit: str,
    *,
    root: Path | None = None,
) -> list[dict[str, Any]]:
    """Bind current no-follow tool bytes to literal blobs at the issuance cut."""

    repository_root = ROOT if root is None else root
    checked_commit = validate_hex(
        issuance_commit,
        HEX40,
        "generator issuance commit",
    )
    with immutable_git_operation(root=repository_root) as operation:
        pinned_root = operation.duplicate_root_descriptor(
            "generator source worktree binding"
        )
        try:
            issued_sources = [
                read_git_blob(
                    checked_commit,
                    relative,
                    maximum=MAX_SOURCE_FILE_BYTES,
                    root=repository_root,
                )
                for relative in GENERATOR_SOURCE_RELATIVES
            ]
            identities = [
                file_identity(relative, content)
                for relative, content in zip(
                    GENERATOR_SOURCE_RELATIVES,
                    issued_sources,
                    strict=True,
                )
            ]
            for pass_number in (1, 2):
                for relative, issued_content in zip(
                    GENERATOR_SOURCE_RELATIVES,
                    issued_sources,
                    strict=True,
                ):
                    current_content = read_repository_regular_file(
                        relative,
                        minimum=1,
                        maximum=MAX_SOURCE_FILE_BYTES,
                        label=(
                            f"current generator source pass {pass_number}: {relative}"
                        ),
                        root_descriptor=pinned_root,
                    )
                    if current_content != issued_content:
                        fail(
                            f"current generator source {relative} differs from its "
                            "literal issuance blob"
                        )
            return identities
        finally:
            os.close(pinned_root)


def registry_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def replace_packet_fence(
    content: bytes,
    *,
    schema: str,
    replacement: dict[str, Any],
) -> bytes:
    text = content.decode("utf-8")
    lines = text.splitlines()
    output: list[str] = []
    index = 0
    replacements = 0
    while index < len(lines):
        if lines[index] != "```json":
            output.append(lines[index])
            index += 1
            continue
        fence_end = index + 1
        while fence_end < len(lines) and lines[fence_end] != "```":
            fence_end += 1
        if fence_end == len(lines):
            fail("self-test packet contains an unterminated JSON fence")
        block_lines = lines[index + 1 : fence_end]
        block = parse_json_bytes(
            ("\n".join(block_lines) + "\n").encode("utf-8"),
            "self-test packet fence",
        )
        output.append("```json")
        if isinstance(block, dict) and block.get("schema") == schema:
            output.extend(
                json.dumps(replacement, ensure_ascii=False, indent=2).splitlines()
            )
            replacements += 1
        else:
            output.extend(block_lines)
        output.append("```")
        index = fence_end + 1
    if replacements != 1:
        fail(f"self-test packet must contain exactly one {schema} fence")
    return ("\n".join(output) + "\n").encode("utf-8")


def synchronize_registry_bytes(
    snapshot: dict[str, Any],
    *,
    primary: bool = True,
    authorized: bool = True,
    issuance: bool = True,
) -> None:
    if primary:
        snapshot["registry_content"] = registry_bytes(snapshot["registry"])
    if authorized:
        snapshot["authorized_registry_content"] = registry_bytes(
            snapshot["authorized_registry"]
        )
    if issuance:
        snapshot["issuance_registry_content"] = registry_bytes(
            snapshot["issuance_registry"]
        )


def synchronize_packet_document(
    snapshot: dict[str, Any],
    *,
    registry_field: str,
    schema: str,
    replacement: dict[str, Any],
) -> None:
    content = replace_packet_fence(
        snapshot["packet_content"],
        schema=schema,
        replacement=replacement,
    )
    identity = file_identity(PACKET_RELATIVE, content)
    snapshot["packet_content"] = content
    snapshot["authorized_packet_content"] = content
    snapshot["issuance_packet_content"] = content
    snapshot["registry"][registry_field] = copy.deepcopy(replacement)
    snapshot["authorized_registry"][registry_field] = copy.deepcopy(replacement)
    snapshot["issuance_registry"][registry_field] = copy.deepcopy(replacement)
    snapshot["registry"]["review_packet"] = copy.deepcopy(identity)
    snapshot["authorized_registry"]["review_packet"] = copy.deepcopy(identity)
    snapshot["issuance_registry"]["review_packet"] = copy.deepcopy(identity)
    synchronize_registry_bytes(snapshot)


def must_fail(action: Any, description: str, expected: str) -> None:
    try:
        action()
    except RequestError as error:
        if expected not in str(error):
            raise AssertionError(
                f"hostile self-test {description} failed for the wrong reason: {error}"
            ) from error
        return
    raise AssertionError(f"hostile self-test passed: {description}")


def git_history_self_test() -> None:
    """Exercise replacement and graft attacks in one disposable repository."""

    with tempfile.TemporaryDirectory(prefix="ncp-b01-git-history-") as directory:
        root = Path(directory)
        run_git(["init", "--quiet"], "initialize hostile Git fixture", root=root)
        run_git(
            ["config", "--local", "user.name", "NCP hostile fixture"],
            "configure hostile Git fixture name",
            root=root,
        )
        run_git(
            ["config", "--local", "user.email", "fixture@ncp.invalid"],
            "configure hostile Git fixture email",
            root=root,
        )
        subject = root / "subject.txt"
        subject.write_bytes(b"official immutable bytes\n")
        run_git(["add", "--", "subject.txt"], "stage official fixture", root=root)
        run_git(
            ["commit", "--quiet", "--no-gpg-sign", "-m", "official"],
            "commit official fixture",
            root=root,
        )
        official = validate_hex(
            run_git(
                ["rev-parse", "--verify", "HEAD^{commit}"],
                "resolve official fixture",
                root=root,
            )
            .decode("ascii")
            .strip(),
            HEX40,
            "official fixture commit",
        )
        _official_commit, official_tree = resolve_commit(
            official, "official fixture commit", root=root
        )
        official_mode, official_blob = read_raw_tree_entry(
            official_tree,
            b"subject.txt",
            label="official fixture root tree",
            root=root,
        )
        if official_mode != "100644":
            raise AssertionError("official fixture subject has the wrong tree mode")
        other_root = root / "other-repository"
        other_root.mkdir()
        run_git(
            ["init", "--quiet"],
            "initialize cross-root Git fixture",
            root=other_root,
        )
        run_git(
            ["config", "--local", "user.name", "NCP cross-root fixture"],
            "configure cross-root Git fixture name",
            root=other_root,
        )
        run_git(
            ["config", "--local", "user.email", "cross-root@ncp.invalid"],
            "configure cross-root Git fixture email",
            root=other_root,
        )
        (other_root / "other.txt").write_bytes(b"cross-root immutable bytes\n")
        run_git(
            ["add", "--", "other.txt"],
            "stage cross-root fixture",
            root=other_root,
        )
        run_git(
            ["commit", "--quiet", "--no-gpg-sign", "-m", "cross-root"],
            "commit cross-root fixture",
            root=other_root,
        )
        other_commit = validate_hex(
            run_git(
                ["rev-parse", "--verify", "HEAD^{commit}"],
                "resolve cross-root fixture",
                root=other_root,
            )
            .decode("ascii")
            .strip(),
            HEX40,
            "cross-root fixture commit",
        )
        swap_peer = root / "swap-peer-repository"
        swap_peer.mkdir()
        run_git(
            ["init", "--quiet"],
            "initialize root-swap peer fixture",
            root=swap_peer,
        )
        run_git(
            ["config", "--local", "user.name", "NCP root-swap fixture"],
            "configure root-swap peer fixture name",
            root=swap_peer,
        )
        run_git(
            ["config", "--local", "user.email", "root-swap@ncp.invalid"],
            "configure root-swap peer fixture email",
            root=swap_peer,
        )
        (swap_peer / "peer.txt").write_bytes(b"substituted repository bytes\n")
        run_git(
            ["add", "--", "peer.txt"],
            "stage root-swap peer fixture",
            root=swap_peer,
        )
        run_git(
            ["commit", "--quiet", "--no-gpg-sign", "-m", "root-swap peer"],
            "commit root-swap peer fixture",
            root=swap_peer,
        )
        peer_commit = validate_hex(
            run_git(
                ["rev-parse", "--verify", "HEAD^{commit}"],
                "resolve root-swap peer fixture",
                root=swap_peer,
            )
            .decode("ascii")
            .strip(),
            HEX40,
            "root-swap peer fixture commit",
        )
        swap_parking = root / "root-swap-parking"

        def swap_repository_names() -> None:
            other_root.rename(swap_parking)
            swap_peer.rename(other_root)
            swap_parking.rename(swap_peer)

        with immutable_git_operation(root=other_root):
            swap_repository_names()
            try:
                must_fail(
                    lambda: resolve_commit(
                        peer_commit,
                        "pre-child root-swap fixture",
                        root=other_root,
                    ),
                    "repository directory swap before Git child",
                    "immutable Git root directory change",
                )
            finally:
                swap_repository_names()

        original_popen = immutable_git_module.subprocess.Popen
        swapped_during_child = False

        def swapping_popen(*arguments: Any, **options: Any) -> Any:
            nonlocal swapped_during_child
            process = original_popen(*arguments, **options)
            if not swapped_during_child:
                swap_repository_names()
                swapped_during_child = True
            return process

        with immutable_git_operation(root=other_root):
            immutable_git_module.subprocess.Popen = swapping_popen
            try:
                must_fail(
                    lambda: resolve_commit(
                        other_commit,
                        "during-child root-swap fixture",
                        root=other_root,
                    ),
                    "repository directory swap during Git child",
                    "immutable Git root directory change",
                )
            finally:
                immutable_git_module.subprocess.Popen = original_popen
                if swapped_during_child:
                    swap_repository_names()
        with immutable_git_operation(root=root) as outer_operation:
            with immutable_git_operation(root=root) as nested_operation:
                if nested_operation is not outer_operation:
                    raise AssertionError("same-root immutable Git budget was reset")
            with immutable_git_operation(root=other_root) as other_operation:
                if other_operation is outer_operation:
                    raise AssertionError("cross-root Git cache and fences were reused")
                if other_operation.budget is not outer_operation.budget:
                    raise AssertionError("cross-root aggregate Git budget was reset")

        prior_process_limit = immutable_git_module.MAX_OPERATION_PROCESSES
        try:
            try:
                with immutable_git_operation(root=root) as outer_operation:
                    immutable_git_module.MAX_OPERATION_PROCESSES = (
                        outer_operation.processes * 2
                    )
                    with immutable_git_operation(root=other_root):
                        pass
            except ImmutableGitError as error:
                if "aggregate Git subprocess budget" not in str(error):
                    raise AssertionError(
                        "cross-root process budget failed for the wrong reason"
                    ) from error
            else:
                raise AssertionError("cross-root process budget hostile control passed")
        finally:
            immutable_git_module.MAX_OPERATION_PROCESSES = prior_process_limit

        prior_byte_limit = immutable_git_module.MAX_OPERATION_BYTES
        try:
            try:
                with immutable_git_operation(root=root) as outer_operation:
                    resolve_commit(official, "cross-root byte parent", root=root)
                    immutable_git_module.MAX_OPERATION_BYTES = outer_operation.bytes + 1
                    with immutable_git_operation(root=other_root):
                        resolve_commit(
                            other_commit,
                            "cross-root byte child",
                            root=other_root,
                        )
            except RequestError as error:
                if "aggregate Git object-read budget" not in str(error):
                    raise AssertionError(
                        "cross-root byte budget failed for the wrong reason"
                    ) from error
            else:
                raise AssertionError("cross-root byte budget hostile control passed")
        finally:
            immutable_git_module.MAX_OPERATION_BYTES = prior_byte_limit

        prior_cross_root_tree_limit = immutable_git_module.MAX_OPERATION_TREE_ENTRIES
        try:
            try:
                with immutable_git_operation(root=root) as outer_operation:
                    resolve_commit(official, "cross-root tree parent", root=root)
                    immutable_git_module.MAX_OPERATION_TREE_ENTRIES = (
                        outer_operation.tree_entries
                    )
                    with immutable_git_operation(root=other_root):
                        resolve_commit(
                            other_commit,
                            "cross-root tree child",
                            root=other_root,
                        )
            except RequestError as error:
                if "aggregate Git tree-entry budget" not in str(error):
                    raise AssertionError(
                        "cross-root tree budget failed for the wrong reason"
                    ) from error
            else:
                raise AssertionError("cross-root tree budget hostile control passed")
        finally:
            immutable_git_module.MAX_OPERATION_TREE_ENTRIES = (
                prior_cross_root_tree_limit
            )

        try:
            with immutable_git_operation(root=root) as outer_operation:
                retained_deadline = outer_operation.deadline
                try:
                    outer_operation.budget.deadline = time.monotonic() - 1
                    with immutable_git_operation(root=other_root):
                        pass
                finally:
                    outer_operation.budget.deadline = retained_deadline
        except ImmutableGitError as error:
            if "operation deadline" not in str(error):
                raise AssertionError(
                    "cross-root deadline failed for the wrong reason"
                ) from error
        else:
            raise AssertionError("cross-root deadline hostile control passed")

        prior_tree_entry_limit = immutable_git_module.MAX_OPERATION_TREE_ENTRIES
        immutable_git_module.MAX_OPERATION_TREE_ENTRIES = 0
        try:
            try:
                resolve_commit(official, "aggregate tree budget fixture", root=root)
            except RequestError as error:
                if "aggregate Git tree-entry budget" not in str(error):
                    raise AssertionError(
                        "aggregate tree budget failed for the wrong reason"
                    ) from error
            else:
                raise AssertionError("aggregate tree budget hostile control passed")
        finally:
            immutable_git_module.MAX_OPERATION_TREE_ENTRIES = prior_tree_entry_limit

        prior_operation_seconds = immutable_git_module.MAX_OPERATION_SECONDS
        immutable_git_module.MAX_OPERATION_SECONDS = 0
        try:
            try:
                with immutable_git_operation(root=root):
                    pass
            except ImmutableGitError as error:
                if "operation deadline" not in str(error):
                    raise AssertionError(
                        "global deadline failed for the wrong reason"
                    ) from error
            else:
                raise AssertionError("global deadline hostile control passed")
        finally:
            immutable_git_module.MAX_OPERATION_SECONDS = prior_operation_seconds
        object_path_raw = run_git(
            [
                "rev-parse",
                "--path-format=absolute",
                "--git-path",
                f"objects/{official_blob[:2]}/{official_blob[2:]}",
            ],
            "resolve loose object fixture path",
            root=root,
        )
        loose_object_path = Path(object_path_raw.decode("utf-8").strip())
        original_loose_bytes = loose_object_path.read_bytes()
        original_loose_mode = stat.S_IMODE(loose_object_path.stat().st_mode)
        official_body = b"official immutable bytes\n"
        tampered_body = b"tampered immutable bytes\n"
        if len(official_body) != len(tampered_body):
            raise AssertionError("loose-object fixture bodies differ in length")
        loose_object_path.chmod(original_loose_mode | stat.S_IWUSR)
        loose_object_path.write_bytes(
            zlib.compress(
                f"blob {len(tampered_body)}\0".encode("ascii") + tampered_body
            )
        )
        try:
            must_fail(
                lambda: read_git_object(
                    official_blob,
                    "blob",
                    maximum=1024,
                    label="tampered loose blob fixture",
                    root=root,
                ),
                "loose object content substitution",
                "raw bytes do not match their Git object ID",
            )
        finally:
            loose_object_path.write_bytes(original_loose_bytes)
            loose_object_path.chmod(original_loose_mode)

        subject.write_bytes(b"hostile substituted bytes\n")
        run_git(["add", "--", "subject.txt"], "stage hostile fixture", root=root)
        run_git(
            ["commit", "--quiet", "--no-gpg-sign", "-m", "hostile"],
            "commit hostile fixture",
            root=root,
        )
        hostile = validate_hex(
            run_git(
                ["rev-parse", "--verify", "HEAD^{commit}"],
                "resolve hostile fixture",
                root=root,
            )
            .decode("ascii")
            .strip(),
            HEX40,
            "hostile fixture commit",
        )
        run_git(
            ["checkout", "--quiet", "--detach", hostile],
            "detach hostile fixture checkout",
            root=root,
        )
        checkout_commit, _checkout_tree = resolve_checkout_head(root=root)
        if checkout_commit != hostile:
            raise AssertionError("detached checkout resolved the wrong literal HEAD")
        require_ancestor(
            official,
            checkout_commit,
            "detached full-history checkout lost literal ancestry",
            root=root,
        )
        run_git(
            ["replace", official, hostile],
            "install hostile replacement ref",
            root=root,
        )
        must_fail(
            lambda: resolve_commit(
                official, "replacement-protected fixture", root=root
            ),
            "replacement-ref raw commit admission",
            "Git replacement refs are forbidden",
        )
        must_fail(
            lambda: read_git_blob(
                official,
                "subject.txt",
                maximum=1024,
                root=root,
            ),
            "replacement-ref raw blob admission",
            "Git replacement refs are forbidden",
        )
        must_fail(
            lambda: require_unmodified_git_history(root=root),
            "replacement-ref repository admission",
            "replacement refs are forbidden",
        )
        run_git(
            ["replace", "-d", official],
            "remove hostile replacement ref",
            root=root,
        )

        unrelated = validate_hex(
            run_git(
                ["commit-tree", official_tree, "-m", "unrelated root"],
                "create unrelated fixture commit",
                root=root,
            )
            .decode("ascii")
            .strip(),
            HEX40,
            "unrelated fixture commit",
        )
        must_fail(
            lambda: require_ancestor(
                unrelated,
                hostile,
                "bounded raw ancestry unexpectedly reached an unrelated commit",
                root=root,
                commit_bound=1,
            ),
            "raw ancestry node ceiling",
            "1-commit verification bound",
        )
        must_fail(
            lambda: require_ancestor(
                unrelated,
                hostile,
                "bounded raw ancestry unexpectedly reached an unrelated commit",
                root=root,
                edge_bound=0,
            ),
            "raw ancestry edge ceiling",
            "0-edge verification bound",
        )
        malformed_path = root / "malformed.commit"
        malformed_path.write_bytes(
            (
                f"tree {official_tree}\n"
                "author Fixture <fixture@ncp.invalid> 1 +0000\n"
                f"parent {official}\n"
                "committer Fixture <fixture@ncp.invalid> 1 +0000\n\n"
                "late-parent attack\n"
            ).encode("ascii")
        )
        malformed_commit = validate_hex(
            run_git(
                [
                    "hash-object",
                    "--literally",
                    "-t",
                    "commit",
                    "-w",
                    "--",
                    "malformed.commit",
                ],
                "write malformed raw commit fixture",
                root=root,
            )
            .decode("ascii")
            .strip(),
            HEX40,
            "malformed raw commit fixture",
        )
        must_fail(
            lambda: resolve_commit(
                malformed_commit,
                "malformed raw commit fixture",
                root=root,
            ),
            "late raw parent header",
            "raw commit headers are noncanonical",
        )
        cr_commit_path = root / "cr.commit"
        cr_commit_path.write_bytes(
            (
                f"tree {official_tree}\r\n"
                "author Fixture <fixture@ncp.invalid> 1 +0000\r\n"
                "committer Fixture <fixture@ncp.invalid> 1 +0000\r\n\n"
                "carriage-return attack\r\n"
            ).encode("ascii")
        )
        cr_commit = validate_hex(
            run_git(
                [
                    "hash-object",
                    "--literally",
                    "-t",
                    "commit",
                    "-w",
                    "--",
                    "cr.commit",
                ],
                "write carriage-return commit fixture",
                root=root,
            )
            .decode("ascii")
            .strip(),
            HEX40,
            "carriage-return commit fixture",
        )
        must_fail(
            lambda: resolve_commit(
                cr_commit,
                "carriage-return commit fixture",
                root=root,
            ),
            "carriage-return commit header",
            "raw commit lacks a canonical header boundary",
        )

        malformed_tree_path = root / "malformed.tree"
        malformed_tree_path.write_bytes(
            b"100644 b.txt\x00"
            + bytes.fromhex(official_blob)
            + b"100644 a.txt\x00"
            + bytes.fromhex(official_blob)
        )
        malformed_tree = validate_hex(
            run_git(
                [
                    "hash-object",
                    "--literally",
                    "-t",
                    "tree",
                    "-w",
                    "--",
                    "malformed.tree",
                ],
                "write malformed raw tree fixture",
                root=root,
            )
            .decode("ascii")
            .strip(),
            HEX40,
            "malformed raw tree fixture",
        )
        must_fail(
            lambda: read_raw_tree_entry(
                malformed_tree,
                b"a.txt",
                label="malformed raw tree fixture",
                root=root,
            ),
            "unsorted raw tree",
            "noncanonical raw tree ordering",
        )
        malformed_root_commit_path = root / "malformed-root.commit"
        malformed_root_commit_path.write_bytes(
            (
                f"tree {malformed_tree}\n"
                "author Fixture <fixture@ncp.invalid> 1 +0000\n"
                "committer Fixture <fixture@ncp.invalid> 1 +0000\n\n"
                "malformed root tree attack\n"
            ).encode("ascii")
        )
        malformed_root_commit = validate_hex(
            run_git(
                [
                    "hash-object",
                    "--literally",
                    "-t",
                    "commit",
                    "-w",
                    "--",
                    "malformed-root.commit",
                ],
                "write malformed-root commit fixture",
                root=root,
            )
            .decode("ascii")
            .strip(),
            HEX40,
            "malformed-root commit fixture",
        )
        must_fail(
            lambda: resolve_commit(
                malformed_root_commit,
                "malformed-root commit fixture",
                root=root,
            ),
            "commit with noncanonical root tree",
            "noncanonical raw tree ordering",
        )
        dangling_tree = "e" * 40
        dangling_tree_commit_path = root / "dangling-tree.commit"
        dangling_tree_commit_path.write_bytes(
            (
                f"tree {dangling_tree}\n"
                "author Fixture <fixture@ncp.invalid> 1 +0000\n"
                "committer Fixture <fixture@ncp.invalid> 1 +0000\n\n"
                "dangling root tree attack\n"
            ).encode("ascii")
        )
        dangling_tree_commit = validate_hex(
            run_git(
                [
                    "hash-object",
                    "--literally",
                    "-t",
                    "commit",
                    "-w",
                    "--",
                    "dangling-tree.commit",
                ],
                "write dangling-tree commit fixture",
                root=root,
            )
            .decode("ascii")
            .strip(),
            HEX40,
            "dangling-tree commit fixture",
        )
        must_fail(
            lambda: resolve_commit(
                dangling_tree_commit,
                "dangling-tree commit fixture",
                root=root,
            ),
            "commit with dangling root tree",
            "does not resolve to one bounded raw Git object",
        )
        invalid_mode_tree_path = root / "invalid-mode.tree"
        invalid_mode_tree_path.write_bytes(
            b"100600 a.txt\x00" + bytes.fromhex(official_blob)
        )
        invalid_mode_tree = validate_hex(
            run_git(
                [
                    "hash-object",
                    "--literally",
                    "-t",
                    "tree",
                    "-w",
                    "--",
                    "invalid-mode.tree",
                ],
                "write invalid-mode raw tree fixture",
                root=root,
            )
            .decode("ascii")
            .strip(),
            HEX40,
            "invalid-mode raw tree fixture",
        )
        must_fail(
            lambda: read_raw_tree_entry(
                invalid_mode_tree,
                b"a.txt",
                label="invalid-mode raw tree fixture",
                root=root,
            ),
            "invalid raw tree mode",
            "noncanonical raw tree mode",
        )
        dangling_parent = "f" * 40
        dangling_commit_path = root / "dangling-parent.commit"
        dangling_commit_path.write_bytes(
            (
                f"tree {official_tree}\n"
                f"parent {dangling_parent}\n"
                "author Fixture <fixture@ncp.invalid> 1 +0000\n"
                "committer Fixture <fixture@ncp.invalid> 1 +0000\n\n"
                "dangling parent attack\n"
            ).encode("ascii")
        )
        dangling_commit = validate_hex(
            run_git(
                [
                    "hash-object",
                    "--literally",
                    "-t",
                    "commit",
                    "-w",
                    "--",
                    "dangling-parent.commit",
                ],
                "write dangling-parent commit fixture",
                root=root,
            )
            .decode("ascii")
            .strip(),
            HEX40,
            "dangling-parent commit fixture",
        )
        must_fail(
            lambda: require_ancestor(
                dangling_parent,
                dangling_commit,
                "dangling parent cannot establish ancestry",
                root=root,
            ),
            "dangling raw parent object",
            "does not resolve to one bounded raw Git object",
        )
        graft_path = git_metadata_path("info/grafts", root=root)
        graft_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            try:
                with immutable_git_operation(root=root):
                    graft_path.write_bytes(f"{unrelated} {official}\n".encode("ascii"))
            except ImmutableGitError as error:
                if "Git graft file is forbidden" not in str(error):
                    raise AssertionError(
                        "final history fence failed for the wrong reason"
                    ) from error
            else:
                raise AssertionError("final history fence missed a graft race")
        finally:
            graft_path.unlink(missing_ok=True)
        graft_path.write_bytes(f"{unrelated} {official}\n".encode("ascii"))
        run_git(
            ["merge-base", "--is-ancestor", official, unrelated],
            "confirm hostile graft changes Git ancestry",
            root=root,
        )
        must_fail(
            lambda: require_ancestor(
                official,
                unrelated,
                "raw ancestry rejected the hostile graft",
                root=root,
            ),
            "raw ancestry under a hostile graft",
            "Git graft file is forbidden",
        )
        must_fail(
            lambda: require_unmodified_git_history(root=root),
            "grafted repository admission",
            "Git graft file is forbidden",
        )
        graft_path.unlink()

        shallow_path = git_metadata_path("shallow", root=root)
        shallow_path.write_bytes(b"")
        must_fail(
            lambda: require_unmodified_git_history(root=root),
            "empty shallow-boundary repository admission",
            "shallow Git boundary is forbidden",
        )
        shallow_path.unlink()
        shallow_path.write_bytes(f"{official}\n".encode("ascii"))
        must_fail(
            lambda: require_unmodified_git_history(root=root),
            "nonempty shallow-boundary repository admission",
            "shallow Git boundary is forbidden",
        )
        shallow_path.unlink()

        fixture_scripts = root / "scripts"
        fixture_scripts.mkdir()
        fixture_sources = {
            SCRIPT_RELATIVE: b"fixture generator source\n",
            IMMUTABLE_GIT_RELATIVE: b"fixture immutable Git source\n",
        }
        for relative, content in fixture_sources.items():
            (root / relative).write_bytes(content)
        run_git(
            ["add", "--", *GENERATOR_SOURCE_RELATIVES],
            "stage issuance source fixture",
            root=root,
        )
        run_git(
            ["commit", "--quiet", "--no-gpg-sign", "-m", "issuance sources"],
            "commit issuance source fixture",
            root=root,
        )
        tool_commit = validate_hex(
            run_git(
                ["rev-parse", "--verify", "HEAD^{commit}"],
                "resolve issuance source fixture",
                root=root,
            )
            .decode("ascii")
            .strip(),
            HEX40,
            "issuance source fixture commit",
        )
        expected_tool_identity = [
            file_identity(relative, fixture_sources[relative])
            for relative in GENERATOR_SOURCE_RELATIVES
        ]
        if current_tool_identity(tool_commit, root=root) != expected_tool_identity:
            raise AssertionError("issuance source fixture returned the wrong identity")
        (root / SCRIPT_RELATIVE).write_bytes(b"dirty generator source\n")
        must_fail(
            lambda: current_tool_identity(tool_commit, root=root),
            "dirty post-issuance generator source",
            "differs from its literal issuance blob",
        )
        (root / SCRIPT_RELATIVE).write_bytes(fixture_sources[SCRIPT_RELATIVE])
        must_fail(
            lambda: current_tool_identity(official, root=root),
            "absent issuance generator source",
            "Git blob path is absent or ambiguous",
        )

        alternates_path = git_metadata_path("objects/info/alternates", root=root)
        alternates_path.parent.mkdir(parents=True, exist_ok=True)
        alternates_path.write_bytes(b"/hostile/object/store\n")
        must_fail(
            lambda: require_unmodified_git_history(root=root),
            "alternate-object-store repository admission",
            "Git object alternates is forbidden",
        )


def self_test(snapshot: dict[str, Any], tool_identity: list[dict[str, Any]]) -> None:
    git_history_self_test()
    baseline = build_request(snapshot, tool_identity)
    validated = validate_snapshot(snapshot)
    first = generated_bytes(baseline)
    second = generated_bytes(build_request(copy.deepcopy(snapshot), tool_identity))
    if first != second:
        raise AssertionError("repeated generation changed request bytes")
    if str(ROOT).encode("utf-8") in first:
        raise AssertionError("generated request contains an absolute repository path")

    hostile_snapshot = copy.deepcopy(snapshot)
    hostile_snapshot.pop("issuance_tool_identity")
    must_fail(
        lambda: build_request(hostile_snapshot, tool_identity),
        "missing issuance generator source roster",
        "must contain the exact ordered generator sources",
    )
    hostile_snapshot = copy.deepcopy(snapshot)
    hostile_snapshot["issuance_tool_identity"][0]["sha256"] = "0" * 64
    must_fail(
        lambda: build_request(hostile_snapshot, tool_identity),
        "substituted issuance generator source identity",
        "differ from the literal issuance blobs",
    )
    hostile_request = copy.deepcopy(baseline)
    hostile_request["generated_by"][1]["sha256"] = "0" * 64
    must_fail(
        lambda: validate_request(
            hostile_request,
            validated=validated,
            tool_identity=tool_identity,
        ),
        "substituted request generator source identity",
        "differs from the exact issuing source bytes",
    )

    observed_test_commit = "a" * 40

    if trusted_fixed_executable_metadata(stat.S_IFREG | 0o755, 1):
        raise AssertionError("non-root executable metadata passed its trust predicate")
    if trusted_fixed_executable_metadata(stat.S_IFREG | 0o775, 0):
        raise AssertionError("group-writable executable metadata passed its predicate")

    def canonical_runner(
        command: list[str], **options: Any
    ) -> subprocess.CompletedProcess[bytes]:
        expected_command = [
            GIT_BINARY,
            "--no-replace-objects",
            "ls-remote",
            "--exit-code",
            "--refs",
            CANONICAL_SSH_URL,
            REMOTE_QUERY_REF,
        ]
        if command != expected_command:
            raise AssertionError("remote query command differs from the fixed command")
        if options.get("cwd") != ROOT.parent:
            raise AssertionError("remote query did not run outside repository config")
        if options.get("timeout") != REMOTE_TIMEOUT_SECONDS:
            raise AssertionError("remote query lacks the fixed timeout")
        environment = options.get("env")
        if not isinstance(environment, dict) or (
            environment.get("GIT_TERMINAL_PROMPT") != "0"
        ):
            raise AssertionError("remote query can prompt for credentials")
        if environment.get("GIT_DIR") != os.devnull:
            raise AssertionError("remote query can load repository-local config")
        if environment.get("PATH") != "/usr/bin:/bin":
            raise AssertionError("remote query inherits the caller PATH")
        if environment.get("GIT_SSH_VARIANT") != "ssh":
            raise AssertionError("remote query does not force the SSH transport")
        if environment.get("GIT_ALLOW_PROTOCOL") != "ssh":
            raise AssertionError("remote query permits a non-SSH transport")
        ssh_command = environment.get("GIT_SSH_COMMAND")
        if not isinstance(ssh_command, str) or not ssh_command.startswith(
            f"{SSH_BINARY} -F /dev/null "
        ):
            raise AssertionError("remote query lacks the pinned SSH command")
        if environment.get("SSH_AUTH_SOCK") != SELF_TEST_AGENT_SOCKET:
            raise AssertionError("remote query does not pass one exact agent socket")
        if environment["SSH_AUTH_SOCK"] in ssh_command:
            raise AssertionError(
                "remote query interpolates SSH_AUTH_SOCK into shell text"
            )
        if options.get("stdin") is not subprocess.DEVNULL:
            raise AssertionError("remote query can read interactive input")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=(f"{observed_test_commit}\t{REMOTE_QUERY_REF}\n").encode("ascii"),
            stderr=b"",
        )

    inherited_path = os.environ.get("PATH")
    os.environ["PATH"] = str(Path(tempfile.gettempdir()) / "hostile-first-path")
    try:
        if (
            query_remote_main(CANONICAL_HTTPS_URL, runner=canonical_runner)
            != observed_test_commit
        ):
            raise AssertionError("canonical remote observation changed its commit")
    finally:
        if inherited_path is None:
            os.environ.pop("PATH", None)
        else:
            os.environ["PATH"] = inherited_path

    with tempfile.TemporaryDirectory(
        prefix="ncp-b01-hostile-path-", dir=ROOT.parent
    ) as hostile_path_directory:
        fake_git = Path(hostile_path_directory) / "git"
        sentinel = Path(hostile_path_directory) / "executed"
        fake_git.write_text(f"#!/bin/sh\ntouch {sentinel}\nexit 0\n", encoding="utf-8")
        fake_git.chmod(0o755)
        inherited_path = os.environ.get("PATH")
        os.environ["PATH"] = hostile_path_directory
        try:
            run_git(["--version"], "fixed local Git PATH hostile control")
            resolve_commit(
                snapshot["packet_commit"],
                "fixed immutable Git PATH hostile control",
            )
        finally:
            if inherited_path is None:
                os.environ.pop("PATH", None)
            else:
                os.environ["PATH"] = inherited_path
        if sentinel.exists():
            raise AssertionError("local Git control executed a caller-PATH binary")

    effective_environment = remote_git_environment()
    effective_environment["SSH_AUTH_SOCK"] = EFFECTIVE_TEST_AGENT_SOCKET
    effective_environment["GIT_SSH_COMMAND"] = github_ssh_command(
        EFFECTIVE_TEST_KNOWN_HOSTS
    )
    validate_effective_ssh_config(EFFECTIVE_TEST_KNOWN_HOSTS, effective_environment)

    with tempfile.TemporaryDirectory(
        prefix="ncp-b01-agent-paths-", dir=ROOT.parent
    ) as socket_directory:
        for leaf in (
            "agent space.sock",
            "agent'quote.sock",
            "agent;semicolon.sock",
            "agent$(command).sock",
        ):
            hostile_socket_path = str(Path(socket_directory) / leaf)
            unix_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                unix_socket.bind(hostile_socket_path)
                observed_path, _identity = ssh_auth_socket_identity(hostile_socket_path)
                if observed_path != hostile_socket_path:
                    raise AssertionError("SSH agent socket path changed")
                if hostile_socket_path in github_ssh_command(HOSTILE_TEST_KNOWN_HOSTS):
                    raise AssertionError("SSH agent socket path entered shell text")
            finally:
                unix_socket.close()
                Path(hostile_socket_path).unlink(missing_ok=True)

    must_fail(
        lambda: ssh_auth_socket_identity("relative-agent.sock"),
        "relative SSH agent socket path",
        "bounded absolute path",
    )
    must_fail(
        lambda: ssh_auth_socket_identity("/" + "a" * 4_097),
        "overlong SSH agent socket path",
        "1..4096 characters",
    )
    must_fail(
        lambda: ssh_auth_socket_identity(
            str(Path(tempfile.gettempdir()) / "control\nagent.sock")
        ),
        "control-bearing SSH agent socket path",
        "bounded absolute path",
    )
    must_fail(
        lambda: ssh_auth_socket_identity(
            str(Path(tempfile.gettempdir()) / "surrogate-\udcff.sock")
        ),
        "surrogate-bearing SSH agent socket path",
        "not UTF-8",
    )

    must_fail(
        lambda: validate_origin_url(
            "https://credential@github.com/sepahead/NCP.git",
            "hostile origin URL",
        ),
        "credential-bearing origin URL",
        "canonical sepahead/NCP SSH or credential-free HTTPS",
    )
    for description, raw, expected in (
        (
            "duplicate origin URL lines",
            (CANONICAL_SSH_URL + "\n" + CANONICAL_SSH_URL + "\n").encode(),
            "exactly one LF-terminated fetch URL",
        ),
        (
            "carriage-return origin URL",
            (CANONICAL_SSH_URL + "\r\n").encode(),
            "exactly one LF-terminated fetch URL",
        ),
        (
            "vertical-tab origin URL",
            (CANONICAL_SSH_URL + "\v\n").encode(),
            "control byte",
        ),
        (
            "Unicode line-separator origin URL",
            (CANONICAL_SSH_URL + "\u2028\n").encode(),
            "not canonical ASCII",
        ),
    ):
        must_fail(
            lambda raw=raw: parse_origin_url_output(raw),
            description,
            expected,
        )

    must_fail(
        lambda: validate_authorized_ref(LOCAL_MAIN_REF, "hostile authorized ref"),
        "wrong authorized ref",
        f"must be exactly {DEFAULT_AUTHORIZED_REF}",
    )

    must_fail(
        lambda: validate_remote_ref_join("a" * 40, "b" * 40, "a" * 40),
        "remote and local ref mismatch",
        "must resolve to one commit",
    )

    malformed_remote = subprocess.CompletedProcess(
        ["git", "ls-remote"],
        0,
        stdout=(f"{'a' * 40}\trefs/heads/not-main\n").encode("ascii"),
        stderr=b"",
    )
    must_fail(
        lambda: query_remote_main(
            CANONICAL_HTTPS_URL,
            runner=lambda *_args, **_options: malformed_remote,
        ),
        "wrong ls-remote ref",
        "malformed or names the wrong ref",
    )

    malformed_remote = subprocess.CompletedProcess(
        ["git", "ls-remote"],
        0,
        stdout=b"not-a-git-ls-remote-response\n",
        stderr=b"",
    )
    must_fail(
        lambda: query_remote_main(
            CANONICAL_HTTPS_URL,
            runner=lambda *_args, **_options: malformed_remote,
        ),
        "malformed ls-remote response",
        "malformed or names the wrong ref",
    )

    def timeout_runner(*_args: Any, **_options: Any) -> Any:
        raise subprocess.TimeoutExpired(["git", "ls-remote"], REMOTE_TIMEOUT_SECONDS)

    must_fail(
        lambda: query_remote_main(CANONICAL_HTTPS_URL, runner=timeout_runner),
        "ls-remote timeout",
        f"timed out after {REMOTE_TIMEOUT_SECONDS} seconds",
    )

    hostile = copy.deepcopy(snapshot)
    hostile["registry"]["review_records"] = [{"forbidden": True}]
    synchronize_registry_bytes(hostile, authorized=False, issuance=False)
    must_fail(
        lambda: build_request(hostile, tool_identity),
        "existing review record",
        "registry.review_records must remain empty",
    )

    hostile = copy.deepcopy(snapshot)
    hostile["registry"]["review_packet"]["sha256"] = "0" * 64
    synchronize_registry_bytes(hostile, authorized=False, issuance=False)
    must_fail(
        lambda: build_request(hostile, tool_identity),
        "packet digest substitution",
        "registry.review_packet differs from the exact retained bytes",
    )

    hostile = copy.deepcopy(snapshot)
    lifecycle = copy.deepcopy(hostile["registry"]["review_packet_lifecycle"])
    lifecycle["state"] = "SUPERSEDED"
    synchronize_packet_document(
        hostile,
        registry_field="review_packet_lifecycle",
        schema=PACKET_LIFECYCLE_SCHEMA,
        replacement=lifecycle,
    )
    must_fail(
        lambda: build_request(hostile, tool_identity),
        "superseded packet",
        "review packet lifecycle must be CURRENT",
    )

    hostile = copy.deepcopy(snapshot)
    subject = copy.deepcopy(hostile["registry"]["review_packet_subject"])
    subject["claim_boundary"] = "This packet grants authority."
    synchronize_packet_document(
        hostile,
        registry_field="review_packet_subject",
        schema=REVIEW_SUBJECT_SCHEMA,
        replacement=subject,
    )
    must_fail(
        lambda: build_request(hostile, tool_identity),
        "packet authority claim",
        "review packet subject claim_boundary is not the accepted boundary",
    )

    hostile = copy.deepcopy(snapshot)
    hostile["registry"]["claim_boundary"] = "This registry grants authority."
    synchronize_registry_bytes(hostile, authorized=False, issuance=False)
    must_fail(
        lambda: build_request(hostile, tool_identity),
        "registry authority claim",
        "registry.claim_boundary differs from the non-authorizing boundary",
    )

    hostile = copy.deepcopy(snapshot)
    hostile["registry"]["promotion_target"] = "contract/other.json"
    synchronize_registry_bytes(hostile, authorized=False, issuance=False)
    must_fail(
        lambda: build_request(hostile, tool_identity),
        "promotion target substitution",
        "registry.promotion_target differs from the reviewed target",
    )

    hostile = copy.deepcopy(snapshot)
    subject = copy.deepcopy(hostile["registry"]["review_packet_subject"])
    subject["review_policy"]["schema"] = "ncp.permissive-policy.v1"
    hostile["registry"]["review_policy"] = copy.deepcopy(subject["review_policy"])
    hostile["authorized_registry"]["review_policy"] = copy.deepcopy(
        subject["review_policy"]
    )
    synchronize_packet_document(
        hostile,
        registry_field="review_packet_subject",
        schema=REVIEW_SUBJECT_SCHEMA,
        replacement=subject,
    )
    must_fail(
        lambda: build_request(hostile, tool_identity),
        "review policy substitution",
        "registry.review_policy.schema differs from the frozen non-authorizing policy",
    )

    hostile = copy.deepcopy(snapshot)
    subject = copy.deepcopy(hostile["registry"]["review_packet_subject"])
    subject["decision_set"]["sha256"] = "0" * 64
    hostile["registry"]["decision_set"]["sha256"] = "0" * 64
    hostile["authorized_registry"]["decision_set"]["sha256"] = "0" * 64
    hostile["registry"]["semantic_closure_evaluation"]["decision_set_sha256"] = "0" * 64
    hostile["authorized_registry"]["semantic_closure_evaluation"][
        "decision_set_sha256"
    ] = "0" * 64
    synchronize_packet_document(
        hostile,
        registry_field="review_packet_subject",
        schema=REVIEW_SUBJECT_SCHEMA,
        replacement=subject,
    )
    must_fail(
        lambda: build_request(hostile, tool_identity),
        "decision-set substitution",
        "decision-set SHA-256 differs from the canonical projection",
    )

    hostile = copy.deepcopy(snapshot)
    subject = copy.deepcopy(hostile["registry"]["review_packet_subject"])
    subject["decision_set"]["semantic_closure"]["extra"] = "forbidden"
    for name in ("registry", "authorized_registry", "issuance_registry"):
        hostile[name]["decision_set"] = copy.deepcopy(subject["decision_set"])
    synchronize_packet_document(
        hostile,
        registry_field="review_packet_subject",
        schema=REVIEW_SUBJECT_SCHEMA,
        replacement=subject,
    )
    must_fail(
        lambda: build_request(hostile, tool_identity),
        "open semantic-closure binding",
        "decision_set.semantic_closure has unexpected members",
    )

    for description, mutate, expected in (
        (
            "truncated semantic-closure evaluation",
            lambda evaluation: evaluation.pop("source"),
            "semantic_closure_evaluation has unexpected members",
        ),
        (
            "extended semantic-closure evaluation",
            lambda evaluation: evaluation.__setitem__("extra", "forbidden"),
            "semantic_closure_evaluation has unexpected members",
        ),
        (
            "failed semantic-corpus status",
            lambda evaluation: evaluation["semantic_corpus"].__setitem__(
                "observed_status", "FAILED"
            ),
            "not the required COMPLETE_CURRENT corpus",
        ),
        (
            "zero semantic-corpus count",
            lambda evaluation: evaluation["semantic_corpus"].__setitem__(
                "case_count", 0
            ),
            "counts differ from the bound corpus bytes",
        ),
        (
            "wrong semantic-corpus identity",
            lambda evaluation: evaluation["semantic_corpus"][
                "observed_identity"
            ].__setitem__("sha256", "0" * 64),
            "differs from the exact retained bytes",
        ),
        (
            "failed B03 deferral status",
            lambda evaluation: evaluation["b03_deferrals"].__setitem__(
                "observed_status", "FAILED"
            ),
            "deferral counts differ from the bound closure source",
        ),
    ):
        hostile = copy.deepcopy(snapshot)
        mutate(hostile["registry"]["semantic_closure_evaluation"])
        synchronize_registry_bytes(hostile, authorized=False, issuance=False)
        must_fail(
            lambda hostile=hostile: build_request(hostile, tool_identity),
            description,
            expected,
        )

    for description, mutate, expected in (
        (
            "deleted acceptance blocker",
            lambda blockers: blockers.pop(),
            "differs from the canonical required-review blocker roster",
        ),
        (
            "extra acceptance blocker member",
            lambda blockers: blockers[0].__setitem__("extra", "forbidden"),
            "has unexpected members",
        ),
        (
            "null acceptance blocker",
            lambda blockers: blockers.__setitem__(0, None),
            "must be an object",
        ),
        (
            "duplicate acceptance blocker",
            lambda blockers: blockers.__setitem__(1, copy.deepcopy(blockers[0])),
            "differs from the canonical required-review blocker roster",
        ),
    ):
        hostile = copy.deepcopy(snapshot)
        blockers = hostile["registry"]["decisions"][0]["acceptance_blockers"]
        mutate(blockers)
        synchronize_registry_bytes(hostile, authorized=False, issuance=False)
        must_fail(
            lambda hostile=hostile: build_request(hostile, tool_identity),
            description,
            expected,
        )

    hostile = copy.deepcopy(snapshot)
    subject = copy.deepcopy(hostile["registry"]["review_packet_subject"])
    subject["decisions"].pop()
    synchronize_packet_document(
        hostile,
        registry_field="review_packet_subject",
        schema=REVIEW_SUBJECT_SCHEMA,
        replacement=subject,
    )
    must_fail(
        lambda: build_request(hostile, tool_identity),
        "short packet roster",
        "packet, source, and registry rosters must each contain exactly 11 decisions",
    )

    hostile = copy.deepcopy(snapshot)
    subject = copy.deepcopy(hostile["registry"]["review_packet_subject"])
    subject["decisions"][0]["required_reviews"][1]["role_id"] = subject["decisions"][0][
        "required_reviews"
    ][0]["role_id"]
    synchronize_packet_document(
        hostile,
        registry_field="review_packet_subject",
        schema=REVIEW_SUBJECT_SCHEMA,
        replacement=subject,
    )
    must_fail(
        lambda: build_request(hostile, tool_identity),
        "duplicate ADR role",
        "packet decisions[0].required_reviews contains duplicate role IDs",
    )

    hostile = copy.deepcopy(snapshot)
    hostile["authorized_packet_content"] += b"\n"
    must_fail(
        lambda: build_request(hostile, tool_identity),
        "authorized packet drift",
        "authorized ref does not retain the exact CURRENT review packet bytes",
    )

    hostile = copy.deepcopy(snapshot)
    hostile["authorized_registry"]["review_records"] = [{"forbidden": True}]
    synchronize_registry_bytes(hostile, primary=False)
    must_fail(
        lambda: build_request(hostile, tool_identity),
        "authorized ref review record",
        "authorized-ref registry.review_records must remain empty",
    )

    hostile_request = copy.deepcopy(baseline)
    hostile_request["review_slots"][0]["decision"] = "ACCEPT"
    must_fail(
        lambda: validate_request(
            hostile_request,
            validated=validated,
            tool_identity=tool_identity,
        ),
        "prepopulated decision",
        "unexpected members",
    )

    hostile_request = copy.deepcopy(baseline)
    hostile_request["human_response_contract"]["decision_population"] = "MODEL"
    must_fail(
        lambda: validate_request(
            hostile_request,
            validated=validated,
            tool_identity=tool_identity,
        ),
        "model decision population",
        "human response contract is invalid",
    )

    hostile_request = copy.deepcopy(baseline)
    hostile_request["review_slots"][0]["state"] = "FILLED"
    must_fail(
        lambda: validate_request(
            hostile_request,
            validated=validated,
            tool_identity=tool_identity,
        ),
        "filled review slot",
        "state must be UNFILLED",
    )

    hostile_request = copy.deepcopy(baseline)
    hostile_request["review_slots"][0]["role_label"] += " changed"
    must_fail(
        lambda: validate_request(
            hostile_request,
            validated=validated,
            tool_identity=tool_identity,
        ),
        "slot roster drift",
        "review slots differ from the frozen 11-decision roster",
    )

    hostile_request = copy.deepcopy(baseline)
    hostile_request["subject_cut"]["issuance_currentness"]["resolved_commit"] = "0" * 40
    hostile_request["subject_cut"]["issuance_currentness"]["remote_observation"][
        "retained_observed_commit"
    ] = "0" * 40
    must_fail(
        lambda: validate_request(
            hostile_request,
            validated=validated,
            tool_identity=tool_identity,
        ),
        "issuance cut drift",
        "subject_cut differs from the exact validated issuance cut",
    )

    hostile_request = copy.deepcopy(baseline)
    hostile_request["subject_cut"]["issuance_currentness"]["remote_observation"][
        "authorizing"
    ] = True
    must_fail(
        lambda: validate_request(
            hostile_request,
            validated=validated,
            tool_identity=tool_identity,
        ),
        "authorizing remote observation",
        "differs from the non-authorizing issuance observation",
    )

    hostile_request = copy.deepcopy(baseline)
    hostile_request["subject_cut"]["issuance_currentness"]["remote_observation"][
        "host_key_line_sha256"
    ] = "0" * 64
    must_fail(
        lambda: validate_request(
            hostile_request,
            validated=validated,
            tool_identity=tool_identity,
        ),
        "substituted remote host-key profile",
        "differs from the non-authorizing issuance observation",
    )

    hostile_request = copy.deepcopy(baseline)
    hostile_request["evidence_requirements"][1]["evidence_requirement_id"] = (
        hostile_request["evidence_requirements"][0]["evidence_requirement_id"]
    )
    must_fail(
        lambda: validate_request(
            hostile_request,
            validated=validated,
            tool_identity=tool_identity,
        ),
        "duplicate evidence ID",
        "differs from its slot and kind",
    )

    hostile_request = copy.deepcopy(baseline)
    hostile_request["evidence_requirements"].pop()
    must_fail(
        lambda: validate_request(
            hostile_request,
            validated=validated,
            tool_identity=tool_identity,
        ),
        "missing evidence requirement",
        "exactly 112 evidence requirements",
    )

    hostile_request = copy.deepcopy(baseline)
    hostile_request["evidence_requirements"][0]["required_path_prefix"] = "../reviews/"
    must_fail(
        lambda: validate_request(
            hostile_request,
            validated=validated,
            tool_identity=tool_identity,
        ),
        "escaping review path prefix",
        "required_path_prefix is invalid",
    )

    print(
        "B01 REVIEW REQUEST SELF-TEST PASSED — "
        "53 unfilled review slots and 112 unfilled evidence requirements",
        file=sys.stderr,
    )


def stat_identity(metadata: os.stat_result, *, include_ctime: bool) -> tuple[int, ...]:
    identity = (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_size,
        metadata.st_mtime_ns,
    )
    return identity + ((metadata.st_ctime_ns,) if include_ctime else ())


def read_fd_exact(descriptor: int, maximum: int, label: str) -> bytes:
    observed = bytearray()
    offset = 0
    while len(observed) <= maximum:
        chunk = os.pread(
            descriptor,
            min(64 * 1024, maximum + 1 - len(observed)),
            offset,
        )
        if not chunk:
            break
        observed.extend(chunk)
        offset += len(chunk)
    if len(observed) > maximum:
        fail(f"{label} exceeds its byte bound")
    return bytes(observed)


def installed_target_snapshot(
    parent: int, leaf: str
) -> tuple[tuple[int, ...], str, int] | None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(leaf, flags, dir_fd=parent)
    except FileNotFoundError:
        return None
    except OSError as error:
        fail(f"cannot inspect existing {OUTPUT_RELATIVE}: {error}")
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            fail(f"{OUTPUT_RELATIVE} must be a regular non-symlink file")
        raw = read_fd_exact(descriptor, MAX_OUTPUT_BYTES, OUTPUT_RELATIVE)
        closed = os.fstat(descriptor)
        named = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
    except OSError as error:
        fail(f"cannot reopen existing {OUTPUT_RELATIVE}: {error}")
    finally:
        if descriptor is not None:
            os.close(descriptor)
    identity = stat_identity(opened, include_ctime=True)
    if (
        stat_identity(closed, include_ctime=True) != identity
        or stat_identity(named, include_ctime=True) != identity
    ):
        fail(f"{OUTPUT_RELATIVE} changed during its bounded snapshot")
    return identity, sha256_bytes(raw), len(raw)


def write_output(
    content: bytes,
    *,
    authorized_ref: str,
    authorized_commit: str,
    authorized_tree: str,
    issuance_commit: str,
    tool_identity: list[dict[str, Any]],
) -> None:
    validate_authorized_ref(authorized_ref, "authorized ref")
    parent, leaf = open_repository_parent(OUTPUT_RELATIVE, OUTPUT_RELATIVE)
    try:
        parent_identity = os.fstat(parent)
    except OSError as error:
        os.close(parent)
        fail(f"cannot inspect {OUTPUT_RELATIVE} parent: {error}")
    if (
        not stat.S_ISDIR(parent_identity.st_mode)
        or parent_identity.st_uid != os.getuid()
        or parent_identity.st_mode & 0o022
    ):
        os.close(parent)
        fail(
            f"{OUTPUT_RELATIVE} parent must be current-user owned and not "
            "writable by group or world"
        )
    temporary_name: str | None = None
    temporary_identity: tuple[int, ...] | None = None
    descriptor: int | None = None
    installation_attempted = False
    installation_succeeded = False
    try:
        initial_target = installed_target_snapshot(parent, leaf)
        flags = (
            os.O_RDWR
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        for _attempt in range(16):
            candidate = f".review-request.{secrets.token_hex(16)}.tmp"
            try:
                descriptor = os.open(candidate, flags, 0o644, dir_fd=parent)
                temporary_name = candidate
                break
            except FileExistsError:
                continue
        if descriptor is None or temporary_name is None:
            fail("cannot allocate one exclusive B01 request temporary file")
        remaining = memoryview(content)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                fail("cannot write the complete B01 request")
            remaining = remaining[written:]
        os.fsync(descriptor)
        opened_temporary = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened_temporary.st_mode)
            or opened_temporary.st_uid != os.getuid()
            or opened_temporary.st_nlink != 1
            or opened_temporary.st_mode & 0o022
        ):
            fail("B01 request temporary file has an unsafe installation identity")
        temporary_identity = stat_identity(opened_temporary, include_ctime=True)
        final_observation = observe_official_main(authorized_ref)
        if (
            final_observation["authorized_commit"] != authorized_commit
            or final_observation["authorized_tree"] != authorized_tree
            or final_observation["local_main_commit"] != authorized_commit
            or final_observation["local_main_tree"] != authorized_tree
            or final_observation["remote_observed_commit"] != authorized_commit
        ):
            fail("canonical remote or local main moved before request installation")
        require_unmodified_git_history()
        if current_tool_identity(issuance_commit, root=ROOT) != tool_identity:
            fail("B01 request generator changed before durable output installation")
        require_repository_parent_identity(
            OUTPUT_RELATIVE,
            parent_identity,
            label="B01 request installation",
        )
        closed_temporary = os.fstat(descriptor)
        named_temporary = os.stat(temporary_name, dir_fd=parent, follow_symlinks=False)
        observed_content = read_fd_exact(
            descriptor, len(content), "B01 request temporary file"
        )
        if (
            temporary_identity is None
            or stat_identity(closed_temporary, include_ctime=True) != temporary_identity
            or stat_identity(named_temporary, include_ctime=True) != temporary_identity
            or not stat.S_ISREG(closed_temporary.st_mode)
            or observed_content != content
        ):
            fail("B01 request temporary file changed before atomic installation")
        if installed_target_snapshot(parent, leaf) != initial_target:
            fail("B01 request target changed before atomic installation")
        installation_attempted = True
        os.replace(
            temporary_name,
            leaf,
            src_dir_fd=parent,
            dst_dir_fd=parent,
        )
        temporary_name = None
        published_fd = os.fstat(descriptor)
        published_path = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
        expected_published_identity = stat_identity(
            opened_temporary, include_ctime=False
        )
        if (
            stat_identity(published_fd, include_ctime=False)
            != expected_published_identity
            or stat_identity(published_path, include_ctime=False)
            != expected_published_identity
            or read_fd_exact(descriptor, len(content), "installed B01 request")
            != content
        ):
            fail(
                "B01 request installation outcome is unknown: the published file "
                "differs from the owned temporary file"
            )
        os.fsync(descriptor)
        os.fsync(parent)
        final_fd = os.fstat(descriptor)
        final_path = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
        if (
            stat_identity(final_fd, include_ctime=False) != expected_published_identity
            or stat_identity(final_path, include_ctime=False)
            != expected_published_identity
            or read_fd_exact(descriptor, len(content), "durable B01 request") != content
        ):
            fail(
                "B01 request installation outcome is unknown: the published file "
                "changed before the durable rejoin"
            )
        require_repository_parent_identity(
            OUTPUT_RELATIVE,
            parent_identity,
            label="durable B01 request installation",
        )
        final_rejoin = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
        if (
            stat_identity(os.fstat(descriptor), include_ctime=False)
            != expected_published_identity
            or stat_identity(final_rejoin, include_ctime=False)
            != expected_published_identity
            or read_fd_exact(descriptor, len(content), "final B01 request rejoin")
            != content
        ):
            fail(
                "B01 request installation outcome is unknown: the final path "
                "rejoin changed"
            )
        installation_succeeded = True
    except OSError as error:
        if installation_attempted and not installation_succeeded:
            fail(
                "B01 request installation outcome is unknown after atomic replace: "
                f"{error}"
            )
        fail(f"cannot write {OUTPUT_RELATIVE}: {error}")
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary_name is not None:
            try:
                current_temporary = os.stat(
                    temporary_name, dir_fd=parent, follow_symlinks=False
                )
                current_identity = stat_identity(current_temporary, include_ctime=True)
                if current_identity == temporary_identity:
                    os.unlink(temporary_name, dir_fd=parent)
            except FileNotFoundError:
                pass
        os.close(parent)


def check_output(content: bytes) -> None:
    current = read_repository_regular_file(
        OUTPUT_RELATIVE,
        minimum=1,
        maximum=MAX_OUTPUT_BYTES,
        label=OUTPUT_RELATIVE,
    )
    if current != content:
        fail(f"{OUTPUT_RELATIVE} is stale; run this command with --write")


def retained_issuance_commit(authorized_ref: str) -> str:
    raw = read_repository_regular_file(
        OUTPUT_RELATIVE,
        minimum=1,
        maximum=MAX_OUTPUT_BYTES,
        label=OUTPUT_RELATIVE,
    )
    value = parse_json_bytes(raw, OUTPUT_RELATIVE)
    if not isinstance(value, dict) or value.get("schema") != REQUEST_SCHEMA:
        fail(f"{OUTPUT_RELATIVE} does not contain a B01 review request")
    subject_cut = value.get("subject_cut")
    if not isinstance(subject_cut, dict):
        fail(f"{OUTPUT_RELATIVE} lacks its retained issuance cut")
    issuance = subject_cut.get("issuance_currentness")
    if not isinstance(issuance, dict):
        fail(f"{OUTPUT_RELATIVE} lacks its retained issuance currentness")
    if issuance.get("authorized_ref") != authorized_ref:
        fail(f"{OUTPUT_RELATIVE} binds a different authorized ref")
    retained_commit = validate_hex(
        issuance.get("resolved_commit"),
        HEX40,
        f"{OUTPUT_RELATIVE} retained issuance commit",
    )
    validate_remote_observation_identity(
        issuance.get("remote_observation"),
        authorized_ref=authorized_ref,
        retained_observed_commit=retained_commit,
        path=f"{OUTPUT_RELATIVE} retained remote observation",
    )
    return retained_commit


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate the non-authorizing B01 review request"
    )
    parser.add_argument(
        "--commit",
        required=True,
        help="exact 40-character commit that contains the immutable CURRENT packet",
    )
    parser.add_argument(
        "--authorized-ref",
        default=DEFAULT_AUTHORIZED_REF,
        help=(
            "fixed local remote-tracking ref used for issuance currentness "
            f"(default: {DEFAULT_AUTHORIZED_REF})"
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--write", action="store_true", help="write the generated request"
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="check the retained request against checked-out HEAD (default)",
    )
    mode.add_argument(
        "--live-check",
        action="store_true",
        help="check the request and reobserve canonical remote and local main",
    )
    mode.add_argument(
        "--stdout", action="store_true", help="write the request to stdout"
    )
    parser.add_argument(
        "--self-test", action="store_true", help="run hostile request mutations first"
    )
    args = parser.parse_args()

    try:
        authorized_ref = validate_authorized_ref(args.authorized_ref, "authorized ref")
        checking = not args.write and not args.stdout
        live_currentness = args.live_check or args.write or args.stdout
        issuance_commit = retained_issuance_commit(authorized_ref) if checking else None
        snapshot = load_snapshot(
            args.commit,
            authorized_ref,
            issuance_commit_value=issuance_commit,
            live_currentness=live_currentness,
        )
        tool_identity = current_tool_identity(snapshot["issuance_commit"], root=ROOT)
        if args.self_test:
            self_test(snapshot, tool_identity)
        request = build_request(snapshot, tool_identity)
        content = generated_bytes(request)
        if len(content) > MAX_OUTPUT_BYTES:
            fail(f"generated request exceeds {MAX_OUTPUT_BYTES} bytes")
        if live_currentness:
            require_official_observation_unchanged(snapshot)
            require_local_refs_unchanged(snapshot["authorized_commit"])
        else:
            require_checkout_head_unchanged(snapshot["authorized_commit"])
        if (
            current_tool_identity(snapshot["issuance_commit"], root=ROOT)
            != tool_identity
        ):
            fail("B01 request generator changed during request validation")
        if args.stdout:
            sys.stdout.buffer.write(content)
        elif args.write:
            write_output(
                content,
                authorized_ref=snapshot["authorized_ref"],
                authorized_commit=snapshot["authorized_commit"],
                authorized_tree=snapshot["authorized_tree"],
                issuance_commit=snapshot["issuance_commit"],
                tool_identity=tool_identity,
            )
            print(f"WROTE {OUTPUT_RELATIVE}")
        else:
            check_output(content)
            if live_currentness:
                require_official_observation_unchanged(snapshot)
            else:
                require_checkout_head_unchanged(snapshot["authorized_commit"])
            if (
                current_tool_identity(snapshot["issuance_commit"], root=ROOT)
                != tool_identity
            ):
                fail("B01 request generator changed during retained-output validation")
            state = (
                "LIVE CANONICAL MAIN CURRENT"
                if args.live_check
                else "RETAINED CUT VALID; LIVE CURRENTNESS NOT CHECKED"
            )
            print(
                f"B01 REVIEW REQUEST {state} — 53 unfilled review slots and "
                "112 unfilled evidence requirements"
            )
        return 0
    except RequestError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
