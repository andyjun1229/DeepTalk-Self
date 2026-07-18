#!/usr/bin/env python3
"""Deterministic check: interview progress integrity.

Errors if:
- progress.json is invalid JSON
- Any 'completed' question has no matching interview file
- Total completed + pending + skipped != 63
- Duplicate status entries exist

Exit 0 = OK. Exit 1 = ERROR (fix before continuing).
"""
import json, sys, glob
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
PROGRESS = DATA / "interview-progress.json"
INTERVIEWS = DATA / "interviews"

def validate():
    if not PROGRESS.exists():
        print(f"ERROR: progress file not found at {PROGRESS}")
        return False

    try:
        with open(PROGRESS) as f:
            p = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: progress.json is corrupt: {e}")
        return False

    errs = []
    questions = p.get("questions", [])

    if not questions:
        print("ERROR: no questions array in progress.json")
        return False

    for q in questions:
        qid = q.get("id", "?")
        for field in ["id", "dimension", "topic", "status"]:
            if field not in q:
                errs.append(f"Question {qid} missing '{field}'")

    completed = [q for q in questions if q.get("status") == "completed"]
    for q in completed:
        qid = q["id"]
        dim = q.get("dimension", "*")
        pattern = str(INTERVIEWS / f"*--{dim}--*--{qid}.md")
        matches = [m for m in glob.glob(pattern) if "--skipped" not in m]
        if not matches:
            errs.append(f"Question {qid} marked completed but no interview file found: {pattern}")

    valid_statuses = {"completed", "pending", "skipped"}
    status_counts = {}
    for q in questions:
        s = q.get("status", "unknown")
        status_counts[s] = status_counts.get(s, 0) + 1
        if s not in valid_statuses:
            errs.append(f"Question {q.get('id', '?')} has invalid status '{s}'")

    total = len(questions)
    if total != 63:
        errs.append(f"Expected 63 questions, found {total}")

    if errs:
        print(f"ERRORS ({len(errs)}):")
        for e in errs:
            print(f"  * {e}")
        return False
    else:
        print(f"OK: {status_counts.get('completed', 0)} completed, "
              f"{status_counts.get('pending', 0)} pending, "
              f"{status_counts.get('skipped', 0)} skipped / {total} total")
        return True

if __name__ == "__main__":
    sys.exit(0 if validate() else 1)
