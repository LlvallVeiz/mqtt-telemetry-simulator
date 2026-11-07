"""Tests for the device model: battery curve, determinism, energy math."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mqtt_sim.device import DeviceSim, voltage_from_percent  # noqa: E402


def test_curve_endpoints_and_monotonicity():
    assert voltage_from_percent(0) == 3.00
    assert voltage_from_percent(100) == 4.20
    prev = -1.0
    for pct in range(0, 101, 5):
        v = voltage_from_percent(pct)
        assert v > prev, f"curve not increasing at {pct}%"
        prev = v
    # clamping outside the range
    assert voltage_from_percent(-10) == 3.00
    assert voltage_from_percent(250) == 4.20


def test_determinism_same_seed():
    a = DeviceSim(seed=42)
    b = DeviceSim(seed=42)
    seq_a = [a.tick(1.0) for _ in range(60)]
    seq_b = [b.tick(1.0) for _ in range(60)]
    assert seq_a == seq_b
    c = DeviceSim(seed=7)
    seq_c = [c.tick(1.0) for _ in range(60)]
    assert seq_a != seq_c


def test_counters_and_energy_consistency():
    dev = DeviceSim(seed=42)
    total_power_dt = 0.0
    last_total = 0
    for _ in range(120):
        out = dev.tick(1.0)
        assert out["footsteps_total"] >= last_total
        assert out["footsteps_total"] - last_total == out["footsteps_delta"]
        last_total = out["footsteps_total"]
        total_power_dt += out["power_mw"] * (1.0 / 3600.0)  # mW * h = mWh
    # cumulative energy is exactly the time-integral of power
    assert abs(dev.energy_total_mwh - total_power_dt) < 1e-9
    assert dev.footsteps_total > 0  # bursts happened within 120 ticks


def test_battery_drains_under_load_without_steps():
    dev = DeviceSim(seed=1, burst_probability=0.0)
    start = dev.percent
    for _ in range(3600):  # one simulated hour of ticks at dt=1s
        dev.tick(1.0)
    # 55 mW for 1 h from a 9900 mWh cell: ~0.56 % drop
    drop = start - dev.percent
    assert 0.4 < drop < 0.7, drop
    assert dev.energy_total_mwh == 0.0


def test_harvest_offsets_drain():
    busy = DeviceSim(seed=3, burst_probability=1.0, burst_max_steps=14)
    idle = DeviceSim(seed=3, burst_probability=0.0)
    for _ in range(600):
        busy.tick(1.0)
        idle.tick(1.0)
    assert busy.percent > idle.percent
    assert busy.energy_total_mwh > 0.0


if __name__ == "__main__":
    test_curve_endpoints_and_monotonicity()
    test_determinism_same_seed()
    test_counters_and_energy_consistency()
    test_battery_drains_under_load_without_steps()
    test_harvest_offsets_drain()
    print("test_device: all passed")
