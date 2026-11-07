#!/usr/bin/env python3
"""Entry point: run the telemetry listener.

Usage:
    python3 listener.py [--mode local|mqtt] [--seconds N]
                        [--csv session.csv] [--summary summary.txt]

In local mode a listener alone hears nothing (the bus is in-process);
use `python3 simulator.py demo` for a self-contained local session, or
mqtt mode with a simulator running in another terminal.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from mqtt_sim import cli  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(cli.main_listen(sys.argv[1:]))
