"""Tests for the local bus and an end-to-end local demo session."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mqtt_sim import schema  # noqa: E402
from mqtt_sim.device import DeviceSim  # noqa: E402
from mqtt_sim.listener import Listener  # noqa: E402
from mqtt_sim.simulator import run_simulator  # noqa: E402
from mqtt_sim.transport import LocalBus  # noqa: E402


def test_pub_sub_and_topic_isolation():
    bus = LocalBus()
    got, other = [], []
    bus.connect()
    bus.subscribe("voltread/telemetry", lambda t, p: got.append(p))
    bus.subscribe("voltread/status", lambda t, p: other.append(p))
    bus.publish("voltread/telemetry", "hello")
    assert got == ["hello"]
    assert other == []


def test_retained_replayed_to_late_subscriber():
    bus = LocalBus()
    bus.connect()
    bus.publish("voltread/status", "online", retain=True)
    late = []
    bus.subscribe("voltread/status", lambda t, p: late.append(p))
    assert late == ["online"]
    # an empty retained payload clears the retained message
    bus.publish("voltread/status", "", retain=True)
    later = []
    bus.subscribe("voltread/status", lambda t, p: later.append(p))
    assert later == []


def test_end_to_end_demo_session():
    bus = LocalBus()
    listener = Listener(echo=False)
    bus.connect()
    bus.subscribe(schema.TOPIC_TELEMETRY, listener.handle)
    sent = run_simulator(bus, DeviceSim(seed=42), seconds=10,
                         interval_s=1.0, realtime=False, echo=False)
    assert sent == 10
    summary = listener.summary()
    assert summary["messages"] == 10
    assert summary["invalid"] == 0
    assert summary["seq_gaps"] == 0
    rows = listener.csv_text().strip().splitlines()
    assert rows[0].startswith("seq,timestamp,")
    assert len(rows) == 11  # header + 10 records


def test_listener_counts_invalid():
    listener = Listener(echo=False)
    listener.handle("voltread/telemetry", "not json")
    listener.handle("voltread/telemetry", '{"device_id": 1}')
    assert listener.invalid == 2
    assert listener.records == []


if __name__ == "__main__":
    test_pub_sub_and_topic_isolation()
    test_retained_replayed_to_late_subscriber()
    test_end_to_end_demo_session()
    test_listener_counts_invalid()
    print("test_local_bus: all passed")
