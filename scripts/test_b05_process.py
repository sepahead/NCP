#!/usr/bin/env python3
"""Exercise B05 process cleanup with simulated observations and owned processes."""

from __future__ import annotations

import importlib.util
import os
import selectors
import signal
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SOURCE = Path(__file__).with_name("run_b05_preflight.py")
SPEC = importlib.util.spec_from_file_location("b05_process_runner", SOURCE)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load the selected B05 runner")
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)
REAL_KILLPG = os.killpg
REAL_POPEN = subprocess.Popen
REAL_READ = os.read
REAL_SELECTOR = selectors.DefaultSelector


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, duration: float) -> None:
        self.now += duration


class ObservationControls(unittest.TestCase):
    def setUp(self) -> None:
        self.process = mock.Mock(pid=123456, returncode=0)
        self.process.poll.return_value = 0
        self.process.wait.return_value = 0
        self.clock = Clock()
        self.enterContext(
            mock.patch.object(RUNNER.time, "monotonic", self.clock.monotonic)
        )
        self.enterContext(mock.patch.object(RUNNER.time, "sleep", self.clock.sleep))

    def test_only_esrch_proves_group_absence(self) -> None:
        with mock.patch.object(RUNNER.os, "killpg", side_effect=ProcessLookupError):
            self.assertFalse(RUNNER.group_exists(self.process))
        self.process.poll.assert_called_once_with()

    def test_exited_leader_does_not_resolve_permission_error(self) -> None:
        with mock.patch.object(RUNNER.os, "killpg", side_effect=PermissionError):
            with self.assertRaises(PermissionError):
                RUNNER.group_exists(self.process)

    def test_transient_permission_error_requires_later_esrch(self) -> None:
        with mock.patch.object(
            RUNNER.os, "killpg", side_effect=[PermissionError(), ProcessLookupError()]
        ):
            self.assertTrue(RUNNER.wait_for_group_exit(self.process, 0.1))
        self.assertEqual(self.clock.now, 0.05)

    def test_persistent_permission_error_fails_at_original_deadline(self) -> None:
        with mock.patch.object(RUNNER.os, "killpg", side_effect=PermissionError):
            with self.assertRaisesRegex(SystemExit, "cannot inspect.*cleanup deadline"):
                RUNNER.wait_for_group_exit(self.process, 0.1)
        self.assertEqual(self.clock.now, 0.1)

    def test_existing_group_exhausts_bound_without_claiming_absence(self) -> None:
        with mock.patch.object(RUNNER.os, "killpg", return_value=None):
            self.assertFalse(RUNNER.wait_for_group_exit(self.process, 0.1))
        self.assertEqual(self.clock.now, 0.1)

    def test_later_existence_resolves_only_observation_uncertainty(self) -> None:
        with mock.patch.object(
            RUNNER.os, "killpg", side_effect=[PermissionError(), None, None]
        ):
            self.assertFalse(RUNNER.wait_for_group_exit(self.process, 0.1))

    def test_term_denial_uses_full_grace_then_kill_esrch_resolves_it(self) -> None:
        events = []
        killed = False

        def signal_group(_pid: int, number: int) -> None:
            nonlocal killed
            events.append((self.clock.now, number))
            if number == signal.SIGKILL:
                killed = True
                return
            if killed:
                raise ProcessLookupError
            raise PermissionError

        with mock.patch.object(RUNNER.os, "killpg", side_effect=signal_group):
            RUNNER.terminate_process_group(self.process)
        self.assertEqual(events[0], (0.0, signal.SIGTERM))
        self.assertIn((float(RUNNER.TERMINATION_GRACE_SECONDS), signal.SIGKILL), events)
        self.assertEqual(self.clock.now, RUNNER.TERMINATION_GRACE_SECONDS)
        self.process.wait.assert_called_once_with(timeout=RUNNER.KILL_GRACE_SECONDS)

    def test_persistent_denial_escalates_and_reaps_but_fails(self) -> None:
        with mock.patch.object(
            RUNNER.os, "killpg", side_effect=PermissionError
        ) as calls:
            with self.assertRaisesRegex(SystemExit, "cannot inspect"):
                RUNNER.terminate_process_group(self.process)
        self.assertEqual(
            [item.args[1] for item in calls.call_args_list if item.args[1]],
            [signal.SIGTERM, signal.SIGKILL],
        )
        self.assertEqual(
            self.clock.now, RUNNER.TERMINATION_GRACE_SECONDS + RUNNER.KILL_GRACE_SECONDS
        )
        self.process.wait.assert_called_once_with(timeout=RUNNER.KILL_GRACE_SECONDS)

    def test_surviving_group_fails_even_after_leader_exit(self) -> None:
        with mock.patch.object(RUNNER.os, "killpg", return_value=None):
            with self.assertRaisesRegex(SystemExit, "survived termination"):
                RUNNER.terminate_process_group(self.process)
        self.process.wait.assert_called_once_with(timeout=RUNNER.KILL_GRACE_SECONDS)

    def test_unexpected_observation_error_still_reaps(self) -> None:
        with mock.patch.object(
            RUNNER.os, "killpg", side_effect=OSError("injected I/O")
        ):
            with self.assertRaisesRegex(SystemExit, "injected I/O"):
                RUNNER.terminate_process_group(self.process)
        self.process.wait.assert_called_once_with(timeout=RUNNER.KILL_GRACE_SECONDS)

    def test_leader_wait_retry_occurs_even_if_fallback_signal_fails(self) -> None:
        self.process.wait.side_effect = [subprocess.TimeoutExpired("owned", 2), 0]
        self.process.kill.side_effect = PermissionError("injected signal denial")
        with mock.patch.object(RUNNER.os, "killpg", side_effect=ProcessLookupError):
            with self.assertRaisesRegex(SystemExit, "leader signal failed"):
                RUNNER.terminate_process_group(self.process)
        self.assertEqual(self.process.wait.call_count, 2)
        self.process.kill.assert_called_once_with()


