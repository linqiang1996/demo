from __future__ import annotations

from pathlib import Path

from .db import Database
from .nav_parser import parse_excel_file


def bootstrap_sample_nav_data(db: Database, sample_dir: Path) -> int:
    if not sample_dir.exists():
        return 0

    existing = db.fetchone("SELECT COUNT(1) AS cnt FROM nav_records")
    if existing and int(existing["cnt"]) > 0:
        return 0

    inserted = 0
    for path in sorted(sample_dir.glob("*.xlsx")):
        if path.name.startswith("._"):
            continue
        for parsed in parse_excel_file(path):
            product_id = db.upsert_product(parsed.product_name, parsed.product_name, source="sample-excel")
            inserted += db.insert_nav_records(
                product_id,
                [(nav_date, nav_value, "sample-excel", str(path.name)) for nav_date, nav_value in parsed.records],
            )
    return inserted

