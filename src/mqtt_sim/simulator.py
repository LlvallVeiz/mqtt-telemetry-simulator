"""Simulator runner: advance a DeviceSim and publish each tick."""

from __future__ import annotations

import time

from . import schema
from .device import DeviceSim


def run_simulator(transport, device: DeviceSim, seconds: float,
                  interval_s: float = 1.0, realtime: bool = True,
                  echo: bool = True) -> int:
    """Publish telemetry for `seconds` of simulated time.

    Returns the number of messages published. With `realtime=False`
    the ticks run back-to-back without sleeping (used by tests/demo).
    """
    transport.connect()
    ticks = int(seconds // interval_s)
    sent = 0
    try:
        for _ in range(ticks):
            values = device.tick(interval_s)
            message = schema.build_message(
                device_id=device.device_id, **values)
            transport.publish(schema.TOPIC_TELEMETRY,
                              schema.encode(message))
            sent += 1
            if echo:
                print(f"[sim] seq={message['seq']:>3} "
                      f"V={message['battery_voltage_v']:.2f} "
                      f"pct={message['battery_percent']:5.2f} "
                      f"steps+={message['footsteps_delta']:>2} "
                      f"P={message['power_mw']:.4f} mW "
                      f"E={message['energy_total_mwh']:.6f} mWh",
                      flush=True)
            if realtime and sent < ticks:
                time.sleep(interval_s)
    finally:
        transport.disconnect()
    return sent
