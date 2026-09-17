"""Retry behaviour: the app must wait out a busy or rebooting terminal."""

from __future__ import annotations

import contextlib
import sys
import time
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wl20_exporter import device  # noqa: E402
from wl20_exporter.models import DeviceInfo, DeviceRead, PunchRecord  # noqa: E402


def good_read() -> DeviceRead:
    return DeviceRead(info=DeviceInfo(host="192.168.88.245"),
                      records=[PunchRecord(user_id="STF-0001",
                                           timestamp=datetime(2026, 9, 15, 8, 0, 0))])


class FailNTimes:
    """Stands in for device.read_all: fails N times, then returns data."""

    def __init__(self, failures: int, error: str = "ZKNetworkError: [Errno 32] Broken pipe"):
        self.failures = failures
        self.error = error
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        if self.calls <= self.failures:
            raise device.DeviceError(self.error + "\n" + device.BUSY_HINT)
        return good_read()


class RetryTests(unittest.TestCase):
    def setUp(self):
        self.original = device.read_all
        self.addCleanup(lambda: setattr(device, "read_all", self.original))
        self.messages: list = []

    def log(self, message: str) -> None:
        self.messages.append(message)

    def test_single_attempt_by_default(self):
        fake = FailNTimes(failures=99)
        device.read_all = fake
        with self.assertRaises(device.DeviceError):
            device.read_with_retry(attempts=1, delay=0, log=self.log)
        self.assertEqual(fake.calls, 1, "a single attempt must not retry")

    def test_recovers_after_transient_failures(self):
        fake = FailNTimes(failures=2)
        device.read_all = fake
        read = device.read_with_retry(attempts=5, delay=0.01, log=self.log)
        self.assertEqual(fake.calls, 3)
        self.assertEqual(len(read.records), 1)
        self.assertTrue(any("Attempt 1 failed" in message for message in self.messages))
        self.assertTrue(any("Attempt 3" in message for message in self.messages))

    def test_gives_up_after_the_attempt_budget(self):
        fake = FailNTimes(failures=99)
        device.read_all = fake
        with self.assertRaises(device.DeviceError):
            device.read_with_retry(attempts=3, delay=0.01, log=self.log)
        self.assertEqual(fake.calls, 3)
        self.assertTrue(any("Giving up after 3 attempt" in message for message in self.messages))

    def test_wait_mode_keeps_trying_past_the_attempt_count(self):
        fake = FailNTimes(failures=4)
        device.read_all = fake
        read = device.read_with_retry(attempts=1, delay=0.01, wait_seconds=30, log=self.log)
        self.assertEqual(fake.calls, 5, "wait mode ignores the attempts budget")
        self.assertEqual(len(read.records), 1)

    def test_wait_mode_stops_at_the_deadline(self):
        fake = FailNTimes(failures=999)
        device.read_all = fake
        started = time.monotonic()
        with self.assertRaises(device.DeviceError):
            device.read_with_retry(delay=0.05, wait_seconds=0.3, log=self.log)
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 3.0)
        self.assertGreaterEqual(elapsed, 0.25)
        self.assertTrue(any("Giving up" in message for message in self.messages))

    def test_stop_flag_aborts_the_wait_promptly(self):
        fake = FailNTimes(failures=999)
        device.read_all = fake
        state = {"stop": False}

        def stop() -> bool:
            return state["stop"]

        def flip() -> None:
            time.sleep(0.2)
            state["stop"] = True

        import threading
        threading.Thread(target=flip, daemon=True).start()
        started = time.monotonic()
        with self.assertRaises(device.DeviceError) as caught:
            device.read_with_retry(delay=30, wait_seconds=3600, log=self.log, should_stop=stop)
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 2.0, "Stop must not wait out a 30s sleep")
        self.assertIn("cancelled", str(caught.exception))

    def test_interruptible_sleep_reports_cancellation(self):
        self.assertFalse(device._interruptible_sleep(0.05))
        self.assertTrue(device._interruptible_sleep(5, should_stop=lambda: True))


class FakeConnection:
    """Records that the reboot command was sent."""

    def __init__(self, owner):
        self.owner = owner

    def restart(self):
        self.owner.restarts += 1


class FakeSessions:
    """Stands in for device.device_session.

    ``fail_probes`` fails the first probes outright (a dead terminal);
    ``fail_after_restart`` fails the probes that follow a successful reboot,
    which is how a terminal behaves while it is still booting.
    """

    def __init__(self, fail_probes: int = 0, fail_after_restart: int = 0):
        self.fail_probes = fail_probes
        self.fail_after_restart = fail_after_restart
        self.probes = 0
        self.restarts = 0
        self.after_restart_failures = 0

    @contextlib.contextmanager
    def session(self, host, port=4370, password=0, timeout=10):
        self.probes += 1
        if self.probes <= self.fail_probes:
            raise device.DeviceError("ZKNetworkError: [Errno 113] No route to host\nhint")
        if self.restarts and self.after_restart_failures < self.fail_after_restart:
            self.after_restart_failures += 1
            raise device.DeviceError("ZKNetworkError: [Errno 111] Connection refused\nhint")
        yield FakeConnection(self)


