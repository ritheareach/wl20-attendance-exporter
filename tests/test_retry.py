"""Retry behaviour: the app must wait out a busy or rebooting terminal."""

from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
