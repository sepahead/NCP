"""Smoke test for the maturin-built `ncp` binding.

The behavioral DECISION functions (check_version / contract_status / validate /
govern) are exhaustively pinned by the shared corpus
(`scripts/check_behavior_vectors.py`, run with `NCP_REQUIRE_BINDING=1` in the maturin
CI job, so the binding must agree with the Rust reference). This smoke adds the one
path the decision corpus does NOT cover — the rate-codec round-trip
(`encode_rates` -> `decode_command`) — plus a check that the module-level contract
pins are exported. `importorskip` keeps it a no-op where the wheel isn't built.
"""

import json

import pytest

ncp = pytest.importorskip("ncp")

_EP = "00000000-0000-4000-8000-000000000001"
_GEN = "00000000-0000-4000-8000-0000000000a2"
_AUTHORITY = {
    "session_epoch": _GEN,
    "term": 1,
    "lease_id": "20000000-0000-4000-8000-000000000001",
    "issuer_principal_id": "commander-principal-1",
    "holder_principal_id": "commander-principal-1",
    "holder_entity_id": "controller-1",
    "issued_at_utc_ms": 1000,
    "expires_at_utc_ms": 2000,
}

# A minimal single-axis codec: pose_error[0] in [-2, 2] -> "err_x" rate in [0, 200] Hz;
# "err_x" readout in [0, 200] Hz -> velocity_setpoint[0] in [-1.5, 1.5] m/s. Defaulted
# fields (codec_id, coding, rate_range_hz, n_neurons, readout) are omitted.
CODEC = json.dumps(
    {
        "encoder": [
            {"channel": "pose_error", "component": 0, "population": "err_x", "value_range": [-2.0, 2.0]}
        ],
        "decoder": [
            {
                "population": "err_x",
                "command_channel": "velocity_setpoint",
                "component": 0,
                "unit": "m/s",
                "value_range": [-1.5, 1.5],
            }
        ],
    }
)


def test_module_pins_exported():
    assert ncp.PACKAGE_VERSION == "1.0.0-rc.1"
    assert ncp.NCP_VERSION == "1.0"
    assert ncp.CONTRACT_HASH == "163acc57d8a62b66"
    assert len(ncp.NORMATIVE_CONTRACT_DIGEST) == 64
    assert ncp.BUILD_IDENTITY == "unreleased-worktree"


def test_codec_roundtrip_encode_then_decode():
    # encode: lerp(1.0, [-2,2] -> [0,200]) = 150 Hz.
    sensor = json.dumps(
        {
            "kind": "sensor_frame",
            "ncp_version": "1.0",
            "stream": {"epoch": _EP, "seq": 1}, "session": {"generation": _GEN}, "session_id": "s",
            "t": 0.0,
            "channels": {"pose_error": {"data": [1.0, 0.0, 0.0]}},
        }
    )
    rates = json.loads(ncp.encode_rates(CODEC, sensor))
    assert rates.get("err_x") == pytest.approx(150.0)

    # decode: lerp(150 Hz, [0,200] -> [-1.5,1.5]) = 0.75 m/s, on velocity_setpoint[0].
    command = json.loads(
        ncp.decode_command(
            CODEC,
            json.dumps(rates),
            seq=1,
            mode="active",
            epoch=_EP,
            session_generation=_GEN,
            session_id="s",
            authority_json=json.dumps(_AUTHORITY),
        )
    )
    vel = command["channels"]["velocity_setpoint"]["data"]
    assert vel[0] == pytest.approx(0.75)


def test_codec_rejects_incomplete_sensor_and_unsafe_command_metadata():
    versionless = json.dumps(
        {
            "kind": "sensor_frame",
            "stream": {"epoch": _EP, "seq": 1}, "session": {"generation": _GEN}, "session_id": "s",
            "t": 0.0,
            "channels": {"pose_error": {"data": [1.0]}},
        }
    )
    with pytest.raises(ValueError):
        ncp.encode_rates(CODEC, versionless)
    with pytest.raises(ValueError):
        ncp.encode_rates(CODEC, "")
    with pytest.raises(ValueError):
        ncp.decode_command(CODEC, "{}", seq=0)
    with pytest.raises(ValueError):
        ncp.decode_command(CODEC, "{}", seq=1, t=float("nan"))


