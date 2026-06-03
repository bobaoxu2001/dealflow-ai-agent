"""Download the two source Kaggle datasets into data/raw/.

Datasets (the ONLY two sources for this project):
  1. CRM Sales Opportunities : nilkamalsaha/crm-sales-opportunities-on-google-sheets
  2. Customer Support Tickets : suraj520/customer-support-ticket-dataset

Requires `kagglehub` and Kaggle credentials (~/.kaggle/kaggle.json or
KAGGLE_USERNAME / KAGGLE_KEY env vars). If kagglehub or credentials are missing,
this prints clear instructions and exits non-zero; use `make seed-demo` to run
the project fully offline instead.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from app.utils.config import RAW_DIR
from app.utils.logging import get_logger

logger = get_logger(__name__)

CRM_DATASET = "nilkamalsaha/crm-sales-opportunities-on-google-sheets"
SUPPORT_DATASET = "suraj520/customer-support-ticket-dataset"


def _copy_tree(src: str, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for path in Path(src).rglob("*"):
        if path.is_file():
            shutil.copy2(path, dst / path.name)


def main() -> int:
    try:
        import kagglehub
    except ImportError:
        logger.error(
            "kagglehub not installed. Run `pip install kagglehub` or use `make seed-demo`."
        )
        return 1

    try:
        crm_path = kagglehub.dataset_download(CRM_DATASET)
        support_path = kagglehub.dataset_download(SUPPORT_DATASET)
    except Exception as exc:  # noqa: BLE001
        logger.error("Kaggle download failed: %s", exc)
        logger.error("Set Kaggle credentials, or run `make seed-demo` for an offline dataset.")
        return 1

    logger.info("CRM dataset path: %s", crm_path)
    logger.info("Support dataset path: %s", support_path)

    _copy_tree(crm_path, RAW_DIR / "crm")
    _copy_tree(support_path, RAW_DIR / "support")
    logger.info("Copied raw files into %s", RAW_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
