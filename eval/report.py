"""Summarise eval runs into eval/RESULTS.md.

Usage:
  python eval/report.py eval/results/final.json [more runs ...]

Each file is one run of run_eval.py over the eval set. The report shows the
score, a per-category breakdown, and every case per run with its time, LLM
calls and failure reason.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(paths):
    runs = [json.loads(Path(p).read_text()) for p in paths]
    first = runs[0]
    names = [r["case"] for r in first["results"]]
    by_run = [{r["case"]: r for r in run["results"]} for run in runs]
    categories = list(dict.fromkeys(r["category"] for r in first["results"]))

    out = ["# Evaluation results", ""]
    out.append(f"- **Model:** `{first['model']}` served at `{first.get('base_url', '?')}`")
    out.append(f"- **Hardware:** {first.get('hardware', '?')}")
    out.append(f"- **Runs:** {len(runs)} ("
               + ", ".join(f"{Path(p).stem}, {run.get('started', '?')}" for p, run in zip(paths, runs))
               + ")")
    out.append("- **Command:** `python eval/run_eval.py --tag <name>` then "
               "`python eval/report.py <result files>`")
    out.append("- **Expected values** come from hand-written SQL against the database "
               "(see the comments in `eval/cases.py`); the agent hardcodes none of them.")
    out += ["", "## Score", "", "| Run | Passed | Total time | Avg per case | Avg LLM calls |",
            "|---|---|---|---|---|"]
    for p, run in zip(paths, runs):
        res = run["results"]
        secs = sum(r["secs"] for r in res)
        calls = sum(r["llm_calls"] for r in res)
        out.append(f"| {Path(p).stem} | **{sum(r['ok'] for r in res)}/{len(res)}** | "
                   f"{secs / 60:.1f} min | {secs / len(res):.1f} s | {calls / len(res):.1f} |")

    out += ["", "## By category", "", "| Category | " + " | ".join(Path(p).stem for p in paths) + " |",
            "|---|" + "---|" * len(runs)]
    for cat in categories:
        cells = []
        for run in runs:
            group = [r for r in run["results"] if r["category"] == cat]
            cells.append(f"{sum(r['ok'] for r in group)}/{len(group)}")
        out.append(f"| {cat} | " + " | ".join(cells) + " |")

    out += ["", "## Every case", "",
            "Time and LLM calls are averaged over the runs.", "",
            "| Case | Category | " + " | ".join(Path(p).stem for p in paths) + " | Time | Calls |",
            "|---|---|" + "---|" * len(runs) + "---|---|"]
    for name in names:
        rs = [b[name] for b in by_run if name in b]
        marks = " | ".join("✅" if r["ok"] else "❌" for r in rs)
        secs = sum(r["secs"] for r in rs) / len(rs)
        calls = sum(r["llm_calls"] for r in rs) / len(rs)
        out.append(f"| {name} | {rs[0]['category']} | {marks} | {secs:.0f} s | {calls:.1f} |")

    failures = [(Path(p).stem, r) for p, run in zip(paths, runs) for r in run["results"] if not r["ok"]]
    out += ["", "## Failures", ""]
    if not failures:
        out.append("None.")
    for run_name, r in failures:
        out.append(f"- **{r['case']}** ({run_name}): " + "; ".join(r["reasons"])[:300])

    target = ROOT / "eval" / "RESULTS.md"
    target.write_text("\n".join(out) + "\n")
    print(f"Wrote {target.relative_to(ROOT)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