class RestartTests(unittest.TestCase):
    def setUp(self):
        self.original_session = device.device_session
        self.original_read_all = device.read_all
        self.addCleanup(lambda: setattr(device, "device_session", self.original_session))
        self.addCleanup(lambda: setattr(device, "read_all", self.original_read_all))
        self.messages: list = []

    def log(self, message: str) -> None:
        self.messages.append(message)

    def test_restart_sends_the_reboot_command(self):
        fake = FakeSessions()
        device.device_session = fake.session
        self.assertTrue(device.restart_device(wait_seconds=0, progress=self.log))
        self.assertEqual(fake.restarts, 1, "CMD_RESTART must be sent exactly once")
        self.assertTrue(any("Reboot accepted" in message for message in self.messages))
        self.assertTrue(any("not lost" in message for message in self.messages))

    def test_restart_waits_until_the_terminal_answers_again(self):
        # A rebooted terminal refuses connections until it has finished booting.
        fake = FakeSessions(fail_after_restart=2)
        device.device_session = fake.session
        self.assertTrue(device.restart_device(wait_seconds=5, poll=0.05, progress=self.log))
        self.assertEqual(fake.restarts, 1)
        self.assertEqual(fake.probes, 4, "reboot + two failed probes + the successful one")
        self.assertTrue(any("back online" in message for message in self.messages))

    def test_restart_reports_when_the_command_cannot_be_sent(self):
        fake = FakeSessions(fail_probes=1)
        device.device_session = fake.session
        self.assertFalse(device.restart_device(wait_seconds=0, progress=self.log))
        self.assertEqual(fake.restarts, 0)
        self.assertTrue(any("Could not send the reboot command" in message
                            for message in self.messages))

    def test_wait_gives_up_when_the_terminal_never_returns(self):
        fake = FakeSessions(fail_probes=999)
        device.device_session = fake.session
        started = time.monotonic()
        self.assertFalse(device.wait_until_reachable(wait_seconds=0.3, poll=0.05,
                                                     progress=self.log))
        self.assertLess(time.monotonic() - started, 3.0)
        self.assertTrue(any("did not come back" in message for message in self.messages))

    def test_wait_can_be_stopped(self):
        fake = FakeSessions(fail_probes=999)
        device.device_session = fake.session
        started = time.monotonic()
        self.assertFalse(device.wait_until_reachable(wait_seconds=60, poll=5,
                                                     progress=self.log,
                                                     should_stop=lambda: True))
        self.assertLess(time.monotonic() - started, 1.0)

    def test_read_reboots_once_when_the_reads_keep_failing(self):
        fake_read = FailNTimes(failures=999)
        device.read_all = fake_read
        self.addCleanup(lambda: setattr(device, "read_all", self.original_read_all))
        reboots = []

        def fake_restart(*args, **kwargs):
            reboots.append(kwargs.get("host"))
            return True

        original_restart = device.restart_device
        device.restart_device = fake_restart
        self.addCleanup(lambda: setattr(device, "restart_device", original_restart))

        with self.assertRaises(device.DeviceError):
            device.read_with_retry(attempts=1, delay=0, log=self.log, restart_if_stuck=True)
        self.assertEqual(len(reboots), 1, "exactly one reboot attempt")
        self.assertEqual(fake_read.calls, 2, "one read before the reboot, one after")
        self.assertTrue(any("one more read attempt" in message for message in self.messages))

    def test_read_does_not_reboot_unless_asked(self):
        fake_read = FailNTimes(failures=999)
        device.read_all = fake_read
        self.addCleanup(lambda: setattr(device, "read_all", self.original_read_all))
        called = []
        original_restart = device.restart_device
        device.restart_device = lambda *args, **kwargs: called.append(True) or True
        self.addCleanup(lambda: setattr(device, "restart_device", original_restart))
        with self.assertRaises(device.DeviceError):
            device.read_with_retry(attempts=1, delay=0, log=self.log)
        self.assertEqual(called, [], "rebooting must stay opt-in")


class CliRestartTests(unittest.TestCase):
    def setUp(self):
        self.messages: list = []
        self.original_restart = device.restart_device
        self.addCleanup(lambda: setattr(device, "restart_device", self.original_restart))

    def test_cli_restart_reports_success(self):
        from wl20_exporter import cli

        device.restart_device = lambda *args, **kwargs: kwargs["progress"]("Reboot accepted") or True
        self.assertEqual(cli.main(["--restart", "--host", "10.0.0.5"]), 0)

    def test_cli_restart_reports_failure(self):
        from wl20_exporter import cli

        device.restart_device = lambda *args, **kwargs: False
        self.assertEqual(cli.main(["--restart", "--host", "10.0.0.5"]), 1)

    def test_cli_restart_passes_the_wait_window(self):
        from wl20_exporter import cli

        seen = {}

        def fake(host, **kwargs):
            seen.update(kwargs)
            return True

        device.restart_device = fake
        cli.main(["--restart", "--host", "10.0.0.5", "--restart-wait", "45"])
        self.assertEqual(seen["wait_seconds"], 45.0)
        self.assertEqual(seen["port"], 4370)


if __name__ == "__main__":
    unittest.main()