def test_decision_functions_callable():
    # Smoke only — exhaustive cross-language parity is the corpus's job.
    assert ncp.check_version("1.0", False) is True
    assert ncp.check_version("0.8", False) is False  # released legacy wire is incompatible
    assert ncp.contract_status("163acc57d8a62b66") == "match"
    frame = '{"kind":"command_frame","ncp_version":"1.0","stream":{"epoch":"00000000-0000-4000-8000-000000000001","seq":1},"session":{"generation":"00000000-0000-4000-8000-0000000000a2"},"session_id":"s"}'
    result = ncp.validate("command_frame", frame)
    assert '"kind":"command_frame"' in result  # canonical JSON, not just truthy
    # Wire 1.0: a version-less or unstamped command frame is rejected.
    with pytest.raises(ValueError):
        ncp.validate("command_frame", '{"kind":"command_frame"}')
    with pytest.raises(ValueError):
        ncp.validate("command_frame", '{"kind":"command_frame","ncp_version":"1.0","stream":{"epoch":"00000000-0000-4000-8000-000000000001","seq":0},"session":{"generation":"00000000-0000-4000-8000-0000000000a2"},"session_id":"s"}')
    with pytest.raises(ValueError):
        ncp.validate("command_frame", '{"ncp_version":"1.0","stream":{"epoch":"00000000-0000-4000-8000-000000000001","seq":1},"session":{"generation":"00000000-0000-4000-8000-0000000000a2"},"session_id":"s"}')

    error = {
        "kind": "error",
        "ncp_version": "1.0",
        "code": "NCP-WIRE-001",
        "error": "rejected",
        "request_kind": "open_session",
    }
    assert json.loads(ncp.validate("error", json.dumps(error)))["error"] == "rejected"
    with pytest.raises(ValueError):
        ncp.validate("error", json.dumps({key: value for key, value in error.items() if key != "code"}))
    with pytest.raises(ValueError):
        ncp.validate("error", json.dumps({**error, "code": "NCP-NOT-REGISTERED"}))


def test_validate_rejects_duplicate_json_keys_before_serde_collapse():
    duplicate = '{"kind":"command_frame","kind":"command_frame"}'
    with pytest.raises(ValueError, match="NCP-LIMIT-007"):
        ncp.validate("command_frame", duplicate)


def test_validate_rejects_frames_over_the_universal_byte_ceiling():
    oversized = '{"kind":"command_frame","padding":"' + ("x" * 1_048_576) + '"}'
    with pytest.raises(ValueError, match="NCP-LIMIT-001"):
        ncp.validate("command_frame", oversized)


def test_validate_rejects_json_over_the_universal_nesting_ceiling():
    nested = '{"kind":"command_frame","nested":' + ("[" * 34) + "0" + ("]" * 34) + "}"
    with pytest.raises(ValueError, match="NCP-LIMIT-002"):
        ncp.validate("command_frame", nested)


def test_validate_reports_malformed_json_with_the_registered_limit_code():
    with pytest.raises(ValueError, match="NCP-LIMIT-009"):
        ncp.validate("command_frame", '{"kind":')


