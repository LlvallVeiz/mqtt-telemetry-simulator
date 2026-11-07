"""Simulated VOLTREAD node: battery, footsteps and harvested energy.

The physics is deliberately small but internally consistent:

* **Battery** — a 1S Li-ion cell. State of charge (percent) is the state
  variable; bus voltage is *derived* from it through a discharge-curve
  lookup (a typical 18650 curve under light load), the same way the real
  firmware estimates percent from the INA219 bus voltage — here run in
  the opposite direction. A constant background load drains the cell;
  harvested step energy charges it back.
* **Footsteps** — pedestrian traffic arrives in bursts: most ticks are
  quiet, occasionally a "passer-by" produces a burst of steps. A seeded
  `random.Random` makes every run reproducible.
* **Energy** — each footstep delivers a fixed amount of energy
  (`energy_per_step_uj`, default 0.565 µJ — the per-step figure from the
  VOLTREAD CPE103 design model). Instantaneous power is the energy
  delivered in the tick divided by the tick length; cumulative energy is
  its running integral, so `energy_total == Σ power_mw · Δt` holds by
  construction (a test asserts exactly that).
"""

from __future__ import annotations

import bisect
import random

# Typical 1S Li-ion (18650) discharge curve under light load:
# (state of charge %, bus voltage V), ascending in percent.
DISCHARGE_CURVE: list[tuple[float, float]] = [
    (0.0, 3.00), (5.0, 3.35), (10.0, 3.55), (20.0, 3.65), (30.0, 3.70),
    (40.0, 3.73), (50.0, 3.76), (60.0, 3.80), (70.0, 3.86), (80.0, 3.93),
    (90.0, 4.02), (95.0, 4.10), (100.0, 4.20),
]

UJ_PER_MWH = 3.6e6  # 1 mWh = 3.6 J = 3.6e6 µJ


def voltage_from_percent(percent: float) -> float:
    """Map state of charge (%) to bus voltage via the discharge curve.

    Piecewise-linear interpolation; clamps outside 0-100 %.
    The curve is strictly increasing, so the mapping is monotonic.
    """
    percent = min(100.0, max(0.0, percent))
    xs = [p for p, _ in DISCHARGE_CURVE]
    i = bisect.bisect_left(xs, percent)
    if i == 0:
        return DISCHARGE_CURVE[0][1]
    if i >= len(DISCHARGE_CURVE):
        return DISCHARGE_CURVE[-1][1]
    (x0, y0), (x1, y1) = DISCHARGE_CURVE[i - 1], DISCHARGE_CURVE[i]
    if x1 == x0:
        return y0
    frac = (percent - x0) / (x1 - x0)
    return y0 + frac * (y1 - y0)


class DeviceSim:
    """A seeded, deterministic simulated telemetry node.

    Parameters mirror the quantities a builder would tune on the real
    node: battery capacity, background load, per-step harvested energy
    and how bursty the pedestrian traffic is.
    """

    def __init__(self, device_id: str = "voltread-01", seed: int = 42,
                 battery_capacity_mwh: float = 9900.0,
                 start_percent: float = 87.0,
                 load_mw: float = 55.0,
                 energy_per_step_uj: float = 0.565,
                 burst_probability: float = 0.18,
                 burst_max_steps: int = 14):
        self.device_id = device_id
        self.rng = random.Random(seed)
        self.capacity_mwh = float(battery_capacity_mwh)
        self.percent = float(start_percent)
        self.load_mw = float(load_mw)
        self.energy_per_step_mwh = float(energy_per_step_uj) / UJ_PER_MWH
        self.burst_probability = float(burst_probability)
        self.burst_max_steps = int(burst_max_steps)
        self.footsteps_total = 0
        self.energy_total_mwh = 0.0
        self.seq = 0

    def _steps_this_tick(self) -> int:
        """Bursty pedestrian model: quiet ticks, occasional bursts."""
        if self.rng.random() < self.burst_probability:
            return self.rng.randint(1, self.burst_max_steps)
        return 0

    def tick(self, dt_s: float) -> dict:
        """Advance the simulation by `dt_s` seconds; return raw values.

        Order of operations per tick: footsteps harvest energy, the
        background load drains the battery for the whole interval, then
        state of charge is updated from the net energy flow.
        """
        steps = self._steps_this_tick()
        harvested_mwh = steps * self.energy_per_step_mwh
        load_mwh = self.load_mw * dt_s / 3600.0

        self.footsteps_total += steps
        self.energy_total_mwh += harvested_mwh
        net_mwh = harvested_mwh - load_mwh
        self.percent = min(100.0, max(
            0.0, self.percent + 100.0 * net_mwh / self.capacity_mwh))

        # Instantaneous harvested power over this tick, in mW:
        # P = E / t with E in mWh and t in hours -> mW.
        power_mw = harvested_mwh / (dt_s / 3600.0) if dt_s > 0 else 0.0

        self.seq += 1
        return {
            "seq": self.seq,
            "battery_voltage_v": voltage_from_percent(self.percent),
            "battery_percent": self.percent,
            "footsteps_total": self.footsteps_total,
            "footsteps_delta": steps,
            "power_mw": power_mw,
            "energy_total_mwh": self.energy_total_mwh,
        }
