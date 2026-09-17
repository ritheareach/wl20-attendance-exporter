"""Diagnostics: the failure text must say *which* problem this is.

'Cannot connect to the terminal' has two very different causes -- the terminal
is busy, or this computer cannot reach it at all -- and they look identical in
a raw socket error. The helpers below turn that into a plain sentence, and the
reported network must match the machine actually running the app.
"""

from __future__ import annotations

import socket
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wl20_exporter import device  # noqa: E402


class NetworkHintTests(unittest.TestCase):
    def test_same_subnet_is_reported_as_not_a_network_problem(self):
        hint = device.network_hint("192.168.88.245", "192.168.88.55")
        self.assertIn("same network", hint)
        self.assertIn("192.168.88.x", hint)
        self.assertNotIn("different networks", hint)

    def test_neighbouring_third_octet_is_the_same_larger_range(self):
        # the office LAN is a /23: 192.168.88.x and 192.168.89.x are one network
        hint = device.network_hint("192.168.88.245", "192.168.89.30")
        self.assertIn("same larger range", hint)
        self.assertNotIn("different networks", hint)

    def test_other_subnet_is_reported_as_a_network_mismatch(self):
        hint = device.network_hint("192.168.88.245", "192.168.1.55")
        self.assertIn("different networks", hint)
        self.assertIn("192.168.1.x", hint)
        self.assertIn("192.168.88.x", hint)

    def test_far_apart_subnets_are_a_mismatch(self):
        hint = device.network_hint("192.168.88.245", "10.42.0.7")
        self.assertIn("different networks", hint)

    def test_hostname_or_garbage_falls_back_to_the_plain_fact(self):
        hint = device.network_hint("wl20.local", "192.168.88.55")
        self.assertIn("would reach wl20.local from 192.168.88.55", hint)

    def test_nothing_is_said_without_both_addresses(self):
        self.assertEqual(device.network_hint("", "192.168.88.55"), "")
        self.assertEqual(device.network_hint("192.168.88.245", ""), "")

    def test_every_verdict_is_a_single_line(self):
        # the GUI shows this in a dialog, so no wrapping into a paragraph
        for local in ("192.168.88.55", "192.168.89.55", "192.168.1.55"):
            hint = device.network_hint("192.168.88.245", local)
            self.assertTrue(hint)
            self.assertEqual(len(hint.splitlines()), 1, hint)


class LocalAddressTests(unittest.TestCase):
    def test_loopback_reports_itself(self):
        self.assertEqual(device.local_address_for("127.0.0.1"), "127.0.0.1")

    def test_empty_host_is_not_probed(self):
        self.assertEqual(device.local_address_for(""), "")

    def test_unresolvable_host_does_not_raise(self):
        # must never blow up inside the error handler that calls it
        self.assertIsInstance(device.local_address_for("no-such-host.invalid"), str)

    def test_route_lookup_sends_nothing(self):
        """The probe is a UDP connect: no packets, so it is safe during a read."""
        created = []
        real_socket = socket.socket

        def spy(*args, **kwargs):
            instance = real_socket(*args, **kwargs)
            created.append(instance)
            return instance

        with mock.patch.object(device.socket, "socket", side_effect=spy):
            device.local_address_for("192.168.88.245")
        self.assertTrue(created, "expected a probe socket")
        for instance in created:
            self.assertEqual(instance.type, socket.SOCK_DGRAM)


class ExplainTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(device, "local_address_for",
                                    lambda host, port=0: "10.7.7.7")
        self.addCleanup(patcher.stop)
        patcher.start()

    def test_refused_connection_mentions_the_network_mismatch(self):
        text = device._explain(OSError("[Errno 111] Connection refused"),
                               host="192.168.88.245", port=4370)
        self.assertIn("Connection refused", text)
        self.assertIn(device.UNREACHABLE_HINT, text)
        self.assertIn("different networks", text)
        self.assertNotIn(device.BUSY_HINT, text)

    def test_timeout_mentions_the_busy_terminal_not_the_network(self):
        text = device._explain(socket.timeout("timed out"),
                               host="192.168.88.245", port=4370)
        self.assertIn(device.BUSY_HINT, text)
        self.assertNotIn(device.UNREACHABLE_HINT, text)
        self.assertIn("different networks", text)  # 10.7.7.7 vs 192.168.88.x

    def test_same_network_timeout_points_at_the_terminal_being_busy(self):
        with mock.patch.object(device, "local_address_for",
                               lambda host, port=0: "192.168.88.217"):
            text = device._explain(socket.timeout("timed out"),
                                   host="192.168.88.245", port=4370)
        self.assertIn(device.BUSY_HINT, text)
        self.assertIn("same network", text)

    def test_no_host_keeps_the_old_two_line_shape(self):
        text = device._explain(OSError("[Errno 111] Connection refused"))
        self.assertIn(device.UNREACHABLE_HINT, text)
        self.assertNotIn("This computer", text)


if __name__ == "__main__":
    unittest.main()
