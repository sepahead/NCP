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
    assert ncp.NCP_VERSION == "0.8"
    assert ncp.CONTRACT_HASH == "d1b50a2d8a265276"


def test_codec_roundtrip_encode_then_decode():
    # encode: lerp(1.0, [-2,2] -> [0,200]) = 150 Hz.
    sensor = json.dumps(
        {
            "kind": "sensor_frame",
            "ncp_version": "0.8",
            "stream": {"epoch": _EP, "seq": 1}, "session": {"generation": _GEN}, "session_id": "s",
            "t": 0.0,
            "channels": {"pose_error": {"data": [1.0, 0.0, 0.0]}},
        }
    )
    rates = json.loads(ncp.encode_rates(CODEC, sensor))
    assert rates.get("err_x") == pytest.approx(150.0)

    # decode: lerp(150 Hz, [0,200] -> [-1.5,1.5]) = 0.75 m/s, on velocity_setpoint[0].
    command = json.loads(ncp.decode_command(CODEC, json.dumps(rates), seq=1, mode="active", epoch=_EP, session_generation=_GEN, session_id="s"))
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
    assert ncp.check_version("0.8", False) is True
    assert ncp.check_version("0.6", False) is False  # previous wire: incompatible
    assert ncp.contract_status("d1b50a2d8a265276") == "match"
    frame = '{"kind":"command_frame","ncp_version":"0.8","stream":{"epoch":"00000000-0000-4000-8000-000000000001","seq":1},"session":{"generation":"00000000-0000-4000-8000-0000000000a2"},"session_id":"s"}'
    result = ncp.validate("command_frame", frame)
    assert '"kind":"command_frame"' in result  # canonical JSON, not just truthy
    # Wire 0.6: a version-less or unstamped command frame is rejected.
    with pytest.raises(ValueError):
        ncp.validate("command_frame", '{"kind":"command_frame"}')
    with pytest.raises(ValueError):
        ncp.validate("command_frame", '{"kind":"command_frame","ncp_version":"0.8","stream":{"epoch":"00000000-0000-4000-8000-000000000001","seq":0},"session":{"generation":"00000000-0000-4000-8000-0000000000a2"},"session_id":"s"}')
    with pytest.raises(ValueError):
        ncp.validate("command_frame", '{"ncp_version":"0.8","stream":{"epoch":"00000000-0000-4000-8000-000000000001","seq":1},"session":{"generation":"00000000-0000-4000-8000-0000000000a2"},"session_id":"s"}')

    error = {
        "kind": "error",
        "ncp_version": "0.8",
        "error": "rejected",
        "request_kind": "open_session",
    }
    assert json.loads(ncp.validate("error", json.dumps(error)))["error"] == "rejected"


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


def test_unknown_enum_roundtrips_losslessly():
    frame = {
        "kind": "open_session",
        "ncp_version": "0.8",
        "session_id": "s",
        "network": {"kind": "future_network_kind", "ref": "model"},
    }
    canonical = json.loads(ncp.validate("open_session", json.dumps(frame)))
    assert canonical["network"]["kind"] == "future_network_kind"


def test_decode_command_defaults_to_hold():
    command = json.loads(ncp.decode_command(CODEC, "{}", seq=1, epoch=_EP, session_generation=_GEN, session_id="s"))
    assert command["mode"] == "hold"


def test_action_buffer_enforces_horizon_ttl_and_replay():
    buffer = ncp.ActionBuffer()
    command = {
        "kind": "command_frame",
        "ncp_version": "0.8",
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
    }
    buffer.on_command(1.0, json.dumps(command))
    assert json.loads(buffer.active(1.06))["velocity_setpoint"]["data"][0] == pytest.approx(0.2)
    assert buffer.should_hold(1.16) is True

    replay = {**command, "channels": {"velocity_setpoint": {"data": [9.0]}}, "horizon": []}
    buffer.on_command(2.0, json.dumps(replay))
    assert buffer.should_hold(2.0) is True


def test_action_buffer_latches_unstamped_estop_until_reset():
    buffer = ncp.ActionBuffer()
    buffer.on_command(0.0, '{"mode":"estop"}')
    assert buffer.is_estopped() is True
    assert buffer.active(0.0) is None
    buffer.reset()
    assert buffer.is_estopped() is False

    invalid_active = {
        "kind": "command_frame",
        "ncp_version": "0.8",
        "stream": {"epoch": _EP, "seq": 0}, "session": {"generation": _GEN}, "session_id": "s",
        "mode": "active",
        "ttl_ms": 200.0,
        "channels": {"velocity_setpoint": {"data": [1.0]}},
    }
    buffer.on_command(0.1, json.dumps(invalid_active))
    assert buffer.should_hold(0.1) is True


def test_persistent_governor_latches_across_calls():
    """The Governor CLASS is the latching form — the one-shot govern() cannot
    latch by construction (fresh governor per call). A geofence breach must keep
    every later call at ESTOP until a supervisor reset()."""
    gov = ncp.Governor(json.dumps({"geofence_radius_m": 5.0, "command_timeout_ms": 500.0}))
    active = json.dumps(
        {
            "kind": "command_frame",
            "ncp_version": "0.8",
            "stream": {"epoch": _EP, "seq": 1}, "session": {"generation": _GEN}, "session_id": "s",
            "mode": "active",
            "ttl_ms": 200.0,
            "channels": {"velocity_setpoint": {"data": [1.0, 0.0, 0.0], "unit": "m/s"}},
        }
    )
    breach = json.dumps(
        {
            "kind": "sensor_frame",
            "ncp_version": "0.8",
            "stream": {"epoch": _EP, "seq": 1}, "session": {"generation": _GEN}, "session_id": "s",
            "channels": {
                "pose_position": {"data": [10.0, 0.0, 0.0], "unit": "m"}
            },
        }
    )
    safe = json.dumps(
        {
            "kind": "sensor_frame",
            "ncp_version": "0.8",
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
    # Supervisor reset restores normal governing.
    gov.reset()
    assert gov.is_estopped() is False
    out3 = json.loads(gov.govern(active, 3.0, safe, 3.0))
    assert out3["mode"] == "active"
    # note_link(burst=True) latches too (the jam escalation path).
    gov.note_link(True)
    assert gov.is_estopped() is True
