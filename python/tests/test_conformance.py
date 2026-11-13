"""Run the shared conformance vectors (conformance/vectors.json) against the Python SDK."""

from __future__ import annotations

import logging
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from ncp import conformance as K  # noqa: E402

VECTORS = K.load(os.path.join(HERE, "..", "..", "conformance", "vectors.json"))


class ConformanceTests(unittest.TestCase):
    def setUp(self) -> None:
        logging.disable(logging.CRITICAL)  # the scenarios make the application fail on purpose
        self.addCleanup(logging.disable, logging.NOTSET)

    def test_frames(self) -> None:
        self.assertEqual(K.run_frames(VECTORS, K.python_decode), [])

    def test_messages(self) -> None:
        self.assertEqual(K.run_messages(VECTORS), [])

    def test_authenticated_frames(self) -> None:
        self.assertEqual(K.run_auth(VECTORS), [])

    def test_owner_scenarios(self) -> None:
        failures, skipped = K.run_scenarios(VECTORS, K.python_owner(VECTORS))
        self.assertEqual((failures, skipped), ([], 0))

    def test_client_rules(self) -> None:
        self.assertEqual(K.run_clients(VECTORS), [])

    def test_streams(self) -> None:
        self.assertEqual(K.run_streams(VECTORS), [])

    def test_transcripts(self) -> None:
        self.assertEqual(K.run_transcripts(VECTORS), [])

    def test_contracts(self) -> None:
        self.assertEqual(K.run_contracts(VECTORS), [])

    def test_schemas(self) -> None:
        self.assertEqual(K.run_schemas(VECTORS), [])


if __name__ == "__main__":
    unittest.main()
