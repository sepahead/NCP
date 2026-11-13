"""Tests of the rounds profile (spec/NCP-2-ROUNDS.md) in the Python SDK."""

from __future__ import annotations

import logging
import os
import random
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import ncp  # noqa: E402

CONTRACT = ncp.Contract.from_bytes(
    b'{"ncp_contract":1,"application":"world","version":"1","operations":{"act":{}},"streams":{}}'
)


class Direct:
    """A lossless channel that hands each request to its owner in the client's thread."""

    lossy = False

    def __init__(self, owner: ncp.Owner) -> None:
        self.owner, self.queue = owner, []

    def send(self, frame: bytes) -> None:
        self.queue.append(self.owner.handle(frame))

    def receive(self, bound: int, timeout):
        return self.queue.pop(0)

    def close(self) -> None:
        pass


class World:
    """A step function that records what each round applied, in order."""

    def __init__(self) -> None:
        self.rounds: list[tuple[int, list[str]]] = []

    def __call__(self, number, inputs):
        self.rounds.append((number, [agent for agent, _ in inputs]))
        return {agent: {"value": body["value"], "position": i} for i, (agent, body) in enumerate(inputs)}


def make_rounds(members, step, deadline=5.0) -> ncp.Rounds:
    return ncp.Rounds(CONTRACT, "act", members, step, deadline=deadline)


def client_for(owner: ncp.Owner) -> ncp.Client:
    client = ncp.Client(Direct(owner), CONTRACT)
    client.open()
    return client


def act(agent: str, number: int, value=None) -> dict:
    return {"ncp.round": {"agent": agent, "round": number}, "value": agent if value is None else value}


def run_agents(plan, timeout=10.0):
    """Run each (name, function) of plan in its own thread; return name -> result or exception."""
    results: dict[str, object] = {}

    def run(name, function):
        try:
            results[name] = function()
        except Exception as error:  # noqa: BLE001 - the test inspects it
            results[name] = error

    threads = [threading.Thread(target=run, args=item, daemon=True) for item in plan]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout)
        if thread.is_alive():
            raise AssertionError("an agent did not finish")
    return results


def both_act(a: ncp.Client, b: ncp.Client, number: int) -> dict[str, object]:
    """Agents a and b each send round `number` at the same time."""
    return run_agents([("a", lambda: a.call("act", act("a", number))), ("b", lambda: b.call("act", act("b", number)))])


