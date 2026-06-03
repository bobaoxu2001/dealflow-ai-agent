"""Inspect raw dataset files: row counts, columns, missing values, samples.

Run after `make download`. Helps verify schema before transformation.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.utils.config import RAW_DIR
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _inspect_file(path: Path) -> None:
    print("\n" + "=" * 78)
    print(f"FILE: {path.relative_to(RAW_DIR.parent)}  ({path.stat().st_size:,} bytes)")
    try:
        df = pd.read_csv(path)
    except Exception as exc:  # noqa: BLE001
        print(f"  could not read as CSV: {exc}")
        return
    print(f"  rows: {len(df):,}   columns: {len(df.columns)}")
    print(f"  columns: {list(df.columns)}")
    missing = df.isna().sum()
    missing = missing[missing > 0]
    if len(missing):
        print("  missing values:")
        for col, n in missing.items():
            print(f"    - {col}: {n} ({n / len(df):.1%})")
    else:
        print("  missing values: none")
    print("  sample rows:")
    print(df.head(3).to_string(max_colwidth=40))


def main() -> int:
    files = sorted(RAW_DIR.rglob("*.csv"))
    if not files:
        logger.warning("No CSV files under %s. Run `make download` or `make seed-demo`.", RAW_DIR)
        return 0
    for f in files:
        _inspect_file(f)
    print("\nSuggested table mappings:")
    print("  CRM: accounts.csv->accounts, sales_pipeline.csv->opportunities,")
    print("       products.csv->products, sales_teams.csv->sales_teams")
    print("  Support: *ticket*.csv->support_tickets (+ derived client/risk notes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
