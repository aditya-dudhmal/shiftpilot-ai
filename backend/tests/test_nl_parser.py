"""NL parser tests: correct parses, and rejections, not guesses."""
from app.nl_parser import parse_instruction, validate_llm_constraint
from app.seed import SEED_EMPLOYEES


def _emps():
    return [{"name": e["name"], "role": e["role"],
             "max_hours_per_week": e["max_hours_per_week"],
             "availability": e["availability"]} for e in SEED_EMPLOYEES]


def test_fewer_evening_shifts():
    r = parse_instruction("Give Alex fewer evening shifts next week", _emps())
    assert r["ok"] and r["kind"] == "limit_evening_shifts"
    assert r["employee_name"] == "Alex Morgan" and r["payload"]["max"] == 1


def test_day_off():
    r = parse_instruction("Don't schedule Maya on Friday", _emps())
    assert r["ok"] and r["kind"] == "day_off" and r["payload"]["day"] == "Friday"


def test_max_hours():
    r = parse_instruction("Cap Priya at 20 hours", _emps())
    assert r["ok"] and r["kind"] == "max_hours" and r["payload"]["max_hours"] == 20


def test_min_hours_over_max_is_rejected():
    # Sam's max is 16h; a 24h minimum contradicts it.
    r = parse_instruction("Sam needs at least 24 hours", _emps())
    assert not r["ok"]


def test_unknown_employee_is_rejected_not_guessed():
    r = parse_instruction("Give Zebra fewer evening shifts", _emps())
    assert not r["ok"] and "couldn't find" in r["error"]


def test_gibberish_is_rejected():
    assert not parse_instruction("hello there", _emps())["ok"]


def test_llm_validation_rejects_unknown_employee():
    ok, _ = validate_llm_constraint(
        {"kind": "day_off", "employee_name": "Nobody Real", "payload": {"day": "Monday"}},
        _emps())
    assert not ok


def test_llm_validation_rejects_bad_hours():
    ok, _ = validate_llm_constraint(
        {"kind": "max_hours", "employee_name": "Alex Morgan", "payload": {"max_hours": 33}},
        _emps())
    assert not ok  # 33 is not a multiple of 4
