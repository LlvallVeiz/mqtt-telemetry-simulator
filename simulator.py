#!/usr/bin/env python3
"""Entry point: run the simulated VOLTREAD telemetry node.

Usage:
    python3 simulator.py sim  [--mode local|mqtt] [--seconds N] ...
    python3 simulator.py demo [--seconds N] [--csv out.csv] ...

`demo` runs node + listener together in-process (no network needed).
See README.md for the full option list.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from mqtt_sim import cli  # noqa: E402

if __name__ == "__main__":
    argv = sys.argv[1:]
    if argv and argv[0] == "demo":
        raise SystemExit(cli.main_demo(argv[1:]))
    if argv and argv[0] == "sim":
        argv = argv[1:]
    raise SystemExit(cli.main_sim(argv))