@pytest.mark.parametrize(
    "entrypoint",
    [
        pytest.param(
            lambda: ncp.request_digest('{"kind":"step_request","kind":"step_request"}'),
            id="request-digest",
        ),
        pytest.param(
            lambda: ncp.encode_rates('{"encoder":[],"encoder":[],"decoder":[]}', "null"),
            id="codec-config",
        ),
        pytest.param(
            lambda: ncp.encode_rates(CODEC, '{"kind":"sensor_frame","kind":"sensor_frame"}'),
            id="sensor-frame",
        ),
        pytest.param(
            lambda: ncp.decode_command(CODEC, '{"rate":1,"rate":2}', seq=1),
            id="rate-map",
        ),
        pytest.param(
            lambda: ncp.decode_command(
                CODEC,
                "{}",
                seq=1,
                authority_json='{"term":1,"term":2}',
            ),
            id="authority-lease",
        ),
        pytest.param(
            lambda: ncp.govern('{"geofence_radius_m":1,"geofence_radius_m":2}', "{}", 0.0),
            id="one-shot-governor-limits",
        ),
        pytest.param(
            lambda: ncp.govern("{}", '{"mode":"hold","mode":"hold"}', 0.0),
            id="one-shot-command",
        ),
        pytest.param(
            lambda: ncp.govern(
                "{}",
                "{}",
                0.0,
                '{"kind":"sensor_frame","kind":"sensor_frame"}',
                0.0,
            ),
            id="one-shot-sensor",
        ),
        pytest.param(
            lambda: ncp.Governor('{"command_timeout_ms":1,"command_timeout_ms":2}'),
            id="persistent-governor-limits",
        ),
        pytest.param(
            lambda: ncp.Governor("{}").govern(
                '{"mode":"hold","mode":"hold"}', 0.0
            ),
            id="persistent-governor-command",
        ),
        pytest.param(
            lambda: ncp.ActionBuffer().on_command(
                0.0, '{"mode":"hold","mode":"hold"}'
            ),
            id="action-buffer-command",
        ),
    ],
)
def test_every_direct_json_entrypoint_rejects_duplicate_keys(entrypoint):
    with pytest.raises(ValueError, match="NCP-LIMIT-007"):
        entrypoint()


def test_channel_value_rejects_nonfinite_programmatic_input():
    with pytest.raises(ValueError, match="NCP-LIMIT-006"):
        ncp.channel_value([float("nan")])


def test_channel_value_rejects_programmatic_output_over_the_frame_budget():
    with pytest.raises(ValueError, match="NCP-LIMIT-001|NCP-LIMIT-004"):
        ncp.channel_value([0.0] * 262_145)


def test_rpc_keys_are_kind_scoped_and_realm_validated():
    keys = ncp.Keys("fleet/ncp")
    assert keys.rpc() == "fleet/ncp/rpc"
    assert keys.rpc_for_kind("open_session") == "fleet/ncp/rpc/open_session"
    assert keys.rpc_glob() == "fleet/ncp/rpc/*"
    with pytest.raises(ValueError):
        keys.rpc_for_kind("session_opened")
    with pytest.raises(ValueError):
        ncp.Keys("ncp/*")
    with pytest.raises(ValueError):
        keys.command("s1/*")
    with pytest.raises(ValueError):
        keys.sensor_named("s1", "imu/**")


def test_closed_network_kind_is_rejected():
    frame = {
        "kind": "open_session",
        "ncp_version": "1.0",
        "session_id": "s",
        "network": {"kind": "future_network_kind", "ref": "model"},
        "identity": {
            "principal_id": "commander-principal-1",
            "entity_id": "controller-1",
            "role": "commander",
            "plane": "control",
        },
        "security_profile": "dev-loopback-insecure",
        "security_state_digest": "0" * 64,
        "gateway_permitted": False,
    }
    with pytest.raises(ValueError, match="network.kind is unknown"):
        ncp.validate("open_session", json.dumps(frame))


def test_unknown_mode_roundtrips_losslessly_and_governs_as_hold():
    frame = {
        "kind": "command_frame",
        "ncp_version": "1.0",
        "stream": {"epoch": _EP, "seq": 1},
        "session": {"generation": _GEN},
        "session_id": "s",
        "mode": "future_hold",
    }
    canonical = json.loads(ncp.validate("command_frame", json.dumps(frame)))
    assert canonical["mode"] == "future_hold"
    governed = json.loads(ncp.govern("{}", json.dumps(frame), 0.0))
    assert governed["mode"] == "hold"


def test_decode_command_defaults_to_hold():
    command = json.loads(ncp.decode_command(CODEC, "{}", seq=1, epoch=_EP, session_generation=_GEN, session_id="s"))
    assert command["mode"] == "hold"


