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
    assert ncp.NCP_VERSION == "0.5"
    assert ncp.CONTRACT_HASH == "24e8e6e31e1dec8a"


def test_codec_roundtrip_encode_then_decode():
    # encode: lerp(1.0, [-2,2] -> [0,200]) = 150 Hz.
    sensor = json.dumps({"kind": "sensor_frame", "channels": {"pose_error": {"data": [1.0, 0.0, 0.0]}}})
    rates = json.loads(ncp.encode_rates(CODEC, sensor))
    assert rates.get("err_x") == pytest.approx(150.0)

    # decode: lerp(150 Hz, [0,200] -> [-1.5,1.5]) = 0.75 m/s, on velocity_setpoint[0].
    command = json.loads(ncp.decode_command(CODEC, json.dumps(rates)))
    vel = command["channels"]["velocity_setpoint"]["data"]
    assert vel[0] == pytest.approx(0.75)


def test_decision_functions_callable():
    # Smoke only — exhaustive cross-language parity is the corpus's job.
    assert ncp.check_version("0.5", False) is True
    assert ncp.contract_status("24e8e6e31e1dec8a") == "match"
    result = ncp.validate("command_frame", '{"kind":"command_frame"}')
    assert '"kind":"command_frame"' in result  # canonical JSON, not just truthy