class RoundsTests(unittest.TestCase):
    def test_a_round_applies_the_requests_in_member_order_whatever_their_arrival(self) -> None:
        world = World()
        rounds = make_rounds(["a", "b", "c", "d"], world)
        clients = {name: client_for(rounds.owner()) for name in "abcd"}

        def agent(name, delay):
            def call():
                time.sleep(delay)
                return clients[name].call("act", act(name, 1))

            return call

        results = run_agents([(name, agent(name, 0.02 * i)) for i, name in enumerate("dbac")])
        self.assertEqual(world.rounds, [(1, ["a", "b", "c", "d"])])
        records = {name: ncp.RoundRecord.of(results[name], name) for name in "abcd"}
        self.assertEqual(len(set(records.values())), 1)  # every agent received the same record
        record = records["a"]
        self.assertEqual((record.round, record.agents, record.missing), (1, ("a", "b", "c", "d"), ()))
        self.assertEqual(record.requests, tuple(results[name].request for name in "abcd"))
        for position, name in enumerate("abcd"):
            self.assertEqual((results[name].body["value"], results[name].body["position"]), (name, position))

    def test_rounds_follow_each_other_in_lockstep(self) -> None:
        world = World()
        names = [f"agent-{i}" for i in range(8)]
        rounds = make_rounds(names, world)
        clients = {name: client_for(rounds.owner()) for name in names}
        records: dict[str, list[ncp.RoundRecord]] = {name: [] for name in names}

        def agent(name):
            def run():
                rng = random.Random(name)
                for number in range(1, 21):
                    time.sleep(rng.uniform(0, 0.002))
                    result = clients[name].call("act", act(name, number))
                    records[name].append(ncp.RoundRecord.of(result, name))
                return True

            return run

        results = run_agents([(name, agent(name)) for name in names])
        self.assertTrue(all(value is True for value in results.values()))
        self.assertEqual(world.rounds, [(number, names) for number in range(1, 21)])
        for number in range(20):
            self.assertEqual(len({records[name][number] for name in names}), 1)

    def test_a_member_without_a_request_at_the_deadline_is_excluded_and_does_not_delay_later_rounds(self) -> None:
        world = World()
        rounds = make_rounds(["a", "b", "c"], world, deadline=0.5)
        a, b, c = (client_for(rounds.owner()) for _ in range(3))
        started = time.monotonic()
        results = both_act(a, b, 1)
        self.assertGreaterEqual(time.monotonic() - started, 0.5)
        record = ncp.RoundRecord.of(results["a"], "a")
        self.assertEqual((record.agents, record.missing), (("a", "b"), ("c",)))
        self.assertEqual(rounds.excluded, {"c": 1})
        started = time.monotonic()
        results = both_act(a, b, 2)
        self.assertLess(time.monotonic() - started, 0.4)  # c is no longer waited for
        self.assertEqual(ncp.RoundRecord.of(results["b"], "b").missing, ())
        for number in (1, 3):
            with self.assertRaises(ncp.Declined) as caught:
                c.call("act", act("c", number))
            self.assertEqual(caught.exception.code, "body_invalid")
            self.assertIn("excluded", caught.exception.detail)

    def test_a_request_that_the_owner_accepted_before_the_deadline_is_in_the_round(self) -> None:
        # b's request is validated before the deadline and added after it: the round must wait
        # for it instead of closing without it.
        world = World()
        rounds = make_rounds(["a", "b", "c"], world, deadline=0.1)
        a = client_for(rounds.owner())
        slow_owner = rounds.owner()
        inner = slow_owner.handler
        reserved = threading.Event()

        class Slow:
            def validate(self, request):
                inner.validate(request)  # opens round 1 and reserves b's place
                reserved.set()
                time.sleep(0.5)  # past the deadline, before execute adds the request

            def execute(self, request):
                return inner.execute(request)

        slow_owner.handler = Slow()
        b = client_for(slow_owner)

        def a_after_b():
            reserved.wait(5)
            return a.call("act", act("a", 1))

        results = run_agents([("b", lambda: b.call("act", act("b", 1))), ("a", a_after_b)])
        record = ncp.RoundRecord.of(results["a"], "a")
        self.assertEqual((record.agents, record.missing), (("a", "b"), ("c",)))
        self.assertEqual(ncp.RoundRecord.of(results["b"], "b"), record)

    def test_invalid_round_requests_are_declined_and_change_nothing(self) -> None:
        world = World()
        rounds = make_rounds(["a", "b"], world)
        first, second = client_for(rounds.owner()), client_for(rounds.owner())
        for body, words in (
            ({"value": 1}, "ncp.round"),
            ({"ncp.round": {"agent": "a"}, "value": 1}, "ncp.round"),
            ({"ncp.round": {"agent": "a", "round": "1"}, "value": 1}, "integer"),
            (act("z", 1), "unknown agent"),
            (act("a", 2), "round 2 is not open"),
        ):
            with self.assertRaises(ncp.Declined) as caught:
                first.call("act", body)
            self.assertEqual(caught.exception.code, "body_invalid")
            self.assertIn(words, caught.exception.detail)

        def second_session_for_a():
            time.sleep(0.05)  # first is now waiting in round 1 as agent a
            try:
                second.call("act", act("a", 1))
            except ncp.Declined as error:
                rejection = error.detail
            return rejection, second.call("act", act("b", 1))

        results = run_agents([("a", lambda: first.call("act", act("a", 1))), ("other", second_session_for_a)])
        rejection, result_b = results["other"]
        self.assertIn("another session", rejection)
        self.assertEqual(ncp.RoundRecord.of(result_b, "b").agents, ("a", "b"))
        with self.assertRaises(ncp.Declined) as caught:
            first.call("act", act("b", 2))
        self.assertIn("belongs to another agent", caught.exception.detail)
        self.assertEqual(world.rounds, [(1, ["a", "b"])])

    def test_a_failed_step_ends_the_sessions_of_its_round_and_stops_the_rounds(self) -> None:
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        for broken in (
            lambda number, inputs: 1 / 0,
            lambda number, inputs: {inputs[0][0]: {}},  # no result for the second agent
            lambda number, inputs: {**{agent: {} for agent, _ in inputs}, "z": {}},  # a result for no agent
            lambda number, inputs: {agent: {"ncp.round_record": 1} for agent, _ in inputs},
        ):
            rounds = make_rounds(["a", "b"], broken)
            results = both_act(client_for(rounds.owner()), client_for(rounds.owner()), 1)
            for name in "ab":
                self.assertIsInstance(results[name], ncp.Ended)
                self.assertEqual((results[name].code, results[name].executed), ("owner_failure", "unknown"))
            self.assertIsNotNone(rounds.error)
            late = client_for(rounds.owner())
            with self.assertRaises(ncp.Declined) as caught:
                late.call("act", act("a", 2))
            self.assertIn("step failed", caught.exception.detail)

    def test_an_agent_checks_that_the_record_lists_its_own_request(self) -> None:
        rounds = make_rounds(["a", "b"], World())
        results = both_act(client_for(rounds.owner()), client_for(rounds.owner()), 1)
        with self.assertRaises(ncp.ProtocolError):
            ncp.RoundRecord.of(results["a"], "b")  # a's request listed as b's
        forged = ncp.Result(results["a"].body, results["a"].identity, results["a"].arrays, "0" * 64)
        with self.assertRaises(ncp.ProtocolError):
            ncp.RoundRecord.of(forged, "a")  # a request that the round did not apply
        with self.assertRaises(ncp.ProtocolError):
            ncp.RoundRecord.of(ncp.Result({"value": 1}, "0" * 64, [], "0" * 64), "a")

    def test_rounds_over_a_unix_domain_socket(self) -> None:
        world = World()
        names = [f"robot-{i}" for i in range(6)]
        rounds = make_rounds(names, world)
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "world.sock")
            server = ncp.UnixServer(rounds.owner, path).start()
            try:

                def agent(name):
                    def run():
                        client = ncp.Client(ncp.connect_unix(path), CONTRACT)
                        client.open()
                        seen = [ncp.RoundRecord.of(client.call("act", act(name, k)), name) for k in range(1, 6)]
                        client.close()
                        return seen

                    return run

                results = run_agents([(name, agent(name)) for name in names])
            finally:
                server.stop()
        self.assertEqual(world.rounds, [(k, names) for k in range(1, 6)])
        for k in range(5):
            self.assertEqual(len({results[name][k] for name in names}), 1)

    def test_a_member_whose_session_ended_may_take_a_new_session(self) -> None:
        world = World()
        rounds = make_rounds(["a", "b"], world)
        first_owner = rounds.owner()
        first, b = client_for(first_owner), client_for(rounds.owner())
        both_act(first, b, 1)
        first_owner.finish("lost")  # the connection of a's first session broke
        again = client_for(rounds.owner())
        results = both_act(again, b, 2)
        self.assertEqual(ncp.RoundRecord.of(results["a"], "a").agents, ("a", "b"))

    def test_members_and_deadline_are_checked(self) -> None:
        for members in ([], ["a", "a"], [""], ["x" * 129], [1]):
            with self.assertRaises(ValueError):
                make_rounds(members, World())
        with self.assertRaises(ValueError):
            make_rounds(["a"], World(), deadline=0)


if __name__ == "__main__":
    unittest.main()
