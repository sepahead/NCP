"""Run the shared conformance vectors (conformance/vectors.json) against the Python SDK."""
from __future__ import annotations

import json
import os
import sys
import unittest
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import ncp  # noqa: E402
from ncp import frame as F  # noqa: E402

with open(os.path.join(HERE, "..", "..", "conformance", "vectors.json"), encoding="utf-8") as handle:
    VECTORS = json.load(handle)


def plain(value, decoded):
    if isinstance(value, F.Array):
        return {"ncp.array": {"dtype": value.dtype, "shape": list(value.shape), "att": decoded.arrays.index(value)}}
    if isinstance(value, dict):
        return {k: plain(v, decoded) for k, v in value.items()}
    if isinstance(value, list):
        return [plain(v, decoded) for v in value]
    return value


class Handler:
    def validate(self, op, body):
        if op == "step" and isinstance(body, dict) and body.get("invalid") is True:
            raise ncp.BodyInvalid("invalid")

    def execute(self, op, body):
        if op == "fail":
            raise RuntimeError("fail")
        if op == "big":
            return {"blob": "z" * body["size"]}
        return {"echo": body}


def run_scenario(scenario, contract):
    owner = ncp.Owner("conformance", contract.identity, Handler(), contract.operations, max_bound=F.HANDSHAKE_BOUND)
    history: list[str] = []
    frames: list[bytes] = []
    responses: list[bytes] = []
    for index, step in enumerate(scenario["steps"]):
        if "repeat" in step:
            frame = frames[step["repeat"]]
        else:
            if "open" in step:
                spec = step["open"]
                body = {"application": spec.get("application", "conformance"),
                        "contract": spec.get("contract", contract.identity), "bound": spec.get("bound")}
                body.pop(spec.get("omit", ""), None)
            else:
                body = step.get("body", {})
            ack = {"last": history[-1] if history else None, "stale": history[-2] if len(history) > 1 else None,
                   "none": None, "other": "0" * 64}[step["ack"]]
            session = VECTORS["session"] if step.get("session") != "other" else str(uuid.uuid4())
            frame = F.encode({"ncp": step.get("ncp", 2), "session": session, "seq": step["seq"], "op": step["op"],
                              "ack": ack, "body": body})
        response = owner.handle(frame)
        message = F.decode(response, F.MAX_BOUND).message
        observed = [message["outcome"], message["code"]]
        yield index, step, observed, response, responses
        if "repeat" in step and step["expect"][0] != "rejected":
            assert response == responses[step["repeat"]], f"step {index}: repeat returned different bytes"
        if "open_bound" in step:
            assert message["body"]["bound"] == step["open_bound"]
        if message["outcome"] != "rejected" and "repeat" not in step:
            history.append(F.identity(response))  # a repeat returns the same response
        frames.append(frame)
        responses.append(response)


class ConformanceTests(unittest.TestCase):
    def test_frames(self) -> None:
        for case in VECTORS["frames"]:
            with self.subTest(case["name"]):
                frame = bytes.fromhex(case["frame"])
                if not case["valid"]:
                    with self.assertRaises(F.FrameError):
                        F.decode(frame, case["bound"])
                    continue
                decoded = F.decode(frame, case["bound"])
                self.assertEqual(plain(decoded.message, decoded), case["message"])
                self.assertEqual(decoded.identity, case["identity"])
                self.assertEqual([bytes(a.data).hex() for a in decoded.arrays], case["arrays"])

    def test_scenarios(self) -> None:
        contract = ncp.Contract.from_bytes(VECTORS["contract"].encode())
        self.assertEqual(contract.identity, VECTORS["contract_identity"])
        for scenario in VECTORS["scenarios"]:
            for index, step, observed, _, _ in run_scenario(scenario, contract):
                with self.subTest(scenario=scenario["name"], step=index):
                    self.assertEqual(observed, step["expect"])

    def test_streams(self) -> None:
        subscriber = ncp.Subscriber({VECTORS["contract_identity"]})
        for index, case in enumerate(VECTORS["streams"]):
            with self.subTest(index=index):
                delivery = subscriber.receive(bytes.fromhex(case["frame"]))
                self.assertEqual((delivery.status, delivery.lost), (case["status"], case["lost"]))


if __name__ == "__main__":
    unittest.main()
