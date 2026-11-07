"""Transports: one interface, two implementations.

Both the simulator and the listener talk to a transport object with
this interface (a deliberately tiny subset of MQTT semantics):

    connect() / disconnect()
    publish(topic, payload, qos=0, retain=False)
    subscribe(topic, callback)   # callback(topic, payload_str)
    wait_for(timeout_s)          # block/drain for a while (listener)

`LocalBus` is an in-process publish/subscribe bus: simulator and
listener in the same process exchange messages with zero network. It
implements exact-topic matching (the only subscription this project
uses) and retained messages (a retained payload is stored and replayed
to later subscribers, as a broker does). It does NOT emulate broker
behaviours that need a broker: Last Will delivery on ungraceful
disconnect, QoS handshakes, or wildcard matching — see
docs/RESEARCH.md for which MQTT features each mode really exercises.

`PahoTransport` uses the Eclipse Paho Python client against a real
broker (default the public test broker test.mosquitto.org:1883) and
exercises the wire protocol — QoS, retained status messages and a
Last Will ("offline") on `voltread/status` — whenever a broker is
actually reachable. In restricted sandboxes whose egress blocks MQTT
(as in the environment this project was developed in — see
docs/RESEARCH.md §4), it fails cleanly with a descriptive error and
`LocalBus` is the working path.
"""

from __future__ import annotations

import time
from typing import Callable

Callback = Callable[[str, str], None]


class LocalBus:
    """In-process pub/sub bus with retained-message support."""

    def __init__(self):
        self._subs: dict[str, list[Callback]] = {}
        self._retained: dict[str, str] = {}
        self.connected = False

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.connected = False

    def subscribe(self, topic: str, callback: Callback):
        self._subs.setdefault(topic, []).append(callback)
        if topic in self._retained:
            callback(topic, self._retained[topic])

    def publish(self, topic: str, payload: str, qos: int = 0,
                retain: bool = False):
        if retain:
            if payload:
                self._retained[topic] = payload
            else:
                self._retained.pop(topic, None)
        for callback in list(self._subs.get(topic, [])):
            callback(topic, payload)

    def wait_for(self, timeout_s: float):
        # Delivery is synchronous, so there is nothing to drain; the
        # listener loop simply sleeps to let wall-clock time pass.
        time.sleep(timeout_s)


class PahoTransport:
    """MQTT transport backed by Eclipse Paho (optional dependency)."""

    def __init__(self, host: str = "test.mosquitto.org", port: int = 1883,
                 client_id: str = "voltread-sim",
                 status_topic: str | None = None):
        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:  # pragma: no cover - env dependent
            raise RuntimeError(
                "paho-mqtt is not installed; either `pip install "
                "paho-mqtt` or use --mode local") from exc
        import threading
        self._mqtt = mqtt
        self.host, self.port = host, port
        self.status_topic = status_topic
        self._callbacks: dict[str, list[Callback]] = {}
        self._connected = threading.Event()
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        self.client.on_message = self._on_message
        self.client.on_connect = self._on_connect
        if status_topic:
            # Last Will: if this client drops ungracefully, the broker
            # publishes "offline" (retained) on the status topic.
            self.client.will_set(status_topic, payload="offline",
                                 qos=1, retain=True)

    # -- paho plumbing -------------------------------------------------
    def _on_connect(self, client, userdata, flags, reason_code, props):
        # Subscriptions are (re)issued here, not in subscribe(): this is
        # the canonical paho pattern — it guarantees the SUBSCRIBE goes
        # out only after CONNACK, and re-establishes subscriptions
        # after an automatic reconnect.
        if int(reason_code) == 0:
            for topic in self._callbacks:
                client.subscribe(topic)
            self._connected.set()

    def _on_message(self, client, userdata, msg):
        payload = msg.payload.decode("utf-8", errors="replace")
        for callback in list(self._callbacks.get(msg.topic, [])):
            callback(msg.topic, payload)

    # -- interface ------------------------------------------------------
    def connect(self):
        self.client.connect(self.host, self.port, keepalive=30)
        self.client.loop_start()
        if not self._connected.wait(timeout=10):
            raise RuntimeError(
                f"could not connect to MQTT broker "
                f"{self.host}:{self.port} within 10 s")
        if self.status_topic:
            self.publish(self.status_topic, "online", qos=1, retain=True)

    def disconnect(self):
        if self.status_topic:
            self.publish(self.status_topic, "offline", qos=1, retain=True)
        self.client.loop_stop()
        self.client.disconnect()

    def subscribe(self, topic: str, callback: Callback):
        first = topic not in self._callbacks
        self._callbacks.setdefault(topic, []).append(callback)
        # If we are already connected, subscribe right away; otherwise
        # _on_connect issues the subscription when CONNACK arrives.
        if first and self._connected.is_set():
            self.client.subscribe(topic)

    def publish(self, topic: str, payload: str, qos: int = 0,
                retain: bool = False):
        self.client.publish(topic, payload, qos=qos, retain=retain)

    def wait_for(self, timeout_s: float):
        time.sleep(timeout_s)  # network loop runs in paho's thread


def make_transport(mode: str, **kwargs):
    """Factory: mode "local" -> LocalBus, mode "mqtt" -> PahoTransport."""
    if mode == "local":
        return LocalBus()
    if mode == "mqtt":
        return PahoTransport(**kwargs)
    raise ValueError(f"unknown mode: {mode!r} (expected 'local' or 'mqtt')")
