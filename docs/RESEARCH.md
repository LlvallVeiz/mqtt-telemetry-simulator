# Background & Research — MQTT Telemetry Simulator

This document records the protocol sources the implementation is built
on, the design choices they drove, and — in §4 — an honest account of
what could and could not be verified from the development sandbox.
Every source below was consulted while writing the code.

## 1. MQTT, the protocol: OASIS standards

MQTT is an OASIS-standard publish/subscribe messaging protocol for
constrained devices and unreliable networks [1][2]. The concepts this
project uses, and where the specifications define them:

* **Publish/subscribe over topics** — clients publish messages to a
  *topic* on a broker; the broker forwards each message to clients
  subscribed to that topic (MQTT 3.1.1 §3.3, MQTT 5.0 §3.3). Topics are
  hierarchical UTF-8 strings (`voltread/telemetry`); subscriptions may
  use the wildcards `+` (single level) and `#` (multi level)
  (MQTT 3.1.1 §4.7).
* **QoS levels** — delivery guarantees negotiated per message:
  QoS 0 "at most once" (fire and forget), QoS 1 "at least once"
  (acknowledged, duplicates possible), QoS 2 "exactly once"
  (four-part handshake) (MQTT 3.1.1 §4.3). Telemetry that is re-sent
  every second tolerates QoS 0/1; the node's *status* here uses QoS 1
  because a lost "offline" matters more than a lost sample.
* **Retained messages** — a PUBLISH flagged RETAIN is stored by the
  broker and delivered immediately to future subscribers of the topic
  (MQTT 3.1.1 §3.3.1.3). Used here for `voltread/status` so a listener
  that starts late still learns the node's last known state at once.
* **Last Will and Testament (LWT)** — at CONNECT time a client may
  register a Will message; if the client's connection ends
  ungracefully, the broker publishes it on its behalf
  (MQTT 3.1.1 §3.1.2.5). The simulator registers Will = "offline"
  (retained, QoS 1) on `voltread/status` and publishes a graceful
  retained "online"/"offline" itself when it can.
* **Keep alive** — the client promises to talk to the broker within
  the keep-alive interval (PINGREQ/PINGRESP); the broker disconnects
  silent clients at 1.5× the interval, which is also what triggers the
  Will (MQTT 3.1.1 §3.1.2.10). PahoTransport uses 30 s.
* **Sessions** — MQTT 5.0 replaced 3.1.1's "clean session" flag with
  clean-start + session-expiry semantics (MQTT 5.0 §3.1.2.4); this
  project does not depend on session state and works with either
  version's defaults.

Accessible introductions that agree with the specifications — HiveMQ's
*MQTT Essentials* series [3] and EMQX's MQTT guide [4] — were used to
cross-check terminology (both describe the same QoS/retain/Will
semantics as the standards).

## 2. The client library: Eclipse Paho (Python)

`PahoTransport` is written against the Eclipse Paho Python client [5],
the reference MQTT client library from the Eclipse Foundation. Two
implementation details come straight from its documented usage
patterns:

* **Subscriptions are (re)issued inside `on_connect`.** Paho's own
  documentation warns that subscribing directly after `connect()` can
  race the CONNACK, and that putting subscriptions in the connect
  callback both fixes the race and restores them after reconnects.
  This project first shipped the racy version; §4 describes the
  (unrelated) network failure that prompted the audit that fixed it.
* **Last Will is registered with `will_set()` before `connect()`** —
  a Will cannot be added once the connection exists, because it is
  part of the CONNECT packet itself [1].

## 3. Why the schema mirrors VOLTREAD

VOLTREAD is a piezoelectric energy-harvesting floor tile: an ESP32 with
an INA219 power monitor publishes JSON telemetry that an MQTT bridge
stores in Supabase for a web dashboard. The production system moved
from HTTP ingestion to MQTT (EMQX broker) precisely for the properties
in §1 — a broker decouples the node from its consumers, retained
status survives node reboots, and QoS 1 covers an unreliable site
network. This simulator reproduces the *shape* of that system so the
listener/validation logic can be developed and tested without
hardware:

| Real VOLTREAD | This simulator |
|---|---|
| ESP32 + INA219 node | `DeviceSim` (battery curve, step bursts) |
| EMQX broker, topic `voltread/telemetry` | LocalBus, or any broker via Paho |
| Bridge validation before storage | `schema.validate_message` in the listener |
| Dashboard session view | Listener live table + CSV + summary |
| Per-step harvested energy 0.565 µJ (CPE103 model) | `energy_per_step_uj` default |

The battery model inverts the real data flow on purpose: the firmware
*measures* voltage and estimates percent; the simulator *chooses*
percent (state variable) and derives voltage from a typical 18650
discharge curve, so listener code sees the same joint distribution of
(V, %) it would see from hardware.

## 4. Verification environment: what the sandbox allowed

The development sandbox has proxied egress. Raw TCP to
`test.mosquitto.org:1883` *connects*, but the MQTT handshake never
completes (no CONNACK is ever returned — the proxy accepts the socket
and drops non-HTTP protocol bytes). Two fallbacks were attempted:
MQTT over WebSockets on port 8080 (proxy refused the upgrade:
"connection not upgraded") and TLS on port 8883 (the peer answered in
plain HTTP — `SSL: WRONG_VERSION_NUMBER` — the signature of an HTTP
intercepting proxy). Conclusion: **no external MQTT broker is usable
from this sandbox**, so:

* `--mode local` (in-process bus) is the default and is fully
  verified: unit/integration tests plus a 120-message demo session
  whose outputs are committed under `examples/`.
* `--mode mqtt` is code-complete against Paho and fails *cleanly*
  where the network blocks it (a descriptive `RuntimeError` after a
  10 s connect timeout rather than a hang or silent message loss).
  On any unrestricted network the same two commands
  (`simulator.py sim --mode mqtt`, `listener.py --mode mqtt`) run
  against the public test broker unchanged.

## References

1. *MQTT Version 3.1.1*, OASIS Standard, 2014 —
   https://docs.oasis-open.org/mqtt/mqtt/v3.1.1/mqtt-v3.1.1.html
2. *MQTT Version 5.0*, OASIS Standard, 2019 —
   https://docs.oasis-open.org/mqtt/mqtt/v5.0/mqtt-v5.0.html
3. HiveMQ, *MQTT Essentials* (QoS, retained messages, Last Will,
   keep alive) — https://www.hivemq.com/mqtt-essentials/
4. EMQX, *MQTT Guide / MQTT 5.0 introduction* —
   https://www.emqx.com/en/blog/mqtt-5-introduction-to-mqtt-5-0
5. Eclipse Paho, *Python MQTT client documentation* —
   https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html
6. Eclipse Mosquitto, *public test broker* (test.mosquitto.org) —
   https://test.mosquitto.org/
