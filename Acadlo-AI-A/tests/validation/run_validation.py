#!/usr/bin/env python3
"""Run validation scenarios against the tutor API.

Usage:
  python -m tests.validation.run_validation [--base-url URL] [--scenario ID] [--category CATEGORY]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def _post_json(url: str, payload: dict, timeout: int = 60) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        raise RuntimeError(f"HTTP {e.code}: {body}") from e


def load_scenarios(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_start(base_url: str, setup: dict, initial_message: str = None) -> dict:
    url = f"{base_url.rstrip('/')}/v1/tutor/start"
    payload = {
        "tenant_id": setup["tenant_id"],
        "student_id": setup["student_id"],
        "lesson_id": setup.get("lesson_id", "pending"),
        "locale": setup.get("locale", "en-US"),
    }
    if setup.get("objective_ids") is not None:
        payload["objective_ids"] = setup["objective_ids"]
    if setup.get("objectives") is not None:
        payload["objectives"] = setup["objectives"]
    if initial_message:
        payload["initial_student_message"] = initial_message
    # If no objectives and no lesson, use pending
    if not payload.get("objective_ids") and not payload.get("objectives"):
        payload["lesson_id"] = payload.get("lesson_id") or "pending"
        payload["objective_ids"] = []
    return _post_json(url, payload)


def run_turn(base_url: str, tenant_id: str, session_id: str, student_message: str) -> dict:
    url = f"{base_url.rstrip('/')}/v1/tutor/turn"
    return _post_json(
        url,
        {
            "tenant_id": tenant_id,
            "session_id": session_id,
            "student_message": student_message,
        },
    )


def check_expected(reply: str, lesson_complete: bool, expected: dict) -> list:
    failures = []
    reply_lower = (reply or "").lower()
    if expected.get("contains_any"):
        if not any(s.lower() in reply_lower for s in expected["contains_any"]):
            failures.append(f"contains_any: reply did not contain any of {expected['contains_any']}")
    if expected.get("contains_all"):
        for s in expected["contains_all"]:
            if s.lower() not in reply_lower:
                failures.append(f"contains_all: reply did not contain '{s}'")
    if expected.get("must_not_contain"):
        for s in expected["must_not_contain"]:
            if s.lower() in reply_lower:
                failures.append(f"must_not_contain: reply contained '{s}'")
    if "lesson_complete" in expected:
        if lesson_complete != expected["lesson_complete"]:
            failures.append(f"lesson_complete: expected {expected['lesson_complete']}, got {lesson_complete}")
    if expected.get("mcq_format"):
        if not any(x in reply for x in ["A)", "B)", "C)", "D)"]):
            failures.append("mcq_format: reply did not contain A) B) C) D) options")
    return failures


def run_scenario(base_url: str, scenario: dict) -> tuple:
    scenario_id = scenario["id"]
    setup = scenario["setup"]
    turns = scenario.get("turns", [])
    all_failures = []
    session_id = None
    tenant_id = setup["tenant_id"]

    for turn_spec in turns:
        turn_num = turn_spec["turn"]
        action = turn_spec.get("action", "turn")
        user_input = turn_spec.get("input")
        expected = turn_spec.get("expected") or {}

        if action == "start":
            resp = run_start(base_url, setup, initial_message=user_input)
            session_id = resp["session_id"]
            reply = resp.get("tutor_reply", "")
            lesson_complete = resp.get("lesson_complete", False)
        else:
            if not session_id:
                all_failures.append(f"Turn {turn_num}: no session_id (start may have failed)")
                break
            resp = run_turn(base_url, tenant_id, session_id, user_input or "")
            reply = resp.get("tutor_reply", "")
            lesson_complete = resp.get("lesson_complete", False)

        failures = check_expected(reply, lesson_complete, expected)
        for f in failures:
            all_failures.append(f"Turn {turn_num}: {f} [reply snippet: {(reply or '')[:120]}...]")

    return len(all_failures) == 0, all_failures


def main():
    parser = argparse.ArgumentParser(description="Run tutor validation scenarios")
    parser.add_argument("--base-url", default=os.environ.get("TUTOR_BASE_URL", "http://localhost:8000"), help="Base URL of the API")
    parser.add_argument("--scenario", help="Run only this scenario ID")
    parser.add_argument("--category", help="Run only scenarios in this category")
    parser.add_argument("--list", action="store_true", help="List scenarios and exit")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    scenarios_path = script_dir / "scenarios.json"
    if not scenarios_path.exists():
        print(f"Scenarios file not found: {scenarios_path}", file=sys.stderr)
        sys.exit(1)

    data = load_scenarios(scenarios_path)
    base_url = args.base_url.rstrip("/")
    scenarios = data.get("scenarios", [])

    if args.scenario:
        scenarios = [s for s in scenarios if s["id"] == args.scenario]
        if not scenarios:
            print(f"Scenario not found: {args.scenario}", file=sys.stderr)
            sys.exit(1)
    if args.category:
        scenarios = [s for s in scenarios if s.get("category") == args.category]

    if args.list:
        for s in scenarios:
            print(f"  {s['id']}  [{s.get('category', '')}]  {s.get('name', '')}")
        return

    passed = 0
    failed = 0
    for scenario in scenarios:
        ok, failures = run_scenario(base_url, scenario)
        if ok:
            passed += 1
            print(f"PASS  {scenario['id']}  {scenario.get('name', '')}")
        else:
            failed += 1
            print(f"FAIL  {scenario['id']}  {scenario.get('name', '')}")
            for f in failures:
                print(f"      - {f}")

    print("")
    print(f"Summary: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