def test_action_buffer_enforces_horizon_ttl_and_replay():
    buffer = ncp.ActionBuffer()
    command = {
        "kind": "command_frame",
        "ncp_version": "1.0",
        "stream": {"epoch": _EP, "seq": 10}, "session": {"generation": _GEN}, "session_id": "s",
        "t": 0.0,
        "mode": "active",
        "ttl_ms": 200.0,
        "channels": {"velocity_setpoint": {"data": [0.1]}},
        "horizon": [
            {"velocity_setpoint": {"data": [0.2]}},
            {"velocity_setpoint": {"data": [0.3]}},
        ],
        "horizon_dt_ms": 50.0,
        "authority": _AUTHORITY,
    }
    buffer.on_command(1.0, json.dumps(command))
    assert json.loads(buffer.active(1.06))["velocity_setpoint"]["data"][0] == pytest.approx(0.2)
    assert buffer.should_hold(1.16) is True

    replay = {**command, "channels": {"velocity_setpoint": {"data": [9.0]}}, "horizon": []}
    buffer.on_command(2.0, json.dumps(replay))
    assert buffer.should_hold(2.0) is True


def test_local_action_buffer_reset_retires_generation_context():
    buffer = ncp.ActionBuffer()
    buffer.on_command(0.0, '{"mode":"estop"}')
    assert buffer.is_estopped() is True
    assert buffer.active(0.0) is None
    buffer.reset()
    assert buffer.is_estopped() is False
    assert buffer.is_retired() is True

    invalid_active = {
        "kind": "command_frame",
        "ncp_version": "1.0",
        "stream": {"epoch": _EP, "seq": 0}, "session": {"generation": _GEN}, "session_id": "s",
        "mode": "active",
        "ttl_ms": 200.0,
        "channels": {"velocity_setpoint": {"data": [1.0]}},
    }
    buffer.on_command(0.1, json.dumps(invalid_active))
    assert buffer.should_hold(0.1) is True

    fresh = ncp.ActionBuffer()
    assert fresh.is_retired() is False


def test_persistent_governor_latches_across_calls():
    """The Governor CLASS is the latching form — the one-shot govern() cannot
    latch by construction (fresh governor per call). A geofence breach must keep
    every later call at ESTOP until a supervisor reset()."""
    gov = ncp.Governor(json.dumps({"geofence_radius_m": 5.0, "command_timeout_ms": 500.0}))
    active = json.dumps(
        {
            "kind": "command_frame",
            "ncp_version": "1.0",
            "stream": {"epoch": _EP, "seq": 1}, "session": {"generation": _GEN}, "session_id": "s",
            "mode": "active",
            "ttl_ms": 200.0,
            "channels": {"velocity_setpoint": {"data": [1.0, 0.0, 0.0], "unit": "m/s"}},
            "authority": _AUTHORITY,
        }
    )
    breach = json.dumps(
        {
            "kind": "sensor_frame",
            "ncp_version": "1.0",
            "stream": {"epoch": _EP, "seq": 1}, "session": {"generation": _GEN}, "session_id": "s",
            "channels": {
                "pose_position": {"data": [10.0, 0.0, 0.0], "unit": "m"}
            },
        }
    )
    safe = json.dumps(
        {
            "kind": "sensor_frame",
            "ncp_version": "1.0",
            "stream": {"epoch": _EP, "seq": 2}, "session": {"generation": _GEN}, "session_id": "s",
            "channels": {
                "pose_position": {"data": [0.0, 0.0, 0.0], "unit": "m"}
            },
        }
    )

    out = json.loads(gov.govern(active, 1.0, breach, 1.0))
    assert out["mode"] == "estop"
    assert gov.is_estopped() is True
    assert gov.safety_ok() is False
    # A perfectly safe frame on the NEXT call is still ESTOP — the latch persisted.
    out2 = json.loads(gov.govern(active, 2.0, safe, 2.0))
    assert out2["mode"] == "estop"
    # The externally authorized local reset clears only the governor latch.
    gov.reset()
    assert gov.is_estopped() is False
    out3 = json.loads(gov.govern(active, 3.0, safe, 3.0))
    assert out3["mode"] == "active"
    # note_link(burst=True) latches too (the jam escalation path).
    gov.note_link(True)
    assert gov.is_estopped() is True
