"""Telemetry message schema: construction and validation.

The schema mirrors the real VOLTREAD pipeline (ESP32 + INA219 publishing
JSON that a bridge stores and a dashboard renders):

    device_id          str    node identifier, e.g. "voltread-01"
    timestamp          str    ISO-8601 UTC timestamp of the sample
    seq                int    monotonically increasing sequence number
    battery_voltage_v  float  battery bus voltage, 2.50-4.35 V (1S Li-ion)
    battery_percent    float  state of charge, 0-100 %
    footsteps_total    int    lifetime footstep counter (>= 0)
    footsteps_delta    int    footsteps since the previous message (>= 0)
    power_mw           float  instantaneous harvested power, mW (>= 0)
    energy_total_mwh   float  cumulative harvested energy, mWh (>= 0)

`validate_message` returns a list of human-readable problems; an empty
list means the message is valid. The listener counts and reports every
invalid message instead of crashing on bad input from the wire.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

TOPIC_TELEMETRY = "voltread/telemetry"
TOPIC_STATUS = "voltread/status"

# Plausible physical ranges for a 1S Li-ion powered node.
VOLTAGE_RANGE = (2.50, 4.35)
PERCENT_RANGE = (0.0, 100.0)

REQUIRED_FIELDS = {
    "device_id": str,
    "timestamp": str,
    "seq": int,
    "battery_voltage_v": (int, float),
    "battery_percent": (int, float),
    "footsteps_total": int,
    "footsteps_delta": int,
    "power_mw": (int, float),
    "energy_total_mwh": (int, float),
}


def build_message(device_id: str, seq: int, battery_voltage_v: float,
                  battery_percent: float, footsteps_total: int,
                  footsteps_delta: int, power_mw: float,
                  energy_total_mwh: float,
                  timestamp: str | None = None) -> dict:
    """Assemble one telemetry message dict (see module docstring)."""
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        "device_id": device_id,
        "timestamp": timestamp,
        "seq": seq,
        "battery_voltage_v": round(float(battery_voltage_v), 3),
        "battery_percent": round(float(battery_percent), 2),
        "footsteps_total": int(footsteps_total),
        "footsteps_delta": int(footsteps_delta),
        "power_mw": round(float(power_mw), 4),
        "energy_total_mwh": round(float(energy_total_mwh), 6),
    }


def encode(message: dict) -> str:
    """Serialise a message to the JSON string put on the wire."""
    return json.dumps(message, separators=(",", ":"))


def decode(payload: str | bytes) -> dict:
    """Parse a wire payload back into a dict (raises ValueError)."""
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"payload is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("payload JSON is not an object")
    return data


def validate_message(data: dict) -> list[str]:
    """Return a list of validation problems (empty == valid)."""
    problems: list[str] = []
    for field, types in REQUIRED_FIELDS.items():
        if field not in data:
            problems.append(f"missing field: {field}")
            continue
        value = data[field]
        # bool is a subclass of int; reject it for numeric fields.
        if isinstance(value, bool) or not isinstance(value, types):
            problems.append(f"field {field}: wrong type "
                            f"({type(value).__name__})")
    if problems:
        return problems

    lo, hi = VOLTAGE_RANGE
    if not lo <= data["battery_voltage_v"] <= hi:
        problems.append(f"battery_voltage_v {data['battery_voltage_v']} "
                        f"outside plausible range {lo}-{hi} V")
    lo, hi = PERCENT_RANGE
    if not lo <= data["battery_percent"] <= hi:
        problems.append(f"battery_percent {data['battery_percent']} "
                        f"outside {lo}-{hi}")
    if data["seq"] < 0:
        problems.append("seq is negative")
    for field in ("footsteps_total", "footsteps_delta"):
        if data[field] < 0:
            problems.append(f"{field} is negative")
    for field in ("power_mw", "energy_total_mwh"):
        if data[field] < 0:
            problems.append(f"{field} is negative")
    if data["footsteps_delta"] > data["footsteps_total"]:
        problems.append("footsteps_delta exceeds footsteps_total")
    return problems
