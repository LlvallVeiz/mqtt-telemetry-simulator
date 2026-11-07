"""Listener: subscribe, validate, tabulate, and summarise a session.

Every incoming payload is parsed and validated against the schema.
Valid messages are printed as a live table row and appended to the
session records; invalid ones are counted (with the first few problems
shown) instead of aborting the session — the behaviour you want when a
real node misbehaves on the wire.
"""

from __future__ import annotations

import csv
import io
import time

from . import schema

CSV_FIELDS = ["seq", "timestamp", "battery_voltage_v", "battery_percent",
              "footsteps_total", "footsteps_delta", "power_mw",
              "energy_total_mwh"]


class Listener:
    def __init__(self, echo: bool = True):
        self.records: list[dict] = []
        self.invalid = 0
        self.invalid_notes: list[str] = []
        self.echo = echo

    # -- transport callback ---------------------------------------------
    def handle(self, topic: str, payload: str):
        try:
            data = schema.decode(payload)
        except ValueError as exc:
            self._note_invalid(str(exc))
            return
        problems = schema.validate_message(data)
        if problems:
            self._note_invalid("; ".join(problems))
            return
        self.records.append(data)
        if self.echo:
            print(f"[lst] seq={data['seq']:>3} "
                  f"V={data['battery_voltage_v']:.2f} "
                  f"pct={data['battery_percent']:5.2f} "
                  f"steps={data['footsteps_total']:>4} "
                  f"(+{data['footsteps_delta']:>2}) "
                  f"P={data['power_mw']:.4f} mW "
                  f"E={data['energy_total_mwh']:.6f} mWh", flush=True)

    def _note_invalid(self, note: str):
        self.invalid += 1
        if len(self.invalid_notes) < 5:
            self.invalid_notes.append(note)
        if self.echo:
            print(f"[lst] INVALID message ignored: {note}", flush=True)

    # -- session ---------------------------------------------------------
    def run(self, transport, seconds: float):
        """Subscribe and collect for `seconds` of wall-clock time."""
        transport.connect()
        try:
            transport.subscribe(schema.TOPIC_TELEMETRY, self.handle)
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                transport.wait_for(min(0.25, deadline - time.monotonic()))
        finally:
            transport.disconnect()

    # -- reporting ---------------------------------------------------------
    def summary(self) -> dict:
        n = len(self.records)
        if n == 0:
            return {"messages": 0, "invalid": self.invalid}
        powers = [r["power_mw"] for r in self.records]
        first, last = self.records[0], self.records[-1]
        return {
            "messages": n,
            "invalid": self.invalid,
            "device_id": last["device_id"],
            "footsteps_total": last["footsteps_total"],
            "steps_in_session": last["footsteps_total"]
                                - first["footsteps_total"]
                                + first["footsteps_delta"],
            "energy_total_mwh": last["energy_total_mwh"],
            "mean_power_mw": sum(powers) / n,
            "max_power_mw": max(powers),
            "battery_percent_start": first["battery_percent"],
            "battery_percent_end": last["battery_percent"],
            "seq_gaps": (last["seq"] - first["seq"] + 1) - n,
        }

    def summary_text(self) -> str:
        s = self.summary()
        lines = ["=== session summary ==="]
        if s["messages"] == 0:
            lines.append("no valid messages received")
            lines.append(f"invalid messages: {s['invalid']}")
            return "\n".join(lines)
        lines += [
            f"device              : {s['device_id']}",
            f"valid messages      : {s['messages']}",
            f"invalid messages    : {s['invalid']}",
            f"missing seq numbers : {s['seq_gaps']}",
            f"footsteps (session) : {s['steps_in_session']}",
            f"footsteps (total)   : {s['footsteps_total']}",
            f"energy harvested    : {s['energy_total_mwh']:.6f} mWh",
            f"mean power          : {s['mean_power_mw']:.4f} mW",
            f"max power           : {s['max_power_mw']:.4f} mW",
            f"battery             : {s['battery_percent_start']:.2f}% -> "
            f"{s['battery_percent_end']:.2f}%",
        ]
        return "\n".join(lines)

    def csv_text(self) -> str:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for record in self.records:
            writer.writerow({k: record[k] for k in CSV_FIELDS})
        return buf.getvalue()

    def write_csv(self, path: str):
        with open(path, "w", newline="") as fh:
            fh.write(self.csv_text())