class RealProcessControls(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = self.enterContext(
            tempfile.TemporaryDirectory(prefix="ncp-b05-proc-")
        )
        self.root = Path(self.temporary)
        self.owned = []
        self.signals = []
        self.enterContext(mock.patch.object(RUNNER, "ROOT", self.root))
        self.enterContext(mock.patch.object(RUNNER.subprocess, "Popen", self.launch))
        self.enterContext(mock.patch.object(RUNNER.os, "killpg", self.signal_group))
        self.addCleanup(self.cleanup_owned)

    def launch(self, *args, **kwargs):
        process = REAL_POPEN(*args, **kwargs)
        self.owned.append(process)
        return process

    def signal_group(self, pid: int, number: int) -> None:
        self.signals.append((pid, number))
        REAL_KILLPG(pid, number)

    def cleanup_owned(self) -> None:
        # Signal only Popen handles created by this test, never discovered PIDs.
        for process in self.owned:
            try:
                REAL_KILLPG(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                pass
            process.wait(timeout=3)
            if process.stdout is not None:
                process.stdout.close()

    def assert_group_gone_and_leader_reaped(self) -> None:
        for process in self.owned:
            self.assertIsNotNone(process.returncode, "owned leader was not reaped")
            with self.assertRaises(ProcessLookupError):
                REAL_KILLPG(process.pid, 0)

    def run_command(self, text: str, timeout: float = 0.2, maximum: int = 1024):
        return RUNNER.run_bounded(
            ["/bin/bash", "-c", text], timeout_seconds=timeout, maximum=maximum
        )

    def assert_descendant_absent(self) -> None:
        pid = int((self.root / "child.pid").read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_success_preserves_exact_output(self) -> None:
        self.assertEqual(
            self.run_command("printf 'payload'", timeout=2), (0, b"payload")
        )
        self.assert_group_gone_and_leader_reaped()
        self.assertFalse(any(number for _, number in self.signals))

    def test_nonzero_exit_preserves_code_and_output(self) -> None:
        self.assertEqual(
            self.run_command("printf 'failure'; exit 7", timeout=2), (7, b"failure")
        )
        self.assert_group_gone_and_leader_reaped()

    def test_exact_output_bound_is_accepted(self) -> None:
        self.assertEqual(
            self.run_command("printf '%*s' 1024 ''", timeout=2), (0, b" " * 1024)
        )
        self.assert_group_gone_and_leader_reaped()

    def test_output_bound_plus_one_is_rejected(self) -> None:
        with self.assertRaisesRegex(SystemExit, "exceeded its output byte limit"):
            self.run_command("printf '%*s' 1025 ''; exec sleep 30", timeout=2)
        self.assert_group_gone_and_leader_reaped()

    def test_term_responsive_timeout_does_not_need_kill(self) -> None:
        with self.assertRaisesRegex(SystemExit, "exceeded its timeout"):
            self.run_command("exec sleep 30")
        self.assertIn(signal.SIGTERM, [number for _, number in self.signals])
        self.assertNotIn(signal.SIGKILL, [number for _, number in self.signals])
        self.assert_group_gone_and_leader_reaped()

    def test_term_resistant_descendant_requires_kill(self) -> None:
        with self.assertRaisesRegex(SystemExit, "exceeded its timeout"):
            self.run_command(
                "trap '' TERM; sleep 30 & child=$!; "
                'printf \'%s\' "$child" > child.pid; wait "$child"'
            )
        self.assertIn(signal.SIGKILL, [number for _, number in self.signals])
        self.assert_group_gone_and_leader_reaped()
        self.assert_descendant_absent()

    def test_successful_leader_cannot_leave_closed_output_descendant(self) -> None:
        self.assertEqual(
            self.run_command(
                "trap '' TERM; sleep 30 >/dev/null 2>&1 & "
                "printf '%s' \"$!\" > child.pid; exit 0",
                timeout=4,
            ),
            (0, b""),
        )
        self.assertIn(signal.SIGKILL, [number for _, number in self.signals])
        self.assert_group_gone_and_leader_reaped()
        self.assert_descendant_absent()

    def test_descendant_that_exits_within_existing_grace_is_accepted(self) -> None:
        self.assertEqual(
            self.run_command("sleep 0.1 >/dev/null 2>&1 & exit 0", timeout=2),
            (0, b""),
        )
        self.assert_group_gone_and_leader_reaped()
        self.assertFalse(any(number for _, number in self.signals))

    def test_closed_output_descendant_cannot_extend_execution_deadline(self) -> None:
        with self.assertRaisesRegex(SystemExit, "exceeded its timeout"):
            self.run_command("sleep 30 >/dev/null 2>&1 & exit 0")
        self.assert_group_gone_and_leader_reaped()

    def test_exited_leader_with_inherited_output_descendant_times_out(self) -> None:
        with self.assertRaisesRegex(SystemExit, "exceeded its timeout"):
            self.run_command(
                "trap '' TERM; sleep 30 & printf '%s' \"$!\" > child.pid; exit 0"
            )
        self.assert_group_gone_and_leader_reaped()
        self.assert_descendant_absent()

    def test_closed_output_with_live_leader_times_out(self) -> None:
        with self.assertRaisesRegex(SystemExit, "exceeded its timeout"):
            self.run_command("exec >/dev/null 2>&1; exec sleep 30")
        self.assert_group_gone_and_leader_reaped()

    def test_selector_construction_failure_cleans_up(self) -> None:
        with mock.patch.object(
            RUNNER.selectors,
            "DefaultSelector",
            side_effect=OSError("injected constructor"),
        ):
            with self.assertRaisesRegex(OSError, "injected constructor"):
                self.run_command("exec sleep 30")
        self.assert_group_gone_and_leader_reaped()

    def test_selector_registration_failure_cleans_up(self) -> None:
        selector = REAL_SELECTOR()
        with mock.patch.object(
            selector, "register", side_effect=OSError("injected registration")
        ):
            with mock.patch.object(
                RUNNER.selectors, "DefaultSelector", return_value=selector
            ):
                with self.assertRaisesRegex(OSError, "injected registration"):
                    self.run_command("exec sleep 30")
        self.assert_group_gone_and_leader_reaped()

    def test_output_read_failure_cleans_up(self) -> None:
        def read(descriptor: int, count: int) -> bytes:
            if self.owned and descriptor == self.owned[-1].stdout.fileno():
                raise OSError("injected output read")
            return REAL_READ(descriptor, count)

        with mock.patch.object(RUNNER.os, "read", side_effect=read):
            with self.assertRaisesRegex(OSError, "injected output read"):
                self.run_command("printf 'ready'; exec sleep 30")
        self.assert_group_gone_and_leader_reaped()

    def test_transient_inspection_denial_resolves_without_cleanup_failure(self) -> None:
        denials = 2

        def signal_group(pid: int, number: int) -> None:
            nonlocal denials
            if number == 0 and denials:
                denials -= 1
                raise PermissionError("injected transient observation")
            self.signal_group(pid, number)

        with mock.patch.object(RUNNER.os, "killpg", side_effect=signal_group):
            with self.assertRaises(SystemExit) as result:
                self.run_command("exec sleep 30")
        self.assertEqual(str(result.exception), "bounded command exceeded its timeout")
        self.assertEqual(denials, 0)
        self.assert_group_gone_and_leader_reaped()

    def test_persistent_inspection_denial_preserves_timeout_and_cleanup_error(
        self,
    ) -> None:
        def signal_group(pid: int, number: int) -> None:
            if number == 0:
                raise PermissionError("injected persistent observation")
            self.signal_group(pid, number)

        with mock.patch.object(RUNNER.os, "killpg", side_effect=signal_group):
            with self.assertRaises(SystemExit) as result:
                self.run_command("exec sleep 30")
        self.assertIn(
            "bounded command exceeded its timeout; cleanup failed:",
            str(result.exception),
        )
        self.assertIn("cannot inspect", str(result.exception))
        self.assert_group_gone_and_leader_reaped()

    def test_signal_denial_then_confirmed_kill_preserves_only_primary_error(
        self,
    ) -> None:
        def signal_group(pid: int, number: int) -> None:
            if number == signal.SIGTERM:
                raise PermissionError("injected TERM denial")
            self.signal_group(pid, number)

        with mock.patch.object(RUNNER.os, "killpg", side_effect=signal_group):
            with self.assertRaises(SystemExit) as result:
                self.run_command("exec sleep 30")
        self.assertEqual(str(result.exception), "bounded command exceeded its timeout")
        self.assertIn(signal.SIGKILL, [number for _, number in self.signals])
        self.assert_group_gone_and_leader_reaped()

    def test_persistent_inspection_denial_preserves_output_failure(self) -> None:
        def signal_group(pid: int, number: int) -> None:
            if number == 0:
                raise PermissionError("injected persistent observation")
            self.signal_group(pid, number)

        with mock.patch.object(RUNNER.os, "killpg", side_effect=signal_group):
            with self.assertRaises(SystemExit) as result:
                self.run_command("printf '%*s' 1025 ''; exec sleep 30", timeout=2)
        self.assertIn(
            "bounded command exceeded its output byte limit; cleanup failed:",
            str(result.exception),
        )
        self.assertIn("cannot inspect", str(result.exception))
        self.assert_group_gone_and_leader_reaped()


if __name__ == "__main__":
    unittest.main(verbosity=2)
