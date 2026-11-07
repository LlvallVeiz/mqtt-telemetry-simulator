"""Command-line entry points: `sim`, `listen`, and `demo`.

* `sim`    — run only the simulated node (pair with a listener
             elsewhere; in mqtt mode that can be another terminal).
* `listen` — run only the listener; writes CSV + summary on exit.
* `demo`   — local mode only: simulator and listener in one process
             over the in-process bus; the fastest way to see the whole
             pipeline (this is what produced the files in examples/).
"""

from __future__ import annotations

import argparse
import sys

from . import schema
from .device import DeviceSim
from .listener import Listener
from .simulator import run_simulator
from .transport import make_transport


def _device_args(p: argparse.ArgumentParser):
    p.add_argument("--device-id", default="voltread-01")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--start-percent", type=float, default=87.0)
    p.add_argument("--load-mw", type=float, default=55.0)
    p.add_argument("--energy-per-step-uj", type=float, default=0.565)
    p.add_argument("--burst-probability", type=float, default=0.18)


def _transport_args(p: argparse.ArgumentParser):
    p.add_argument("--mode", choices=["local", "mqtt"], default="local")
    p.add_argument("--host", default="test.mosquitto.org")
    p.add_argument("--port", type=int, default=1883)


def _make_device(args) -> DeviceSim:
    return DeviceSim(device_id=args.device_id, seed=args.seed,
                     start_percent=args.start_percent,
                     load_mw=args.load_mw,
                     energy_per_step_uj=args.energy_per_step_uj,
                     burst_probability=args.burst_probability)


def _make_transport(args, role: str):
    if args.mode == "local":
        return make_transport("local")
    status = schema.TOPIC_STATUS if role == "sim" else None
    return make_transport("mqtt", host=args.host, port=args.port,
                          client_id=f"voltread-{role}",
                          status_topic=status)


def main_sim(argv=None) -> int:
    p = argparse.ArgumentParser(prog="simulator",
                                description="Simulated VOLTREAD node")
    _device_args(p)
    _transport_args(p)
    p.add_argument("--seconds", type=float, default=30)
    p.add_argument("--interval", type=float, default=1.0)
    args = p.parse_args(argv)

    transport = _make_transport(args, "sim")
    sent = run_simulator(transport, _make_device(args),
                         seconds=args.seconds, interval_s=args.interval)
    print(f"[sim] done: {sent} messages published "
          f"(mode={args.mode})")
    return 0


def main_listen(argv=None) -> int:
    p = argparse.ArgumentParser(prog="listener",
                                description="Telemetry listener")
    _transport_args(p)
    p.add_argument("--seconds", type=float, default=30)
    p.add_argument("--csv", default=None, help="write session CSV here")
    p.add_argument("--summary", default=None,
                   help="write summary text here")
    args = p.parse_args(argv)

    listener = Listener()
    transport = _make_transport(args, "listen")
    listener.run(transport, seconds=args.seconds)
    text = listener.summary_text()
    print(text)
    if args.csv:
        listener.write_csv(args.csv)
        print(f"[lst] CSV written to {args.csv}")
    if args.summary:
        with open(args.summary, "w") as fh:
            fh.write(text + "\n")
    return 0


def main_demo(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="demo", description="Simulator + listener in one process "
                                 "over the local in-process bus")
    _device_args(p)
    p.add_argument("--seconds", type=float, default=10)
    p.add_argument("--interval", type=float, default=1.0)
    p.add_argument("--csv", default=None)
    p.add_argument("--summary", default=None)
    args = p.parse_args(argv)

    bus = make_transport("local")
    listener = Listener()
    bus.connect()
    bus.subscribe(schema.TOPIC_TELEMETRY, listener.handle)
    run_simulator(bus, _make_device(args), seconds=args.seconds,
                  interval_s=args.interval, realtime=False)
    text = listener.summary_text()
    print(text)
    if args.csv:
        listener.write_csv(args.csv)
        print(f"[lst] CSV written to {args.csv}")
    if args.summary:
        with open(args.summary, "w") as fh:
            fh.write(text + "\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main_sim())
