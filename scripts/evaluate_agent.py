"""CLI: run agent evaluation checks and print a summary table.

Usage:
    python -m scripts.evaluate_agent            # uses current DATABASE_URL
    # writes reports/evaluation_summary.json

Works against whatever data is loaded (demo seed or real Kaggle ingest). If the
database is empty, run `make seed-demo` or the Kaggle ingest pipeline first.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.db.session import SessionLocal
from app.services.evaluation_service import run_evaluation
from app.utils.config import PROJECT_ROOT
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _print_table(result: dict) -> None:
    print("\n=== DealFlow AI Agent — Evaluation Summary ===")
    print(f"{'check':32s} {'passed':8s} detail")
    print("-" * 72)
    for c in result["checks"]:
        detail_keys = [k for k in c if k not in {"name", "passed"}]
        detail = ", ".join(f"{k}={c[k]}" for k in detail_keys)
        mark = "PASS" if c["passed"] else "FAIL"
        print(f"{c['name']:32s} {mark:8s} {detail[:120]}")
    s = result["summary"]
    print("-" * 72)
    print(f"TOTAL: {s['passed']}/{s['checks']} checks passed "
          f"({'ALL PASSED' if s['all_passed'] else 'SOME FAILED'})")


def main() -> int:
    session = SessionLocal()
    try:
        result = run_evaluation(session)
    finally:
        session.close()

    _print_table(result)

    out_dir = Path(PROJECT_ROOT) / "reports"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "evaluation_summary.json"
    out_path.write_text(json.dumps(result, indent=2))
    logger.info("Wrote evaluation report to %s", out_path)
    return 0 if result["summary"]["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
