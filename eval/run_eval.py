"""Run the eval cases against the agent and report accuracy, time and LLM calls.

Usage (from the repo root, with the model server running):
  python eval/run_eval.py                 # all cases
  python eval/run_eval.py --only seller   # cases whose name contains "seller"

The model is whatever llm.py points at (LLM_BASE_URL / LLM_MODEL).
Results are written to eval/results/<model>_<timestamp>.json.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))

import os  # noqa: E402

os.chdir(ROOT)  # db.py opens data/olist.duckdb relative to the working directory

import agent as agent_module  # noqa: E402
import llm  # noqa: E402
from cases import CASES  # noqa: E402

SUPERLATIVE = re.compile(r"\b(highest|peak|peaked|largest|maximum|max|top|best|most)\b", re.I)
NUMBER = re.compile(r"\d[\d,]*\.\d+|\d{1,3}(?:,\d{3})+")

# Count LLM calls without touching the agent: agent.py does `from llm import chat`.
_calls = 0
_real_chat = agent_module.chat


def _counting_chat(*args, **kwargs):
    global _calls
    _calls += 1
    return _real_chat(*args, **kwargs)


agent_module.chat = _counting_chat


def table_rows(table: str | None) -> list[list[str]]:
    """Data rows of db.format_table output (skips header, separator, captions)."""
    rows = []
    for line in (table or "").split("\n")[2:]:
        if " | " in line or (line.strip() and not line.startswith(("(", "..."))):
            rows.append([c.strip() for c in line.split(" | ")])
    return rows


def column_index(table: str, col) -> int | None:
    """`col` is an index, or text matched against the header names."""
    if isinstance(col, int):
        return col
    header = [h.strip().lower() for h in (table or "").split("\n")[0].split(" | ")]
    return next((i for i, h in enumerate(header) if col.lower() in h), None)


def run_check(check: dict, reply) -> str:
    """Return '' if the check passes, else a short reason."""
    kind = check["type"]
    if kind == "kind":
        allowed = check["kind"] if isinstance(check["kind"], list) else [check["kind"]]
        return "" if reply.kind in allowed else f"kind={reply.kind}, expected {'/'.join(allowed)}"
    if kind in ("question_has", "question_lacks"):
        # The standalone question the agent actually answered ("Interpreted as").
        q = (reply.question or "").lower()
        hits = [i for i in check["items"] if any(a.lower() in q for a in i.split("|"))]
        if kind == "question_has":
            missing = [i for i in check["items"] if i not in hits]
            return f"question missing {missing}: {reply.question[:120]}" if missing else ""
        return f"question contains {hits}: {reply.question[:120]}" if hits else ""
    if kind == "sql_has":
        missing = [i for i in check["items"] if i not in (reply.sql or "")]
        return f"SQL missing {missing}" if missing else ""
    if kind == "no_data":
        # Honest either way: CANNOT, or an answer whose table has no real values.
        if reply.kind == "cannot":
            return ""
        values = [v for r in table_rows(reply.table) for v in r]
        if reply.kind == "answer" and all(v in ("NULL", "0", "0.00", "") for v in values):
            return ""
        return f"kind={reply.kind} with data: {(reply.text or '')[:80]}"
    if reply.kind != "answer":
        return f"kind={reply.kind}: {reply.text[:80]}"

    table, text = reply.table or "", reply.text or ""
    if kind == "table_has":
        missing = [i for i in check["items"] if not any(a in table for a in i.split("|"))]
        return f"table missing {missing}" if missing else ""
    if kind == "text_has":
        missing = [i for i in check["items"] if i not in text]
        return f"text missing {missing}" if missing else ""
    if kind == "text_lacks":
        found = [i for i in check["items"] if i in text]
        return f"text contains {found}" if found else ""
    if kind == "only_values":
        col = column_index(table, check["col"])
        if col is None:
            return f"no column matching {check['col']!r}"
        values = {r[col] for r in table_rows(table) if len(r) > col}
        extra = values - set(check["allowed"])
        if not values:
            return "no values"
        return f"unexpected values {sorted(extra)[:8]}" if extra else ""
    if kind == "value_is":
        # A one-cell result must be exactly this value ("a|b" = either form).
        rows = table_rows(table)
        cell = rows[0][-1] if len(rows) == 1 else None
        return "" if cell in check["value"].split("|") else f"value {cell!r}, expected {check['value']}"
    if kind == "row_count":
        n = len(table_rows(table))
        return "" if n == check["rows"] else f"{n} rows, expected {check['rows']}"
    if kind == "superlative":
        target = check["value"]
        # The first number after each "highest/peak/..." must be the real maximum.
        for m in SUPERLATIVE.finditer(text):
            after = NUMBER.search(text, m.end())
            if after and not after.group().startswith(target):
                return f"'{m.group()}' is followed by {after.group()}, expected {target}"
        return ""
    return f"unknown check type {kind}"


def main():
    global _calls
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="run only cases whose name contains this text")
    parser.add_argument("--category", help="run only cases in this category")
    args = parser.parse_args()

    cases = [c for c in CASES if (not args.only or args.only.lower() in c["name"].lower())
             and (not args.category or c["category"] == args.category)]
    print(f"Model: {llm.MODEL} at {llm.BASE_URL}  ({len(cases)} cases)\n")

    results = []
    for case in cases:
        agent = agent_module.Agent()
        _calls = 0
        start = time.time()
        reply, reasons, turns_log = None, [], []
        try:
            for n, turn in enumerate(case["turns"], 1):
                # A turn is a message, or {"ask": message, "checks": [...]} to also
                # check that intermediate reply (multi-turn chains).
                ask = turn if isinstance(turn, str) else turn["ask"]
                reply = agent.ask(ask)
                checks = [] if isinstance(turn, str) else turn["checks"]
                if n == len(case["turns"]):
                    checks = checks + case.get("checks", [])
                turn_reasons = [f"turn {n}: {r}" if len(case["turns"]) > 1 else r
                                for r in (run_check(c, reply) for c in checks) if r]
                reasons += turn_reasons
                turns_log.append({"ask": ask, "kind": reply.kind, "question": reply.question,
                                  "sql": reply.sql, "table": reply.table, "text": reply.text,
                                  "reasons": turn_reasons})
        except Exception as e:  # noqa: BLE001 - a crash is a failed case, keep going
            reasons.append(f"crashed: {type(e).__name__}: {e}")
        secs = time.time() - start

        ok = not reasons
        tag = f" [{case['issue']}]" if case.get("issue") else ""
        print(f"{'PASS' if ok else 'FAIL'}  {secs:5.1f}s  {_calls:2d} calls  "
              f"{case['category']:<12} {case['name']}{tag}")
        for r in reasons:
            print(f"        - {r}")
        results.append({
            "case": case["name"], "category": case["category"], "issue": case.get("issue"),
            "ok": ok, "reasons": reasons, "turns": turns_log,
            "secs": round(secs, 1), "llm_calls": _calls,
            "kind": reply.kind if reply else None, "attempts": reply.attempts if reply else None,
            "question": reply.question if reply else None, "sql": reply.sql if reply else None,
            "table": reply.table if reply else None, "text": reply.text if reply else None,
        })

    passed = sum(r["ok"] for r in results)
    total_secs = sum(r["secs"] for r in results)
    total_calls = sum(r["llm_calls"] for r in results)
    print(f"\n{passed}/{len(results)} passed | {total_secs:.0f}s total | "
          f"{total_secs / max(len(results), 1):.1f}s and {total_calls / max(len(results), 1):.1f} "
          f"LLM calls per case")
    for cat in dict.fromkeys(r["category"] for r in results):
        group = [r for r in results if r["category"] == cat]
        print(f"  {cat:<12} {sum(r['ok'] for r in group)}/{len(group)}")

    out_dir = ROOT / "eval" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{llm.MODEL.replace(':', '_').replace('/', '_')}_{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps({"model": llm.MODEL, "passed": passed, "total": len(results),
                               "results": results}, indent=1))
    print(f"Saved {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
