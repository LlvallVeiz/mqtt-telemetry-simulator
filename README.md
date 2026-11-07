# MQTT Telemetry Simulator

A simulator of a **VOLTREAD-style ESP32 telemetry node** plus a
validating **listener**, in Python. The node publishes JSON telemetry
(battery, footsteps, harvested power/energy) to the MQTT topic
`voltread/telemetry`; the listener subscribes, validates every message
against the schema, prints a live table, and writes a session CSV with
summary statistics.

Two transports share one interface:

- **`--mode local` (default)** — an in-process pub/sub bus: node and
  listener in one process, **zero network, zero dependencies**.
- **`--mode mqtt`** — a real broker via Eclipse Paho (default the
  public test broker `test.mosquitto.org:1883`), exercising QoS,
  retained status messages and a Last Will. See *Verification status*
  below for an honest account of testing this mode.

## Background

MQTT is a lightweight publish/subscribe protocol for constrained
devices (OASIS standards 3.1.1 and 5.0). A *broker* routes messages
published to hierarchical *topics* to subscribed clients. The features
that matter for a battery-powered sensor node:

- **QoS 0/1/2** — at-most-once / at-least-once / exactly-once delivery.
- **Retained messages** — the broker stores the last retained message
  per topic and replays it to new subscribers (used here for the
  node's `voltread/status`: `online`/`offline`).
- **Last Will (LWT)** — a message the broker publishes for a client
  that disappears ungracefully; the simulator registers "offline" as
  its Will.
- **Keep alive** — the client's liveness promise to the broker
  (30 s here).

The simulated schema mirrors the real VOLTREAD pipeline (ESP32 +
INA219 → MQTT → bridge → database → dashboard), including its
per-step harvested-energy figure of 0.565 µJ from the project's CPE103
design model. Full protocol background, sources, and the schema
mapping are in [docs/RESEARCH.md](docs/RESEARCH.md).

The device model is small but internally consistent:

- **Battery**: state of charge is the state variable; voltage is
  derived from a typical 18650 discharge curve (lookup +
  interpolation). A constant load drains the cell; harvested step
  energy charges it.
- **Footsteps**: bursty pedestrian traffic — mostly quiet ticks,
  occasional bursts from a seeded RNG (fully reproducible runs).
- **Energy**: `energy_total = Σ power_mw · Δt` holds exactly, by
  construction — a test asserts it.

## Project structure

```text
mqtt-telemetry-simulator/
├── simulator.py            # entry point: node (`sim` / `demo`)
├── listener.py             # entry point: listener
├── requirements.txt        # paho-mqtt — ONLY for --mode mqtt
├── src/mqtt_sim/
│   ├── schema.py           # message build / encode / validate
│   ├── device.py           # battery curve, step bursts, energy math
│   ├── transport.py        # LocalBus + PahoTransport (one interface)
│   ├── simulator.py        # publish loop
│   ├── listener.py         # validate, tabulate, CSV, summary
│   └── cli.py              # argparse wiring for both entry points
├── tests/
│   ├── test_schema.py      # build/round-trip/range/type validation
│   ├── test_device.py      # curve, determinism, energy consistency
│   └── test_local_bus.py   # pub/sub, retained replay, end-to-end
├── examples/               # outputs of the verified local demo run
└── docs/RESEARCH.md        # protocol sources & verification notes
```

## How to run

No dependencies are needed for local mode.

```bash
# Self-contained demo: node + listener in one process (local bus)
python3 simulator.py demo --seconds 120 --seed 42 \
    --csv session.csv --summary summary.txt

# Tests
for t in tests/test_*.py; do python3 "$t"; done
```

Real broker mode (needs `pip install paho-mqtt`, e.g. in a venv):

```bash
# terminal 1 — listener
python3 listener.py --mode mqtt --seconds 60 --csv session.csv

# terminal 2 — node
python3 simulator.py sim --mode mqtt --seconds 30
```

Both default to `test.mosquitto.org:1883` and topic
`voltread/telemetry`; use `--host`/`--port` for your own broker (the
real VOLTREAD deployment uses EMQX with TLS — pass the TLS port and
extend `PahoTransport` with `tls_set()` for that).

## Example output

From the committed local demo (`examples/example_output.txt`,
120 simulated seconds, seed 42):

```text
=== session summary ===
device              : voltread-01
valid messages      : 120
invalid messages    : 0
missing seq numbers : 0
footsteps (session) : 175
energy harvested    : 0.000027 mWh
mean power          : 0.0008 mW
battery             : 87.00% -> 86.98%
```

The harvested energies look tiny because they are honest: one
footstep delivers ~0.565 µJ, so 175 steps ≈ 99 µJ ≈ 0.000027 mWh,
while the 55 mW background load dominates the battery over minutes —
exactly the energy reality the real harvesting tile lives with.

## Verification status

- **Local mode**: fully verified — all tests pass and the demo
  session in `examples/` (120/120 valid messages, 0 sequence gaps,
  energy integral consistent) was produced by running the code.
- **MQTT mode**: code-complete against the Paho API, but **not**
  end-to-end verified, because the development sandbox's egress proxy
  blocks MQTT (plain 1883 handshake silently dropped, WebSocket
  upgrade refused, 8883 answered in plain HTTP). The transport detects
  this and exits with a descriptive error instead of hanging.
  Details and evidence: docs/RESEARCH.md §4.

## Design decisions

- **One transport interface, two implementations** — simulator and
  listener code never branch on the mode; the local bus implements
  the subset of MQTT semantics used here (exact topics, retained
  replay) and says so in its docstring.
- **Subscriptions are issued in Paho's `on_connect`** — the canonical
  pattern from the Paho docs; subscribing immediately after
  `connect()` races CONNACK and loses subscriptions on reconnect.
- **The listener never crashes on bad input** — invalid payloads are
  counted with reasons, mirroring what a production bridge must do
  when a node misbehaves.
- **Seeded everything** — same seed ⇒ identical telemetry stream,
  which is what makes the tests and the committed examples exact.

## Limitations & future work

- LocalBus does not emulate wildcards, QoS handshakes, or Will
  delivery on ungraceful disconnect (documented in `transport.py`).
- The battery curve is a generic 18650 curve, not a fit to a specific
  cell; percent is integrated in the energy domain, which ignores
  rate-dependent capacity effects.
- Natural next steps: TLS + authentication for the EMQX deployment,
  a `voltread/commands` downlink (the real system uses it for relay
  control and lamp schedules), and a bridge that writes the listener's
  CSV stream into SQLite/Supabase like the production one.
