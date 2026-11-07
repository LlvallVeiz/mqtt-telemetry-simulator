"""Tests for the telemetry schema: build, round-trip, validation."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mqtt_sim import schema  # noqa: E402


def good_message(**overrides):
    msg = schema.build_message(
        device_id="voltread-01", seq=7, battery_voltage_v=3.91,
        battery_percent=82.5, footsteps_total=120, footsteps_delta=5,
        power_mw=0.31, energy_total_mwh=1.25,
        timestamp="2026-11-08T01:00:00+00:00")
    msg.update(overrides)
    return msg


def test_build_and_roundtrip():
    msg = good_message()
    assert schema.validate_message(msg) == []
    back = schema.decode(schema.encode(msg))
    assert back == msg


def test_missing_field_rejected():
    msg = good_message()
    del msg["power_mw"]
    problems = schema.validate_message(msg)
    assert any("power_mw" in p for p in problems)


def test_wrong_type_rejected():
    problems = schema.validate_message(good_message(seq="seven"))
    assert any("seq" in p for p in problems)
    problems = schema.validate_message(good_message(battery_percent=True))
    assert any("battery_percent" in p for p in problems)


def test_range_checks():
    assert schema.validate_message(good_message(battery_voltage_v=5.1))
    assert schema.validate_message(good_message(battery_percent=101))
    assert schema.validate_message(good_message(footsteps_delta=-1))
    assert schema.validate_message(good_message(power_mw=-0.5))
    # delta larger than the lifetime counter is inconsistent
    assert schema.validate_message(
        good_message(footsteps_total=3, footsteps_delta=9))


def test_decode_rejects_garbage():
    for payload in ("not json", "[1,2,3]", ""):
        try:
            schema.decode(payload)
        except ValueError:
            pass
        else:  # pragma: no cover
            raise AssertionError(f"accepted garbage payload {payload!r}")


if __name__ == "__main__":
    test_build_and_roundtrip()
    test_missing_field_rejected()
    test_wrong_type_rejected()
    test_range_checks()
    test_decode_rejects_garbage()
    print("test_schema: all passed")
